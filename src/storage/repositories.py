from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterable, Mapping
from uuid import uuid4

from src.storage.db import get_connection, init_db


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def row_value(row: object, key: str, index: int = 0) -> object:
    try:
        return row[key]  # type: ignore[index]
    except (KeyError, TypeError, IndexError):
        return row[index]  # type: ignore[index]


def row_to_dict(row: object) -> dict[str, object]:
    if isinstance(row, dict):
        return row
    try:
        return dict(row)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        keys = getattr(row, "keys", lambda: [])()
        if keys:
            return {key: row[key] for key in keys}  # type: ignore[index]
    return {}


def save_universe_snapshot(rows: Iterable[Mapping[str, object]]) -> None:
    init_db()
    created_at = utc_now()
    with get_connection() as connection:
        connection.executemany(
            "INSERT INTO universe_snapshots (created_at, symbol, payload_json) VALUES (?, ?, ?)",
            [(created_at, str(row.get("symbol")), json.dumps(dict(row))) for row in rows],
        )


def get_universe_cache(cache_key: str) -> list[dict[str, object]] | None:
    record = get_universe_cache_record(cache_key)
    if not record:
        return None
    rows = record["rows"]
    return list(rows) if rows else None


def get_universe_cache_record(cache_key: str) -> dict[str, object] | None:
    init_db()
    with get_connection() as connection:
        row = connection.execute(
            "SELECT created_at, payload_json FROM universe_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    if not row:
        return None
    payload = json.loads(str(row_value(row, "payload_json")))
    if isinstance(payload, list):
        rows = payload
        diagnostics = {}
    elif isinstance(payload, dict):
        rows = payload.get("rows", [])
        diagnostics = payload.get("diagnostics", {})
    else:
        return None
    return {
        "created_at": row_value(row, "created_at"),
        "rows": list(rows) if isinstance(rows, list) else [],
        "diagnostics": dict(diagnostics) if isinstance(diagnostics, dict) else {},
    }


def save_universe_cache(
    cache_key: str,
    rows: list[Mapping[str, object]],
    diagnostics: Mapping[str, object] | None = None,
) -> None:
    if not rows:
        return
    init_db()
    payload = {
        "rows": [dict(row) for row in rows],
        "diagnostics": dict(diagnostics or {}),
    }
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO universe_cache (cache_key, created_at, payload_json)
            VALUES (?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET created_at = excluded.created_at, payload_json = excluded.payload_json
            """,
            (cache_key, utc_now(), json.dumps(payload)),
        )


def save_scan(scan_rows: list[Mapping[str, object]], trade_card: Mapping[str, object] | None) -> str:
    init_db()
    scan_id = str(uuid4())
    created_at = utc_now()
    with get_connection() as connection:
        connection.executemany(
            """
            INSERT INTO scan_results (scan_id, created_at, symbol, score, phase, verdict, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    scan_id,
                    created_at,
                    str(row.get("ticker") or row.get("symbol")),
                    float(row.get("score", 0)),
                    str(row.get("phase", "")),
                    str(row.get("verdict", "")),
                    json.dumps(dict(row)),
                )
                for row in scan_rows
            ],
        )
        connection.executemany(
            """
            INSERT INTO shortlist_history (scan_id, created_at, symbol, rank, score)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (scan_id, created_at, str(row.get("ticker") or row.get("symbol")), index + 1, float(row.get("score", 0)))
                for index, row in enumerate(scan_rows[:30])
            ],
        )
        if trade_card:
            connection.execute(
                """
                INSERT INTO trade_cards (scan_id, created_at, symbol, verdict, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    scan_id,
                    created_at,
                    str(trade_card.get("ticker")),
                    str(trade_card.get("verdict")),
                    json.dumps(dict(trade_card)),
                ),
            )
    return scan_id


