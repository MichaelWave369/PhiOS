from __future__ import annotations

import json
from pathlib import Path

import pytest

from phios.macro_accepted_intent import (
    GhostWalkAcceptedIntentRegistry,
    GhostWalkIntentFamily,
)
from phios.macro_authority_request import GhostWalkAuthorityRequestService
from phios.macro_authorization_decision import (
    GhostWalkAuthorizationDecisionKind,
    GhostWalkAuthorizationDecisionService,
)
from phios.macro_capability_binding import (
    GhostWalkBindingReadinessReason,
    GhostWalkCapabilityBindingError,
    GhostWalkCapabilityBindingService,
    GhostWalkCapabilityMapping,
    GhostWalkCapabilityMappingRegistry,
)
from phios.macro_ghostwalk import (
    GhostWalkRecorder,
    SemanticTarget,
    TargetStrategy,
)
from phios.macro_ghostwalk_operator_editor import GhostWalkOperatorEditor
from phios.macro_interaction_guard import WindowFrame
from phios.macro_operator_log import OperatorLog
from phios.macro_policy_admission import (
    GhostWalkPolicyAdmissionService,
    GhostWalkPolicyProfile,
)
from phios.macro_transition_inference import (
    TransitionInferenceReceipt,
    TransitionInferenceStatus,
)
from phios.spine.ledger import RealityLedger

INTENT_CODE = "OPEN_NETWORK_ADAPTER_PROPERTIES"


def _ledger(tmp_path: Path) -> RealityLedger:
    return RealityLedger(tmp_path / "ledger" / "receipts.jsonl")


def _mapping(
    *,
    mapping_id: str = "ghostwalk.open-network-adapter.desktop-click.v1",
    strategy: TargetStrategy = TargetStrategy.SEMANTIC,
) -> GhostWalkCapabilityMapping:
    return GhostWalkCapabilityMapping.desktop_click(
        mapping_id=mapping_id,
        intent_code=INTENT_CODE,
        required_target_strategy=strategy,
    )


def _seed(
    ledger: RealityLedger,
    *,
    semantic: bool = True,
) -> tuple[
    str,
    str,
    GhostWalkAuthorizationDecisionService,
    GhostWalkAuthorityRequestService,
]:
    recorder = GhostWalkRecorder(ledger)
    recorder.start(
        session_id="demo",
        recorder_id="operator:local",
        started_at="2026-09-27T18:30:00+00:00",
    )
    frame = WindowFrame(
        process_id="control.exe",
        window_title_sha256="a" * 64,
        left_px=100,
        top_px=100,
        width_px=1200,
        height_px=800,
        display_scale_percent=100,
        foreground=True,
        captured_at="2026-09-27T18:30:01+00:00",
    )
    target = (
        SemanticTarget(
            provider="windows-uia",
            selector="root/settings/network/adapter-properties",
            role="button",
            name_hint="Adapter properties",
        )
        if semantic
        else None
    )
    observation = recorder.record_click(
        session_id="demo",
        frame=frame,
        x_px=640,
        y_px=420,
        observed_at="2026-09-27T18:30:02+00:00",
        semantic_target=target,
        semantic_hint=None if target is None else target.name_hint,
    )
    inference = TransitionInferenceReceipt(
        session_id="demo",
        action_observation_sha256=observation.observation_sha256,
        before_snapshot_sha256="b" * 64,
        after_snapshot_sha256="c" * 64,
        status=TransitionInferenceStatus.NO_OBSERVABLE_CHANGE,
        candidates=(),
        inferred_at="2026-09-27T18:30:03+00:00",
    )
    ledger.append_transition_inference_receipt(inference)

    note = OperatorLog(ledger).create(
        note_id=(
            "ghostwalk-transition:"
            + observation.observation_sha256
        ),
        target_sha256=inference.receipt_sha256,
        author_id="operator:local",
        body="Opened network adapter properties.",
        created_at="2026-09-27T18:30:04+00:00",
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
        target_inference_receipt_sha256=inference.receipt_sha256,
        source_operator_note_revision_sha256=note.revision_sha256,
        intent_family=GhostWalkIntentFamily.OPEN,
        intent_code=INTENT_CODE,
        expected_current_revision_sha256=None,
        accepted_at="2026-09-27T18:30:05+00:00",
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
            allow_request_intent_codes=(INTENT_CODE,),
            deny_intent_codes=(),
        ),
    )
    admission_receipt = admission.record(
        target_inference_receipt_sha256=inference.receipt_sha256,
        expected_accepted_intent_revision_sha256=intent.revision_sha256,
        expected_policy_profile_sha256=admission.profile.profile_sha256,
        evaluated_at="2026-09-27T18:30:06+00:00",
    )
    requests = GhostWalkAuthorityRequestService(
        ledger=ledger,
        policy_admission=admission,
        requester_id="operator:local",
    )
    request = requests.create(
        target_inference_receipt_sha256=inference.receipt_sha256,
        expected_admission_receipt_sha256=(
            admission_receipt.admission_receipt_sha256
        ),
        requested_at="2026-09-27T18:30:07+00:00",
    )
    decisions = GhostWalkAuthorizationDecisionService(
        ledger=ledger,
        authority_requests=requests,
        authorizer_id="operator:local",
    )
    decision = decisions.record(
        target_inference_receipt_sha256=inference.receipt_sha256,
        expected_authority_request_sha256=request.authority_request_sha256,
        expected_previous_decision_sha256=None,
        decision=GhostWalkAuthorizationDecisionKind.APPROVE,
        decided_at="2026-09-27T18:30:08+00:00",
    )
    return (
        inference.receipt_sha256,
        decision.authorization_decision_sha256,
        decisions,
        requests,
    )


