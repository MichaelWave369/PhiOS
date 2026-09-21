"""Governed canonical memory contracts for PhiOS."""

from .config import MemoryRuntimeConfig
from .embeddings import EmbeddingProvider, OllamaEmbeddingProvider
from .horizon import (
    EVIDENCE_HORIZON_POLICY_SCHEMA_VERSION,
    EVIDENCE_HORIZON_RECEIPT_SCHEMA_VERSION,
    REACTIVATION_WINDOW_RECEIPT_SCHEMA_VERSION,
    RECONSOLIDATION_GATE_SCHEMA_VERSION,
    EvidenceHorizonController,
    EvidenceHorizonError,
    EvidenceHorizonEvaluation,
    EvidenceHorizonPolicy,
    EvidenceHorizonReceipt,
    ReactivationWindowReceipt,
    ReconsolidationGate,
    ReconsolidationGateDecision,
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
    "EVIDENCE_HORIZON_POLICY_SCHEMA_VERSION",
    "EVIDENCE_HORIZON_RECEIPT_SCHEMA_VERSION",
    "EmbeddingIdentity",
    "EvidenceHorizonController",
    "EvidenceHorizonError",
    "EvidenceHorizonEvaluation",
    "EvidenceHorizonPolicy",
    "EvidenceHorizonReceipt",
    "EmbeddingProvider",
    "GovernedMemoryService",
    "IndexSyncResult",
    "LegacyImportPlan",
    "MemoryAccessDecision",
    "MemoryAccessPolicy",
    "MemoryHit",
    "MemoryOperatorRuntime",
    "MemoryOperatorStatus",
    "MemoryPolicyRule",
    "MemoryRecord",
    "MemoryReceiptPublisher",
    "MemoryResult",
    "MemoryRuntimeConfig",
    "MemoryStore",
    "REACTIVATION_WINDOW_RECEIPT_SCHEMA_VERSION",
    "RECONSOLIDATION_GATE_SCHEMA_VERSION",
    "ReactivationWindowReceipt",
    "ReconsolidationGate",
    "ReconsolidationGateDecision",
    "OllamaEmbeddingProvider",
    "RetrievalIndex",
    "SqliteVecIndex",
    "UnavailableRetrievalIndex",
    "VectorCandidate",
    "plan_legacy_agent_memory_import",
]
