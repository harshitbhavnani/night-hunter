from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

from src.providers.base import BaseMarketDataProvider, ProviderMessageHandler
from src.universe.build_universe import build_universe


class FakeUniverseProvider(BaseMarketDataProvider):
    def get_assets(self) -> list[Mapping[str, object]]:
        return [
            {"symbol": "GOOD", "name": "Good Common Inc", "asset_class": "us_equity", "status": "active", "tradable": True, "exchange": "NASDAQ"},
            {"symbol": "LOWV", "name": "Low Volume Inc", "asset_class": "us_equity", "status": "active", "tradable": True, "exchange": "NYSE"},
            {"symbol": "FUND", "name": "Example ETF", "asset_class": "us_equity", "status": "active", "tradable": True, "exchange": "NYSE"},
            {"symbol": "OTC", "name": "OTC Common", "asset_class": "us_equity", "status": "active", "tradable": True, "exchange": "OTC"},
        ]

    def get_historical_bars(self, symbols: Sequence[str], timeframe: str, start: datetime, end: datetime):
        return {
            "GOOD": [{"v": 800000} for _ in range(30)],
            "LOWV": [{"v": 100000} for _ in range(30)],
        }

    def get_latest_bars(self, symbols: Sequence[str]):
        return {}

    def get_snapshots(self, symbols: Sequence[str]):
        return {
            "GOOD": {"latestTrade": {"p": 12}},
            "LOWV": {"latestTrade": {"p": 10}},
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

    assert [row["symbol"] for row in rows] == ["GOOD"]
    assert "market_cap" not in rows[0]
