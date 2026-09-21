from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path

from phios.mandala import (
    AuthorityContext,
    MandalaReceiptLedger,
    TransformationLineageReceipt,
)

from .config import MemoryRuntimeConfig
from .embeddings import OllamaEmbeddingProvider
from .horizon import EvidenceHorizonPolicy, MemoryEvidenceHorizon
from .legacy import LegacyImportPlan
from .models import IndexSyncResult, MemoryRecord, MemoryResult
from .policy import MemoryAccessPolicy, MemoryPolicyRule
from .publisher import MemoryReceiptPublisher
from .service import GovernedMemoryService
from .sqlite_vec_index import SqliteVecIndex
from .store import MemoryStore


@dataclass(frozen=True, kw_only=True)
class MemoryOperatorStatus:
    enabled: bool
    semantic_enabled: bool
    evidence_horizon_enabled: bool
    evidence_horizon_policy_sha256: str | None
    state_root: str
    canonical_db: str
    mandala_ledger: str
    sqlite_vec_installed: bool
    principal_id: str
    scopes: tuple[str, ...]
    classifications: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "semantic_enabled": self.semantic_enabled,
            "evidence_horizon_enabled": self.evidence_horizon_enabled,
            "evidence_horizon_policy_sha256": self.evidence_horizon_policy_sha256,
            "state_root": self.state_root,
            "canonical_db": self.canonical_db,
            "mandala_ledger": self.mandala_ledger,
            "sqlite_vec_installed": self.sqlite_vec_installed,
            "principal_id": self.principal_id,
            "scopes": list(self.scopes),
            "classifications": list(self.classifications),
        }


