from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from phios.macro_accepted_intent import (
    GhostWalkAcceptedIntentRegistry,
    GhostWalkIntentFamily,
)
from phios.macro_authority_request import (
    GhostWalkAuthorityRequestError,
    GhostWalkAuthorityRequestReadinessReason,
    GhostWalkAuthorityRequestService,
    GhostWalkAuthorityRequestState,
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
    GhostWalkPolicyAdmissionService,
    str,
]:
    ledger.path.parent.mkdir(parents=True, exist_ok=True)
    inference_path = (
        ledger.path.parent / "transition-inference-receipts.jsonl"
    )
    inference_path.write_text(
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
        created_at="2026-09-27T07:20:00+00:00",
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
        accepted_at="2026-09-27T07:21:00+00:00",
    )
    service = GhostWalkPolicyAdmissionService(
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
    return service, intent.revision_sha256


def test_readiness_requires_recorded_allow_request_admission(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    admission, _ = _seed(ledger)
    requests = GhostWalkAuthorityRequestService(
        ledger=ledger,
        policy_admission=admission,
        requester_id="operator:local",
    )

    readiness = requests.readiness(
        target_inference_receipt_sha256=TARGET
    )
    assert readiness.ready is False
    assert (
        readiness.reason
        is GhostWalkAuthorityRequestReadinessReason
        .ADMISSION_RECEIPT_REQUIRED
    )


def test_create_binds_exact_admission_and_remains_zero_authority(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    admission, intent_sha = _seed(ledger)
    receipt = admission.record(
        target_inference_receipt_sha256=TARGET,
        expected_accepted_intent_revision_sha256=intent_sha,
        expected_policy_profile_sha256=admission.profile.profile_sha256,
        evaluated_at="2026-09-27T07:22:00+00:00",
    )
    requests = GhostWalkAuthorityRequestService(
        ledger=ledger,
        policy_admission=admission,
        requester_id="operator:local",
    )

    readiness = requests.readiness(
        target_inference_receipt_sha256=TARGET
    )
    assert readiness.ready is True
    assert readiness.admission_receipt_sha256 == (
        receipt.admission_receipt_sha256
    )

    request = requests.create(
        target_inference_receipt_sha256=TARGET,
        expected_admission_receipt_sha256=(
            receipt.admission_receipt_sha256
        ),
        requested_at="2026-09-27T07:23:00+00:00",
    )
    assert request.request_state is (
        GhostWalkAuthorityRequestState.PENDING_AUTHORIZATION
    )
    assert request.authorization_granted is False
    assert request.action_lease_created is False
    assert request.action_authority is False
    assert request.execution_authority is False
    assert request.requested_scope_value == (
        "OPEN_NETWORK_ADAPTER_PROPERTIES"
    )


def test_one_request_per_admission_receipt(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    admission, intent_sha = _seed(ledger)
    receipt = admission.record(
        target_inference_receipt_sha256=TARGET,
        expected_accepted_intent_revision_sha256=intent_sha,
        expected_policy_profile_sha256=admission.profile.profile_sha256,
    )
    requests = GhostWalkAuthorityRequestService(
        ledger=ledger,
        policy_admission=admission,
        requester_id="operator:local",
    )
    requests.create(
        target_inference_receipt_sha256=TARGET,
        expected_admission_receipt_sha256=(
            receipt.admission_receipt_sha256
        ),
    )

    readiness = requests.readiness(
        target_inference_receipt_sha256=TARGET
    )
    assert readiness.ready is False
    assert (
        readiness.reason
        is GhostWalkAuthorityRequestReadinessReason
        .REQUEST_ALREADY_EXISTS
    )
    assert readiness.existing_authority_request_sha256 is not None


def test_stale_admission_cannot_seed_new_request(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    admission, intent_sha = _seed(ledger)
    receipt = admission.record(
        target_inference_receipt_sha256=TARGET,
        expected_accepted_intent_revision_sha256=intent_sha,
        expected_policy_profile_sha256=admission.profile.profile_sha256,
    )
    current = OperatorLog(ledger).current(
        note_id=f"ghostwalk-transition:{ACTION}"
    )
    OperatorLog(ledger).edit(
        note_id=current.note_id,
        expected_current_revision_sha256=current.revision_sha256,
        author_id="operator:local",
        body="Newer interpretation.",
        created_at="2026-09-27T07:24:00+00:00",
        tags=current.tags,
    )
    requests = GhostWalkAuthorityRequestService(
        ledger=ledger,
        policy_admission=admission,
        requester_id="operator:local",
    )

    readiness = requests.readiness(
        target_inference_receipt_sha256=TARGET
    )
    assert readiness.ready is False
    assert (
        readiness.reason
        is GhostWalkAuthorityRequestReadinessReason
        .POLICY_NOT_ALLOW_REQUEST
    )

    with pytest.raises(
        GhostWalkAuthorityRequestError,
        match="not ready",
    ):
        requests.create(
            target_inference_receipt_sha256=TARGET,
            expected_admission_receipt_sha256=(
                receipt.admission_receipt_sha256
            ),
        )


def test_tampered_admission_receipt_fails_closed(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    admission, intent_sha = _seed(ledger)
    admission.record(
        target_inference_receipt_sha256=TARGET,
        expected_accepted_intent_revision_sha256=intent_sha,
        expected_policy_profile_sha256=admission.profile.profile_sha256,
    )
    path = ledger.path.parent / "ghostwalk-policy-admission-receipts.jsonl"
    row = json.loads(path.read_text(encoding="utf-8"))
    row["reason"] = "INTENT_UNMAPPED"
    path.write_text(
        json.dumps(row, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    requests = GhostWalkAuthorityRequestService(
        ledger=ledger,
        policy_admission=admission,
        requester_id="operator:local",
    )

    with pytest.raises(
        GhostWalkAuthorityRequestError,
        match="admission receipt is invalid",
    ):
        requests.readiness(
            target_inference_receipt_sha256=TARGET
        )
