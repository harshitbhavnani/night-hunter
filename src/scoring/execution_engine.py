from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping

from src.config import AppSettings, get_settings
from src.scoring.veto_engine import apply_veto_logic


@dataclass(frozen=True)
class TradeCard:
    ticker: str
    verdict: str
    phase: str
    score: float
    score_breakdown: Mapping[str, float]
    catalyst_summary: str
    entry: float
    stop: float
    target_1: float
    target_2: float
    risk_reward: float
    estimated_momentum_life: str
    reason_summary: str
    veto_reasons: List[str]
    features: Mapping[str, object]
    feed: str
    data_confidence: str
    limitations: str
    settings_snapshot: Mapping[str, object]

    def as_dict(self) -> Dict[str, object]:
        return {
            "ticker": self.ticker,
            "verdict": self.verdict,
            "phase": self.phase,
            "score": self.score,
            "score_breakdown": dict(self.score_breakdown),
            "catalyst_summary": self.catalyst_summary,
            "entry": self.entry,
            "stop": self.stop,
            "target_1": self.target_1,
            "target_2": self.target_2,
            "risk_reward": self.risk_reward,
            "estimated_momentum_life": self.estimated_momentum_life,
            "reason_summary": self.reason_summary,
            "veto_reasons": self.veto_reasons,
            "features": dict(self.features),
            "feed": self.feed,
            "data_confidence": self.data_confidence,
            "limitations": self.limitations,
            "settings_snapshot": dict(self.settings_snapshot),
            "venue_name": self.features.get("venue_name"),
            "venue_symbol": self.features.get("venue_symbol"),
            "venue_bid": self.features.get("venue_bid"),
            "venue_ask": self.features.get("venue_ask"),
            "venue_mid": self.features.get("venue_mid"),
            "venue_spread_pct": self.features.get("venue_spread_pct"),
            "venue_quote_time": self.features.get("venue_quote_time"),
            "venue_quote_age_seconds": self.features.get("venue_quote_age_seconds"),
            "venue_tradable": self.features.get("venue_tradable"),
            "venue_quote_status": self.features.get("venue_quote_status"),
            "venue_depth_notional": self.features.get("venue_depth_notional"),
            "venue_depth_bid_notional": self.features.get("venue_depth_bid_notional"),
            "venue_depth_ask_notional": self.features.get("venue_depth_ask_notional"),
            "venue_depth_bps": self.features.get("venue_depth_bps"),
            "venue_quote_volume_24h": self.features.get("venue_quote_volume_24h"),
            "execution_profile": self.features.get("execution_profile"),
            "execution_quality": self.features.get("execution_quality"),
            "target_1_r": self.features.get("target_1_r"),
            "target_2_r": self.features.get("target_2_r"),
            "stop_basis": self.features.get("stop_basis"),
            "stop_distance_pct": self.features.get("stop_distance_pct"),
            "recommended_hold_minutes": self.features.get("recommended_hold_minutes"),
            "alpaca_venue_price_deviation_pct": self.features.get("alpaca_venue_price_deviation_pct"),
            "venue_quote_snapshot": self.features.get("venue_quote_snapshot"),
            "market_regime": self.features.get("market_regime"),
            "btc_return_15m": self.features.get("btc_return_15m"),
            "btc_return_30m": self.features.get("btc_return_30m"),
            "eth_return_15m": self.features.get("eth_return_15m"),
            "eth_return_30m": self.features.get("eth_return_30m"),
            "regime_risk": self.features.get("regime_risk"),
            "alpaca_depth_notional": self.features.get("alpaca_depth_notional"),
            "alpaca_depth_bid_notional": self.features.get("alpaca_depth_bid_notional"),
            "alpaca_depth_ask_notional": self.features.get("alpaca_depth_ask_notional"),
            "alpaca_depth_bps": self.features.get("alpaca_depth_bps"),
            "alpaca_depth_proxy_ok": self.features.get("alpaca_depth_proxy_ok"),
        }


