from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

from src.config import AppSettings
from src.providers.base import BaseMarketDataProvider, ProviderMessageHandler
from src.storage.repositories import row_value
from src.universe.build_universe import build_universe


class FakeCryptoUniverseProvider(BaseMarketDataProvider):
    def __init__(self) -> None:
        self.asset_calls = 0

    def get_assets(self) -> list[Mapping[str, object]]:
        self.asset_calls += 1
        return [
            {"symbol": "BTC/USD", "asset_class": "crypto", "status": "active", "tradable": True},
            {"symbol": "ETH/USD", "asset_class": "crypto", "status": "active", "tradable": True},
            {"symbol": "ZERO/USD", "asset_class": "crypto", "status": "active", "tradable": True},
            {"symbol": "BTC/EUR", "asset_class": "crypto", "status": "active", "tradable": True},
            {"symbol": "OLD/USD", "asset_class": "crypto", "status": "inactive", "tradable": True},
            {"symbol": "LOCK/USD", "asset_class": "crypto", "status": "active", "tradable": False},
            {"symbol": "TEST", "asset_class": "us_equity", "status": "active", "tradable": True},
        ]

    def get_historical_bars(self, symbols: Sequence[str], timeframe: str, start: datetime, end: datetime):
        return {
            "BTC/USD": [{"c": 60_000, "v": 3} for _ in range(3)],
            "ETH/USD": [{"c": 3_000, "v": 20} for _ in range(3)],
            "ZERO/USD": [{"c": 1, "v": 0} for _ in range(3)],
        }

    def get_latest_bars(self, symbols: Sequence[str]):
        return {}

    def get_market_calendar(self, start: datetime, end: datetime):
        raise AssertionError("Crypto universe should not need calendar.")

    def get_snapshots(self, symbols: Sequence[str]):
        return {}

    def get_orderbooks(self, symbols: Sequence[str]):
        return {}

    def stream_bars(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        raise NotImplementedError

    def stream_trades(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        raise NotImplementedError

    def stream_quotes(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        raise NotImplementedError

    def get_historical_news(self, symbols: Sequence[str], start: datetime, end: datetime):
        return {}

    def stream_news(self, symbols: Sequence[str], on_message: ProviderMessageHandler) -> None:
        raise NotImplementedError


def test_build_universe_discovers_active_tradable_usd_crypto_pairs() -> None:
    rows = build_universe(
        provider=FakeCryptoUniverseProvider(),
        settings=AppSettings(crypto_symbols=("DOGE/USD",), crypto_min_quote_volume=50_000),
    )

    assert [row["symbol"] for row in rows] == ["BTC/USD", "ETH/USD"]
    assert all(row["asset_class"] == "crypto" for row in rows)
    assert rows[0]["avg_daily_volume_source"] == "alpaca_crypto"
    assert "market_cap" not in rows[0]


def test_build_universe_uses_safe_fallback_when_discovery_fails() -> None:
    rows = build_universe(
        provider=FailingCryptoUniverseProvider(),
        settings=AppSettings(crypto_symbols=("BTC/USD", "ETH/USD"), crypto_min_quote_volume=50_000),
        use_cache=False,
    )

    assert [row["symbol"] for row in rows] == ["BTC/USD", "ETH/USD"]


def test_empty_crypto_universe_is_not_cached() -> None:
    provider = EmptyCryptoUniverseProvider()
    settings = AppSettings(crypto_symbols=("ZERO/USD",), crypto_min_quote_volume=50_000)

    first = build_universe(provider=provider, settings=settings)
    second = build_universe(provider=provider, settings=settings)

    assert first == []
    assert second == []
    assert provider.asset_calls == 2


def test_tuple_row_value_reads_selected_payload_column() -> None:
    row = ("2026-04-24T00:00:00+00:00", '{"rows": []}')

    assert row_value(row, "payload_json", 1) == '{"rows": []}'


class EmptyCryptoUniverseProvider(FakeCryptoUniverseProvider):
    def get_assets(self) -> list[Mapping[str, object]]:
        self.asset_calls += 1
        return [{"symbol": "ZERO/USD", "asset_class": "crypto", "status": "active", "tradable": True}]

    def get_historical_bars(self, symbols: Sequence[str], timeframe: str, start: datetime, end: datetime):
        return {"ZERO/USD": [{"c": 10, "v": 0} for _ in range(3)]}


class FailingCryptoUniverseProvider(FakeCryptoUniverseProvider):
    def get_assets(self) -> list[Mapping[str, object]]:
        self.asset_calls += 1
        raise RuntimeError("asset discovery unavailable")
