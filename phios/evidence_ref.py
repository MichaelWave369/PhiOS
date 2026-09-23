"""Canonical evidence identity contract for PhiOS.

EvidenceRef binds evidence identity and provenance. It never grants operational,
action, or execution authority, and it does not claim that referenced evidence
is currently admissible merely because it can be named.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

EVIDENCE_REF_SCHEMA_VERSION = "phios.evidence_ref.v0.1"
_EVIDENCE_URI_PREFIX = "evidence:sha256:"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class EvidenceRefContractError(ValueError):
    """Raised when an EvidenceRef violates the canonical contract."""


def _require_text(value: object, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value:
        raise EvidenceRefContractError(f"{field} must be a non-empty string")
    if len(value) > maximum:
        raise EvidenceRefContractError(f"{field} exceeds {maximum} characters")
    if any(ord(char) < 32 for char in value):
        raise EvidenceRefContractError(f"{field} contains control characters")
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise EvidenceRefContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _require_optional_sha256(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _require_sha256(value, field)


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceRefContractError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceRefContractError(
            f"{field} must include a timezone offset"
        )
    return text


def _require_optional_timestamp(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _require_timestamp(value, field)


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    """Immutable evidence reference with explicit zero authority.

    admissibility_receipt_sha256 may bind this identity to an external
    admissibility evaluation. Its presence does not make the evidence currently
    admissible and does not carry authority.
    """

    source_id: str
    source_kind: str
    content_sha256: str
    observed_at: str
    source_version: str | None = None
    created_at: str | None = None
    transformation_lineage_sha256s: tuple[str, ...] = ()
    admissibility_receipt_sha256: str | None = None
    exactness_class: str | None = None
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = EVIDENCE_REF_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != EVIDENCE_REF_SCHEMA_VERSION:
            raise EvidenceRefContractError(
                f"unsupported EvidenceRef schema: {self.schema_version}"
            )
        _require_text(self.source_id, "source_id")
        _require_text(self.source_kind, "source_kind", maximum=64)
        _require_sha256(self.content_sha256, "content_sha256")
        _require_timestamp(self.observed_at, "observed_at")
        if self.source_version is not None:
            _require_text(self.source_version, "source_version", maximum=128)
        _require_optional_timestamp(self.created_at, "created_at")
        if self.created_at is not None:
            created = datetime.fromisoformat(
                self.created_at.replace("Z", "+00:00")
            )
            observed = datetime.fromisoformat(
                self.observed_at.replace("Z", "+00:00")
            )
            if created > observed:
                raise EvidenceRefContractError(
                    "created_at cannot be later than observed_at"
                )
        if len(self.transformation_lineage_sha256s) > 64:
            raise EvidenceRefContractError(
                "transformation_lineage_sha256s exceeds 64 items"
            )
        if tuple(sorted(self.transformation_lineage_sha256s)) != (
            self.transformation_lineage_sha256s
        ):
            raise EvidenceRefContractError(
                "transformation_lineage_sha256s must be sorted"
            )
        if len(set(self.transformation_lineage_sha256s)) != len(
            self.transformation_lineage_sha256s
        ):
            raise EvidenceRefContractError(
                "transformation_lineage_sha256s must not contain duplicates"
            )
        for digest in self.transformation_lineage_sha256s:
            _require_sha256(digest, "transformation lineage digest")
        _require_optional_sha256(
            self.admissibility_receipt_sha256,
            "admissibility_receipt_sha256",
        )
        if self.exactness_class is not None:
            _require_text(self.exactness_class, "exactness_class", maximum=64)
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise EvidenceRefContractError(
                "EvidenceRef cannot carry operational, action, or execution authority"
            )

    @property
    def evidence_ref(self) -> str:
        return f"{_EVIDENCE_URI_PREFIX}{self.content_sha256}"

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_ref": self.evidence_ref,
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "source_version": self.source_version,
            "content_sha256": self.content_sha256,
            "created_at": self.created_at,
            "observed_at": self.observed_at,
            "transformation_lineage_sha256s": list(
                self.transformation_lineage_sha256s
            ),
            "admissibility_receipt_sha256": self.admissibility_receipt_sha256,
            "exactness_class": self.exactness_class,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def reference_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        payload = self.body_dict()
        payload["evidence_ref_sha256"] = self.reference_sha256
        return payload

    @classmethod
    def build(
        cls,
        *,
        source_id: str,
        source_kind: str,
        content_sha256: str,
        observed_at: str,
        source_version: str | None = None,
        created_at: str | None = None,
        transformation_lineage_sha256s: tuple[str, ...] = (),
        admissibility_receipt_sha256: str | None = None,
        exactness_class: str | None = None,
    ) -> "EvidenceRef":
        lineage = tuple(sorted(set(transformation_lineage_sha256s)))
        return cls(
            source_id=source_id,
            source_kind=source_kind,
            content_sha256=content_sha256,
            observed_at=observed_at,
            source_version=source_version,
            created_at=created_at,
            transformation_lineage_sha256s=lineage,
            admissibility_receipt_sha256=admissibility_receipt_sha256,
            exactness_class=exactness_class,
        )

    @classmethod
    def from_dict(cls, value: object) -> "EvidenceRef":
        if not isinstance(value, dict):
            raise EvidenceRefContractError("EvidenceRef must be an object")
        data = dict(value)
        expected = {
            "schema_version",
            "evidence_ref",
            "source_id",
            "source_kind",
            "source_version",
            "content_sha256",
            "created_at",
            "observed_at",
            "transformation_lineage_sha256s",
            "admissibility_receipt_sha256",
            "exactness_class",
            "operational_authority",
            "action_authority",
            "execution_authority",
            "evidence_ref_sha256",
        }
        if set(data) != expected:
            missing = sorted(expected - set(data))
            unknown = sorted(set(data) - expected)
            raise EvidenceRefContractError(
                f"EvidenceRef fields mismatch: missing={missing}; unknown={unknown}"
            )

        lineage_raw = data["transformation_lineage_sha256s"]
        if not isinstance(lineage_raw, list):
            raise EvidenceRefContractError(
                "transformation_lineage_sha256s must be an array"
            )
        lineage = tuple(
            _require_sha256(item, "transformation lineage digest")
            for item in lineage_raw
        )

        for field in (
            "operational_authority",
            "action_authority",
            "execution_authority",
        ):
            if not isinstance(data[field], bool):
                raise EvidenceRefContractError(f"{field} must be Boolean")

        ref = cls(
            schema_version=_require_text(
                data["schema_version"],
                "schema_version",
                maximum=64,
            ),
            source_id=_require_text(data["source_id"], "source_id"),
            source_kind=_require_text(
                data["source_kind"],
                "source_kind",
                maximum=64,
            ),
            source_version=(
                None
                if data["source_version"] is None
                else _require_text(
                    data["source_version"],
                    "source_version",
                    maximum=128,
                )
            ),
            content_sha256=_require_sha256(
                data["content_sha256"],
                "content_sha256",
            ),
            created_at=_require_optional_timestamp(
                data["created_at"],
                "created_at",
            ),
            observed_at=_require_timestamp(
                data["observed_at"],
                "observed_at",
            ),
            transformation_lineage_sha256s=lineage,
            admissibility_receipt_sha256=_require_optional_sha256(
                data["admissibility_receipt_sha256"],
                "admissibility_receipt_sha256",
            ),
            exactness_class=(
                None
                if data["exactness_class"] is None
                else _require_text(
                    data["exactness_class"],
                    "exactness_class",
                    maximum=64,
                )
            ),
            operational_authority=data["operational_authority"],
            action_authority=data["action_authority"],
            execution_authority=data["execution_authority"],
        )

        if data["evidence_ref"] != ref.evidence_ref:
            raise EvidenceRefContractError(
                "evidence_ref does not match content_sha256"
            )
        if data["evidence_ref_sha256"] != ref.reference_sha256:
            raise EvidenceRefContractError(
                "evidence_ref_sha256 does not match canonical EvidenceRef"
            )
        return ref
