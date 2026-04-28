from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Sequence

from src.config import DB_PATH, get_settings


_LAST_DB_WARNING: str | None = None


SCHEMA = """
CREATE TABLE IF NOT EXISTS universe_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS universe_cache (
    cache_key TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    score REAL NOT NULL,
    phase TEXT NOT NULL,
    verdict TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shortlist_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    rank INTEGER NOT NULL,
    score REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    score REAL NOT NULL,
    message TEXT NOT NULL,
    sent INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS trade_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    verdict TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    phase TEXT,
    score REAL,
    catalyst TEXT,
    entry REAL,
    stop REAL,
    target_1 REAL,
    target_2 REAL,
    exit REAL,
    pnl REAL,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mock_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    entered_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    ticker TEXT NOT NULL,
    status TEXT NOT NULL,
    phase TEXT,
    score REAL,
    card_json TEXT NOT NULL,
    dollar_amount REAL NOT NULL,
    entry REAL NOT NULL,
    stop REAL NOT NULL,
    current_stop REAL NOT NULL,
    target_1 REAL NOT NULL,
    target_2 REAL NOT NULL,
    target_1_pct REAL NOT NULL,
    target_2_pct REAL NOT NULL,
    max_hold_minutes INTEGER NOT NULL,
    move_stop_to_breakeven INTEGER NOT NULL DEFAULT 1,
    shares REAL NOT NULL,
    remaining_shares REAL NOT NULL,
    risk_per_share REAL NOT NULL,
    entry_notional REAL NOT NULL,
    last_price REAL NOT NULL,
    realized_pnl REAL NOT NULL DEFAULT 0,
    closed_at TEXT,
    exit_reason TEXT,
    settings_json TEXT NOT NULL DEFAULT '{}',
    notes TEXT
);

CREATE TABLE IF NOT EXISTS mock_fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    fill_time TEXT NOT NULL,
    fill_type TEXT NOT NULL,
    shares REAL NOT NULL,
    price REAL NOT NULL,
    pnl REAL NOT NULL,
    payload_json TEXT NOT NULL,
    FOREIGN KEY (trade_id) REFERENCES mock_trades(id)
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    cash REAL NOT NULL,
    open_exposure REAL NOT NULL,
    realized_pnl REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    equity REAL NOT NULL,
    payload_json TEXT NOT NULL
);
"""


class DatabaseConnection:
    def __init__(self, path: Path | str | None = None) -> None:
        settings = get_settings()
        self.path = Path(path or settings.db_path)
        self.uses_turso = bool(settings.turso_database_url and settings.turso_auth_token)
        if self.uses_turso:
            try:
                import libsql_client

                self._connection = libsql_client.create_client_sync(
                    settings.turso_database_url,
                    auth_token=settings.turso_auth_token,
                )
            except Exception as exc:
                self._fallback_to_sqlite(exc)
        else:
            self._connect_sqlite()

    def __enter__(self) -> "DatabaseConnection":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()

    def execute(self, sql: str, params: Sequence[object] = ()) -> object:
        try:
            result = self._connection.execute(sql, params)
        except Exception as exc:
            if self.uses_turso:
                self._fallback_to_sqlite(exc)
                result = self._connection.execute(sql, params)
            else:
                raise
        return LibsqlResult(result) if self.uses_turso else result

    def executemany(self, sql: str, rows: Iterable[Sequence[object]]) -> None:
        if self.uses_turso:
            for row in rows:
                self.execute(sql, row)
            return
        if hasattr(self._connection, "executemany"):
            self._connection.executemany(sql, list(rows))
            return
        for row in rows:
            self._connection.execute(sql, row)

    def executescript(self, script: str) -> None:
        if hasattr(self._connection, "executescript"):
            self._connection.executescript(script)
            return
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                self.execute(statement)

    def commit(self) -> None:
        if self.uses_turso:
            return
        self._connection.commit()

    def rollback(self) -> None:
        if not self.uses_turso and hasattr(self._connection, "rollback"):
            self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def _connect_sqlite(self) -> None:
        self.uses_turso = False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row

    def _fallback_to_sqlite(self, exc: Exception) -> None:
        global _LAST_DB_WARNING
        _LAST_DB_WARNING = f"Turso unavailable; using local SQLite fallback. {type(exc).__name__}: {exc}"
        try:
            self._connection.close()
        except Exception:
            pass
        self._connect_sqlite()


def get_connection(path: Path | str | None = None) -> DatabaseConnection:
    return DatabaseConnection(path)


def storage_warning() -> str | None:
    return _LAST_DB_WARNING


class LibsqlResult:
    def __init__(self, result: object) -> None:
        self._result = result
        self.lastrowid = getattr(result, "last_insert_rowid", None)

    def fetchone(self) -> object | None:
        rows = self.fetchall()
        return rows[0] if rows else None

    def fetchall(self) -> list[object]:
        rows = getattr(self._result, "rows", [])
        return list(rows)


def init_db(path: Path | str | None = None) -> None:
    with get_connection(path) as connection:
        connection.executescript(SCHEMA)
        _run_migrations(connection)


def _run_migrations(connection: DatabaseConnection) -> None:
    columns = _table_columns(connection, "mock_trades")
    if columns and "settings_json" not in columns:
        connection.execute("ALTER TABLE mock_trades ADD COLUMN settings_json TEXT NOT NULL DEFAULT '{}'")


def _table_columns(connection: DatabaseConnection, table: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    columns: set[str] = set()
    for row in rows:
        try:
            columns.add(str(row["name"]))  # type: ignore[index]
        except (KeyError, TypeError, IndexError):
            columns.add(str(row[1]))  # type: ignore[index]
    return columns
