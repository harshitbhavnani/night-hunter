from __future__ import annotations

from typing import Literal, Mapping


Phase = Literal["Ignition", "Expansion", "Exhaustion", "Dump"]


def classify_phase(features: Mapping[str, object]) -> Phase:
    rvol = float(features.get("rvol", 0))
    acceleration = float(features.get("acceleration", 0))
    return_15m = float(features.get("return_15m", 0))
    return_30m = float(features.get("return_30m", 0))
    reversal_risk = float(features.get("reversal_risk", 0))
    distance_vwap = float(features.get("distance_from_vwap_pct", 0))

    if return_15m < -2 or acceleration < -1.5:
        return "Dump"
    if reversal_risk >= 7 or distance_vwap > 9:
        return "Exhaustion"
    if rvol >= 3 and acceleration >= 1.25 and 0 <= return_15m <= 8:
        return "Ignition"
    if rvol >= 2 and return_30m > 2 and acceleration >= -0.2:
        return "Expansion"
    if return_30m < 0:
        return "Dump"
    return "Expansion"

