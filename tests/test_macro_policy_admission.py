from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from phios.macro_accepted_intent import (
    GhostWalkAcceptedIntentRegistry,
    GhostWalkIntentFamily,
)
from phios.macro_ghostwalk_operator_editor import GhostWalkOperatorEditor
from phios.macro_operator_log import OperatorLog
from phios.macro_policy_admission import (
    GhostWalkPolicyAdmissionError,
    GhostWalkPolicyAdmissionService,
    GhostWalkPolicyDecision,
    GhostWalkPolicyProfile,
    GhostWalkPolicyReason,
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
    *,
    intent_code: str = "OPEN_NETWORK_ADAPTER_PROPERTIES",
) -> tuple[str, str]:
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
        body="Correction: opened network adapter properties.",
        created_at="2026-09-27T07:10:00+00:00",
        tags=(
            "ghostwalk",
            "operator-interpretation",
            "transition-inference",
        ),
    )
    registry = GhostWalkAcceptedIntentRegistry(
        ledger=ledger,
        accepted_by="operator:local",
    )
    accepted = registry.accept(
        target_inference_receipt_sha256=TARGET,
        source_operator_note_revision_sha256=note.revision_sha256,
        intent_family=GhostWalkIntentFamily.OPEN,
        intent_code=intent_code,
        expected_current_revision_sha256=None,
        accepted_at="2026-09-27T07:11:00+00:00",
    )
    return note.revision_sha256, accepted.revision_sha256


def _service(
    ledger: RealityLedger,
    *,
    allow: tuple[str, ...] = (),
    deny: tuple[str, ...] = (),
) -> GhostWalkPolicyAdmissionService:
    return GhostWalkPolicyAdmissionService(
        ledger=ledger,
        accepted_intents=GhostWalkAcceptedIntentRegistry(
            ledger=ledger,
            accepted_by="operator:local",
        ),
        operator_editor=GhostWalkOperatorEditor(
            ledger=ledger,
            author_id="operator:local",
        ),
        profile=GhostWalkPolicyProfile(
            profile_id="ghostwalk-policy:test",
            allow_request_intent_codes=allow,
            deny_intent_codes=deny,
        ),
    )


def test_unmapped_intent_holds_by_default(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    _seed(ledger)
    projection = _service(ledger).project(
        target_inference_receipt_sha256=TARGET
    )
    assert projection.decision is GhostWalkPolicyDecision.HOLD
    assert projection.reason is GhostWalkPolicyReason.INTENT_UNMAPPED
    assert projection.request_authority_eligible is False
    assert projection.action_authority is False


def test_explicit_allow_makes_request_eligible_without_authority(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    _seed(ledger)
    projection = _service(
        ledger,
        allow=("OPEN_NETWORK_ADAPTER_PROPERTIES",),
    ).project(target_inference_receipt_sha256=TARGET)

    assert projection.decision is GhostWalkPolicyDecision.ALLOW_REQUEST
    assert projection.request_authority_eligible is True
    assert projection.policy_authority is False
    assert projection.action_authority is False
    assert projection.execution_authority is False


def test_explicit_deny_wins_as_policy_decision(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    _seed(ledger)
    projection = _service(
        ledger,
        deny=("OPEN_NETWORK_ADAPTER_PROPERTIES",),
    ).project(target_inference_receipt_sha256=TARGET)
    assert projection.decision is GhostWalkPolicyDecision.DENY
    assert (
        projection.reason
        is GhostWalkPolicyReason.INTENT_EXPLICITLY_DENIED
    )


def test_stale_operator_binding_holds_even_if_code_allowed(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    note_sha, _ = _seed(ledger)
    current = OperatorLog(ledger).current(
        note_id=f"ghostwalk-transition:{ACTION}"
    )
    assert current.revision_sha256 == note_sha
    OperatorLog(ledger).edit(
        note_id=current.note_id,
        expected_current_revision_sha256=note_sha,
        author_id="operator:local",
        body="Newer human interpretation.",
        created_at="2026-09-27T07:12:00+00:00",
        tags=current.tags,
    )

    projection = _service(
        ledger,
        allow=("OPEN_NETWORK_ADAPTER_PROPERTIES",),
    ).project(target_inference_receipt_sha256=TARGET)
    assert projection.decision is GhostWalkPolicyDecision.HOLD
    assert (
        projection.reason
        is GhostWalkPolicyReason.STALE_OPERATOR_BINDING
    )


def test_record_binds_exact_intent_and_policy_without_authority(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    _, intent_sha = _seed(ledger)
    service = _service(
        ledger,
        allow=("OPEN_NETWORK_ADAPTER_PROPERTIES",),
    )

    receipt = service.record(
        target_inference_receipt_sha256=TARGET,
        expected_accepted_intent_revision_sha256=intent_sha,
        expected_policy_profile_sha256=service.profile.profile_sha256,
        evaluated_at="2026-09-27T07:13:00+00:00",
    )

    assert receipt.request_authority_eligible is True
    assert receipt.authority_request_created is False
    assert receipt.action_lease_created is False
    assert receipt.execution_authority is False
    assert receipt.effect_performed is True
    assert len(ledger.ghostwalk_policy_admission_receipts()) == 1


def test_record_rejects_stale_expected_intent(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    _seed(ledger)
    service = _service(ledger)

    with pytest.raises(
        GhostWalkPolicyAdmissionError,
        match="accepted intent changed",
    ):
        service.record(
            target_inference_receipt_sha256=TARGET,
            expected_accepted_intent_revision_sha256="f" * 64,
            expected_policy_profile_sha256=service.profile.profile_sha256,
        )


def test_policy_env_is_fail_closed_and_rejects_overlap() -> None:
    empty = GhostWalkPolicyProfile.from_environment({})
    assert empty.allow_request_intent_codes == ()
    assert empty.deny_intent_codes == ()
    assert empty.default_decision is GhostWalkPolicyDecision.HOLD

    with pytest.raises(
        GhostWalkPolicyAdmissionError,
        match="must not overlap",
    ):
        GhostWalkPolicyProfile.from_environment(
            {
                "PHIOS_GHOSTWALK_POLICY_ALLOW_REQUEST": "OPEN_SETTINGS",
                "PHIOS_GHOSTWALK_POLICY_DENY": "OPEN_SETTINGS",
            }
        )
