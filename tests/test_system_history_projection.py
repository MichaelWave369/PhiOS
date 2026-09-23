from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from phios.memory import (
    MemoryOperatorRuntime,
    MemoryRuntimeConfig,
    SystemHistoryPersistenceBridge,
    SystemHistoryProjectionService,
    create_history_projection_server,
)


def _body_digest(value: dict[str, object], field: str) -> str:
    body = dict(value)
    body.pop(field, None)
    encoded = json.dumps(
        body,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _state(composed_at: str) -> dict[str, object]:
    value: dict[str, object] = {
        "schemaVersion": "phios.system-state.v1",
        "source": "phios-system-state-composer",
        "composedAt": composed_at,
        "readOnly": True,
        "executionAuthority": False,
        "effectPerformed": False,
        "receiptDigest": "",
    }
    value["receiptDigest"] = _body_digest(value, "receiptDigest")
    return value


def _change(
    previous: dict[str, object],
    current: dict[str, object],
    recorded_at: str,
) -> dict[str, object]:
    value: dict[str, object] = {
        "schemaVersion": "phios.system-change.v1",
        "source": "phios-system-change-deriver",
        "recordedAt": recorded_at,
        "fromReceiptDigest": previous["receiptDigest"],
        "toReceiptDigest": current["receiptDigest"],
        "causeAssigned": False,
        "severityAssigned": False,
        "readOnly": True,
        "executionAuthority": False,
        "effectPerformed": False,
        "changeDigest": "",
    }
    value["changeDigest"] = _body_digest(value, "changeDigest")
    return value


def _runtime(
    root: Path,
    *,
    permissions: tuple[str, ...] = (
        "history.persist",
        "memory.write",
        "history.read",
        "memory.read",
    ),
) -> MemoryOperatorRuntime:
    config = MemoryRuntimeConfig(
        enabled=True,
        principal_id="system-history-reader",
        scopes=("system-history",),
        classifications=("system-observation",),
        retention_policy_id="retain-system-history",
        semantic_enabled=False,
    )
    return MemoryOperatorRuntime(
        state_root=root,
        config=config,
        allowed_permissions=permissions,
    )


def _seed(runtime: MemoryOperatorRuntime) -> None:
    previous = _state("2026-09-22T20:00:00+00:00")
    current = _state("2026-09-22T20:00:05+00:00")
    change = _change(previous, current, "2026-09-22T20:00:06+00:00")
    SystemHistoryPersistenceBridge(runtime).persist_transition(
        previous_state=previous,
        current_state=current,
        change_receipt=change,
        task_id="seed-system-history",
    )


def test_projection_returns_only_governed_read_admissible_records(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path / "memory")
    _seed(runtime)
    ledger_before = runtime.ledger.path.read_text(encoding="utf-8").splitlines()

    projection = SystemHistoryProjectionService(runtime).project(limit=16)

    assert projection.status == "ok"
    assert projection.persistent is True
    assert projection.read_only is True
    assert projection.execution_authority is False
    assert projection.effect_performed is False
    assert len(projection.records) == 3
    assert len(projection.read_admissibility_receipt_sha256s) == 3
    assert all(len(value) == 64 for value in projection.read_admissibility_receipt_sha256s)
    assert {record["kind"] for record in projection.records} == {"state", "change"}
    assert all(record["scopeId"] == "system-history" for record in projection.records)
    assert all(
        record["classification"] == "system-observation"
        for record in projection.records
    )

    change = next(record for record in projection.records if record["kind"] == "change")
    assert change["epistemicKind"] == "derived"
    assert change["exactnessClass"] == "REVERSIBLE"
    assert len(change["derivedFrom"]) == 2
    assert len(change["transformationLineageSha256s"]) == 1

    ledger_after = runtime.ledger.path.read_text(encoding="utf-8").splitlines()
    assert ledger_after == ledger_before


def test_projection_requires_history_read_and_memory_read(tmp_path: Path) -> None:
    write_only = _runtime(
        tmp_path / "memory-write-only",
        permissions=("history.persist", "memory.write", "memory.read"),
    )
    _seed(write_only)
    with pytest.raises(PermissionError, match="history.read"):
        SystemHistoryProjectionService(write_only).project()

    no_memory_read = _runtime(
        tmp_path / "memory-no-read",
        permissions=("history.persist", "memory.write", "history.read"),
    )
    _seed(no_memory_read)
    with pytest.raises(PermissionError, match="memory.read"):
        SystemHistoryProjectionService(no_memory_read).project()


def test_projection_limit_is_hard_bounded(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path / "memory")
    _seed(runtime)
    service = SystemHistoryProjectionService(runtime)

    with pytest.raises(ValueError, match="between 1 and 16"):
        service.project(limit=17)
    with pytest.raises(ValueError, match="between 1 and 16"):
        service.project(limit=0)


def test_loopback_sidecar_is_get_only_and_emits_no_cors(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path / "memory")
    _seed(runtime)
    server = create_history_projection_server(runtime, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address
        assert host == "127.0.0.1"

        with urlopen(
            f"http://127.0.0.1:{port}/api/v1/system-history?limit=16",
            timeout=2,
        ) as response:
            assert response.status == 200
            assert response.headers.get("Access-Control-Allow-Origin") is None
            payload = json.loads(response.read().decode("utf-8"))

        assert payload["transportSchemaVersion"] == "phios.system-history-transport.v0.12"
        assert payload["transportIdentity"] == "phios-governed-history-reader"
        assert payload["localOnly"] is True
        assert payload["readOnly"] is True
        assert payload["executionAuthority"] is False
        assert payload["effectPerformed"] is False
        assert payload["projection"]["count"] == 3

        request = Request(
            f"http://127.0.0.1:{port}/api/v1/system-history",
            method="POST",
            data=b"{}",
        )
        with pytest.raises(HTTPError) as exc_info:
            urlopen(request, timeout=2)
        assert exc_info.value.code == 405
        assert exc_info.value.headers.get("Allow") == "GET"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_sidecar_fails_closed_without_read_grants(tmp_path: Path) -> None:
    runtime = _runtime(
        tmp_path / "memory",
        permissions=("history.persist", "memory.write", "memory.read"),
    )
    _seed(runtime)

    with pytest.raises(PermissionError, match="history.read"):
        create_history_projection_server(runtime, port=0)
