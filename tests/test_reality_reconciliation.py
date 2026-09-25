from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from phios.evidence_ref import EvidenceRef
from phios.reality import RealityClaim, RealityClaimKind
from phios.reality.local_network import InterfaceObservation
from phios.reality_reconciliation import (
    RealityReconciliationContractError,
    RealityReconciliationPolicy,
    reconcile_execution_with_reality,
)
from phios.spine.models import Capability, ExecutionReceipt
from phios.spine.runtime import PhiOSSpine


class StaticInterfaceProvider:
    name = "test.static-interface"

    def __init__(self, *, is_up: bool) -> None:
        self._is_up = is_up

    def observe(self, interface_name: str) -> InterfaceObservation:
        return InterfaceObservation(
            interface_name=interface_name,
            is_up=self._is_up,
            duplex=2,
            speed_mbps=1000,
            mtu=1500,
            provider=self.name,
            provider_version="1.0",
            captured_at_utc="2026-09-25T03:01:00+00:00",
        )


def _capability(
    *,
    version: str = "1.0.0",
    effects: tuple[str, ...] = ("local_state.change",),
) -> Capability:
    return Capability(
        id="network.local-interface-state",
        name="Local interface state",
        description="Change one governed local interface state.",
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
        capability_id="network.local-interface-state",
        planner="phivessel.spine.deterministic",
        input_sha256="a" * 64,
        permissions_requested=["network.change"],
        permission_status="allowed",
        execution_status="outcome_unknown",
        executor_entered=True,
        reconciliation_status="required",
        error="OutcomeUnknownError: connection lost after state change request",
    )


def _policy(
    capability: Capability,
    *,
    contradicted_disposition: str = "inconclusive",
) -> RealityReconciliationPolicy:
    return RealityReconciliationPolicy.build(
        policy_id="local-interface-postcondition-v01",
        capability=capability,
        allowed_claim_kinds=(RealityClaimKind.LOCAL_INTERFACE_STATE,),
        contradicted_disposition=contradicted_disposition,
    )


def _verify_interface(
    spine: PhiOSSpine,
    *,
    observed_is_up: bool,
    expected_is_up: bool,
):
    claim = RealityClaim.create(
        kind=RealityClaimKind.LOCAL_INTERFACE_STATE,
        statement="intended local interface postcondition is observed",
        interface_name="eth-test",
        expected_is_up=expected_is_up,
    )
    verification = spine.verify_reality(
        claims=(claim,),
        interface_provider=StaticInterfaceProvider(is_up=observed_is_up),
    )
    assert len(verification.receipt.evidence_used) == 1
    evidence_uri = verification.receipt.evidence_used[0]
    prefix = "evidence:sha256:"
    assert evidence_uri.startswith(prefix)
    evidence = EvidenceRef.build(
        source_id="interface-observer:eth-test",
        source_kind="runtime_observation",
        content_sha256=evidence_uri[len(prefix):],
        observed_at=verification.receipt.timestamp_utc,
        exactness_class="direct_observation",
    )
    return verification, evidence


def _spine(tmp_path: Path) -> PhiOSSpine:
    return PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=[
            "reality.verify",
            "reality.local_interface.read",
        ],
    )


def test_supported_reality_postcondition_confirms_uncertain_effect(
    tmp_path: Path,
) -> None:
    spine = _spine(tmp_path)
    capability = _capability()
    policy = _policy(capability)
    verification, evidence = _verify_interface(
        spine,
        observed_is_up=False,
        expected_is_up=False,
    )

    receipt = spine.reconcile_uncertain_execution(
        execution=_unknown_execution(),
        capability=capability,
        policy=policy,
        verification=verification,
        evidence_refs=(evidence,),
        reconciler_id="reconciler:local-interface",
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
    spine = _spine(tmp_path)
    capability = _capability()
    policy = _policy(
        capability,
        contradicted_disposition="no_effect_confirmed",
    )
    verification, evidence = _verify_interface(
        spine,
        observed_is_up=True,
        expected_is_up=False,
    )

    receipt = reconcile_execution_with_reality(
        execution=_unknown_execution(),
        capability=capability,
        policy=policy,
        verification=verification,
        evidence_refs=(evidence,),
        reconciler_id="reconciler:local-interface",
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
    spine = _spine(tmp_path)
    capability = _capability()
    policy = _policy(capability)
    verification, evidence = _verify_interface(
        spine,
        observed_is_up=True,
        expected_is_up=False,
    )

    receipt = reconcile_execution_with_reality(
        execution=_unknown_execution(),
        capability=capability,
        policy=policy,
        verification=verification,
        evidence_refs=(evidence,),
        reconciler_id="reconciler:local-interface",
        reconciled_at="2026-09-25T03:02:00+00:00",
    )

    assert receipt.disposition == "inconclusive"
    assert receipt.effect_confirmed is None
    assert receipt.retry_safe is False
    assert receipt.reconciliation_required is True


def test_capability_effect_scope_drift_fails_closed(
    tmp_path: Path,
) -> None:
    spine = _spine(tmp_path)
    original = _capability()
    policy = _policy(original)
    drifted = _capability(effects=("control_plane.change",))
    verification, evidence = _verify_interface(
        spine,
        observed_is_up=False,
        expected_is_up=False,
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
            reconciler_id="reconciler:local-interface",
            reconciled_at="2026-09-25T03:02:00+00:00",
        )


def test_unrelated_canonical_evidence_cannot_reconcile_reality_result(
    tmp_path: Path,
) -> None:
    spine = _spine(tmp_path)
    capability = _capability()
    policy = _policy(capability)
    verification, _ = _verify_interface(
        spine,
        observed_is_up=False,
        expected_is_up=False,
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
            reconciler_id="reconciler:local-interface",
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


def test_tampered_reality_claim_results_cannot_be_reconciled(
    tmp_path: Path,
) -> None:
    spine = _spine(tmp_path)
    capability = _capability()
    policy = _policy(capability)
    verification, evidence = _verify_interface(
        spine,
        observed_is_up=False,
        expected_is_up=False,
    )
    tampered = replace(
        verification,
        claim_results=(
            {
                **verification.claim_results[0],
                "verdict": "CONTRADICTED",
            },
        ),
    )

    with pytest.raises(
        RealityReconciliationContractError,
        match="claims_checked does not match claim_results",
    ):
        reconcile_execution_with_reality(
            execution=_unknown_execution(),
            capability=capability,
            policy=policy,
            verification=tampered,
            evidence_refs=(evidence,),
            reconciler_id="reconciler:local-interface",
            reconciled_at="2026-09-25T03:02:00+00:00",
        )
