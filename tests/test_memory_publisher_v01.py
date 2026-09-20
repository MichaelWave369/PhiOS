import json
from pathlib import Path

from phios.mandala import MandalaReceiptLedger, MandalaStatus, MemoryOperationReceipt
from phios.memory import MemoryRecord, MemoryStore
from phios.memory.publisher import MemoryReceiptPublisher
from phios.memory.validation import sha256_json


def test_outbox_reconciliation_is_idempotent_across_append_mark_gap(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "canonical.sqlite3")
    ledger = MandalaReceiptLedger(tmp_path / "mandala.jsonl")
    record = MemoryRecord.build(
        record_id="mem-1",
        revision=1,
        source_id="source-1",
        source_kind="human",
        provenance_refs=(),
        created_at="2026-09-20T20:00:00+00:00",
        scope_id="private",
        classification="operator",
        retention_policy_id="retain",
        expires_at=None,
        epistemic_kind="source",
        text="hello",
    )
    request_sha256 = sha256_json({"record": record.to_dict()})
    receipt = MemoryOperationReceipt(
        receipt_id="receipt-1",
        packet_id="packet-1",
        task_id="task-1",
        status=MandalaStatus.ACCEPTED,
        produced_by="phios.memory",
        timestamp_utc=record.created_at,
        operation_id="op-1",
        operation="put",
        source_ids=(record.source_id,),
        record_versions=(
            {
                "record_id": record.record_id,
                "revision": record.revision,
                "record_sha256": record.record_sha256,
            },
        ),
        authorization_policy_sha256="a" * 64,
        input_sha256=request_sha256,
        canonical_status="pending_publication",
        index_status="unavailable",
    )
    store.put_pending(
        record,
        operation_id="op-1",
        request_sha256=request_sha256,
        receipt_json=json.dumps(receipt.to_dict(), sort_keys=True),
    )

    ledger.append(receipt)
    publisher = MemoryReceiptPublisher(store, ledger)
    assert publisher.publish_pending() == 1
    assert store.pending_receipts() == []
    assert len(ledger.recent(10)) == 1
    assert store.get("mem-1") is not None
