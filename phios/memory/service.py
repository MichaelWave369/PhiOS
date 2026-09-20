from __future__ import annotations

import json
import time
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol

from phios.mandala import AuthorityContext, MandalaStatus, MemoryOperationReceipt

from .embeddings import EmbeddingProvider
from .models import (
    EmbeddingIdentity,
    IndexSyncResult,
    MemoryHit,
    MemoryRecord,
    MemoryResult,
    VectorCandidate,
)
from .policy import MemoryAccessPolicy
from .store import MemoryStore
from .validation import require_nonempty, sha256_json, validate_text


class RetrievalIndex(Protocol):
    generation_id: str
    embedding_identity: EmbeddingIdentity

    def available(self) -> bool: ...

    def upsert(
        self,
        *,
        record_id: str,
        revision: int,
        record_sha256: str,
        vector: tuple[float, ...],
        identity: EmbeddingIdentity,
    ) -> None: ...

    def remove(self, record_id: str) -> None: ...

    def search(
        self,
        vector: tuple[float, ...],
        *,
        eligible_versions: tuple[tuple[str, int, str], ...],
        limit: int,
    ) -> tuple[VectorCandidate, ...]: ...


class UnavailableRetrievalIndex:
    generation_id = ""
    embedding_identity: EmbeddingIdentity

    def available(self) -> bool:
        return False

    def upsert(
        self,
        *,
        record_id: str,
        revision: int,
        record_sha256: str,
        vector: tuple[float, ...],
        identity: EmbeddingIdentity,
    ) -> None:
        del record_id, revision, record_sha256, vector, identity
        raise RuntimeError("retrieval index unavailable")

    def remove(self, record_id: str) -> None:
        del record_id
        raise RuntimeError("retrieval index unavailable")

    def search(
        self,
        vector: tuple[float, ...],
        *,
        eligible_versions: tuple[tuple[str, int, str], ...],
        limit: int,
    ) -> tuple[VectorCandidate, ...]:
        del vector, eligible_versions, limit
        raise RuntimeError("retrieval index unavailable")


