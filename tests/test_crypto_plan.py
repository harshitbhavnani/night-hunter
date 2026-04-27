from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Mapping, Sequence

from src.config import AppSettings
from src.jobs.run_scan import run_scan
from src.jobs.watch_shortlist import watch_shortlist
from src.providers.base import BaseMarketDataProvider, ProviderMessageHandler


class FakeCryptoProvider(BaseMarketDataProvider):
    def __init__(self, count: int = 8, minute_bars: list[Mapping[str, object]] | None = None) -> None:
        self.symbols = ["BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD", "LINK/USD", "UNI/USD", "AAVE/USD", "DOGE/USD"][:count]
        self._minute_bars = minute_bars
        self.asset_calls = 0
        self.daily_bar_calls = 0
        self.minute_bar_calls = 0
        self.snapshot_calls = 0
        self.orderbook_calls = 0
        self.news_calls = 0
        self.minute_bar_windows: list[tuple[datetime, datetime]] = []

    def get_assets(self) -> list[Mapping[str, object]]:
        self.asset_calls += 1
        return [
            {"symbol": symbol, "asset_class": "crypto", "status": "active", "tradable": True}
            for symbol in self.symbols
        ]

    def get_historical_bars(self, symbols: Sequence[str], timeframe: str, start: datetime, end: datetime):
        if timeframe == "1Day":
            self.daily_bar_calls += 1
            return {symbol: [{"c": 100.0 + index, "v": 1000 + index * 100} for _ in range(3)] for index, symbol in enumerate(symbols)}
        self.minute_bar_calls += 1
        self.minute_bar_windows.append((start, end))
        return {symbol: (self._minute_bars if self._minute_bars is not None else _minute_bars()) for symbol in symbols}

    def get_latest_bars(self, symbols: Sequence[str]):
        return {}

    def get_market_calendar(self, start: datetime, end: datetime):
        raise AssertionError("Crypto scan should not request the equity market calendar.")

    def get_snapshots(self, symbols: Sequence[str]):
        self.snapshot_calls += 1
        return {
            symbol: {
                "latestTrade": {"p": 105.0},
                "latestQuote": {"bp": 104.95, "ap": 105.05},
                "dailyBar": {"c": 105.0},
            }
            for symbol in symbols
        }

    def get_orderbooks(self, symbols: Sequence[str]):
        self.orderbook_calls += 1
        return {
            symbol: {
                "bids": [{"p": 104.9, "s": 500}, {"p": 104.8, "s": 500}],
                "asks": [{"p": 105.1, "s": 500}, {"p": 105.2, "s": 500}],
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
        self.news_calls += 1
        return {symbol: [] for symbol in symbols}

    def stream_news(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        raise NotImplementedError


class FakeVenueProvider:
    def __init__(
        self,
        tradable: bool = True,
        bid: float = 104.95,
        ask: float = 105.05,
        depth_notional: float = 75_000,
    ) -> None:
        self.tradable = tradable
        self.bid = bid
        self.ask = ask
        self.depth_notional = depth_notional

    def get_products(self, symbols: Sequence[str]):
        return {
            symbol: {"symbol": symbol, "venue_symbol": symbol.replace("BTC", "XBT"), "tradable": self.tradable}
            for symbol in symbols
        }

    def get_quotes(self, symbols: Sequence[str]):
        now = datetime.now(timezone.utc).isoformat()
        mid = (self.bid + self.ask) / 2
        spread_pct = (self.ask - self.bid) / mid * 100
        return {
            symbol: {
                "symbol": symbol,
                "venue_symbol": symbol.replace("BTC", "XBT"),
                "bid": self.bid,
                "ask": self.ask,
                "mid": mid,
                "spread_pct": spread_pct,
                "quote_time": now,
            }
            for symbol in symbols
        }

    def get_orderbooks(self, symbols: Sequence[str]):
        return {
            symbol: {
                "symbol": symbol,
                "venue_symbol": symbol.replace("BTC", "XBT"),
                "venue_depth_notional": self.depth_notional,
                "venue_depth_bid_notional": self.depth_notional,
                "venue_depth_ask_notional": self.depth_notional,
                "venue_depth_bps": 25,
                "quote_time": datetime.now(timezone.utc).isoformat(),
            }
            for symbol in symbols
        }


def test_crypto_scan_uses_daily_cache_and_skips_news() -> None:
    provider = FakeCryptoProvider(count=8)
    venue = FakeVenueProvider()
    settings = AppSettings(
        alpaca_api_key="key",
        alpaca_secret_key="secret",
        provider_mode="live",
        crypto_symbols=tuple(provider.symbols),
        shortlist_size=5,
        min_score=1.0,
    )

    first = run_scan(provider=provider, venue_provider=venue, settings=settings, persist=False)
    second = run_scan(provider=provider, venue_provider=venue, settings=settings, persist=False)

    assert provider.asset_calls == 1
    assert provider.daily_bar_calls == 1
    assert provider.minute_bar_calls == 2
    assert provider.snapshot_calls == 2
    assert provider.orderbook_calls == 2
    assert provider.news_calls == 0
    assert len(first["rows"]) == 5
    assert len(second["rows"]) == 5
    assert first["diagnostics"]["configured_pair_count"] == 8
    assert first["diagnostics"]["usd_pair_count"] == 8
    assert first["diagnostics"]["universe_size"] == 8
    assert first["diagnostics"]["feature_rows"] == 8
    assert first["diagnostics"]["alpaca_depth_eligible_count"] == 8
    assert first["diagnostics"]["venue_quote_status"] == "ok"
    assert first["diagnostics"]["venue_quote_count"] == 8
    assert first["diagnostics"]["final_trading_universe_size"] == 8
    assert second["diagnostics"]["cache_source"] == "hit"
    assert first["diagnostics"]["scan_mode"] == "crypto_rolling"
    start, end = provider.minute_bar_windows[0]
    assert end - start == timedelta(minutes=90)


def test_crypto_scan_labels_rows_and_trade_card_as_alpaca_crypto() -> None:
    provider = FakeCryptoProvider(count=5)
    venue = FakeVenueProvider()
    settings = AppSettings(
        alpaca_api_key="key",
        alpaca_secret_key="secret",
        provider_mode="live",
        crypto_symbols=tuple(provider.symbols),
        shortlist_size=5,
        min_score=1.0,
    )

    result = run_scan(provider=provider, venue_provider=venue, settings=settings, persist=False)

    assert result["feed"] == "crypto"
    assert result["data_confidence"] == "Alpaca Crypto"
    assert all(row["feed"] == "crypto" for row in result["rows"])
    assert all(row["limitations"] == "Venue-specific crypto data; not consolidated global tape." for row in result["rows"])
    assert result["rows"][0]["settings_snapshot"]["market_mode"] == "crypto"
    assert result["trade_card"]["data_confidence"] == "Alpaca Crypto"
    assert result["trade_card"]["verdict"] == "Valid Trade"
    assert result["trade_card"]["venue_ask"] == 105.05
    assert result["trade_card"]["venue_depth_notional"] >= settings.kraken_min_orderbook_notional_depth
    assert result["trade_card"]["alpaca_depth_notional"] >= settings.crypto_min_orderbook_notional_depth
    assert result["trade_card"]["settings_snapshot"]["data_confidence"] == "Alpaca Crypto"
    assert result["diagnostics"]["min_quote_volume"] == 50000.0


def test_crypto_scan_missing_kraken_quote_returns_invalid_venue_rows() -> None:
    provider = FakeCryptoProvider(count=3)
    settings = AppSettings(
        alpaca_api_key="key",
        alpaca_secret_key="secret",
        provider_mode="live",
        crypto_symbols=tuple(provider.symbols),
        shortlist_size=3,
    )

    result = run_scan(provider=provider, venue_provider=EmptyVenueProvider(), settings=settings, persist=False)

    assert result["rows"]
    assert result["diagnostics"]["venue_quote_status"] == "ok"
    assert result["trade_card"]["verdict"] == "Invalid"
    assert "Kraken venue confirmation missing." in result["trade_card"]["veto_reasons"]


def test_empty_crypto_scan_returns_diagnostics_without_candidates() -> None:
    provider = FakeCryptoProvider(count=5, minute_bars=[])
    settings = AppSettings(
        alpaca_api_key="key",
        alpaca_secret_key="secret",
        provider_mode="live",
        crypto_symbols=tuple(provider.symbols),
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


def test_low_depth_pairs_are_excluded_before_ranking() -> None:
    provider = FakeCryptoProvider(count=3)

    def thin_orderbooks(symbols: Sequence[str]):
        return {
            symbol: {
                "bids": [{"p": 104.9, "s": 1}],
                "asks": [{"p": 105.1, "s": 1}],
            }
            for symbol in symbols
        }

    provider.get_orderbooks = thin_orderbooks  # type: ignore[method-assign]
    settings = AppSettings(
        alpaca_api_key="key",
        alpaca_secret_key="secret",
        provider_mode="live",
        crypto_symbols=tuple(provider.symbols),
        shortlist_size=3,
        min_score=1.0,
        crypto_min_orderbook_notional_depth=25_000,
    )

    result = run_scan(provider=provider, venue_provider=FakeVenueProvider(), settings=settings, persist=False)

    assert result["rows"] == []
    assert result["diagnostics"]["feature_rows"] == 3
    assert result["diagnostics"]["alpaca_depth_eligible_count"] == 0
    assert result["diagnostics"]["final_trading_universe_size"] == 0


def test_watch_shortlist_caps_streamed_symbols_at_30() -> None:
    provider = FakeCryptoProvider(count=8)

    watch_shortlist(provider, [f"PAIR{i}/USD" for i in range(40)], lambda _: None)

    assert len(provider.streamed_symbols) == 30
    assert provider.streamed_symbols[0] == "PAIR0/USD"
    assert provider.streamed_symbols[-1] == "PAIR29/USD"


class EmptyVenueProvider(FakeVenueProvider):
    def get_products(self, symbols: Sequence[str]):
        return {}

    def get_quotes(self, symbols: Sequence[str]):
        return {}

    def get_orderbooks(self, symbols: Sequence[str]):
        return {}


def _minute_bars() -> list[dict[str, object]]:
    bars = []
    price = 100.0
    now = datetime.now(timezone.utc) - timedelta(minutes=90)
    for minute in range(90):
        close = price * 1.001
        bars.append(
            {
                "t": (now + timedelta(minutes=minute)).isoformat(),
                "o": price,
                "h": close * 1.001,
                "l": price * 0.999,
                "c": close,
                "v": 80 + minute,
            }
        )
        price = close
    return bars
