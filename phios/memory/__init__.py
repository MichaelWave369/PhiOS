"""Governed canonical memory contracts for PhiOS."""

from .config import MemoryRuntimeConfig
from .embeddings import EmbeddingProvider, OllamaEmbeddingProvider
from .horizon import (
    EvidenceHorizonEvaluation,
    EvidenceHorizonPolicy,
    EvidenceHorizonReceipt,
    MemoryEvidenceHorizon,
    ReactivationWindowReceipt,
    ReconsolidationGate,
    memory_record_ref,
)
from .legacy import LegacyImportPlan, plan_legacy_agent_memory_import
from .models import (
    EmbeddingIdentity,
    IndexSyncResult,
    MemoryAccessDecision,
    MemoryHit,
    MemoryRecord,
    MemoryResult,
    VectorCandidate,
)
from .operator import MemoryOperatorRuntime, MemoryOperatorStatus
from .policy import MemoryAccessPolicy, MemoryPolicyRule
from .publisher import MemoryReceiptPublisher
from .service import GovernedMemoryService, RetrievalIndex, UnavailableRetrievalIndex
from .sqlite_vec_index import SqliteVecIndex
from .store import MemoryStore

__all__ = [
    "EmbeddingIdentity",
    "EmbeddingProvider",
    "EvidenceHorizonEvaluation",
    "EvidenceHorizonPolicy",
    "EvidenceHorizonReceipt",
    "GovernedMemoryService",
    "IndexSyncResult",
    "LegacyImportPlan",
    "MemoryAccessDecision",
    "MemoryAccessPolicy",
    "MemoryHit",
    "MemoryEvidenceHorizon",
    "MemoryOperatorRuntime",
    "MemoryOperatorStatus",
    "MemoryPolicyRule",
    "MemoryRecord",
    "MemoryReceiptPublisher",
    "MemoryResult",
    "MemoryRuntimeConfig",
    "MemoryStore",
    "OllamaEmbeddingProvider",
    "ReactivationWindowReceipt",
    "ReconsolidationGate",
    "RetrievalIndex",
    "SqliteVecIndex",
    "UnavailableRetrievalIndex",
    "VectorCandidate",
    "memory_record_ref",
    "plan_legacy_agent_memory_import",
]
