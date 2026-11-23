"""R4b HTTP tests: local-only, authenticated, bounded and durable receipts."""
from __future__ import annotations

import http.client
import json
import sqlite3
import threading
from pathlib import Path

import pytest

from phios.memory.agentora_writeback import PROTOCOL, operation_id
from phios.memory.agentora_writeback_server import (
    MAX_REQUEST_BYTES, create_agentora_writeback_server,
)
from phios.memory.config import MemoryRuntimeConfig
from phios.memory.operator import MemoryOperatorRuntime

KEY = "local-only-0123456789abcdef0123456789abcdef"
WHEN = "2026-11-21T19:00:00+00:00"
ROUTE = "/api/v1/agentora/writeback"


def _runtime(root: Path, *, enabled=True, grants=("memory.write", "memory.read")):
    return MemoryOperatorRuntime(
        state_root=root / "memory",
        config=MemoryRuntimeConfig.from_mapping({"enabled": enabled}),
        allowed_permissions=grants,
    )


def _payload():
    return {
        "session_id": "session-1",
        "task_id": "job-123",
        "raw_payload": {"outcome": {
            "job_id": "job-123", "status": "completed", "summary": "Done",
        }},
    }


def _envelope():
    payload = _payload()
    return {
        "protocol_version": PROTOCOL,
        "operation_id": operation_id(payload),
        "created_at_utc": WHEN,
        "payload": payload,
    }


def _send(server, method, path, *, body=None, key=KEY, content_type="application/json"):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=4)
    headers = {"Content-Type": content_type}
    if key is not None:
        headers["X-API-Key"] = key
    if body is not None:
        headers["Content-Length"] = str(len(body))
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    status = response.status
    cache = response.getheader("Cache-Control")
    result = json.loads(response.read())
    connection.close()
    return status, result, cache


@pytest.fixture()
def bridge(tmp_path):
    runtime = _runtime(tmp_path)
    server = create_agentora_writeback_server(runtime, token=KEY, port=0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server, runtime
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=4)


def test_denied_by_default_even_with_secret(tmp_path):
    with pytest.raises(RuntimeError, match="disabled"):
        create_agentora_writeback_server(
            _runtime(tmp_path, enabled=False), token=KEY, port=0
        )
    with pytest.raises(PermissionError, match="memory.write"):
        create_agentora_writeback_server(
            _runtime(tmp_path, grants=("memory.read",)), token=KEY, port=0
        )
    with pytest.raises(ValueError, match="secret"):
        create_agentora_writeback_server(_runtime(tmp_path), token="", port=0)
    with pytest.raises(ValueError, match="port"):
        create_agentora_writeback_server(_runtime(tmp_path), token=KEY, port=80)
    server = create_agentora_writeback_server(_runtime(tmp_path), token=KEY, port=0)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()


def test_missing_and_wrong_token_do_not_store(bridge):
    server, runtime = bridge
    encoded = json.dumps(_envelope()).encode("utf-8")
    for token in (None, "incorrect"):
        code, result, cache = _send(server, "POST", ROUTE, body=encoded, key=token)
        assert code == 401 and result["error_code"] == "UNAUTHENTICATED"
        assert cache == "no-store"
    with sqlite3.connect(runtime.store.path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 0


def test_published_receipt_and_replay_survive_http_boundary(bridge):
    server, runtime = bridge
    encoded = json.dumps(_envelope()).encode("utf-8")
    code, first, _ = _send(server, "POST", ROUTE, body=encoded)
    assert code == 200 and first["ok"] and first["state"] == "published"
    assert first["replayed"] is False
    assert first["operation_id"] == operation_id(_payload())
    code, replay, _ = _send(server, "POST", ROUTE, body=encoded)
    assert code == 200 and replay["replayed"] is True
    assert replay["receipt_id"] == first["receipt_id"]
    code, receipt, _ = _send(server, "GET", ROUTE + "/" + first["operation_id"])
    assert code == 200 and receipt["state"] == "published"
    assert "Done" not in json.dumps(receipt)
    assert "payload" not in receipt
    with sqlite3.connect(runtime.store.path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 1


def test_mismatch_unknown_status_and_bad_payloads(bridge):
    server, _ = bridge
    bad_op = _envelope()
    bad_op["operation_id"] = "f" * 64
    code, data, _ = _send(server, "POST", ROUTE, body=json.dumps(bad_op).encode())
    assert code == 400 and data["error_code"] == "INVALID_REQUEST"
    code, data, _ = _send(server, "GET", ROUTE + "/" + "f" * 64)
    assert code == 404 and data["state"] == "not_found"
    for invalid in (b'{"x":1,"x":2}', b'{"bad":NaN}', b"oops"):
        code, data, _ = _send(server, "POST", ROUTE, body=invalid)
        assert code == 400 and not data["ok"]


def test_reject_large_and_unsupported_requests(bridge):
    server, _ = bridge
    code, data, _ = _send(server, "POST", ROUTE, body=b"x" * (MAX_REQUEST_BYTES + 1))
    assert code == 413 and data["error_code"] == "REQUEST_TOO_LARGE"
    code, data, _ = _send(server, "POST", ROUTE, body=b"{}", content_type="text/plain")
    assert code == 415 and data["error_code"] == "JSON_REQUIRED"
    code, data, _ = _send(server, "PUT", ROUTE, body=b"{}")
    assert code == 405 and data["error_code"] == "METHOD_NOT_ALLOWED"
    code, _, _ = _send(server, "GET", ROUTE + "/" + "a" * 64 + "?debug=1")
    assert code == 404
