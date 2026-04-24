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
    features: Mapping[str, float]

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
        }


def build_execution_candidate(row: Mapping[str, object]) -> Dict[str, object]:
    price = float(row.get("price", 0))
    vwap = float(row.get("vwap", price))
    breakout = max(0.0, float(row.get("breakout_strength", 0)))
    entry = round(price, 2)
    vwap_stop = vwap * 0.992 if 0 < vwap < price else price * 0.975
    structural_stop = max(price * 0.975, vwap_stop)
    stop = round(max(0.01, structural_stop), 2)
    risk = max(0.01, entry - stop)
    extension_penalty = max(0.0, float(row.get("distance_from_vwap_pct", 0)) - 3)
    reward_multiple = max(2.0, min(3.2, 2.4 + breakout / 4 - extension_penalty / 10))
    target_1 = round(entry + risk * 1.5, 2)
    target_2 = round(entry + risk * reward_multiple, 2)
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


def _card_from_candidate(candidate: Mapping[str, object], verdict: str, veto_reasons: List[str]) -> TradeCard:
    score = float(candidate.get("score", 0))
    phase = str(candidate.get("phase", "Expansion"))
    life = "10-25 minutes" if phase == "Ignition" else "5-15 minutes" if phase == "Expansion" else "Stand down"
    reasons = [
        f"RVOL {float(candidate.get('rvol', 0)):.1f}x",
        f"acceleration {float(candidate.get('acceleration', 0)):.2f}",
        f"breakout {float(candidate.get('breakout_strength', 0)):.2f}%",
        f"VWAP distance {float(candidate.get('distance_from_vwap_pct', 0)):.2f}%",
    ]
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
        },
    )
