"""Governed action binding for PhiOS core reasoning v0.7.

This layer binds one exact transition in an adopted PlanState to one exact Spine
Capability plus one payload digest. Binding does not grant the capability's
permissions and does not execute anything.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from phios.core.governed_plan_adoption import (
    GovernedPlanAdoptionGate,
    PlanState,
)
from phios.spine.models import Capability


class ActionBindingContractError(ValueError):
    """Raised when action-binding inputs or state are malformed."""


@dataclass(frozen=True, slots=True)
class ActionBindingGrant:
    """External authority scoped to one exact plan edge/capability/payload tuple."""

    grant_id: str
    authority_source: str
    plan_id: str
    plan_state_sha256: str
    transition_index: int
    source_state_id: str
    target_state_id: str
    capability_id: str
    payload_sha256: str

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": "phios.action_binding_grant.v0.7",
            "grant_id": self.grant_id,
            "authority_source": self.authority_source,
            "plan_id": self.plan_id,
            "plan_state_sha256": self.plan_state_sha256,
            "transition_index": self.transition_index,
            "source_state_id": self.source_state_id,
            "target_state_id": self.target_state_id,
            "capability_id": self.capability_id,
            "payload_sha256": self.payload_sha256,
        }

    @property
    def grant_sha256(self) -> str:
        return _payload_digest(self.to_payload())


@dataclass(frozen=True, slots=True)
class PlanActionBinding:
    """Immutable executable-intent binding with zero execution authority."""

    schema: str
    plan_id: str
    plan_state_sha256: str
    plan_revision: int
    transition_index: int
    source_state_id: str
    target_state_id: str
    capability_id: str
    capability_version: str
    capability_risk: str
    permissions_requested: tuple[str, ...]
    payload_sha256: str
    grant_id: str
    grant_sha256: str
    authority_source: str
    action_authority: bool
    execution_authority: bool
    binding_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "plan_id": self.plan_id,
            "plan_state_sha256": self.plan_state_sha256,
            "plan_revision": self.plan_revision,
            "transition_index": self.transition_index,
            "source_state_id": self.source_state_id,
            "target_state_id": self.target_state_id,
            "capability_id": self.capability_id,
            "capability_version": self.capability_version,
            "capability_risk": self.capability_risk,
            "permissions_requested": list(self.permissions_requested),
            "payload_sha256": self.payload_sha256,
            "grant_id": self.grant_id,
            "grant_sha256": self.grant_sha256,
            "authority_source": self.authority_source,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "binding_sha256": self.binding_sha256,
        }


@dataclass(frozen=True, slots=True)
class ActionBindingReceipt:
    """Deterministic BOUND / HELD binding receipt."""

    schema: str
    status: str
    reason: str
    plan_id: str
    plan_state_sha256: str
    transition_index: int
    source_state_id: str
    target_state_id: str
    capability_id: str
    payload_sha256: str
    permissions_requested: tuple[str, ...]
    grant_id: str | None
    grant_sha256: str | None
    authority_source: str | None
    grant_scope_valid: bool
    binding_sha256: str | None
    action_authority: bool
    execution_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "status": self.status,
            "reason": self.reason,
            "plan_id": self.plan_id,
            "plan_state_sha256": self.plan_state_sha256,
            "transition_index": self.transition_index,
            "source_state_id": self.source_state_id,
            "target_state_id": self.target_state_id,
            "capability_id": self.capability_id,
            "payload_sha256": self.payload_sha256,
            "permissions_requested": list(self.permissions_requested),
            "grant_id": self.grant_id,
            "grant_sha256": self.grant_sha256,
            "authority_source": self.authority_source,
            "grant_scope_valid": self.grant_scope_valid,
            "binding_sha256": self.binding_sha256,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "receipt_sha256": self.receipt_sha256,
        }


class GovernedActionBinder:
    """Bind an adopted plan edge to a Spine capability without executing it."""

    def __init__(self) -> None:
        self._plan_gate = GovernedPlanAdoptionGate()

    def validate_binding(self, binding: PlanActionBinding) -> None:
        """Validate a v0.7 binding without granting or executing anything."""

        if binding.schema != "phios.plan_action_binding.v0.7":
            raise ActionBindingContractError("unsupported action binding schema")
        if binding.action_authority is not False:
            raise ActionBindingContractError(
                "action binding cannot carry action authority"
            )
        if binding.execution_authority is not False:
            raise ActionBindingContractError(
                "action binding cannot carry execution authority"
            )
        if not binding.plan_id.strip():
            raise ActionBindingContractError("binding plan_id must be non-empty")
        if binding.plan_revision < 0:
            raise ActionBindingContractError(
                "binding plan_revision must be non-negative"
            )
        if binding.transition_index < 0:
            raise ActionBindingContractError(
                "binding transition_index must be non-negative"
            )
        if not binding.source_state_id.strip() or not binding.target_state_id.strip():
            raise ActionBindingContractError(
                "binding source and target state IDs must be non-empty"
            )
        if not binding.capability_id.strip():
            raise ActionBindingContractError(
                "binding capability_id must be non-empty"
            )
        if not binding.capability_version.strip():
            raise ActionBindingContractError(
                "binding capability_version must be non-empty"
            )
        if binding.capability_risk not in {"read", "low", "medium", "high"}:
            raise ActionBindingContractError(
                "binding capability_risk is invalid"
            )
        if any(not item.strip() for item in binding.permissions_requested):
            raise ActionBindingContractError(
                "binding permissions must be non-empty strings"
            )
        if len(set(binding.permissions_requested)) != len(
            binding.permissions_requested
        ):
            raise ActionBindingContractError(
                "binding permissions must be unique"
            )
        for label, digest in (
            ("plan_state_sha256", binding.plan_state_sha256),
            ("payload_sha256", binding.payload_sha256),
            ("grant_sha256", binding.grant_sha256),
            ("binding_sha256", binding.binding_sha256),
        ):
            _require_sha256(digest, label)
        if not binding.grant_id.strip():
            raise ActionBindingContractError("binding grant_id must be non-empty")
        if not binding.authority_source.strip():
            raise ActionBindingContractError(
                "binding authority_source must be non-empty"
            )

        payload: dict[str, object] = {
            "schema": binding.schema,
            "plan_id": binding.plan_id,
            "plan_state_sha256": binding.plan_state_sha256,
            "plan_revision": binding.plan_revision,
            "transition_index": binding.transition_index,
            "source_state_id": binding.source_state_id,
            "target_state_id": binding.target_state_id,
            "capability_id": binding.capability_id,
            "capability_version": binding.capability_version,
            "capability_risk": binding.capability_risk,
            "permissions_requested": list(binding.permissions_requested),
            "payload_sha256": binding.payload_sha256,
            "grant_id": binding.grant_id,
            "grant_sha256": binding.grant_sha256,
            "authority_source": binding.authority_source,
            "action_authority": False,
            "execution_authority": False,
        }
        if _payload_digest(payload) != binding.binding_sha256:
            raise ActionBindingContractError(
                "action binding hash does not match binding contents"
            )

    def payload_sha256(self, payload: Mapping[str, Any]) -> str:
        """Return the canonical v0.7 payload digest used by action bindings."""

        return _payload_digest(dict(payload))

    def bind(
        self,
        *,
        plan: PlanState,
        transition_index: int,
        capability: Capability,
        payload: Mapping[str, Any],
        grant: ActionBindingGrant | None,
    ) -> tuple[PlanActionBinding | None, ActionBindingReceipt]:
        self._plan_gate.validate_plan_state(plan)
        source_state_id, target_state_id = self._transition(plan, transition_index)
        capability_id, version, risk, permissions = self._validate_capability(
            capability
        )
        payload_sha256 = _payload_digest(dict(payload))

        scope_valid, scope_reason = self._grant_scope(
            plan=plan,
            transition_index=transition_index,
            source_state_id=source_state_id,
            target_state_id=target_state_id,
            capability_id=capability_id,
            payload_sha256=payload_sha256,
            grant=grant,
        )
        if not scope_valid:
            receipt = self._receipt(
                status="HELD",
                reason=scope_reason,
                plan=plan,
                transition_index=transition_index,
                source_state_id=source_state_id,
                target_state_id=target_state_id,
                capability_id=capability_id,
                payload_sha256=payload_sha256,
                permissions=permissions,
                grant=grant,
                grant_scope_valid=False,
                binding_sha256=None,
            )
            return None, receipt

        assert grant is not None
        binding_payload: dict[str, object] = {
            "schema": "phios.plan_action_binding.v0.7",
            "plan_id": plan.plan_id,
            "plan_state_sha256": plan.state_sha256,
            "plan_revision": plan.revision,
            "transition_index": transition_index,
            "source_state_id": source_state_id,
            "target_state_id": target_state_id,
            "capability_id": capability_id,
            "capability_version": version,
            "capability_risk": risk,
            "permissions_requested": list(permissions),
            "payload_sha256": payload_sha256,
            "grant_id": grant.grant_id.strip(),
            "grant_sha256": grant.grant_sha256,
            "authority_source": grant.authority_source.strip(),
            "action_authority": False,
            "execution_authority": False,
        }
        binding = PlanActionBinding(
            schema="phios.plan_action_binding.v0.7",
            plan_id=plan.plan_id,
            plan_state_sha256=plan.state_sha256,
            plan_revision=plan.revision,
            transition_index=transition_index,
            source_state_id=source_state_id,
            target_state_id=target_state_id,
            capability_id=capability_id,
            capability_version=version,
            capability_risk=risk,
            permissions_requested=permissions,
            payload_sha256=payload_sha256,
            grant_id=grant.grant_id.strip(),
            grant_sha256=grant.grant_sha256,
            authority_source=grant.authority_source.strip(),
            action_authority=False,
            execution_authority=False,
            binding_sha256=_payload_digest(binding_payload),
        )
        receipt = self._receipt(
            status="BOUND",
            reason="authorized_action_binding",
            plan=plan,
            transition_index=transition_index,
            source_state_id=source_state_id,
            target_state_id=target_state_id,
            capability_id=capability_id,
            payload_sha256=payload_sha256,
            permissions=permissions,
            grant=grant,
            grant_scope_valid=True,
            binding_sha256=binding.binding_sha256,
        )
        return binding, receipt

    def _transition(
        self,
        plan: PlanState,
        transition_index: int,
    ) -> tuple[str, str]:
        if isinstance(transition_index, bool) or not isinstance(
            transition_index, int
        ):
            raise ActionBindingContractError(
                "transition_index must be an integer"
            )
        if transition_index < 0 or transition_index >= len(plan.path_ids) - 1:
            raise ActionBindingContractError(
                "transition_index must identify an existing plan edge"
            )
        return (
            plan.path_ids[transition_index],
            plan.path_ids[transition_index + 1],
        )

    def _validate_capability(
        self,
        capability: Capability,
    ) -> tuple[str, str, str, tuple[str, ...]]:
        capability_id = capability.id.strip()
        version = capability.version.strip()
        risk = str(capability.risk).strip()
        if not capability_id:
            raise ActionBindingContractError(
                "capability id must be non-empty"
            )
        if not version:
            raise ActionBindingContractError(
                "capability version must be non-empty"
            )
        if risk not in {"read", "low", "medium", "high"}:
            raise ActionBindingContractError(
                "capability risk must be read, low, medium, or high"
            )
        permissions = tuple(item.strip() for item in capability.permissions)
        if any(not item for item in permissions):
            raise ActionBindingContractError(
                "capability permissions must be non-empty"
            )
        if len(set(permissions)) != len(permissions):
            raise ActionBindingContractError(
                "capability permissions must be unique"
            )
        return capability_id, version, risk, permissions

    def _grant_scope(
        self,
        *,
        plan: PlanState,
        transition_index: int,
        source_state_id: str,
        target_state_id: str,
        capability_id: str,
        payload_sha256: str,
        grant: ActionBindingGrant | None,
    ) -> tuple[bool, str]:
        if grant is None:
            return False, "action_binding_authority_missing"
        if not grant.grant_id.strip():
            raise ActionBindingContractError("grant_id must be non-empty")
        if not grant.authority_source.strip():
            raise ActionBindingContractError(
                "grant authority_source must be non-empty"
            )
        if grant.plan_id.strip() != plan.plan_id:
            return False, "grant_plan_scope_mismatch"
        if grant.plan_state_sha256 != plan.state_sha256:
            return False, "grant_plan_state_scope_mismatch"
        if grant.transition_index != transition_index:
            return False, "grant_transition_scope_mismatch"
        if grant.source_state_id != source_state_id:
            return False, "grant_source_scope_mismatch"
        if grant.target_state_id != target_state_id:
            return False, "grant_target_scope_mismatch"
        if grant.capability_id != capability_id:
            return False, "grant_capability_scope_mismatch"
        if grant.payload_sha256 != payload_sha256:
            return False, "grant_payload_scope_mismatch"
        return True, "grant_scope_valid"

    def _receipt(
        self,
        *,
        status: str,
        reason: str,
        plan: PlanState,
        transition_index: int,
        source_state_id: str,
        target_state_id: str,
        capability_id: str,
        payload_sha256: str,
        permissions: tuple[str, ...],
        grant: ActionBindingGrant | None,
        grant_scope_valid: bool,
        binding_sha256: str | None,
    ) -> ActionBindingReceipt:
        grant_id = grant.grant_id.strip() if grant is not None else None
        grant_sha256 = grant.grant_sha256 if grant is not None else None
        authority_source = (
            grant.authority_source.strip() if grant is not None else None
        )
        receipt_payload: dict[str, object] = {
            "schema": "phios.action_binding_receipt.v0.7",
            "status": status,
            "reason": reason,
            "plan_id": plan.plan_id,
            "plan_state_sha256": plan.state_sha256,
            "transition_index": transition_index,
            "source_state_id": source_state_id,
            "target_state_id": target_state_id,
            "capability_id": capability_id,
            "payload_sha256": payload_sha256,
            "permissions_requested": list(permissions),
            "grant_id": grant_id,
            "grant_sha256": grant_sha256,
            "authority_source": authority_source,
            "grant_scope_valid": grant_scope_valid,
            "binding_sha256": binding_sha256,
            "action_authority": False,
            "execution_authority": False,
        }
        return ActionBindingReceipt(
            schema="phios.action_binding_receipt.v0.7",
            status=status,
            reason=reason,
            plan_id=plan.plan_id,
            plan_state_sha256=plan.state_sha256,
            transition_index=transition_index,
            source_state_id=source_state_id,
            target_state_id=target_state_id,
            capability_id=capability_id,
            payload_sha256=payload_sha256,
            permissions_requested=permissions,
            grant_id=grant_id,
            grant_sha256=grant_sha256,
            authority_source=authority_source,
            grant_scope_valid=grant_scope_valid,
            binding_sha256=binding_sha256,
            action_authority=False,
            execution_authority=False,
            receipt_sha256=_payload_digest(receipt_payload),
        )


def _require_sha256(value: str, label: str) -> None:
    normalized = value.strip().lower()
    if len(normalized) != 64:
        raise ActionBindingContractError(f"{label} must be a SHA-256 hex digest")
    try:
        int(normalized, 16)
    except ValueError as exc:
        raise ActionBindingContractError(
            f"{label} must be a SHA-256 hex digest"
        ) from exc


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
        raise ActionBindingContractError(
            "action binding payload must be canonical JSON"
        ) from exc


def _payload_digest(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(
        _canonical_json(dict(payload)).encode("utf-8")
    ).hexdigest()
