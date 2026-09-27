from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from phios.macro_ghostwalk import SemanticTarget
from phios.macro_interaction_guard import WindowFrame
from phios.macro_transition_inference import (
    GhostWalkTransitionInferer,
    SnapshotPhase,
    TransitionInferenceStatus,
)
from phios.macro_uia_state_observer import (
    ComtypesWindowsUiaInventoryBackend,
    GhostWalkUiaStateObserver,
    MAX_UIA_INVENTORY_ELEMENTS,
    MAX_UIA_STATE_TARGETS,
    UiaInventoryLimitExceeded,
    UiaInventoryScan,
    UiaStateObservationReason,
    UiaStateObservationStatus,
    UiaStateObserverContractError,
)
from phios.macro_windows_uia import UiaElementSnapshot
from phios.spine.ledger import RealityLedger

ACTION = "a" * 64
TITLE_BEFORE = "b" * 64
TITLE_AFTER = "c" * 64


def _ledger(tmp_path: Path) -> RealityLedger:
    return RealityLedger(tmp_path / "ledger" / "receipts.jsonl")


def _frame(
    *,
    title: str = TITLE_BEFORE,
    foreground: bool = True,
    captured_at: str = "2026-09-27T04:00:00+00:00",
) -> WindowFrame:
    return WindowFrame(
        process_id="pid:4242",
        window_title_sha256=title,
        left_px=100,
        top_px=50,
        width_px=800,
        height_px=600,
        display_scale_percent=100,
        foreground=foreground,
        captured_at=captured_at,
    )


def _element(
    automation_id: str | None,
    *,
    name: str | None,
    control_type: int | None = 50000,
    pid: int = 4242,
    offscreen: bool | None = False,
    password: bool | None = False,
    left: int | None = 200,
    top: int | None = 150,
    right: int | None = 300,
    bottom: int | None = 200,
) -> UiaElementSnapshot:
    return UiaElementSnapshot(
        process_id=pid,
        automation_id=automation_id,
        name_hint=name,
        control_type=control_type,
        class_name="Control",
        framework_id="Win32",
        enabled=True,
        offscreen=offscreen,
        is_password=password,
        bounding_left=left,
        bounding_top=top,
        bounding_right=right,
        bounding_bottom=bottom,
    )


