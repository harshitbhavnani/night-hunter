from __future__ import annotations

from typing import Mapping, Sequence


def close_values(bars: Sequence[Mapping[str, object]]) -> list[float]:
    return [float(bar["c"]) for bar in bars if "c" in bar]


def percent_change(first: float, last: float) -> float:
    if first == 0:
        return 0.0
    return (last - first) / first * 100


def rolling_return(bars: Sequence[Mapping[str, object]], minutes: int) -> float:
    closes = close_values(bars)
    if len(closes) < 2:
        return 0.0
    lookback = min(minutes, len(closes) - 1)
    return percent_change(closes[-lookback - 1], closes[-1])


def day_percent_change(snapshot: Mapping[str, object], bars: Sequence[Mapping[str, object]]) -> float:
    daily = snapshot.get("dailyBar") or {}
    previous = snapshot.get("prevDailyBar") or {}
    current = float((daily or {}).get("c") or (bars[-1]["c"] if bars else 0))
    previous_close = float((previous or {}).get("c") or (bars[0]["o"] if bars else current))
    return percent_change(previous_close, current)

