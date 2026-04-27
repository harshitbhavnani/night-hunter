from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Dict, Iterable, Mapping
from urllib.parse import urlencode

import requests

from src.config import AppSettings, get_settings


def alpaca_to_robinhood_symbol(symbol: str) -> str:
    return symbol.upper().replace("/", "-")


def robinhood_to_alpaca_symbol(symbol: str) -> str:
    return symbol.upper().replace("-", "/")


class RobinhoodCryptoProvider:
    """Read-only Robinhood Crypto Trading API adapter for venue quote checks."""

    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or get_settings()
        self._session = requests.Session()

    @property
    def configured(self) -> bool:
        return self.settings.robinhood_quote_gate_ready

    def get_products(self, symbols: Iterable[str]) -> Dict[str, Mapping[str, object]]:
        wanted = {symbol.upper() for symbol in symbols}
        payload = self._request("GET", "/api/v1/crypto/trading/trading_pairs/")
        products = _extract_items(payload)
        normalized: Dict[str, Mapping[str, object]] = {}
        for item in products:
            symbol = _product_symbol(item)
            if not symbol or symbol not in wanted:
                continue
            normalized[symbol] = {
                "symbol": symbol,
                "rh_symbol": alpaca_to_robinhood_symbol(symbol),
                "tradable": _is_tradable_product(item),
                "raw": dict(item),
            }
        return normalized

    def get_quotes(self, symbols: Iterable[str]) -> Dict[str, Mapping[str, object]]:
        quotes: Dict[str, Mapping[str, object]] = {}
        for symbol in symbols:
            alpaca_symbol = symbol.upper()
            rh_symbol = alpaca_to_robinhood_symbol(alpaca_symbol)
            query = urlencode({"symbol": rh_symbol})
            payload = self._request("GET", f"/api/v1/crypto/marketdata/best_bid_ask/?{query}")
            item = _first_item(payload)
            if not item:
                continue
            bid = _first_float(item, ("bid_price", "bid", "best_bid", "bp"))
            ask = _first_float(item, ("ask_price", "ask", "best_ask", "ap"))
            mid = (bid + ask) / 2 if bid > 0 and ask > 0 else _first_float(item, ("mark_price", "price", "mid"))
            quote_time = _quote_time(item)
            quotes[alpaca_symbol] = {
                "symbol": alpaca_symbol,
                "rh_symbol": rh_symbol,
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "spread_pct": _spread_pct(bid, ask),
                "quote_time": quote_time,
                "raw": dict(item),
            }
        return quotes

    def _request(self, method: str, path: str, body: str = "") -> object:
        if not self.configured:
            raise RuntimeError("Robinhood quote gate requires ROBINHOOD_CRYPTO_API_KEY and ROBINHOOD_CRYPTO_PRIVATE_KEY.")
        response = self._session.request(
            method,
            f"{self.settings.robinhood_crypto_base_url}{path}",
            data=body or None,
            headers=self._auth_headers(method, path, body),
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def _auth_headers(self, method: str, path: str, body: str = "") -> dict[str, str]:
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError as exc:
            raise RuntimeError("Robinhood Crypto API signing requires the cryptography package.") from exc

        timestamp = str(int(datetime.now(timezone.utc).timestamp()))
        private_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(self.settings.robinhood_crypto_private_key))
        message = f"{self.settings.robinhood_crypto_api_key}{timestamp}{path}{method.upper()}{body}"
        signature = base64.b64encode(private_key.sign(message.encode("utf-8"))).decode("utf-8")
        return {
            "x-api-key": self.settings.robinhood_crypto_api_key,
            "x-signature": signature,
            "x-timestamp": timestamp,
            "Content-Type": "application/json",
        }


def _extract_items(payload: object) -> list[Mapping[str, object]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("results", "data", "items", "trading_pairs"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, Mapping)]
        return [payload]
    return []


def _first_item(payload: object) -> Mapping[str, object] | None:
    items = _extract_items(payload)
    return items[0] if items else None


def _product_symbol(item: Mapping[str, object]) -> str:
    direct = str(item.get("symbol") or item.get("id") or "").upper()
    if direct:
        return robinhood_to_alpaca_symbol(direct)
    asset = item.get("asset_currency")
    quote = item.get("quote_currency")
    if isinstance(asset, Mapping) and isinstance(quote, Mapping):
        base_code = str(asset.get("code") or "").upper()
        quote_code = str(quote.get("code") or "").upper()
        if base_code and quote_code:
            return f"{base_code}/{quote_code}"
    return ""


def _is_tradable_product(item: Mapping[str, object]) -> bool:
    if "tradable" in item:
        return bool(item.get("tradable"))
    status = str(item.get("status") or item.get("state") or "").lower()
    return status in {"active", "tradable", "enabled", ""}


def _first_float(mapping: Mapping[str, object], keys: tuple[str, ...]) -> float:
    for key in keys:
        try:
            value = float(mapping.get(key) or 0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            return value
    return 0.0


def _quote_time(item: Mapping[str, object]) -> str:
    for key in ("updated_at", "timestamp", "quote_time", "created_at", "t"):
        value = item.get(key)
        if value:
            return str(value)
    return datetime.now(timezone.utc).isoformat()


def _spread_pct(bid: float, ask: float) -> float:
    mid = (bid + ask) / 2 if bid > 0 and ask > 0 else 0
    return (ask - bid) / mid * 100 if mid else 999.0
