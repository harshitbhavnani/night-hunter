from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

from src.config import AppSettings
from src.jobs.run_scan import run_scan
from src.jobs.watch_shortlist import watch_shortlist
from src.providers.base import BaseMarketDataProvider, ProviderMessageHandler


class FakeBasicProvider(BaseMarketDataProvider):
    def __init__(self, count: int = 80) -> None:
        self.symbols = [f"T{i:03d}" for i in range(count)]
        self.asset_calls = 0
        self.daily_bar_calls = 0
        self.minute_bar_calls = 0
        self.snapshot_calls = 0
        self.news_symbol_counts: list[int] = []

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
        return {symbol: _minute_bars() for symbol in symbols}

    def get_latest_bars(self, symbols: Sequence[str]):
        return {}

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
    assert result["trade_card"]["data_confidence"] == "Basic/IEX"


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
