from __future__ import annotations

import json
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol

from phios.mandala import AuthorityContext, MandalaStatus, MemoryOperationReceipt

from .models import MemoryRecord, MemoryResult
from .policy import MemoryAccessPolicy
from .store import MemoryStore
from .validation import require_nonempty, sha256_json


class RetrievalIndex(Protocol):
    def available(self) -> bool: ...


class UnavailableRetrievalIndex:
    def available(self) -> bool:
        return False


class GovernedMemoryService:
    def __init__(
        self,
        store: MemoryStore,
        policy: MemoryAccessPolicy,
        *,
        retrieval_index: RetrievalIndex | None = None,
    ) -> None:
        self.store = store
        self.policy = policy
        self.retrieval_index = retrieval_index or UnavailableRetrievalIndex()

    def put(
        self,
        record: MemoryRecord,
        *,
        principal_id: str,
        task_id: str,
        authority: AuthorityContext,
        operation_id: str,
        packet_id: str = "",
    ) -> MemoryResult:
        decision = self.policy.resolve(
            principal_id=principal_id,
            task_id=task_id,
            operation="memory.write",
            authority=authority,
        )
        if decision is None or not self.policy.permits(decision, record):
            return MemoryResult(status="blocked", error_code="MEMORY_WRITE_DENIED")
        operation_id = require_nonempty(operation_id, "operation_id")
        request_sha256 = sha256_json(
            {"operation": "put", "record": record.to_dict(), "principal_id": principal_id}
        )
        receipt = self._receipt(
            operation_id=operation_id,
            packet_id=packet_id,
            task_id=task_id,
            status=MandalaStatus.ACCEPTED,
            operation="put",
            source_ids=(record.source_id,),
            record=record,
            policy_sha256=decision.policy_sha256,
            input_sha256=request_sha256,
            canonical_status="pending_publication",
            index_status="unavailable",
        )
        self.store.put_pending(
            record,
            operation_id=operation_id,
            request_sha256=request_sha256,
            receipt_json=json.dumps(receipt.to_dict(), sort_keys=True),
        )
        return MemoryResult(status="ok", record=record)

    def get(
        self,
        record_id: str,
        *,
        principal_id: str,
        task_id: str,
        authority: AuthorityContext,
    ) -> MemoryResult:
        decision = self.policy.resolve(
            principal_id=principal_id,
            task_id=task_id,
            operation="memory.read",
            authority=authority,
        )
        if decision is None:
            return MemoryResult(status="blocked", error_code="MEMORY_READ_DENIED")
        record = self.store.get(record_id)
        if record is None:
            return MemoryResult(status="unavailable", error_code="MEMORY_NOT_AVAILABLE")
        if not self.policy.permits(decision, record):
            return MemoryResult(status="blocked", error_code="MEMORY_READ_DENIED")
        return MemoryResult(status="ok", record=record)

    def delete(
        self,
        record_id: str,
        *,
        principal_id: str,
        task_id: str,
        authority: AuthorityContext,
        operation_id: str,
        packet_id: str = "",
    ) -> MemoryResult:
        decision = self.policy.resolve(
            principal_id=principal_id,
            task_id=task_id,
            operation="memory.delete",
            authority=authority,
        )
        if decision is None:
            return MemoryResult(status="blocked", error_code="MEMORY_DELETE_DENIED")
        current = self.store.get(record_id)
        if current is None:
            return MemoryResult(status="unavailable", error_code="MEMORY_NOT_AVAILABLE")
        if not self.policy.permits(decision, current):
            return MemoryResult(status="blocked", error_code="MEMORY_DELETE_DENIED")
        now = datetime.now(UTC).isoformat()
        request_sha256 = sha256_json(
            {"operation": "delete", "record_id": record_id, "principal_id": principal_id}
        )
        receipt = self._receipt(
            operation_id=operation_id,
            packet_id=packet_id,
            task_id=task_id,
            status=MandalaStatus.ACCEPTED,
            operation="delete",
            source_ids=(current.source_id,),
            record=current,
            policy_sha256=decision.policy_sha256,
            input_sha256=request_sha256,
            canonical_status="deleted",
            index_status="remove_pending",
        )
        self.store.delete(
            record_id,
            operation_id=operation_id,
            deleted_at=now,
            request_sha256=request_sha256,
            receipt_json=json.dumps(receipt.to_dict(), sort_keys=True),
        )
        return MemoryResult(status="ok")

    def expire_due(self, *, now: datetime) -> tuple[str, ...]:
        return tuple(self.store.expire_due(now=now))

    @staticmethod
    def _receipt(
        *,
        operation_id: str,
        packet_id: str,
        task_id: str,
        status: MandalaStatus,
        operation: str,
        source_ids: tuple[str, ...],
        record: MemoryRecord,
        policy_sha256: str,
        input_sha256: str,
        canonical_status: str,
        index_status: str,
    ) -> MemoryOperationReceipt:
        receipt_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"phios.memory:{operation_id}"))
        timestamp = record.created_at if operation == "put" else datetime.now(UTC).isoformat()
        body = MemoryOperationReceipt(
            receipt_id=receipt_id,
            packet_id=packet_id or f"memory:{operation_id}",
            task_id=task_id,
            status=status,
            produced_by="phios.memory",
            timestamp_utc=timestamp,
            operation_id=operation_id,
            operation=operation,
            source_ids=source_ids,
            record_versions=(
                {
                    "record_id": record.record_id,
                    "revision": record.revision,
                    "record_sha256": record.record_sha256,
                },
            ),
            authorization_policy_sha256=policy_sha256,
            input_sha256=input_sha256,
            canonical_status=canonical_status,
            index_status=index_status,
        )
        return replace(body, receipt_sha256=sha256_json(body.to_dict()))
