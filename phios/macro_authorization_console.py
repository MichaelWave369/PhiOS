"""Human authorization and lease console for Macro Runtime v0.36.

This layer surfaces the already-governed v0.32-v0.34 trust chain to a local
human operator. It does not execute a capability and it does not let the
browser choose capability, payload, effects, permissions, policy, authority
epoch, lease duration, principal, or issuer.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Protocol

from phios.macro_action_lease_service import (
    GhostWalkActionLeaseError,
    GhostWalkActionLeaseRecord,
    GhostWalkLeaseReadiness,
)
from phios.macro_authorization_decision import (
    GhostWalkAuthorizationDecision,
    GhostWalkAuthorizationDecisionError,
    GhostWalkAuthorizationDecisionKind,
    GhostWalkAuthorizationReadiness,
)
from phios.macro_capability_binding import (
    GhostWalkBindingReadiness,
    GhostWalkCapabilityBindingError,
    GhostWalkExecutableBinding,
)

GHOSTWALK_AUTHORIZATION_CONSOLE_SCHEMA_VERSION = (
    "phios.ghostwalk_authorization_console_snapshot.v0.36"
)
GHOSTWALK_BINDING_SUMMARY_SCHEMA_VERSION = (
    "phios.ghostwalk_executable_binding_summary.v0.36"
)
GHOSTWALK_LEASE_SUMMARY_SCHEMA_VERSION = (
    "phios.ghostwalk_action_lease_summary.v0.36"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class GhostWalkAuthorizationConsoleError(ValueError):
    """Raised when the human authorization console cannot trust its state."""


def _require_sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise GhostWalkAuthorizationConsoleError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return value


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
        raise GhostWalkAuthorizationConsoleError(
            "authorization-console payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class GhostWalkExecutableBindingSummary:
    executable_binding_sha256: str
    authorization_decision_sha256: str
    intent_code: str
    mapping_id: str
    capability_id: str
    capability_version: str
    payload_sha256: str
    permissions_required: tuple[str, ...]
    effects_declared: tuple[str, ...]
    bound_at: str
    effect_performed: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_BINDING_SUMMARY_SCHEMA_VERSION

    @classmethod
    def from_binding(
        cls,
        binding: GhostWalkExecutableBinding,
    ) -> "GhostWalkExecutableBindingSummary":
        return cls(
            executable_binding_sha256=binding.executable_binding_sha256,
            authorization_decision_sha256=(
                binding.authorization_decision_sha256
            ),
            intent_code=binding.intent_code,
            mapping_id=binding.mapping_id,
            capability_id=binding.capability_id,
            capability_version=binding.capability_version,
            payload_sha256=binding.payload_sha256,
            permissions_required=binding.permissions_required,
            effects_declared=binding.effects_declared,
            bound_at=binding.bound_at,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "executable_binding_sha256": self.executable_binding_sha256,
            "authorization_decision_sha256": (
                self.authorization_decision_sha256
            ),
            "intent_code": self.intent_code,
            "mapping_id": self.mapping_id,
            "capability_id": self.capability_id,
            "capability_version": self.capability_version,
            "payload_sha256": self.payload_sha256,
            "permissions_required": list(self.permissions_required),
            "effects_declared": list(self.effects_declared),
            "bound_at": self.bound_at,
            "effect_performed": self.effect_performed,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }


@dataclass(frozen=True, slots=True)
class GhostWalkActionLeaseSummary:
    action_lease_sha256: str
    lease_record_sha256: str
    executable_binding_sha256: str
    principal_id: str
    issuer_id: str
    capability_id: str
    capability_version: str
    payload_sha256: str
    effects_declared: tuple[str, ...]
    permissions_authorized: tuple[str, ...]
    valid_from: str
    valid_until: str
    max_uses: int
    lease_action_authority: bool
    effect_performed: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_LEASE_SUMMARY_SCHEMA_VERSION

    @classmethod
    def from_record(
        cls,
        record: GhostWalkActionLeaseRecord,
    ) -> "GhostWalkActionLeaseSummary":
        lease = record.action_lease
        return cls(
            action_lease_sha256=lease.action_lease_sha256,
            lease_record_sha256=record.lease_record_sha256,
            executable_binding_sha256=record.executable_binding_sha256,
            principal_id=lease.principal_id,
            issuer_id=lease.issuer_id,
            capability_id=lease.capability_id,
            capability_version=lease.capability_version,
            payload_sha256=lease.payload_sha256,
            effects_declared=lease.effects_declared,
            permissions_authorized=lease.permissions_authorized,
            valid_from=lease.valid_from,
            valid_until=lease.valid_until,
            max_uses=lease.max_uses,
            lease_action_authority=lease.action_authority,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "action_lease_sha256": self.action_lease_sha256,
            "lease_record_sha256": self.lease_record_sha256,
            "executable_binding_sha256": self.executable_binding_sha256,
            "principal_id": self.principal_id,
            "issuer_id": self.issuer_id,
            "capability_id": self.capability_id,
            "capability_version": self.capability_version,
            "payload_sha256": self.payload_sha256,
            "effects_declared": list(self.effects_declared),
            "permissions_authorized": list(self.permissions_authorized),
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "max_uses": self.max_uses,
            "lease_action_authority": self.lease_action_authority,
            "effect_performed": self.effect_performed,
            "execution_authority": self.execution_authority,
        }


@dataclass(frozen=True, slots=True)
class GhostWalkAuthorizationConsoleSnapshot:
    target_inference_receipt_sha256: str
    authorization_readiness: GhostWalkAuthorizationReadiness
    authorization_decision: GhostWalkAuthorizationDecision | None
    binding_available: bool
    binding_readiness: GhostWalkBindingReadiness | None
    binding: GhostWalkExecutableBindingSummary | None
    lease_available: bool
    lease_readiness: GhostWalkLeaseReadiness | None
    lease: GhostWalkActionLeaseSummary | None
    effect_performed: bool = False
    policy_authority: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_AUTHORIZATION_CONSOLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_sha256(
            self.target_inference_receipt_sha256,
            "target_inference_receipt_sha256",
        )
        if self.target_inference_receipt_sha256 != (
            self.authorization_readiness.target_inference_receipt_sha256
        ):
            raise GhostWalkAuthorizationConsoleError(
                "authorization readiness target differs from console target"
            )
        if self.authorization_decision is not None and (
            self.authorization_decision.target_inference_receipt_sha256
            != self.target_inference_receipt_sha256
        ):
            raise GhostWalkAuthorizationConsoleError(
                "authorization decision target differs from console target"
            )
        if self.binding_available is not (
            self.binding_readiness is not None
        ):
            raise GhostWalkAuthorizationConsoleError(
                "binding availability differs from readiness presence"
            )
        if self.lease_available is not (
            self.lease_readiness is not None
        ):
            raise GhostWalkAuthorizationConsoleError(
                "lease availability differs from readiness presence"
            )
        if any(
            (
                self.effect_performed,
                self.policy_authority,
                self.operational_authority,
                self.action_authority,
                self.execution_authority,
            )
        ):
            raise GhostWalkAuthorizationConsoleError(
                "authorization console snapshot cannot carry effects or authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "target_inference_receipt_sha256": (
                self.target_inference_receipt_sha256
            ),
            "authorization_readiness": (
                self.authorization_readiness.to_dict()
            ),
            "authorization_decision": (
                None
                if self.authorization_decision is None
                else self.authorization_decision.to_dict()
            ),
            "binding_available": self.binding_available,
            "binding_readiness": (
                None
                if self.binding_readiness is None
                else self.binding_readiness.to_dict()
            ),
            "binding": (
                None if self.binding is None else self.binding.to_dict()
            ),
            "lease_available": self.lease_available,
            "lease_readiness": (
                None
                if self.lease_readiness is None
                else self.lease_readiness.to_dict()
            ),
            "lease": None if self.lease is None else self.lease.to_dict(),
            "effect_performed": self.effect_performed,
            "policy_authority": self.policy_authority,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def snapshot_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["snapshot_sha256"] = self.snapshot_sha256
        return payload


class AuthorizationDecisionPort(Protocol):
    def readiness(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkAuthorizationReadiness: ...

    def latest(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkAuthorizationDecision | None: ...

    def record(
        self,
        *,
        target_inference_receipt_sha256: str,
        expected_authority_request_sha256: str,
        expected_previous_decision_sha256: str | None,
        decision: GhostWalkAuthorizationDecisionKind,
        decision_note: str | None = None,
        decided_at: str | None = None,
    ) -> GhostWalkAuthorizationDecision: ...


class CapabilityBindingPort(Protocol):
    def readiness(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkBindingReadiness: ...

    def latest(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkExecutableBinding | None: ...

    def create(
        self,
        *,
        target_inference_receipt_sha256: str,
        expected_authorization_decision_sha256: str,
        expected_mapping_sha256: str,
        expected_mapping_set_sha256: str,
        bound_at: str,
    ) -> GhostWalkExecutableBinding: ...


class ActionLeasePort(Protocol):
    def readiness(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkLeaseReadiness: ...

    def latest(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkActionLeaseRecord | None: ...

    def issue(
        self,
        *,
        target_inference_receipt_sha256: str,
        expected_executable_binding_sha256: str,
        expected_policy_sha256: str,
        expected_policy_set_sha256: str,
        expected_enforcement_profile_sha256: str,
        expected_authority_epoch_sha256: str,
    ) -> GhostWalkActionLeaseRecord: ...


class GhostWalkAuthorizationConsoleService:
    """Human-facing façade over v0.32-v0.34 governed services."""

    def __init__(
        self,
        *,
        authorization_decisions: AuthorizationDecisionPort,
        capability_bindings: CapabilityBindingPort | None = None,
        action_leases: ActionLeasePort | None = None,
    ) -> None:
        self._authorization_decisions = authorization_decisions
        self._capability_bindings = capability_bindings
        self._action_leases = action_leases

    def snapshot(
        self,
        *,
        target_inference_receipt_sha256: str,
    ) -> GhostWalkAuthorizationConsoleSnapshot:
        target = _require_sha256(
            target_inference_receipt_sha256,
            "target_inference_receipt_sha256",
        )
        try:
            auth_readiness = self._authorization_decisions.readiness(
                target_inference_receipt_sha256=target
            )
            decision = self._authorization_decisions.latest(
                target_inference_receipt_sha256=target
            )
        except GhostWalkAuthorizationDecisionError as exc:
            raise GhostWalkAuthorizationConsoleError(str(exc)) from exc

        binding_readiness: GhostWalkBindingReadiness | None = None
        binding_summary: GhostWalkExecutableBindingSummary | None = None
        if self._capability_bindings is not None:
            try:
                binding_readiness = self._capability_bindings.readiness(
                    target_inference_receipt_sha256=target
                )
                binding = self._capability_bindings.latest(
                    target_inference_receipt_sha256=target
                )
            except GhostWalkCapabilityBindingError as exc:
                raise GhostWalkAuthorizationConsoleError(str(exc)) from exc
            if binding is not None:
                binding_summary = (
                    GhostWalkExecutableBindingSummary.from_binding(binding)
                )

        lease_readiness: GhostWalkLeaseReadiness | None = None
        lease_summary: GhostWalkActionLeaseSummary | None = None
        if self._action_leases is not None:
            try:
                lease_readiness = self._action_leases.readiness(
                    target_inference_receipt_sha256=target
                )
                lease = self._action_leases.latest(
                    target_inference_receipt_sha256=target
                )
            except GhostWalkActionLeaseError as exc:
                raise GhostWalkAuthorizationConsoleError(str(exc)) from exc
            if lease is not None:
                lease_summary = GhostWalkActionLeaseSummary.from_record(lease)

        return GhostWalkAuthorizationConsoleSnapshot(
            target_inference_receipt_sha256=target,
            authorization_readiness=auth_readiness,
            authorization_decision=decision,
            binding_available=binding_readiness is not None,
            binding_readiness=binding_readiness,
            binding=binding_summary,
            lease_available=lease_readiness is not None,
            lease_readiness=lease_readiness,
            lease=lease_summary,
        )

    def record_decision(
        self,
        *,
        target_inference_receipt_sha256: str,
        expected_authority_request_sha256: str,
        expected_previous_decision_sha256: str | None,
        decision: GhostWalkAuthorizationDecisionKind,
        decision_note: str | None,
    ) -> GhostWalkAuthorizationDecision:
        try:
            return self._authorization_decisions.record(
                target_inference_receipt_sha256=(
                    target_inference_receipt_sha256
                ),
                expected_authority_request_sha256=(
                    expected_authority_request_sha256
                ),
                expected_previous_decision_sha256=(
                    expected_previous_decision_sha256
                ),
                decision=decision,
                decision_note=decision_note,
            )
        except GhostWalkAuthorizationDecisionError as exc:
            raise GhostWalkAuthorizationConsoleError(str(exc)) from exc

    def create_binding(
        self,
        *,
        target_inference_receipt_sha256: str,
        expected_authorization_decision_sha256: str,
        expected_mapping_sha256: str,
        expected_mapping_set_sha256: str,
        bound_at: str,
    ) -> GhostWalkExecutableBindingSummary:
        if self._capability_bindings is None:
            raise GhostWalkAuthorizationConsoleError(
                "trusted capability binding service is not mounted"
            )
        try:
            binding = self._capability_bindings.create(
                target_inference_receipt_sha256=(
                    target_inference_receipt_sha256
                ),
                expected_authorization_decision_sha256=(
                    expected_authorization_decision_sha256
                ),
                expected_mapping_sha256=expected_mapping_sha256,
                expected_mapping_set_sha256=expected_mapping_set_sha256,
                bound_at=bound_at,
            )
        except GhostWalkCapabilityBindingError as exc:
            raise GhostWalkAuthorizationConsoleError(str(exc)) from exc
        return GhostWalkExecutableBindingSummary.from_binding(binding)

    def issue_lease(
        self,
        *,
        target_inference_receipt_sha256: str,
        expected_executable_binding_sha256: str,
        expected_policy_sha256: str,
        expected_policy_set_sha256: str,
        expected_enforcement_profile_sha256: str,
        expected_authority_epoch_sha256: str,
    ) -> GhostWalkActionLeaseSummary:
        if self._action_leases is None:
            raise GhostWalkAuthorizationConsoleError(
                "trusted ActionLease service is not mounted"
            )
        try:
            record = self._action_leases.issue(
                target_inference_receipt_sha256=(
                    target_inference_receipt_sha256
                ),
                expected_executable_binding_sha256=(
                    expected_executable_binding_sha256
                ),
                expected_policy_sha256=expected_policy_sha256,
                expected_policy_set_sha256=expected_policy_set_sha256,
                expected_enforcement_profile_sha256=(
                    expected_enforcement_profile_sha256
                ),
                expected_authority_epoch_sha256=(
                    expected_authority_epoch_sha256
                ),
            )
        except GhostWalkActionLeaseError as exc:
            raise GhostWalkAuthorizationConsoleError(str(exc)) from exc
        return GhostWalkActionLeaseSummary.from_record(record)


__all__ = [
    "GhostWalkActionLeaseSummary",
    "GhostWalkAuthorizationConsoleError",
    "GhostWalkAuthorizationConsoleService",
    "GhostWalkAuthorizationConsoleSnapshot",
    "GhostWalkExecutableBindingSummary",
]
