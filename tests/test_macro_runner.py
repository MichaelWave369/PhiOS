from __future__ import annotations

import pytest

from phios.macro_graph import (
    ApproveStep,
    CallStep,
    CheckpointStep,
    DoStep,
    ForEachStep,
    IfStep,
    LoopStep,
    MacroDefinition,
    MacroGraphPlanner,
)
from phios.macro_runner import (
    ApprovalResolution,
    CallResolution,
    CheckpointResolution,
    CollectionResolution,
    ConditionResolution,
    MacroRunner,
    MacroRunnerContractError,
    OperationResolution,
    ResolutionStatus,
    RunnerInputs,
    RunnerStatus,
)
from phios.macro_runtime import (
    ExecutionMode,
    IdempotencyClass,
    Operation,
    ReplayClass,
    RollbackClass,
    SideEffectClass,
)

EVIDENCE_A = "a" * 64
EVIDENCE_B = "b" * 64
EVIDENCE_C = "c" * 64
EVIDENCE_D = "d" * 64


def _operation(text: str = "one") -> Operation:
    return Operation(
        operation_id="macro.runner.write",
        operation_version="0.4.0",
        adapter_id="phios.spine",
        action="commons.text_artifact",
        inputs={"name": "runner-test", "text": text},
        required_capabilities=("artifact.write",),
        execution_modes_supported=(ExecutionMode.LIVE,),
        idempotency_class=IdempotencyClass.NON_IDEMPOTENT,
        replay_class=ReplayClass.NON_REPLAYABLE,
        rollback_class=RollbackClass.NONE,
        side_effect_class=SideEffectClass.LOCAL_IRREVERSIBLE,
    )


def _plan(*steps):
    return MacroGraphPlanner().plan(
        MacroDefinition(
            macro_id="macro:runner-test",
            macro_version="0.4.0",
            steps=tuple(steps),
        )
    )


def test_runner_001_do_pauses_until_matching_operation_resolution() -> None:
    operation = _operation()
    plan = _plan(DoStep(operation))
    runner = MacroRunner()
    waiting = runner.advance(plan, runner.start(plan))

    assert waiting.status is RunnerStatus.WAITING_OPERATION
    assert waiting.cursor == 0
    assert waiting.waiting_on == {
        "instruction_path": "root.0",
        "opcode": "DO",
    }
    assert waiting.operational_authority is False
    assert waiting.action_authority is False
    assert waiting.execution_authority is False

    completed = runner.advance(
        plan,
        waiting,
        RunnerInputs(
            operations=(
                OperationResolution(
                    instruction_path="root.0",
                    operation_hash=operation.operation_hash,
                    status=ResolutionStatus.SUCCEEDED,
                    receipt_sha256=EVIDENCE_A,
                ),
            ),
        ),
    )

    assert completed.status is RunnerStatus.COMPLETED
    assert completed.cursor == 1
    assert completed.operational_authority is False
    assert completed.action_authority is False
    assert completed.execution_authority is False


def test_runner_002_operation_scope_mismatch_holds_without_advancing() -> None:
    operation = _operation()
    plan = _plan(DoStep(operation))
    runner = MacroRunner()
    waiting = runner.advance(plan, runner.start(plan))

    held = runner.advance(
        plan,
        waiting,
        RunnerInputs(
            operations=(
                OperationResolution(
                    instruction_path="root.0",
                    operation_hash="f" * 64,
                    status=ResolutionStatus.SUCCEEDED,
                    receipt_sha256=EVIDENCE_A,
                ),
            ),
        ),
    )

    assert held.status is RunnerStatus.HELD
    assert held.reason == "operation_resolution_scope_mismatch"
    assert held.cursor == 0


def test_runner_003_if_waits_then_selects_false_branch_only() -> None:
    plan = _plan(
        IfStep(
            condition_id="condition:test",
            then_steps=(CheckpointStep(label="then-checkpoint"),),
            else_steps=(
                CallStep(
                    macro_id="macro:else",
                    macro_version="1.0.0",
                    arguments={"selected": "else"},
                ),
            ),
        )
    )
    runner = MacroRunner()
    waiting_condition = runner.advance(plan, runner.start(plan))

    assert waiting_condition.status is RunnerStatus.WAITING_CONDITION
    assert waiting_condition.reason == "condition_resolution_required"

    waiting_callee = runner.advance(
        plan,
        waiting_condition,
        RunnerInputs(
            conditions=(
                ConditionResolution(
                    condition_id="condition:test",
                    value=False,
                    evidence_ref_sha256=EVIDENCE_A,
                ),
            ),
        ),
    )

    assert waiting_callee.status is RunnerStatus.WAITING_CALLEE
    assert waiting_callee.waiting_on == {
        "instruction_path": "root.0.else.0",
        "opcode": "CALL",
    }

    call_instruction = plan.instructions[3]
    completed = runner.advance(
        plan,
        waiting_callee,
        RunnerInputs(
            conditions=(
                ConditionResolution(
                    condition_id="condition:test",
                    value=False,
                    evidence_ref_sha256=EVIDENCE_A,
                ),
            ),
            calls=(
                CallResolution(
                    instruction_path="root.0.else.0",
                    macro_id="macro:else",
                    macro_version="1.0.0",
                    arguments_sha256=str(
                        call_instruction.payload["arguments_sha256"]
                    ),
                    status=ResolutionStatus.SUCCEEDED,
                    receipt_sha256=EVIDENCE_B,
                ),
            ),
        ),
    )

    assert completed.status is RunnerStatus.COMPLETED


