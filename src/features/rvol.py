from __future__ import annotations

from typing import Mapping, Sequence


def compute_rvol(
    bars: Sequence[Mapping[str, object]],
    avg_daily_volume: float | None = None,
    session_minutes: int = 390,
) -> float:
    if not bars:
        return 0.0
    current_volume = sum(float(bar.get("v", 0)) for bar in bars)
    if avg_daily_volume and avg_daily_volume > 0:
        expected_fraction = min(1.0, max(0.01, len(bars) / max(1, session_minutes)))
        expected = avg_daily_volume * expected_fraction
    else:
        recent = [float(bar.get("v", 0)) for bar in bars[-30:]]
        baseline = sum(recent) / max(1, len(recent))
        expected = baseline * len(bars)
    if expected <= 0:
        return 0.0
    return current_volume / expected
