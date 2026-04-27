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
    venue_status = str(candidate.get("venue_quote_status", "") or "")
    venue_bid = _float_default(candidate.get("venue_bid"), 0.0)
    venue_ask = _float_default(candidate.get("venue_ask"), 0.0)
    venue_spread_pct = _float_default(candidate.get("venue_spread_pct"), 999.0)
    venue_quote_age = _optional_float(candidate.get("venue_quote_age_seconds"))
    venue_tradable = bool(candidate.get("venue_tradable", False))
    venue_depth_notional = _float_default(candidate.get("venue_depth_notional"), 0.0)
    alpaca_venue_deviation = _float_default(candidate.get("alpaca_venue_price_deviation_pct"), 999.0)

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
    if is_crypto:
        if venue_status != "ok":
            reasons.append("Kraken venue confirmation missing.")
        else:
            if not venue_tradable:
                reasons.append("Asset is not tradable on Kraken.")
            if venue_bid <= 0 or venue_ask <= 0:
                reasons.append("No usable Kraken bid/ask quote.")
            if venue_spread_pct > settings.kraken_max_spread_pct:
                reasons.append(f"Kraken spread above {settings.kraken_max_spread_pct:.2f}%.")
            if venue_quote_age is None or venue_quote_age > settings.kraken_max_quote_age_seconds:
                reasons.append(f"Kraken quote stale or undated beyond {settings.kraken_max_quote_age_seconds}s.")
            if venue_depth_notional < settings.kraken_min_orderbook_notional_depth:
                reasons.append(f"Kraken depth below ${settings.kraken_min_orderbook_notional_depth:,.0f}.")
            if alpaca_venue_deviation > settings.max_alpaca_venue_deviation_pct:
                reasons.append(f"Alpaca/Kraken price deviation above {settings.max_alpaca_venue_deviation_pct:.2f}%.")
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
