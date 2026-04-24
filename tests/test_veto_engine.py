from __future__ import annotations

from src.scoring.veto_engine import apply_veto_logic


def test_veto_engine_accepts_clean_candidate() -> None:
    result = apply_veto_logic(
        {
            "score": 8.3,
            "phase": "Ignition",
            "has_catalyst": True,
            "stop_distance_pct": 2.1,
            "risk_reward": 2.4,
            "liquidity_quality": 7.5,
            "distance_from_vwap_pct": 3.0,
        }
    )

    assert result.valid is True
    assert result.verdict == "Valid Trade"


def test_veto_engine_rejects_exhausted_candidate() -> None:
    result = apply_veto_logic(
        {
            "score": 8.8,
            "phase": "Exhaustion",
            "has_catalyst": True,
            "stop_distance_pct": 4.2,
            "risk_reward": 1.4,
            "liquidity_quality": 8.0,
            "distance_from_vwap_pct": 11.0,
        }
    )

    assert result.valid is False
    assert any("Phase is Exhaustion" in reason for reason in result.reasons)
    assert any("Stop distance" in reason for reason in result.reasons)