class MemoryOperatorRuntime:
    def __init__(
        self,
        *,
        state_root: Path,
        config: MemoryRuntimeConfig,
        allowed_permissions: tuple[str, ...] = (),
    ) -> None:
        self.state_root = state_root.expanduser()
        self.config = config
        self.authority = AuthorityContext(
            ceiling=allowed_permissions,
            grants=allowed_permissions,
        )
        self.store = MemoryStore(self.state_root / "canonical.sqlite3")
        self.ledger = MandalaReceiptLedger(
            self.state_root.parent / "spine-v0.1" / "ledger" / "mandala-receipts.jsonl"
        )
        self.policy = MemoryAccessPolicy(
            (
                MemoryPolicyRule(
                    principal_id=config.principal_id,
                    scopes=config.scopes,
                    classifications=config.classifications,
                    operations=(
                        "memory.read",
                        "memory.write",
                        "memory.delete",
                        "memory.index",
                        "memory.import",
                    ),
                ),
            ),
            revision="operator-v0.3",
        )
        self.publisher = MemoryReceiptPublisher(self.store, self.ledger)
        self.evidence_horizon: MemoryEvidenceHorizon | None = None
        if config.evidence_horizon_enabled:
            self.evidence_horizon = MemoryEvidenceHorizon(
                EvidenceHorizonPolicy(
                    policy_id="operator-memory-horizon",
                    active_window_seconds=config.active_context_window_seconds,
                    reactivation_window_seconds=config.reactivation_window_seconds,
                    fresh_evidence_window_seconds=(
                        config.fresh_evidence_window_seconds
                    ),
                )
            )
        self.service = GovernedMemoryService(
            self.store,
            self.policy,
            evidence_horizon=self.evidence_horizon,
        )

    def status(self) -> MemoryOperatorStatus:
        return MemoryOperatorStatus(
            enabled=self.config.enabled,
            semantic_enabled=self.config.semantic_enabled,
            evidence_horizon_enabled=self.config.evidence_horizon_enabled,
            evidence_horizon_policy_sha256=(
                self.evidence_horizon.policy.policy_sha256
                if self.evidence_horizon is not None
                else None
            ),
            state_root=str(self.state_root),
            canonical_db=str(self.store.path),
            mandala_ledger=str(self.ledger.path),
            sqlite_vec_installed=importlib.util.find_spec("sqlite_vec") is not None,
            principal_id=self.config.principal_id,
            scopes=self.config.scopes,
            classifications=self.config.classifications,
        )

    def require_enabled(self) -> None:
        if not self.config.enabled:
            raise RuntimeError("governed memory is disabled by operator configuration")

    def put(
        self,
        record: MemoryRecord,
        *,
        operation_id: str,
        task_id: str,
        transformation_lineage: tuple[TransformationLineageReceipt, ...] = (),
    ) -> MemoryResult:
        self.require_enabled()
        result = self.service.put(
            record,
            principal_id=self.config.principal_id,
            task_id=task_id,
            authority=self.authority,
            operation_id=operation_id,
            transformation_lineage=transformation_lineage,
        )
        if result.status == "ok":
            try:
                self.publisher.publish_pending()
            except Exception:
                return MemoryResult(
                    status="unavailable",
                    error_code="MEMORY_RECEIPT_PUBLICATION_FAILED",
                )
        return result

    def get(
        self,
        record_id: str,
        *,
        task_id: str,
        reactivation_record_id: str | None = None,
    ) -> MemoryResult:
        self.require_enabled()
        return self.service.get(
            record_id,
            principal_id=self.config.principal_id,
            task_id=task_id,
            authority=self.authority,
            reactivation_record_id=reactivation_record_id,
        )

    def delete(self, record_id: str, *, operation_id: str, task_id: str) -> MemoryResult:
        self.require_enabled()
        result = self.service.delete(
            record_id,
            principal_id=self.config.principal_id,
            task_id=task_id,
            authority=self.authority,
            operation_id=operation_id,
        )
        if result.status == "ok":
            try:
                self.publisher.publish_pending()
            except Exception:
                return MemoryResult(
                    status="degraded",
                    error_code="MEMORY_DELETE_RECEIPT_PUBLICATION_FAILED",
                )
        return result

    def semantic_search(
        self,
        query: str,
        *,
        operation_id: str,
        task_id: str,
        limit: int,
        reactivation_record_ids: dict[str, str] | None = None,
    ) -> MemoryResult:
        self.require_enabled()
        service = self._semantic_service()
        result = service.semantic_search(
            query,
            principal_id=self.config.principal_id,
            task_id=task_id,
            authority=self.authority,
            operation_id=operation_id,
            limit=limit,
            reactivation_record_ids=reactivation_record_ids,
        )
        try:
            self.publisher.publish_pending()
        except Exception:
            return MemoryResult(
                status="unavailable",
                error_code="MEMORY_RECEIPT_PUBLICATION_FAILED",
            )
        return result

    def reindex(self, *, full: bool = False, limit: int = 100) -> IndexSyncResult:
        self.require_enabled()
        decision = self.policy.resolve(
            principal_id=self.config.principal_id,
            task_id="memory-index-maintenance",
            operation="memory.index",
            authority=self.authority,
        )
        if decision is None:
            return IndexSyncResult(status="unavailable", error_code="MEMORY_INDEX_DENIED")
        if full:
            self.store.enqueue_reindex(
                allowed_scopes=decision.allowed_scopes,
                allowed_classifications=decision.allowed_classifications,
            )
        service = self._semantic_service()
        result = service.sync_index(
            limit=limit,
            allowed_scopes=decision.allowed_scopes,
            allowed_classifications=decision.allowed_classifications,
        )
        if result.status == "ok":
            try:
                self.publisher.publish_pending()
            except Exception:
                return IndexSyncResult(
                    status="degraded",
                    processed=result.processed,
                    indexed=result.indexed,
                    removed=result.removed,
                    stale=result.stale,
                    error_code="MEMORY_RECEIPT_PUBLICATION_FAILED",
                )
        return result

    def import_legacy(self, plan: LegacyImportPlan, *, task_id: str) -> tuple[int, tuple[str, ...]]:
        self.require_enabled()
        decision = self.policy.resolve(
            principal_id=self.config.principal_id,
            task_id=task_id,
            operation="memory.import",
            authority=self.authority,
        )
        if decision is None or not self.authority.allows("memory.write"):
            raise PermissionError("legacy import requires memory.import and memory.write")
        imported = 0
        record_ids: list[str] = []
        for item in plan.items:
            if not self.policy.permits(decision, item.record):
                raise PermissionError("legacy import record falls outside configured memory policy")
            result = self.service.put(
                item.record,
                principal_id=self.config.principal_id,
                task_id=task_id,
                authority=self.authority,
                operation_id=item.operation_id,
                transformation_lineage=item.transformation_lineage,
            )
            if result.status != "ok":
                raise RuntimeError(result.error_code or "legacy import failed")
            self.publisher.publish_pending()
            imported += 1
            record_ids.append(item.record.record_id)
        return imported, tuple(record_ids)

    def _semantic_service(self) -> GovernedMemoryService:
        if not self.config.semantic_enabled:
            raise RuntimeError("semantic memory is disabled by operator configuration")
        provider = OllamaEmbeddingProvider(
            endpoint=self.config.ollama_endpoint,
            model=self.config.embedding_model,
            dimensions=self.config.embedding_dimensions,
            expected_digest=self.config.embedding_model_digest,
        )
        identity = provider.identity()
        index = SqliteVecIndex(
            self.state_root / "indexes" / identity.generation_id / "vectors.sqlite3",
            identity=identity,
        )
        return GovernedMemoryService(
            self.store,
            self.policy,
            retrieval_index=index,
            embedding_provider=provider,
            evidence_horizon=self.evidence_horizon,
        )
