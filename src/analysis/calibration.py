from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class CalibrationCandidate:
    name: str
    value: object
    train_trades: int
    holdout_trades: int
    train_expectancy_r: float
    holdout_expectancy_r: float
    holdout_win_rate: float
    max_drawdown_r: float

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "value": self.value,
            "train_trades": self.train_trades,
            "holdout_trades": self.holdout_trades,
            "train_expectancy_r": self.train_expectancy_r,
            "holdout_expectancy_r": self.holdout_expectancy_r,
            "holdout_win_rate": self.holdout_win_rate,
            "max_drawdown_r": self.max_drawdown_r,
        }


def build_calibration_report(
    trades: list[Mapping[str, object]],
    min_trades: int = 30,
    holdout_pct: float = 30.0,
) -> dict[str, object]:
    closed = [trade for trade in trades if trade.get("status") == "closed"]
    closed.sort(key=lambda item: str(item.get("closed_at") or item.get("entered_at") or ""))
    r_trades = [_trade_with_r(trade) for trade in closed]
    readiness = "ready" if len(r_trades) >= min_trades else "collecting"
    candidates = _candidate_settings(r_trades, min_trades, holdout_pct) if readiness == "ready" else []
    return {
        "readiness": readiness,
        "closed_trades": len(r_trades),
        "min_trades": min_trades,
        "holdout_pct": holdout_pct,
        "message": _readiness_message(len(r_trades), min_trades),
        "baseline": _summary(r_trades),
        "by_phase": _group_summary(r_trades, "phase"),
        "by_score_bucket": _score_bucket_summary(r_trades),
        "by_market_regime": _card_group_summary(r_trades, "market_regime"),
        "by_execution_profile": _card_group_summary(r_trades, "execution_profile"),
        "by_target_split": _target_split_summary(r_trades),
        "by_target_2_r": _card_numeric_bucket_summary(r_trades, "target_2_r", (2.0, 2.4, 2.8, 3.2)),
        "common_exit_reasons": dict(Counter(str(trade.get("exit_reason") or "open") for trade in r_trades).most_common()),
        "candidates": [candidate.as_dict() for candidate in candidates],
        "recommendation": _recommendation(candidates),
        "auto_apply": False,
    }


def scan_score_diagnostics(rows: Iterable[Mapping[str, object]]) -> dict[str, object]:
    rows = list(rows)
    scores = [float(row.get("score", 0) or 0) for row in rows]
    reason_counts: Counter[str] = Counter()
    for row in rows:
        for reason in row.get("veto_reasons") or []:
            reason_counts[str(reason)] += 1
    return {
        "candidate_count": len(rows),
        "valid_count": sum(1 for row in rows if row.get("verdict") == "Valid Trade"),
        "score_min": round(min(scores), 2) if scores else 0.0,
        "score_median": round(_percentile(scores, 0.5), 2) if scores else 0.0,
        "score_max": round(max(scores), 2) if scores else 0.0,
        "score_buckets": _score_counts(scores),
        "top_veto_reasons": dict(reason_counts.most_common(6)),
    }


