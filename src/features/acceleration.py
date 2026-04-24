from __future__ import annotations

from typing import Mapping, Sequence

from src.features.returns import rolling_return


def compute_acceleration(bars: Sequence[Mapping[str, object]]) -> float:
    if len(bars) < 12:
        return 0.0
    latest_5m = rolling_return(bars, 5)
    latest_15m = rolling_return(bars, 15)
    prior_slice = bars[:-5]
    prior_5m = rolling_return(prior_slice, 5) if len(prior_slice) >= 6 else 0.0
    slope_bonus = max(0.0, latest_15m / 3)
    return latest_5m - prior_5m + slope_bonus

