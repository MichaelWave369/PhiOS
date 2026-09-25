from __future__ import annotations

from pathlib import Path

import pytest

from phios.evidence_ref import EvidenceRef
from phios.reality import RealityClaim, RealityClaimKind
from phios.reality_reconciliation import (
    RealityReconciliationContractError,
    RealityReconciliationPolicy,
    reconcile_execution_with_reality,
)
from phios.spine.models import Capability, ExecutionReceipt
from phios.spine.runtime import PhiOSSpine


def _capability(
    *,
    version: str = "1.0.0",
    effects: tuple[str, ...] = ("external_state.change",),
) -> Capability:
    return Capability(
        id="network.switch.port-state",
        name="Switch port state",
        description="Change one governed switch-port state.",
        permissions=("network.change",),
        effects=effects,
        risk="medium",
        version=version,
    )


def _unknown_execution() -> ExecutionReceipt:
    return ExecutionReceipt(
        schema_version="phios.execution_receipt.v0.1",
        receipt_id="exec-reality-unknown-001",
        timestamp_utc="2026-09-25T03:00:00+00:00",
        capability_id="network.switch.port-state",
        planner="phivessel.spine.deterministic",
        input_sha256="a" * 64,
        permissions_requested=["network.change"],
        permission_status="allowed",
        execution_status="outcome_unknown",
        executor_entered=True,
        reconciliation_status="required",
        error="OutcomeUnknownError: connection lost after command send",
    )


def _policy(
    capability: Capability,
    *,
    contradicted_disposition: str = "inconclusive",
) -> RealityReconciliationPolicy:
    return RealityReconciliationPolicy.build(
        policy_id="switch-port-postcondition-v01",
        capability=capability,
        allowed_claim_kinds=(RealityClaimKind.SOURCE_CONTAINS_TEXT,),
        contradicted_disposition=contradicted_disposition,
    )


def _verify_text(
    spine: PhiOSSpine,
    *,
    observed_text: str,
    expected_text: str,
):
    observation = spine.perceive_text(
        source_id="switch-observer:test",
        text=observed_text,
    )
    claim = RealityClaim.create(
        kind=RealityClaimKind.SOURCE_CONTAINS_TEXT,
        statement="intended switch-port postcondition is present",
        evidence_refs=(observation.evidence.evidence_ref,),
        expected_text=expected_text,
    )
    verification = spine.verify_reality(claims=(claim,))
    evidence = EvidenceRef.build(
        source_id="switch-observer:test",
        source_kind="runtime_observation",
        content_sha256=observation.evidence.sha256,
        observed_at=observation.receipt.timestamp_utc,
        exactness_class=observation.receipt.exactness_class,
    )
    return verification, evidence


def test_supported_reality_postcondition_confirms_uncertain_effect(
    tmp_path: Path,
) -> None:
    spine = PhiOSSpine(state_root=tmp_path)
    capability = _capability()
    policy = _policy(capability)
    verification, evidence = _verify_text(
        spine,
        observed_text="interface Gi1/0/24 state=down",
        expected_text="state=down",
    )

    receipt = spine.reconcile_uncertain_execution(
        execution=_unknown_execution(),
        capability=capability,
        policy=policy,
        verification=verification,
        evidence_refs=(evidence,),
        reconciler_id="reconciler:switch-state",
        reconciled_at="2026-09-25T03:02:00+00:00",
    )

    assert receipt.disposition == "effect_confirmed"
    assert receipt.effect_confirmed is True
    assert receipt.retry_safe is False
    assert receipt.reconciliation_required is False
    assert receipt.policy_sha256 == policy.policy_sha256
    assert receipt.action_authority is False
    assert receipt.execution_authority is False

    recent = spine.ledger.recent_reconciliations(1)
    assert len(recent) == 1
    assert recent[0]["receipt_sha256"] == receipt.receipt_sha256
    assert recent[0]["policy_sha256"] == policy.policy_sha256


