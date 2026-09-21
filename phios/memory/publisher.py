from __future__ import annotations

from typing import Any

from phios.mandala import MandalaReceiptLedger, MandalaStatus, MemoryOperationReceipt

from .store import MemoryStore


class MemoryReceiptPublisher:
    """Reconcile the durable memory outbox into the append-only Mandala ledger."""

    def __init__(self, store: MemoryStore, ledger: MandalaReceiptLedger) -> None:
        self.store = store
        self.ledger = ledger

    def publish_pending(self) -> int:
        published = 0
        for payload in self.store.pending_receipts():
            receipt = _receipt_from_payload(payload)
            if not self.ledger.has_receipt(receipt.receipt_id):
                self.ledger.append(receipt)
            self.store.mark_receipt_published(receipt.operation_id)
            published += 1
        return published


def _receipt_from_payload(payload: dict[str, Any]) -> MemoryOperationReceipt:
    if payload.get("receipt_type") != "MemoryOperationReceipt":
        raise ValueError("memory outbox contains a non-memory receipt")
    return MemoryOperationReceipt(
        receipt_id=str(payload["receipt_id"]),
        packet_id=str(payload["packet_id"]),
        task_id=str(payload["task_id"]),
        status=MandalaStatus(str(payload["status"])),
        produced_by=str(payload["produced_by"]),
        timestamp_utc=str(payload["timestamp_utc"]),
        contract_version=str(payload["contract_version"]),
        parent_receipt_id=(
            str(payload["parent_receipt_id"])
            if payload.get("parent_receipt_id") is not None
            else None
        ),
        operation_id=str(payload["operation_id"]),
        operation=str(payload["operation"]),
        source_ids=tuple(str(item) for item in payload.get("source_ids", [])),
        record_versions=tuple(
            dict(item)
            for item in payload.get("record_versions", [])
            if isinstance(item, dict)
        ),
        authorization_policy_sha256=str(
            payload.get("authorization_policy_sha256", "")
        ),
        input_sha256=str(payload.get("input_sha256", "")),
        canonical_status=str(payload.get("canonical_status", "unchanged")),
        index_status=str(payload.get("index_status", "unavailable")),
        embedding_identity=(
            dict(payload["embedding_identity"])
            if isinstance(payload.get("embedding_identity"), dict)
            else None
        ),
        index_generation=(
            str(payload["index_generation"])
            if payload.get("index_generation") is not None
            else None
        ),
        error_code=(
            str(payload["error_code"])
            if payload.get("error_code") is not None
            else None
        ),
        transformation_lineage=tuple(
            dict(item)
            for item in payload.get("transformation_lineage", [])
            if isinstance(item, dict)
        ),
        transformation_lineage_sha256s=tuple(
            str(item)
            for item in payload.get("transformation_lineage_sha256s", [])
        ),
        exactness_classes=tuple(
            str(item)
            for item in payload.get("exactness_classes", [])
        ),
        taint_labels=tuple(
            str(item)
            for item in payload.get("taint_labels", [])
        ),
        promotion_status=str(payload.get("promotion_status", "not_promoted")),
        action_authority=bool(payload.get("action_authority", False)),
        execution_authority=bool(payload.get("execution_authority", False)),
        receipt_sha256=str(payload.get("receipt_sha256", "")),
    )
