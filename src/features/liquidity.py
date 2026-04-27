from __future__ import annotations

from typing import Mapping, Sequence


def spread_pct_from_snapshot(snapshot: Mapping[str, object]) -> float:
    quote = snapshot.get("latestQuote") or {}
    bid = _first_float(quote, ("bp", "bid_price", "bidPrice", "b"))
    ask = _first_float(quote, ("ap", "ask_price", "askPrice", "a"))
    mid = (bid + ask) / 2 if bid and ask else 0
    if mid <= 0:
        return 0.0
    return (ask - bid) / mid * 100


def liquidity_quality(snapshot: Mapping[str, object], avg_daily_volume: float) -> float:
    spread_pct = spread_pct_from_snapshot(snapshot)
    spread_score = max(0.0, min(10.0, 10 - spread_pct * 20))
    volume_score = max(0.0, min(10.0, avg_daily_volume / 1_500_000 * 10))
    return spread_score * 0.65 + volume_score * 0.35


def crypto_liquidity_quality(snapshot: Mapping[str, object], quote_volume: float, min_quote_volume: float) -> float:
    spread_pct = spread_pct_from_snapshot(snapshot)
    spread_score = max(0.0, min(10.0, 10 - spread_pct * 25))
    volume_floor = max(1.0, min_quote_volume)
    volume_score = max(0.0, min(10.0, quote_volume / volume_floor * 7))
    return round(spread_score * 0.7 + volume_score * 0.3, 4)


def orderbook_depth_metrics(orderbook: Mapping[str, object], depth_bps: float) -> dict[str, float | bool]:
    bids = sorted(
        _levels(orderbook.get("bids") or orderbook.get("bid") or orderbook.get("b") or []),
        key=lambda level: level[0],
        reverse=True,
    )
    asks = sorted(
        _levels(orderbook.get("asks") or orderbook.get("ask") or orderbook.get("a") or []),
        key=lambda level: level[0],
    )
    best_bid = bids[0][0] if bids else 0.0
    best_ask = asks[0][0] if asks else 0.0
    mid = (best_bid + best_ask) / 2 if best_bid > 0 and best_ask > 0 else 0.0
    if mid <= 0:
        return {
            "alpaca_orderbook_mid": 0.0,
            "alpaca_depth_bid_notional": 0.0,
            "alpaca_depth_ask_notional": 0.0,
            "alpaca_depth_notional": 0.0,
            "alpaca_depth_bps": float(depth_bps),
            "alpaca_depth_proxy_available": False,
        }

    band = max(0.0, float(depth_bps)) / 10_000
    bid_floor = mid * (1 - band)
    ask_ceiling = mid * (1 + band)
    bid_notional = sum(price * size for price, size in bids if price >= bid_floor)
    ask_notional = sum(price * size for price, size in asks if price <= ask_ceiling)
    return {
        "alpaca_orderbook_mid": round(mid, 8),
        "alpaca_depth_bid_notional": round(bid_notional, 4),
        "alpaca_depth_ask_notional": round(ask_notional, 4),
        "alpaca_depth_notional": round(min(bid_notional, ask_notional), 4),
        "alpaca_depth_bps": float(depth_bps),
        "alpaca_depth_proxy_available": True,
    }


def _first_float(mapping: object, keys: tuple[str, ...]) -> float:
    if not isinstance(mapping, Mapping):
        return 0.0
    for key in keys:
        try:
            value = float(mapping.get(key) or 0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            return value
    return 0.0


def _levels(raw_levels: object) -> list[tuple[float, float]]:
    if not isinstance(raw_levels, Sequence) or isinstance(raw_levels, (str, bytes)):
        return []
    levels: list[tuple[float, float]] = []
    for raw_level in raw_levels:
        price = 0.0
        size = 0.0
        if isinstance(raw_level, Mapping):
            price = _first_float(raw_level, ("p", "price", "px"))
            size = _first_float(raw_level, ("s", "size", "qty", "quantity"))
        elif isinstance(raw_level, Sequence) and not isinstance(raw_level, (str, bytes)) and len(raw_level) >= 2:
            try:
                price = float(raw_level[0] or 0)
                size = float(raw_level[1] or 0)
            except (TypeError, ValueError):
                price = 0.0
                size = 0.0
        if price > 0 and size > 0:
            levels.append((price, size))
    return levels
