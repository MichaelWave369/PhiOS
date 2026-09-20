from dataclasses import FrozenInstanceError

import pytest

from phios.mandala import MemoryOperationReceipt, MandalaStatus
from phios.memory import MemoryRecord


def _record(**overrides: object) -> MemoryRecord:
    payload = {
        "record_id": "mem-1",
        "revision": 1,
        "source_id": "source-1",
        "source_kind": "human",
        "provenance_refs": ("evidence:1",),
        "created_at": "2026-09-20T18:00:00+00:00",
        "scope_id": "private",
        "classification": "operator",
        "retention_policy_id": "retain-30d",
        "expires_at": "2026-10-20T18:00:00+00:00",
        "epistemic_kind": "source",
        "text": "canonical memory",
    }
    payload.update(overrides)
    return MemoryRecord.build(**payload)  # type: ignore[arg-type]


def test_record_digest_is_deterministic_and_record_is_frozen() -> None:
    a = _record()
    b = _record()
    assert a.record_sha256 == b.record_sha256
    assert a.content_sha256 == b.content_sha256
    with pytest.raises(FrozenInstanceError):
        a.text = "changed"  # type: ignore[misc]


def test_derived_record_requires_source_lineage() -> None:
    with pytest.raises(ValueError, match="derived records require"):
        _record(epistemic_kind="derived", derived_from=())


def test_revision_rejects_bool_and_timestamp_requires_timezone() -> None:
    with pytest.raises(ValueError, match="revision"):
        _record(revision=True)
    with pytest.raises(ValueError, match="timezone"):
        _record(created_at="2026-09-20T18:00:00")


def test_noncanonical_source_kind_is_rejected() -> None:
    with pytest.raises(ValueError, match="OriginKind"):
        _record(source_kind="mystery")


def test_memory_operation_receipt_is_authority_false() -> None:
    receipt = MemoryOperationReceipt(
        receipt_id="r1",
        packet_id="p1",
        task_id="t1",
        status=MandalaStatus.ACCEPTED,
        produced_by="phios.memory",
        timestamp_utc="2026-09-20T18:00:00+00:00",
        operation_id="op1",
        operation="put",
    )
    body = receipt.to_dict()
    assert body["promotion_status"] == "not_promoted"
    assert body["action_authority"] is False
    assert body["execution_authority"] is False
    assert body["receipt_type"] == "MemoryOperationReceipt"