def latest_scan_results(limit: int = 100) -> list[dict[str, object]]:
    init_db()
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT payload_json FROM scan_results
            WHERE scan_id = (SELECT scan_id FROM scan_results ORDER BY id DESC LIMIT 1)
            ORDER BY score DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [json.loads(str(row_value(row, "payload_json"))) for row in rows]


def latest_trade_card() -> dict[str, object] | None:
    init_db()
    with get_connection() as connection:
        row = connection.execute("SELECT payload_json FROM trade_cards ORDER BY id DESC LIMIT 1").fetchone()
    return json.loads(str(row_value(row, "payload_json"))) if row else None


def add_journal_entry(entry: Mapping[str, object]) -> None:
    init_db()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO journal_entries (
                trade_date, ticker, phase, score, catalyst, entry, stop, target_1, target_2,
                exit, pnl, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.get("trade_date"),
                str(entry.get("ticker", "")).upper(),
                entry.get("phase"),
                entry.get("score"),
                entry.get("catalyst"),
                entry.get("entry"),
                entry.get("stop"),
                entry.get("target_1"),
                entry.get("target_2"),
                entry.get("exit"),
                entry.get("pnl"),
                entry.get("notes"),
                utc_now(),
            ),
        )


def list_journal_entries() -> list[dict[str, object]]:
    init_db()
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM journal_entries ORDER BY trade_date DESC, id DESC").fetchall()
    return [row_to_dict(row) for row in rows]


def save_settings_version(payload: Mapping[str, object]) -> None:
    init_db()
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO settings_versions (created_at, payload_json) VALUES (?, ?)",
            (utc_now(), json.dumps(dict(payload))),
        )


def create_mock_trade(trade: Mapping[str, object]) -> int:
    init_db()
    now = utc_now()
    settings_payload = trade.get("settings_snapshot", trade.get("settings_json", {}))
    settings_json = settings_payload if isinstance(settings_payload, str) else json.dumps(dict(settings_payload or {}))
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO mock_trades (
                created_at, entered_at, updated_at, ticker, status, phase, score, card_json,
                dollar_amount, entry, stop, current_stop, target_1, target_2, target_1_pct,
                target_2_pct, max_hold_minutes, move_stop_to_breakeven, shares,
                remaining_shares, risk_per_share, entry_notional, last_price, realized_pnl,
                closed_at, exit_reason, settings_json, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                trade.get("entered_at") or now,
                now,
                str(trade.get("ticker", "")).upper(),
                trade.get("status", "open"),
                trade.get("phase"),
                trade.get("score"),
                json.dumps(dict(trade.get("card", {}))),
                trade.get("dollar_amount"),
                trade.get("entry"),
                trade.get("stop"),
                trade.get("current_stop", trade.get("stop")),
                trade.get("target_1"),
                trade.get("target_2"),
                trade.get("target_1_pct"),
                trade.get("target_2_pct"),
                trade.get("max_hold_minutes"),
                1 if trade.get("move_stop_to_breakeven", True) else 0,
                trade.get("shares"),
                trade.get("remaining_shares", trade.get("shares")),
                trade.get("risk_per_share"),
                trade.get("entry_notional"),
                trade.get("last_price", trade.get("entry")),
                trade.get("realized_pnl", 0),
                trade.get("closed_at"),
                trade.get("exit_reason"),
                settings_json,
                trade.get("notes", ""),
            ),
        )
        trade_id = getattr(cursor, "lastrowid", None)
        if trade_id is None:
            row = connection.execute("SELECT last_insert_rowid()").fetchone()
            trade_id = int(row_value(row, "last_insert_rowid()", 0))
    save_portfolio_snapshot()
    return int(trade_id)


def list_mock_trades(status: str | None = None) -> list[dict[str, object]]:
    init_db()
    sql = "SELECT * FROM mock_trades"
    params: tuple[object, ...] = ()
    if status:
        sql += " WHERE status = ?"
        params = (status,)
    sql += " ORDER BY entered_at DESC, id DESC"
    with get_connection() as connection:
        rows = connection.execute(sql, params).fetchall()
    return [row_to_dict(row) for row in rows]


