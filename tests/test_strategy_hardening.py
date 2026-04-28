from __future__ import annotations

from src.features.rvol import compute_rvol
from src.mock_trading.recommendations import recommend_entry_controls
from src.scoring.veto_engine import apply_veto_logic


def test_crypto_rvol_uses_24_hour_session_baseline() -> None:
    bars = [{"v": 100} for _ in range(90)]

    crypto_rvol = compute_rvol(bars, avg_daily_volume=144_000, session_minutes=1440)
    equity_style_rvol = compute_rvol(bars, avg_daily_volume=144_000, session_minutes=390)

    assert round(crypto_rvol, 2) == 1.0
    assert crypto_rvol > equity_style_rvol


def test_risk_off_regime_blocks_altcoin_longs_but_not_btc_eth() -> None:
    alt = _crypto_candidate(ticker="SOL/USD", market_regime="Risk-Off")
    btc = _crypto_candidate(ticker="BTC/USD", market_regime="Risk-Off")

    alt_result = apply_veto_logic(alt)
    btc_result = apply_veto_logic(btc)

    assert alt_result.valid is False
    assert "Crypto regime is risk-off for altcoin longs." in alt_result.reasons
    assert btc_result.valid is True


def test_caution_regime_makes_entry_controls_more_conservative() -> None:
    constructive = _valid_card(market_regime="Constructive")
    caution = _valid_card(market_regime="Caution")

    constructive_controls = recommend_entry_controls(constructive, available_cash=10_000)
    caution_controls = recommend_entry_controls(caution, available_cash=10_000)

    assert caution_controls["dollar_amount"] < constructive_controls["dollar_amount"]
    assert caution_controls["max_hold_minutes"] < constructive_controls["max_hold_minutes"]
    assert caution_controls["target_1_pct"] == 85
    assert caution_controls["target_2_pct"] == 15


def _crypto_candidate(**overrides: object) -> dict[str, object]:
    candidate = {
        "ticker": "BTC/USD",
        "asset_class": "crypto",
        "score": 8.3,
        "phase": "Ignition",
        "has_catalyst": False,
        "stop_distance_pct": 2.1,
        "risk_reward": 2.4,
        "liquidity_quality": 7.5,
        "distance_from_vwap_pct": 3.0,
        "spread_pct": 0.08,
        "venue_quote_status": "ok",
        "venue_tradable": True,
        "venue_bid": 99.9,
        "venue_ask": 100.1,
        "venue_spread_pct": 0.2,
        "venue_quote_age_seconds": 2,
        "venue_depth_notional": 50_000,
        "alpaca_venue_price_deviation_pct": 0.1,
        "market_regime": "Constructive",
    }
    candidate.update(overrides)
    return candidate


def _valid_card(**overrides: object) -> dict[str, object]:
    card = {
        "ticker": "SOL/USD",
        "verdict": "Valid Trade",
        "score": 8.9,
        "phase": "Ignition",
        "entry": 100,
        "features": {
            "reversal_risk": 2,
            "liquidity_quality": 8,
            "distance_from_vwap_pct": 2,
            "market_regime": "Constructive",
        },
    }
    if "market_regime" in overrides:
        card["features"]["market_regime"] = overrides.pop("market_regime")
    card.update(overrides)
    return card
