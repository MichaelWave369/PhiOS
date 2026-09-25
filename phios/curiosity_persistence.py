"""Governed Curiosity persistence capability for PhiOS.

This module does not mint authority. It exposes one bounded capability,
`curiosity.persist`, whose only declared active effect is `filesystem.change`.
Execution is available only through the existing single-use ActionLease runtime
handoff.

The stored CuriosityArtifact remains zero-authority even when the persistence
operation itself was authorized.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from phios.action_lease import ActionLease
from phios.core.governed_action_binding import PlanActionBinding
from phios.core.governed_plan_adoption import PlanState
from phios.core.leased_execution_handoff import (
    GovernedLeasedExecutionHandoff,
    LeaseVerificationEvidence,
    LeasedExecutionHandoffReceipt,
)
from phios.curiosity import CuriosityArtifact
from phios.curiosity_store import CuriosityStore
from phios.spine.executor import ArtifactResult
from phios.spine.models import Capability
from phios.spine.runtime import PhiOSSpine

CURIOSITY_PERSIST_PAYLOAD_SCHEMA_VERSION = (
    "phios.curiosity_persist_payload.v0.4"
)
CURIOSITY_PERSIST_CAPABILITY_ID = "curiosity.persist"
CURIOSITY_PERSIST_PERMISSION = "curiosity.write"


class CuriosityPersistenceError(ValueError):
    """Raised when a Curiosity persistence request is malformed or unsafe."""


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CuriosityPersistenceError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise CuriosityPersistenceError(
            f"{field} exceeds {maximum} characters"
        )
    return value


def _string_tuple(
    value: object,
    field: str,
    *,
    maximum_items: int = 64,
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise CuriosityPersistenceError(f"{field} must be an array")
    if len(value) > maximum_items:
        raise CuriosityPersistenceError(
            f"{field} exceeds {maximum_items} items"
        )
    result: list[str] = []
    for item in value:
        text = _require_text(item, f"{field} item", maximum=256)
        if text in result:
            raise CuriosityPersistenceError(
                f"{field} must not contain duplicates"
            )
        result.append(text)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class CuriosityPersistPayload:
    artifact_kind: str
    title: str
    content: str
    created_at: str
    created_by: str
    tags: tuple[str, ...] = ()
    evidence_ref_sha256s: tuple[str, ...] = ()
    parent_artifact_sha256s: tuple[str, ...] = ()
    schema_version: str = CURIOSITY_PERSIST_PAYLOAD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CURIOSITY_PERSIST_PAYLOAD_SCHEMA_VERSION:
            raise CuriosityPersistenceError(
                "unsupported Curiosity persistence payload schema"
            )
        _require_text(
            self.artifact_kind,
            "artifact_kind",
            maximum=64,
        )
        _require_text(self.title, "title", maximum=256)
        _require_text(self.content, "content", maximum=65536)
        _require_text(self.created_at, "created_at", maximum=64)
        _require_text(self.created_by, "created_by", maximum=256)

        # CuriosityArtifact performs the canonical kind, timestamp, tag,
        # provenance-hash, and authority validation. The persistence payload
        # itself must already be canonical because ActionLease scope binds the
        # exact payload digest.
        artifact = self.to_artifact()
        if artifact.artifact_kind != self.artifact_kind:
            raise CuriosityPersistenceError(
                "artifact_kind must already be canonical lowercase"
            )
        if artifact.tags != self.tags:
            raise CuriosityPersistenceError(
                "tags must already be sorted, unique, and lowercase"
            )
        if artifact.evidence_ref_sha256s != self.evidence_ref_sha256s:
            raise CuriosityPersistenceError(
                "evidence_ref_sha256s must already be sorted and unique"
            )
        if artifact.parent_artifact_sha256s != self.parent_artifact_sha256s:
            raise CuriosityPersistenceError(
                "parent_artifact_sha256s must already be sorted and unique"
            )

    def to_artifact(self) -> CuriosityArtifact:
        return CuriosityArtifact.build(
            artifact_kind=self.artifact_kind,
            title=self.title,
            content=self.content,
            created_at=self.created_at,
            created_by=self.created_by,
            tags=self.tags,
            evidence_ref_sha256s=self.evidence_ref_sha256s,
            parent_artifact_sha256s=self.parent_artifact_sha256s,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "artifact_kind": self.artifact_kind,
            "title": self.title,
            "content": self.content,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "tags": list(self.tags),
            "evidence_ref_sha256s": list(
                self.evidence_ref_sha256s
            ),
            "parent_artifact_sha256s": list(
                self.parent_artifact_sha256s
            ),
        }

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
    ) -> "CuriosityPersistPayload":
        data = dict(value)
        expected = {
            "schema_version",
            "artifact_kind",
            "title",
            "content",
            "created_at",
            "created_by",
            "tags",
            "evidence_ref_sha256s",
            "parent_artifact_sha256s",
        }
        if set(data) != expected:
            missing = sorted(expected - set(data))
            unknown = sorted(set(data) - expected)
            raise CuriosityPersistenceError(
                "Curiosity persistence payload fields mismatch: "
                f"missing={missing}; unknown={unknown}"
            )
        return cls(
            schema_version=_require_text(
                data["schema_version"],
                "schema_version",
                maximum=64,
            ),
            artifact_kind=_require_text(
                data["artifact_kind"],
                "artifact_kind",
                maximum=64,
            ),
            title=_require_text(
                data["title"],
                "title",
                maximum=256,
            ),
            content=_require_text(
                data["content"],
                "content",
                maximum=65536,
            ),
            created_at=_require_text(
                data["created_at"],
                "created_at",
                maximum=64,
            ),
            created_by=_require_text(
                data["created_by"],
                "created_by",
                maximum=256,
            ),
            tags=_string_tuple(data["tags"], "tags"),
            evidence_ref_sha256s=_string_tuple(
                data["evidence_ref_sha256s"],
                "evidence_ref_sha256s",
            ),
            parent_artifact_sha256s=_string_tuple(
                data["parent_artifact_sha256s"],
                "parent_artifact_sha256s",
            ),
        )


def curiosity_persist_capability() -> Capability:
    return Capability(
        id=CURIOSITY_PERSIST_CAPABILITY_ID,
        name="Persist Curiosity Artifact",
        description=(
            "Append one canonical zero-authority CuriosityArtifact "
            "to the local Curiosity Store."
        ),
        permissions=(CURIOSITY_PERSIST_PERMISSION,),
        effects=("filesystem.change",),
        risk="low",
        version="0.4.0",
    )


class GovernedCuriosityPersistence:
    """Lease-gated Curiosity persistence service.

    This service deliberately does not expose an unleased write method.
    """

    def __init__(
        self,
        *,
        state_root: Path,
        allowed_permissions: Iterable[str] = (),
    ) -> None:
        self.state_root = state_root.expanduser()
        self.store = CuriosityStore(
            self.state_root / "curiosity"
        )
        self._spine = PhiOSSpine(
            state_root=self.state_root,
            allowed_permissions=allowed_permissions,
        )
        self._capability = curiosity_persist_capability()
        self._spine.registry.register(self._capability)
        self._spine.executors.register(
            self._capability.id,
            self._handler,
            effects=("filesystem.change",),
        )
        self._handoff = GovernedLeasedExecutionHandoff()

    @property
    def capability(self) -> Capability:
        return self._capability

    def execute(
        self,
        *,
        plan: PlanState,
        binding: PlanActionBinding,
        payload: Mapping[str, Any],
        lease: ActionLease,
        verification: LeaseVerificationEvidence,
        current_authority_epoch_sha256: str,
        checked_at: str,
    ) -> LeasedExecutionHandoffReceipt:
        candidate = CuriosityPersistPayload.from_mapping(payload)

        if candidate.created_by != lease.principal_id:
            raise CuriosityPersistenceError(
                "created_by must match ActionLease principal_id"
            )
        if binding.capability_id != self._capability.id:
            raise CuriosityPersistenceError(
                "binding is not scoped to curiosity.persist"
            )

        return self._handoff.execute(
            plan=plan,
            binding=binding,
            payload=candidate.to_dict(),
            spine=self._spine,
            lease=lease,
            verification=verification,
            current_authority_epoch_sha256=(
                current_authority_epoch_sha256
            ),
            checked_at=checked_at,
        )

    def _handler(self, payload: dict[str, Any]) -> ArtifactResult:
        candidate = CuriosityPersistPayload.from_mapping(payload)
        artifact = candidate.to_artifact()
        self.store.append_artifact(artifact)

        path = self.store.artifacts_path.resolve()
        if not path.exists():
            raise CuriosityPersistenceError(
                "Curiosity Store did not materialize after persistence"
            )
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return ArtifactResult(path=path, sha256=digest)
