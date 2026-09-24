from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from phios.memory import (
    MemoryOperatorRuntime,
    MemoryRuntimeConfig,
    SystemHistoryPersistenceBridge,
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


def _state(char: str, composed_at: str) -> dict[str, object]:
    del char
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
    char: str,
    *,
    previous: dict[str, object],
    current: dict[str, object],
    recorded_at: str,
) -> dict[str, object]:
    del char
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
    permissions: tuple[str, ...] = ("history.persist", "memory.write", "memory.read"),
) -> MemoryOperatorRuntime:
    config = MemoryRuntimeConfig(
        enabled=True,
        principal_id="system-history-operator",
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


def test_persistent_history_uses_canonical_memory_and_mandala_receipts(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path / "memory")
    previous = _state("a", "2026-09-22T20:00:00+00:00")
    current = _state("b", "2026-09-22T20:00:05+00:00")
    change = _change(
        "c",
        previous=previous,
        current=current,
        recorded_at="2026-09-22T20:00:06+00:00",
    )

    result = SystemHistoryPersistenceBridge(runtime).persist_transition(
        previous_state=previous,
        current_state=current,
        change_receipt=change,
        task_id="test-system-history",
    )

    assert result.persistent is True
    assert result.canonical is True
    assert result.operational_authority is False
    assert result.action_authority is False
    assert result.execution_authority is False
    assert result.state_record_ids == (
        "phishell.system-state." + str(previous["receiptDigest"]).removeprefix("sha256:"),
        "phishell.system-state." + str(current["receiptDigest"]).removeprefix("sha256:"),
    )
    assert result.change_record_id == (
        "phishell.system-change." + str(change["changeDigest"]).removeprefix("sha256:")
    )

    previous_evidence, current_evidence = result.state_evidence_refs
    change_evidence = result.change_evidence_ref

    assert previous_evidence.source_id == "phishell.system-state"
    assert current_evidence.source_id == "phishell.system-state"
    assert previous_evidence.source_version == "phios.system-state.v1"
    assert current_evidence.source_version == "phios.system-state.v1"
    assert change_evidence.source_id == "phishell.system-change"
    assert change_evidence.source_version == "phios.system-change.v1"

    assert previous_evidence.operational_authority is False
    assert previous_evidence.action_authority is False
    assert previous_evidence.execution_authority is False
    assert change_evidence.operational_authority is False
    assert change_evidence.action_authority is False
    assert change_evidence.execution_authority is False

    previous_record = runtime.get(result.state_record_ids[0], task_id="read-previous").record
    current_record = runtime.get(result.state_record_ids[1], task_id="read-current").record
    change_record = runtime.get(result.change_record_id, task_id="read-change").record

    assert previous_record is not None
    assert current_record is not None
    assert change_record is not None
    assert previous_record.epistemic_kind == "source"
    assert current_record.epistemic_kind == "source"
    assert change_record.epistemic_kind == "derived"
    assert change_record.exactness_class == "REVERSIBLE"
    assert change_record.derived_from == result.state_record_ids
    assert len(change_record.transformation_lineage_sha256s) == 1
    assert change_record.scope_id == "system-history"
    assert change_record.classification == "system-observation"
    assert change_record.retention_policy_id == "retain-system-history"

    assert previous_evidence.content_sha256 == previous_record.content_sha256
    assert current_evidence.content_sha256 == current_record.content_sha256
    assert change_evidence.content_sha256 == change_record.content_sha256
    assert previous_evidence.evidence_ref == (
        "evidence:sha256:" + previous_record.content_sha256
    )
    assert change_evidence.transformation_lineage_sha256s == (
        change_record.transformation_lineage_sha256s
    )
    assert change_evidence.exactness_class == "REVERSIBLE"

    ledger_path = runtime.ledger.path
    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    payloads = [json.loads(line) for line in lines]
    assert all(payload["receipt_type"] == "MemoryOperationReceipt" for payload in payloads)
    assert all(payload["execution_authority"] is False for payload in payloads)
    assert payloads[-1]["transformation_lineage_sha256s"] == list(
        change_record.transformation_lineage_sha256s
    )


def test_persistent_history_is_idempotent_for_same_receipt_hashes(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path / "memory")
    previous = _state("d", "2026-09-22T20:10:00+00:00")
    current = _state("e", "2026-09-22T20:10:05+00:00")
    change = _change(
        "f",
        previous=previous,
        current=current,
        recorded_at="2026-09-22T20:10:06+00:00",
    )
    bridge = SystemHistoryPersistenceBridge(runtime)

    first = bridge.persist_transition(
        previous_state=previous,
        current_state=current,
        change_receipt=change,
    )
    second = bridge.persist_transition(
        previous_state=previous,
        current_state=current,
        change_receipt=change,
    )

    assert first.state_record_ids == second.state_record_ids
    assert first.change_record_id == second.change_record_id
    assert len(runtime.ledger.path.read_text(encoding="utf-8").splitlines()) == 3


def test_persistent_history_requires_explicit_history_persist_authority(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path / "memory", permissions=("memory.write", "memory.read"))
    previous = _state("1", "2026-09-22T20:20:00+00:00")
    current = _state("2", "2026-09-22T20:20:05+00:00")
    change = _change(
        "3",
        previous=previous,
        current=current,
        recorded_at="2026-09-22T20:20:06+00:00",
    )

    with pytest.raises(PermissionError, match="history.persist"):
        SystemHistoryPersistenceBridge(runtime).persist_transition(
            previous_state=previous,
            current_state=current,
            change_receipt=change,
        )


def test_change_receipt_must_reference_the_two_supplied_states(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path / "memory")
    previous = _state("4", "2026-09-22T20:30:00+00:00")
    current = _state("5", "2026-09-22T20:30:05+00:00")
    change = _change(
        "6",
        previous=previous,
        current=current,
        recorded_at="2026-09-22T20:30:06+00:00",
    )
    change["toReceiptDigest"] = "sha256:" + "7" * 64
    change["changeDigest"] = _body_digest(change, "changeDigest")

    with pytest.raises(ValueError, match="current system-state"):
        SystemHistoryPersistenceBridge(runtime).persist_transition(
            previous_state=previous,
            current_state=current,
            change_receipt=change,
        )


def test_persistent_history_also_requires_memory_write_authority(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path / "memory", permissions=("history.persist", "memory.read"))
    previous = _state("8", "2026-09-22T20:40:00+00:00")
    current = _state("9", "2026-09-22T20:40:05+00:00")
    change = _change(
        "a",
        previous=previous,
        current=current,
        recorded_at="2026-09-22T20:40:06+00:00",
    )

    with pytest.raises(PermissionError, match="memory.write"):
        SystemHistoryPersistenceBridge(runtime).persist_transition(
            previous_state=previous,
            current_state=current,
            change_receipt=change,
        )


def test_persistence_rejects_tampered_system_state_body(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path / "memory")
    previous = _state("ignored", "2026-09-22T20:50:00+00:00")
    current = _state("ignored", "2026-09-22T20:50:05+00:00")
    change = _change(
        "ignored",
        previous=previous,
        current=current,
        recorded_at="2026-09-22T20:50:06+00:00",
    )
    current["readOnly"] = False

    with pytest.raises(ValueError, match="readOnly"):
        SystemHistoryPersistenceBridge(runtime).persist_transition(
            previous_state=previous,
            current_state=current,
            change_receipt=change,
        )


def test_persistence_rejects_digest_mismatch_after_body_edit(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path / "memory")
    previous = _state("ignored", "2026-09-22T21:00:00+00:00")
    current = _state("ignored", "2026-09-22T21:00:05+00:00")
    change = _change(
        "ignored",
        previous=previous,
        current=current,
        recorded_at="2026-09-22T21:00:06+00:00",
    )
    change["recordedAt"] = "2026-09-22T21:00:07+00:00"

    with pytest.raises(ValueError, match="changeDigest does not match"):
        SystemHistoryPersistenceBridge(runtime).persist_transition(
            previous_state=previous,
            current_state=current,
            change_receipt=change,
        )
