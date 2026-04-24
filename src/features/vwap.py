from __future__ import annotations

from typing import Mapping, Sequence


def compute_vwap(bars: Sequence[Mapping[str, object]]) -> float:
    numerator = 0.0
    denominator = 0.0
    for bar in bars:
        high = float(bar.get("h", 0))
        low = float(bar.get("l", 0))
        close = float(bar.get("c", 0))
        volume = float(bar.get("v", 0))
        typical = (high + low + close) / 3
        numerator += typical * volume
        denominator += volume
    return numerator / denominator if denominator else 0.0


def distance_from_vwap_pct(price: float, vwap: float) -> float:
    if vwap <= 0:
        return 0.0
    return (price - vwap) / vwap * 100