def test_runner_004_if_true_branch_skips_else_branch() -> None:
    plan = _plan(
        IfStep(
            condition_id="condition:test",
            then_steps=(CheckpointStep(label="then-checkpoint"),),
            else_steps=(
                CallStep(
                    macro_id="macro:else",
                    macro_version="1.0.0",
                    arguments={},
                ),
            ),
        )
    )
    runner = MacroRunner()
    state = runner.advance(plan, runner.start(plan))

    checkpointing = runner.advance(
        plan,
        state,
        RunnerInputs(
            conditions=(
                ConditionResolution(
                    condition_id="condition:test",
                    value=True,
                    evidence_ref_sha256=EVIDENCE_A,
                ),
            ),
        ),
    )

    assert checkpointing.status is RunnerStatus.CHECKPOINTING
    assert checkpointing.waiting_on == {
        "instruction_path": "root.0.then.0",
        "opcode": "CHECKPOINT",
    }

    completed = runner.advance(
        plan,
        checkpointing,
        RunnerInputs(
            conditions=(
                ConditionResolution(
                    condition_id="condition:test",
                    value=True,
                    evidence_ref_sha256=EVIDENCE_A,
                ),
            ),
            checkpoints=(
                CheckpointResolution(
                    instruction_path="root.0.then.0",
                    label="then-checkpoint",
                    status=ResolutionStatus.SUCCEEDED,
                    receipt_sha256=EVIDENCE_B,
                ),
            ),
        ),
    )

    assert completed.status is RunnerStatus.COMPLETED


def test_runner_005_loop_executes_exact_declared_iteration_bound() -> None:
    plan = _plan(
        LoopStep(
            loop_id="twice",
            max_iterations=2,
            body=(CheckpointStep(label="loop-checkpoint"),),
        )
    )
    runner = MacroRunner()
    started = runner.start(plan)
    checkpointing = runner.advance(plan, started)

    assert checkpointing.status is RunnerStatus.CHECKPOINTING

    completed = runner.advance(
        plan,
        checkpointing,
        RunnerInputs(
            checkpoints=(
                CheckpointResolution(
                    instruction_path="root.0.body.0",
                    label="loop-checkpoint",
                    status=ResolutionStatus.SUCCEEDED,
                    receipt_sha256=EVIDENCE_A,
                ),
            ),
        ),
    )

    assert completed.status is RunnerStatus.COMPLETED
    assert len(completed.loop_iterations) == 1
    assert completed.loop_iterations[0][1] == 2


def test_runner_006_foreach_waits_for_collection_and_enforces_bound() -> None:
    plan = _plan(
        ForEachStep(
            item_name="item",
            collection_ref="input:items",
            max_items=2,
            body=(CheckpointStep(label="item-checkpoint"),),
        )
    )
    runner = MacroRunner()
    waiting = runner.advance(plan, runner.start(plan))

    assert waiting.status is RunnerStatus.WAITING_COLLECTION

    held = runner.advance(
        plan,
        waiting,
        RunnerInputs(
            collections=(
                CollectionResolution(
                    collection_ref="input:items",
                    items=("a", "b", "c"),
                    evidence_ref_sha256=EVIDENCE_A,
                ),
            ),
        ),
    )

    assert held.status is RunnerStatus.HELD
    assert held.reason == "collection_bound_exceeded"


