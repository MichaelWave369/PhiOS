from dataclasses import replace
from pathlib import Path

import pytest

from phios.mandala import GovernanceEscalationError, MandalaStatus
from phios.reality import RealityClaim, RealityClaimKind
from phios.spine.runtime import PhiOSSpine


def _text_evidence(spine: PhiOSSpine, text: str) -> str:
    return spine.soma.evidence.put_text(text).evidence_ref


def _contradicted(spine: PhiOSSpine):
    ref = _text_evidence(spine, "PORT 24 UP")
    claim = RealityClaim.create(
        kind=RealityClaimKind.SOURCE_CONTAINS_TEXT,
        statement="The cited text contains PORT 24 DOWN.",
        evidence_refs=(ref,),
        expected_text="PORT 24 DOWN",
    )
    return claim, spine.verify_reality(claims=(claim,))


def _supported(spine: PhiOSSpine):
    ref = _text_evidence(spine, "PORT 24 DOWN")
    claim = RealityClaim.create(
        kind=RealityClaimKind.SOURCE_CONTAINS_TEXT,
        statement="The cited text contains PORT 24 DOWN.",
        evidence_refs=(ref,),
        expected_text="PORT 24 DOWN",
    )
    return claim, spine.verify_reality(claims=(claim,))


def _unresolved(spine: PhiOSSpine):
    claim = RealityClaim.create(
        kind=RealityClaimKind.WORLD_STATE,
        statement="Physical switch port 24 is currently down.",
    )
    return claim, spine.verify_reality(claims=(claim,))


def test_contradiction_can_route_review_without_minting_authority(
    tmp_path: Path,
) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("reality.verify",),
        task_id="escalation-review",
    )
    claim, verification = _contradicted(spine)
    authority_before = spine.core.authority

    result = spine.escalate_reality_finding(
        verification=verification,
        disposition="REVIEW",
        trigger_claim_ids=(claim.claim_id,),
        reason="contradicted reality claim requires operator review",
        target_ref="governance.operator_review",
    )

    semantics = result.verifier_semantics
    escalation = result.escalation
    assert semantics.may_emit_escalation_request is True
    assert semantics.may_authorize_remediation is False
    assert semantics.may_execute_remediation is False
    assert semantics.may_promote is False
    assert (
        semantics.observation_frontier_sha256
        == verification.receipt.observation_frontier_sha256
    )
    assert (
        semantics.observability_receipt_sha256
        == verification.receipt.observability_receipt_sha256
    )
    assert semantics.observability_status == verification.receipt.observability_status
    assert semantics.operational_authority is False
    assert semantics.action_authority is False
    assert semantics.execution_authority is False
    assert escalation.status is MandalaStatus.ACCEPTED
    assert escalation.routing_status == "ROUTED_FOR_REVIEW"
    assert escalation.downstream_authority_required is True
    assert escalation.remediation_authorized is False
    assert escalation.remediation_executed is False
    assert escalation.promotion_status == "not_promoted"
    assert spine.core.authority == authority_before


def test_remediation_candidate_routes_only_for_authorization(
    tmp_path: Path,
) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("reality.verify",),
        task_id="escalation-remediate",
    )
    claim, verification = _contradicted(spine)
    payload = {"name": "proposed-fix", "text": "candidate only"}

    result = spine.escalate_reality_finding(
        verification=verification,
        disposition="REMEDIATE",
        trigger_claim_ids=(claim.claim_id,),
        reason="propose bounded corrective artifact",
        target_ref="governed_action_binding.review",
        candidate_capability_id="commons.text_artifact",
        candidate_payload=payload,
    )

    escalation = result.escalation
    assert escalation.status is MandalaStatus.ACCEPTED
    assert escalation.routing_status == "ROUTED_FOR_AUTHORIZATION"
    assert escalation.candidate_capability_id == "commons.text_artifact"
    assert escalation.candidate_capability_version == "0.1.0"
    assert escalation.candidate_capability_risk == "low"
    assert escalation.candidate_capability_contract_sha256
    assert escalation.candidate_payload_sha256
    assert escalation.requested_permissions == ("artifact.write",)
    assert escalation.requested_effects == ("filesystem.change",)
    assert escalation.action_authority is False
    assert escalation.execution_authority is False
    assert not (tmp_path / "artifacts" / "proposed-fix.txt").exists()
    assert not any(
        row["receipt_type"] == "ActionReceipt"
        for row in spine.mandala_ledger.recent(10)
    )


