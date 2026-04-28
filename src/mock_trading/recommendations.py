from __future__ import annotations

from typing import Mapping


def recommend_entry_controls(card: Mapping[str, object], available_cash: float) -> dict[str, object]:
    entry = float(card.get("entry", 0) or 0)
    allocation_pct = recommended_allocation_pct(card)
    dollar_amount = max(0.0, available_cash * allocation_pct / 100)
    shares = round(dollar_amount / entry, 8) if entry > 0 else 0.0
    return {
        "allocation_pct": round(allocation_pct, 2),
        "dollar_amount": round(shares * entry, 2),
        "shares": shares,
        "max_hold_minutes": recommended_max_hold_minutes(card),
        **recommended_target_split(card),
    }


def recommended_allocation_pct(card: Mapping[str, object]) -> float:
    if card.get("verdict") != "Valid Trade":
        return 0.0
    score = float(card.get("score", 0) or 0)
    reversal_risk = _feature(card, "reversal_risk")
    market_regime = _market_regime(card)
    allocation = 5.0
    if score >= 9.0:
        allocation += 7.5
    elif score >= 8.5:
        allocation += 5.0
    elif score >= 8.0:
        allocation += 2.5
    if card.get("phase") == "Ignition":
        allocation += 2.5
    if reversal_risk >= 4.5:
        allocation -= 2.5
    if market_regime == "Caution":
        allocation -= 2.5
    if market_regime == "Risk-Off" and str(card.get("ticker") or "") not in {"BTC/USD", "ETH/USD"}:
        allocation = min(allocation, 3.0)
    return max(3.0, min(15.0, allocation))


def recommended_max_hold_minutes(card: Mapping[str, object]) -> int:
    score = float(card.get("score", 0) or 0)
    phase = str(card.get("phase", "Expansion"))
    liquidity = _feature(card, "liquidity_quality")
    reversal_risk = _feature(card, "reversal_risk")
    vwap_extension = _feature(card, "distance_from_vwap_pct")
    market_regime = _market_regime(card)
    hold = 30 if phase == "Ignition" else 18
    if score >= 8.75 and liquidity >= 7.5 and reversal_risk <= 3:
        hold += 10
    if vwap_extension > 5 or reversal_risk >= 4.5:
        hold -= 8
    if market_regime in {"Caution", "Risk-Off"}:
        hold -= 5
    return int(max(10, min(45, hold)))


def recommended_target_split(card: Mapping[str, object]) -> dict[str, int]:
    score = float(card.get("score", 0) or 0)
    phase = str(card.get("phase", ""))
    liquidity = _feature(card, "liquidity_quality")
    reversal_risk = _feature(card, "reversal_risk")
    vwap_extension = _feature(card, "distance_from_vwap_pct")
    market_regime = _market_regime(card)
    if market_regime in {"Caution", "Risk-Off"}:
        return {"target_1_pct": 85, "target_2_pct": 15}
    if score >= 8.7 and phase == "Ignition" and reversal_risk <= 3 and liquidity >= 7:
        return {"target_1_pct": 60, "target_2_pct": 40}
    if reversal_risk >= 4.5 or vwap_extension >= 5 or liquidity < 7:
        return {"target_1_pct": 85, "target_2_pct": 15}
    return {"target_1_pct": 75, "target_2_pct": 25}


def _feature(card: Mapping[str, object], key: str) -> float:
    if key in card:
        return float(card.get(key, 0) or 0)
    features = card.get("features") or {}
    if isinstance(features, Mapping):
        return float(features.get(key, 0) or 0)
    return 0.0


def _market_regime(card: Mapping[str, object]) -> str:
    value = card.get("market_regime")
    if value:
        return str(value)
    features = card.get("features") or {}
    if isinstance(features, Mapping):
        return str(features.get("market_regime") or "")
    return ""
