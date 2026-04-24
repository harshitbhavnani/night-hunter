from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.config import AppSettings
from src.providers.alpaca_provider import AlpacaProvider
from src.providers.base import BaseMarketDataProvider


def test_alpaca_provider_implements_contract_with_mocked_api(monkeypatch) -> None:
    provider = AlpacaProvider(
        AppSettings(
            alpaca_api_key="key",
            alpaca_secret_key="secret",
            provider_mode="live",
        )
    )
    assert isinstance(provider, BaseMarketDataProvider)

    def fake_trading(path: str, params: dict[str, object]) -> object:
        assert path == "/v2/assets"
        return [{"symbol": "TEST", "asset_class": "us_equity", "status": "active", "tradable": True}]

    def fake_data(path: str, params: dict[str, object]) -> object:
        if path == "/v2/stocks/bars":
            return {"bars": {"TEST": [{"t": "2026-01-01T14:30:00Z", "o": 10, "h": 11, "l": 9, "c": 10.5, "v": 1000}]}}
        if path == "/v2/stocks/snapshots":
            return {"TEST": {"latestTrade": {"p": 10.5}}}
        if path == "/v1beta1/news":
            return {"news": [{"headline": "Contract award", "symbols": ["TEST"]}]}
        if path == "/v2/stocks/bars/latest":
            return {"bars": {"TEST": {"t": "2026-01-01T14:30:00Z", "c": 10.5}}}
        raise AssertionError(path)

    monkeypatch.setattr(provider, "_get_trading", fake_trading)
    monkeypatch.setattr(provider, "_get_data", fake_data)

    symbols = ["TEST"]
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=45)

    assert provider.get_assets()[0]["symbol"] == "TEST"
    assert "TEST" in provider.get_historical_bars(symbols, "1Min", start, end)
    assert "TEST" in provider.get_snapshots(symbols)
    assert "TEST" in provider.get_historical_news(symbols, start, end)
    assert "TEST" in provider.get_latest_bars(symbols)
