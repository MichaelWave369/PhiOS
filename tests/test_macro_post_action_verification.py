from __future__ import annotations

import json
from pathlib import Path

from phios.macro_ghostwalk import SemanticTarget
from phios.macro_interaction_guard import WindowFrame
from phios.macro_post_action_verification import (
    PostActionExpectation,
    PostActionExpectationKind,
    PostActionObservationStatus,
    PostActionVerificationDecision,
    PostActionVerificationReason,
    PostActionVerifier,
)
from phios.macro_uia_revalidation import SemanticReplayRevalidator
from phios.macro_windows_uia import UiaElementSnapshot
from phios.spine.ledger import RealityLedger

SOURCE_TITLE = "a" * 64
NEW_TITLE = "b" * 64


def _ledger(tmp_path: Path) -> RealityLedger:
    return RealityLedger(tmp_path / "ledger" / "receipts.jsonl")


def _frame(
    *,
    title: str = SOURCE_TITLE,
    pid: int = 4242,
    observed_at: str = "2026-09-27T03:10:00+00:00",
) -> WindowFrame:
    return WindowFrame(
        process_id=f"pid:{pid}",
        window_title_sha256=title,
        left_px=100,
        top_px=50,
        width_px=800,
        height_px=600,
        display_scale_percent=100,
        foreground=True,
        captured_at=observed_at,
    )


