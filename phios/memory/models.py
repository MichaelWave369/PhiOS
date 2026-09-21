from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .horizon import EvidenceHorizonReceipt, ReactivationWindowReceipt

from phios.mandala import ExactnessClass, OriginKind, ReadAdmissibilityReceipt

from .validation import require_nonempty, require_utc_timestamp, sha256_json, validate_text

EpistemicKind = Literal["source", "derived"]


@dataclass(frozen=True, kw_only=True)
class MemoryRecord:
    record_id: str
    revision: int
    source_id: str
    source_kind: str
    provenance_refs: tuple[str, ...]
    created_at: str
    scope_id: str
    classification: str
    retention_policy_id: str
    expires_at: str | None
    epistemic_kind: EpistemicKind
    derived_from: tuple[str, ...] = field(default_factory=tuple)
    exactness_class: str | None = None
    transformation_lineage_sha256s: tuple[str, ...] = field(default_factory=tuple)
    taint_labels: tuple[str, ...] = field(default_factory=tuple)
    contradicts: tuple[str, ...] = field(default_factory=tuple)
    text: str
    content_sha256: str
    record_sha256: str

    @classmethod
    def build(
        cls,
        *,
        record_id: str,
        revision: int,
        source_id: str,
        source_kind: str,
        provenance_refs: tuple[str, ...],
        created_at: str,
        scope_id: str,
        classification: str,
        retention_policy_id: str,
        expires_at: str | None,
        epistemic_kind: EpistemicKind,
        text: str,
        derived_from: tuple[str, ...] = (),
        exactness_class: str | None = None,
        transformation_lineage_sha256s: tuple[str, ...] = (),
        taint_labels: tuple[str, ...] = (),
        contradicts: tuple[str, ...] = (),
    ) -> "MemoryRecord":
        record_id = require_nonempty(record_id, "record_id")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise ValueError("revision must be an integer >= 1")
        source_id = require_nonempty(source_id, "source_id")
        try:
            source_kind = OriginKind(source_kind).value
        except ValueError as exc:
            raise ValueError("source_kind must be a canonical OriginKind") from exc
        created_at = require_utc_timestamp(created_at, "created_at")
        scope_id = require_nonempty(scope_id, "scope_id")
        classification = require_nonempty(classification, "classification")
        retention_policy_id = require_nonempty(retention_policy_id, "retention_policy_id")
        expires_at = require_utc_timestamp(expires_at, "expires_at") if expires_at else None
        if epistemic_kind not in ("source", "derived"):
            raise ValueError("epistemic_kind must be 'source' or 'derived'")
        text = validate_text(text)
        provenance_refs = tuple(require_nonempty(v, "provenance_ref") for v in provenance_refs)
        derived_from = tuple(require_nonempty(v, "derived_from") for v in derived_from)
        lineage_hashes = tuple(
            require_nonempty(v, "transformation_lineage_sha256")
            for v in transformation_lineage_sha256s
        )
        for digest in lineage_hashes:
            if len(digest) != 64:
                raise ValueError(
                    "transformation_lineage_sha256 must be a SHA-256 hex digest"
                )
            try:
                int(digest, 16)
            except ValueError as exc:
                raise ValueError(
                    "transformation_lineage_sha256 must be a SHA-256 hex digest"
                ) from exc
        if len(set(lineage_hashes)) != len(lineage_hashes):
            raise ValueError("transformation lineage hashes must be unique")
        taint_labels = tuple(
            sorted({require_nonempty(v, "taint_label") for v in taint_labels})
        )
        contradicts = tuple(require_nonempty(v, "contradicts") for v in contradicts)
        if epistemic_kind == "derived":
            if not derived_from:
                raise ValueError("derived records require derived_from references")
            if exactness_class is None:
                raise ValueError("derived records require exactness_class")
            try:
                exactness_class = ExactnessClass(exactness_class).value
            except ValueError as exc:
                raise ValueError("invalid exactness_class") from exc
            if not lineage_hashes:
                raise ValueError(
                    "derived records require transformation lineage hashes"
                )
        else:
            if exactness_class is not None:
                raise ValueError("source records cannot declare derived exactness")
            if lineage_hashes:
                raise ValueError(
                    "source records cannot declare transformation lineage hashes"
                )
            if taint_labels:
                raise ValueError("source records cannot declare transformation taints")
        content_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        body = {
            "record_id": record_id,
            "revision": revision,
            "source_id": source_id,
            "source_kind": source_kind,
            "provenance_refs": list(provenance_refs),
            "created_at": created_at,
            "scope_id": scope_id,
            "classification": classification,
            "retention_policy_id": retention_policy_id,
            "expires_at": expires_at,
            "epistemic_kind": epistemic_kind,
            "derived_from": list(derived_from),
            "exactness_class": exactness_class,
            "transformation_lineage_sha256s": list(lineage_hashes),
            "taint_labels": list(taint_labels),
            "contradicts": list(contradicts),
            "text": text,
            "content_sha256": content_sha256,
        }
        return cls(
            record_id=record_id,
            revision=revision,
            source_id=source_id,
            source_kind=source_kind,
            provenance_refs=provenance_refs,
            created_at=created_at,
            scope_id=scope_id,
            classification=classification,
            retention_policy_id=retention_policy_id,
            expires_at=expires_at,
            epistemic_kind=epistemic_kind,
            derived_from=derived_from,
            exactness_class=exactness_class,
            transformation_lineage_sha256s=lineage_hashes,
            taint_labels=taint_labels,
            contradicts=contradicts,
            text=text,
            content_sha256=content_sha256,
            record_sha256=sha256_json(body),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "revision": self.revision,
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "provenance_refs": list(self.provenance_refs),
            "created_at": self.created_at,
            "scope_id": self.scope_id,
            "classification": self.classification,
            "retention_policy_id": self.retention_policy_id,
            "expires_at": self.expires_at,
            "epistemic_kind": self.epistemic_kind,
            "derived_from": list(self.derived_from),
            "exactness_class": self.exactness_class,
            "transformation_lineage_sha256s": list(
                self.transformation_lineage_sha256s
            ),
            "taint_labels": list(self.taint_labels),
            "contradicts": list(self.contradicts),
            "text": self.text,
            "content_sha256": self.content_sha256,
            "record_sha256": self.record_sha256,
        }