def build_execution_candidate(row: Mapping[str, object]) -> Dict[str, object]:
    price = float(row.get("venue_ask") or row.get("price", 0))
    vwap = float(row.get("vwap", price))
    entry = _round_price(price)
    model = _execution_model(row, entry, vwap)
    stop = _round_price(max(_min_tick(entry), entry - model["risk"]))
    risk = max(_min_tick(price), entry - stop)
    target_1 = _round_price(entry + risk * float(model["target_1_r"]))
    target_2 = _round_price(entry + risk * float(model["target_2_r"]))
    risk_reward = round((target_2 - entry) / risk, 2) if risk > 0 else 0.0
    stop_distance_pct = (entry - stop) / entry * 100 if entry else 999.0
    exceptional_structure = (
        float(row.get("rvol", 0)) >= 5
        and float(row.get("acceleration", 0)) >= 2
        and float(row.get("breakout_strength", 0)) >= 1.5
        and float(row.get("reversal_risk", 10)) <= 4
    )
    candidate = dict(row)
    candidate.update(
        {
            "entry": entry,
            "stop": stop,
            "target_1": target_1,
            "target_2": target_2,
            "risk_reward": risk_reward,
            "stop_distance_pct": stop_distance_pct,
            "execution_profile": model["execution_profile"],
            "execution_quality": model["execution_quality"],
            "target_1_r": model["target_1_r"],
            "target_2_r": model["target_2_r"],
            "stop_basis": model["stop_basis"],
            "recommended_hold_minutes": model["recommended_hold_minutes"],
            "exceptional_structure": exceptional_structure,
        }
    )
    return candidate


def generate_trade_card(
    ranked_rows: Iterable[Mapping[str, object]],
    settings: AppSettings | None = None,
) -> TradeCard | None:
    settings = settings or get_settings()
    rows = sorted(ranked_rows, key=lambda item: float(item.get("score", 0)), reverse=True)
    if not rows:
        return None

    best_invalid: TradeCard | None = None
    for row in rows:
        candidate = build_execution_candidate(row)
        veto = apply_veto_logic(candidate, settings)
        card = _card_from_candidate(candidate, veto.verdict, veto.reasons)
        if veto.valid:
            return card
        if best_invalid is None:
            best_invalid = card
    return best_invalid


def generate_trade_card_for_symbol(
    ranked_rows: Iterable[Mapping[str, object]],
    symbol: str,
    settings: AppSettings | None = None,
) -> TradeCard | None:
    target = symbol.upper()
    for row in ranked_rows:
        row_symbol = str(row.get("ticker") or row.get("symbol") or "").upper()
        if row_symbol == target:
            return generate_trade_card([row], settings)
    return None


