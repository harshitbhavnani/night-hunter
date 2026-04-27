from __future__ import annotations

from src.scoring.execution_engine import generate_trade_card, generate_trade_card_for_symbol


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


def test_execution_engine_can_generate_card_for_selected_ticker() -> None:
    rows = [
        _valid_row("TOP", 9.1),
        _valid_row("PICK", 8.1),
    ]

    card = generate_trade_card_for_symbol(rows, "PICK")

    assert card is not None
    assert card.ticker == "PICK"
    assert card.score == 8.1


def test_execution_engine_uses_robinhood_ask_for_crypto_entry() -> None:
    row = {
        **_valid_row("BTC/USD", 8.6),
        "asset_class": "crypto",
        "price": 100.0,
        "rh_bid": 100.4,
        "rh_ask": 100.6,
        "rh_mid": 100.5,
        "rh_spread_pct": 0.2,
        "rh_quote_status": "ok",
        "rh_tradable": True,
        "rh_quote_age_seconds": 1,
        "alpaca_rh_price_deviation_pct": 0.5,
        "alpaca_depth_notional": 50_000,
        "alpaca_depth_proxy_ok": True,
    }

    card = generate_trade_card([row])

    assert card is not None
    assert card.verdict == "Valid Trade"
    assert card.entry == 100.6
    assert card.as_dict()["rh_ask"] == 100.6
    assert card.as_dict()["alpaca_depth_proxy_ok"] is True


def _valid_row(ticker: str, score: float) -> dict[str, object]:
    return {
        "ticker": ticker,
        "price": 10.0,
        "vwap": 9.9,
        "score": score,
        "score_breakdown": {"total": score},
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
