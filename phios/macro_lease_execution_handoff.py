"""Lease-only Ghost-Walk execution handoff for Macro Runtime v0.35.

The public execution input is exactly one ActionLease identity. The service
recovers every executable detail from trusted PhiOS custody, revalidates the
current binding/policy/enforcement/authority state, atomically claims the
single-use lease, and delegates the exact stored payload through PhiOS Spine.

No caller may provide or replace a capability, payload, permission, effect,
target, enforcement rule, authority epoch, or lease field.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Mapping

from phios.action_lease import ActionLeaseContractError, evaluate_action_lease
from phios.enforcement_profile import (
    EnforcementProfile,
    EnforcementProfileContractError,
)
from phios.macro_action_lease_service import (
    GhostWalkActionLeaseError,
    GhostWalkActionLeaseRecord,
    GhostWalkAuthorityEpochProvider,
    GhostWalkBindingPort,
    GhostWalkLeasePolicy,
    GhostWalkLeasePolicyRegistry,
)
from phios.macro_capability_binding import (
    GhostWalkBindingReadinessReason,
    GhostWalkCapabilityBindingError,
    GhostWalkExecutableBinding,
)
from phios.spine.effects import EffectBoundaryContractError, normalize_effects
from phios.spine.ledger import RealityLedger
from phios.spine.models import GhostWalkExecutionProvenance
from phios.spine.runtime import PhiOSSpine

GHOSTWALK_LEASE_EXECUTION_RECEIPT_SCHEMA_VERSION = (
    "phios.ghostwalk_lease_execution_receipt.v0.35"
)
GHOSTWALK_EXECUTION_PROVENANCE_SCHEMA_VERSION = (
    "phios.ghostwalk_execution_provenance.v0.35"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class GhostWalkLeaseExecutionError(ValueError):
    """Raised when lease-only execution inputs or custody cannot be trusted."""


def _require_text(value: object, field: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value:
        raise GhostWalkLeaseExecutionError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise GhostWalkLeaseExecutionError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise GhostWalkLeaseExecutionError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise GhostWalkLeaseExecutionError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _optional_sha256(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _require_sha256(value, field)


def _optional_text(
    value: object,
    field: str,
    *,
    maximum: int = 512,
) -> str | None:
    if value is None:
        return None
    return _require_text(value, field, maximum=maximum)


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
        raise GhostWalkLeaseExecutionError(
            "Ghost-Walk execution payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _parse_time(value: object, field: str) -> datetime:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GhostWalkLeaseExecutionError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GhostWalkLeaseExecutionError(
            f"{field} must include a timezone"
        )
    return parsed.astimezone(UTC)


def _canonical_time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise GhostWalkLeaseExecutionError(
            "execution clock must be timezone-aware"
        )
    return value.astimezone(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class GhostWalkLeaseExecutionReceipt:
    """Immutable custody/outcome record for one lease-only execution call."""

    status: str
    reason: str
    action_lease_sha256: str
    attempted_at: str
    lease_record_sha256: str | None
    target_inference_receipt_sha256: str | None
    executable_binding_sha256: str | None
    authority_epoch_sha256: str | None
    policy_sha256: str | None
    enforcement_profile_sha256: str | None
    spine_receipt_id: str | None
    spine_permission_status: str | None
    spine_execution_status: str | None
    executor_entered: bool
    lease_claimed: bool
    lease_consumed: bool
    replay_blocked: bool
    effect_performed: bool | None
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_LEASE_EXECUTION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_LEASE_EXECUTION_RECEIPT_SCHEMA_VERSION:
            raise GhostWalkLeaseExecutionError(
                "unsupported Ghost-Walk lease execution receipt schema"
            )
        if self.status not in {
            "HELD",
            "DENIED",
            "SUCCEEDED",
            "FAILED",
            "OUTCOME_UNKNOWN",
        }:
            raise GhostWalkLeaseExecutionError(
                "unsupported Ghost-Walk lease execution status"
            )
        _require_text(self.reason, "reason", maximum=512)
        _require_sha256(self.action_lease_sha256, "action_lease_sha256")
        canonical = _parse_time(self.attempted_at, "attempted_at")
        if canonical.isoformat() != self.attempted_at:
            raise GhostWalkLeaseExecutionError(
                "attempted_at must use canonical UTC ISO-8601 form"
            )
        for field, digest in (
            ("lease_record_sha256", self.lease_record_sha256),
            (
                "target_inference_receipt_sha256",
                self.target_inference_receipt_sha256,
            ),
            ("executable_binding_sha256", self.executable_binding_sha256),
            ("authority_epoch_sha256", self.authority_epoch_sha256),
            ("policy_sha256", self.policy_sha256),
            (
                "enforcement_profile_sha256",
                self.enforcement_profile_sha256,
            ),
        ):
            _optional_sha256(digest, field)
        _optional_text(self.spine_receipt_id, "spine_receipt_id")
        _optional_text(
            self.spine_permission_status,
            "spine_permission_status",
            maximum=64,
        )
        _optional_text(
            self.spine_execution_status,
            "spine_execution_status",
            maximum=64,
        )
        for field, value in (
            ("executor_entered", self.executor_entered),
            ("lease_claimed", self.lease_claimed),
            ("lease_consumed", self.lease_consumed),
            ("replay_blocked", self.replay_blocked),
            ("action_authority", self.action_authority),
            ("execution_authority", self.execution_authority),
        ):
            if not isinstance(value, bool):
                raise GhostWalkLeaseExecutionError(
                    f"{field} must be Boolean"
                )
        if self.effect_performed not in {True, False, None}:
            raise GhostWalkLeaseExecutionError(
                "effect_performed must be Boolean or null"
            )
        if self.action_authority or self.execution_authority:
            raise GhostWalkLeaseExecutionError(
                "execution receipt cannot grant authority"
            )
        if self.lease_consumed and not self.lease_claimed:
            raise GhostWalkLeaseExecutionError(
                "consumed lease must have been claimed"
            )
        if self.executor_entered and not self.lease_claimed:
            raise GhostWalkLeaseExecutionError(
                "entered executor must have a claimed lease"
            )
        if self.status in {"HELD", "DENIED"}:
            if self.executor_entered or self.lease_consumed:
                raise GhostWalkLeaseExecutionError(
                    "held or denied execution cannot consume the lease"
                )
            if self.effect_performed is not False:
                raise GhostWalkLeaseExecutionError(
                    "held or denied execution cannot claim an effect"
                )
        if self.status == "SUCCEEDED":
            if (
                not self.executor_entered
                or not self.lease_consumed
                or self.effect_performed is not True
            ):
                raise GhostWalkLeaseExecutionError(
                    "successful execution receipt is incomplete"
                )
        if self.status in {"FAILED", "OUTCOME_UNKNOWN"}:
            if not self.executor_entered or not self.lease_consumed:
                raise GhostWalkLeaseExecutionError(
                    "entered failed/unknown execution must consume lease"
                )
            if self.effect_performed is not None:
                raise GhostWalkLeaseExecutionError(
                    "failed/unknown effect state must remain unknown"
                )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "reason": self.reason,
            "action_lease_sha256": self.action_lease_sha256,
            "attempted_at": self.attempted_at,
            "lease_record_sha256": self.lease_record_sha256,
            "target_inference_receipt_sha256": (
                self.target_inference_receipt_sha256
            ),
            "executable_binding_sha256": self.executable_binding_sha256,
            "authority_epoch_sha256": self.authority_epoch_sha256,
            "policy_sha256": self.policy_sha256,
            "enforcement_profile_sha256": (
                self.enforcement_profile_sha256
            ),
            "spine_receipt_id": self.spine_receipt_id,
            "spine_permission_status": self.spine_permission_status,
            "spine_execution_status": self.spine_execution_status,
            "executor_entered": self.executor_entered,
            "lease_claimed": self.lease_claimed,
            "lease_consumed": self.lease_consumed,
            "replay_blocked": self.replay_blocked,
            "effect_performed": self.effect_performed,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def receipt_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["receipt_sha256"] = self.receipt_sha256
        return payload

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, object],
    ) -> "GhostWalkLeaseExecutionReceipt":
        expected = {
            "schema_version",
            "status",
            "reason",
            "action_lease_sha256",
            "attempted_at",
            "lease_record_sha256",
            "target_inference_receipt_sha256",
            "executable_binding_sha256",
            "authority_epoch_sha256",
            "policy_sha256",
            "enforcement_profile_sha256",
            "spine_receipt_id",
            "spine_permission_status",
            "spine_execution_status",
            "executor_entered",
            "lease_claimed",
            "lease_consumed",
            "replay_blocked",
            "effect_performed",
            "action_authority",
            "execution_authority",
            "receipt_sha256",
        }
        if set(value) != expected:
            raise GhostWalkLeaseExecutionError(
                "lease execution receipt fields do not match contract"
            )
