from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from phios.macro_accepted_intent import (
    GhostWalkAcceptedIntentRegistry,
    GhostWalkIntentFamily,
)
from phios.macro_authority_request import GhostWalkAuthorityRequestService
from phios.macro_authorization_decision import (
    GhostWalkAuthorizationDecisionError,
    GhostWalkAuthorizationDecisionKind,
    GhostWalkAuthorizationDecisionService,
    GhostWalkAuthorizationReadinessReason,
)
from phios.macro_ghostwalk_operator_editor import GhostWalkOperatorEditor
from phios.macro_operator_log import OperatorLog
from phios.macro_policy_admission import (
    GhostWalkPolicyAdmissionService,
    GhostWalkPolicyProfile,
)
from phios.spine.ledger import RealityLedger

ACTION = "b" * 64
_INFERENCE_BODY = {
    "status": "CANDIDATES",
    "session_id": "demo",
    "action_observation_sha256": ACTION,
}
TARGET = hashlib.sha256(
    json.dumps(
        _INFERENCE_BODY,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
).hexdigest()


def _ledger(tmp_path: Path) -> RealityLedger:
    return RealityLedger(tmp_path / "ledger" / "receipts.jsonl")


def _seed(
    ledger: RealityLedger,
) -> tuple[
    GhostWalkAuthorizationDecisionService,
    GhostWalkAuthorityRequestService,
    GhostWalkPolicyAdmissionService,
]:
    ledger.path.parent.mkdir(parents=True, exist_ok=True)
    (
        ledger.path.parent / "transition-inference-receipts.jsonl"
    ).write_text(
        json.dumps(
            {
                **_INFERENCE_BODY,
                "receipt_sha256": TARGET,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    note = OperatorLog(ledger).create(
        note_id=f"ghostwalk-transition:{ACTION}",
        target_sha256=TARGET,
        author_id="operator:local",
        body="Opened network adapter properties.",
        created_at="2026-09-27T08:20:00+00:00",
        tags=(
            "ghostwalk",
            "operator-interpretation",
            "transition-inference",
        ),
    )
    accepted = GhostWalkAcceptedIntentRegistry(
        ledger=ledger,
        accepted_by="operator:local",
    )
    intent = accepted.accept(
        target_inference_receipt_sha256=TARGET,
        source_operator_note_revision_sha256=note.revision_sha256,
        intent_family=GhostWalkIntentFamily.OPEN,
        intent_code="OPEN_NETWORK_ADAPTER_PROPERTIES",
        expected_current_revision_sha256=None,
        accepted_at="2026-09-27T08:21:00+00:00",
    )
    admission = GhostWalkPolicyAdmissionService(
        ledger=ledger,
        accepted_intents=accepted,
        operator_editor=GhostWalkOperatorEditor(
            ledger=ledger,
            author_id="operator:local",
        ),
        profile=GhostWalkPolicyProfile(
            profile_id="ghostwalk-policy:test",
            allow_request_intent_codes=(
                "OPEN_NETWORK_ADAPTER_PROPERTIES",
            ),
            deny_intent_codes=(),
        ),
    )
    admission_receipt = admission.record(
        target_inference_receipt_sha256=TARGET,
        expected_accepted_intent_revision_sha256=intent.revision_sha256,
        expected_policy_profile_sha256=admission.profile.profile_sha256,
        evaluated_at="2026-09-27T08:22:00+00:00",
    )
    requests = GhostWalkAuthorityRequestService(
        ledger=ledger,
        policy_admission=admission,
        requester_id="operator:local",
    )
    requests.create(
        target_inference_receipt_sha256=TARGET,
        expected_admission_receipt_sha256=(
            admission_receipt.admission_receipt_sha256
        ),
        requested_at="2026-09-27T08:23:00+00:00",
    )
    decisions = GhostWalkAuthorizationDecisionService(
        ledger=ledger,
        authority_requests=requests,
        authorizer_id="operator:local",
    )
    return decisions, requests, admission


def test_approve_records_authorization_fact_without_action_authority(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    decisions, requests, _ = _seed(ledger)
    request = requests.latest(
        target_inference_receipt_sha256=TARGET
    )
    assert request is not None

    readiness = decisions.readiness(
        target_inference_receipt_sha256=TARGET
    )
    assert readiness.ready is True
    assert readiness.reason is GhostWalkAuthorizationReadinessReason.READY

    decision = decisions.record(
        target_inference_receipt_sha256=TARGET,
        expected_authority_request_sha256=(
            request.authority_request_sha256
        ),
        expected_previous_decision_sha256=None,
        decision=GhostWalkAuthorizationDecisionKind.APPROVE,
        decision_note="Approve exact semantic request only.",
        decided_at="2026-09-27T08:24:00+00:00",
    )
    assert decision.authorization_granted is True
    assert decision.request_resolved is True
    assert decision.capability_binding_created is False
    assert decision.action_lease_created is False
    assert decision.action_authority is False
    assert decision.execution_authority is False
    assert decision.effect_performed is False


def test_hold_can_be_followed_by_approve_with_hash_chain(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    decisions, requests, _ = _seed(ledger)
    request = requests.latest(
        target_inference_receipt_sha256=TARGET
    )
    assert request is not None

    held = decisions.record(
        target_inference_receipt_sha256=TARGET,
        expected_authority_request_sha256=(
            request.authority_request_sha256
        ),
        expected_previous_decision_sha256=None,
        decision=GhostWalkAuthorizationDecisionKind.HOLD,
        decided_at="2026-09-27T08:24:00+00:00",
    )
    readiness = decisions.readiness(
        target_inference_receipt_sha256=TARGET
    )
    assert readiness.ready is True
    assert readiness.latest_decision == "HOLD"
    assert (
        readiness.latest_decision_sha256
        == held.authorization_decision_sha256
    )

    approved = decisions.record(
        target_inference_receipt_sha256=TARGET,
        expected_authority_request_sha256=(
            request.authority_request_sha256
        ),
        expected_previous_decision_sha256=(
            held.authorization_decision_sha256
        ),
        decision=GhostWalkAuthorizationDecisionKind.APPROVE,
        decided_at="2026-09-27T08:25:00+00:00",
    )
    assert approved.decision_sequence == 1
    assert (
        approved.previous_decision_sha256
        == held.authorization_decision_sha256
    )
    assert approved.authorization_granted is True


def test_deny_is_terminal(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    decisions, requests, _ = _seed(ledger)
    request = requests.latest(
        target_inference_receipt_sha256=TARGET
    )
    assert request is not None

    denied = decisions.record(
        target_inference_receipt_sha256=TARGET,
        expected_authority_request_sha256=(
            request.authority_request_sha256
        ),
        expected_previous_decision_sha256=None,
        decision=GhostWalkAuthorizationDecisionKind.DENY,
    )
    readiness = decisions.readiness(
        target_inference_receipt_sha256=TARGET
    )
    assert readiness.ready is False
    assert (
        readiness.reason
        is GhostWalkAuthorizationReadinessReason.DECISION_FINAL
    )
    assert readiness.authorization_granted is False

    with pytest.raises(
        GhostWalkAuthorizationDecisionError,
        match="not ready",
    ):
        decisions.record(
            target_inference_receipt_sha256=TARGET,
            expected_authority_request_sha256=(
                request.authority_request_sha256
            ),
            expected_previous_decision_sha256=(
                denied.authorization_decision_sha256
            ),
            decision=GhostWalkAuthorizationDecisionKind.APPROVE,
        )


def test_stale_authority_request_cannot_be_authorized(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    decisions, requests, _ = _seed(ledger)
    request = requests.latest(
        target_inference_receipt_sha256=TARGET
    )
    assert request is not None

    current = OperatorLog(ledger).current(
        note_id=f"ghostwalk-transition:{ACTION}"
    )
    OperatorLog(ledger).edit(
        note_id=current.note_id,
        expected_current_revision_sha256=current.revision_sha256,
        author_id="operator:local",
        body="Interpretation changed after request creation.",
        created_at="2026-09-27T08:26:00+00:00",
        tags=current.tags,
    )

    readiness = decisions.readiness(
        target_inference_receipt_sha256=TARGET
    )
    assert readiness.ready is False
    assert (
        readiness.reason
        is GhostWalkAuthorizationReadinessReason
        .AUTHORITY_REQUEST_STALE
    )

    with pytest.raises(
        GhostWalkAuthorizationDecisionError,
        match="not ready",
    ):
        decisions.record(
            target_inference_receipt_sha256=TARGET,
            expected_authority_request_sha256=(
                request.authority_request_sha256
            ),
            expected_previous_decision_sha256=None,
            decision=GhostWalkAuthorizationDecisionKind.APPROVE,
        )


def test_optimistic_concurrency_rejects_stale_previous_decision(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    decisions, requests, _ = _seed(ledger)
    request = requests.latest(
        target_inference_receipt_sha256=TARGET
    )
    assert request is not None

    held = decisions.record(
        target_inference_receipt_sha256=TARGET,
        expected_authority_request_sha256=(
            request.authority_request_sha256
        ),
        expected_previous_decision_sha256=None,
        decision=GhostWalkAuthorizationDecisionKind.HOLD,
    )
    assert held.authorization_decision_sha256

    with pytest.raises(
        GhostWalkAuthorizationDecisionError,
        match="history changed",
    ):
        decisions.record(
            target_inference_receipt_sha256=TARGET,
            expected_authority_request_sha256=(
                request.authority_request_sha256
            ),
            expected_previous_decision_sha256=None,
            decision=GhostWalkAuthorizationDecisionKind.APPROVE,
        )


def test_tampered_authorization_decision_fails_closed(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    decisions, requests, _ = _seed(ledger)
    request = requests.latest(
        target_inference_receipt_sha256=TARGET
    )
    assert request is not None
    decisions.record(
        target_inference_receipt_sha256=TARGET,
        expected_authority_request_sha256=(
            request.authority_request_sha256
        ),
        expected_previous_decision_sha256=None,
        decision=GhostWalkAuthorizationDecisionKind.HOLD,
    )

    path = (
        ledger.path.parent
        / "ghostwalk-authorization-decisions.jsonl"
    )
    row = json.loads(path.read_text(encoding="utf-8"))
    row["authorizer_id"] = "tampered"
    path.write_text(
        json.dumps(row, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        GhostWalkAuthorizationDecisionError,
        match="persisted AuthorizationDecision is invalid",
    ):
        decisions.latest(
            target_inference_receipt_sha256=TARGET
        )
