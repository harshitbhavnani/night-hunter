from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.config import AppSettings
from src.providers.alpaca_provider import AlpacaProvider
from src.providers.base import BaseMarketDataProvider
from src.providers.robinhood_crypto_provider import RobinhoodCryptoProvider, alpaca_to_robinhood_symbol


def test_alpaca_provider_implements_crypto_contract_with_mocked_api(monkeypatch) -> None:
    provider = AlpacaProvider(
        AppSettings(
            alpaca_api_key="key",
            alpaca_secret_key="secret",
            provider_mode="live",
            crypto_symbols=("BTC/USD",),
            crypto_location="us",
        )
    )
    assert isinstance(provider, BaseMarketDataProvider)

    paths: list[str] = []

    def fake_data(path: str, params: dict[str, object]) -> object:
        paths.append(path)
        assert params["symbols"] == "BTC/USD"
        if path == "/v1beta3/crypto/us/bars":
            return {"bars": {"BTC/USD": [{"t": "2026-01-01T00:00:00Z", "o": 100, "h": 105, "l": 99, "c": 104, "v": 10}]}}
        if path == "/v1beta3/crypto/us/latest/bars":
            return {"bars": {"BTC/USD": {"t": "2026-01-01T00:00:00Z", "c": 104, "v": 10}}}
        if path == "/v1beta3/crypto/us/latest/trades":
            return {"trades": {"BTC/USD": {"p": 104}}}
        if path == "/v1beta3/crypto/us/latest/quotes":
            return {"quotes": {"BTC/USD": {"bp": 103.9, "ap": 104.1}}}
        if path == "/v1beta3/crypto/us/latest/orderbooks":
            return {"orderbooks": {"BTC/USD": {"bids": [{"p": 103.9, "s": 1}], "asks": [{"p": 104.1, "s": 1}]}}}
        raise AssertionError(path)

    monkeypatch.setattr(provider, "_get_data", fake_data)

    def fake_trading(path: str, params: dict[str, object]) -> object:
        assert path == "/v2/assets"
        assert params["asset_class"] == "crypto"
        return [{"symbol": "BTC/USD", "asset_class": "crypto", "status": "active", "tradable": True}]

    monkeypatch.setattr(provider, "_get_trading", fake_trading)

    symbols = ["BTC/USD"]
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=45)

    assert provider.get_assets()[0]["symbol"] == "BTC/USD"
    assert provider.get_assets()[0]["asset_class"] == "crypto"
    assert "BTC/USD" in provider.get_historical_bars(symbols, "1Min", start, end)
    assert "BTC/USD" in provider.get_snapshots(symbols)
    assert provider.get_snapshots(symbols)["BTC/USD"]["latestQuote"]["bp"] == 103.9
    assert provider.get_orderbooks(symbols)["BTC/USD"]["bids"][0]["p"] == 103.9
    assert provider.get_historical_news(symbols, start, end) == {"BTC/USD": []}
    assert "BTC/USD" in provider.get_latest_bars(symbols)
    assert "/v1beta3/crypto/us/bars" in paths
    assert "/v1beta3/crypto/us/latest/trades" in paths
    assert "/v1beta3/crypto/us/latest/orderbooks" in paths


def test_robinhood_crypto_provider_normalizes_products_and_quotes(monkeypatch) -> None:
    provider = RobinhoodCryptoProvider(
        AppSettings(
            robinhood_crypto_api_key="key",
            robinhood_crypto_private_key="secret",
        )
    )
    paths: list[str] = []

    def fake_request(method: str, path: str, body: str = "") -> object:
        paths.append(path)
        if path == "/api/v1/crypto/trading/trading_pairs/":
            return {"results": [{"symbol": "BTC-USD", "tradable": True}]}
        if path.startswith("/api/v1/crypto/marketdata/best_bid_ask/"):
            return {
                "results": [
                    {
                        "symbol": "BTC-USD",
                        "bid_price": "100.00",
                        "ask_price": "100.20",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                ]
            }
        raise AssertionError(path)

    monkeypatch.setattr(provider, "_request", fake_request)

    products = provider.get_products(["BTC/USD"])
    quotes = provider.get_quotes(["BTC/USD"])

    assert alpaca_to_robinhood_symbol("BTC/USD") == "BTC-USD"
    assert products["BTC/USD"]["tradable"] is True
    assert quotes["BTC/USD"]["ask"] == 100.2
    assert quotes["BTC/USD"]["spread_pct"] > 0
    assert "/api/v1/crypto/trading/trading_pairs/" in paths
