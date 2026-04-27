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
    is_crypto = str(candidate.get("asset_class") or candidate.get("feed") or "").lower() == "crypto"
    stop_distance_pct = float(candidate.get("stop_distance_pct", 999))
    risk_reward = float(candidate.get("risk_reward", 0))
    liquidity_quality = float(candidate.get("liquidity_quality", 0))
    distance_vwap = float(candidate.get("distance_from_vwap_pct", 0))
    spread_pct = float(candidate.get("spread_pct", 0) or 0)
    alpaca_depth_notional = _float_default(candidate.get("alpaca_depth_notional"), 0.0)
    rh_status = str(candidate.get("rh_quote_status", "") or "")
    rh_bid = _float_default(candidate.get("rh_bid"), 0.0)
    rh_ask = _float_default(candidate.get("rh_ask"), 0.0)
    rh_spread_pct = _float_default(candidate.get("rh_spread_pct"), 999.0)
    rh_quote_age = _optional_float(candidate.get("rh_quote_age_seconds"))
    rh_tradable = bool(candidate.get("rh_tradable", False))
    alpaca_rh_deviation = _float_default(candidate.get("alpaca_rh_price_deviation_pct"), 999.0)

    if score < settings.min_score:
        reasons.append(f"Score below {settings.min_score:.1f}.")
    if phase in {"Exhaustion", "Dump"}:
        reasons.append(f"Phase is {phase}.")
    if not is_crypto and not has_catalyst and not exceptional_structure:
        reasons.append("No catalyst and structure is not exceptional.")
    if stop_distance_pct > settings.max_stop_distance_pct:
        reasons.append(f"Stop distance above {settings.max_stop_distance_pct:.1f}%.")
    if risk_reward < settings.min_risk_reward:
        reasons.append(f"Risk/reward below 1:{settings.min_risk_reward:.0f}.")
    if liquidity_quality < 6:
        reasons.append("Spread/liquidity quality is poor.")
    if is_crypto and spread_pct > settings.crypto_max_spread_pct:
        reasons.append(f"Crypto spread above {settings.crypto_max_spread_pct:.2f}%.")
    if is_crypto and alpaca_depth_notional < settings.crypto_min_orderbook_notional_depth:
        reasons.append(f"Alpaca depth proxy below ${settings.crypto_min_orderbook_notional_depth:,.0f}.")
    if is_crypto and settings.robinhood_quote_gate_enabled:
        if rh_status != "ok":
            reasons.append("Robinhood venue confirmation missing.")
        else:
            if not rh_tradable:
                reasons.append("Asset is not tradable on Robinhood.")
            if rh_bid <= 0 or rh_ask <= 0:
                reasons.append("No usable Robinhood bid/ask quote.")
            if rh_spread_pct > settings.robinhood_max_spread_pct:
                reasons.append(f"Robinhood spread above {settings.robinhood_max_spread_pct:.2f}%.")
            if rh_quote_age is None or rh_quote_age > settings.robinhood_max_quote_age_seconds:
                reasons.append(f"Robinhood quote stale or undated beyond {settings.robinhood_max_quote_age_seconds}s.")
            if alpaca_rh_deviation > settings.max_alpaca_rh_deviation_pct:
                reasons.append(f"Alpaca/Robinhood price deviation above {settings.max_alpaca_rh_deviation_pct:.2f}%.")
    if distance_vwap > settings.max_vwap_extension_pct:
        reasons.append(f"Too extended from VWAP ({distance_vwap:.1f}%).")

    valid = not reasons
    return VetoResult("Valid Trade" if valid else "Invalid", valid, reasons)


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _float_default(value: object, default: float) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