def _card_from_candidate(candidate: Mapping[str, object], verdict: str, veto_reasons: List[str]) -> TradeCard:
    score = float(candidate.get("score", 0))
    phase = str(candidate.get("phase", "Expansion"))
    hold_minutes = int(float(candidate.get("recommended_hold_minutes", 0) or 0))
    life = f"{max(5, hold_minutes - 8)}-{hold_minutes + 5} minutes" if hold_minutes else "Stand down"
    reasons = [
        f"RVOL {float(candidate.get('rvol', 0)):.1f}x",
        f"acceleration {float(candidate.get('acceleration', 0)):.2f}",
        f"breakout {float(candidate.get('breakout_strength', 0)):.2f}%",
        f"VWAP distance {float(candidate.get('distance_from_vwap_pct', 0)):.2f}%",
        f"profile {candidate.get('execution_profile', 'unknown')}",
    ]
    settings_snapshot = candidate.get("settings_snapshot")
    if not isinstance(settings_snapshot, Mapping):
        settings_snapshot = {}
    return TradeCard(
        ticker=str(candidate.get("ticker") or candidate.get("symbol") or ""),
        verdict=verdict,
        phase=phase,
        score=round(score, 2),
        score_breakdown=dict(candidate.get("score_breakdown", {})),
        catalyst_summary=str(candidate.get("catalyst_summary", "")),
        entry=float(candidate.get("entry", 0)),
        stop=float(candidate.get("stop", 0)),
        target_1=float(candidate.get("target_1", 0)),
        target_2=float(candidate.get("target_2", 0)),
        risk_reward=float(candidate.get("risk_reward", 0)),
        estimated_momentum_life=life,
        reason_summary=", ".join(reasons),
        veto_reasons=veto_reasons,
        features={
            "rvol": float(candidate.get("rvol", 0)),
            "acceleration": float(candidate.get("acceleration", 0)),
            "breakout_strength": float(candidate.get("breakout_strength", 0)),
            "reversal_risk": float(candidate.get("reversal_risk", 0)),
            "liquidity_quality": float(candidate.get("liquidity_quality", 0)),
            "distance_from_vwap_pct": float(candidate.get("distance_from_vwap_pct", 0)),
            "spread_pct": float(candidate.get("spread_pct", 0) or 0),
            "quote_volume": float(candidate.get("quote_volume", 0) or 0),
            "alpaca_quote_volume": float(candidate.get("alpaca_quote_volume", 0) or 0),
            "venue_implied_quote_volume": float(candidate.get("venue_implied_quote_volume", 0) or 0),
            "short_term_volatility": float(candidate.get("short_term_volatility", 0) or 0),
            "stop_distance_pct": float(candidate.get("stop_distance_pct", 0) or 0),
            "execution_profile": str(candidate.get("execution_profile", "") or ""),
            "execution_quality": float(candidate.get("execution_quality", 0) or 0),
            "target_1_r": float(candidate.get("target_1_r", 0) or 0),
            "target_2_r": float(candidate.get("target_2_r", 0) or 0),
            "stop_basis": str(candidate.get("stop_basis", "") or ""),
            "recommended_hold_minutes": float(candidate.get("recommended_hold_minutes", 0) or 0),
            "alpaca_depth_notional": float(candidate.get("alpaca_depth_notional", 0) or 0),
            "alpaca_depth_bid_notional": float(candidate.get("alpaca_depth_bid_notional", 0) or 0),
            "alpaca_depth_ask_notional": float(candidate.get("alpaca_depth_ask_notional", 0) or 0),
            "alpaca_depth_bps": float(candidate.get("alpaca_depth_bps", 0) or 0),
            "alpaca_depth_proxy_ok": bool(candidate.get("alpaca_depth_proxy_ok", False)),
            "venue_name": str(candidate.get("venue_name", "Kraken") or "Kraken"),
            "venue_symbol": str(candidate.get("venue_symbol", "") or ""),
            "venue_bid": float(candidate.get("venue_bid", 0) or 0),
            "venue_ask": float(candidate.get("venue_ask", 0) or 0),
            "venue_mid": float(candidate.get("venue_mid", 0) or 0),
            "venue_spread_pct": float(candidate.get("venue_spread_pct", 0) or 0),
            "venue_quote_time": str(candidate.get("venue_quote_time", "") or ""),
            "venue_quote_age_seconds": float(candidate.get("venue_quote_age_seconds", 0) or 0),
            "venue_tradable": bool(candidate.get("venue_tradable", False)),
            "venue_quote_status": str(candidate.get("venue_quote_status", "") or ""),
            "venue_depth_notional": float(candidate.get("venue_depth_notional", 0) or 0),
            "venue_depth_bid_notional": float(candidate.get("venue_depth_bid_notional", 0) or 0),
            "venue_depth_ask_notional": float(candidate.get("venue_depth_ask_notional", 0) or 0),
            "venue_depth_bps": float(candidate.get("venue_depth_bps", 0) or 0),
            "venue_quote_volume_24h": float(candidate.get("venue_quote_volume_24h", 0) or 0),
            "alpaca_venue_price_deviation_pct": float(candidate.get("alpaca_venue_price_deviation_pct", 0) or 0),
            "venue_quote_snapshot": dict(candidate.get("venue_quote_snapshot", {}) or {}),
            "market_regime": str(candidate.get("market_regime", "") or ""),
            "btc_return_15m": float(candidate.get("btc_return_15m", 0) or 0),
            "btc_return_30m": float(candidate.get("btc_return_30m", 0) or 0),
            "eth_return_15m": float(candidate.get("eth_return_15m", 0) or 0),
            "eth_return_30m": float(candidate.get("eth_return_30m", 0) or 0),
            "regime_risk": float(candidate.get("regime_risk", 0) or 0),
        },
        feed=str(candidate.get("feed", "crypto")),
        data_confidence=str(candidate.get("data_confidence", "Alpaca Crypto")),
        limitations=str(candidate.get("limitations", "Venue-specific crypto data; not consolidated global tape.")),
        settings_snapshot=dict(settings_snapshot),
    )


def _round_price(price: float) -> float:
    if price >= 10:
        return round(price, 2)
    if price >= 1:
        return round(price, 4)
    return round(price, 6)


def _min_tick(price: float) -> float:
    if price >= 10:
        return 0.01
    if price >= 1:
        return 0.0001
    return 0.000001