def test_binding_reuses_exact_demonstration_and_builds_effect_intent(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    target, decision_sha, decisions, _ = _seed(ledger)
    registry = GhostWalkCapabilityMappingRegistry((_mapping(),))
    service = GhostWalkCapabilityBindingService(
        ledger=ledger,
        authorization_decisions=decisions,
        registry=registry,
    )

    readiness = service.readiness(
        target_inference_receipt_sha256=target
    )
    assert readiness.ready is True
    assert readiness.reason is GhostWalkBindingReadinessReason.READY
    assert readiness.authorization_decision_sha256 == decision_sha
    assert readiness.selected_mapping_sha256 is not None
    assert readiness.action_observation_sha256 is not None

    binding = service.create(
        target_inference_receipt_sha256=target,
        expected_authorization_decision_sha256=decision_sha,
        expected_mapping_sha256=readiness.selected_mapping_sha256,
        expected_mapping_set_sha256=readiness.mapping_set_sha256,
        bound_at="2026-09-27T18:30:09+00:00",
    )
    assert binding.capability_id == "desktop.interaction.click"
    assert binding.capability_version == "0.19.0"
    assert binding.permissions_required == ("ui.interact",)
    assert binding.effects_declared == (
        "display.control",
        "filesystem.change",
    )
    assert (
        binding.payload["observation_sha256"]
        == binding.action_observation_sha256
    )
    assert binding.payload["preferred_strategy"] == "SEMANTIC"
    assert binding.payload["guard_required"] is True
    assert binding.payload["absolute_pixel_is_evidence_only"] is True
    assert binding.effect_intent.payload_sha256 == binding.payload_sha256
    assert (
        binding.effect_intent.effect_intent_sha256
        == binding.to_dict()["effect_intent"]["effect_intent_sha256"]
    )
    assert binding.action_authority is False
    assert binding.execution_authority is False
    assert binding.effect_performed is False


def test_no_mapping_holds(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    target, _, decisions, _ = _seed(ledger)
    service = GhostWalkCapabilityBindingService(
        ledger=ledger,
        authorization_decisions=decisions,
        registry=GhostWalkCapabilityMappingRegistry(),
    )

    readiness = service.readiness(
        target_inference_receipt_sha256=target
    )
    assert readiness.ready is False
    assert readiness.reason is GhostWalkBindingReadinessReason.NO_MAPPING


def test_multiple_mappings_for_same_intent_hold_as_ambiguous(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    target, _, decisions, _ = _seed(ledger)
    registry = GhostWalkCapabilityMappingRegistry(
        (
            _mapping(
                mapping_id=(
                    "ghostwalk.open-network-adapter.desktop-click.v1"
                )
            ),
            _mapping(
                mapping_id=(
                    "ghostwalk.open-network-adapter.desktop-click.alt"
                )
            ),
        )
    )
    service = GhostWalkCapabilityBindingService(
        ledger=ledger,
        authorization_decisions=decisions,
        registry=registry,
    )

    readiness = service.readiness(
        target_inference_receipt_sha256=target
    )
    assert readiness.ready is False
    assert (
        readiness.reason
        is GhostWalkBindingReadinessReason.AMBIGUOUS_MAPPING
    )


def test_mapping_strategy_must_match_demonstrated_strategy(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    target, _, decisions, _ = _seed(ledger, semantic=False)
    service = GhostWalkCapabilityBindingService(
        ledger=ledger,
        authorization_decisions=decisions,
        registry=GhostWalkCapabilityMappingRegistry((_mapping(),)),
    )

    readiness = service.readiness(
        target_inference_receipt_sha256=target
    )
    assert readiness.ready is False
    assert (
        readiness.reason
        is GhostWalkBindingReadinessReason.MAPPING_CONSTRAINT_MISMATCH
    )


def test_stale_approval_cannot_be_bound(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    target, _, decisions, _ = _seed(ledger)

    rows = ledger.ghostwalk_observations()
    observation_sha = rows[0]["observation_sha256"]
    assert isinstance(observation_sha, str)
    current = OperatorLog(ledger).current(
        note_id=f"ghostwalk-transition:{observation_sha}"
    )
    OperatorLog(ledger).edit(
        note_id=current.note_id,
        expected_current_revision_sha256=current.revision_sha256,
        author_id="operator:local",
        body="Interpretation changed after approval.",
        created_at="2026-09-27T18:31:00+00:00",
        tags=current.tags,
    )

    service = GhostWalkCapabilityBindingService(
        ledger=ledger,
        authorization_decisions=decisions,
        registry=GhostWalkCapabilityMappingRegistry((_mapping(),)),
    )
    readiness = service.readiness(
        target_inference_receipt_sha256=target
    )
    assert readiness.ready is False
    assert (
        readiness.reason
        is GhostWalkBindingReadinessReason.AUTHORIZATION_STALE
    )


def test_binding_is_single_per_authorization(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    target, decision_sha, decisions, _ = _seed(ledger)
    registry = GhostWalkCapabilityMappingRegistry((_mapping(),))
    service = GhostWalkCapabilityBindingService(
        ledger=ledger,
        authorization_decisions=decisions,
        registry=registry,
    )
    readiness = service.readiness(
        target_inference_receipt_sha256=target
    )
    assert readiness.selected_mapping_sha256 is not None
    first = service.create(
        target_inference_receipt_sha256=target,
        expected_authorization_decision_sha256=decision_sha,
        expected_mapping_sha256=readiness.selected_mapping_sha256,
        expected_mapping_set_sha256=readiness.mapping_set_sha256,
        bound_at="2026-09-27T18:30:09+00:00",
    )
    later = service.readiness(
        target_inference_receipt_sha256=target
    )
    assert later.ready is False
    assert (
        later.reason
        is GhostWalkBindingReadinessReason.BINDING_ALREADY_EXISTS
    )
    assert (
        later.existing_binding_sha256
        == first.executable_binding_sha256
    )


def test_tampered_transition_receipt_fails_closed(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    target, _, decisions, _ = _seed(ledger)
    path = ledger.path.parent / "transition-inference-receipts.jsonl"
    row = json.loads(path.read_text(encoding="utf-8"))
    row["session_id"] = "tampered"
    path.write_text(
        json.dumps(row, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    service = GhostWalkCapabilityBindingService(
        ledger=ledger,
        authorization_decisions=decisions,
        registry=GhostWalkCapabilityMappingRegistry((_mapping(),)),
    )
    with pytest.raises(
        GhostWalkCapabilityBindingError,
        match="transition inference receipt is invalid",
    ):
        service.readiness(
            target_inference_receipt_sha256=target
        )


def test_tampered_persisted_binding_fails_closed(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    target, decision_sha, decisions, _ = _seed(ledger)
    registry = GhostWalkCapabilityMappingRegistry((_mapping(),))
    service = GhostWalkCapabilityBindingService(
        ledger=ledger,
        authorization_decisions=decisions,
        registry=registry,
    )
    readiness = service.readiness(
        target_inference_receipt_sha256=target
    )
    assert readiness.selected_mapping_sha256 is not None
    service.create(
        target_inference_receipt_sha256=target,
        expected_authorization_decision_sha256=decision_sha,
        expected_mapping_sha256=readiness.selected_mapping_sha256,
        expected_mapping_set_sha256=readiness.mapping_set_sha256,
        bound_at="2026-09-27T18:30:09+00:00",
    )

    path = ledger.path.parent / "ghostwalk-executable-bindings.jsonl"
    row = json.loads(path.read_text(encoding="utf-8"))
    row["capability_version"] = "999.0.0"
    path.write_text(
        json.dumps(row, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        GhostWalkCapabilityBindingError,
        match="persisted executable binding is invalid",
    ):
        service.latest(
            target_inference_receipt_sha256=target
        )
