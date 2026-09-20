from datetime import UTC, datetime
from pathlib import Path

import pytest

from phios.memory import MemoryRecord, MemoryStore
from phios.memory.validation import sha256_json


def _record(*, record_id: str = "mem-1", revision: int = 1, source_id: str = "src-1") -> MemoryRecord:
    return MemoryRecord.build(
        record_id=record_id,
        revision=revision,
        source_id=source_id,
        source_kind="human",
        provenance_refs=("evidence:1",),
        created_at="2026-09-20T18:00:00+00:00",
        scope_id="private",
        classification="operator",
        retention_policy_id="retain",
        expires_at="2026-10-20T18:00:00+00:00",
        epistemic_kind="source",
        text="same text",
    )


def _receipt(operation_id: str, record: MemoryRecord, operation: str = "put") -> str:
    import json

    return json.dumps(
        {
            "operation_id": operation_id,
            "operation": operation,
            "record_versions": [
                {
                    "record_id": record.record_id,
                    "revision": record.revision,
                    "record_sha256": record.record_sha256,
                }
            ],
        },
        sort_keys=True,
    )


def test_pending_insert_is_not_readable_until_publication(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "canonical.sqlite3")
    record = _record()
    request = sha256_json({"record": record.to_dict()})
    assert store.put_pending(
        record,
        operation_id="op-1",
        request_sha256=request,
        receipt_json=_receipt("op-1", record),
    )
    assert store.get("mem-1") is None
    assert len(store.pending_receipts()) == 1
    store.mark_receipt_published("op-1")
    assert store.get("mem-1") == record


def test_operation_replay_is_idempotent_but_payload_change_is_rejected(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "canonical.sqlite3")
    record = _record()
    request = sha256_json({"record": record.to_dict()})
    store.put_pending(record, operation_id="op-1", request_sha256=request, receipt_json=_receipt("op-1", record))
    assert not store.put_pending(
        record,
        operation_id="op-1",
        request_sha256=request,
        receipt_json=_receipt("op-1", record),
    )
    with pytest.raises(ValueError, match="different request"):
        store.put_pending(
            record,
            operation_id="op-1",
            request_sha256="0" * 64,
            receipt_json=_receipt("op-1", record),
        )


def test_same_text_from_different_sources_remains_distinct(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "canonical.sqlite3")
    a = _record(record_id="a", source_id="source-a")
    b = _record(record_id="b", source_id="source-b")
    for op, record in (("op-a", a), ("op-b", b)):
        request = sha256_json({"record": record.to_dict()})
        store.put_pending(record, operation_id=op, request_sha256=request, receipt_json=_receipt(op, record))
        store.mark_receipt_published(op)
    assert store.get("a") is not None
    assert store.get("b") is not None
    assert store.get("a").source_id != store.get("b").source_id  # type: ignore[union-attr]


def test_delete_immediately_makes_record_ineligible(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "canonical.sqlite3")
    record = _record()
    request = sha256_json({"record": record.to_dict()})
    store.put_pending(record, operation_id="put", request_sha256=request, receipt_json=_receipt("put", record))
    store.mark_receipt_published("put")
    delete_request = sha256_json({"record_id": record.record_id})
    store.delete(
        record.record_id,
        operation_id="delete",
        deleted_at="2026-09-20T19:00:00+00:00",
        request_sha256=delete_request,
        receipt_json=_receipt("delete", record, "delete"),
    )
    assert store.get(record.record_id) is None


def test_expired_record_is_never_returned_even_without_sweeper(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "canonical.sqlite3")
    record = MemoryRecord.build(
        record_id="expired",
        revision=1,
        source_id="src",
        source_kind="human",
        provenance_refs=(),
        created_at="2026-09-20T18:00:00+00:00",
        scope_id="private",
        classification="operator",
        retention_policy_id="short",
        expires_at="2026-09-20T18:30:00+00:00",
        epistemic_kind="source",
        text="expired",
    )
    request = sha256_json({"record": record.to_dict()})
    store.put_pending(record, operation_id="put", request_sha256=request, receipt_json=_receipt("put", record))
    store.mark_receipt_published("put")
    assert store.get("expired", now=datetime(2026, 9, 20, 19, tzinfo=UTC)) is None