def _execution_model(row: Mapping[str, object], entry: float, vwap: float) -> dict[str, object]:
    score = float(row.get("score", 0) or 0)
    phase = str(row.get("phase", "Expansion") or "Expansion")
    breakout = max(0.0, float(row.get("breakout_strength", 0) or 0))
    acceleration = max(0.0, float(row.get("acceleration", 0) or 0))
    reversal_risk = float(row.get("reversal_risk", 0) or 0)
    liquidity = float(row.get("liquidity_quality", 0) or 0)
    vwap_extension = max(0.0, float(row.get("distance_from_vwap_pct", 0) or 0))
    volatility = max(0.0, float(row.get("short_term_volatility", 0) or 0))
    regime = str(row.get("market_regime", "") or "")

    quality = _execution_quality(score, breakout, acceleration, reversal_risk, liquidity, vwap_extension, regime)
    profile = _execution_profile(phase, quality, reversal_risk, liquidity, vwap_extension, regime)
    stop_pct = _stop_distance_pct(profile, volatility, reversal_risk, liquidity, vwap_extension, regime)
    volatility_stop = entry * (1 - stop_pct / 100)
    vwap_buffer = min(0.012, 0.004 + volatility * 0.006)
    vwap_stop = vwap * (1 - vwap_buffer) if 0 < vwap < entry else volatility_stop
    if profile == "expansion_runner" and 0 < vwap < entry and vwap_extension <= 4:
        raw_stop = max(volatility_stop, vwap_stop)
        stop_basis = "vwap_structure"
    elif profile == "defensive_scalp":
        raw_stop = volatility_stop
        stop_basis = "volatility_defensive"
    else:
        raw_stop = max(volatility_stop, vwap_stop)
        stop_basis = "hybrid_structure"

    raw_stop = min(raw_stop, entry - _min_tick(entry))
    risk = max(_min_tick(entry), entry - raw_stop)
    target_1_r, target_2_r = _target_multiples(profile, quality, breakout, reversal_risk, vwap_extension, regime)
    return {
        "execution_profile": profile,
        "execution_quality": round(quality * 10, 2),
        "risk": risk,
        "target_1_r": round(target_1_r, 2),
        "target_2_r": round(target_2_r, 2),
        "stop_basis": stop_basis,
        "recommended_hold_minutes": _recommended_hold_minutes(profile, quality, phase, regime),
    }


def _execution_quality(
    score: float,
    breakout: float,
    acceleration: float,
    reversal_risk: float,
    liquidity: float,
    vwap_extension: float,
    regime: str,
) -> float:
    raw = (
        0.30 * _unit((score - 7.0) / 2.0)
        + 0.20 * _unit(breakout / 3.0)
        + 0.18 * _unit(acceleration / 3.0)
        + 0.16 * _unit((liquidity - 6.0) / 4.0)
        + 0.16 * _unit((4.5 - reversal_risk) / 4.5)
    )
    raw -= max(0.0, vwap_extension - 4.0) * 0.035
    if regime == "Caution":
        raw -= 0.12
    elif regime == "Risk-Off":
        raw -= 0.25
    return _unit(raw)


def _execution_profile(
    phase: str,
    quality: float,
    reversal_risk: float,
    liquidity: float,
    vwap_extension: float,
    regime: str,
) -> str:
    if regime in {"Caution", "Risk-Off"} or reversal_risk >= 4.5 or vwap_extension >= 5.0 or liquidity < 7:
        return "defensive_scalp"
    if phase == "Ignition" and quality >= 0.68 and reversal_risk <= 3.2:
        return "expansion_runner"
    return "balanced_momentum"


def _stop_distance_pct(
    profile: str,
    volatility: float,
    reversal_risk: float,
    liquidity: float,
    vwap_extension: float,
    regime: str,
) -> float:
    base = 0.72 + volatility * 3.0 + reversal_risk * 0.10 + max(0.0, vwap_extension - 2.0) * 0.08
    base -= max(0.0, liquidity - 7.0) * 0.07
    if profile == "expansion_runner":
        base += 0.20
    elif profile == "defensive_scalp":
        base -= 0.15
    if regime == "Caution":
        base -= 0.10
    elif regime == "Risk-Off":
        base -= 0.20
    return max(0.55, min(2.75, base))


def _target_multiples(
    profile: str,
    quality: float,
    breakout: float,
    reversal_risk: float,
    vwap_extension: float,
    regime: str,
) -> tuple[float, float]:
    if profile == "expansion_runner":
        target_1_r = 1.35
        target_2_r = 2.65 + quality * 0.75 + min(0.35, breakout / 10)
    elif profile == "defensive_scalp":
        target_1_r = 1.0
        target_2_r = 2.05 + quality * 0.30
    else:
        target_1_r = 1.2
        target_2_r = 2.25 + quality * 0.55 + min(0.25, breakout / 14)
    target_2_r -= max(0.0, reversal_risk - 3.5) * 0.08
    target_2_r -= max(0.0, vwap_extension - 4.0) * 0.06
    if regime == "Caution":
        target_2_r -= 0.18
    elif regime == "Risk-Off":
        target_2_r -= 0.35
    return target_1_r, max(2.0, min(3.6, target_2_r))


def _recommended_hold_minutes(profile: str, quality: float, phase: str, regime: str) -> int:
    if profile == "expansion_runner":
        hold = 30 + int(quality * 15)
    elif profile == "defensive_scalp":
        hold = 12 + int(quality * 8)
    else:
        hold = 18 + int(quality * 12)
    if phase == "Ignition":
        hold += 4
    if regime in {"Caution", "Risk-Off"}:
        hold -= 5
    return int(max(10, min(50, hold)))


def _unit(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
