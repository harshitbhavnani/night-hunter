from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping, Sequence

from src.config import AppSettings
from src.jobs.run_scan import run_scan
from src.jobs.watch_shortlist import watch_shortlist
from src.providers.base import BaseMarketDataProvider, ProviderMessageHandler


class FakeBasicProvider(BaseMarketDataProvider):
    def __init__(self, count: int = 80, minute_bars: list[Mapping[str, object]] | None = None) -> None:
        self.symbols = [f"T{i:03d}" for i in range(count)]
        self._minute_bars = minute_bars
        self.asset_calls = 0
        self.daily_bar_calls = 0
        self.minute_bar_calls = 0
        self.snapshot_calls = 0
        self.news_symbol_counts: list[int] = []
        self.minute_bar_windows: list[tuple[datetime, datetime]] = []

    def get_assets(self) -> list[Mapping[str, object]]:
        self.asset_calls += 1
        return [
            {
                "symbol": symbol,
                "name": f"{symbol} Common Inc",
                "asset_class": "us_equity",
                "status": "active",
                "tradable": True,
                "exchange": "NASDAQ",
            }
            for symbol in self.symbols
        ]

    def get_historical_bars(self, symbols: Sequence[str], timeframe: str, start: datetime, end: datetime):
        if timeframe == "1Day":
            self.daily_bar_calls += 1
            return {symbol: [{"c": 10.0, "v": 800000} for _ in range(30)] for symbol in symbols}
        self.minute_bar_calls += 1
        self.minute_bar_windows.append((start, end))
        return {symbol: (self._minute_bars if self._minute_bars is not None else _minute_bars()) for symbol in symbols}

    def get_latest_bars(self, symbols: Sequence[str]):
        return {}

    def get_market_calendar(self, start: datetime, end: datetime):
        return [{"date": "2026-04-24", "open": "09:30", "close": "16:00"}]

    def get_snapshots(self, symbols: Sequence[str]):
        self.snapshot_calls += 1
        return {
            symbol: {
                "latestTrade": {"p": 10.5},
                "latestQuote": {"bp": 10.49, "ap": 10.51},
                "dailyBar": {"c": 10.5},
                "prevDailyBar": {"c": 10.0},
            }
            for symbol in symbols
        }

    def stream_bars(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        self.streamed_symbols = list(symbols)

    def stream_trades(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        raise NotImplementedError

    def stream_quotes(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        raise NotImplementedError

    def get_historical_news(self, symbols: Sequence[str], start: datetime, end: datetime):
        self.news_symbol_counts.append(len(symbols))
        return {symbol: [] for symbol in symbols}

    def stream_news(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        raise NotImplementedError


def test_basic_scan_uses_daily_cache_and_fetches_news_after_coarse_ranking() -> None:
    provider = FakeBasicProvider(count=80)
    settings = AppSettings(
        alpaca_api_key="key",
        alpaca_secret_key="secret",
        provider_mode="live",
        alpaca_feed="iex",
        shortlist_size=10,
        basic_news_candidate_count=60,
    )

    first = run_scan(provider=provider, settings=settings, persist=False)
    second = run_scan(provider=provider, settings=settings, persist=False)

    assert provider.asset_calls == 1
    assert provider.daily_bar_calls == 1
    assert provider.minute_bar_calls == 2
    assert provider.snapshot_calls == 2
    assert provider.news_symbol_counts == [60, 60]
    assert len(first["rows"]) == 10
    assert len(second["rows"]) == 10
    assert first["diagnostics"]["assets_loaded"] == 80
    assert first["diagnostics"]["common_stock_count"] == 80
    assert first["diagnostics"]["universe_size"] == 80
    assert first["diagnostics"]["feature_rows"] == 80
    assert second["diagnostics"]["cache_source"] == "hit"
    assert first["diagnostics"]["scan_mode"] == "last_session"
    assert first["diagnostics"]["scan_window_label"] == "Last regular session: 2026-04-24 14:30-16:00 ET"
    assert provider.minute_bar_windows[0] == (
        datetime(2026, 4, 24, 18, 30, tzinfo=timezone.utc),
        datetime(2026, 4, 24, 20, 0, tzinfo=timezone.utc),
    )


def test_basic_scan_labels_rows_and_trade_card_as_iex() -> None:
    provider = FakeBasicProvider(count=8)
    settings = AppSettings(
        alpaca_api_key="key",
        alpaca_secret_key="secret",
        provider_mode="live",
        alpaca_feed="iex",
        shortlist_size=5,
    )

    result = run_scan(provider=provider, settings=settings, persist=False)

    assert result["feed"] == "iex"
    assert result["data_confidence"] == "Basic/IEX"
    assert all(row["feed"] == "iex" for row in result["rows"])
    assert all(row["limitations"] == "Not consolidated SIP tape" for row in result["rows"])
    assert result["rows"][0]["settings_snapshot"]["alpaca_feed"] == "iex"
    assert result["rows"][0]["settings_snapshot"]["basic_min_iex_avg_daily_volume"] == 10000.0
    assert result["trade_card"]["data_confidence"] == "Basic/IEX"
    assert result["trade_card"]["settings_snapshot"]["data_confidence"] == "Basic/IEX"
    assert result["diagnostics"]["volume_floor"] == 10000.0


def test_empty_scan_returns_diagnostics_without_candidates() -> None:
    provider = FakeBasicProvider(count=5, minute_bars=[])
    settings = AppSettings(
        alpaca_api_key="key",
        alpaca_secret_key="secret",
        provider_mode="live",
        alpaca_feed="iex",
        shortlist_size=5,
    )

    result = run_scan(provider=provider, settings=settings, persist=False)

    assert result["rows"] == []
    assert result["trade_card"] is None
    assert result["diagnostics"]["universe_size"] == 5
    assert result["diagnostics"]["symbols_with_1min_bars"] == 0
    assert result["diagnostics"]["feature_rows"] == 0
    assert result["diagnostics"]["shortlist_size"] == 0
    assert result["diagnostics"]["news_symbols_fetched"] == 0
    assert result["diagnostics"]["scan_window_start"] == "2026-04-24T18:30:00+00:00"


def test_watch_shortlist_caps_streamed_symbols_at_30() -> None:
    provider = FakeBasicProvider(count=40)

    watch_shortlist(provider, [f"T{i:03d}" for i in range(40)], lambda _: None)

    assert len(provider.streamed_symbols) == 30
    assert provider.streamed_symbols[0] == "T000"
    assert provider.streamed_symbols[-1] == "T029"


def _minute_bars() -> list[dict[str, object]]:
    bars = []
    price = 10.0
    for minute in range(90):
        close = price * 1.001
        bars.append(
            {
                "t": f"2026-01-01T14:{minute % 60:02d}:00Z",
                "o": price,
                "h": close * 1.001,
                "l": price * 0.999,
                "c": close,
                "v": 20000 + minute * 100,
            }
        )
        price = close
    return bars