def _target() -> SemanticTarget:
    return SemanticTarget(
        provider="windows.uia.v0.16",
        selector=json.dumps(
            {
                "automation_id": "saved-banner",
                "control_type": 50000,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        role="uia.control_type.50000",
        name_hint="Saved",
    )


def _candidate() -> UiaElementSnapshot:
    return UiaElementSnapshot(
        process_id=4242,
        automation_id="saved-banner",
        name_hint="Saved",
        control_type=50000,
        class_name="Text",
        framework_id="Win32",
        enabled=True,
        offscreen=False,
        is_password=False,
        bounding_left=400,
        bounding_top=200,
        bounding_right=600,
        bounding_bottom=250,
    )


class SequenceFrameProvider:
    provider_id = "test.post-action-frame"

    def __init__(
        self,
        *frames: WindowFrame | None,
    ) -> None:
        self._frames = list(frames)
        self.calls = 0

    def current_frame(
        self,
        *,
        observed_at: str,
    ) -> WindowFrame | None:
        self.calls += 1
        if len(self._frames) == 1:
            return self._frames[0]
        return self._frames.pop(0)


class SequenceReplayBackend:
    backend_id = "test.post-action-uia"

    def __init__(
        self,
        *results: tuple[UiaElementSnapshot, ...],
    ) -> None:
        self._results = list(results)
        self.calls = 0

    def find_matches(
        self,
        *,
        frame: WindowFrame,
        selector,
    ) -> tuple[UiaElementSnapshot, ...]:
        self.calls += 1
        if len(self._results) == 1:
            return self._results[0]
        return self._results.pop(0)


class SequenceClock:
    def __init__(self) -> None:
        self._counter = 0

    def __call__(self) -> str:
        self._counter += 1
        return f"2026-09-27T03:10:{self._counter:02d}+00:00"


def _verifier(
    tmp_path: Path,
    *,
    frames: tuple[WindowFrame | None, ...],
    semantic_results: tuple[
        tuple[UiaElementSnapshot, ...], ...
    ] = ((),),
):
    ledger = _ledger(tmp_path)
    backend = SequenceReplayBackend(*semantic_results)
    semantic = SemanticReplayRevalidator(
        ledger=ledger,
        backend=backend,
    )
    pauses: list[float] = []
    verifier = PostActionVerifier(
        ledger=ledger,
        frame_provider=SequenceFrameProvider(*frames),
        semantic_revalidator=semantic,
        clock=SequenceClock(),
        pause=pauses.append,
    )
    return ledger, verifier, backend, pauses


def _expectation(
    kind: PostActionExpectationKind,
    *,
    expected_title: str | None = None,
    target: SemanticTarget | None = None,
    max_observations: int = 3,
) -> PostActionExpectation:
    return PostActionExpectation(
        kind=kind,
        expected_process_id="pid:4242",
        source_window_title_sha256=SOURCE_TITLE,
        expected_window_title_sha256=expected_title,
        semantic_target=target,
        max_observations=max_observations,
        interval_ms=25,
    )


def test_post_001_window_title_change_verifies_after_retry(
    tmp_path: Path,
) -> None:
    ledger, verifier, _, pauses = _verifier(
        tmp_path,
        frames=(
            _frame(title=SOURCE_TITLE),
            _frame(title=NEW_TITLE),
        ),
    )
    expectation = _expectation(
        PostActionExpectationKind.WINDOW_TITLE_CHANGED,
        max_observations=2,
    )

    receipt = verifier.verify(
        desktop_interaction_receipt_sha256="1" * 64,
        operation_payload_sha256="2" * 64,
        expectation=expectation,
    )

    assert receipt.decision is PostActionVerificationDecision.VERIFIED
    assert receipt.reason is PostActionVerificationReason.EXPECTATION_MATCHED
    assert len(receipt.observations) == 2
    assert receipt.observations[0].status is PostActionObservationStatus.NO_MATCH
    assert receipt.observations[1].status is PostActionObservationStatus.MATCH
    assert pauses == [0.025]
    assert receipt.causation_proven is False
    rows = ledger.recent_post_action_verification_receipts(1)
    assert rows[0]["receipt_sha256"] == receipt.receipt_sha256


def test_post_002_window_title_equals_not_verified(
    tmp_path: Path,
) -> None:
    _, verifier, _, _ = _verifier(
        tmp_path,
        frames=(
            _frame(title=SOURCE_TITLE),
            _frame(title=SOURCE_TITLE),
        ),
    )
    expectation = _expectation(
        PostActionExpectationKind.WINDOW_TITLE_EQUALS,
        expected_title=NEW_TITLE,
        max_observations=2,
    )

    receipt = verifier.verify(
        desktop_interaction_receipt_sha256="3" * 64,
        operation_payload_sha256="4" * 64,
        expectation=expectation,
    )

    assert receipt.decision is PostActionVerificationDecision.NOT_VERIFIED
    assert (
        receipt.reason
        is PostActionVerificationReason.EXPECTATION_NOT_OBSERVED
    )
    assert all(
        item.status is PostActionObservationStatus.NO_MATCH
        for item in receipt.observations
    )


def test_post_003_semantic_present_verifies(
    tmp_path: Path,
) -> None:
    ledger, verifier, backend, _ = _verifier(
        tmp_path,
        frames=(_frame(title=SOURCE_TITLE),),
        semantic_results=((_candidate(),),),
    )
    expectation = _expectation(
        PostActionExpectationKind.SEMANTIC_PRESENT,
        expected_title=SOURCE_TITLE,
        target=_target(),
        max_observations=1,
    )

    receipt = verifier.verify(
        desktop_interaction_receipt_sha256="5" * 64,
        operation_payload_sha256="6" * 64,
        expectation=expectation,
    )

    assert receipt.decision is PostActionVerificationDecision.VERIFIED
    assert backend.calls == 1
    observation = receipt.observations[0]
    assert observation.reason is PostActionVerificationReason.SEMANTIC_PRESENT
    assert observation.semantic_revalidation_receipt_sha256 is not None
    assert (
        ledger.recent_semantic_revalidation_receipts(1)[0]["decision"]
        == "CLEAR"
    )


def test_post_004_semantic_absent_verifies_only_on_target_missing(
    tmp_path: Path,
) -> None:
    _, verifier, backend, _ = _verifier(
        tmp_path,
        frames=(_frame(title=SOURCE_TITLE),),
        semantic_results=((),),
    )
    expectation = _expectation(
        PostActionExpectationKind.SEMANTIC_ABSENT,
        expected_title=SOURCE_TITLE,
        target=_target(),
        max_observations=1,
    )

    receipt = verifier.verify(
        desktop_interaction_receipt_sha256="7" * 64,
        operation_payload_sha256="8" * 64,
        expectation=expectation,
    )

    assert receipt.decision is PostActionVerificationDecision.VERIFIED
    assert backend.calls == 1
    assert (
        receipt.observations[0].reason
        is PostActionVerificationReason.SEMANTIC_MISSING
    )


def test_post_005_semantic_ambiguity_is_indeterminate(
    tmp_path: Path,
) -> None:
    candidate = _candidate()
    _, verifier, _, _ = _verifier(
        tmp_path,
        frames=(_frame(title=SOURCE_TITLE),),
        semantic_results=((candidate, candidate),),
    )
    expectation = _expectation(
        PostActionExpectationKind.SEMANTIC_PRESENT,
        expected_title=SOURCE_TITLE,
        target=_target(),
        max_observations=1,
    )

    receipt = verifier.verify(
        desktop_interaction_receipt_sha256="9" * 64,
        operation_payload_sha256="a" * 64,
        expectation=expectation,
    )

    assert receipt.decision is PostActionVerificationDecision.INDETERMINATE
    assert (
        receipt.reason
        is PostActionVerificationReason.OBSERVATION_INDETERMINATE
    )
    assert (
        receipt.observations[0].reason
        is PostActionVerificationReason.SEMANTIC_AMBIGUOUS
    )


def test_post_006_wrong_foreground_process_is_indeterminate(
    tmp_path: Path,
) -> None:
    _, verifier, backend, _ = _verifier(
        tmp_path,
        frames=(_frame(pid=9999),),
    )
    expectation = _expectation(
        PostActionExpectationKind.SEMANTIC_PRESENT,
        expected_title=SOURCE_TITLE,
        target=_target(),
        max_observations=1,
    )

    receipt = verifier.verify(
        desktop_interaction_receipt_sha256="b" * 64,
        operation_payload_sha256="c" * 64,
        expectation=expectation,
    )

    assert receipt.decision is PostActionVerificationDecision.INDETERMINATE
    assert (
        receipt.observations[0].reason
        is PostActionVerificationReason.PROCESS_MISMATCH
    )
    assert backend.calls == 0


def test_post_007_expectation_round_trip_is_hash_bound() -> None:
    expectation = _expectation(
        PostActionExpectationKind.SEMANTIC_PRESENT,
        expected_title=SOURCE_TITLE,
        target=_target(),
    )

    restored = PostActionExpectation.from_dict(
        expectation.to_dict()
    )

    assert restored == expectation
    assert restored.expectation_sha256 == expectation.expectation_sha256
