from __future__ import annotations

import base64
import sqlite3
from collections.abc import Mapping as MappingABC
from pathlib import Path
from typing import Iterable, Sequence

import requests

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
                self._connection = TursoHttpConnection(
                    settings.turso_database_url,
                    settings.turso_auth_token,
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
        return result

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


class TursoHttpConnection:
    def __init__(self, database_url: str, auth_token: str) -> None:
        self.base_url = _http_base_url(database_url)
        self.auth_token = auth_token
        self._session = requests.Session()

    def execute(self, sql: str, params: Sequence[object] = ()) -> "TursoHttpResult":
        statement: dict[str, object] = {"sql": sql}
        if params:
            statement["args"] = [_http_arg(value) for value in params]
        response = self._session.post(
            f"{self.base_url}/v2/pipeline",
            headers={
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json",
            },
            json={
                "requests": [
                    {"type": "execute", "stmt": statement},
                    {"type": "close"},
                ]
            },
            timeout=20,
        )
        if response.status_code >= 400:
            detail = response.text.strip()
            if len(detail) > 500:
                detail = f"{detail[:500]}..."
            raise RuntimeError(f"Turso HTTP {response.status_code}: {detail or response.reason}")
        payload = response.json()
        result = _extract_turso_result(payload)
        return TursoHttpResult(result)

    def close(self) -> None:
        self._session.close()


class TursoHttpResult:
    def __init__(self, result: object) -> None:
        result = result if isinstance(result, dict) else {}
        self.columns = _column_names(result.get("cols") or result.get("columns") or [])
        self.rows = _http_rows(result.get("rows") or [], self.columns)
        self.lastrowid = _optional_int(result.get("last_insert_rowid") or result.get("lastInsertRowid"))

    def fetchone(self) -> "TursoHttpRow | None":
        rows = self.fetchall()
        return rows[0] if rows else None

    def fetchall(self) -> list["TursoHttpRow"]:
        return list(self.rows)


class TursoHttpRow(MappingABC):
    def __init__(self, columns: Sequence[str], values: Sequence[object]) -> None:
        self._columns = list(columns)
        self._values = list(values)
        self._by_name = {name: self._values[index] for index, name in enumerate(self._columns)}

    def __getitem__(self, key: object) -> object:
        if isinstance(key, int):
            return self._values[key]
        return self._by_name[str(key)]

    def __iter__(self):
        return iter(self._columns)

    def __len__(self) -> int:
        return len(self._columns)

    def keys(self):
        return self._by_name.keys()


def _http_base_url(value: str) -> str:
    url = str(value or "").strip().rstrip("/")
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://") :]
    if url.startswith("wss://"):
        url = "https://" + url[len("wss://") :]
    if not url.startswith("https://"):
        raise ValueError("TURSO_DATABASE_URL must be a libsql:// or https:// URL.")
    return url


def _http_arg(value: object) -> dict[str, object]:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": "1" if value else "0"}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    if isinstance(value, bytes):
        return {"type": "blob", "base64": base64.b64encode(value).decode("ascii")}
    return {"type": "text", "value": str(value)}


def _extract_turso_result(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise RuntimeError("Turso returned a non-JSON response.")
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        raise RuntimeError("Turso response did not include SQL results.")
    for item in results:
        result = _find_statement_result(item)
        if result is not None:
            return result
    raise RuntimeError("Turso response did not include an execute result.")


def _find_statement_result(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    if "error" in value:
        raise RuntimeError(f"Turso SQL error: {value['error']}")
    if any(key in value for key in ("cols", "rows", "affected_row_count", "last_insert_rowid")):
        return value
    for key in ("ok", "response", "execute", "result"):
        nested = _find_statement_result(value.get(key))
        if nested is not None:
            return nested
    return None


def _column_names(columns: object) -> list[str]:
    names: list[str] = []
    if not isinstance(columns, list):
        return names
    for index, column in enumerate(columns):
        if isinstance(column, dict):
            names.append(str(column.get("name") or column.get("column") or column.get("displayName") or index))
        else:
            names.append(str(column))
    return names


def _http_rows(rows: object, columns: list[str]) -> list[TursoHttpRow]:
    parsed: list[TursoHttpRow] = []
    if not isinstance(rows, list):
        return parsed
    for row in rows:
        if isinstance(row, dict):
            row_columns = columns or list(row.keys())
            values = [_decode_http_value(row.get(column)) for column in row_columns]
        elif isinstance(row, list):
            row_columns = columns or [str(index) for index in range(len(row))]
            values = [_decode_http_value(value) for value in row]
        else:
            continue
        parsed.append(TursoHttpRow(row_columns, values))
    return parsed


def _decode_http_value(value: object) -> object:
    if not isinstance(value, dict):
        return value
    value_type = str(value.get("type") or "").lower()
    if value_type == "null":
        return None
    if value_type == "integer":
        return _optional_int(value.get("value"))
    if value_type == "float":
        try:
            return float(value.get("value"))
        except (TypeError, ValueError):
            return 0.0
    if value_type == "blob":
        raw = value.get("base64") or ""
        try:
            return base64.b64decode(str(raw))
        except Exception:
            return b""
    if "value" in value:
        return value.get("value")
    return value


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
