from __future__ import annotations

from src.scoring.phase_engine import classify_phase


def test_phase_engine_identifies_ignition() -> None:
    assert (
        classify_phase(
            {
                "rvol": 4.2,
                "acceleration": 2.0,
                "return_15m": 3.5,
                "return_30m": 4.0,
                "reversal_risk": 2.0,
                "distance_from_vwap_pct": 3.0,
            }
        )
        == "Ignition"
    )


def test_phase_engine_identifies_dump() -> None:
    assert (
        classify_phase(
            {
                "rvol": 3.0,
                "acceleration": -2.0,
                "return_15m": -2.5,
                "return_30m": -1.0,
                "reversal_risk": 4.0,
                "distance_from_vwap_pct": 1.0,
            }
        )
        == "Dump"
    )

