from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Mapping

from src.providers.base import BaseMarketDataProvider
from src.storage.repositories import (
    add_mock_fill,
    get_mock_trade,
    list_mock_fills,
    list_mock_trades,
    save_portfolio_snapshot,
    update_mock_trade,
)


def update_open_mock_trades(provider: BaseMarketDataProvider) -> list[dict[str, object]]:
    results = []
    for trade in list_mock_trades(status="open"):
        results.append(update_mock_trade_results(int(trade["id"]), provider))
    return results


def update_mock_trade_results(trade_id: int, provider: BaseMarketDataProvider) -> dict[str, object]:
    trade = get_mock_trade(trade_id)
    if not trade or trade.get("status") != "open":
        return {"trade_id": trade_id, "updated": False, "reason": "Trade is not open."}

    entered_at = _parse_dt(str(trade["entered_at"]))
    max_hold_at = entered_at + timedelta(minutes=int(trade["max_hold_minutes"]))
    now = datetime.now(timezone.utc)
    end = min(now, max_hold_at + timedelta(minutes=1))
    bars = provider.get_historical_bars([str(trade["ticker"])], "1Min", entered_at, end).get(str(trade["ticker"]), [])
    fills = list_mock_fills(trade_id)
    state = _state_from_trade_and_fills(trade, fills)
    if not bars:
        return {"trade_id": trade_id, "updated": False, "reason": "No bars available yet."}

    for bar in sorted(bars, key=lambda item: str(item.get("t", ""))):
        bar_time = _parse_dt(str(bar["t"]))
        if bar_time <= state["last_event_at"]:
            continue
        high = float(bar.get("h", 0) or 0)
        low = float(bar.get("l", 0) or 0)
        close = float(bar.get("c", 0) or 0)
        state["last_price"] = close or state["last_price"]
        filled_target_1_this_bar = False

        if not state["target_1_filled"]:
            stop_hit = low <= state["current_stop"]
            target_1_hit = high >= float(trade["target_1"])
            if stop_hit:
                _record_fill(trade, state, bar_time, "stop", state["remaining_shares"], state["current_stop"])
                break
            if target_1_hit:
                tranche = max(1, round(int(trade["shares"]) * float(trade["target_1_pct"]) / 100))
                _record_fill(trade, state, bar_time, "target_1", min(tranche, state["remaining_shares"]), float(trade["target_1"]))
                state["target_1_filled"] = True
                filled_target_1_this_bar = True
                if int(trade.get("move_stop_to_breakeven", 1)):
                    state["current_stop"] = float(trade["entry"])
                if state["remaining_shares"] <= 0:
                    break

        if state["target_1_filled"] and state["remaining_shares"] > 0 and not filled_target_1_this_bar:
            if low <= state["current_stop"]:
                _record_fill(trade, state, bar_time, "breakeven_stop", state["remaining_shares"], state["current_stop"])
                break
            if high >= float(trade["target_2"]):
                _record_fill(trade, state, bar_time, "target_2", state["remaining_shares"], float(trade["target_2"]))
                break

        if bar_time >= max_hold_at and state["remaining_shares"] > 0:
            _record_fill(trade, state, bar_time, "max_hold", state["remaining_shares"], close)
            break

    status = "closed" if state["remaining_shares"] <= 0 else "open"
    update_mock_trade(
        trade_id,
        {
            "status": status,
            "current_stop": state["current_stop"],
            "remaining_shares": state["remaining_shares"],
            "last_price": state["last_price"],
            "realized_pnl": state["realized_pnl"],
            "closed_at": state["closed_at"],
            "exit_reason": state["exit_reason"],
        },
    )
    save_portfolio_snapshot()
    return {"trade_id": trade_id, "updated": True, "status": status, "exit_reason": state["exit_reason"]}


def _state_from_trade_and_fills(trade: Mapping[str, object], fills: list[Mapping[str, object]]) -> dict[str, object]:
    remaining = int(trade["shares"])
    realized_pnl = 0.0
    target_1_filled = False
    last_event_at = _parse_dt(str(trade["entered_at"]))
    closed_at = None
    exit_reason = None
    for fill in fills:
        remaining -= int(fill["shares"])
        realized_pnl += float(fill["pnl"])
        target_1_filled = target_1_filled or fill["fill_type"] == "target_1"
        last_event_at = max(last_event_at, _parse_dt(str(fill["fill_time"])))
        closed_at = fill["fill_time"] if remaining <= 0 else closed_at
        exit_reason = fill["fill_type"] if remaining <= 0 else exit_reason
    return {
        "remaining_shares": max(0, remaining),
        "target_1_filled": target_1_filled,
        "current_stop": float(trade["current_stop"]),
        "last_price": float(trade.get("last_price", trade["entry"])),
        "realized_pnl": realized_pnl,
        "last_event_at": last_event_at,
        "closed_at": closed_at,
        "exit_reason": exit_reason,
    }


def _record_fill(
    trade: Mapping[str, object],
    state: dict[str, object],
    fill_time: datetime,
    fill_type: str,
    shares: int,
    price: float,
) -> None:
    if shares <= 0:
        return
    pnl = (price - float(trade["entry"])) * shares
    state["remaining_shares"] = int(state["remaining_shares"]) - shares
    state["realized_pnl"] = float(state["realized_pnl"]) + pnl
    state["last_event_at"] = fill_time
    state["last_price"] = price
    if int(state["remaining_shares"]) <= 0:
        state["closed_at"] = fill_time.isoformat()
        state["exit_reason"] = fill_type
    add_mock_fill(
        {
            "trade_id": trade["id"],
            "fill_time": fill_time.isoformat(),
            "fill_type": fill_type,
            "shares": shares,
            "price": price,
            "pnl": pnl,
            "payload": {"ticker": trade["ticker"], "entry": trade["entry"]},
        }
    )


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
