"""R4a cross-service operation identity and governed canonical replay."""
from __future__ import annotations

import copy
import sqlite3

import pytest

from phios.memory.agentora_writeback import (
    AgentoraWritebackAdmission, canonical_envelope, operation_id,
)
from phios.memory.config import MemoryRuntimeConfig
from phios.memory.operator import MemoryOperatorRuntime


def _payload():
    return {
        "session_id": "session-1", "task_id": "job-123",
        "raw_payload": {"outcome": {
            "job_id": "job-123", "status": "completed", "summary": "Done",
        }},
    }


def _runtime(tmp_path, *, enabled=True, authorities=("memory.write", "memory.read")):
    config = MemoryRuntimeConfig.from_mapping({"enabled": enabled})
    return MemoryOperatorRuntime(
        state_root=tmp_path / "memory",
        config=config,
        allowed_permissions=authorities,
    )


def _counts(path):
    with sqlite3.connect(path) as db:
        return (
            db.execute("SELECT COUNT(*) FROM records").fetchone()[0],
            db.execute("SELECT COUNT(*) FROM receipt_outbox").fetchone()[0],
        )


def test_shared_protocol_fixed_identity():
    assert operation_id(_payload()) == (
        "056f70f4e94787b3aa2f96e82fd93bd173f1b92582deaec4c2f12e698431ba06"
    )
    modified = copy.deepcopy(_payload())
    modified["operator_notes"] = "separate presentation"
    assert operation_id(modified) == operation_id(_payload())
    modified["raw_payload"]["outcome"]["summary"] = "Changed"
    assert operation_id(modified) != operation_id(_payload())


def test_replay_survives_restart_with_one_canonical_record(tmp_path):
    runtime = _runtime(tmp_path)
    bridge = AgentoraWritebackAdmission(runtime)
    when = "2026-11-21T19:00:00+00:00"
    first = bridge.admit(_payload(), created_at_utc=when)
    assert first["ok"] and first["state"] == "published" and not first["replayed"]
    assert bridge.status(first["operation_id"])["state"] == "published"
    restarted = AgentoraWritebackAdmission(_runtime(tmp_path))
    repeat = restarted.admit(_payload(), created_at_utc=when)
    assert repeat["ok"] and repeat["replayed"]
    assert repeat["receipt_id"] == first["receipt_id"]
    assert _counts(runtime.store.path) == (1, 1)


def test_same_operation_changed_payload_conflicts_not_overwrites(tmp_path):
    bridge = AgentoraWritebackAdmission(_runtime(tmp_path))
    when = "2026-11-21T19:00:00+00:00"
    bridge.admit(_payload(), created_at_utc=when)
    altered = copy.deepcopy(_payload())
    altered["operator_notes"] = "changed"
    with pytest.raises(ValueError, match="different request"):
        bridge.admit(altered, created_at_utc=when)
    assert _counts(bridge.runtime.store.path) == (1, 1)


def test_changed_outcome_gets_separate_operation(tmp_path):
    bridge = AgentoraWritebackAdmission(_runtime(tmp_path))
    when = "2026-11-21T19:00:00+00:00"
    first = bridge.admit(_payload(), created_at_utc=when)
    altered = copy.deepcopy(_payload())
    altered["raw_payload"]["outcome"]["status"] = "failed"
    second = bridge.admit(altered, created_at_utc=when)
    assert first["operation_id"] != second["operation_id"]
    assert _counts(bridge.runtime.store.path) == (2, 2)


def test_disabled_or_no_write_authority_fails_closed(tmp_path):
    disabled = AgentoraWritebackAdmission(_runtime(tmp_path / "disabled", enabled=False))
    with pytest.raises(RuntimeError, match="disabled"):
        disabled.admit(_payload(), created_at_utc="2026-11-21T19:00:00+00:00")
    readonly = AgentoraWritebackAdmission(
        _runtime(tmp_path / "readonly", authorities=("memory.read",))
    )
    with pytest.raises(PermissionError, match="memory.write"):
        readonly.admit(_payload(), created_at_utc="2026-11-21T19:00:00+00:00")


def test_read_status_requires_read_authority(tmp_path):
    writer = AgentoraWritebackAdmission(
        _runtime(tmp_path, authorities=("memory.write",))
    )
    with pytest.raises(PermissionError, match="memory.read"):
        writer.status(operation_id(_payload()))


@pytest.mark.parametrize("bad", [
    {}, {"session_id": "session-1", "task_id": "job-123"},
    {"session_id": "session-1", "task_id": "job-123", "raw_payload": {"outcome": []}},
])
def test_invalid_payload_refused(bad):
    with pytest.raises(ValueError):
        operation_id(bad)


def test_canonical_envelope_enforces_timezone_and_bound():
    with pytest.raises(ValueError, match="timezone"):
        canonical_envelope(_payload(), created_at_utc="2026-11-21T19:00:00")
    huge = copy.deepcopy(_payload())
    huge["operator_notes"] = "x" * 40000
    with pytest.raises(ValueError, match="too large"):
        canonical_envelope(huge, created_at_utc="2026-11-21T19:00:00+00:00")


def test_operation_id_mismatch_rejected_before_write(tmp_path):
    bridge = AgentoraWritebackAdmission(_runtime(tmp_path))
    with pytest.raises(ValueError, match="identity mismatch"):
        bridge.admit(_payload(), created_at_utc="2026-11-21T19:00:00+00:00",
                     expected_operation_id="0" * 64)
    assert _counts(bridge.runtime.store.path) == (0, 0)