class StaticInventoryBackend:
    backend_id = "test.uia-inventory"

    def __init__(
        self,
        scan: UiaInventoryScan | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.scan = scan or UiaInventoryScan(
            scanned_element_count=0,
            snapshots=(),
        )
        self.error = error
        self.calls = 0

    def inventory(
        self,
        *,
        frame: WindowFrame,
    ) -> UiaInventoryScan:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.scan


class SequenceInventoryBackend:
    backend_id = "test.sequence-uia-inventory"

    def __init__(self, *scans: UiaInventoryScan) -> None:
        self.scans = list(scans)
        self.calls = 0

    def inventory(
        self,
        *,
        frame: WindowFrame,
    ) -> UiaInventoryScan:
        self.calls += 1
        if len(self.scans) == 1:
            return self.scans[0]
        return self.scans.pop(0)


def _capture(
    tmp_path: Path,
    *,
    scan: UiaInventoryScan,
    phase: SnapshotPhase = SnapshotPhase.BEFORE,
    frame: WindowFrame | None = None,
):
    ledger = _ledger(tmp_path)
    observer = GhostWalkUiaStateObserver(
        ledger=ledger,
        backend=StaticInventoryBackend(scan),
    )
    return ledger, observer.capture(
        session_id="ghost:uia-state",
        action_observation_sha256=ACTION,
        phase=phase,
        frame=frame or _frame(),
        observed_at=(
            "2026-09-27T04:00:00+00:00"
            if phase is SnapshotPhase.BEFORE
            else "2026-09-27T04:00:01+00:00"
        ),
    )


def test_state_001_complete_inventory_builds_stable_snapshot(
    tmp_path: Path,
) -> None:
    scan = UiaInventoryScan(
        scanned_element_count=3,
        snapshots=(
            _element("save", name="Save"),
            _element("cancel", name="Cancel"),
            _element(None, name="Decorative"),
        ),
    )

    ledger, outcome = _capture(tmp_path, scan=scan)

    assert outcome.receipt.status is UiaStateObservationStatus.CAPTURED
    assert (
        outcome.receipt.reason
        is UiaStateObservationReason.COMPLETE_INVENTORY
    )
    assert outcome.snapshot is not None
    assert outcome.receipt.scanned_element_count == 3
    assert outcome.receipt.scoped_element_count == 3
    assert outcome.receipt.semantic_candidate_count == 2
    assert outcome.receipt.unique_target_count == 2
    assert outcome.receipt.complete_inventory is True
    assert len(outcome.snapshot.semantic_targets) == 2
    rows = ledger.recent_uia_state_observation_receipts(1)
    assert rows[0]["receipt_sha256"] == outcome.receipt.receipt_sha256
    assert len(ledger.uia_element_snapshots()) == 3


def test_state_002_duplicate_selector_identity_is_excluded_even_if_names_differ(
    tmp_path: Path,
) -> None:
    scan = UiaInventoryScan(
        scanned_element_count=3,
        snapshots=(
            _element("duplicate", name="First"),
            _element("duplicate", name="Second"),
            _element("unique", name="Unique"),
        ),
    )

    _, outcome = _capture(tmp_path, scan=scan)

    assert outcome.snapshot is not None
    assert outcome.receipt.semantic_candidate_count == 3
    assert outcome.receipt.ambiguous_identity_count == 2
    assert outcome.receipt.unique_target_count == 1
    target = outcome.snapshot.semantic_targets[0]
    selector = json.loads(target.selector)
    assert selector["automation_id"] == "unique"


def test_state_003_password_name_is_redacted_from_semantic_target(
    tmp_path: Path,
) -> None:
    scan = UiaInventoryScan(
        scanned_element_count=1,
        snapshots=(
            _element(
                "password-box",
                name="Password",
                control_type=50004,
                password=True,
            ),
        ),
    )

    _, outcome = _capture(tmp_path, scan=scan)

    assert outcome.snapshot is not None
    assert outcome.receipt.excluded_password_name_count == 1
    assert outcome.snapshot.semantic_targets[0].name_hint is None


def test_state_004_out_of_scope_and_offscreen_controls_are_filtered(
    tmp_path: Path,
) -> None:
    scan = UiaInventoryScan(
        scanned_element_count=4,
        snapshots=(
            _element("inside", name="Inside"),
            _element(
                "other-process",
                name="Other",
                pid=9999,
            ),
            _element(
                "offscreen",
                name="Offscreen",
                offscreen=True,
            ),
            _element(
                "outside-window",
                name="Outside",
                left=950,
                top=150,
                right=1050,
                bottom=200,
            ),
        ),
    )

    ledger, outcome = _capture(tmp_path, scan=scan)

    assert outcome.snapshot is not None
    assert outcome.receipt.scoped_element_count == 1
    assert outcome.receipt.unique_target_count == 1
    assert len(ledger.uia_element_snapshots()) == 1


def test_state_005_non_foreground_frame_holds_without_backend(
    tmp_path: Path,
) -> None:
    backend = StaticInventoryBackend()
    ledger = _ledger(tmp_path)
    observer = GhostWalkUiaStateObserver(
        ledger=ledger,
        backend=backend,
    )

    outcome = observer.capture(
        session_id="ghost:uia-state",
        action_observation_sha256=ACTION,
        phase=SnapshotPhase.BEFORE,
        frame=_frame(foreground=False),
        observed_at="2026-09-27T04:00:00+00:00",
    )

    assert outcome.snapshot is None
    assert outcome.receipt.status is UiaStateObservationStatus.HELD
    assert (
        outcome.receipt.reason
        is UiaStateObservationReason.FRAME_NOT_FOREGROUND
    )
    assert backend.calls == 0


def test_state_006_inventory_overflow_holds_without_partial_snapshot(
    tmp_path: Path,
) -> None:
    backend = StaticInventoryBackend(
        error=UiaInventoryLimitExceeded("too many controls")
    )
    ledger = _ledger(tmp_path)
    observer = GhostWalkUiaStateObserver(
        ledger=ledger,
        backend=backend,
    )

    outcome = observer.capture(
        session_id="ghost:uia-state",
        action_observation_sha256=ACTION,
        phase=SnapshotPhase.BEFORE,
        frame=_frame(),
        observed_at="2026-09-27T04:00:00+00:00",
    )

    assert outcome.snapshot is None
    assert outcome.receipt.complete_inventory is False
    assert outcome.receipt.target_sha256s == ()
    assert (
        outcome.receipt.reason
        is UiaStateObservationReason.INVENTORY_LIMIT_EXCEEDED
    )


def test_state_007_backend_error_holds_without_partial_snapshot(
    tmp_path: Path,
) -> None:
    backend = StaticInventoryBackend(
        error=RuntimeError("COM unavailable")
    )
    ledger = _ledger(tmp_path)
    observer = GhostWalkUiaStateObserver(
        ledger=ledger,
        backend=backend,
    )

    outcome = observer.capture(
        session_id="ghost:uia-state",
        action_observation_sha256=ACTION,
        phase=SnapshotPhase.BEFORE,
        frame=_frame(),
        observed_at="2026-09-27T04:00:00+00:00",
    )

    assert outcome.snapshot is None
    assert outcome.receipt.reason is UiaStateObservationReason.BACKEND_ERROR
    assert outcome.receipt.complete_inventory is False


def test_state_008_target_limit_holds_instead_of_truncating(
    tmp_path: Path,
) -> None:
    snapshots = tuple(
        _element(
            f"control-{index}",
            name=f"Control {index}",
            left=110 + (index % 20),
            top=60 + (index % 20),
            right=400 + (index % 20),
            bottom=200 + (index % 20),
        )
        for index in range(MAX_UIA_STATE_TARGETS + 1)
    )
    scan = UiaInventoryScan(
        scanned_element_count=len(snapshots),
        snapshots=snapshots,
    )

    _, outcome = _capture(tmp_path, scan=scan)

    assert outcome.snapshot is None
    assert (
        outcome.receipt.reason
        is UiaStateObservationReason.TARGET_LIMIT_EXCEEDED
    )
    assert outcome.receipt.complete_inventory is False
    assert outcome.receipt.semantic_candidate_count == (
        MAX_UIA_STATE_TARGETS + 1
    )


def test_state_009_name_hint_change_does_not_create_transition_noise(
    tmp_path: Path,
) -> None:
    before_scan = UiaInventoryScan(
        scanned_element_count=1,
        snapshots=(_element("save", name="Save"),),
    )
    after_scan = UiaInventoryScan(
        scanned_element_count=1,
        snapshots=(_element("save", name="Saved"),),
    )
    ledger = _ledger(tmp_path)
    backend = SequenceInventoryBackend(before_scan, after_scan)
    observer = GhostWalkUiaStateObserver(
        ledger=ledger,
        backend=backend,
    )

    before = observer.capture(
        session_id="ghost:uia-state",
        action_observation_sha256=ACTION,
        phase=SnapshotPhase.BEFORE,
        frame=_frame(
            title=TITLE_BEFORE,
            captured_at="2026-09-27T04:00:00+00:00",
        ),
        observed_at="2026-09-27T04:00:00+00:00",
    )
    after = observer.capture(
        session_id="ghost:uia-state",
        action_observation_sha256=ACTION,
        phase=SnapshotPhase.AFTER,
        frame=_frame(
            title=TITLE_BEFORE,
            captured_at="2026-09-27T04:00:01+00:00",
        ),
        observed_at="2026-09-27T04:00:01+00:00",
    )

    assert before.snapshot is not None
    assert after.snapshot is not None
    inference = GhostWalkTransitionInferer(ledger).infer(
        before=before.snapshot,
        after=after.snapshot,
        inferred_at="2026-09-27T04:00:02+00:00",
    )
    assert (
        inference.status
        is TransitionInferenceStatus.NO_OBSERVABLE_CHANGE
    )
    assert inference.candidates == ()


def test_state_010_real_observer_output_feeds_transition_inference(
    tmp_path: Path,
) -> None:
    stable = _element("save", name="Save")
    appeared = _element("saved-banner", name="Saved")
    before_scan = UiaInventoryScan(
        scanned_element_count=1,
        snapshots=(stable,),
    )
    after_scan = UiaInventoryScan(
        scanned_element_count=2,
        snapshots=(stable, appeared),
    )
    ledger = _ledger(tmp_path)
    observer = GhostWalkUiaStateObserver(
        ledger=ledger,
        backend=SequenceInventoryBackend(
            before_scan,
            after_scan,
        ),
    )

    before = observer.capture(
        session_id="ghost:uia-state",
        action_observation_sha256=ACTION,
        phase=SnapshotPhase.BEFORE,
        frame=_frame(
            title=TITLE_BEFORE,
            captured_at="2026-09-27T04:00:00+00:00",
        ),
        observed_at="2026-09-27T04:00:00+00:00",
    )
    after = observer.capture(
        session_id="ghost:uia-state",
        action_observation_sha256=ACTION,
        phase=SnapshotPhase.AFTER,
        frame=_frame(
            title=TITLE_AFTER,
            captured_at="2026-09-27T04:00:01+00:00",
        ),
        observed_at="2026-09-27T04:00:01+00:00",
    )

    assert before.snapshot is not None
    assert after.snapshot is not None
    inference = GhostWalkTransitionInferer(ledger).infer(
        before=before.snapshot,
        after=after.snapshot,
        inferred_at="2026-09-27T04:00:02+00:00",
    )

    assert inference.status is TransitionInferenceStatus.CANDIDATES
    assert len(inference.candidates) == 2
    kinds = {
        candidate.expectation.kind.value
        for candidate in inference.candidates
    }
    assert kinds == {
        "WINDOW_TITLE_CHANGED",
        "SEMANTIC_PRESENT",
    }


def test_state_011_inventory_scan_rejects_impossible_count() -> None:
    with pytest.raises(
        UiaStateObserverContractError,
        match="exceeds safety bound",
    ):
        UiaInventoryScan(
            scanned_element_count=MAX_UIA_INVENTORY_ELEMENTS + 1,
            snapshots=(),
        )


def test_state_012_real_backend_rejects_non_windows() -> None:
    if os.name == "nt":
        pytest.skip("non-Windows contract test")
    with pytest.raises(
        UiaStateObserverContractError,
        match="requires Windows",
    ):
        ComtypesWindowsUiaInventoryBackend()