def test_runner_007_foreach_iterates_bounded_collection_to_completion() -> None:
    plan = _plan(
        ForEachStep(
            item_name="item",
            collection_ref="input:items",
            max_items=3,
            body=(CheckpointStep(label="item-checkpoint"),),
        )
    )
    runner = MacroRunner()
    waiting = runner.advance(plan, runner.start(plan))
    inputs = RunnerInputs(
        collections=(
            CollectionResolution(
                collection_ref="input:items",
                items=("a", "b"),
                evidence_ref_sha256=EVIDENCE_A,
            ),
        ),
        checkpoints=(
            CheckpointResolution(
                instruction_path="root.0.body.0",
                label="item-checkpoint",
                status=ResolutionStatus.SUCCEEDED,
                receipt_sha256=EVIDENCE_B,
            ),
        ),
    )
    completed = runner.advance(plan, waiting, inputs)

    assert completed.status is RunnerStatus.COMPLETED
    assert len(completed.foreach_indices) == 1
    assert completed.foreach_indices[0][1] == 2
    assert completed.variables == {}


def test_runner_008_approval_is_a_pause_barrier_not_authority() -> None:
    operation = _operation()
    plan = _plan(
        ApproveStep(
            barrier_id="approval:write",
            required_capabilities=("artifact.write",),
            reason="Obtain current governed authority before execution.",
        ),
        DoStep(operation),
    )
    runner = MacroRunner()
    waiting = runner.advance(plan, runner.start(plan))

    assert waiting.status is RunnerStatus.WAITING_APPROVAL

    after_approval = runner.advance(
        plan,
        waiting,
        RunnerInputs(
            approvals=(
                ApprovalResolution(
                    barrier_id="approval:write",
                    required_capabilities=("artifact.write",),
                    approved=True,
                    evidence_ref_sha256=EVIDENCE_A,
                ),
            ),
        ),
    )

    assert after_approval.status is RunnerStatus.WAITING_OPERATION
    assert after_approval.operational_authority is False
    assert after_approval.action_authority is False
    assert after_approval.execution_authority is False


def test_runner_009_denied_approval_holds_at_barrier() -> None:
    plan = _plan(
        ApproveStep(
            barrier_id="approval:write",
            required_capabilities=("artifact.write",),
            reason="Authority is externally governed.",
        )
    )
    runner = MacroRunner()
    waiting = runner.advance(plan, runner.start(plan))

    held = runner.advance(
        plan,
        waiting,
        RunnerInputs(
            approvals=(
                ApprovalResolution(
                    barrier_id="approval:write",
                    required_capabilities=("artifact.write",),
                    approved=False,
                    evidence_ref_sha256=EVIDENCE_A,
                ),
            ),
        ),
    )

    assert held.status is RunnerStatus.HELD
    assert held.reason == "approval_not_granted"
    assert held.cursor == 0


def test_runner_010_call_failure_becomes_failed_run() -> None:
    plan = _plan(
        CallStep(
            macro_id="macro:child",
            macro_version="1.0.0",
            arguments={"x": 1},
        )
    )
    runner = MacroRunner()
    waiting = runner.advance(plan, runner.start(plan))
    instruction = plan.instructions[0]

    failed = runner.advance(
        plan,
        waiting,
        RunnerInputs(
            calls=(
                CallResolution(
                    instruction_path="root.0",
                    macro_id="macro:child",
                    macro_version="1.0.0",
                    arguments_sha256=str(
                        instruction.payload["arguments_sha256"]
                    ),
                    status=ResolutionStatus.FAILED,
                    receipt_sha256=EVIDENCE_A,
                ),
            ),
        ),
    )

    assert failed.status is RunnerStatus.FAILED
    assert failed.reason == "callee_failed"


def test_runner_011_state_is_deterministic_for_same_plan_and_inputs() -> None:
    operation = _operation()
    plan = _plan(DoStep(operation))
    runner = MacroRunner()

    first = runner.advance(plan, runner.start(plan))
    second = runner.advance(plan, runner.start(plan))

    assert first.to_dict() == second.to_dict()
    assert first.state_sha256 == second.state_sha256


def test_runner_012_stale_plan_resume_is_rejected() -> None:
    first_plan = _plan(DoStep(_operation("one")))
    second_plan = _plan(DoStep(_operation("two")))
    runner = MacroRunner()
    state = runner.advance(first_plan, runner.start(first_plan))

    with pytest.raises(
        MacroRunnerContractError,
        match="plan hash does not match",
    ):
        runner.advance(second_plan, state)


def test_runner_013_abort_is_terminal_and_zero_authority() -> None:
    plan = _plan(DoStep(_operation()))
    runner = MacroRunner()
    state = runner.advance(plan, runner.start(plan))
    aborted = runner.abort(plan, state, reason="operator_cancelled")

    assert aborted.status is RunnerStatus.ABORTED
    assert runner.advance(plan, aborted) == aborted
    assert aborted.operational_authority is False
    assert aborted.action_authority is False
    assert aborted.execution_authority is False
