from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Mapping


def compute_performance(
    trades: list[Mapping[str, object]],
    fills: list[Mapping[str, object]],
    starting_cash: float = 10_000.0,
) -> dict[str, object]:
    closed = [trade for trade in trades if trade.get("status") == "closed"]
    fill_types_by_trade: dict[int, set[str]] = defaultdict(set)
    for fill in fills:
        fill_types_by_trade[int(fill["trade_id"])].add(str(fill["fill_type"]))

    pnls = [float(trade.get("realized_pnl", 0) or 0) for trade in closed]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    r_values = [_r_multiple(trade) for trade in closed]
    expectancy = sum(r_values) / len(r_values) if r_values else 0.0
    equity_curve = _equity_curve(closed, starting_cash)
    return {
        "total_pnl": round(sum(pnls), 2),
        "win_rate": round(len(wins) / len(closed) * 100, 2) if closed else 0.0,
        "average_r": round(expectancy, 2),
        "expectancy": round(expectancy, 2),
        "max_drawdown": round(_max_drawdown(equity_curve), 2),
        "target_1_hit_rate": _hit_rate(closed, fill_types_by_trade, "target_1"),
        "target_2_hit_rate": _hit_rate(closed, fill_types_by_trade, "target_2"),
        "average_hold_minutes": round(_average_hold_minutes(closed), 2),
        "trade_count": len(trades),
        "closed_trade_count": len(closed),
        "open_trade_count": len(trades) - len(closed),
        "equity_curve": equity_curve,
        "pnl_by_phase": _group_pnl(closed, "phase"),
        "pnl_by_ticker": _group_pnl(closed, "ticker"),
        "pnl_by_score_bucket": _score_bucket_pnl(closed),
    }


def _r_multiple(trade: Mapping[str, object]) -> float:
    risk = float(trade.get("risk_per_share", 0) or 0) * int(trade.get("shares", 0) or 0)
    return float(trade.get("realized_pnl", 0) or 0) / risk if risk > 0 else 0.0


def _equity_curve(trades: list[Mapping[str, object]], starting_cash: float) -> list[dict[str, object]]:
    equity = starting_cash
    curve = [{"time": "", "equity": round(equity, 2)}]
    for trade in sorted(trades, key=lambda item: str(item.get("closed_at") or item.get("entered_at") or "")):
        equity += float(trade.get("realized_pnl", 0) or 0)
        curve.append({"time": trade.get("closed_at") or trade.get("entered_at"), "equity": round(equity, 2)})
    return curve


def _max_drawdown(curve: list[Mapping[str, object]]) -> float:
    peak = 0.0
    max_drawdown = 0.0
    for point in curve:
        equity = float(point.get("equity", 0) or 0)
        peak = max(peak, equity)
        if peak:
            max_drawdown = max(max_drawdown, (peak - equity) / peak * 100)
    return max_drawdown


def _hit_rate(
    trades: list[Mapping[str, object]],
    fill_types_by_trade: dict[int, set[str]],
    fill_type: str,
) -> float:
    if not trades:
        return 0.0
    hits = sum(1 for trade in trades if fill_type in fill_types_by_trade.get(int(trade["id"]), set()))
    return round(hits / len(trades) * 100, 2)


def _average_hold_minutes(trades: list[Mapping[str, object]]) -> float:
    durations = []
    for trade in trades:
        entered_at = _parse_dt(str(trade.get("entered_at", "")))
        closed_at = _parse_dt(str(trade.get("closed_at", "")))
        if entered_at and closed_at:
            durations.append((closed_at - entered_at).total_seconds() / 60)
    return sum(durations) / len(durations) if durations else 0.0


def _group_pnl(trades: list[Mapping[str, object]], key: str) -> dict[str, float]:
    grouped: dict[str, float] = defaultdict(float)
    for trade in trades:
        grouped[str(trade.get(key) or "Unknown")] += float(trade.get("realized_pnl", 0) or 0)
    return {key: round(value, 2) for key, value in sorted(grouped.items())}


def _score_bucket_pnl(trades: list[Mapping[str, object]]) -> dict[str, float]:
    grouped: dict[str, float] = defaultdict(float)
    for trade in trades:
        score = float(trade.get("score", 0) or 0)
        bucket = f"{int(score // 0.5 * 0.5)}+"
        if score >= 9:
            bucket = "9+"
        elif score >= 8.5:
            bucket = "8.5-8.99"
        elif score >= 8:
            bucket = "8.0-8.49"
        elif score >= 7.5:
            bucket = "7.5-7.99"
        grouped[bucket] += float(trade.get("realized_pnl", 0) or 0)
    return {key: round(value, 2) for key, value in sorted(grouped.items())}


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

