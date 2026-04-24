from __future__ import annotations

from typing import Mapping, Sequence


def breakout_strength(bars: Sequence[Mapping[str, object]], lookback: int = 30) -> float:
    if len(bars) < 3:
        return 0.0
    current = float(bars[-1].get("c", 0))
    if len(bars) > lookback + 5:
        prior = bars[-lookback - 5 : -5]
    else:
        prior = bars[:-5] or bars[:-1]
    prior_high = max(float(bar.get("h", 0)) for bar in prior)
    if prior_high <= 0:
        return 0.0
    return (current - prior_high) / prior_high * 100
