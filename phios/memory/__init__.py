"""Governed canonical memory contracts for PhiOS."""

from .embeddings import EmbeddingProvider, OllamaEmbeddingProvider
from .models import (
    EmbeddingIdentity,
    IndexSyncResult,
    MemoryAccessDecision,
    MemoryHit,
    MemoryRecord,
    MemoryResult,
    VectorCandidate,
)
from .policy import MemoryAccessPolicy, MemoryPolicyRule
from .service import GovernedMemoryService, RetrievalIndex, UnavailableRetrievalIndex
from .sqlite_vec_index import SqliteVecIndex
from .store import MemoryStore

__all__ = [
    "EmbeddingIdentity",
    "EmbeddingProvider",
    "GovernedMemoryService",
    "IndexSyncResult",
    "MemoryAccessDecision",
    "MemoryAccessPolicy",
    "MemoryHit",
    "MemoryPolicyRule",
    "MemoryRecord",
    "MemoryResult",
    "MemoryStore",
    "OllamaEmbeddingProvider",
    "RetrievalIndex",
    "SqliteVecIndex",
    "UnavailableRetrievalIndex",
    "VectorCandidate",
]
