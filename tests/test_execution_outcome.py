from __future__ import annotations

from pathlib import Path

import pytest

from phios.evidence_ref import EvidenceRef
from phios.execution_outcome import (
    ExecutionReconciliationContractError,
    reconcile_execution_outcome,
)
from phios.spine.ledger import RealityLedger
from phios.spine.models import ExecutionReceipt


def _unknown_execution() -> ExecutionReceipt:
    return ExecutionReceipt(
        schema_version="phios.execution_receipt.v0.1",
        receipt_id="exec-unknown-001",
        timestamp_utc="2026-09-24T23:00:00+00:00",
        capability_id="network.switch.change",
        planner="phivessel.spine.deterministic",
        input_sha256="a" * 64,
        permissions_requested=["network.change"],
        permission_status="allowed",
        execution_status="outcome_unknown",
        executor_entered=True,
        reconciliation_status="required",
        error="OutcomeUnknownError: transport lost after command send",
    )


def _evidence(digest: str = "b" * 64) -> EvidenceRef:
    return EvidenceRef.build(
        source_id="switch-observer:test",
        source_kind="runtime_observation",
        content_sha256=digest,
        observed_at="2026-09-24T23:01:00+00:00",
        exactness_class="direct_observation",
    )


def test_effect_confirmed_blocks_retry_and_carries_zero_authority() -> None:
    receipt = reconcile_execution_outcome(
        execution=_unknown_execution(),
        disposition="effect_confirmed",
        evidence_refs=(_evidence(),),
        reconciler_id="reconciler:test",
        reconciled_at="2026-09-24T23:02:00+00:00",
    )

    assert receipt.effect_confirmed is True
    assert receipt.retry_safe is False
    assert receipt.reconciliation_required is False
    assert receipt.operational_authority is False
    assert receipt.action_authority is False
    assert receipt.execution_authority is False
    assert len(receipt.receipt_sha256) == 64


def test_no_effect_confirmation_marks_semantic_retry_safe_without_authority() -> None:
    receipt = reconcile_execution_outcome(
        execution=_unknown_execution(),
        disposition="no_effect_confirmed",
        evidence_refs=(_evidence(),),
        reconciler_id="reconciler:test",
        reconciled_at="2026-09-24T23:02:00+00:00",
    )

    assert receipt.effect_confirmed is False
    assert receipt.retry_safe is True
    assert receipt.reconciliation_required is False
    assert receipt.action_authority is False
    assert receipt.execution_authority is False


def test_inconclusive_reconciliation_remains_blocked() -> None:
    receipt = reconcile_execution_outcome(
        execution=_unknown_execution(),
        disposition="inconclusive",
        evidence_refs=(_evidence(),),
        reconciler_id="reconciler:test",
        reconciled_at="2026-09-24T23:02:00+00:00",
    )

    assert receipt.effect_confirmed is None
    assert receipt.retry_safe is False
    assert receipt.reconciliation_required is True


def test_reconciliation_is_deterministic_over_evidence_order() -> None:
    first = reconcile_execution_outcome(
        execution=_unknown_execution(),
        disposition="effect_confirmed",
        evidence_refs=(_evidence("b" * 64), _evidence("c" * 64)),
        reconciler_id="reconciler:test",
        reconciled_at="2026-09-24T23:02:00+00:00",
    )
    second = reconcile_execution_outcome(
        execution=_unknown_execution(),
        disposition="effect_confirmed",
        evidence_refs=(_evidence("c" * 64), _evidence("b" * 64)),
        reconciler_id="reconciler:test",
        reconciled_at="2026-09-24T23:02:00+00:00",
    )

    assert first.evidence_ref_sha256s == second.evidence_ref_sha256s
    assert first.receipt_sha256 == second.receipt_sha256


def test_non_unknown_execution_cannot_be_reconciled() -> None:
    execution = _unknown_execution()
    execution.execution_status = "failed"

    with pytest.raises(
        ExecutionReconciliationContractError,
        match="only outcome_unknown executions can be reconciled",
    ):
        reconcile_execution_outcome(
            execution=execution,
            disposition="inconclusive",
            evidence_refs=(_evidence(),),
            reconciler_id="reconciler:test",
            reconciled_at="2026-09-24T23:02:00+00:00",
        )


def test_reconciliation_requires_evidence() -> None:
    with pytest.raises(
        ExecutionReconciliationContractError,
        match="requires at least one EvidenceRef",
    ):
        reconcile_execution_outcome(
            execution=_unknown_execution(),
            disposition="inconclusive",
            evidence_refs=(),
            reconciler_id="reconciler:test",
            reconciled_at="2026-09-24T23:02:00+00:00",
        )


def test_reconciliation_receipt_is_append_only_in_reality_ledger(
    tmp_path: Path,
) -> None:
    ledger = RealityLedger(tmp_path / "ledger" / "receipts.jsonl")
    receipt = reconcile_execution_outcome(
        execution=_unknown_execution(),
        disposition="no_effect_confirmed",
        evidence_refs=(_evidence(),),
        reconciler_id="reconciler:test",
        reconciled_at="2026-09-24T23:02:00+00:00",
    )

    ledger.append_reconciliation(receipt)
    recent = ledger.recent_reconciliations(1)

    assert len(recent) == 1
    assert recent[0]["receipt_sha256"] == receipt.receipt_sha256
    assert recent[0]["execution_receipt_id"] == "exec-unknown-001"
