from __future__ import annotations

from typing import Mapping


def spread_pct_from_snapshot(snapshot: Mapping[str, object]) -> float:
    quote = snapshot.get("latestQuote") or {}
    bid = float((quote or {}).get("bp") or 0)
    ask = float((quote or {}).get("ap") or 0)
    mid = (bid + ask) / 2 if bid and ask else 0
    if mid <= 0:
        return 0.0
    return (ask - bid) / mid * 100


def liquidity_quality(snapshot: Mapping[str, object], avg_daily_volume: float) -> float:
    spread_pct = spread_pct_from_snapshot(snapshot)
    spread_score = max(0.0, min(10.0, 10 - spread_pct * 20))
    volume_score = max(0.0, min(10.0, avg_daily_volume / 1_500_000 * 10))
    return spread_score * 0.65 + volume_score * 0.35
