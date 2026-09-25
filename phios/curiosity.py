"""Zero-authority curiosity and symbolic exploration contracts for PhiOS.

The curiosity lane preserves symbols, metaphors, questions, hypotheses,
associations, dream fragments, patterns, and creative seeds without promoting
them into factual, operational, action, or execution authority.

A CuriosityArtifact may be meaningful without being verified. Promotion into a
different PhiOS lane always requires an explicit CuriosityPromotionRequest and
the destination lane's own admission/governance process.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

CURIOSITY_ARTIFACT_SCHEMA_VERSION = "phios.curiosity_artifact.v0.1"
CURIOSITY_PROMOTION_SCHEMA_VERSION = "phios.curiosity_promotion_request.v0.1"

CURIOSITY_KINDS = (
    "association",
    "creative_seed",
    "dream_fragment",
    "hypothesis",
    "metaphor",
    "pattern",
    "question",
    "symbol",
)

PROMOTION_TARGETS = (
    "build",
    "ledger_review",
    "research",
)

_CLAIM_CLASS_BY_KIND = {
    "association": "unverified_association",
    "creative_seed": "non_claim",
    "dream_fragment": "non_claim",
    "hypothesis": "hypothesis",
    "metaphor": "non_claim",
    "pattern": "unverified_association",
    "question": "open_question",
    "symbol": "non_claim",
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class CuriosityContractError(ValueError):
    """Raised when a curiosity-lane contract is malformed."""


def _require_text(value: object, field: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CuriosityContractError(f"{field} must be a non-empty string")
    if len(value) > maximum:
        raise CuriosityContractError(f"{field} exceeds {maximum} characters")
    if any(ord(char) < 32 and char not in "\n\t" for char in value):
        raise CuriosityContractError(f"{field} contains unsupported control characters")
    return value


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CuriosityContractError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CuriosityContractError(f"{field} must include a timezone offset")
    return text


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise CuriosityContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _canonical_json(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            dict(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise CuriosityContractError(
            "curiosity payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_canonical_text_tuple(
    values: tuple[str, ...],
    field: str,
    *,
    maximum_items: int = 64,
) -> None:
    if len(values) > maximum_items:
        raise CuriosityContractError(
            f"{field} exceeds {maximum_items} items"
        )
    if tuple(sorted(values)) != values:
        raise CuriosityContractError(f"{field} must be sorted")
    if len(set(values)) != len(values):
        raise CuriosityContractError(f"{field} must not contain duplicates")
    for value in values:
        _require_text(value, f"{field} item", maximum=128)


def _require_canonical_sha_tuple(
    values: tuple[str, ...],
    field: str,
) -> None:
    if len(values) > 64:
        raise CuriosityContractError(f"{field} exceeds 64 items")
    if tuple(sorted(values)) != values:
        raise CuriosityContractError(f"{field} must be sorted")
    if len(set(values)) != len(values):
        raise CuriosityContractError(f"{field} must not contain duplicates")
    for value in values:
        _require_sha256(value, f"{field} item")


@dataclass(frozen=True, slots=True)
class CuriosityArtifact:
    """Immutable curiosity-lane artifact with explicit zero authority."""

    artifact_kind: str
    title: str
    content: str
    created_at: str
    created_by: str
    tags: tuple[str, ...] = ()
    evidence_ref_sha256s: tuple[str, ...] = ()
    parent_artifact_sha256s: tuple[str, ...] = ()
    effect_performed: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = CURIOSITY_ARTIFACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CURIOSITY_ARTIFACT_SCHEMA_VERSION:
            raise CuriosityContractError(
                f"unsupported CuriosityArtifact schema: {self.schema_version}"
            )
        if self.artifact_kind not in CURIOSITY_KINDS:
            raise CuriosityContractError(
                f"unsupported curiosity artifact kind: {self.artifact_kind}"
            )
        _require_text(self.title, "title", maximum=256)
        _require_text(self.content, "content", maximum=65536)
        _require_timestamp(self.created_at, "created_at")
        _require_text(self.created_by, "created_by", maximum=256)
        _require_canonical_text_tuple(self.tags, "tags")
        _require_canonical_sha_tuple(
            self.evidence_ref_sha256s,
            "evidence_ref_sha256s",
        )
        _require_canonical_sha_tuple(
            self.parent_artifact_sha256s,
            "parent_artifact_sha256s",
        )

        if self.effect_performed is not False:
            raise CuriosityContractError(
                "CuriosityArtifact cannot claim that an effect was performed"
            )
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise CuriosityContractError(
                "CuriosityArtifact cannot carry operational, action, "
                "or execution authority"
            )

    @property
    def lane(self) -> str:
        return "curiosity"

    @property
    def claim_class(self) -> str:
        return _CLAIM_CLASS_BY_KIND[self.artifact_kind]

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "lane": self.lane,
            "artifact_kind": self.artifact_kind,
            "claim_class": self.claim_class,
            "title": self.title,
            "content": self.content,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "tags": list(self.tags),
            "evidence_ref_sha256s": list(self.evidence_ref_sha256s),
            "parent_artifact_sha256s": list(
                self.parent_artifact_sha256s
            ),
            "effect_performed": self.effect_performed,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def curiosity_artifact_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        payload = self.body_dict()
        payload["curiosity_artifact_sha256"] = (
            self.curiosity_artifact_sha256
        )
        return payload

    @classmethod
    def build(
        cls,
        *,
        artifact_kind: str,
        title: str,
        content: str,
        created_at: str,
        created_by: str,
        tags: tuple[str, ...] = (),
        evidence_ref_sha256s: tuple[str, ...] = (),
        parent_artifact_sha256s: tuple[str, ...] = (),
    ) -> "CuriosityArtifact":
        canonical_tags = tuple(
            sorted({tag.strip().lower() for tag in tags if tag.strip()})
        )
        evidence_refs = tuple(sorted(set(evidence_ref_sha256s)))
        parent_refs = tuple(sorted(set(parent_artifact_sha256s)))
        return cls(
            artifact_kind=artifact_kind.strip().lower(),
            title=title,
            content=content,
            created_at=created_at,
            created_by=created_by,
            tags=canonical_tags,
            evidence_ref_sha256s=evidence_refs,
            parent_artifact_sha256s=parent_refs,
        )

    @classmethod
    def from_dict(cls, value: object) -> "CuriosityArtifact":
        if not isinstance(value, dict):
            raise CuriosityContractError(
                "CuriosityArtifact must be an object"
            )
        data = dict(value)
        expected = {
            "schema_version",
            "lane",
            "artifact_kind",
            "claim_class",
            "title",
            "content",
            "created_at",
            "created_by",
            "tags",
            "evidence_ref_sha256s",
            "parent_artifact_sha256s",
            "effect_performed",
            "operational_authority",
            "action_authority",
            "execution_authority",
            "curiosity_artifact_sha256",
        }
        if set(data) != expected:
            missing = sorted(expected - set(data))
            unknown = sorted(set(data) - expected)
            raise CuriosityContractError(
                f"CuriosityArtifact fields mismatch: "
                f"missing={missing}; unknown={unknown}"
            )

        tuple_fields = (
            "tags",
            "evidence_ref_sha256s",
            "parent_artifact_sha256s",
        )
        parsed: dict[str, tuple[str, ...]] = {}
        for field in tuple_fields:
            raw = data[field]
            if not isinstance(raw, list):
                raise CuriosityContractError(
                    f"{field} must be an array"
                )
            parsed[field] = tuple(raw)

        for field in (
            "effect_performed",
            "operational_authority",
            "action_authority",
            "execution_authority",
        ):
            if not isinstance(data[field], bool):
                raise CuriosityContractError(
                    f"{field} must be Boolean"
                )

        artifact = cls(
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
            title=_require_text(data["title"], "title", maximum=256),
            content=_require_text(
                data["content"],
                "content",
                maximum=65536,
            ),
            created_at=_require_timestamp(
                data["created_at"],
                "created_at",
            ),
            created_by=_require_text(
                data["created_by"],
                "created_by",
                maximum=256,
            ),
            tags=parsed["tags"],
            evidence_ref_sha256s=parsed["evidence_ref_sha256s"],
            parent_artifact_sha256s=parsed[
                "parent_artifact_sha256s"
            ],
            effect_performed=data["effect_performed"],
            operational_authority=data["operational_authority"],
            action_authority=data["action_authority"],
            execution_authority=data["execution_authority"],
        )

        if data["lane"] != artifact.lane:
            raise CuriosityContractError(
                "lane must remain curiosity"
            )
        if data["claim_class"] != artifact.claim_class:
            raise CuriosityContractError(
                "claim_class does not match artifact_kind"
            )
        if (
            data["curiosity_artifact_sha256"]
            != artifact.curiosity_artifact_sha256
        ):
            raise CuriosityContractError(
                "curiosity_artifact_sha256 does not match canonical artifact"
            )
        return artifact


@dataclass(frozen=True, slots=True)
class CuriosityPromotionRequest:
    """Explicit request to offer a curiosity artifact to another lane.

    This is only a proposal. It does not itself promote the artifact and carries
    no operational, action, or execution authority.
    """

    artifact_sha256: str
    target_lane: str
    requested_at: str
    requested_by: str
    rationale: str
    evidence_ref_sha256s: tuple[str, ...] = ()
    effect_performed: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = CURIOSITY_PROMOTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CURIOSITY_PROMOTION_SCHEMA_VERSION:
            raise CuriosityContractError(
                "unsupported CuriosityPromotionRequest schema"
            )
        _require_sha256(self.artifact_sha256, "artifact_sha256")
        if self.target_lane not in PROMOTION_TARGETS:
            raise CuriosityContractError(
                f"unsupported promotion target: {self.target_lane}"
            )
        _require_timestamp(self.requested_at, "requested_at")
        _require_text(
            self.requested_by,
            "requested_by",
            maximum=256,
        )
        _require_text(self.rationale, "rationale", maximum=4096)
        _require_canonical_sha_tuple(
            self.evidence_ref_sha256s,
            "evidence_ref_sha256s",
        )

        if self.effect_performed is not False:
            raise CuriosityContractError(
                "CuriosityPromotionRequest cannot claim an effect"
            )
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise CuriosityContractError(
                "CuriosityPromotionRequest cannot carry operational, "
                "action, or execution authority"
            )

    @property
    def request_status(self) -> str:
        return "proposal_only"

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_sha256": self.artifact_sha256,
            "target_lane": self.target_lane,
            "requested_at": self.requested_at,
            "requested_by": self.requested_by,
            "rationale": self.rationale,
            "evidence_ref_sha256s": list(self.evidence_ref_sha256s),
            "request_status": self.request_status,
            "effect_performed": self.effect_performed,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def promotion_request_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        payload = self.body_dict()
        payload["promotion_request_sha256"] = (
            self.promotion_request_sha256
        )
        return payload

    @classmethod
    def build(
        cls,
        *,
        artifact_sha256: str,
        target_lane: str,
        requested_at: str,
        requested_by: str,
        rationale: str,
        evidence_ref_sha256s: tuple[str, ...] = (),
    ) -> "CuriosityPromotionRequest":
        return cls(
            artifact_sha256=artifact_sha256,
            target_lane=target_lane.strip().lower(),
            requested_at=requested_at,
            requested_by=requested_by,
            rationale=rationale,
            evidence_ref_sha256s=tuple(
                sorted(set(evidence_ref_sha256s))
            ),
        )

    @classmethod
    def from_dict(
        cls,
        value: object,
    ) -> "CuriosityPromotionRequest":
        if not isinstance(value, dict):
            raise CuriosityContractError(
                "CuriosityPromotionRequest must be an object"
            )
        data = dict(value)
        expected = {
            "schema_version",
            "artifact_sha256",
            "target_lane",
            "requested_at",
            "requested_by",
            "rationale",
            "evidence_ref_sha256s",
            "request_status",
            "effect_performed",
            "operational_authority",
            "action_authority",
            "execution_authority",
            "promotion_request_sha256",
        }
        if set(data) != expected:
            missing = sorted(expected - set(data))
            unknown = sorted(set(data) - expected)
            raise CuriosityContractError(
                f"CuriosityPromotionRequest fields mismatch: "
                f"missing={missing}; unknown={unknown}"
            )

        evidence_raw = data["evidence_ref_sha256s"]
        if not isinstance(evidence_raw, list):
            raise CuriosityContractError(
                "evidence_ref_sha256s must be an array"
            )

        for field in (
            "effect_performed",
            "operational_authority",
            "action_authority",
            "execution_authority",
        ):
            if not isinstance(data[field], bool):
                raise CuriosityContractError(
                    f"{field} must be Boolean"
                )

        request = cls(
            schema_version=_require_text(
                data["schema_version"],
                "schema_version",
                maximum=64,
            ),
            artifact_sha256=_require_sha256(
                data["artifact_sha256"],
                "artifact_sha256",
            ),
            target_lane=_require_text(
                data["target_lane"],
                "target_lane",
                maximum=64,
            ),
            requested_at=_require_timestamp(
                data["requested_at"],
                "requested_at",
            ),
            requested_by=_require_text(
                data["requested_by"],
                "requested_by",
                maximum=256,
            ),
            rationale=_require_text(
                data["rationale"],
                "rationale",
                maximum=4096,
            ),
            evidence_ref_sha256s=tuple(evidence_raw),
            effect_performed=data["effect_performed"],
            operational_authority=data["operational_authority"],
            action_authority=data["action_authority"],
            execution_authority=data["execution_authority"],
        )

        if data["request_status"] != request.request_status:
            raise CuriosityContractError(
                "request_status must remain proposal_only"
            )
        if (
            data["promotion_request_sha256"]
            != request.promotion_request_sha256
        ):
            raise CuriosityContractError(
                "promotion_request_sha256 does not match canonical request"
            )
        return request
