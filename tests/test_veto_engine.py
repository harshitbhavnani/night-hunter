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


def test_veto_engine_allows_crypto_without_catalyst() -> None:
    result = apply_veto_logic(
        {
            "asset_class": "crypto",
            "score": 8.3,
            "phase": "Ignition",
            "has_catalyst": False,
            "stop_distance_pct": 2.1,
            "risk_reward": 2.4,
            "liquidity_quality": 7.5,
            "distance_from_vwap_pct": 3.0,
            "spread_pct": 0.08,
            "alpaca_depth_notional": 50_000,
            "venue_quote_status": "ok",
            "venue_tradable": True,
            "venue_bid": 99.9,
            "venue_ask": 100.1,
            "venue_spread_pct": 0.2,
            "venue_quote_age_seconds": 2,
            "venue_depth_notional": 50_000,
            "alpaca_venue_price_deviation_pct": 0.1,
        }
    )

    assert result.valid is True


def test_veto_engine_rejects_wide_crypto_spread() -> None:
    result = apply_veto_logic(
        {
            "asset_class": "crypto",
            "score": 8.3,
            "phase": "Ignition",
            "stop_distance_pct": 2.1,
            "risk_reward": 2.4,
            "liquidity_quality": 7.5,
            "distance_from_vwap_pct": 3.0,
            "spread_pct": 0.8,
            "alpaca_depth_notional": 50_000,
        }
    )

    assert result.valid is False
    assert any("Crypto spread" in reason for reason in result.reasons)


def test_veto_engine_rejects_low_depth_crypto_pair() -> None:
    result = apply_veto_logic(_crypto_candidate(alpaca_depth_notional=1000))

    assert result.valid is False
    assert any("depth proxy" in reason for reason in result.reasons)


def test_veto_engine_rejects_stale_kraken_quote() -> None:
    result = apply_veto_logic(_crypto_candidate(venue_quote_age_seconds=60))

    assert result.valid is False
    assert any("Kraken quote stale" in reason for reason in result.reasons)


def test_veto_engine_rejects_non_tradable_kraken_asset() -> None:
    result = apply_veto_logic(_crypto_candidate(venue_tradable=False))

    assert result.valid is False
    assert any("not tradable on Kraken" in reason for reason in result.reasons)


def test_veto_engine_rejects_alpaca_kraken_deviation() -> None:
    result = apply_veto_logic(_crypto_candidate(alpaca_venue_price_deviation_pct=1.5))

    assert result.valid is False
    assert any("Alpaca/Kraken price deviation" in reason for reason in result.reasons)


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


def _crypto_candidate(**overrides: object) -> dict[str, object]:
    candidate = {
        "asset_class": "crypto",
        "score": 8.3,
        "phase": "Ignition",
        "has_catalyst": False,
        "stop_distance_pct": 2.1,
        "risk_reward": 2.4,
        "liquidity_quality": 7.5,
        "distance_from_vwap_pct": 3.0,
        "spread_pct": 0.08,
        "alpaca_depth_notional": 50_000,
        "venue_quote_status": "ok",
        "venue_tradable": True,
        "venue_bid": 99.9,
        "venue_ask": 100.1,
        "venue_spread_pct": 0.2,
        "venue_quote_age_seconds": 2,
        "venue_depth_notional": 50_000,
        "alpaca_venue_price_deviation_pct": 0.1,
    }
    candidate.update(overrides)
    return candidate
