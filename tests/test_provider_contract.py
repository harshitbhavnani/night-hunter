from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.config import AppSettings
from src.providers.alpaca_provider import AlpacaProvider
from src.providers.base import BaseMarketDataProvider
from src.providers.kraken_venue_provider import KrakenVenueProvider, _normalize_alpaca_symbol


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


def test_kraken_venue_provider_normalizes_products_quotes_and_depth(monkeypatch) -> None:
    provider = KrakenVenueProvider(AppSettings())
    paths: list[str] = []

    def fake_request(path: str, params: dict[str, object]) -> object:
        paths.append(path)
        if path == "AssetPairs":
            return {
                "error": [],
                "result": {
                    "XXBTZUSD": {"altname": "XBTUSD", "wsname": "XBT/USD", "status": "online"},
                    "XETHZUSD": {"altname": "ETHUSD", "wsname": "ETH/USD", "status": "online"},
                    "XDGUSD": {"altname": "XDGUSD", "wsname": "XDG/USD", "status": "online"},
                    "XXBTZEUR": {"altname": "XBTEUR", "wsname": "XBT/EUR", "status": "online"},
                    "LOCKUSD": {"altname": "LOCKUSD", "wsname": "LOCK/USD", "status": "cancel_only"},
                },
            }
        if path == "Ticker":
            assert params["pair"] == "XXBTZUSD,XDGUSD,LOCKUSD"
            return {
                "error": [],
                "result": {
                    "XXBTZUSD": {"a": ["100.20", "1", "1"], "b": ["100.00", "1", "1"], "c": ["100.10", "1"]},
                    "XDGUSD": {"a": ["0.2005", "1", "1"], "b": ["0.1995", "1", "1"], "c": ["0.2000", "1"]},
                    "LOCKUSD": {"a": ["1.01", "1", "1"], "b": ["1.00", "1", "1"], "c": ["1.005", "1"]},
                },
            }
        if path == "Depth":
            return {
                "error": [],
                "result": {
                    str(params["pair"]): {
                        "bids": [["100.00", "300", "1770000000.0"]],
                        "asks": [["100.20", "250", "1770000000.0"]],
                    }
                },
            }
        raise AssertionError(path)

    monkeypatch.setattr(provider, "_request", fake_request)

    products = provider.get_products(["BTC/USD", "DOGE/USD", "LOCK/USD", "BTC/EUR"])
    quotes = provider.get_quotes(["BTC/USD", "DOGE/USD", "LOCK/USD"])
    books = provider.get_orderbooks(["BTC/USD"])

    assert _normalize_alpaca_symbol("XBT/USD") == "BTC/USD"
    assert _normalize_alpaca_symbol("XDG/USD") == "DOGE/USD"
    assert _normalize_alpaca_symbol("ETHUSD") == "ETH/USD"
    assert products["BTC/USD"]["tradable"] is True
    assert products["DOGE/USD"]["venue_symbol"] == "XDG/USD"
    assert products["LOCK/USD"]["tradable"] is False
    assert "BTC/EUR" not in products
    assert quotes["BTC/USD"]["ask"] == 100.2
    assert quotes["DOGE/USD"]["bid"] == 0.1995
    assert quotes["BTC/USD"]["spread_pct"] > 0
    assert books["BTC/USD"]["venue_depth_notional"] > 0
    assert "AssetPairs" in paths
    assert "Ticker" in paths
    assert "Depth" in paths