def test_contradicted_postcondition_can_confirm_no_effect_only_when_policy_allows(
    tmp_path: Path,
) -> None:
    spine = PhiOSSpine(state_root=tmp_path)
    capability = _capability()
    policy = _policy(
        capability,
        contradicted_disposition="no_effect_confirmed",
    )
    verification, evidence = _verify_text(
        spine,
        observed_text="interface Gi1/0/24 state=up",
        expected_text="state=down",
    )

    receipt = reconcile_execution_with_reality(
        execution=_unknown_execution(),
        capability=capability,
        policy=policy,
        verification=verification,
        evidence_refs=(evidence,),
        reconciler_id="reconciler:switch-state",
        reconciled_at="2026-09-25T03:02:00+00:00",
    )

    assert receipt.disposition == "no_effect_confirmed"
    assert receipt.effect_confirmed is False
    assert receipt.retry_safe is True
    assert receipt.reconciliation_required is False
    assert receipt.action_authority is False
    assert receipt.execution_authority is False


def test_contradiction_defaults_to_inconclusive(
    tmp_path: Path,
) -> None:
    spine = PhiOSSpine(state_root=tmp_path)
    capability = _capability()
    policy = _policy(capability)
    verification, evidence = _verify_text(
        spine,
        observed_text="interface Gi1/0/24 state=up",
        expected_text="state=down",
    )

    receipt = reconcile_execution_with_reality(
        execution=_unknown_execution(),
        capability=capability,
        policy=policy,
        verification=verification,
        evidence_refs=(evidence,),
        reconciler_id="reconciler:switch-state",
        reconciled_at="2026-09-25T03:02:00+00:00",
    )

    assert receipt.disposition == "inconclusive"
    assert receipt.effect_confirmed is None
    assert receipt.retry_safe is False
    assert receipt.reconciliation_required is True


def test_capability_effect_scope_drift_fails_closed(
    tmp_path: Path,
) -> None:
    spine = PhiOSSpine(state_root=tmp_path)
    original = _capability()
    policy = _policy(original)
    drifted = _capability(effects=("control_plane.change",))
    verification, evidence = _verify_text(
        spine,
        observed_text="interface Gi1/0/24 state=down",
        expected_text="state=down",
    )

    with pytest.raises(
        RealityReconciliationContractError,
        match="effect scope mismatch",
    ):
        reconcile_execution_with_reality(
            execution=_unknown_execution(),
            capability=drifted,
            policy=policy,
            verification=verification,
            evidence_refs=(evidence,),
            reconciler_id="reconciler:switch-state",
            reconciled_at="2026-09-25T03:02:00+00:00",
        )


def test_unrelated_canonical_evidence_cannot_reconcile_reality_result(
    tmp_path: Path,
) -> None:
    spine = PhiOSSpine(state_root=tmp_path)
    capability = _capability()
    policy = _policy(capability)
    verification, _ = _verify_text(
        spine,
        observed_text="interface Gi1/0/24 state=down",
        expected_text="state=down",
    )
    unrelated = EvidenceRef.build(
        source_id="unrelated",
        source_kind="runtime_observation",
        content_sha256="f" * 64,
        observed_at="2026-09-25T03:01:00+00:00",
        exactness_class="direct_observation",
    )

    with pytest.raises(
        RealityReconciliationContractError,
        match="must exactly cover Reality evidence_used",
    ):
        reconcile_execution_with_reality(
            execution=_unknown_execution(),
            capability=capability,
            policy=policy,
            verification=verification,
            evidence_refs=(unrelated,),
            reconciler_id="reconciler:switch-state",
            reconciled_at="2026-09-25T03:02:00+00:00",
        )


def test_policy_digest_is_deterministic_and_zero_authority() -> None:
    capability = _capability()
    first = _policy(capability)
    second = _policy(capability)

    assert first.policy_sha256 == second.policy_sha256
    assert first.operational_authority is False
    assert first.action_authority is False
    assert first.execution_authority is False
