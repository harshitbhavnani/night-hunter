from __future__ import annotations

from dataclasses import dataclass
from math import log
from typing import Dict, Mapping

from src.config import ScoreWeights


@dataclass(frozen=True)
class ScoreBreakdown:
    rvol: float
    acceleration: float
    breakout_strength: float
    catalyst: float
    reversal_risk: float
    total: float

    def as_dict(self) -> Dict[str, float]:
        return {
            "rvol": self.rvol,
            "acceleration": self.acceleration,
            "breakout_strength": self.breakout_strength,
            "catalyst": self.catalyst,
            "reversal_risk": self.reversal_risk,
            "total": self.total,
        }


def clamp_0_10(value: float) -> float:
    return max(0.0, min(10.0, value))


def normalize_rvol(rvol: float) -> float:
    if rvol <= 1:
        return 0.0
    return clamp_0_10(log(rvol) / log(6) * 10)


def normalize_acceleration(acceleration: float) -> float:
    return clamp_0_10(acceleration / 1.2 * 10)


def normalize_breakout(strength_pct: float) -> float:
    return clamp_0_10((strength_pct + 0.1) / 2.0 * 10)


def compute_momentum_score(
    features: Mapping[str, object],
    weights: ScoreWeights | None = None,
) -> ScoreBreakdown:
    weights = weights or ScoreWeights()
    rvol_score = normalize_rvol(float(features.get("rvol", 0)))
    acceleration_score = normalize_acceleration(float(features.get("acceleration", 0)))
    breakout_score = normalize_breakout(float(features.get("breakout_strength", 0)))
    catalyst_score = clamp_0_10(float(features.get("catalyst_score", 0)))
    reversal_score = clamp_0_10(float(features.get("reversal_risk", 0)))
    total = (
        weights.rvol * rvol_score
        + weights.acceleration * acceleration_score
        + weights.breakout_strength * breakout_score
        + weights.catalyst * catalyst_score
        + weights.reversal_risk * reversal_score
    )
    return ScoreBreakdown(
        rvol=round(rvol_score, 2),
        acceleration=round(acceleration_score, 2),
        breakout_strength=round(breakout_score, 2),
        catalyst=round(catalyst_score, 2),
        reversal_risk=round(reversal_score, 2),
        total=round(clamp_0_10(total), 2),
    )
