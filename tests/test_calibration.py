from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from src.analysis.calibration import build_calibration_report, scan_score_diagnostics


def test_calibration_collects_until_minimum_closed_trades() -> None:
    trades = [_trade(index, score=8.0, pnl=20) for index in range(5)]

    report = build_calibration_report(trades, min_trades=10, holdout_pct=30)

    assert report["readiness"] == "collecting"
    assert report["closed_trades"] == 5
    assert report["candidates"] == []
    assert report["auto_apply"] is False


def test_calibration_recommends_only_after_holdout_validation() -> None:
    trades = []
    for index in range(28):
        trades.append(_trade(index, score=8.2, pnl=55))
    for index in range(28, 34):
        trades.append(_trade(index, score=6.8, pnl=-25))

    report = build_calibration_report(trades, min_trades=30, holdout_pct=30)

    assert report["readiness"] == "ready"
    assert report["baseline"]["trades"] == 34
    assert report["by_execution_profile"]["expansion_runner"]["trades"] == 28
    assert report["by_target_split"]["60/40"]["trades"] == 28
    assert report["by_target_2_r"]["3.2+"]["trades"] == 28
    assert report["candidates"]
    assert report["recommendation"]["action"] in {"review_candidate", "do_not_change"}
    assert report["auto_apply"] is False


def test_scan_score_diagnostics_counts_buckets_and_vetoes() -> None:
    report = scan_score_diagnostics(
        [
            {"score": 6.8, "verdict": "Invalid", "veto_reasons": ["Score below 7.5."]},
            {"score": 8.1, "verdict": "Valid Trade", "veto_reasons": []},
            {"score": 8.8, "verdict": "Invalid", "veto_reasons": ["Kraken spread above 0.35%."]},
        ]
    )

    assert report["candidate_count"] == 3
    assert report["valid_count"] == 1
    assert report["score_buckets"]["<7"] == 1
    assert report["score_buckets"]["8.0-8.49"] == 1
    assert report["top_veto_reasons"]["Score below 7.5."] == 1


def _trade(index: int, score: float, pnl: float) -> dict[str, object]:
    entered_at = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=index)
    return {
        "id": index + 1,
        "status": "closed",
        "entered_at": entered_at.isoformat(),
        "closed_at": (entered_at + timedelta(minutes=20)).isoformat(),
        "ticker": "BTC/USD" if index % 2 else "ETH/USD",
        "phase": "Ignition" if index % 3 else "Expansion",
        "score": score,
        "shares": 10,
        "risk_per_share": 1,
        "target_1_pct": 60 if pnl > 0 else 85,
        "target_2_pct": 40 if pnl > 0 else 15,
        "realized_pnl": pnl,
        "exit_reason": "target_2" if pnl > 0 else "stop",
        "card_json": json.dumps(
            {
                "market_regime": "Constructive" if pnl > 0 else "Caution",
                "execution_profile": "expansion_runner" if pnl > 0 else "defensive_scalp",
                "target_2_r": 3.4 if pnl > 0 else 2.1,
            }
        ),
    }