@dataclass(frozen=True, kw_only=True)
class MemoryAccessDecision:
    principal_id: str
    task_id: str
    operation: str
    allowed_scopes: tuple[str, ...]
    allowed_classifications: tuple[str, ...]
    policy_sha256: str
    expires_at: str | None = None


@dataclass(frozen=True, kw_only=True)
class EmbeddingIdentity:
    provider: str
    provider_version: str
    model: str
    model_digest: str
    dimensions: int
    preprocessing_version: str = "text-v1"
    metric: Literal["l2"] = "l2"

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "provider_version": self.provider_version,
            "model": self.model,
            "model_digest": self.model_digest,
            "dimensions": self.dimensions,
            "preprocessing_version": self.preprocessing_version,
            "metric": self.metric,
        }

    @property
    def generation_id(self) -> str:
        return sha256_json(self.to_dict())


@dataclass(frozen=True, kw_only=True)
class VectorCandidate:
    record_id: str
    revision: int
    record_sha256: str
    retrieval_distance: float


@dataclass(frozen=True, kw_only=True)
class MemoryHit:
    record: MemoryRecord
    retrieval_distance: float


@dataclass(frozen=True, kw_only=True)
class IndexSyncResult:
    status: Literal["ok", "unavailable", "degraded"]
    processed: int = 0
    indexed: int = 0
    removed: int = 0
    stale: int = 0
    error_code: str | None = None


@dataclass(frozen=True, kw_only=True)
class MemoryResult:
    status: Literal["ok", "blocked", "unavailable", "invalid", "degraded"]
    record: MemoryRecord | None = None
    hits: tuple[MemoryHit, ...] = field(default_factory=tuple)
    read_admissibility_receipts: tuple[ReadAdmissibilityReceipt, ...] = field(
        default_factory=tuple
    )
    evidence_horizon_receipts: tuple["EvidenceHorizonReceipt", ...] = field(
        default_factory=tuple
    )
    reactivation_window_receipts: tuple["ReactivationWindowReceipt", ...] = field(
        default_factory=tuple
    )
    receipt_id: str | None = None
    error_code: str | None = None
