from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Literal

from phios.mandala import OriginKind

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
        contradicts = tuple(require_nonempty(v, "contradicts") for v in contradicts)
        if epistemic_kind == "derived" and not derived_from:
            raise ValueError("derived records require derived_from references")
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
            "contradicts": list(contradicts),
            "text": text,
            "content_sha256": content_sha256,
        }
        return cls(**body, record_sha256=sha256_json(body))

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
class MemoryResult:
    status: Literal["ok", "blocked", "unavailable", "invalid"]
    record: MemoryRecord | None = None
    error_code: str | None = None