def _candidate_settings(
    trades: list[dict[str, object]],
    min_trades: int,
    holdout_pct: float,
) -> list[CalibrationCandidate]:
    split_index = max(1, int(len(trades) * (1 - max(5.0, min(60.0, holdout_pct)) / 100)))
    train = trades[:split_index]
    holdout = trades[split_index:]
    if len(train) < max(10, min_trades // 2) or len(holdout) < max(5, min_trades // 4):
        return []

    candidates: list[CalibrationCandidate] = []
    for threshold in (6.5, 7.0, 7.5, 8.0, 8.5):
        train_subset = [trade for trade in train if float(trade.get("score", 0) or 0) >= threshold]
        holdout_subset = [trade for trade in holdout if float(trade.get("score", 0) or 0) >= threshold]
        if len(train_subset) < 5 or len(holdout_subset) < 3:
            continue
        candidates.append(
            CalibrationCandidate(
                name="min_score",
                value=threshold,
                train_trades=len(train_subset),
                holdout_trades=len(holdout_subset),
                train_expectancy_r=round(_expectancy(train_subset), 3),
                holdout_expectancy_r=round(_expectancy(holdout_subset), 3),
                holdout_win_rate=round(_win_rate(holdout_subset), 2),
                max_drawdown_r=round(_max_drawdown_r(holdout_subset), 3),
            )
        )
    return sorted(
        candidates,
        key=lambda item: (item.holdout_expectancy_r, item.holdout_trades, -item.max_drawdown_r),
        reverse=True,
    )


def _recommendation(candidates: list[CalibrationCandidate]) -> dict[str, object]:
    if not candidates:
        return {
            "action": "collect_more_data",
            "reason": "Not enough closed trades for walk-forward calibration.",
        }
    best = candidates[0]
    if best.holdout_expectancy_r <= 0 or best.holdout_trades < 3:
        return {
            "action": "do_not_change",
            "reason": "No candidate improved holdout expectancy with enough trades.",
        }
    return {
        "action": "review_candidate",
        "parameter": best.name,
        "value": best.value,
        "reason": "Best holdout expectancy among tested thresholds. Review before applying.",
    }


def _trade_with_r(trade: Mapping[str, object]) -> dict[str, object]:
    row = dict(trade)
    risk = float(row.get("risk_per_share", 0) or 0) * float(row.get("shares", 0) or 0)
    pnl = float(row.get("realized_pnl", 0) or 0)
    row["r_multiple"] = pnl / risk if risk > 0 else 0.0
    row["card"] = _json_object(row.get("card_json"))
    return row


def _summary(trades: list[Mapping[str, object]]) -> dict[str, object]:
    return {
        "trades": len(trades),
        "expectancy_r": round(_expectancy(trades), 3),
        "win_rate": round(_win_rate(trades), 2),
        "average_score": round(sum(float(trade.get("score", 0) or 0) for trade in trades) / len(trades), 2)
        if trades
        else 0.0,
        "max_drawdown_r": round(_max_drawdown_r(trades), 3),
    }


def _group_summary(trades: list[Mapping[str, object]], key: str) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for trade in trades:
        grouped[str(trade.get(key) or "Unknown")].append(trade)
    return {name: _summary(rows) for name, rows in sorted(grouped.items())}


def _card_group_summary(trades: list[Mapping[str, object]], key: str) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for trade in trades:
        card = trade.get("card")
        value = card.get(key) if isinstance(card, Mapping) else None
        grouped[str(value or "Unknown")].append(trade)
    return {name: _summary(rows) for name, rows in sorted(grouped.items())}


def _score_bucket_summary(trades: list[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for trade in trades:
        score = float(trade.get("score", 0) or 0)
        grouped[_score_bucket(score)].append(trade)
    return {name: _summary(rows) for name, rows in sorted(grouped.items())}


def _target_split_summary(trades: list[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for trade in trades:
        t1 = float(trade.get("target_1_pct", 0) or 0)
        t2 = float(trade.get("target_2_pct", 0) or 0)
        label = f"{t1:.0f}/{t2:.0f}" if t1 or t2 else "Unknown"
        grouped[label].append(trade)
    return {name: _summary(rows) for name, rows in sorted(grouped.items())}


def _card_numeric_bucket_summary(
    trades: list[Mapping[str, object]],
    key: str,
    thresholds: tuple[float, ...],
) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for trade in trades:
        card = trade.get("card")
        value = float(card.get(key, 0) or 0) if isinstance(card, Mapping) else 0.0
        grouped[_numeric_bucket(value, thresholds)].append(trade)
    return {name: _summary(rows) for name, rows in sorted(grouped.items())}


def _score_bucket(score: float) -> str:
    if score >= 9:
        return "9+"
    if score >= 8.5:
        return "8.5-8.99"
    if score >= 8:
        return "8.0-8.49"
    if score >= 7.5:
        return "7.5-7.99"
    if score >= 7:
        return "7.0-7.49"
    return "<7"


def _numeric_bucket(value: float, thresholds: tuple[float, ...]) -> str:
    if value <= 0:
        return "Unknown"
    previous = 0.0
    for threshold in thresholds:
        if value < threshold:
            return f"{previous:.1f}-{threshold:.1f}"
        previous = threshold
    return f"{thresholds[-1]:.1f}+"


def _score_counts(scores: list[float]) -> dict[str, int]:
    counts: Counter[str] = Counter(_score_bucket(score) for score in scores)
    return {key: counts.get(key, 0) for key in ("<7", "7.0-7.49", "7.5-7.99", "8.0-8.49", "8.5-8.99", "9+")}


def _expectancy(trades: list[Mapping[str, object]]) -> float:
    return sum(float(trade.get("r_multiple", 0) or 0) for trade in trades) / len(trades) if trades else 0.0


def _win_rate(trades: list[Mapping[str, object]]) -> float:
    if not trades:
        return 0.0
    wins = sum(1 for trade in trades if float(trade.get("r_multiple", 0) or 0) > 0)
    return wins / len(trades) * 100


def _max_drawdown_r(trades: list[Mapping[str, object]]) -> float:
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for trade in trades:
        equity += float(trade.get("r_multiple", 0) or 0)
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * pct))))
    return ordered[index]


def _readiness_message(closed_count: int, min_trades: int) -> str:
    if closed_count >= min_trades:
        return "Enough closed mock trades for guarded walk-forward calibration."
    return f"Collect {min_trades - closed_count} more closed mock trade(s) before trusting calibration output."


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
