from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Iterable, Mapping

import requests

from src.config import AppSettings, get_settings


ALIAS_TO_ALPACA = {
    "XBT": "BTC",
    "XXBT": "BTC",
    "XDG": "DOGE",
    "XXDG": "DOGE",
}


class KrakenVenueProvider:
    """Public Kraken market-data adapter for execution-venue quote checks."""

    venue_name = "Kraken"

    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or get_settings()
        self._session = requests.Session()
        self._pair_map: dict[str, dict[str, object]] | None = None

    def get_products(self, symbols: Iterable[str]) -> Dict[str, Mapping[str, object]]:
        wanted = {_normalize_alpaca_symbol(symbol) for symbol in symbols}
        wanted.discard("")
        pair_map = self._asset_pair_map()
        return {
            symbol: {
                "symbol": symbol,
                "venue_name": self.venue_name,
                "venue_symbol": str(meta.get("venue_symbol") or symbol),
                "kraken_pair": str(meta.get("kraken_pair") or ""),
                "tradable": bool(meta.get("tradable", False)),
                "raw": dict(meta.get("raw", {}) or {}),
            }
            for symbol, meta in pair_map.items()
            if symbol in wanted
        }

    def get_quotes(self, symbols: Iterable[str]) -> Dict[str, Mapping[str, object]]:
        pair_map = self._asset_pair_map()
        requested = [_normalize_alpaca_symbol(symbol) for symbol in symbols]
        requested = [symbol for symbol in requested if symbol in pair_map]
        if not requested:
            return {}

        pairs = [str(pair_map[symbol]["kraken_pair"]) for symbol in requested]
        quote_time = datetime.now(timezone.utc).isoformat()
        payload = self._request("Ticker", {"pair": ",".join(pairs)})
        results = payload.get("result", {}) if isinstance(payload, Mapping) else {}
        if not isinstance(results, Mapping):
            return {}

        quotes: Dict[str, Mapping[str, object]] = {}
        pair_to_symbol = {str(pair_map[symbol]["kraken_pair"]): symbol for symbol in requested}
        for key, item in results.items():
            if not isinstance(item, Mapping):
                continue
            symbol = pair_to_symbol.get(str(key)) or _symbol_for_result_key(str(key), pair_map)
            if not symbol:
                continue
            bid = _list_float(item.get("b"), 0)
            ask = _list_float(item.get("a"), 0)
            mid = (bid + ask) / 2 if bid > 0 and ask > 0 else _list_float(item.get("c"), 0)
            quotes[symbol] = {
                "symbol": symbol,
                "venue_name": self.venue_name,
                "venue_symbol": str(pair_map[symbol].get("venue_symbol") or symbol),
                "kraken_pair": str(pair_map[symbol].get("kraken_pair") or ""),
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "spread_pct": _spread_pct(bid, ask),
                "quote_time": quote_time,
                "raw": dict(item),
            }
        return quotes

    def get_orderbooks(self, symbols: Iterable[str]) -> Dict[str, Mapping[str, object]]:
        pair_map = self._asset_pair_map()
        books: Dict[str, Mapping[str, object]] = {}
        for raw_symbol in symbols:
            symbol = _normalize_alpaca_symbol(raw_symbol)
            meta = pair_map.get(symbol)
            if not meta:
                continue
            payload = self._request("Depth", {"pair": str(meta["kraken_pair"]), "count": 100})
            results = payload.get("result", {}) if isinstance(payload, Mapping) else {}
            if not isinstance(results, Mapping):
                continue
            item = next((value for value in results.values() if isinstance(value, Mapping)), None)
            if not item:
                continue
            depth = _depth_metrics(item, self.settings.crypto_depth_bps)
            quote_time = _book_time(item) or datetime.now(timezone.utc).isoformat()
            books[symbol] = {
                "symbol": symbol,
                "venue_name": self.venue_name,
                "venue_symbol": str(meta.get("venue_symbol") or symbol),
                "kraken_pair": str(meta.get("kraken_pair") or ""),
                "quote_time": quote_time,
                **depth,
                "raw": dict(item),
            }
        return books

    def _asset_pair_map(self) -> dict[str, dict[str, object]]:
        if self._pair_map is not None:
            return self._pair_map
        payload = self._request("AssetPairs", {})
        results = payload.get("result", {}) if isinstance(payload, Mapping) else {}
        pair_map: dict[str, dict[str, object]] = {}
        if isinstance(results, Mapping):
            for pair_key, item in results.items():
                if not isinstance(item, Mapping):
                    continue
                symbol = _kraken_item_symbol(item, str(pair_key))
                if not symbol:
                    continue
                status = str(item.get("status") or "online").lower()
                pair_map[symbol] = {
                    "symbol": symbol,
                    "venue_name": self.venue_name,
                    "venue_symbol": str(item.get("wsname") or symbol),
                    "kraken_pair": str(pair_key),
                    "tradable": status in {"online", "enabled", "active", "tradable", ""},
                    "raw": dict(item),
                }
        self._pair_map = pair_map
        return pair_map

    def _request(self, path: str, params: Mapping[str, object]) -> Mapping[str, object]:
        response = self._session.get(f"{self.settings.kraken_base_url}/0/public/{path}", params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()
        errors = payload.get("error") if isinstance(payload, Mapping) else None
        if errors:
            raise RuntimeError(f"Kraken {path} error: {errors}")
        return payload if isinstance(payload, Mapping) else {}


def _kraken_item_symbol(item: Mapping[str, object], pair_key: str) -> str:
    for key in ("wsname", "altname"):
        symbol = _normalize_alpaca_symbol(item.get(key))
        if symbol:
            return symbol
    return _normalize_alpaca_symbol(pair_key)


def _normalize_alpaca_symbol(value: object) -> str:
    raw = str(value or "").strip().upper().replace("-", "/")
    if not raw:
        return ""
    if "/" in raw:
        base, quote = raw.split("/", 1)
        base = _normalize_asset_code(base)
        quote = _normalize_asset_code(quote)
        return f"{base}/USD" if base and quote == "USD" else ""
    compact = raw.replace("/", "")
    if compact.endswith("ZUSD"):
        base = compact[:-4]
        quote = "USD"
    elif compact.endswith("USD"):
        base = compact[:-3]
        quote = "USD"
    else:
        return ""
    base = _normalize_asset_code(base)
    return f"{base}/USD" if base and quote == "USD" else ""


def _normalize_asset_code(value: object) -> str:
    code = str(value or "").strip().upper()
    if code in ALIAS_TO_ALPACA:
        return ALIAS_TO_ALPACA[code]
    if code.startswith("X") and code[1:] in ALIAS_TO_ALPACA:
        return ALIAS_TO_ALPACA[code[1:]]
    if code.startswith(("X", "Z")) and len(code) > 3:
        code = code[1:]
    return ALIAS_TO_ALPACA.get(code, code)


def _symbol_for_result_key(result_key: str, pair_map: Mapping[str, Mapping[str, object]]) -> str:
    for symbol, meta in pair_map.items():
        if str(meta.get("kraken_pair")) == result_key:
            return symbol
    return ""


def _list_float(value: object, index: int) -> float:
    try:
        if isinstance(value, (list, tuple)):
            return float(value[index] or 0)
        return float(value or 0)
    except (IndexError, TypeError, ValueError):
        return 0.0


def _spread_pct(bid: float, ask: float) -> float:
    mid = (bid + ask) / 2 if bid > 0 and ask > 0 else 0
    return (ask - bid) / mid * 100 if mid else 999.0


def _depth_metrics(orderbook: Mapping[str, object], depth_bps: float) -> dict[str, float | bool]:
    bids = sorted(_levels(orderbook.get("bids") or []), key=lambda level: level[0], reverse=True)
    asks = sorted(_levels(orderbook.get("asks") or []), key=lambda level: level[0])
    best_bid = bids[0][0] if bids else 0.0
    best_ask = asks[0][0] if asks else 0.0
    mid = (best_bid + best_ask) / 2 if best_bid > 0 and best_ask > 0 else 0.0
    if mid <= 0:
        return {
            "venue_orderbook_mid": 0.0,
            "venue_depth_bid_notional": 0.0,
            "venue_depth_ask_notional": 0.0,
            "venue_depth_notional": 0.0,
            "venue_depth_bps": float(depth_bps),
            "venue_depth_available": False,
        }
    band = max(0.0, float(depth_bps)) / 10_000
    bid_floor = mid * (1 - band)
    ask_ceiling = mid * (1 + band)
    bid_notional = sum(price * size for price, size, _ in bids if price >= bid_floor)
    ask_notional = sum(price * size for price, size, _ in asks if price <= ask_ceiling)
    return {
        "venue_orderbook_mid": round(mid, 8),
        "venue_depth_bid_notional": round(bid_notional, 4),
        "venue_depth_ask_notional": round(ask_notional, 4),
        "venue_depth_notional": round(min(bid_notional, ask_notional), 4),
        "venue_depth_bps": float(depth_bps),
        "venue_depth_available": True,
    }


def _levels(raw_levels: object) -> list[tuple[float, float, float]]:
    if not isinstance(raw_levels, list):
        return []
    levels: list[tuple[float, float, float]] = []
    for raw_level in raw_levels:
        if isinstance(raw_level, Mapping):
            price = _first_float(raw_level, ("p", "price", "px"))
            size = _first_float(raw_level, ("s", "size", "qty", "quantity", "volume"))
            timestamp = _first_float(raw_level, ("t", "time", "timestamp"))
        elif isinstance(raw_level, (list, tuple)) and len(raw_level) >= 2:
            price = _list_float(raw_level, 0)
            size = _list_float(raw_level, 1)
            timestamp = _list_float(raw_level, 2) if len(raw_level) > 2 else 0.0
        else:
            price = 0.0
            size = 0.0
            timestamp = 0.0
        if price > 0 and size > 0:
            levels.append((price, size, timestamp))
    return levels


def _book_time(orderbook: Mapping[str, object]) -> str:
    timestamps = [
        timestamp
        for _, _, timestamp in _levels(orderbook.get("bids") or []) + _levels(orderbook.get("asks") or [])
        if timestamp > 0
    ]
    if not timestamps:
        return ""
    return datetime.fromtimestamp(max(timestamps), tz=timezone.utc).isoformat()


def _first_float(mapping: Mapping[str, object], keys: tuple[str, ...]) -> float:
    for key in keys:
        try:
            value = float(mapping.get(key) or 0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            return value
    return 0.0
