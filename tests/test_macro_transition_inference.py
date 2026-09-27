from __future__ import annotations

import json
from pathlib import Path

import pytest

from phios.macro_ghostwalk import SemanticTarget
from phios.macro_operator_log import OperatorLog, OperatorNoteStatus
from phios.macro_post_action_verification import PostActionExpectationKind
from phios.macro_transition_inference import (
    GhostWalkTransitionInferer,
    GhostWalkUiStateSnapshot,
    SnapshotPhase,
    TransitionBasis,
    TransitionInferenceContractError,
    TransitionInferenceStatus,
)
from phios.spine.ledger import RealityLedger

ACTION = "a" * 64
BEFORE_FRAME = "b" * 64
AFTER_FRAME = "c" * 64
TITLE_BEFORE = "d" * 64
TITLE_AFTER = "e" * 64


def _ledger(tmp_path: Path) -> RealityLedger:
    return RealityLedger(tmp_path / "ledger" / "receipts.jsonl")


def _target(
    automation_id: str,
    *,
    name: str,
    control_type: int = 50000,
) -> SemanticTarget:
    return SemanticTarget(
        provider="windows.uia.v0.16",
        selector=json.dumps(
            {
                "automation_id": automation_id,
                "control_type": control_type,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        role=f"uia.control_type.{control_type}",
        name_hint=name,
    )


def _snapshot(
    *,
    phase: SnapshotPhase,
    title: str,
    frame: str,
    targets: tuple[SemanticTarget, ...],
    observed_at: str,
    pid: str = "pid:4242",
    session_id: str = "ghost:transition",
    action_sha: str = ACTION,
) -> GhostWalkUiStateSnapshot:
    ordered = tuple(sorted(targets, key=lambda item: item.target_sha256))
    return GhostWalkUiStateSnapshot(
        session_id=session_id,
        action_observation_sha256=action_sha,
        phase=phase,
        process_id=pid,
        window_title_sha256=title,
        frame_sha256=frame,
        semantic_targets=ordered,
        observed_at=observed_at,
    )


def test_transition_001_detects_title_appeared_and_disappeared(
    tmp_path: Path,
) -> None:
    stable = _target("stable", name="Stable")
    disappeared = _target("old-banner", name="Old")
    appeared = _target("saved-banner", name="Saved")

    before = _snapshot(
        phase=SnapshotPhase.BEFORE,
        title=TITLE_BEFORE,
        frame=BEFORE_FRAME,
        targets=(stable, disappeared),
        observed_at="2026-09-27T03:40:00+00:00",
    )
    after = _snapshot(
        phase=SnapshotPhase.AFTER,
        title=TITLE_AFTER,
        frame=AFTER_FRAME,
        targets=(stable, appeared),
        observed_at="2026-09-27T03:40:01+00:00",
    )

    ledger = _ledger(tmp_path)
    receipt = GhostWalkTransitionInferer(ledger).infer(
        before=before,
        after=after,
        inferred_at="2026-09-27T03:40:02+00:00",
    )

    assert receipt.status is TransitionInferenceStatus.CANDIDATES
    assert len(receipt.candidates) == 3
    assert tuple(
        candidate.candidate_id for candidate in receipt.candidates
    ) == tuple(
        sorted(candidate.candidate_id for candidate in receipt.candidates)
    )

    by_basis = {
        candidate.basis: candidate
        for candidate in receipt.candidates
    }
    assert (
        by_basis[TransitionBasis.WINDOW_TITLE_CHANGED]
        .expectation.kind
        is PostActionExpectationKind.WINDOW_TITLE_CHANGED
    )
    assert (
        by_basis[TransitionBasis.SEMANTIC_APPEARED]
        .expectation.kind
        is PostActionExpectationKind.SEMANTIC_PRESENT
    )
    assert (
        by_basis[TransitionBasis.SEMANTIC_DISAPPEARED]
        .expectation.kind
        is PostActionExpectationKind.SEMANTIC_ABSENT
    )
    assert stable.target_sha256 not in {
        candidate.expectation.semantic_target.target_sha256
        for candidate in receipt.candidates
        if candidate.expectation.semantic_target is not None
    }

    assert receipt.human_intent_confirmed is False
    assert receipt.causation_proven is False
    assert all(
        candidate.human_intent_confirmed is False
        and candidate.causation_proven is False
        and candidate.operational_authority is False
        and candidate.action_authority is False
        and candidate.execution_authority is False
        for candidate in receipt.candidates
    )

    snapshots = ledger.ghostwalk_state_snapshots(
        action_observation_sha256=ACTION
    )
    assert [row["phase"] for row in snapshots] == ["BEFORE", "AFTER"]
    rows = ledger.recent_transition_inference_receipts(1)
    assert rows[0]["receipt_sha256"] == receipt.receipt_sha256


def test_transition_002_no_observable_change_is_not_candidate_noise(
    tmp_path: Path,
) -> None:
    stable = _target("stable", name="Stable")
    before = _snapshot(
        phase=SnapshotPhase.BEFORE,
        title=TITLE_BEFORE,
        frame=BEFORE_FRAME,
        targets=(stable,),
        observed_at="2026-09-27T03:40:00+00:00",
    )
    after = _snapshot(
        phase=SnapshotPhase.AFTER,
        title=TITLE_BEFORE,
        frame=AFTER_FRAME,
        targets=(stable,),
        observed_at="2026-09-27T03:40:01+00:00",
    )

    receipt = GhostWalkTransitionInferer(_ledger(tmp_path)).infer(
        before=before,
        after=after,
        inferred_at="2026-09-27T03:40:02+00:00",
    )

    assert (
        receipt.status
        is TransitionInferenceStatus.NO_OBSERVABLE_CHANGE
    )
    assert receipt.candidates == ()


def test_transition_003_process_change_is_scope_change(
    tmp_path: Path,
) -> None:
    before = _snapshot(
        phase=SnapshotPhase.BEFORE,
        title=TITLE_BEFORE,
        frame=BEFORE_FRAME,
        targets=(),
        observed_at="2026-09-27T03:40:00+00:00",
        pid="pid:4242",
    )
    after = _snapshot(
        phase=SnapshotPhase.AFTER,
        title=TITLE_AFTER,
        frame=AFTER_FRAME,
        targets=(),
        observed_at="2026-09-27T03:40:01+00:00",
        pid="pid:9999",
    )

    receipt = GhostWalkTransitionInferer(_ledger(tmp_path)).infer(
        before=before,
        after=after,
        inferred_at="2026-09-27T03:40:02+00:00",
    )

    assert receipt.status is TransitionInferenceStatus.SCOPE_CHANGED
    assert receipt.candidates == ()


def test_transition_004_pair_must_bind_same_demonstrated_action(
    tmp_path: Path,
) -> None:
    before = _snapshot(
        phase=SnapshotPhase.BEFORE,
        title=TITLE_BEFORE,
        frame=BEFORE_FRAME,
        targets=(),
        observed_at="2026-09-27T03:40:00+00:00",
    )
    after = _snapshot(
        phase=SnapshotPhase.AFTER,
        title=TITLE_AFTER,
        frame=AFTER_FRAME,
        targets=(),
        observed_at="2026-09-27T03:40:01+00:00",
        action_sha="f" * 64,
    )

    with pytest.raises(
        TransitionInferenceContractError,
        match="different demonstrated actions",
    ):
        GhostWalkTransitionInferer(_ledger(tmp_path)).infer(
            before=before,
            after=after,
            inferred_at="2026-09-27T03:40:02+00:00",
        )


def test_transition_005_after_must_be_temporally_after_before(
    tmp_path: Path,
) -> None:
    before = _snapshot(
        phase=SnapshotPhase.BEFORE,
        title=TITLE_BEFORE,
        frame=BEFORE_FRAME,
        targets=(),
        observed_at="2026-09-27T03:40:01+00:00",
    )
    after = _snapshot(
        phase=SnapshotPhase.AFTER,
        title=TITLE_AFTER,
        frame=AFTER_FRAME,
        targets=(),
        observed_at="2026-09-27T03:40:00+00:00",
    )

    with pytest.raises(
        TransitionInferenceContractError,
        match="after snapshot must occur after",
    ):
        GhostWalkTransitionInferer(_ledger(tmp_path)).infer(
            before=before,
            after=after,
            inferred_at="2026-09-27T03:40:02+00:00",
        )


def test_transition_006_editable_operator_note_does_not_mutate_evidence(
    tmp_path: Path,
) -> None:
    appeared = _target("saved-banner", name="Saved")
    before = _snapshot(
        phase=SnapshotPhase.BEFORE,
        title=TITLE_BEFORE,
        frame=BEFORE_FRAME,
        targets=(),
        observed_at="2026-09-27T03:40:00+00:00",
    )
    after = _snapshot(
        phase=SnapshotPhase.AFTER,
        title=TITLE_BEFORE,
        frame=AFTER_FRAME,
        targets=(appeared,),
        observed_at="2026-09-27T03:40:01+00:00",
    )
    ledger = _ledger(tmp_path)
    inferer = GhostWalkTransitionInferer(ledger)
    receipt = inferer.infer(
        before=before,
        after=after,
        inferred_at="2026-09-27T03:40:02+00:00",
    )
    original_receipt_sha = receipt.receipt_sha256

    note = inferer.publish_editable_operator_log(
        receipt=receipt,
        note_id="note:transition:1",
        author_id="operator:mikey",
        created_at="2026-09-27T03:40:03+00:00",
    )
    assert note.target_sha256 == original_receipt_sha
    assert "SEMANTIC_PRESENT" in note.body
    assert "human_intent_confirmed: false" in note.body

    edited = OperatorLog(ledger).edit(
        note_id=note.note_id,
        expected_current_revision_sha256=note.revision_sha256,
        author_id="operator:mikey",
        body="I only care about the Saved indicator candidate.",
        tags=("ghostwalk", "reviewed"),
        status=OperatorNoteStatus.ACTIVE,
        created_at="2026-09-27T03:40:04+00:00",
    )
    assert edited.revision == 2
    assert edited.target_sha256 == original_receipt_sha
    persisted = ledger.recent_transition_inference_receipts(1)[0]
    assert persisted["receipt_sha256"] == original_receipt_sha
    assert persisted["human_intent_confirmed"] is False


def test_transition_007_snapshot_rejects_duplicate_semantic_targets() -> None:
    target = _target("duplicate", name="Duplicate")

    with pytest.raises(
        TransitionInferenceContractError,
        match="must be unique",
    ):
        GhostWalkUiStateSnapshot(
            session_id="ghost:transition",
            action_observation_sha256=ACTION,
            phase=SnapshotPhase.BEFORE,
            process_id="pid:4242",
            window_title_sha256=TITLE_BEFORE,
            frame_sha256=BEFORE_FRAME,
            semantic_targets=(target, target),
            observed_at="2026-09-27T03:40:00+00:00",
        )
