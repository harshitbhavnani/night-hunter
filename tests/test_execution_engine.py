from __future__ import annotations

from src.scoring.execution_engine import generate_trade_card


def test_execution_engine_returns_best_valid_trade_card() -> None:
    card = generate_trade_card(
        [
            {
                "ticker": "TEST",
                "price": 10.0,
                "vwap": 9.9,
                "score": 8.6,
                "score_breakdown": {"total": 8.6},
                "phase": "Ignition",
                "has_catalyst": True,
                "catalyst_summary": "Contract award",
                "rvol": 5.2,
                "acceleration": 2.4,
                "breakout_strength": 2.2,
                "reversal_risk": 2.0,
                "liquidity_quality": 8.0,
                "distance_from_vwap_pct": 1.0,
            }
        ]
    )

    assert card is not None
    assert card.verdict == "Valid Trade"
    assert card.ticker == "TEST"
    assert card.risk_reward >= 2.0

