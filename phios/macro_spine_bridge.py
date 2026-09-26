"""Governed bridge from Macro Runtime operations into the PhiOS execution spine.

v0.2 does not create a second authority system. A macro operation is bound to
one exact adopted plan action and one verified single-use ActionLease, then the
existing GovernedLeasedExecutionHandoff remains the authority/execution gate.
The bridge adds macro provenance and an append-only macro receipt only.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from phios.action_lease import ActionLease
from phios.core.governed_action_binding import (
    GovernedActionBinder,
    PlanActionBinding,
)
from phios.core.governed_plan_adoption import PlanState
from phios.core.leased_execution_handoff import (
    GovernedLeasedExecutionHandoff,
    LeaseVerificationEvidence,
)
from phios.macro_runtime import ExecutionMode, Operation
from phios.spine.runtime import PhiOSSpine

MACRO_SPINE_BINDING_SCHEMA_VERSION = "phios.macro_spine_binding.v0.2"
MACRO_SPINE_RECEIPT_SCHEMA_VERSION = "phios.macro_spine_receipt.v0.2"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class MacroSpineBridgeContractError(ValueError):
    """Raised when macro-to-spine scope cannot be proven exactly."""


def _require_text(value: object, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value:
        raise MacroSpineBridgeContractError(f"{field} must be a non-empty string")
    if len(value) > maximum:
        raise MacroSpineBridgeContractError(f"{field} exceeds {maximum} characters")
    if any(ord(char) < 32 for char in value):
        raise MacroSpineBridgeContractError(f"{field} contains control characters")
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise MacroSpineBridgeContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _canonical_sha256(value: Mapping[str, object]) -> str:
    try:
        encoded = json.dumps(
            dict(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise MacroSpineBridgeContractError(
            "macro spine receipt must be canonical JSON"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class MacroSpineBinding:
    """Zero-authority binding from one macro operation to one PhiOS action."""

    macro_id: str
    macro_version: str
    operation_id: str
    operation_version: str
    operation_hash: str
    plan_id: str
    plan_state_sha256: str
    action_binding_sha256: str
    capability_id: str
    payload_sha256: str
    action_lease_sha256: str
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = MACRO_SPINE_BINDING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MACRO_SPINE_BINDING_SCHEMA_VERSION:
            raise MacroSpineBridgeContractError(
                "unsupported macro spine binding schema"
            )
        _require_text(self.macro_id, "macro_id")
        _require_text(self.macro_version, "macro_version", maximum=128)
        _require_text(self.operation_id, "operation_id")
        _require_text(self.operation_version, "operation_version", maximum=128)
        _require_text(self.plan_id, "plan_id")
        _require_text(self.capability_id, "capability_id")
        for label, digest in (
            ("operation_hash", self.operation_hash),
            ("plan_state_sha256", self.plan_state_sha256),
            ("action_binding_sha256", self.action_binding_sha256),
            ("payload_sha256", self.payload_sha256),
            ("action_lease_sha256", self.action_lease_sha256),
        ):
            _require_sha256(digest, label)
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise MacroSpineBridgeContractError(
                "macro spine binding cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "macro_id": self.macro_id,
            "macro_version": self.macro_version,
            "operation_id": self.operation_id,
            "operation_version": self.operation_version,
            "operation_hash": self.operation_hash,
            "plan_id": self.plan_id,
            "plan_state_sha256": self.plan_state_sha256,
            "action_binding_sha256": self.action_binding_sha256,
            "capability_id": self.capability_id,
            "payload_sha256": self.payload_sha256,
            "action_lease_sha256": self.action_lease_sha256,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def binding_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["binding_sha256"] = self.binding_sha256
        return payload

    @classmethod
    def build(
        cls,
        *,
        macro_id: str,
        macro_version: str,
        operation: Operation,
        plan: PlanState,
        binding: PlanActionBinding,
        lease: ActionLease,
    ) -> "MacroSpineBinding":
        return cls(
            macro_id=macro_id,
            macro_version=macro_version,
            operation_id=operation.operation_id,
            operation_version=operation.operation_version,
            operation_hash=operation.operation_hash,
            plan_id=plan.plan_id,
            plan_state_sha256=plan.state_sha256,
            action_binding_sha256=binding.binding_sha256,
            capability_id=binding.capability_id,
            payload_sha256=binding.payload_sha256,
            action_lease_sha256=lease.action_lease_sha256,
        )


@dataclass(frozen=True, slots=True)
class MacroSpineReceipt:
    """Append-only evidence binding a macro operation to leased Spine execution."""

    status: str
    reason: str
    macro_id: str
    macro_version: str
    operation_id: str
    operation_hash: str
    macro_spine_binding_sha256: str
    action_binding_sha256: str
    action_lease_sha256: str
    leased_handoff_receipt_sha256: str
    spine_receipt_id: str | None
    spine_execution_status: str | None
    lease_consumed: bool
    replay_blocked: bool
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    effect_performed: bool = False
    schema_version: str = MACRO_SPINE_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MACRO_SPINE_RECEIPT_SCHEMA_VERSION:
            raise MacroSpineBridgeContractError(
                "unsupported macro spine receipt schema"
            )
        _require_text(self.status, "status", maximum=64)
        _require_text(self.reason, "reason")
        _require_text(self.macro_id, "macro_id")
        _require_text(self.macro_version, "macro_version", maximum=128)
        _require_text(self.operation_id, "operation_id")
        for label, digest in (
            ("operation_hash", self.operation_hash),
            ("macro_spine_binding_sha256", self.macro_spine_binding_sha256),
            ("action_binding_sha256", self.action_binding_sha256),
            ("action_lease_sha256", self.action_lease_sha256),
            (
                "leased_handoff_receipt_sha256",
                self.leased_handoff_receipt_sha256,
            ),
        ):
            _require_sha256(digest, label)
        if self.spine_receipt_id is not None:
            _require_text(self.spine_receipt_id, "spine_receipt_id")
        if self.spine_execution_status is not None:
            _require_text(
                self.spine_execution_status,
                "spine_execution_status",
                maximum=64,
            )
        if not isinstance(self.lease_consumed, bool):
            raise MacroSpineBridgeContractError("lease_consumed must be Boolean")
        if not isinstance(self.replay_blocked, bool):
            raise MacroSpineBridgeContractError("replay_blocked must be Boolean")
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
            or self.effect_performed is not False
        ):
            raise MacroSpineBridgeContractError(
                "macro spine receipt cannot grant authority or claim effects"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "reason": self.reason,
            "macro_id": self.macro_id,
            "macro_version": self.macro_version,
            "operation_id": self.operation_id,
            "operation_hash": self.operation_hash,
            "macro_spine_binding_sha256": self.macro_spine_binding_sha256,
            "action_binding_sha256": self.action_binding_sha256,
            "action_lease_sha256": self.action_lease_sha256,
            "leased_handoff_receipt_sha256": (
                self.leased_handoff_receipt_sha256
            ),
            "spine_receipt_id": self.spine_receipt_id,
            "spine_execution_status": self.spine_execution_status,
            "lease_consumed": self.lease_consumed,
            "replay_blocked": self.replay_blocked,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "effect_performed": self.effect_performed,
        }

    @property
    def receipt_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["receipt_sha256"] = self.receipt_sha256
        return payload


class MacroSpineBridge:
    """Delegate one LIVE macro operation through existing PhiOS leased execution."""

    def __init__(self) -> None:
        self._binder = GovernedActionBinder()
        self._handoff = GovernedLeasedExecutionHandoff()

    def execute(
        self,
        *,
        operation: Operation,
        macro_binding: MacroSpineBinding,
        plan: PlanState,
        binding: PlanActionBinding,
        payload: Mapping[str, Any],
        spine: PhiOSSpine,
        lease: ActionLease,
        verification: LeaseVerificationEvidence,
        current_authority_epoch_sha256: str,
        checked_at: str,
        mode: ExecutionMode = ExecutionMode.LIVE,
    ) -> MacroSpineReceipt:
        if mode is not ExecutionMode.LIVE:
            raise MacroSpineBridgeContractError(
                "v0.2 Spine bridge accepts LIVE execution only"
            )
        self._validate_scope(
            operation=operation,
            macro_binding=macro_binding,
            plan=plan,
            binding=binding,
            payload=payload,
            lease=lease,
        )

        handoff = self._handoff.execute(
            plan=plan,
            binding=binding,
            payload=payload,
            spine=spine,
            lease=lease,
            verification=verification,
            current_authority_epoch_sha256=current_authority_epoch_sha256,
            checked_at=checked_at,
        )
        spine_receipt_id, spine_execution_status = self._spine_outcome(
            handoff.inner_handoff
        )
        receipt = MacroSpineReceipt(
            status=handoff.status,
            reason=handoff.reason,
            macro_id=macro_binding.macro_id,
            macro_version=macro_binding.macro_version,
            operation_id=operation.operation_id,
            operation_hash=operation.operation_hash,
            macro_spine_binding_sha256=macro_binding.binding_sha256,
            action_binding_sha256=binding.binding_sha256,
            action_lease_sha256=lease.action_lease_sha256,
            leased_handoff_receipt_sha256=handoff.receipt_sha256,
            spine_receipt_id=spine_receipt_id,
            spine_execution_status=spine_execution_status,
            lease_consumed=handoff.lease_consumed,
            replay_blocked=handoff.replay_blocked,
        )
        spine.ledger.append_macro_receipt(receipt)
        return receipt

    def _validate_scope(
        self,
        *,
        operation: Operation,
        macro_binding: MacroSpineBinding,
        plan: PlanState,
        binding: PlanActionBinding,
        payload: Mapping[str, Any],
        lease: ActionLease,
    ) -> None:
        if operation.adapter_id != "phios.spine":
            raise MacroSpineBridgeContractError(
                "LIVE Spine operation requires adapter_id=phios.spine"
            )
        if operation.action != binding.capability_id:
            raise MacroSpineBridgeContractError(
                "macro operation action must equal bound Spine capability"
            )
        if operation.required_capabilities != binding.permissions_requested:
            raise MacroSpineBridgeContractError(
                "macro operation capabilities must equal bound permissions"
            )
        operation_payload_sha256 = self._binder.payload_sha256(operation.inputs)
        supplied_payload_sha256 = self._binder.payload_sha256(payload)
        if operation_payload_sha256 != supplied_payload_sha256:
            raise MacroSpineBridgeContractError(
                "macro operation inputs differ from supplied execution payload"
            )
        if supplied_payload_sha256 != binding.payload_sha256:
            raise MacroSpineBridgeContractError(
                "macro execution payload differs from action binding"
            )

        expected = {
            "operation_id": operation.operation_id,
            "operation_version": operation.operation_version,
            "operation_hash": operation.operation_hash,
            "plan_id": plan.plan_id,
            "plan_state_sha256": plan.state_sha256,
            "action_binding_sha256": binding.binding_sha256,
            "capability_id": binding.capability_id,
            "payload_sha256": binding.payload_sha256,
            "action_lease_sha256": lease.action_lease_sha256,
        }
        observed = {
            "operation_id": macro_binding.operation_id,
            "operation_version": macro_binding.operation_version,
            "operation_hash": macro_binding.operation_hash,
            "plan_id": macro_binding.plan_id,
            "plan_state_sha256": macro_binding.plan_state_sha256,
            "action_binding_sha256": macro_binding.action_binding_sha256,
            "capability_id": macro_binding.capability_id,
            "payload_sha256": macro_binding.payload_sha256,
            "action_lease_sha256": macro_binding.action_lease_sha256,
        }
        if observed != expected:
            raise MacroSpineBridgeContractError(
                "macro Spine binding does not match current execution scope"
            )

    @staticmethod
    def _spine_outcome(
        inner_handoff: dict[str, object] | None,
    ) -> tuple[str | None, str | None]:
        if inner_handoff is None:
            return None, None
        receipt_id = inner_handoff.get("spine_receipt_id")
        execution_status = inner_handoff.get("spine_execution_status")
        return (
            receipt_id if isinstance(receipt_id, str) else None,
            execution_status if isinstance(execution_status, str) else None,
        )
