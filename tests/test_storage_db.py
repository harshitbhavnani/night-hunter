from __future__ import annotations

import pytest

from src.storage.db import TursoHttpResult, _extract_turso_result, _http_arg, _http_base_url


def test_turso_http_base_url_normalizes_libsql_and_websocket_urls() -> None:
    assert _http_base_url("libsql://night-hunter-example.turso.io") == "https://night-hunter-example.turso.io"
    assert _http_base_url("wss://night-hunter-example.turso.io/") == "https://night-hunter-example.turso.io"
    assert _http_base_url("https://night-hunter-example.turso.io") == "https://night-hunter-example.turso.io"


def test_turso_http_base_url_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        _http_base_url("night-hunter-example.turso.io")


def test_turso_http_arg_encodes_supported_sql_values() -> None:
    assert _http_arg(None) == {"type": "null"}
    assert _http_arg(True) == {"type": "integer", "value": "1"}
    assert _http_arg(7) == {"type": "integer", "value": "7"}
    assert _http_arg(1.25) == {"type": "float", "value": 1.25}
    assert _http_arg("BTC/USD") == {"type": "text", "value": "BTC/USD"}
    assert _http_arg(b"nh") == {"type": "blob", "base64": "bmg="}


def test_turso_http_result_parses_pipeline_response_rows() -> None:
    payload = {
        "baton": None,
        "base_url": None,
        "results": [
            {
                "type": "ok",
                "response": {
                    "type": "execute",
                    "result": {
                        "cols": [{"name": "id"}, {"name": "ticker"}, {"name": "score"}],
                        "rows": [
                            [
                                {"type": "integer", "value": "1"},
                                {"type": "text", "value": "BTC/USD"},
                                {"type": "float", "value": "8.75"},
                            ]
                        ],
                        "affected_row_count": 0,
                        "last_insert_rowid": "42",
                    },
                },
            },
            {"type": "ok", "response": {"type": "close"}},
        ],
    }

    result = TursoHttpResult(_extract_turso_result(payload))
    row = result.fetchone()

    assert result.lastrowid == 42
    assert row is not None
    assert row["id"] == 1
    assert row[1] == "BTC/USD"
    assert dict(row)["score"] == 8.75


def test_turso_http_result_raises_on_error_response() -> None:
    payload = {"results": [{"type": "error", "error": {"message": "bad sql"}}]}

    with pytest.raises(RuntimeError, match="Turso SQL error"):
        _extract_turso_result(payload)
