"""Pause-capable zero-authority MacroPlan runner.

v0.4 advances deterministic control flow but never executes a DO operation,
grants approval, creates a real checkpoint, evaluates an external condition,
or invokes a child macro by itself. Missing evidence pauses the run.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from phios.macro_graph import MacroPlan, PlanInstruction, PlanOpcode

MACRO_RUN_STATE_SCHEMA_VERSION = "phios.macro_run_state.v0.4"
MAX_ADVANCE_TRANSITIONS = 50_000
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class MacroRunnerContractError(ValueError):
    """Raised when runner inputs or state cannot be verified safely."""


class RunnerStatus(StrEnum):
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_OPERATION = "WAITING_OPERATION"
    WAITING_CONDITION = "WAITING_CONDITION"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    WAITING_CALLEE = "WAITING_CALLEE"
    CHECKPOINTING = "CHECKPOINTING"
    WAITING_COLLECTION = "WAITING_COLLECTION"
    COMPLETED = "COMPLETED"
    HELD = "HELD"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class ResolutionStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    HELD = "HELD"
    FAILED = "FAILED"


TERMINAL_STATUSES = {
    RunnerStatus.COMPLETED,
    RunnerStatus.FAILED,
    RunnerStatus.ABORTED,
}


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 512,
) -> str:
    if not isinstance(value, str) or not value:
        raise MacroRunnerContractError(f"{field} must be a non-empty string")
    if len(value) > maximum:
        raise MacroRunnerContractError(f"{field} exceeds {maximum} characters")
    if any(ord(char) < 32 for char in value):
        raise MacroRunnerContractError(f"{field} contains control characters")
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise MacroRunnerContractError(
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
        raise MacroRunnerContractError(
            "macro runner state must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_name_tuple(
    values: tuple[str, ...],
    field: str,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if not allow_empty and not values:
        raise MacroRunnerContractError(f"{field} must not be empty")
    normalized = tuple(_require_text(value, f"{field} item") for value in values)
    if tuple(sorted(set(normalized))) != normalized:
        raise MacroRunnerContractError(
            f"{field} must be sorted and unique"
        )
    return normalized


@dataclass(frozen=True, slots=True)
class ConditionResolution:
    condition_id: str
    value: bool
    evidence_ref_sha256: str

    def __post_init__(self) -> None:
        _require_text(self.condition_id, "condition_id")
        if not isinstance(self.value, bool):
            raise MacroRunnerContractError("condition value must be Boolean")
        _require_sha256(self.evidence_ref_sha256, "condition evidence_ref_sha256")


@dataclass(frozen=True, slots=True)
class OperationResolution:
    instruction_path: str
    operation_hash: str
    status: ResolutionStatus
    receipt_sha256: str

    def __post_init__(self) -> None:
        _require_text(self.instruction_path, "operation instruction_path")
        _require_sha256(self.operation_hash, "operation_hash")
        _require_sha256(self.receipt_sha256, "operation receipt_sha256")


@dataclass(frozen=True, slots=True)
class ApprovalResolution:
    barrier_id: str
    required_capabilities: tuple[str, ...]
    approved: bool
    evidence_ref_sha256: str

    def __post_init__(self) -> None:
        _require_text(self.barrier_id, "approval barrier_id")
        _canonical_name_tuple(
            self.required_capabilities,
            "approval required_capabilities",
            allow_empty=False,
        )
        if not isinstance(self.approved, bool):
            raise MacroRunnerContractError("approved must be Boolean")
        _require_sha256(self.evidence_ref_sha256, "approval evidence_ref_sha256")


@dataclass(frozen=True, slots=True)
class CallResolution:
    instruction_path: str
    macro_id: str
    macro_version: str
    arguments_sha256: str
    status: ResolutionStatus
    receipt_sha256: str

    def __post_init__(self) -> None:
        _require_text(self.instruction_path, "call instruction_path")
        _require_text(self.macro_id, "call macro_id")
        _require_text(self.macro_version, "call macro_version", maximum=128)
        _require_sha256(self.arguments_sha256, "call arguments_sha256")
        _require_sha256(self.receipt_sha256, "call receipt_sha256")


@dataclass(frozen=True, slots=True)
class CheckpointResolution:
    instruction_path: str
    label: str
    status: ResolutionStatus
    receipt_sha256: str

    def __post_init__(self) -> None:
        _require_text(self.instruction_path, "checkpoint instruction_path")
        _require_text(self.label, "checkpoint label")
        _require_sha256(self.receipt_sha256, "checkpoint receipt_sha256")


@dataclass(frozen=True, slots=True)
class CollectionResolution:
    collection_ref: str
    items: tuple[Any, ...]
    evidence_ref_sha256: str

    def __post_init__(self) -> None:
        _require_text(self.collection_ref, "collection_ref")
        _canonical_sha256(self.items)
        _require_sha256(
            self.evidence_ref_sha256,
            "collection evidence_ref_sha256",
        )


@dataclass(frozen=True, slots=True)
class RunnerInputs:
    conditions: tuple[ConditionResolution, ...] = ()
    operations: tuple[OperationResolution, ...] = ()
    approvals: tuple[ApprovalResolution, ...] = ()
    calls: tuple[CallResolution, ...] = ()
    checkpoints: tuple[CheckpointResolution, ...] = ()
    collections: tuple[CollectionResolution, ...] = ()


@dataclass(frozen=True, slots=True)
class MacroRunState:
    """Deterministic zero-authority snapshot of one compiled macro run."""

    macro_id: str
    macro_version: str
    plan_sha256: str
    cursor: int
    status: RunnerStatus
    reason: str
    loop_iterations: tuple[tuple[str, int], ...] = ()
    foreach_indices: tuple[tuple[str, int], ...] = ()
    variables: dict[str, Any] | None = None
    waiting_on: dict[str, object] | None = None
    last_instruction_path: str | None = None
    transitions: int = 0
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = MACRO_RUN_STATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MACRO_RUN_STATE_SCHEMA_VERSION:
            raise MacroRunnerContractError(
                "unsupported macro run state schema"
            )
        _require_text(self.macro_id, "macro_id")
        _require_text(self.macro_version, "macro_version", maximum=128)
        _require_sha256(self.plan_sha256, "plan_sha256")
        if isinstance(self.cursor, bool) or not isinstance(self.cursor, int):
            raise MacroRunnerContractError("cursor must be an integer")
        if self.cursor < 0:
            raise MacroRunnerContractError("cursor must be non-negative")
        _require_text(self.reason, "reason")
        if self.last_instruction_path is not None:
            _require_text(
                self.last_instruction_path,
                "last_instruction_path",
            )
        if isinstance(self.transitions, bool) or not isinstance(
            self.transitions,
            int,
        ):
            raise MacroRunnerContractError("transitions must be an integer")
        if self.transitions < 0:
            raise MacroRunnerContractError(
                "transitions must be non-negative"
            )
        for key, count in self.loop_iterations:
            _require_sha256(key, "loop source_step_sha256")
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise MacroRunnerContractError(
                    "loop iteration counts must be non-negative integers"
                )
        for key, index in self.foreach_indices:
            _require_sha256(key, "foreach source_step_sha256")
            if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                raise MacroRunnerContractError(
                    "foreach indices must be non-negative integers"
                )
        _canonical_sha256(self.variables or {})
        _canonical_sha256(self.waiting_on or {})
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise MacroRunnerContractError(
                "MacroRunState cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "macro_id": self.macro_id,
            "macro_version": self.macro_version,
            "plan_sha256": self.plan_sha256,
            "cursor": self.cursor,
            "status": self.status.value,
            "reason": self.reason,
            "loop_iterations": [
                [key, count] for key, count in self.loop_iterations
            ],
            "foreach_indices": [
                [key, index] for key, index in self.foreach_indices
            ],
            "variables": self.variables or {},
            "waiting_on": self.waiting_on or {},
            "last_instruction_path": self.last_instruction_path,
            "transitions": self.transitions,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def state_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["state_sha256"] = self.state_sha256
        return payload


class MacroRunner:
    """Advance a MacroPlan until completion or the next unresolved boundary."""

    def start(self, plan: MacroPlan) -> MacroRunState:
        self._validate_plan(plan)
        return self._state(
            plan=plan,
            cursor=0,
            status=RunnerStatus.READY,
            reason="plan_ready",
            loops={},
            foreach={},
            variables={},
            waiting_on={},
            last_instruction_path=None,
            transitions=0,
        )

    def abort(
        self,
        plan: MacroPlan,
        state: MacroRunState,
        *,
        reason: str,
    ) -> MacroRunState:
        self._validate_resume(plan, state)
        return self._state(
            plan=plan,
            cursor=state.cursor,
            status=RunnerStatus.ABORTED,
            reason=_require_text(reason, "abort reason"),
            loops=dict(state.loop_iterations),
            foreach=dict(state.foreach_indices),
            variables=dict(state.variables or {}),
            waiting_on={},
            last_instruction_path=state.last_instruction_path,
            transitions=state.transitions,
        )

    def advance(
        self,
        plan: MacroPlan,
        state: MacroRunState,
        inputs: RunnerInputs | None = None,
        *,
        max_transitions: int = MAX_ADVANCE_TRANSITIONS,
    ) -> MacroRunState:
        self._validate_resume(plan, state)
        if state.status in TERMINAL_STATUSES:
            return state
        if isinstance(max_transitions, bool) or not isinstance(
            max_transitions,
            int,
        ):
            raise MacroRunnerContractError(
                "max_transitions must be an integer"
            )
        if max_transitions < 1 or max_transitions > MAX_ADVANCE_TRANSITIONS:
            raise MacroRunnerContractError(
                f"max_transitions must be between 1 and {MAX_ADVANCE_TRANSITIONS}"
            )

        supplied = inputs or RunnerInputs()
        conditions = self._unique_index(
            supplied.conditions,
            key=lambda item: item.condition_id,
            label="condition resolution",
        )
        operations = self._unique_index(
            supplied.operations,
            key=lambda item: item.instruction_path,
            label="operation resolution",
        )
        approvals = self._unique_index(
            supplied.approvals,
            key=lambda item: item.barrier_id,
            label="approval resolution",
        )
        calls = self._unique_index(
            supplied.calls,
            key=lambda item: item.instruction_path,
            label="call resolution",
        )
        checkpoints = self._unique_index(
            supplied.checkpoints,
            key=lambda item: item.instruction_path,
            label="checkpoint resolution",
        )
        collections = self._unique_index(
            supplied.collections,
            key=lambda item: item.collection_ref,
            label="collection resolution",
        )

        cursor = state.cursor
        loops = dict(state.loop_iterations)
        foreach = dict(state.foreach_indices)
        variables = dict(state.variables or {})
        transitions = state.transitions
        used = 0
        last_path = state.last_instruction_path

        while True:
            if cursor >= len(plan.instructions):
                return self._state(
                    plan=plan,
                    cursor=cursor,
                    status=RunnerStatus.COMPLETED,
                    reason="plan_completed",
                    loops=loops,
                    foreach=foreach,
                    variables=variables,
                    waiting_on={},
                    last_instruction_path=last_path,
                    transitions=transitions,
                )
            if used >= max_transitions:
                return self._state(
                    plan=plan,
                    cursor=cursor,
                    status=RunnerStatus.HELD,
                    reason="advance_transition_budget_exhausted",
                    loops=loops,
                    foreach=foreach,
                    variables=variables,
                    waiting_on={"cursor": cursor},
                    last_instruction_path=last_path,
                    transitions=transitions,
                )

            instruction = plan.instructions[cursor]
            used += 1
            transitions += 1
            last_path = instruction.path

            if instruction.opcode is PlanOpcode.DO:
                resolution = operations.get(instruction.path)
                if resolution is None:
                    return self._pause(
                        plan=plan,
                        cursor=cursor,
                        status=RunnerStatus.WAITING_OPERATION,
                        reason="operation_resolution_required",
                        instruction=instruction,
                        loops=loops,
                        foreach=foreach,
                        variables=variables,
                        transitions=transitions,
                    )
                expected_hash = self._payload_text(
                    instruction,
                    "operation_hash",
                )
                if resolution.operation_hash != expected_hash:
                    return self._terminal_boundary(
                        plan=plan,
                        cursor=cursor,
                        status=RunnerStatus.HELD,
                        reason="operation_resolution_scope_mismatch",
                        instruction=instruction,
                        loops=loops,
                        foreach=foreach,
                        variables=variables,
                        transitions=transitions,
                    )
                boundary = self._resolution_boundary(
                    plan=plan,
                    cursor=cursor,
                    instruction=instruction,
                    status=resolution.status,
                    held_reason="operation_held",
                    failed_reason="operation_failed",
                    loops=loops,
                    foreach=foreach,
                    variables=variables,
                    transitions=transitions,
                )
                if boundary is not None:
                    return boundary
                cursor += 1
                continue

            if instruction.opcode is PlanOpcode.IF_BEGIN:
                condition_id = self._payload_text(
                    instruction,
                    "condition_id",
                )
                resolution = conditions.get(condition_id)
                if resolution is None:
                    return self._pause(
                        plan=plan,
                        cursor=cursor,
                        status=RunnerStatus.WAITING_CONDITION,
                        reason="condition_resolution_required",
                        instruction=instruction,
                        loops=loops,
                        foreach=foreach,
                        variables=variables,
                        transitions=transitions,
                        extra={"condition_id": condition_id},
                    )
                if resolution.value:
                    cursor += 1
                else:
                    else_index = self._find_forward(
                        plan,
                        cursor,
                        PlanOpcode.ELSE,
                        instruction.source_step_sha256,
                    )
                    cursor = else_index + 1
                continue

            if instruction.opcode is PlanOpcode.ELSE:
                end_index = self._find_forward(
                    plan,
                    cursor,
                    PlanOpcode.IF_END,
                    instruction.source_step_sha256,
                )
                cursor = end_index + 1
                continue

            if instruction.opcode is PlanOpcode.IF_END:
                cursor += 1
                continue

            if instruction.opcode is PlanOpcode.LOOP_BEGIN:
                maximum = self._payload_int(
                    instruction,
                    "max_iterations",
                )
                count = loops.get(instruction.source_step_sha256, 0)
                if count >= maximum:
                    end_index = self._find_forward(
                        plan,
                        cursor,
                        PlanOpcode.LOOP_END,
                        instruction.source_step_sha256,
                    )
                    cursor = end_index + 1
                else:
                    cursor += 1
                continue

            if instruction.opcode is PlanOpcode.LOOP_END:
                key = instruction.source_step_sha256
                loops[key] = loops.get(key, 0) + 1
                begin_index = self._find_backward(
                    plan,
                    cursor,
                    PlanOpcode.LOOP_BEGIN,
                    key,
                )
                cursor = begin_index
                continue

            if instruction.opcode is PlanOpcode.FOREACH_BEGIN:
                collection_ref = self._payload_text(
                    instruction,
                    "collection_ref",
                )
                item_name = self._payload_text(
                    instruction,
                    "item_name",
                )
                maximum = self._payload_int(
                    instruction,
                    "max_items",
                )
                resolution = collections.get(collection_ref)
                if resolution is None:
                    return self._pause(
                        plan=plan,
                        cursor=cursor,
                        status=RunnerStatus.WAITING_COLLECTION,
                        reason="collection_resolution_required",
                        instruction=instruction,
                        loops=loops,
                        foreach=foreach,
                        variables=variables,
                        transitions=transitions,
                        extra={"collection_ref": collection_ref},
                    )
                if len(resolution.items) > maximum:
                    return self._terminal_boundary(
                        plan=plan,
                        cursor=cursor,
                        status=RunnerStatus.HELD,
                        reason="collection_bound_exceeded",
                        instruction=instruction,
                        loops=loops,
                        foreach=foreach,
                        variables=variables,
                        transitions=transitions,
                    )
                key = instruction.source_step_sha256
                index = foreach.get(key, 0)
                if index >= len(resolution.items):
                    variables.pop(item_name, None)
                    end_index = self._find_forward(
                        plan,
                        cursor,
                        PlanOpcode.FOREACH_END,
                        key,
                    )
                    cursor = end_index + 1
                else:
                    variables[item_name] = resolution.items[index]
                    cursor += 1
                continue

            if instruction.opcode is PlanOpcode.FOREACH_END:
                key = instruction.source_step_sha256
                foreach[key] = foreach.get(key, 0) + 1
                begin_index = self._find_backward(
                    plan,
                    cursor,
                    PlanOpcode.FOREACH_BEGIN,
                    key,
                )
                cursor = begin_index
                continue

            if instruction.opcode is PlanOpcode.CALL:
                resolution = calls.get(instruction.path)
                if resolution is None:
                    return self._pause(
                        plan=plan,
                        cursor=cursor,
                        status=RunnerStatus.WAITING_CALLEE,
                        reason="callee_resolution_required",
                        instruction=instruction,
                        loops=loops,
                        foreach=foreach,
                        variables=variables,
                        transitions=transitions,
                    )
                expected = (
                    self._payload_text(instruction, "macro_id"),
                    self._payload_text(instruction, "macro_version"),
                    self._payload_text(instruction, "arguments_sha256"),
                )
                observed = (
                    resolution.macro_id,
                    resolution.macro_version,
                    resolution.arguments_sha256,
                )
                if observed != expected:
                    return self._terminal_boundary(
                        plan=plan,
                        cursor=cursor,
                        status=RunnerStatus.HELD,
                        reason="callee_resolution_scope_mismatch",
                        instruction=instruction,
                        loops=loops,
                        foreach=foreach,
                        variables=variables,
                        transitions=transitions,
                    )
                boundary = self._resolution_boundary(
                    plan=plan,
                    cursor=cursor,
                    instruction=instruction,
                    status=resolution.status,
                    held_reason="callee_held",
                    failed_reason="callee_failed",
                    loops=loops,
                    foreach=foreach,
                    variables=variables,
                    transitions=transitions,
                )
                if boundary is not None:
                    return boundary
                cursor += 1
                continue

            if instruction.opcode is PlanOpcode.CHECKPOINT:
                resolution = checkpoints.get(instruction.path)
                if resolution is None:
                    return self._pause(
                        plan=plan,
                        cursor=cursor,
                        status=RunnerStatus.CHECKPOINTING,
                        reason="checkpoint_resolution_required",
                        instruction=instruction,
                        loops=loops,
                        foreach=foreach,
                        variables=variables,
                        transitions=transitions,
                    )
                label = self._payload_text(instruction, "label")
                if resolution.label != label:
                    return self._terminal_boundary(
                        plan=plan,
                        cursor=cursor,
                        status=RunnerStatus.HELD,
                        reason="checkpoint_resolution_scope_mismatch",
                        instruction=instruction,
                        loops=loops,
                        foreach=foreach,
                        variables=variables,
                        transitions=transitions,
                    )
                boundary = self._resolution_boundary(
                    plan=plan,
                    cursor=cursor,
                    instruction=instruction,
                    status=resolution.status,
                    held_reason="checkpoint_held",
                    failed_reason="checkpoint_failed",
                    loops=loops,
                    foreach=foreach,
                    variables=variables,
                    transitions=transitions,
                )
                if boundary is not None:
                    return boundary
                cursor += 1
                continue

            if instruction.opcode is PlanOpcode.APPROVE:
                barrier_id = self._payload_text(
                    instruction,
                    "barrier_id",
                )
                resolution = approvals.get(barrier_id)
                if resolution is None:
                    return self._pause(
                        plan=plan,
                        cursor=cursor,
                        status=RunnerStatus.WAITING_APPROVAL,
                        reason="approval_resolution_required",
                        instruction=instruction,
                        loops=loops,
                        foreach=foreach,
                        variables=variables,
                        transitions=transitions,
                        extra={"barrier_id": barrier_id},
                    )
                required = tuple(
                    self._payload_string_list(
                        instruction,
                        "required_capabilities",
                    )
                )
                if resolution.required_capabilities != required:
                    return self._terminal_boundary(
                        plan=plan,
                        cursor=cursor,
                        status=RunnerStatus.HELD,
                        reason="approval_resolution_scope_mismatch",
                        instruction=instruction,
                        loops=loops,
                        foreach=foreach,
                        variables=variables,
                        transitions=transitions,
                    )
                if not resolution.approved:
                    return self._terminal_boundary(
                        plan=plan,
                        cursor=cursor,
                        status=RunnerStatus.HELD,
                        reason="approval_not_granted",
                        instruction=instruction,
                        loops=loops,
                        foreach=foreach,
                        variables=variables,
                        transitions=transitions,
                    )
                cursor += 1
                continue

            raise MacroRunnerContractError(
                f"unsupported plan opcode: {instruction.opcode}"
            )

    @staticmethod
    def _unique_index(
        values: tuple[Any, ...],
        *,
        key: Any,
        label: str,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for value in values:
            identity = key(value)
            if identity in result:
                raise MacroRunnerContractError(
                    f"duplicate {label}: {identity}"
                )
            result[identity] = value
        return result

    @staticmethod
    def _validate_plan(plan: MacroPlan) -> None:
        if not isinstance(plan, MacroPlan):
            raise MacroRunnerContractError("plan must be a MacroPlan")

    def _validate_resume(
        self,
        plan: MacroPlan,
        state: MacroRunState,
    ) -> None:
        self._validate_plan(plan)
        if not isinstance(state, MacroRunState):
            raise MacroRunnerContractError(
                "state must be a MacroRunState"
            )
        if state.plan_sha256 != plan.plan_sha256:
            raise MacroRunnerContractError(
                "run state plan hash does not match supplied plan"
            )
        if (
            state.macro_id != plan.macro_id
            or state.macro_version != plan.macro_version
        ):
            raise MacroRunnerContractError(
                "run state macro identity does not match supplied plan"
            )
        if state.cursor > len(plan.instructions):
            raise MacroRunnerContractError(
                "run state cursor exceeds plan instruction count"
            )

    @staticmethod
    def _payload_text(
        instruction: PlanInstruction,
        key: str,
    ) -> str:
        value = instruction.payload.get(key)
        return _require_text(value, f"{instruction.opcode.value}.{key}")

    @staticmethod
    def _payload_int(
        instruction: PlanInstruction,
        key: str,
    ) -> int:
        value = instruction.payload.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise MacroRunnerContractError(
                f"{instruction.opcode.value}.{key} must be an integer"
            )
        return value

    @staticmethod
    def _payload_string_list(
        instruction: PlanInstruction,
        key: str,
    ) -> list[str]:
        value = instruction.payload.get(key)
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item for item in value
        ):
            raise MacroRunnerContractError(
                f"{instruction.opcode.value}.{key} must be a string list"
            )
        return value

    @staticmethod
    def _find_forward(
        plan: MacroPlan,
        start: int,
        opcode: PlanOpcode,
        source_hash: str,
    ) -> int:
        for index in range(start + 1, len(plan.instructions)):
            candidate = plan.instructions[index]
            if (
                candidate.opcode is opcode
                and candidate.source_step_sha256 == source_hash
            ):
                return index
        raise MacroRunnerContractError(
            f"matching {opcode.value} marker not found"
        )

    @staticmethod
    def _find_backward(
        plan: MacroPlan,
        start: int,
        opcode: PlanOpcode,
        source_hash: str,
    ) -> int:
        for index in range(start - 1, -1, -1):
            candidate = plan.instructions[index]
            if (
                candidate.opcode is opcode
                and candidate.source_step_sha256 == source_hash
            ):
                return index
        raise MacroRunnerContractError(
            f"matching {opcode.value} marker not found"
        )

    def _resolution_boundary(
        self,
        *,
        plan: MacroPlan,
        cursor: int,
        instruction: PlanInstruction,
        status: ResolutionStatus,
        held_reason: str,
        failed_reason: str,
        loops: dict[str, int],
        foreach: dict[str, int],
        variables: dict[str, Any],
        transitions: int,
    ) -> MacroRunState | None:
        if status is ResolutionStatus.SUCCEEDED:
            return None
        if status is ResolutionStatus.HELD:
            return self._terminal_boundary(
                plan=plan,
                cursor=cursor,
                status=RunnerStatus.HELD,
                reason=held_reason,
                instruction=instruction,
                loops=loops,
                foreach=foreach,
                variables=variables,
                transitions=transitions,
            )
        return self._terminal_boundary(
            plan=plan,
            cursor=cursor,
            status=RunnerStatus.FAILED,
            reason=failed_reason,
            instruction=instruction,
            loops=loops,
            foreach=foreach,
            variables=variables,
            transitions=transitions,
        )

    def _pause(
        self,
        *,
        plan: MacroPlan,
        cursor: int,
        status: RunnerStatus,
        reason: str,
        instruction: PlanInstruction,
        loops: dict[str, int],
        foreach: dict[str, int],
        variables: dict[str, Any],
        transitions: int,
        extra: dict[str, object] | None = None,
    ) -> MacroRunState:
        waiting: dict[str, object] = {
            "instruction_path": instruction.path,
            "opcode": instruction.opcode.value,
        }
        if extra:
            waiting.update(extra)
        return self._state(
            plan=plan,
            cursor=cursor,
            status=status,
            reason=reason,
            loops=loops,
            foreach=foreach,
            variables=variables,
            waiting_on=waiting,
            last_instruction_path=instruction.path,
            transitions=transitions,
        )

    def _terminal_boundary(
        self,
        *,
        plan: MacroPlan,
        cursor: int,
        status: RunnerStatus,
        reason: str,
        instruction: PlanInstruction,
        loops: dict[str, int],
        foreach: dict[str, int],
        variables: dict[str, Any],
        transitions: int,
    ) -> MacroRunState:
        return self._state(
            plan=plan,
            cursor=cursor,
            status=status,
            reason=reason,
            loops=loops,
            foreach=foreach,
            variables=variables,
            waiting_on={
                "instruction_path": instruction.path,
                "opcode": instruction.opcode.value,
            },
            last_instruction_path=instruction.path,
            transitions=transitions,
        )

    @staticmethod
    def _state(
        *,
        plan: MacroPlan,
        cursor: int,
        status: RunnerStatus,
        reason: str,
        loops: dict[str, int],
        foreach: dict[str, int],
        variables: dict[str, Any],
        waiting_on: dict[str, object],
        last_instruction_path: str | None,
        transitions: int,
    ) -> MacroRunState:
        return MacroRunState(
            macro_id=plan.macro_id,
            macro_version=plan.macro_version,
            plan_sha256=plan.plan_sha256,
            cursor=cursor,
            status=status,
            reason=reason,
            loop_iterations=tuple(sorted(loops.items())),
            foreach_indices=tuple(sorted(foreach.items())),
            variables=dict(variables),
            waiting_on=dict(waiting_on),
            last_instruction_path=last_instruction_path,
            transitions=transitions,
        )