def test_unresolved_claim_cannot_route_remediation(
    tmp_path: Path,
) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("reality.verify",),
        task_id="escalation-unresolved",
    )
    claim, verification = _unresolved(spine)

    result = spine.escalate_reality_finding(
        verification=verification,
        disposition="REMEDIATE",
        trigger_claim_ids=(claim.claim_id,),
        reason="do not mutate from unresolved evidence",
        target_ref="governed_action_binding.review",
        candidate_capability_id="commons.text_artifact",
        candidate_payload={"name": "must-not-run", "text": "held"},
    )

    escalation = result.escalation
    assert escalation.status is MandalaStatus.BLOCKED
    assert escalation.routing_status == "HELD"
    assert escalation.reason == (
        "remediation_requires_only_contradicted_trigger_claims"
    )
    assert escalation.remediation_authorized is False
    assert escalation.remediation_executed is False
    assert not (tmp_path / "artifacts" / "must-not-run.txt").exists()


def test_unresolved_claim_can_route_reverification(
    tmp_path: Path,
) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("reality.verify",),
        task_id="escalation-reverify",
    )
    claim, verification = _unresolved(spine)

    result = spine.escalate_reality_finding(
        verification=verification,
        disposition="REVERIFY",
        trigger_claim_ids=(claim.claim_id,),
        reason="needs an independent world-state verifier",
        target_ref="reality.reverification_queue",
    )

    assert result.escalation.status is MandalaStatus.ACCEPTED
    assert result.escalation.routing_status == "ROUTED_FOR_REVERIFICATION"
    assert result.escalation.candidate_capability_id is None


def test_supported_claim_does_not_create_problem_escalation(
    tmp_path: Path,
) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("reality.verify",),
        task_id="escalation-supported",
    )
    claim, verification = _supported(spine)

    result = spine.escalate_reality_finding(
        verification=verification,
        disposition="REVIEW",
        trigger_claim_ids=(claim.claim_id,),
        reason="attempt to escalate healthy result",
        target_ref="governance.operator_review",
    )

    assert result.escalation.status is MandalaStatus.BLOCKED
    assert result.escalation.routing_status == "HELD"
    assert result.escalation.reason == (
        "escalation_requires_problematic_verifier_result"
    )


def test_escalation_requires_persisted_exact_verifier_receipt(
    tmp_path: Path,
) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("reality.verify",),
        task_id="escalation-source-binding",
    )
    claim, verification = _contradicted(spine)
    forged = replace(
        verification.receipt,
        limitations=verification.receipt.limitations + ("forged",),
    )
    forged_verification = replace(verification, receipt=forged)

    with pytest.raises(GovernanceEscalationError, match="persisted evidence"):
        spine.escalate_reality_finding(
            verification=forged_verification,
            disposition="REVIEW",
            trigger_claim_ids=(claim.claim_id,),
            reason="forged source must fail",
            target_ref="governance.operator_review",
        )


def test_cross_task_verifier_receipt_cannot_be_escalated(
    tmp_path: Path,
) -> None:
    source = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("reality.verify",),
        task_id="source-task",
    )
    claim, verification = _contradicted(source)
    consumer = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("reality.verify",),
        task_id="consumer-task",
    )

    with pytest.raises(ValueError, match="active Spine task"):
        consumer.escalate_reality_finding(
            verification=verification,
            disposition="REVIEW",
            trigger_claim_ids=(claim.claim_id,),
            reason="stale cross-task finding",
            target_ref="governance.operator_review",
        )


def test_escalation_receipts_are_parent_linked_to_exact_detection(
    tmp_path: Path,
) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("reality.verify",),
        task_id="escalation-lineage",
    )
    claim, verification = _contradicted(spine)

    result = spine.escalate_reality_finding(
        verification=verification,
        disposition="REVIEW",
        trigger_claim_ids=(claim.claim_id,),
        reason="review finding",
        target_ref="governance.operator_review",
    )

    rows = spine.mandala_ledger.recent(4)
    assert [row["receipt_type"] for row in rows] == [
        "GateReceipt",
        "RealityReceipt",
        "VerifierSemanticsReceipt",
        "GovernanceEscalationReceipt",
    ]
    assert rows[2]["parent_receipt_id"] == verification.receipt.receipt_id
    assert rows[3]["parent_receipt_id"] == result.verifier_semantics.receipt_id
    assert (
        rows[3]["verifier_semantics_receipt_sha256"]
        == result.verifier_semantics.receipt_sha256
    )


def test_non_remediation_escalation_cannot_smuggle_action_candidate(
    tmp_path: Path,
) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("reality.verify",),
        task_id="escalation-smuggle",
    )
    claim, verification = _contradicted(spine)

    with pytest.raises(ValueError, match="cannot carry an action candidate"):
        spine.escalate_reality_finding(
            verification=verification,
            disposition="REVIEW",
            trigger_claim_ids=(claim.claim_id,),
            reason="bad action smuggle",
            target_ref="governance.operator_review",
            candidate_capability_id="commons.text_artifact",
            candidate_payload={"name": "nope", "text": "nope"},
        )
