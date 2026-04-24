from __future__ import annotations

from dataclasses import dataclass
from typing import List, Mapping

from src.config import AppSettings, get_settings


@dataclass(frozen=True)
class VetoResult:
    verdict: str
    valid: bool
    reasons: List[str]


def apply_veto_logic(
    candidate: Mapping[str, object],
    settings: AppSettings | None = None,
) -> VetoResult:
    settings = settings or get_settings()
    reasons: List[str] = []
    score = float(candidate.get("score", 0))
    phase = str(candidate.get("phase", ""))
    has_catalyst = bool(candidate.get("has_catalyst", False))
    exceptional_structure = bool(candidate.get("exceptional_structure", False))
    stop_distance_pct = float(candidate.get("stop_distance_pct", 999))
    risk_reward = float(candidate.get("risk_reward", 0))
    liquidity_quality = float(candidate.get("liquidity_quality", 0))
    distance_vwap = float(candidate.get("distance_from_vwap_pct", 0))

    if score < settings.min_score:
        reasons.append(f"Score below {settings.min_score:.1f}.")
    if phase in {"Exhaustion", "Dump"}:
        reasons.append(f"Phase is {phase}.")
    if not has_catalyst and not exceptional_structure:
        reasons.append("No catalyst and structure is not exceptional.")
    if stop_distance_pct > settings.max_stop_distance_pct:
        reasons.append(f"Stop distance above {settings.max_stop_distance_pct:.1f}%.")
    if risk_reward < settings.min_risk_reward:
        reasons.append(f"Risk/reward below 1:{settings.min_risk_reward:.0f}.")
    if liquidity_quality < 6:
        reasons.append("Spread/liquidity quality is poor.")
    if distance_vwap > settings.max_vwap_extension_pct:
        reasons.append(f"Too extended from VWAP ({distance_vwap:.1f}%).")

    valid = not reasons
    return VetoResult("Valid Trade" if valid else "Invalid", valid, reasons)

