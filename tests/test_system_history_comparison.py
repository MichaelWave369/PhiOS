from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

from phios.memory import (
    MemoryOperatorRuntime,
    MemoryRuntimeConfig,
    SystemHistoryComparisonService,
    SystemHistoryPersistenceBridge,
    create_history_projection_server,
)

COMPONENT_IDS = ("host", "services", "processes", "packages", "devices")
SUMMARY_METRICS = (
    "cpuLogicalCores",
    "memoryTotalBytes",
    "rootStorageTotalBytes",
    "observedServiceCount",
    "activeServiceCount",
    "currentUserProcessCount",
    "installedPackageCount",
    "blockDeviceCount",
    "networkDeviceCount",
    "pciDeviceCount",
    "usbDeviceCount",
    "drmDeviceCount",
    "powerDeviceCount",
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


COMPONENT_CONTRACTS = {
    "host": ("phios.host-observation.v1", "linux-readonly-node-probe"),
    "services": ("phios.service-observation.v1", "systemd-dbus-list-units"),
    "processes": ("phios.process-observation.v1", "procfs-current-user"),
    "packages": ("phios.package-observation.v1", "dpkg-status-file"),
    "devices": ("phios.device-observation.v1", "linux-sysfs-bounded"),
}


def _component(component_id: str, digest_char: str, *, available: bool = True) -> dict[str, object]:
    schema_version, source = COMPONENT_CONTRACTS[component_id]
    return {
        "id": component_id,
        "schemaVersion": schema_version,
        "source": source,
        "capturedAt": "2026-09-23T04:00:00+00:00",
        "availability": "available" if available else "unavailable",
        "digest": "sha256:" + digest_char * 64,
        "readOnly": True,
        "executionAuthority": False,
        "effectPerformed": False,
    }


def _state(
    composed_at: str,
    *,
    digest_char: str,
    cpu: int,
    process_count: int,
    coherence: str = "coherent",
) -> dict[str, object]:
    summary: dict[str, object] = {
        "cpuLogicalCores": cpu,
        "memoryTotalBytes": 64 * 1024**3,
        "rootStorageTotalBytes": 2 * 1024**4,
        "observedServiceCount": 4,
        "activeServiceCount": 3,
        "currentUserProcessCount": process_count,
        "installedPackageCount": 900,
        "blockDeviceCount": 2,
        "networkDeviceCount": 3,
        "pciDeviceCount": 12,
        "usbDeviceCount": 5,
        "drmDeviceCount": 2,
        "powerDeviceCount": 1,
    }
    value: dict[str, object] = {
        "schemaVersion": "phios.system-state.v1",
        "source": "phios-system-state-composer",
        "composedAt": composed_at,
        "captureWindowStart": composed_at,
        "captureWindowEnd": composed_at,
        "captureSkewMs": 0,
        "maxCoherentSkewMs": 5000,
        "coherence": coherence,
        "componentCount": len(COMPONENT_IDS),
        "availableComponentCount": len(COMPONENT_IDS),
        "readOnly": True,
        "executionAuthority": False,
        "effectPerformed": False,
        "components": [
            _component(component_id, digest_char)
            for component_id in COMPONENT_IDS
        ],
        "summary": summary,
        "composeDurationMs": 1,
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
        "history.compare",
    ),
) -> MemoryOperatorRuntime:
    config = MemoryRuntimeConfig(
        enabled=True,
        principal_id="system-history-comparator",
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


def _seed(runtime: MemoryOperatorRuntime) -> tuple[str, str, str]:
    previous = _state(
        "2026-09-23T04:00:00+00:00",
        digest_char="a",
        cpu=8,
        process_count=100,
    )
    current = _state(
        "2026-09-23T04:05:00+00:00",
        digest_char="b",
        cpu=12,
        process_count=124,
        coherence="degraded",
    )
    change = _change(previous, current, "2026-09-23T04:05:01+00:00")
    persisted = SystemHistoryPersistenceBridge(runtime).persist_transition(
        previous_state=previous,
        current_state=current,
        change_receipt=change,
        task_id="seed-system-history-comparison",
    )
    return (
        persisted.state_record_ids[0],
        persisted.state_record_ids[1],
        persisted.change_record_id,
    )


def test_comparison_derives_bounded_nonpersistent_differences(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path / "memory")
    previous_id, current_id, _change_id = _seed(runtime)
    ledger_before = runtime.ledger.path.read_text(encoding="utf-8").splitlines()

    comparison = SystemHistoryComparisonService(runtime).compare(
        from_record_id=previous_id,
        to_record_id=current_id,
    ).to_dict()

    assert comparison["schemaVersion"] == "phios.system-history-comparison.v0.13"
    assert comparison["persistent"] is False
    assert comparison["consecutiveClaimed"] is False
    assert comparison["causeAssigned"] is False
    assert comparison["severityAssigned"] is False
    assert comparison["operationalAuthority"] is False
    assert comparison["actionAuthority"] is False
    assert comparison["executionAuthority"] is False
    assert comparison["effectPerformed"] is False
    assert comparison["chronologicalOrder"] == "forward"
    assert comparison["timeDeltaMs"] == 300000
    assert comparison["changedComponentCount"] == 5
    assert comparison["changedSummaryMetricCount"] == 2
    assert comparison["coherence"] == {
        "from": "coherent",
        "to": "degraded",
        "changed": True,
    }
    assert len(str(comparison["fromReadAdmissibilityReceiptSha256"])) == 64
    assert len(str(comparison["toReadAdmissibilityReceiptSha256"])) == 64
    assert str(comparison["comparisonDigest"]).startswith("sha256:")

    summary_changes = comparison["summaryChanges"]
    assert isinstance(summary_changes, list)
    assert [row["metric"] for row in summary_changes] == [
        "cpuLogicalCores",
        "currentUserProcessCount",
    ]
    assert summary_changes[0]["delta"] == 4
    assert summary_changes[1]["delta"] == 24

    ledger_after = runtime.ledger.path.read_text(encoding="utf-8").splitlines()
    assert ledger_after == ledger_before


def test_comparison_requires_explicit_compare_read_and_memory_grants(tmp_path: Path) -> None:
    no_compare = _runtime(
        tmp_path / "no-compare",
        permissions=("history.persist", "memory.write", "history.read", "memory.read"),
    )
    previous_id, current_id, _ = _seed(no_compare)
    with pytest.raises(PermissionError, match="history.compare"):
        SystemHistoryComparisonService(no_compare).compare(
            from_record_id=previous_id,
            to_record_id=current_id,
        )

    no_history_read = _runtime(
        tmp_path / "no-history-read",
        permissions=("history.persist", "memory.write", "memory.read", "history.compare"),
    )
    previous_id, current_id, _ = _seed(no_history_read)
    with pytest.raises(PermissionError, match="history.read"):
        SystemHistoryComparisonService(no_history_read).compare(
            from_record_id=previous_id,
            to_record_id=current_id,
        )

    no_memory_read = _runtime(
        tmp_path / "no-memory-read",
        permissions=("history.persist", "memory.write", "history.read", "history.compare"),
    )
    previous_id, current_id, _ = _seed(no_memory_read)
    with pytest.raises(PermissionError, match="memory.read"):
        SystemHistoryComparisonService(no_memory_read).compare(
            from_record_id=previous_id,
            to_record_id=current_id,
        )


def test_comparison_accepts_only_two_distinct_canonical_state_records(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path / "memory")
    previous_id, current_id, change_id = _seed(runtime)
    service = SystemHistoryComparisonService(runtime)

    with pytest.raises(ValueError, match="two distinct"):
        service.compare(from_record_id=previous_id, to_record_id=previous_id)

    with pytest.raises(ValueError, match="system-state records"):
        service.compare(from_record_id=previous_id, to_record_id=change_id)

    comparison = service.compare(
        from_record_id=current_id,
        to_record_id=previous_id,
    ).to_dict()
    assert comparison["chronologicalOrder"] == "reverse"
    assert comparison["timeDeltaMs"] == -300000


def test_comparison_sidecar_route_is_get_only_and_no_cors(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path / "memory")
    previous_id, current_id, _ = _seed(runtime)
    server = create_history_projection_server(runtime, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address
        assert host == "127.0.0.1"
        query = urlencode({"from": previous_id, "to": current_id})
        url = f"http://127.0.0.1:{port}/api/v1/system-history-compare?{query}"
        with urlopen(url, timeout=2) as response:
            assert response.status == 200
            assert response.headers.get("Access-Control-Allow-Origin") is None
            payload = json.loads(response.read().decode("utf-8"))

        assert (
            payload["transportSchemaVersion"]
            == "phios.system-history-comparison-transport.v0.13"
        )
        assert payload["transportIdentity"] == "phios-governed-history-reader"
        assert payload["localOnly"] is True
        assert payload["readOnly"] is True
        assert payload["executionAuthority"] is False
        assert payload["effectPerformed"] is False
        assert payload["comparison"]["persistent"] is False
        assert payload["comparison"]["consecutiveClaimed"] is False

        request = Request(url, method="POST", data=b"{}")
        with pytest.raises(HTTPError) as exc_info:
            urlopen(request, timeout=2)
        assert exc_info.value.code == 405
        assert exc_info.value.headers.get("Allow") == "GET"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_sidecar_can_project_history_without_compare_grant_but_compare_is_forbidden(
    tmp_path: Path,
) -> None:
    runtime = _runtime(
        tmp_path / "memory",
        permissions=("history.persist", "memory.write", "history.read", "memory.read"),
    )
    previous_id, current_id, _ = _seed(runtime)
    server = create_history_projection_server(runtime, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        _host, port = server.server_address
        with urlopen(
            f"http://127.0.0.1:{port}/api/v1/system-history?limit=16",
            timeout=2,
        ) as response:
            assert response.status == 200

        query = urlencode({"from": previous_id, "to": current_id})
        with pytest.raises(HTTPError) as exc_info:
            urlopen(
                f"http://127.0.0.1:{port}/api/v1/system-history-compare?{query}",
                timeout=2,
            )
        assert exc_info.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
