"""Macro Run Coordinator for Macro Runtime v0.7.

The coordinator owns the normal runner + journal lifecycle for one macro run:
create, persist, advance, persist, reconstruct, resume, and abort.

It does not execute DO operations, resolve external conditions, acquire
approvals, mint authority, schedule work, or create background workers.
"""

from __future__ import annotations

from dataclasses import dataclass

from phios.macro_graph import MacroPlan
from phios.macro_journal import (
    MacroRunJournal,
    MacroRunResumeReceipt,
)
from phios.macro_runner import (
    TERMINAL_STATUSES,
    MacroRunState,
    MacroRunner,
    RunnerInputs,
)
from phios.spine.ledger import RealityLedger


class MacroRunCoordinatorContractError(ValueError):
    """Raised when a coordinator request cannot preserve run invariants."""


@dataclass(frozen=True, slots=True)
class CoordinatedRun:
    """Current validated coordinator view of one macro run."""

    run_id: str
    state: MacroRunState
    head_entry_sha256: str
    entry_count: int
    changed: bool


@dataclass(frozen=True, slots=True)
class CoordinatedResume:
    """Validated reconstruction plus the persisted resume receipt."""

    run: CoordinatedRun
    resume_receipt: MacroRunResumeReceipt


class MacroRunCoordinator:
    """Single-run lifecycle coordinator over MacroRunner + MacroRunJournal."""

    def __init__(self, ledger: RealityLedger) -> None:
        if not isinstance(ledger, RealityLedger):
            raise MacroRunCoordinatorContractError(
                "ledger must be a RealityLedger"
            )
        self._runner = MacroRunner()
        self._journal = MacroRunJournal(ledger)

    def start_run(
        self,
        *,
        run_id: str,
        plan: MacroPlan,
        initial_inputs: RunnerInputs | None = None,
    ) -> CoordinatedRun:
        """Create one run, persist START, then advance to first boundary."""

        self._validate_run_id(run_id)
        if self._has_existing_run(run_id):
            raise MacroRunCoordinatorContractError(
                "run_id already exists"
            )

        ready = self._runner.start(plan)
        start_entry = self._journal.append_state(
            run_id=run_id,
            plan=plan,
            state=ready,
            expected_head_sha256=None,
        )

        advanced = self._runner.advance(
            plan,
            ready,
            initial_inputs,
        )
        if not self._meaningful_progress(ready, advanced):
            return CoordinatedRun(
                run_id=run_id,
                state=ready,
                head_entry_sha256=start_entry.entry_sha256,
                entry_count=1,
                changed=False,
            )

        evidence = self._evidence_refs(initial_inputs)
        transition = self._journal.append_state(
            run_id=run_id,
            plan=plan,
            state=advanced,
            expected_head_sha256=start_entry.entry_sha256,
            evidence_ref_sha256s=evidence,
        )
        return CoordinatedRun(
            run_id=run_id,
            state=advanced,
            head_entry_sha256=transition.entry_sha256,
            entry_count=2,
            changed=True,
        )

    def advance_run(
        self,
        *,
        run_id: str,
        plan: MacroPlan,
        inputs: RunnerInputs,
    ) -> CoordinatedRun:
        """Reconstruct latest valid state, advance, and persist progress."""

        self._validate_run_id(run_id)
        if not isinstance(inputs, RunnerInputs):
            raise MacroRunCoordinatorContractError(
                "inputs must be RunnerInputs"
            )

        current = self._journal.reconstruct(
            run_id=run_id,
            plan=plan,
        )
        before = current.state
        if before.status in TERMINAL_STATUSES:
            return CoordinatedRun(
                run_id=run_id,
                state=before,
                head_entry_sha256=current.head_entry.entry_sha256,
                entry_count=current.entry_count,
                changed=False,
            )

        after = self._runner.advance(
            plan,
            before,
            inputs,
        )
        if not self._meaningful_progress(before, after):
            return CoordinatedRun(
                run_id=run_id,
                state=before,
                head_entry_sha256=current.head_entry.entry_sha256,
                entry_count=current.entry_count,
                changed=False,
            )

        transition = self._journal.append_state(
            run_id=run_id,
            plan=plan,
            state=after,
            expected_head_sha256=current.head_entry.entry_sha256,
            evidence_ref_sha256s=self._evidence_refs(inputs),
        )
        return CoordinatedRun(
            run_id=run_id,
            state=after,
            head_entry_sha256=transition.entry_sha256,
            entry_count=current.entry_count + 1,
            changed=True,
        )

    def abort_run(
        self,
        *,
        run_id: str,
        plan: MacroPlan,
        reason: str,
        evidence_ref_sha256s: tuple[str, ...] = (),
    ) -> CoordinatedRun:
        """Abort one non-terminal run and persist the terminal state."""

        self._validate_run_id(run_id)
        current = self._journal.reconstruct(
            run_id=run_id,
            plan=plan,
        )
        if current.state.status in TERMINAL_STATUSES:
            return CoordinatedRun(
                run_id=run_id,
                state=current.state,
                head_entry_sha256=current.head_entry.entry_sha256,
                entry_count=current.entry_count,
                changed=False,
            )

        aborted = self._runner.abort(
            plan,
            current.state,
            reason=reason,
        )
        transition = self._journal.append_state(
            run_id=run_id,
            plan=plan,
            state=aborted,
            expected_head_sha256=current.head_entry.entry_sha256,
            evidence_ref_sha256s=tuple(sorted(set(evidence_ref_sha256s))),
        )
        return CoordinatedRun(
            run_id=run_id,
            state=aborted,
            head_entry_sha256=transition.entry_sha256,
            entry_count=current.entry_count + 1,
            changed=True,
        )

    def current_run(
        self,
        *,
        run_id: str,
        plan: MacroPlan,
    ) -> CoordinatedRun:
        """Return the latest fully validated state without emitting resume evidence."""

        self._validate_run_id(run_id)
        current = self._journal.reconstruct(
            run_id=run_id,
            plan=plan,
        )
        return CoordinatedRun(
            run_id=run_id,
            state=current.state,
            head_entry_sha256=current.head_entry.entry_sha256,
            entry_count=current.entry_count,
            changed=False,
        )

    def resume_run(
        self,
        *,
        run_id: str,
        plan: MacroPlan,
        resumed_at: str,
    ) -> CoordinatedResume:
        """Validate persistent history and emit one explicit resume receipt."""

        self._validate_run_id(run_id)
        state, receipt = self._journal.resume(
            run_id=run_id,
            plan=plan,
            resumed_at=resumed_at,
        )
        current = self._journal.reconstruct(
            run_id=run_id,
            plan=plan,
        )
        if state.state_sha256 != current.state.state_sha256:
            raise MacroRunCoordinatorContractError(
                "resume state changed during reconstruction"
            )
        return CoordinatedResume(
            run=CoordinatedRun(
                run_id=run_id,
                state=state,
                head_entry_sha256=current.head_entry.entry_sha256,
                entry_count=current.entry_count,
                changed=False,
            ),
            resume_receipt=receipt,
        )

    def _has_existing_run(self, run_id: str) -> bool:
        return self._journal.has_run(run_id=run_id)

    @staticmethod
    def _validate_run_id(run_id: str) -> None:
        if not isinstance(run_id, str) or not run_id:
            raise MacroRunCoordinatorContractError(
                "run_id must be a non-empty string"
            )
        if len(run_id) > 256:
            raise MacroRunCoordinatorContractError(
                "run_id exceeds 256 characters"
            )
        if any(ord(char) < 32 for char in run_id):
            raise MacroRunCoordinatorContractError(
                "run_id contains control characters"
            )

    @staticmethod
    def _meaningful_progress(
        before: MacroRunState,
        after: MacroRunState,
    ) -> bool:
        return (
            before.cursor != after.cursor
            or before.status != after.status
            or before.reason != after.reason
            or before.loop_iterations != after.loop_iterations
            or before.foreach_indices != after.foreach_indices
            or (before.variables or {}) != (after.variables or {})
            or (before.waiting_on or {}) != (after.waiting_on or {})
            or before.last_instruction_path != after.last_instruction_path
        )

    @staticmethod
    def _evidence_refs(
        inputs: RunnerInputs | None,
    ) -> tuple[str, ...]:
        if inputs is None:
            return ()

        refs: set[str] = set()
        refs.update(
            item.evidence_ref_sha256
            for item in inputs.conditions
        )
        refs.update(
            item.receipt_sha256
            for item in inputs.operations
        )
        refs.update(
            item.evidence_ref_sha256
            for item in inputs.approvals
        )
        refs.update(
            item.receipt_sha256
            for item in inputs.calls
        )
        refs.update(
            item.receipt_sha256
            for item in inputs.checkpoints
        )
        refs.update(
            item.evidence_ref_sha256
            for item in inputs.collections
        )
        return tuple(sorted(refs))
