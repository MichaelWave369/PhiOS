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
