from __future__ import annotations

import json
from pathlib import Path

import pytest

from phios.macro_graph import DoStep, MacroDefinition, MacroGraphPlanner
from phios.macro_journal import (
    MacroRunJournal,
    MacroRunJournalContractError,
)
from phios.macro_runner import (
    MacroRunner,
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


def _operation(text: str = "journal") -> Operation:
    return Operation(
        operation_id="macro.journal.write",
        operation_version="0.6.0",
        adapter_id="phios.spine",
        action="commons.text_artifact",
        inputs={"name": "journal-test", "text": text},
        required_capabilities=("artifact.write",),
        execution_modes_supported=(ExecutionMode.LIVE,),
        idempotency_class=IdempotencyClass.NON_IDEMPOTENT,
        replay_class=ReplayClass.NON_REPLAYABLE,
        rollback_class=RollbackClass.NONE,
        side_effect_class=SideEffectClass.LOCAL_IRREVERSIBLE,
    )


def _plan(text: str = "journal"):
    return MacroGraphPlanner().plan(
        MacroDefinition(
            macro_id="macro:journal-test",
            macro_version="0.6.0",
            steps=(DoStep(_operation(text)),),
        )
    )


def _ledger(tmp_path: Path) -> RealityLedger:
    return RealityLedger(tmp_path / "ledger" / "receipts.jsonl")


def test_journal_001_append_chain_and_reconstruct_latest_state(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    journal = MacroRunJournal(ledger)
    plan = _plan()
    runner = MacroRunner()
    ready = runner.start(plan)

    start_entry = journal.append_state(
        run_id="run:one",
        plan=plan,
        state=ready,
        expected_head_sha256=None,
    )
    waiting = runner.advance(plan, ready)
    wait_entry = journal.append_state(
        run_id="run:one",
        plan=plan,
        state=waiting,
        expected_head_sha256=start_entry.entry_sha256,
        evidence_ref_sha256s=(EVIDENCE_A,),
    )

    reconstructed = journal.reconstruct(
        run_id="run:one",
        plan=plan,
    )

    assert start_entry.sequence == 0
    assert wait_entry.sequence == 1
    assert wait_entry.previous_entry_sha256 == start_entry.entry_sha256
    assert wait_entry.previous_state_sha256 == ready.state_sha256
    assert reconstructed.entry_count == 2
    assert reconstructed.head_entry.entry_sha256 == wait_entry.entry_sha256
    assert reconstructed.state == waiting
    assert reconstructed.state.status is RunnerStatus.WAITING_OPERATION


def test_journal_002_restart_resume_then_complete_and_reconstruct(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    plan = _plan()
    runner = MacroRunner()
    original_journal = MacroRunJournal(ledger)
    ready = runner.start(plan)
    start_entry = original_journal.append_state(
        run_id="run:restart",
        plan=plan,
        state=ready,
        expected_head_sha256=None,
    )
    waiting = runner.advance(plan, ready)
    wait_entry = original_journal.append_state(
        run_id="run:restart",
        plan=plan,
        state=waiting,
        expected_head_sha256=start_entry.entry_sha256,
    )

    restarted_journal = MacroRunJournal(ledger)
    resumed, resume_receipt = restarted_journal.resume(
        run_id="run:restart",
        plan=plan,
        resumed_at="2026-09-26T22:30:00+00:00",
    )

    assert resumed == waiting
    assert resume_receipt.entry_count == 2
    assert resume_receipt.head_entry_sha256 == wait_entry.entry_sha256
    assert resume_receipt.resumed_state_sha256 == waiting.state_sha256
    assert resume_receipt.operational_authority is False
    assert resume_receipt.action_authority is False
    assert resume_receipt.execution_authority is False

    completed = runner.advance(
        plan,
        resumed,
        RunnerInputs(
            operations=(
                OperationResolution(
                    instruction_path="root.0",
                    operation_hash=_operation().operation_hash,
                    status=ResolutionStatus.SUCCEEDED,
                    receipt_sha256=EVIDENCE_B,
                ),
            ),
        ),
    )
    completed_entry = restarted_journal.append_state(
        run_id="run:restart",
        plan=plan,
        state=completed,
        expected_head_sha256=resume_receipt.head_entry_sha256,
        evidence_ref_sha256s=(EVIDENCE_B,),
    )

    after_second_restart = MacroRunJournal(ledger).reconstruct(
        run_id="run:restart",
        plan=plan,
    )
    assert completed.status is RunnerStatus.COMPLETED
    assert after_second_restart.state == completed
    assert after_second_restart.head_entry.entry_sha256 == (
        completed_entry.entry_sha256
    )
    resume_rows = ledger.recent_macro_run_resume_receipts(1)
    assert resume_rows[0]["receipt_sha256"] == resume_receipt.receipt_sha256


def test_journal_003_stale_expected_head_is_rejected(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    journal = MacroRunJournal(ledger)
    plan = _plan()
    runner = MacroRunner()
    ready = runner.start(plan)
    start_entry = journal.append_state(
        run_id="run:stale",
        plan=plan,
        state=ready,
        expected_head_sha256=None,
    )
    waiting = runner.advance(plan, ready)
    journal.append_state(
        run_id="run:stale",
        plan=plan,
        state=waiting,
        expected_head_sha256=start_entry.entry_sha256,
    )
    aborted = runner.abort(plan, waiting, reason="operator_cancelled")

    with pytest.raises(
        MacroRunJournalContractError,
        match="expected journal head does not match",
    ):
        journal.append_state(
            run_id="run:stale",
            plan=plan,
            state=aborted,
            expected_head_sha256=start_entry.entry_sha256,
        )

    assert len(ledger.macro_run_journal_entries(run_id="run:stale")) == 2


def test_journal_004_tampered_history_fails_closed(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    journal = MacroRunJournal(ledger)
    plan = _plan()
    runner = MacroRunner()
    ready = runner.start(plan)
    start_entry = journal.append_state(
        run_id="run:tamper",
        plan=plan,
        state=ready,
        expected_head_sha256=None,
    )
    waiting = runner.advance(plan, ready)
    journal.append_state(
        run_id="run:tamper",
        plan=plan,
        state=waiting,
        expected_head_sha256=start_entry.entry_sha256,
    )

    journal_path = tmp_path / "ledger" / "macro-run-journal.jsonl"
    rows = [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[1]["previous_entry_sha256"] = "f" * 64
    journal_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        MacroRunJournalContractError,
        match="journal entry hash mismatch",
    ):
        MacroRunJournal(ledger).reconstruct(
            run_id="run:tamper",
            plan=plan,
        )


def test_journal_005_wrong_plan_cannot_resume(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    journal = MacroRunJournal(ledger)
    plan = _plan("one")
    ready = MacroRunner().start(plan)
    journal.append_state(
        run_id="run:wrong-plan",
        plan=plan,
        state=ready,
        expected_head_sha256=None,
    )

    with pytest.raises(
        MacroRunJournalContractError,
        match="journal plan hash does not match",
    ):
        journal.reconstruct(
            run_id="run:wrong-plan",
            plan=_plan("two"),
        )


def test_journal_006_terminal_state_cannot_be_extended(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    journal = MacroRunJournal(ledger)
    plan = _plan()
    runner = MacroRunner()
    ready = runner.start(plan)
    first = journal.append_state(
        run_id="run:terminal",
        plan=plan,
        state=ready,
        expected_head_sha256=None,
    )
    waiting = runner.advance(plan, ready)
    second = journal.append_state(
        run_id="run:terminal",
        plan=plan,
        state=waiting,
        expected_head_sha256=first.entry_sha256,
    )
    aborted = runner.abort(plan, waiting, reason="operator_cancelled")
    terminal = journal.append_state(
        run_id="run:terminal",
        plan=plan,
        state=aborted,
        expected_head_sha256=second.entry_sha256,
    )

    with pytest.raises(
        MacroRunJournalContractError,
        match="terminal MacroRunState cannot be followed",
    ):
        journal.append_state(
            run_id="run:terminal",
            plan=plan,
            state=ready,
            expected_head_sha256=terminal.entry_sha256,
        )


def test_journal_007_run_ids_are_isolated(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    journal = MacroRunJournal(ledger)
    plan = _plan()
    ready = MacroRunner().start(plan)

    a = journal.append_state(
        run_id="run:a",
        plan=plan,
        state=ready,
        expected_head_sha256=None,
    )
    b = journal.append_state(
        run_id="run:b",
        plan=plan,
        state=ready,
        expected_head_sha256=None,
    )

    reconstructed_a = journal.reconstruct(run_id="run:a", plan=plan)
    reconstructed_b = journal.reconstruct(run_id="run:b", plan=plan)

    assert reconstructed_a.entry_count == 1
    assert reconstructed_b.entry_count == 1
    assert reconstructed_a.head_entry.entry_sha256 == a.entry_sha256
    assert reconstructed_b.head_entry.entry_sha256 == b.entry_sha256
    assert len(ledger.macro_run_journal_entries()) == 2
