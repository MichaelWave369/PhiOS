from __future__ import annotations

from pathlib import Path

import pytest

from phios.macro_coordinator import (
    MacroRunCoordinator,
    MacroRunCoordinatorContractError,
)
from phios.macro_graph import (
    CheckpointStep,
    DoStep,
    IfStep,
    MacroDefinition,
    MacroGraphPlanner,
)
from phios.macro_runner import (
    CheckpointResolution,
    ConditionResolution,
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
from phios.spine.ledger import RealityLedger

EVIDENCE_A = "a" * 64
EVIDENCE_B = "b" * 64
EVIDENCE_C = "c" * 64


def _operation(text: str = "coordinator") -> Operation:
    return Operation(
        operation_id="macro.coordinator.write",
        operation_version="0.7.0",
        adapter_id="phios.spine",
        action="commons.text_artifact",
        inputs={"name": "coordinator-test", "text": text},
        required_capabilities=("artifact.write",),
        execution_modes_supported=(ExecutionMode.LIVE,),
        idempotency_class=IdempotencyClass.NON_IDEMPOTENT,
        replay_class=ReplayClass.NON_REPLAYABLE,
        rollback_class=RollbackClass.NONE,
        side_effect_class=SideEffectClass.LOCAL_IRREVERSIBLE,
    )


def _plan(text: str = "coordinator"):
    return MacroGraphPlanner().plan(
        MacroDefinition(
            macro_id="macro:coordinator-test",
            macro_version="0.7.0",
            steps=(DoStep(_operation(text)),),
        )
    )


def _conditional_plan():
    return MacroGraphPlanner().plan(
        MacroDefinition(
            macro_id="macro:coordinator-conditional",
            macro_version="0.7.0",
            steps=(
                IfStep(
                    condition_id="condition:go",
                    then_steps=(
                        CheckpointStep(label="after-condition"),
                        DoStep(_operation("conditional")),
                    ),
                    else_steps=(),
                ),
            ),
        )
    )


def _ledger(tmp_path: Path) -> RealityLedger:
    return RealityLedger(tmp_path / "ledger" / "receipts.jsonl")


def test_coordinator_001_start_persists_start_and_first_pause(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    coordinator = MacroRunCoordinator(ledger)
    plan = _plan()

    run = coordinator.start_run(
        run_id="run:coordinator-start",
        plan=plan,
    )

    assert run.state.status is RunnerStatus.WAITING_OPERATION
    assert run.entry_count == 2
    assert run.changed is True

    rows = ledger.macro_run_journal_entries(
        run_id="run:coordinator-start"
    )
    assert [row["sequence"] for row in rows] == [0, 1]
    assert rows[0]["kind"] == "START"
    assert rows[1]["kind"] == "TRANSITION"
    assert rows[1]["state"]["status"] == "WAITING_OPERATION"


def test_coordinator_002_resolution_advances_and_persists_automatically(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    coordinator = MacroRunCoordinator(ledger)
    operation = _operation()
    plan = _plan()
    started = coordinator.start_run(
        run_id="run:coordinator-complete",
        plan=plan,
    )

    completed = coordinator.advance_run(
        run_id="run:coordinator-complete",
        plan=plan,
        inputs=RunnerInputs(
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

    assert started.state.status is RunnerStatus.WAITING_OPERATION
    assert completed.state.status is RunnerStatus.COMPLETED
    assert completed.entry_count == 3
    assert completed.changed is True

    rows = ledger.macro_run_journal_entries(
        run_id="run:coordinator-complete"
    )
    assert rows[-1]["state"]["status"] == "COMPLETED"
    assert rows[-1]["evidence_ref_sha256s"] == [EVIDENCE_A]


def test_coordinator_003_irrelevant_inputs_do_not_create_journal_noise(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    coordinator = MacroRunCoordinator(ledger)
    plan = _plan()
    started = coordinator.start_run(
        run_id="run:coordinator-noise",
        plan=plan,
    )

    unchanged = coordinator.advance_run(
        run_id="run:coordinator-noise",
        plan=plan,
        inputs=RunnerInputs(
            conditions=(
                ConditionResolution(
                    condition_id="condition:irrelevant",
                    value=True,
                    evidence_ref_sha256=EVIDENCE_A,
                ),
            ),
        ),
    )

    assert unchanged.changed is False
    assert unchanged.state == started.state
    assert unchanged.head_entry_sha256 == started.head_entry_sha256
    assert unchanged.entry_count == 2
    assert len(
        ledger.macro_run_journal_entries(
            run_id="run:coordinator-noise"
        )
    ) == 2


def test_coordinator_004_restart_resume_and_continue(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    plan = _conditional_plan()
    first = MacroRunCoordinator(ledger)
    started = first.start_run(
        run_id="run:coordinator-restart",
        plan=plan,
    )

    assert started.state.status is RunnerStatus.WAITING_CONDITION

    second = MacroRunCoordinator(ledger)
    resumed = second.resume_run(
        run_id="run:coordinator-restart",
        plan=plan,
        resumed_at="2026-09-26T22:40:00+00:00",
    )

    assert resumed.run.state == started.state
    assert resumed.run.entry_count == 2
    assert resumed.resume_receipt.resumed_state_sha256 == (
        started.state.state_sha256
    )

    checkpointing = second.advance_run(
        run_id="run:coordinator-restart",
        plan=plan,
        inputs=RunnerInputs(
            conditions=(
                ConditionResolution(
                    condition_id="condition:go",
                    value=True,
                    evidence_ref_sha256=EVIDENCE_A,
                ),
            ),
        ),
    )
    assert checkpointing.state.status is RunnerStatus.CHECKPOINTING

    waiting_operation = second.advance_run(
        run_id="run:coordinator-restart",
        plan=plan,
        inputs=RunnerInputs(
            checkpoints=(
                CheckpointResolution(
                    instruction_path="root.0.then.0",
                    label="after-condition",
                    status=ResolutionStatus.SUCCEEDED,
                    receipt_sha256=EVIDENCE_B,
                ),
            ),
        ),
    )
    assert waiting_operation.state.status is RunnerStatus.WAITING_OPERATION

    third = MacroRunCoordinator(ledger)
    current = third.current_run(
        run_id="run:coordinator-restart",
        plan=plan,
    )
    assert current.state == waiting_operation.state
    assert current.entry_count == 4

    rows = ledger.macro_run_journal_entries(
        run_id="run:coordinator-restart"
    )
    assert rows[2]["evidence_ref_sha256s"] == [EVIDENCE_A]
    assert rows[3]["evidence_ref_sha256s"] == [EVIDENCE_B]


def test_coordinator_005_duplicate_run_id_is_rejected(
    tmp_path: Path,
) -> None:
    coordinator = MacroRunCoordinator(_ledger(tmp_path))
    plan = _plan()
    coordinator.start_run(
        run_id="run:duplicate",
        plan=plan,
    )

    with pytest.raises(
        MacroRunCoordinatorContractError,
        match="run_id already exists",
    ):
        coordinator.start_run(
            run_id="run:duplicate",
            plan=plan,
        )


def test_coordinator_006_abort_is_persisted_and_terminal(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    coordinator = MacroRunCoordinator(ledger)
    plan = _plan()
    coordinator.start_run(
        run_id="run:abort",
        plan=plan,
    )

    aborted = coordinator.abort_run(
        run_id="run:abort",
        plan=plan,
        reason="operator_cancelled",
        evidence_ref_sha256s=(EVIDENCE_C,),
    )
    again = coordinator.abort_run(
        run_id="run:abort",
        plan=plan,
        reason="second_cancel",
    )

    assert aborted.state.status is RunnerStatus.ABORTED
    assert aborted.changed is True
    assert again.state == aborted.state
    assert again.changed is False

    rows = ledger.macro_run_journal_entries(run_id="run:abort")
    assert len(rows) == 3
    assert rows[-1]["state"]["status"] == "ABORTED"
    assert rows[-1]["evidence_ref_sha256s"] == [EVIDENCE_C]


def test_coordinator_007_operation_hold_is_persisted_as_run_hold(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    coordinator = MacroRunCoordinator(ledger)
    operation = _operation()
    plan = _plan()
    coordinator.start_run(
        run_id="run:held",
        plan=plan,
    )

    held = coordinator.advance_run(
        run_id="run:held",
        plan=plan,
        inputs=RunnerInputs(
            operations=(
                OperationResolution(
                    instruction_path="root.0",
                    operation_hash=operation.operation_hash,
                    status=ResolutionStatus.HELD,
                    receipt_sha256=EVIDENCE_A,
                ),
            ),
        ),
    )

    assert held.state.status is RunnerStatus.HELD
    assert held.state.reason == "operation_held"
    assert held.changed is True

    current = MacroRunCoordinator(ledger).current_run(
        run_id="run:held",
        plan=plan,
    )
    assert current.state == held.state
    assert current.entry_count == 3
