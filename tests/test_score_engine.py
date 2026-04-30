from __future__ import annotations

from src.scoring.score_engine import compute_momentum_score


def test_momentum_score_prioritizes_abnormal_behavior_over_day_gain() -> None:
    high_quality = compute_momentum_score(
        {
            "rvol": 7.0,
            "acceleration": 4.0,
            "breakout_strength": 4.5,
            "catalyst_score": 10.0,
            "reversal_risk": 1.0,
            "day_change_pct": 2.0,
        }
    )
    extended_only = compute_momentum_score(
        {
            "rvol": 1.4,
            "acceleration": 0.2,
            "breakout_strength": 0.0,
            "catalyst_score": 0.0,
            "reversal_risk": 8.0,
            "day_change_pct": 30.0,
        }
    )

    assert high_quality.total >= 8.0
    assert extended_only.total < high_quality.total


def test_crypto_score_scale_rewards_real_90_minute_momentum_without_promoting_drift() -> None:
    real_breakout = compute_momentum_score(
        {
            "rvol": 4.0,
            "acceleration": 1.1,
            "breakout_strength": 1.6,
            "catalyst_score": 0.0,
            "reversal_risk": 2.0,
        }
    )
    quiet_drift = compute_momentum_score(
        {
            "rvol": 2.5,
            "acceleration": 0.05,
            "breakout_strength": 0.01,
            "catalyst_score": 0.0,
            "reversal_risk": 0.4,
        }
    )

    assert real_breakout.total >= 7.0
    assert quiet_drift.total < 3.0
