"""Ghost-Walk pre-lease trust state and ActionLease issuance for Macro Runtime v0.34.

This module consumes one exact current GhostWalkExecutableBinding and constructs
an explicit pre-lease trust state from a server-owned lease policy plus a
current AuthorityEpoch. It may issue one bounded ActionLease when every
precondition passes. It does not execute the leased effect.

Core boundary:

    EXECUTABLE BINDING != ENFORCEMENT PROFILE != AUTHORITY EPOCH
    != ACTION LEASE != EXECUTION

The browser/model cannot supply a policy, permission set, enforcement map,
authority epoch, lease duration, or accepted unenforced effects. Those are
owned by trusted local runtime configuration/providers.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Callable, Mapping, Protocol

from phios.action_lease import ActionLease, ActionLeaseContractError
from phios.authority_epoch import AuthorityEpoch, AuthorityEpochContractError
from phios.enforcement_profile import (
    EnforcementProfile,
    EnforcementProfileContractError,
    EnforcementRule,
)
from phios.macro_capability_binding import (
    GhostWalkBindingReadinessReason,
    GhostWalkCapabilityBindingError,
    GhostWalkExecutableBinding,
)
from phios.spine.ledger import RealityLedger

GHOSTWALK_LEASE_POLICY_SCHEMA_VERSION = "phios.ghostwalk_lease_policy.v0.34"
GHOSTWALK_LEASE_READINESS_SCHEMA_VERSION = "phios.ghostwalk_lease_readiness.v0.34"
GHOSTWALK_ACTION_LEASE_RECORD_SCHEMA_VERSION = "phios.ghostwalk_action_lease_record.v0.34"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_POLICY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")


class GhostWalkActionLeaseError(ValueError):
    """Raised when Ghost-Walk lease state cannot be trusted."""


class GhostWalkLeaseReadinessReason(StrEnum):
    READY = "READY"
    EXECUTABLE_BINDING_REQUIRED = "EXECUTABLE_BINDING_REQUIRED"
    EXECUTABLE_BINDING_STALE = "EXECUTABLE_BINDING_STALE"
    LEASE_POLICY_MISSING = "LEASE_POLICY_MISSING"
    ENFORCEMENT_PROFILE_INCOMPLETE = "ENFORCEMENT_PROFILE_INCOMPLETE"
    UNENFORCED_EFFECT_ACK_REQUIRED = "UNENFORCED_EFFECT_ACK_REQUIRED"
    AUTHORITY_EPOCH_UNAVAILABLE = "AUTHORITY_EPOCH_UNAVAILABLE"
    AUTHORITY_EPOCH_STALE = "AUTHORITY_EPOCH_STALE"
    AUTHORITY_PRINCIPAL_MISMATCH = "AUTHORITY_PRINCIPAL_MISMATCH"
    AUTHORITY_PERMISSION_MISSING = "AUTHORITY_PERMISSION_MISSING"
    LEASE_ALREADY_EXISTS = "LEASE_ALREADY_EXISTS"


def _require_text(value: object, field: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value:
        raise GhostWalkActionLeaseError(f"{field} must be a non-empty string")
    if len(value) > maximum:
        raise GhostWalkActionLeaseError(f"{field} exceeds {maximum} characters")
    if any(ord(char) < 32 for char in value):
        raise GhostWalkActionLeaseError(f"{field} contains control characters")
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise GhostWalkActionLeaseError(f"{field} must be a lowercase SHA-256 digest")
    return text


def _optional_sha256(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _require_sha256(value, field)


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise GhostWalkActionLeaseError("lease payload must be canonical JSON") from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _parse_time(value: object, field: str) -> datetime:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GhostWalkActionLeaseError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GhostWalkActionLeaseError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def _canonical_time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise GhostWalkActionLeaseError("lease clock must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def _text_tuple(values: tuple[str, ...], field: str) -> tuple[str, ...]:
    normalized = tuple(_require_text(item, f"{field} item", maximum=256) for item in values)
    if tuple(sorted(set(normalized))) != normalized:
        raise GhostWalkActionLeaseError(f"{field} must be sorted and unique")
    return normalized


@dataclass(frozen=True, slots=True)
class GhostWalkLeasePolicy:
    """One server-owned capability-specific lease policy.

    The policy constrains issuance but carries no action/execution authority.
    """

    policy_id: str
    principal_id: str
    issuer_id: str
    capability_id: str
    capability_version: str
    permissions_authorized: tuple[str, ...]
    effects_declared: tuple[str, ...]
    enforcement_rules: tuple[EnforcementRule, ...]
    accepted_unenforced_effects: tuple[str, ...]
    max_lease_seconds: int = 30
    effect_performed: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_LEASE_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_LEASE_POLICY_SCHEMA_VERSION:
            raise GhostWalkActionLeaseError("unsupported Ghost-Walk lease policy schema")
        if not _POLICY_ID_RE.fullmatch(self.policy_id):
            raise GhostWalkActionLeaseError("policy_id must be a canonical lowercase identifier")
        _require_text(self.principal_id, "principal_id", maximum=256)
        _require_text(self.issuer_id, "issuer_id", maximum=256)
        _require_text(self.capability_id, "capability_id", maximum=256)
        _require_text(self.capability_version, "capability_version", maximum=128)
        _text_tuple(self.permissions_authorized, "permissions_authorized")
        if not self.permissions_authorized:
            raise GhostWalkActionLeaseError("permissions_authorized must not be empty")
        _text_tuple(self.effects_declared, "effects_declared")
        if not self.effects_declared:
            raise GhostWalkActionLeaseError("effects_declared must not be empty")
        ordered = tuple(sorted(self.enforcement_rules, key=lambda item: item.rule_id))
        if ordered != self.enforcement_rules:
            raise GhostWalkActionLeaseError("enforcement_rules must be sorted by rule_id")
        if len({item.rule_id for item in self.enforcement_rules}) != len(self.enforcement_rules):
            raise GhostWalkActionLeaseError("enforcement rule IDs must be unique")
        declared = set(self.effects_declared)
        for rule in self.enforcement_rules:
            if set(rule.effect_scope) - declared:
                raise GhostWalkActionLeaseError("enforcement rule exceeds policy effect scope")
        _text_tuple(self.accepted_unenforced_effects, "accepted_unenforced_effects")
        if not set(self.accepted_unenforced_effects).issubset(declared):
            raise GhostWalkActionLeaseError(
                "accepted_unenforced_effects must be a subset of effects_declared"
            )
        if isinstance(self.max_lease_seconds, bool) or not isinstance(self.max_lease_seconds, int):
            raise GhostWalkActionLeaseError("max_lease_seconds must be an integer")
        if not 1 <= self.max_lease_seconds <= 300:
            raise GhostWalkActionLeaseError("max_lease_seconds must be from 1 to 300")
        if (
            self.effect_performed
            or self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkActionLeaseError(
                "lease policy cannot perform effects or carry action authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "principal_id": self.principal_id,
            "issuer_id": self.issuer_id,
            "capability_id": self.capability_id,
            "capability_version": self.capability_version,
            "permissions_authorized": list(self.permissions_authorized),
            "effects_declared": list(self.effects_declared),
            "enforcement_rules": [rule.to_dict() for rule in self.enforcement_rules],
            "accepted_unenforced_effects": list(self.accepted_unenforced_effects),
            "max_lease_seconds": self.max_lease_seconds,
            "effect_performed": self.effect_performed,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def policy_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["policy_sha256"] = self.policy_sha256
        return payload


class GhostWalkLeasePolicyRegistry:
    """Immutable server-owned lease-policy set."""

    def __init__(self, policies: tuple[GhostWalkLeasePolicy, ...] = ()) -> None:
        ordered = tuple(sorted(policies, key=lambda item: item.policy_id))
        ids = tuple(item.policy_id for item in ordered)
        if len(set(ids)) != len(ids):
            raise GhostWalkActionLeaseError("lease policy IDs must be unique")
        self._policies = ordered
        self.policy_set_sha256 = _canonical_sha256([item.to_dict() for item in ordered])

    @property
    def policies(self) -> tuple[GhostWalkLeasePolicy, ...]:
        return self._policies

    def for_binding(self, binding: GhostWalkExecutableBinding) -> GhostWalkLeasePolicy | None:
        matches = tuple(
            item
            for item in self._policies
            if item.capability_id == binding.capability_id
            and item.capability_version == binding.capability_version
            and item.permissions_authorized == binding.permissions_required
            and item.effects_declared == binding.effects_declared
        )
        if len(matches) > 1:
            raise GhostWalkActionLeaseError("multiple lease policies match executable binding")
        return matches[0] if matches else None


class GhostWalkBindingPort(Protocol):
    def latest(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkExecutableBinding | None: ...

    def readiness(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> object: ...


class GhostWalkAuthorityEpochProvider(Protocol):
    def current(self) -> AuthorityEpoch | None: ...


@dataclass(frozen=True, slots=True)
class GhostWalkLeaseReadiness:
    target_inference_receipt_sha256: str
    executable_binding_sha256: str | None
    policy_sha256: str | None
    policy_set_sha256: str
    enforcement_profile_sha256: str | None
    authority_epoch_sha256: str | None
    required_permissions: tuple[str, ...]
    missing_permissions: tuple[str, ...]
    unenforced_effects: tuple[str, ...]
    accepted_unenforced_effects: tuple[str, ...]
    existing_action_lease_sha256: str | None
    ready: bool
    reason: GhostWalkLeaseReadinessReason
    effect_performed: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_LEASE_READINESS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_LEASE_READINESS_SCHEMA_VERSION:
            raise GhostWalkActionLeaseError("unsupported Ghost-Walk lease readiness schema")
        _require_sha256(self.target_inference_receipt_sha256, "target_inference_receipt_sha256")
        _optional_sha256(self.executable_binding_sha256, "executable_binding_sha256")
        _optional_sha256(self.policy_sha256, "policy_sha256")
        _require_sha256(self.policy_set_sha256, "policy_set_sha256")
        _optional_sha256(self.enforcement_profile_sha256, "enforcement_profile_sha256")
        _optional_sha256(self.authority_epoch_sha256, "authority_epoch_sha256")
        _optional_sha256(self.existing_action_lease_sha256, "existing_action_lease_sha256")
        _text_tuple(self.required_permissions, "required_permissions")
        _text_tuple(self.missing_permissions, "missing_permissions")
        _text_tuple(self.unenforced_effects, "unenforced_effects")
        _text_tuple(self.accepted_unenforced_effects, "accepted_unenforced_effects")
        if self.ready is not (self.reason is GhostWalkLeaseReadinessReason.READY):
            raise GhostWalkActionLeaseError("lease readiness Boolean must match reason")
        if (
            self.effect_performed
            or self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkActionLeaseError("lease readiness cannot carry effects or authority")

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "target_inference_receipt_sha256": self.target_inference_receipt_sha256,
            "executable_binding_sha256": self.executable_binding_sha256,
            "policy_sha256": self.policy_sha256,
            "policy_set_sha256": self.policy_set_sha256,
