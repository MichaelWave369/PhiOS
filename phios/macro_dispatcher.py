"""Governed DO dispatcher for Macro Runtime v0.5.

This layer turns one WAITING_OPERATION runner boundary into an exact,
zero-authority work package, delegates the real effect through the existing
MacroSpineBridge, records dispatch evidence, and returns an OperationResolution
that can resume the MacroRunner.

The dispatcher does not mint grants, leases, approvals, or execution authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from phios.action_lease import ActionLease
from phios.core.governed_action_binding import PlanActionBinding
from phios.core.governed_plan_adoption import PlanState
from phios.core.leased_execution_handoff import LeaseVerificationEvidence
from phios.macro_graph import MacroPlan, PlanInstruction, PlanOpcode
from phios.macro_runner import (
    MacroRunState,
    OperationResolution,
    ResolutionStatus,
    RunnerStatus,
)
from phios.macro_runtime import ExecutionMode, Operation
from phios.macro_spine_bridge import (
    MacroSpineBinding,
    MacroSpineBridge,
    MacroSpineReceipt,
)
from phios.spine.runtime import PhiOSSpine

OPERATION_WORK_PACKAGE_SCHEMA_VERSION = "phios.operation_work_package.v0.5"
DO_DISPATCH_RECEIPT_SCHEMA_VERSION = "phios.do_dispatch_receipt.v0.5"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class GovernedDoDispatcherContractError(ValueError):
    """Raised when a DO dispatch cannot prove exact scope safely."""


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 512,
) -> str:
    if not isinstance(value, str) or not value:
        raise GovernedDoDispatcherContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise GovernedDoDispatcherContractError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise GovernedDoDispatcherContractError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise GovernedDoDispatcherContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


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
        raise GovernedDoDispatcherContractError(
            "dispatcher payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_capabilities(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(
        _require_text(value, "required capability")
        for value in values
    )
    if tuple(sorted(set(normalized))) != normalized:
        raise GovernedDoDispatcherContractError(
            "required capabilities must be sorted and unique"
        )
    return normalized


@dataclass(frozen=True, slots=True)
class OperationWorkPackage:
    """Zero-authority package binding one paused runner DO to one Operation."""

    macro_id: str
    macro_version: str
    macro_plan_sha256: str
    macro_run_state_sha256: str
    instruction_index: int
    instruction_path: str
    operation_id: str
    operation_version: str
    operation_hash: str
    input_hash: str
    adapter_id: str
    action: str
    required_capabilities: tuple[str, ...]
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = OPERATION_WORK_PACKAGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != OPERATION_WORK_PACKAGE_SCHEMA_VERSION:
            raise GovernedDoDispatcherContractError(
                "unsupported operation work package schema"
            )
        _require_text(self.macro_id, "macro_id")
        _require_text(self.macro_version, "macro_version", maximum=128)
        _require_sha256(self.macro_plan_sha256, "macro_plan_sha256")
        _require_sha256(
            self.macro_run_state_sha256,
            "macro_run_state_sha256",
        )
        if isinstance(self.instruction_index, bool) or not isinstance(
            self.instruction_index,
            int,
        ):
            raise GovernedDoDispatcherContractError(
                "instruction_index must be an integer"
            )
        if self.instruction_index < 0:
            raise GovernedDoDispatcherContractError(
                "instruction_index must be non-negative"
            )
        _require_text(self.instruction_path, "instruction_path")
        _require_text(self.operation_id, "operation_id")
        _require_text(
            self.operation_version,
            "operation_version",
            maximum=128,
        )
        _require_sha256(self.operation_hash, "operation_hash")
        _require_sha256(self.input_hash, "input_hash")
        _require_text(self.adapter_id, "adapter_id")
        _require_text(self.action, "action")
        _canonical_capabilities(self.required_capabilities)
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise GovernedDoDispatcherContractError(
                "OperationWorkPackage cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "macro_id": self.macro_id,
            "macro_version": self.macro_version,
            "macro_plan_sha256": self.macro_plan_sha256,
            "macro_run_state_sha256": self.macro_run_state_sha256,
            "instruction_index": self.instruction_index,
            "instruction_path": self.instruction_path,
            "operation_id": self.operation_id,
            "operation_version": self.operation_version,
            "operation_hash": self.operation_hash,
            "input_hash": self.input_hash,
            "adapter_id": self.adapter_id,
            "action": self.action,
            "required_capabilities": list(self.required_capabilities),
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def work_package_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["work_package_sha256"] = self.work_package_sha256
        return payload


@dataclass(frozen=True, slots=True)
class DoDispatchReceipt:
    """Immutable bridge evidence from runner work package to macro Spine receipt."""

    macro_id: str
    macro_version: str
    macro_plan_sha256: str
    macro_run_state_sha256: str
    instruction_path: str
    operation_hash: str
    work_package_sha256: str
    macro_spine_binding_sha256: str
    macro_spine_receipt_sha256: str
    macro_spine_status: str
    macro_spine_reason: str
    spine_receipt_id: str | None
    resolution_status: ResolutionStatus
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    effect_performed: bool = False
    schema_version: str = DO_DISPATCH_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DO_DISPATCH_RECEIPT_SCHEMA_VERSION:
            raise GovernedDoDispatcherContractError(
                "unsupported DO dispatch receipt schema"
            )
        _require_text(self.macro_id, "macro_id")
        _require_text(self.macro_version, "macro_version", maximum=128)
        _require_sha256(self.macro_plan_sha256, "macro_plan_sha256")
        _require_sha256(
            self.macro_run_state_sha256,
            "macro_run_state_sha256",
        )
        _require_text(self.instruction_path, "instruction_path")
        _require_sha256(self.operation_hash, "operation_hash")
        _require_sha256(self.work_package_sha256, "work_package_sha256")
        _require_sha256(
            self.macro_spine_binding_sha256,
            "macro_spine_binding_sha256",
        )
        _require_sha256(
            self.macro_spine_receipt_sha256,
            "macro_spine_receipt_sha256",
        )
        _require_text(self.macro_spine_status, "macro_spine_status")
        _require_text(self.macro_spine_reason, "macro_spine_reason")
        if self.spine_receipt_id is not None:
            _require_text(self.spine_receipt_id, "spine_receipt_id")
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
            or self.effect_performed is not False
        ):
            raise GovernedDoDispatcherContractError(
                "DoDispatchReceipt cannot grant authority or claim effects"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "macro_id": self.macro_id,
            "macro_version": self.macro_version,
            "macro_plan_sha256": self.macro_plan_sha256,
            "macro_run_state_sha256": self.macro_run_state_sha256,
            "instruction_path": self.instruction_path,
            "operation_hash": self.operation_hash,
            "work_package_sha256": self.work_package_sha256,
            "macro_spine_binding_sha256": (
                self.macro_spine_binding_sha256
            ),
            "macro_spine_receipt_sha256": (
                self.macro_spine_receipt_sha256
            ),
            "macro_spine_status": self.macro_spine_status,
            "macro_spine_reason": self.macro_spine_reason,
            "spine_receipt_id": self.spine_receipt_id,
            "resolution_status": self.resolution_status.value,
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


@dataclass(frozen=True, slots=True)
class DoDispatchResult:
    work_package: OperationWorkPackage
    macro_spine_receipt: MacroSpineReceipt
    dispatch_receipt: DoDispatchReceipt
    operation_resolution: OperationResolution


class GovernedDoDispatcher:
    """Package and dispatch one exact WAITING_OPERATION boundary."""

    def __init__(self) -> None:
        self._bridge = MacroSpineBridge()

    def package(
        self,
        *,
        macro_plan: MacroPlan,
        run_state: MacroRunState,
        operation: Operation,
    ) -> OperationWorkPackage:
        instruction = self._validate_waiting_operation(
            macro_plan=macro_plan,
            run_state=run_state,
            operation=operation,
        )
        return OperationWorkPackage(
            macro_id=macro_plan.macro_id,
            macro_version=macro_plan.macro_version,
            macro_plan_sha256=macro_plan.plan_sha256,
            macro_run_state_sha256=run_state.state_sha256,
            instruction_index=instruction.index,
            instruction_path=instruction.path,
            operation_id=operation.operation_id,
            operation_version=operation.operation_version,
            operation_hash=operation.operation_hash,
            input_hash=operation.input_hash,
            adapter_id=operation.adapter_id,
            action=operation.action,
            required_capabilities=operation.required_capabilities,
        )

    def dispatch(
        self,
        *,
        work_package: OperationWorkPackage,
        macro_plan: MacroPlan,
        run_state: MacroRunState,
        operation: Operation,
        plan: PlanState,
        binding: PlanActionBinding,
        payload: Mapping[str, Any],
        spine: PhiOSSpine,
        lease: ActionLease,
        verification: LeaseVerificationEvidence,
        current_authority_epoch_sha256: str,
        checked_at: str,
    ) -> DoDispatchResult:
        expected = self.package(
            macro_plan=macro_plan,
            run_state=run_state,
            operation=operation,
        )
        if work_package != expected:
            raise GovernedDoDispatcherContractError(
                "operation work package does not match current runner boundary"
            )

        macro_binding = MacroSpineBinding.build(
            macro_id=macro_plan.macro_id,
            macro_version=macro_plan.macro_version,
            operation=operation,
            plan=plan,
            binding=binding,
            lease=lease,
        )
        macro_receipt = self._bridge.execute(
            operation=operation,
            macro_binding=macro_binding,
            plan=plan,
            binding=binding,
            payload=payload,
            spine=spine,
            lease=lease,
            verification=verification,
            current_authority_epoch_sha256=(
                current_authority_epoch_sha256
            ),
            checked_at=checked_at,
            mode=ExecutionMode.LIVE,
        )
        resolution_status = self._resolution_status(macro_receipt)
        dispatch_receipt = DoDispatchReceipt(
            macro_id=macro_plan.macro_id,
            macro_version=macro_plan.macro_version,
            macro_plan_sha256=macro_plan.plan_sha256,
            macro_run_state_sha256=run_state.state_sha256,
            instruction_path=work_package.instruction_path,
            operation_hash=operation.operation_hash,
            work_package_sha256=work_package.work_package_sha256,
            macro_spine_binding_sha256=macro_binding.binding_sha256,
            macro_spine_receipt_sha256=macro_receipt.receipt_sha256,
            macro_spine_status=macro_receipt.status,
            macro_spine_reason=macro_receipt.reason,
            spine_receipt_id=macro_receipt.spine_receipt_id,
            resolution_status=resolution_status,
        )
        spine.ledger.append_macro_dispatch_receipt(dispatch_receipt)

        operation_resolution = OperationResolution(
            instruction_path=work_package.instruction_path,
            operation_hash=operation.operation_hash,
            status=resolution_status,
            receipt_sha256=dispatch_receipt.receipt_sha256,
        )
        return DoDispatchResult(
            work_package=work_package,
            macro_spine_receipt=macro_receipt,
            dispatch_receipt=dispatch_receipt,
            operation_resolution=operation_resolution,
        )

    def _validate_waiting_operation(
        self,
        *,
        macro_plan: MacroPlan,
        run_state: MacroRunState,
        operation: Operation,
    ) -> PlanInstruction:
        if run_state.status is not RunnerStatus.WAITING_OPERATION:
            raise GovernedDoDispatcherContractError(
                "runner must be WAITING_OPERATION before DO dispatch"
            )
        if run_state.plan_sha256 != macro_plan.plan_sha256:
            raise GovernedDoDispatcherContractError(
                "runner plan hash does not match macro plan"
            )
        if (
            run_state.macro_id != macro_plan.macro_id
            or run_state.macro_version != macro_plan.macro_version
        ):
            raise GovernedDoDispatcherContractError(
                "runner macro identity does not match macro plan"
            )
        if run_state.cursor >= len(macro_plan.instructions):
            raise GovernedDoDispatcherContractError(
                "runner cursor does not reference an instruction"
            )

        instruction = macro_plan.instructions[run_state.cursor]
        if instruction.opcode is not PlanOpcode.DO:
            raise GovernedDoDispatcherContractError(
                "WAITING_OPERATION cursor must reference DO"
            )
        waiting = run_state.waiting_on or {}
        if (
            waiting.get("instruction_path") != instruction.path
            or waiting.get("opcode") != PlanOpcode.DO.value
        ):
            raise GovernedDoDispatcherContractError(
                "runner waiting boundary does not match current DO"
            )

        self._validate_instruction_operation(
            instruction=instruction,
            operation=operation,
        )
        return instruction

    @staticmethod
    def _validate_instruction_operation(
        *,
        instruction: PlanInstruction,
        operation: Operation,
    ) -> None:
        expected_capabilities = instruction.payload.get(
            "required_capabilities"
        )
        expected = {
            "operation_id": instruction.payload.get("operation_id"),
            "operation_version": instruction.payload.get(
                "operation_version"
            ),
            "operation_hash": instruction.payload.get("operation_hash"),
            "adapter_id": instruction.payload.get("adapter_id"),
            "action": instruction.payload.get("action"),
            "required_capabilities": expected_capabilities,
        }
        observed = {
            "operation_id": operation.operation_id,
            "operation_version": operation.operation_version,
            "operation_hash": operation.operation_hash,
            "adapter_id": operation.adapter_id,
            "action": operation.action,
            "required_capabilities": list(
                operation.required_capabilities
            ),
        }
        if expected != observed:
            raise GovernedDoDispatcherContractError(
                "operation does not match planned DO instruction"
            )

    @staticmethod
    def _resolution_status(
        receipt: MacroSpineReceipt,
    ) -> ResolutionStatus:
        if receipt.status == "SUCCEEDED":
            return ResolutionStatus.SUCCEEDED
        if receipt.status == "FAILED":
            return ResolutionStatus.FAILED
        return ResolutionStatus.HELD
