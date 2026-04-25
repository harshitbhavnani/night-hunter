from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

from src.config import AppSettings
from src.providers.base import BaseMarketDataProvider, ProviderMessageHandler
from src.storage.repositories import row_value
from src.universe.build_universe import build_universe


class FakeUniverseProvider(BaseMarketDataProvider):
    def get_assets(self) -> list[Mapping[str, object]]:
        return [
            {"symbol": "GOOD", "name": "Good Common Inc", "asset_class": "us_equity", "status": "active", "tradable": True, "exchange": "NASDAQ"},
            {"symbol": "LOWV", "name": "Low Volume Inc", "asset_class": "us_equity", "status": "active", "tradable": True, "exchange": "NYSE"},
            {"symbol": "ZEROV", "name": "Zero Volume Inc", "asset_class": "us_equity", "status": "active", "tradable": True, "exchange": "NYSE"},
            {"symbol": "FUND", "name": "Example ETF", "asset_class": "us_equity", "status": "active", "tradable": True, "exchange": "NYSE"},
            {"symbol": "OTC", "name": "OTC Common", "asset_class": "us_equity", "status": "active", "tradable": True, "exchange": "OTC"},
        ]

    def get_historical_bars(self, symbols: Sequence[str], timeframe: str, start: datetime, end: datetime):
        return {
            "GOOD": [{"c": 12, "v": 800000} for _ in range(30)],
            "LOWV": [{"c": 10, "v": 100000} for _ in range(30)],
            "ZEROV": [{"c": 8, "v": 0} for _ in range(30)],
        }

    def get_latest_bars(self, symbols: Sequence[str]):
        return {}

    def get_market_calendar(self, start: datetime, end: datetime):
        return [{"date": "2026-04-24", "open": "09:30", "close": "16:00"}]

    def get_snapshots(self, symbols: Sequence[str]):
        return {
            "GOOD": {"latestTrade": {"p": 12}},
            "LOWV": {"latestTrade": {"p": 10}},
            "ZEROV": {"latestTrade": {"p": 8}},
        }

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


def test_build_universe_uses_alpaca_only_filters_without_market_cap() -> None:
    rows = build_universe(provider=FakeUniverseProvider())

    assert [row["symbol"] for row in rows] == ["GOOD", "LOWV"]
    assert "market_cap" not in rows[0]
    assert rows[0]["avg_daily_volume_source"] == "iex"


def test_basic_iex_universe_allows_low_but_real_iex_volume() -> None:
    rows = build_universe(provider=FakeUniverseProvider(), settings=AppSettings(alpaca_feed="iex"))

    assert [row["symbol"] for row in rows] == ["GOOD", "LOWV"]
    assert "ZEROV" not in {row["symbol"] for row in rows}


def test_sip_universe_preserves_strict_adv_filter() -> None:
    rows = build_universe(provider=FakeUniverseProvider(), settings=AppSettings(alpaca_feed="sip"))

    assert [row["symbol"] for row in rows] == ["GOOD"]


def test_empty_universe_is_not_cached() -> None:
    provider = EmptyUniverseProvider()
    settings = AppSettings(alpaca_feed="iex")

    first = build_universe(provider=provider, settings=settings)
    second = build_universe(provider=provider, settings=settings)

    assert first == []
    assert second == []
    assert provider.asset_calls == 2


def test_tuple_row_value_reads_selected_payload_column() -> None:
    row = ("2026-04-24T00:00:00+00:00", '{"rows": []}')

    assert row_value(row, "payload_json", 1) == '{"rows": []}'


class EmptyUniverseProvider(FakeUniverseProvider):
    def __init__(self) -> None:
        self.asset_calls = 0

    def get_assets(self) -> list[Mapping[str, object]]:
        self.asset_calls += 1
        return [
            {"symbol": "ZERO", "name": "Zero Common Inc", "asset_class": "us_equity", "status": "active", "tradable": True, "exchange": "NASDAQ"}
        ]

    def get_historical_bars(self, symbols: Sequence[str], timeframe: str, start: datetime, end: datetime):
        return {"ZERO": [{"c": 10, "v": 0} for _ in range(30)]}