def get_mock_trade(trade_id: int) -> dict[str, object] | None:
    init_db()
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM mock_trades WHERE id = ?", (trade_id,)).fetchone()
    return row_to_dict(row) if row else None


def list_mock_fills(trade_id: int | None = None) -> list[dict[str, object]]:
    init_db()
    sql = "SELECT * FROM mock_fills"
    params: tuple[object, ...] = ()
    if trade_id is not None:
        sql += " WHERE trade_id = ?"
        params = (trade_id,)
    sql += " ORDER BY fill_time ASC, id ASC"
    with get_connection() as connection:
        rows = connection.execute(sql, params).fetchall()
    return [row_to_dict(row) for row in rows]


def add_mock_fill(fill: Mapping[str, object]) -> None:
    init_db()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO mock_fills (
                trade_id, created_at, fill_time, fill_type, shares, price, pnl, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fill.get("trade_id"),
                utc_now(),
                fill.get("fill_time"),
                fill.get("fill_type"),
                fill.get("shares"),
                fill.get("price"),
                fill.get("pnl"),
                json.dumps(dict(fill.get("payload", {}))),
            ),
        )


def update_mock_trade(trade_id: int, updates: Mapping[str, object]) -> None:
    if not updates:
        return
    init_db()
    allowed = {
        "updated_at",
        "status",
        "current_stop",
        "remaining_shares",
        "last_price",
        "realized_pnl",
        "closed_at",
        "exit_reason",
        "notes",
    }
    assignments = []
    values: list[object] = []
    payload = dict(updates)
    payload.setdefault("updated_at", utc_now())
    for key, value in payload.items():
        if key in allowed:
            assignments.append(f"{key} = ?")
            values.append(value)
    if not assignments:
        return
    values.append(trade_id)
    with get_connection() as connection:
        connection.execute(f"UPDATE mock_trades SET {', '.join(assignments)} WHERE id = ?", tuple(values))


def portfolio_state(starting_cash: float = 10_000.0) -> dict[str, float]:
    trades = list_mock_trades()
    fills = list_mock_fills()
    proceeds = sum(float(fill.get("price", 0)) * int(fill.get("shares", 0)) for fill in fills)
    entry_cost = sum(float(trade.get("entry", 0)) * int(trade.get("shares", 0)) for trade in trades)
    cash = starting_cash - entry_cost + proceeds
    open_exposure = sum(
        float(trade.get("last_price", trade.get("entry", 0))) * int(trade.get("remaining_shares", 0))
        for trade in trades
        if trade.get("status") == "open"
    )
    realized_pnl = sum(float(trade.get("realized_pnl", 0)) for trade in trades)
    unrealized_pnl = sum(
        (float(trade.get("last_price", trade.get("entry", 0))) - float(trade.get("entry", 0)))
        * int(trade.get("remaining_shares", 0))
        for trade in trades
        if trade.get("status") == "open"
    )
    equity = cash + open_exposure
    return {
        "cash": round(cash, 2),
        "open_exposure": round(open_exposure, 2),
        "realized_pnl": round(realized_pnl, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "equity": round(equity, 2),
    }


def save_portfolio_snapshot(starting_cash: float = 10_000.0) -> None:
    init_db()
    state = portfolio_state(starting_cash)
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO portfolio_snapshots (
                created_at, cash, open_exposure, realized_pnl, unrealized_pnl, equity, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                utc_now(),
                state["cash"],
                state["open_exposure"],
                state["realized_pnl"],
                state["unrealized_pnl"],
                state["equity"],
                json.dumps(state),
            ),
        )


def list_portfolio_snapshots() -> list[dict[str, object]]:
    init_db()
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM portfolio_snapshots ORDER BY created_at ASC, id ASC").fetchall()
    return [row_to_dict(row) for row in rows]