class GovernedMemoryService:
    def __init__(
        self,
        store: MemoryStore,
        policy: MemoryAccessPolicy,
        *,
        retrieval_index: RetrievalIndex | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.store = store
        self.policy = policy
        self.retrieval_index = retrieval_index or UnavailableRetrievalIndex()
        self.embedding_provider = embedding_provider

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
        receipt = self._operation_receipt(
            operation_id=operation_id,
            packet_id=packet_id,
            task_id=task_id,
            status=MandalaStatus.ACCEPTED,
            operation="put",
            records=(record,),
            policy_sha256=decision.policy_sha256,
            input_sha256=request_sha256,
            canonical_status="pending_publication",
            index_status="pending" if self.retrieval_index.available() else "unavailable",
        )
        self.store.put_pending(
            record,
            operation_id=operation_id,
            request_sha256=request_sha256,
            receipt_json=json.dumps(receipt.to_dict(), sort_keys=True),
        )
        return MemoryResult(status="ok", record=record, receipt_id=receipt.receipt_id)

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

    def semantic_search(
        self,
        query: str,
        *,
        principal_id: str,
        task_id: str,
        authority: AuthorityContext,
        operation_id: str,
        limit: int = 10,
        packet_id: str = "",
        embedding_timeout: float = 10.0,
    ) -> MemoryResult:
        """Search only policy-eligible canonical versions, then revalidate every hit."""

        decision = self.policy.resolve(
            principal_id=principal_id,
            task_id=task_id,
            operation="memory.read",
            authority=authority,
        )
        if decision is None:
            return MemoryResult(status="blocked", error_code="MEMORY_READ_DENIED")
        operation_id = require_nonempty(operation_id, "operation_id")
        try:
            query = validate_text(query)
        except ValueError:
            return MemoryResult(status="invalid", error_code="INVALID_MEMORY_QUERY")
        if isinstance(limit, bool) or not isinstance(limit, int) or not (1 <= limit <= 50):
            return MemoryResult(status="invalid", error_code="INVALID_MEMORY_LIMIT")

        eligible = self.store.list_eligible_versions(
            allowed_scopes=decision.allowed_scopes,
            allowed_classifications=decision.allowed_classifications,
        )
        request_sha256 = sha256_json(
            {
                "operation": "retrieve",
                "query_sha256": sha256_json({"query": query}),
                "principal_id": principal_id,
                "task_id": task_id,
                "limit": limit,
                "policy_sha256": decision.policy_sha256,
            }
        )
        if not eligible:
            receipt = self._operation_receipt(
                operation_id=operation_id,
                packet_id=packet_id,
                task_id=task_id,
                status=MandalaStatus.ACCEPTED,
                operation="retrieve",
                records=(),
                policy_sha256=decision.policy_sha256,
                input_sha256=request_sha256,
                canonical_status="unchanged",
                index_status="not_needed",
            )
            self.store.record_operation_receipt(
                operation_id=operation_id,
                request_sha256=request_sha256,
                receipt_json=json.dumps(receipt.to_dict(), sort_keys=True),
            )
            return MemoryResult(status="ok", hits=(), receipt_id=receipt.receipt_id)

        if self.embedding_provider is None or not self.retrieval_index.available():
            return self._retrieval_unavailable(
                operation_id=operation_id,
                packet_id=packet_id,
                task_id=task_id,
                decision_policy_sha256=decision.policy_sha256,
                request_sha256=request_sha256,
                error_code="SEMANTIC_RETRIEVAL_UNAVAILABLE",
            )

        try:
            vector = self.embedding_provider.embed(
                query,
                deadline=time.monotonic() + max(0.001, float(embedding_timeout)),
            )
            identity = self.embedding_provider.identity()
            if identity != self.retrieval_index.embedding_identity:
                raise RuntimeError("active index generation does not match embedding identity")
            candidates = self.retrieval_index.search(
                vector,
                eligible_versions=eligible,
                limit=limit,
            )
        except (RuntimeError, TimeoutError, ValueError, OSError):
            return self._retrieval_unavailable(
                operation_id=operation_id,
                packet_id=packet_id,
                task_id=task_id,
                decision_policy_sha256=decision.policy_sha256,
                request_sha256=request_sha256,
                error_code="SEMANTIC_RETRIEVAL_FAILED",
            )

        hits: list[MemoryHit] = []
        records: list[MemoryRecord] = []
        for candidate in candidates:
            record = self.store.get_current_version(
                candidate.record_id,
                candidate.revision,
                candidate.record_sha256,
            )
            if record is None:
                continue
            # Recheck policy after native ranking/canonical hydration.
            if not self.policy.permits(decision, record):
                continue
            records.append(record)
            hits.append(
                MemoryHit(
                    record=record,
                    retrieval_distance=candidate.retrieval_distance,
                )
            )

        receipt = self._operation_receipt(
            operation_id=operation_id,
            packet_id=packet_id,
            task_id=task_id,
            status=MandalaStatus.ACCEPTED,
            operation="retrieve",
            records=tuple(records),
            policy_sha256=decision.policy_sha256,
            input_sha256=request_sha256,
            canonical_status="unchanged",
            index_status="ready",
            embedding_identity=identity,
            index_generation=self.retrieval_index.generation_id,
        )
        self.store.record_operation_receipt(
            operation_id=operation_id,
            request_sha256=request_sha256,
            receipt_json=json.dumps(receipt.to_dict(), sort_keys=True),
        )
        return MemoryResult(
            status="ok",
            hits=tuple(hits),
            receipt_id=receipt.receipt_id,
        )

    def sync_index(
        self,
        *,
        limit: int = 100,
        embedding_timeout: float = 10.0,
    ) -> IndexSyncResult:
        """Explicitly process derived index work. This never grants memory access."""

        if self.embedding_provider is None or not self.retrieval_index.available():
            return IndexSyncResult(
                status="unavailable",
                error_code="SEMANTIC_RETRIEVAL_UNAVAILABLE",
            )
        processed = indexed = removed = stale = 0
        for work in self.store.pending_index_work(limit):
            work_id_raw = work["work_id"]
            revision_raw = work["revision"]
            if (
                isinstance(work_id_raw, bool)
                or not isinstance(work_id_raw, int)
                or isinstance(revision_raw, bool)
                or not isinstance(revision_raw, int)
            ):
                return IndexSyncResult(
                    status="degraded",
                    processed=processed,
                    indexed=indexed,
                    removed=removed,
                    stale=stale,
                    error_code="INDEX_WORK_INVALID",
                )
            work_id = work_id_raw
            record_id = str(work["record_id"])
            revision = revision_raw
            action = str(work["action"])
            if action == "remove":
                try:
                    self.retrieval_index.remove(record_id)
                except (RuntimeError, ValueError, OSError):
                    return IndexSyncResult(
                        status="degraded",
                        processed=processed,
                        indexed=indexed,
                        removed=removed,
                        stale=stale,
                        error_code="INDEX_REMOVE_FAILED",
                    )
                self.store.mark_index_work_done(work_id)
                processed += 1
                removed += 1
                continue

            record = self.store.get_indexable_record(record_id, revision)
            if record is None:
                self.store.mark_index_work_done(work_id)
                processed += 1
                stale += 1
                continue

            try:
                vector = self.embedding_provider.embed(
                    record.text,
                    deadline=time.monotonic() + max(0.001, float(embedding_timeout)),
                )
                identity = self.embedding_provider.identity()
                if identity != self.retrieval_index.embedding_identity:
                    raise RuntimeError("active index generation does not match embedding identity")
                self.retrieval_index.upsert(
                    record_id=record.record_id,
                    revision=record.revision,
                    record_sha256=record.record_sha256,
                    vector=vector,
                    identity=identity,
                )
                index_operation_id = (
                    f"index:{self.retrieval_index.generation_id}:{work_id}:"
                    f"{record.record_sha256}"
                )
                input_sha256 = sha256_json(
                    {
                        "operation": "index",
                        "record_id": record.record_id,
                        "revision": record.revision,
                        "record_sha256": record.record_sha256,
                        "embedding_identity": identity.to_dict(),
                    }
                )
                receipt = self._operation_receipt(
                    operation_id=index_operation_id,
                    packet_id="",
                    task_id="derived-index-maintenance",
                    status=MandalaStatus.ACCEPTED,
                    operation="index",
                    records=(record,),
                    policy_sha256=sha256_json({"policy": "derived-index-maintenance-v0.1"}),
                    input_sha256=input_sha256,
                    canonical_status="unchanged",
                    index_status="ready",
                    embedding_identity=identity,
                    index_generation=self.retrieval_index.generation_id,
                )
                self.store.record_operation_receipt(
                    operation_id=index_operation_id,
                    request_sha256=input_sha256,
                    receipt_json=json.dumps(receipt.to_dict(), sort_keys=True),
                )
            except (RuntimeError, TimeoutError, ValueError, OSError):
                return IndexSyncResult(
                    status="degraded",
                    processed=processed,
                    indexed=indexed,
                    removed=removed,
                    stale=stale,
                    error_code="INDEX_UPSERT_FAILED",
                )
            self.store.mark_index_work_done(work_id)
            processed += 1
            indexed += 1

        return IndexSyncResult(
            status="ok",
            processed=processed,
            indexed=indexed,
            removed=removed,
            stale=stale,
        )

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
        receipt = self._operation_receipt(
            operation_id=operation_id,
            packet_id=packet_id,
            task_id=task_id,
            status=MandalaStatus.ACCEPTED,
            operation="delete",
            records=(current,),
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
        return MemoryResult(status="ok", receipt_id=receipt.receipt_id)

    def expire_due(self, *, now: datetime) -> tuple[str, ...]:
        return tuple(self.store.expire_due(now=now))

    def _retrieval_unavailable(
        self,
        *,
        operation_id: str,
        packet_id: str,
        task_id: str,
        decision_policy_sha256: str,
        request_sha256: str,
        error_code: str,
    ) -> MemoryResult:
        identity: EmbeddingIdentity | None = None
        if self.embedding_provider is not None:
            try:
                identity = self.embedding_provider.identity()
            except (RuntimeError, ValueError, OSError):
                identity = None
        receipt = self._operation_receipt(
            operation_id=operation_id,
            packet_id=packet_id,
            task_id=task_id,
            status=MandalaStatus.DEGRADED,
            operation="retrieve",
            records=(),
            policy_sha256=decision_policy_sha256,
            input_sha256=request_sha256,
            canonical_status="unchanged",
            index_status="unavailable",
            embedding_identity=identity,
            index_generation=(
                self.retrieval_index.generation_id
                if self.retrieval_index.available()
                else None
            ),
            error_code=error_code,
        )
        self.store.record_operation_receipt(
            operation_id=operation_id,
            request_sha256=request_sha256,
            receipt_json=json.dumps(receipt.to_dict(), sort_keys=True),
        )
        return MemoryResult(
            status="unavailable",
            receipt_id=receipt.receipt_id,
            error_code=error_code,
        )

    @staticmethod
    def _operation_receipt(
        *,
        operation_id: str,
        packet_id: str,
        task_id: str,
        status: MandalaStatus,
        operation: str,
        records: tuple[MemoryRecord, ...],
        policy_sha256: str,
        input_sha256: str,
        canonical_status: str,
        index_status: str,
        embedding_identity: EmbeddingIdentity | None = None,
        index_generation: str | None = None,
        error_code: str | None = None,
    ) -> MemoryOperationReceipt:
        receipt_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"phios.memory:{operation_id}"))
        timestamp = (
            records[0].created_at
            if operation == "put" and records
            else datetime.now(UTC).isoformat()
        )
        body = MemoryOperationReceipt(
            receipt_id=receipt_id,
            packet_id=packet_id or f"memory:{operation_id}",
            task_id=task_id,
            status=status,
            produced_by="phios.memory",
            timestamp_utc=timestamp,
            operation_id=operation_id,
            operation=operation,
            source_ids=tuple(record.source_id for record in records),
            record_versions=tuple(
                {
                    "record_id": record.record_id,
                    "revision": record.revision,
                    "record_sha256": record.record_sha256,
                }
                for record in records
            ),
            authorization_policy_sha256=policy_sha256,
            input_sha256=input_sha256,
            canonical_status=canonical_status,
            index_status=index_status,
            embedding_identity=(
                embedding_identity.to_dict() if embedding_identity is not None else None
            ),
            index_generation=index_generation,
            error_code=error_code,
        )
        return replace(body, receipt_sha256=sha256_json(body.to_dict()))
