"""Zero-authority MacroDefinition and deterministic structured graph planner.

v0.3 introduces a bounded declarative automation language. Planning describes
work but never grants permission to perform it. Real LIVE effects still require
the v0.2 MacroSpineBridge and existing PhiOS authority path.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeAlias

from phios.macro_runtime import Operation

MACRO_DEFINITION_SCHEMA_VERSION = "phios.macro_definition.v0.3"
MACRO_PLAN_SCHEMA_VERSION = "phios.macro_plan.v0.3"
MAX_NESTING_DEPTH = 32
MAX_STATIC_STEPS = 4096
MAX_LOOP_ITERATIONS = 10_000
MAX_FOREACH_ITEMS = 10_000


class MacroGraphContractError(ValueError):
    """Raised when a macro definition cannot be planned safely."""


class PlanOpcode(StrEnum):
    DO = "DO"
    IF_BEGIN = "IF_BEGIN"
    ELSE = "ELSE"
    IF_END = "IF_END"
    LOOP_BEGIN = "LOOP_BEGIN"
    LOOP_END = "LOOP_END"
    FOREACH_BEGIN = "FOREACH_BEGIN"
    FOREACH_END = "FOREACH_END"
    CALL = "CALL"
    CHECKPOINT = "CHECKPOINT"
    APPROVE = "APPROVE"


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 256,
) -> str:
    if not isinstance(value, str) or not value:
        raise MacroGraphContractError(f"{field} must be a non-empty string")
    if len(value) > maximum:
        raise MacroGraphContractError(f"{field} exceeds {maximum} characters")
    if any(ord(char) < 32 for char in value):
        raise MacroGraphContractError(f"{field} contains control characters")
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
        raise MacroGraphContractError(
            "macro graph payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _validate_canonical_names(
    values: tuple[str, ...],
    field: str,
    *,
    allow_empty: bool = True,
) -> None:
    if not allow_empty and not values:
        raise MacroGraphContractError(f"{field} must not be empty")
    for value in values:
        _require_text(value, f"{field} item")
    if tuple(sorted(set(values))) != values:
        raise MacroGraphContractError(
            f"{field} must be sorted and unique"
        )


@dataclass(frozen=True, slots=True)
class DoStep:
    """Describe one operation invocation without authorizing it."""

    operation: Operation


@dataclass(frozen=True, slots=True)
class IfStep:
    """Describe a runtime condition branch.

    condition_id names an externally evaluated condition contract. v0.3 plans
    both branches but does not evaluate the condition.
    """

    condition_id: str
    then_steps: tuple["MacroStep", ...]
    else_steps: tuple["MacroStep", ...] = ()


@dataclass(frozen=True, slots=True)
class LoopStep:
    """Describe one explicitly bounded repeated block."""

    loop_id: str
    max_iterations: int
    body: tuple["MacroStep", ...]


@dataclass(frozen=True, slots=True)
class ForEachStep:
    """Describe one explicitly bounded collection iteration."""

    item_name: str
    collection_ref: str
    max_items: int
    body: tuple["MacroStep", ...]


@dataclass(frozen=True, slots=True)
class CallStep:
    """Describe a pinned macro call without resolving or executing it."""

    macro_id: str
    macro_version: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CheckpointStep:
    """Request a runtime checkpoint at this control-flow location."""

    label: str


@dataclass(frozen=True, slots=True)
class ApproveStep:
    """Declare an approval barrier.

    This step carries no grant. It states which capabilities a later execution
    phase must obtain before proceeding beyond the barrier.
    """

    barrier_id: str
    required_capabilities: tuple[str, ...]
    reason: str


MacroStep: TypeAlias = (
    DoStep
    | IfStep
    | LoopStep
    | ForEachStep
    | CallStep
    | CheckpointStep
    | ApproveStep
)


def _step_payload(step: MacroStep) -> dict[str, object]:
    if isinstance(step, DoStep):
        operation = step.operation
        return {
            "kind": "DO",
            "operation_id": operation.operation_id,
            "operation_version": operation.operation_version,
            "operation_hash": operation.operation_hash,
            "adapter_id": operation.adapter_id,
            "action": operation.action,
            "required_capabilities": list(operation.required_capabilities),
        }
    if isinstance(step, IfStep):
        return {
            "kind": "IF",
            "condition_id": step.condition_id,
            "then_steps": [_step_payload(item) for item in step.then_steps],
            "else_steps": [_step_payload(item) for item in step.else_steps],
        }
    if isinstance(step, LoopStep):
        return {
            "kind": "LOOP",
            "loop_id": step.loop_id,
            "max_iterations": step.max_iterations,
            "body": [_step_payload(item) for item in step.body],
        }
    if isinstance(step, ForEachStep):
        return {
            "kind": "FOREACH",
            "item_name": step.item_name,
            "collection_ref": step.collection_ref,
            "max_items": step.max_items,
            "body": [_step_payload(item) for item in step.body],
        }
    if isinstance(step, CallStep):
        return {
            "kind": "CALL",
            "macro_id": step.macro_id,
            "macro_version": step.macro_version,
            "arguments": step.arguments,
            "arguments_sha256": _canonical_sha256(step.arguments),
        }
    if isinstance(step, CheckpointStep):
        return {
            "kind": "CHECKPOINT",
            "label": step.label,
        }
    if isinstance(step, ApproveStep):
        return {
            "kind": "APPROVE",
            "barrier_id": step.barrier_id,
            "required_capabilities": list(step.required_capabilities),
            "reason": step.reason,
        }
    raise MacroGraphContractError(
        f"unsupported macro step type: {type(step).__name__}"
    )


@dataclass(frozen=True, slots=True)
class MacroDefinition:
    """Immutable zero-authority structured macro declaration."""

    macro_id: str
    macro_version: str
    steps: tuple[MacroStep, ...]
    parameters: tuple[str, ...] = ()
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = MACRO_DEFINITION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MACRO_DEFINITION_SCHEMA_VERSION:
            raise MacroGraphContractError(
                "unsupported macro definition schema"
            )
        _require_text(self.macro_id, "macro_id")
        _require_text(self.macro_version, "macro_version", maximum=128)
        _validate_canonical_names(self.parameters, "parameters")
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise MacroGraphContractError(
                "MacroDefinition cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "macro_id": self.macro_id,
            "macro_version": self.macro_version,
            "parameters": list(self.parameters),
            "steps": [_step_payload(step) for step in self.steps],
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def definition_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["definition_sha256"] = self.definition_sha256
        return payload


@dataclass(frozen=True, slots=True)
class PlanInstruction:
    """One canonical zero-authority instruction in a compiled macro plan."""

    index: int
    path: str
    opcode: PlanOpcode
    payload: dict[str, object]
    source_step_sha256: str
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.index, bool) or not isinstance(self.index, int):
            raise MacroGraphContractError("instruction index must be an integer")
        if self.index < 0:
            raise MacroGraphContractError(
                "instruction index must be non-negative"
            )
        _require_text(self.path, "instruction path", maximum=512)
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise MacroGraphContractError(
                "planned instructions cannot carry authority"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "path": self.path,
            "opcode": self.opcode.value,
            "payload": self.payload,
            "source_step_sha256": self.source_step_sha256,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }


@dataclass(frozen=True, slots=True)
class MacroPlan:
    """Deterministic compiled control-flow plan with zero authority."""

    macro_id: str
    macro_version: str
    definition_sha256: str
    instructions: tuple[PlanInstruction, ...]
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = MACRO_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MACRO_PLAN_SCHEMA_VERSION:
            raise MacroGraphContractError("unsupported macro plan schema")
        _require_text(self.macro_id, "macro_id")
        _require_text(self.macro_version, "macro_version", maximum=128)
        if len(self.definition_sha256) != 64:
            raise MacroGraphContractError(
                "definition_sha256 must be a SHA-256 digest"
            )
        try:
            int(self.definition_sha256, 16)
        except ValueError as exc:
            raise MacroGraphContractError(
                "definition_sha256 must be a SHA-256 digest"
            ) from exc
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise MacroGraphContractError("MacroPlan cannot carry authority")

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "macro_id": self.macro_id,
            "macro_version": self.macro_version,
            "definition_sha256": self.definition_sha256,
            "instructions": [
                instruction.to_dict()
                for instruction in self.instructions
            ],
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def plan_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["plan_sha256"] = self.plan_sha256
        return payload


class MacroGraphPlanner:
    """Validate and deterministically compile one structured MacroDefinition."""

    def plan(self, definition: MacroDefinition) -> MacroPlan:
        self.validate(definition)
        emitted: list[PlanInstruction] = []
        self._emit_steps(
            definition.steps,
            prefix="root",
            emitted=emitted,
        )
        return MacroPlan(
            macro_id=definition.macro_id,
            macro_version=definition.macro_version,
            definition_sha256=definition.definition_sha256,
            instructions=tuple(emitted),
        )

    def validate(self, definition: MacroDefinition) -> None:
        if not isinstance(definition, MacroDefinition):
            raise MacroGraphContractError(
                "definition must be a MacroDefinition"
            )
        if not definition.steps:
            raise MacroGraphContractError(
                "macro definition requires at least one step"
            )
        count = self._validate_steps(
            definition.steps,
            depth=0,
        )
        if count > MAX_STATIC_STEPS:
            raise MacroGraphContractError(
                f"macro definition exceeds {MAX_STATIC_STEPS} static steps"
            )

    def _validate_steps(
        self,
        steps: tuple[MacroStep, ...],
        *,
        depth: int,
    ) -> int:
        if depth > MAX_NESTING_DEPTH:
            raise MacroGraphContractError(
                f"macro nesting exceeds {MAX_NESTING_DEPTH}"
            )
        count = 0
        for step in steps:
            count += 1
            if isinstance(step, DoStep):
                self._validate_operation(step.operation)
            elif isinstance(step, IfStep):
                _require_text(step.condition_id, "condition_id")
                if not step.then_steps:
                    raise MacroGraphContractError(
                        "IF requires a non-empty then branch"
                    )
                count += self._validate_steps(
                    step.then_steps,
                    depth=depth + 1,
                )
                count += self._validate_steps(
                    step.else_steps,
                    depth=depth + 1,
                )
            elif isinstance(step, LoopStep):
                _require_text(step.loop_id, "loop_id")
                self._validate_bound(
                    step.max_iterations,
                    "max_iterations",
                    MAX_LOOP_ITERATIONS,
                )
                if not step.body:
                    raise MacroGraphContractError(
                        "LOOP requires a non-empty body"
                    )
                count += self._validate_steps(
                    step.body,
                    depth=depth + 1,
                )
            elif isinstance(step, ForEachStep):
                _require_text(step.item_name, "item_name")
                _require_text(step.collection_ref, "collection_ref")
                self._validate_bound(
                    step.max_items,
                    "max_items",
                    MAX_FOREACH_ITEMS,
                )
                if not step.body:
                    raise MacroGraphContractError(
                        "FOREACH requires a non-empty body"
                    )
                count += self._validate_steps(
                    step.body,
                    depth=depth + 1,
                )
            elif isinstance(step, CallStep):
                _require_text(step.macro_id, "called macro_id")
                _require_text(
                    step.macro_version,
                    "called macro_version",
                    maximum=128,
                )
                _canonical_sha256(step.arguments)
            elif isinstance(step, CheckpointStep):
                _require_text(step.label, "checkpoint label")
            elif isinstance(step, ApproveStep):
                _require_text(step.barrier_id, "approval barrier_id")
                _require_text(step.reason, "approval reason", maximum=512)
                _validate_canonical_names(
                    step.required_capabilities,
                    "approval required_capabilities",
                    allow_empty=False,
                )
            else:
                raise MacroGraphContractError(
                    f"unsupported macro step type: {type(step).__name__}"
                )
            if count > MAX_STATIC_STEPS:
                raise MacroGraphContractError(
                    f"macro definition exceeds {MAX_STATIC_STEPS} static steps"
                )
        return count

    @staticmethod
    def _validate_operation(operation: Operation) -> None:
        if not isinstance(operation, Operation):
            raise MacroGraphContractError(
                "DO requires a Macro Runtime Operation"
            )
        _require_text(operation.operation_id, "operation_id")
        _require_text(
            operation.operation_version,
            "operation_version",
            maximum=128,
        )
        _require_text(operation.adapter_id, "adapter_id")
        _require_text(operation.action, "action")
        _canonical_sha256(operation.inputs)

    @staticmethod
    def _validate_bound(
        value: int,
        field: str,
        maximum: int,
    ) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise MacroGraphContractError(f"{field} must be an integer")
        if value < 1 or value > maximum:
            raise MacroGraphContractError(
                f"{field} must be between 1 and {maximum}"
            )

    def _emit_steps(
        self,
        steps: tuple[MacroStep, ...],
        *,
        prefix: str,
        emitted: list[PlanInstruction],
    ) -> None:
        for local_index, step in enumerate(steps):
            path = f"{prefix}.{local_index}"
            source_hash = _canonical_sha256(_step_payload(step))
            if isinstance(step, DoStep):
                operation = step.operation
                self._append(
                    emitted,
                    path=path,
                    opcode=PlanOpcode.DO,
                    payload={
                        "operation_id": operation.operation_id,
                        "operation_version": operation.operation_version,
                        "operation_hash": operation.operation_hash,
                        "adapter_id": operation.adapter_id,
                        "action": operation.action,
                        "required_capabilities": list(
                            operation.required_capabilities
                        ),
                    },
                    source_hash=source_hash,
                )
            elif isinstance(step, IfStep):
                self._append(
                    emitted,
                    path=path,
                    opcode=PlanOpcode.IF_BEGIN,
                    payload={"condition_id": step.condition_id},
                    source_hash=source_hash,
                )
                self._emit_steps(
                    step.then_steps,
                    prefix=f"{path}.then",
                    emitted=emitted,
                )
                self._append(
                    emitted,
                    path=f"{path}.else",
                    opcode=PlanOpcode.ELSE,
                    payload={"condition_id": step.condition_id},
                    source_hash=source_hash,
                )
                self._emit_steps(
                    step.else_steps,
                    prefix=f"{path}.else",
                    emitted=emitted,
                )
                self._append(
                    emitted,
                    path=f"{path}.end",
                    opcode=PlanOpcode.IF_END,
                    payload={"condition_id": step.condition_id},
                    source_hash=source_hash,
                )
            elif isinstance(step, LoopStep):
                self._append(
                    emitted,
                    path=path,
                    opcode=PlanOpcode.LOOP_BEGIN,
                    payload={
                        "loop_id": step.loop_id,
                        "max_iterations": step.max_iterations,
                    },
                    source_hash=source_hash,
                )
                self._emit_steps(
                    step.body,
                    prefix=f"{path}.body",
                    emitted=emitted,
                )
                self._append(
                    emitted,
                    path=f"{path}.end",
                    opcode=PlanOpcode.LOOP_END,
                    payload={
                        "loop_id": step.loop_id,
                        "max_iterations": step.max_iterations,
                    },
                    source_hash=source_hash,
                )
            elif isinstance(step, ForEachStep):
                self._append(
                    emitted,
                    path=path,
                    opcode=PlanOpcode.FOREACH_BEGIN,
                    payload={
                        "item_name": step.item_name,
                        "collection_ref": step.collection_ref,
                        "max_items": step.max_items,
                    },
                    source_hash=source_hash,
                )
                self._emit_steps(
                    step.body,
                    prefix=f"{path}.body",
                    emitted=emitted,
                )
                self._append(
                    emitted,
                    path=f"{path}.end",
                    opcode=PlanOpcode.FOREACH_END,
                    payload={
                        "item_name": step.item_name,
                        "collection_ref": step.collection_ref,
                        "max_items": step.max_items,
                    },
                    source_hash=source_hash,
                )
            elif isinstance(step, CallStep):
                self._append(
                    emitted,
                    path=path,
                    opcode=PlanOpcode.CALL,
                    payload={
                        "macro_id": step.macro_id,
                        "macro_version": step.macro_version,
                        "arguments": step.arguments,
                        "arguments_sha256": _canonical_sha256(
                            step.arguments
                        ),
                    },
                    source_hash=source_hash,
                )
            elif isinstance(step, CheckpointStep):
                self._append(
                    emitted,
                    path=path,
                    opcode=PlanOpcode.CHECKPOINT,
                    payload={"label": step.label},
                    source_hash=source_hash,
                )
            elif isinstance(step, ApproveStep):
                self._append(
                    emitted,
                    path=path,
                    opcode=PlanOpcode.APPROVE,
                    payload={
                        "barrier_id": step.barrier_id,
                        "required_capabilities": list(
                            step.required_capabilities
                        ),
                        "reason": step.reason,
                        "grants_authority": False,
                    },
                    source_hash=source_hash,
                )
            else:
                raise MacroGraphContractError(
                    f"unsupported macro step type: {type(step).__name__}"
                )

    @staticmethod
    def _append(
        emitted: list[PlanInstruction],
        *,
        path: str,
        opcode: PlanOpcode,
        payload: dict[str, object],
        source_hash: str,
    ) -> None:
        emitted.append(
            PlanInstruction(
                index=len(emitted),
                path=path,
                opcode=opcode,
                payload=payload,
                source_step_sha256=source_hash,
            )
        )
