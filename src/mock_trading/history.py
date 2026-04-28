from __future__ import annotations

import json
from collections import defaultdict
from typing import Mapping


def build_trade_history_rows(
    trades: list[Mapping[str, object]],
    fills: list[Mapping[str, object]],
) -> list[dict[str, object]]:
    fills_by_trade: dict[int, list[Mapping[str, object]]] = defaultdict(list)
    for fill in fills:
        fills_by_trade[int(fill["trade_id"])].append(fill)

    rows = []
    for trade in trades:
        trade_id = int(trade["id"])
        settings = _json_object(trade.get("settings_json"))
        card = _json_object(trade.get("card_json"))
        venue_bid = card.get("venue_bid", card.get("rh_bid"))
        venue_ask = card.get("venue_ask", card.get("rh_ask"))
        venue_spread_pct = card.get("venue_spread_pct", card.get("rh_spread_pct"))
        venue_quote_time = card.get("venue_quote_time", card.get("rh_quote_time"))
        venue_deviation = card.get("alpaca_venue_price_deviation_pct", card.get("alpaca_rh_price_deviation_pct"))
        weights = settings.get("score_weights") if isinstance(settings.get("score_weights"), Mapping) else {}
        trade_fills = fills_by_trade.get(trade_id, [])
        fill_summary = ", ".join(
            f"{fill.get('fill_type')} {float(fill.get('shares', 0) or 0):.8f} @ {float(fill.get('price', 0) or 0):.6f}"
            for fill in trade_fills
        )

        rows.append(
            {
                "id": trade_id,
                "entered_at": trade.get("entered_at"),
                "ticker": trade.get("ticker"),
                "status": trade.get("status"),
                "phase": trade.get("phase"),
                "score": trade.get("score"),
                "dollar_amount": trade.get("dollar_amount"),
                "shares": trade.get("shares"),
                "remaining_shares": trade.get("remaining_shares"),
                "entry": trade.get("entry"),
                "stop": trade.get("stop"),
                "current_stop": trade.get("current_stop"),
                "target_1": trade.get("target_1"),
                "target_2": trade.get("target_2"),
                "target_1_pct": trade.get("target_1_pct"),
                "target_2_pct": trade.get("target_2_pct"),
                "execution_profile": card.get("execution_profile"),
                "execution_quality": card.get("execution_quality"),
                "target_1_r": card.get("target_1_r"),
                "target_2_r": card.get("target_2_r"),
                "stop_basis": card.get("stop_basis"),
                "stop_distance_pct": card.get("stop_distance_pct"),
                "max_hold_minutes": trade.get("max_hold_minutes"),
                "realized_pnl": trade.get("realized_pnl"),
                "exit_reason": trade.get("exit_reason"),
                "closed_at": trade.get("closed_at"),
                "notes": trade.get("notes"),
                "fills": len(trade_fills),
                "fill_summary": fill_summary,
                "venue_name": card.get("venue_name") or ("Robinhood" if "rh_ask" in card else None),
                "venue_symbol": card.get("venue_symbol"),
                "venue_bid": venue_bid,
                "venue_ask": venue_ask,
                "venue_spread_pct": venue_spread_pct,
                "venue_quote_time": venue_quote_time,
                "venue_depth_notional": card.get("venue_depth_notional"),
                "venue_depth_bps": card.get("venue_depth_bps"),
                "alpaca_venue_price_deviation_pct": venue_deviation,
                "alpaca_depth_notional": card.get("alpaca_depth_notional"),
                "alpaca_depth_bps": card.get("alpaca_depth_bps"),
                "feed": settings.get("feed") or settings.get("alpaca_feed") or card.get("feed"),
                "data_confidence": settings.get("data_confidence") or card.get("data_confidence"),
                "settings_crypto_location": settings.get("crypto_location"),
                "settings_crypto_universe_mode": settings.get("crypto_universe_mode"),
                "settings_crypto_scan_minutes": settings.get("crypto_scan_minutes"),
                "settings_crypto_min_quote_volume": settings.get("crypto_min_quote_volume"),
                "settings_crypto_max_spread_pct": settings.get("crypto_max_spread_pct"),
                "settings_crypto_min_orderbook_notional_depth": settings.get("crypto_min_orderbook_notional_depth"),
                "settings_crypto_depth_bps": settings.get("crypto_depth_bps"),
                "settings_venue_provider": settings.get("venue_provider"),
                "settings_kraken_max_spread_pct": settings.get("kraken_max_spread_pct"),
                "settings_kraken_max_quote_age": settings.get("kraken_max_quote_age_seconds"),
                "settings_kraken_min_orderbook_notional_depth": settings.get("kraken_min_orderbook_notional_depth"),
                "settings_max_alpaca_venue_deviation_pct": settings.get("max_alpaca_venue_deviation_pct"),
                "settings_legacy_robinhood_quote_gate": settings.get("robinhood_quote_gate_enabled"),
                "settings_legacy_robinhood_max_spread_pct": settings.get("robinhood_max_spread_pct"),
                "settings_legacy_robinhood_max_quote_age": settings.get("robinhood_max_quote_age_seconds"),
                "settings_legacy_max_alpaca_rh_deviation_pct": settings.get("max_alpaca_rh_deviation_pct"),
                "settings_min_score": settings.get("min_score"),
                "settings_alert_score": settings.get("alert_score"),
                "settings_shortlist_size": settings.get("shortlist_size"),
                "settings_max_stop_distance_pct": settings.get("max_stop_distance_pct"),
                "settings_min_risk_reward": settings.get("min_risk_reward"),
                "settings_max_vwap_extension_pct": settings.get("max_vwap_extension_pct"),
                "weight_rvol": weights.get("rvol") if isinstance(weights, Mapping) else None,
                "weight_acceleration": weights.get("acceleration") if isinstance(weights, Mapping) else None,
                "weight_breakout": weights.get("breakout_strength") if isinstance(weights, Mapping) else None,
                "weight_catalyst": weights.get("catalyst") if isinstance(weights, Mapping) else None,
                "weight_reversal_risk": weights.get("reversal_risk") if isinstance(weights, Mapping) else None,
            }
        )
    return rows


def _json_object(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    if not value:
        return {}
    try:
        payload = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
