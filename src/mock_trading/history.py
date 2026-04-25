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
        weights = settings.get("score_weights") if isinstance(settings.get("score_weights"), Mapping) else {}
        trade_fills = fills_by_trade.get(trade_id, [])
        fill_summary = ", ".join(
            f"{fill.get('fill_type')} {fill.get('shares')} @ {float(fill.get('price', 0) or 0):.2f}"
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
                "max_hold_minutes": trade.get("max_hold_minutes"),
                "realized_pnl": trade.get("realized_pnl"),
                "exit_reason": trade.get("exit_reason"),
                "closed_at": trade.get("closed_at"),
                "notes": trade.get("notes"),
                "fills": len(trade_fills),
                "fill_summary": fill_summary,
                "feed": settings.get("alpaca_feed") or card.get("feed"),
                "data_confidence": settings.get("data_confidence") or card.get("data_confidence"),
                "settings_min_score": settings.get("min_score"),
                "settings_alert_score": settings.get("alert_score"),
                "settings_shortlist_size": settings.get("shortlist_size"),
                "settings_max_stop_distance_pct": settings.get("max_stop_distance_pct"),
                "settings_min_risk_reward": settings.get("min_risk_reward"),
                "settings_max_vwap_extension_pct": settings.get("max_vwap_extension_pct"),
                "settings_basic_min_iex_adv": settings.get("basic_min_iex_avg_daily_volume"),
                "settings_basic_max_universe": settings.get("basic_max_universe_symbols"),
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
