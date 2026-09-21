"""Core deterministic contracts for PhiOS Covenant Runtime CR-01.

CR-01 describes identity, topology, boundary context, and transition intent.
It does not create authority and it does not execute anything.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, cast

from .zones import TrustZone, require_actor_zone, require_transition

BOUNDARY_CONTEXT_SCHEMA_VERSION = "phios.boundary_context.v0.1"
BOUNDARY_TRANSITION_REQUEST_SCHEMA_VERSION = "phios.boundary_transition_request.v0.1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def expect_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, Any], value)


def expect_exact_keys(data: dict[str, Any], expected: set[str], label: str) -> None:
    if set(data) != expected:
        missing = sorted(expected - set(data))
        unknown = sorted(set(data) - expected)
        details: list[str] = []
        if missing:
            details.append(f"missing={','.join(missing)}")
        if unknown:
            details.append(f"unknown={','.join(unknown)}")
        suffix = f": {'; '.join(details)}" if details else ""
        raise ValueError(f"{label} contains missing or unknown fields{suffix}")


def require_text(value: Any, label: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    if len(value) > maximum:
        raise ValueError(f"{label} exceeds {maximum} characters")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"{label} contains control characters")
    return value


def require_sha256(value: Any, label: str) -> str:
    text = require_text(value, label, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return text


def require_optional_sha256(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return require_sha256(value, label)


def require_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be Boolean")
    return value


def require_string_tuple(
    value: Any,
    label: str,
    *,
    maximum_items: int = 64,
    maximum_text: int = 256,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    if len(value) > maximum_items:
        raise ValueError(f"{label} exceeds {maximum_items} items")
    result = tuple(
        require_text(item, f"{label} item", maximum=maximum_text) for item in value
    )
    if len(set(result)) != len(result):
        raise ValueError(f"{label} must not contain duplicates")
    if tuple(sorted(result)) != result:
        raise ValueError(f"{label} must be sorted")
    return result


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_sha256(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class BoundaryContext:
    """Describe the current actor boundary state without granting authority."""

    zone: TrustZone
    identity_seal_sha256: str
    execution_circle_sha256: str | None = None
    previous_transition_receipt_sha256: str | None = None
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = BOUNDARY_CONTEXT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != BOUNDARY_CONTEXT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported boundary context schema: {self.schema_version}")
        require_actor_zone(self.zone)
        require_sha256(self.identity_seal_sha256, "identity_seal_sha256")
        require_optional_sha256(self.execution_circle_sha256, "execution_circle_sha256")
        require_optional_sha256(
            self.previous_transition_receipt_sha256,
            "previous_transition_receipt_sha256",
        )
        if self.action_authority is not False or self.execution_authority is not False:
            raise ValueError("boundary context cannot carry action or execution authority")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "zone": self.zone.value,
            "identity_seal_sha256": self.identity_seal_sha256,
            "execution_circle_sha256": self.execution_circle_sha256,
            "previous_transition_receipt_sha256": self.previous_transition_receipt_sha256,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    def sha256(self) -> str:
        return canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["boundary_context_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> BoundaryContext:
        data = expect_mapping(value, "boundary context")
        expected = {
            "schema_version",
            "zone",
            "identity_seal_sha256",
            "execution_circle_sha256",
            "previous_transition_receipt_sha256",
            "action_authority",
            "execution_authority",
            "boundary_context_sha256",
        }
        expect_exact_keys(data, expected, "boundary context")
        try:
            zone = TrustZone(require_text(data["zone"], "zone", maximum=32))
        except ValueError as exc:
            raise ValueError(f"Unsupported trust zone: {data['zone']}") from exc
        context = cls(
            schema_version=require_text(
                data["schema_version"],
                "schema_version",
                maximum=64,
            ),
            zone=zone,
            identity_seal_sha256=require_sha256(
                data["identity_seal_sha256"],
                "identity_seal_sha256",
            ),
            execution_circle_sha256=require_optional_sha256(
                data["execution_circle_sha256"],
                "execution_circle_sha256",
            ),
            previous_transition_receipt_sha256=require_optional_sha256(
                data["previous_transition_receipt_sha256"],
                "previous_transition_receipt_sha256",
            ),
            action_authority=require_bool(
                data["action_authority"],
                "action_authority",
            ),
            execution_authority=require_bool(
                data["execution_authority"],
                "execution_authority",
            ),
        )
        if data["boundary_context_sha256"] != context.sha256():
            raise ValueError("boundary context digest does not match canonical context")
        return context


@dataclass(frozen=True, slots=True)
class BoundaryTransitionRequest:
    """Describe one proposed actor-zone crossing with zero authority."""

    source_zone: TrustZone
    target_zone: TrustZone
    subject_seal_sha256: str
    evidence_refs: tuple[str, ...] = ()
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = BOUNDARY_TRANSITION_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != BOUNDARY_TRANSITION_REQUEST_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported boundary transition request schema: {self.schema_version}"
            )
        require_actor_zone(self.source_zone)
        require_actor_zone(self.target_zone)
        require_transition(self.source_zone, self.target_zone)
        require_sha256(self.subject_seal_sha256, "subject_seal_sha256")
        if len(self.evidence_refs) > 64:
            raise ValueError("evidence_refs exceeds 64 items")
        if tuple(sorted(self.evidence_refs)) != self.evidence_refs:
            raise ValueError("evidence_refs must be sorted")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("evidence_refs must not contain duplicates")
        for item in self.evidence_refs:
            require_text(item, "evidence reference", maximum=256)
        if self.action_authority is not False or self.execution_authority is not False:
            raise ValueError(
                "boundary transition request cannot carry action or execution authority"
            )

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_zone": self.source_zone.value,
            "target_zone": self.target_zone.value,
            "subject_seal_sha256": self.subject_seal_sha256,
            "evidence_refs": list(self.evidence_refs),
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    def sha256(self) -> str:
        return canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["boundary_transition_request_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> BoundaryTransitionRequest:
        data = expect_mapping(value, "boundary transition request")
        expected = {
            "schema_version",
            "source_zone",
            "target_zone",
            "subject_seal_sha256",
            "evidence_refs",
            "action_authority",
            "execution_authority",
            "boundary_transition_request_sha256",
        }
        expect_exact_keys(data, expected, "boundary transition request")
        try:
            source_zone = TrustZone(
                require_text(data["source_zone"], "source_zone", maximum=32)
            )
            target_zone = TrustZone(
                require_text(data["target_zone"], "target_zone", maximum=32)
            )
        except ValueError as exc:
            raise ValueError("boundary transition request contains unsupported zone") from exc
        request = cls(
            schema_version=require_text(
                data["schema_version"],
                "schema_version",
                maximum=64,
            ),
            source_zone=source_zone,
            target_zone=target_zone,
            subject_seal_sha256=require_sha256(
                data["subject_seal_sha256"],
                "subject_seal_sha256",
            ),
            evidence_refs=require_string_tuple(data["evidence_refs"], "evidence_refs"),
            action_authority=require_bool(
                data["action_authority"],
                "action_authority",
            ),
            execution_authority=require_bool(
                data["execution_authority"],
                "execution_authority",
            ),
        )
        if data["boundary_transition_request_sha256"] != request.sha256():
            raise ValueError(
                "boundary transition request digest does not match canonical request"
            )
        return request
