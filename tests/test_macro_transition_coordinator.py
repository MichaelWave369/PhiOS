from __future__ import annotations

from pathlib import Path

import pytest

from phios.macro_ghostwalk import GhostWalkRecorder
from phios.macro_ghostwalk_capture import GhostWalkCaptureAdapter
from phios.macro_ghostwalk_listener import (
    GhostWalkListenerBridge,
    LLMHF_INJECTED,
    RawMouseHookEvent,
)
from phios.macro_interaction_guard import WindowFrame
from phios.macro_transition_coordinator import (
    GhostWalkTransitionCoordinator,
    TransitionCoordinatorReason,
    TransitionCoordinatorStatus,
)
from phios.macro_transition_inference import (
    GhostWalkTransitionInferer,
    TransitionInferenceStatus,
)
from phios.macro_uia_state_observer import (
    GhostWalkUiaStateObserver,
    UiaInventoryScan,
)
from phios.macro_windows_uia import UiaElementSnapshot
from phios.spine.ledger import RealityLedger

TITLE_BEFORE = "a" * 64
TITLE_AFTER = "b" * 64


def _ledger(tmp_path: Path) -> RealityLedger:
    return RealityLedger(tmp_path / "ledger" / "receipts.jsonl")


def _frame(
    *,
    title: str = TITLE_BEFORE,
    left: int = 100,
    top: int = 50,
    width: int = 800,
    height: int = 600,
    captured_at: str = "2026-09-27T04:30:00+00:00",
) -> WindowFrame:
    return WindowFrame(
        process_id="pid:4242",
        window_title_sha256=title,
        left_px=left,
        top_px=top,
        width_px=width,
        height_px=height,
        display_scale_percent=100,
        foreground=True,
        captured_at=captured_at,
    )


def _element(
    automation_id: str,
    *,
    name: str,
    left: int = 200,
    top: int = 150,
    right: int = 300,
    bottom: int = 200,
) -> UiaElementSnapshot:
    return UiaElementSnapshot(
        process_id=4242,
        automation_id=automation_id,
        name_hint=name,
        control_type=50000,
        class_name="Control",
        framework_id="Win32",
        enabled=True,
        offscreen=False,
        is_password=False,
        bounding_left=left,
        bounding_top=top,
        bounding_right=right,
        bounding_bottom=bottom,
    )


def _scan(*elements: UiaElementSnapshot) -> UiaInventoryScan:
    return UiaInventoryScan(
        scanned_element_count=len(elements),
        snapshots=elements,
    )


class SequenceInventoryBackend:
    backend_id = "test.transition-coordinator-uia"

    def __init__(self, *items: UiaInventoryScan | Exception) -> None:
        self.items = list(items)
        self.calls = 0

    def inventory(
        self,
        *,
        frame: WindowFrame,
    ) -> UiaInventoryScan:
        self.calls += 1
        if not self.items:
            raise RuntimeError("inventory sequence exhausted")
        item = self.items[0] if len(self.items) == 1 else self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class SequenceFrameProvider:
    provider_id = "test.transition-coordinator-frame"

    def __init__(self, *frames: WindowFrame | None) -> None:
        self.frames = list(frames)
        self.calls = 0

    def current_frame(
        self,
        *,
        observed_at: str,
    ) -> WindowFrame | None:
        self.calls += 1
        if not self.frames:
            raise RuntimeError("frame sequence exhausted")
        if len(self.frames) == 1:
            return self.frames[0]
        return self.frames.pop(0)


class StaticClickWindowProvider:
    provider_id = "test.click-window"

    def __init__(
        self,
        frame: WindowFrame | None,
    ) -> None:
        self.frame = frame
        self.calls = 0

    def frame_for_click(self, event) -> WindowFrame | None:
        self.calls += 1
        return self.frame


class SequenceClock:
    def __init__(self, *values: str) -> None:
        self.values = list(values)
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if not self.values:
            raise RuntimeError("clock sequence exhausted")
        if len(self.values) == 1:
            return self.values[0]
        return self.values.pop(0)


def _start_session(
    ledger: RealityLedger,
    session_id: str,
) -> None:
    GhostWalkRecorder(ledger).start(
        session_id=session_id,
        recorder_id="operator:test",
        started_at="2026-09-27T04:29:00+00:00",
    )


def _listener_outcome(
    *,
    ledger: RealityLedger,
    session_id: str,
    click_frame: WindowFrame | None,
    observed_at: str,
    flags: int = 0,
    listener_id: str = "listener:transition",
):
    bridge = GhostWalkListenerBridge(
        ledger=ledger,
        capture_adapter=GhostWalkCaptureAdapter(
            ledger=ledger,
            window_provider=StaticClickWindowProvider(click_frame),
        ),
        listener_id=listener_id,
    )
    return bridge.observe_left_button(
        session_id=session_id,
        raw_event=RawMouseHookEvent(
            x_px=500,
            y_px=350,
            flags=flags,
            hook_time_ms=12345,
            extra_info=0,
        ),
        observed_at=observed_at,
    )


def _coordinator(
    *,
    ledger: RealityLedger,
    backend: SequenceInventoryBackend,
    frame_provider: SequenceFrameProvider,
    clock: SequenceClock,
    max_baseline_age_ms: int = 1500,
):
    pauses: list[float] = []
    state_observer = GhostWalkUiaStateObserver(
        ledger=ledger,
        backend=backend,
    )
    coordinator = GhostWalkTransitionCoordinator(
        ledger=ledger,
        state_observer=state_observer,
        frame_provider=frame_provider,
        transition_inferer=GhostWalkTransitionInferer(ledger),
        coordinator_id="coordinator:transition",
        operator_author_id="operator:test",
        max_baseline_age_ms=max_baseline_age_ms,
        post_action_delay_ms=75,
        clock=clock,
        pause=pauses.append,
    )
    return coordinator, pauses


def test_coordinator_001_fresh_baseline_click_after_infers_and_logs(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    session_id = "ghost:transition:complete"
    _start_session(ledger, session_id)

    baseline_frame = _frame(
        captured_at="2026-09-27T04:30:00+00:00"
    )
    click_frame = _frame(
        captured_at="2026-09-27T04:30:00.500000+00:00"
    )
    after_frame = _frame(
        title=TITLE_AFTER,
        captured_at="2026-09-27T04:30:00.700000+00:00",
    )
    backend = SequenceInventoryBackend(
        _scan(
            _element("save", name="Save"),
            _element("dialog", name="Save Dialog"),
        ),
        _scan(
            _element("save", name="Save"),
            _element("saved", name="Saved"),
        ),
    )
    frames = SequenceFrameProvider(
        baseline_frame,
        after_frame,
    )
    clock = SequenceClock(
        "2026-09-27T04:30:00+00:00",
        "2026-09-27T04:30:00.600000+00:00",
        "2026-09-27T04:30:00.700000+00:00",
        "2026-09-27T04:30:00.800000+00:00",
        "2026-09-27T04:30:00.900000+00:00",
    )
    coordinator, pauses = _coordinator(
        ledger=ledger,
        backend=backend,
        frame_provider=frames,
        clock=clock,
    )

    baseline = coordinator.refresh_baseline(session_id=session_id)
    assert baseline is not None
    original_baseline_snapshot_sha = (
        baseline.state_snapshot.snapshot_sha256
    )

    listener = _listener_outcome(
        ledger=ledger,
        session_id=session_id,
        click_frame=click_frame,
        observed_at="2026-09-27T04:30:00.500000+00:00",
    )
    result = coordinator.handle_listener_outcome(listener)

    assert result.receipt.status is TransitionCoordinatorStatus.COMPLETED
    assert result.receipt.reason is TransitionCoordinatorReason.INFERENCE_RECORDED
    assert result.receipt.baseline_age_ms == 500
    assert result.receipt.baseline_consumed is True
    assert coordinator.baseline is None
    assert pauses == [0.075]
    assert result.inference is not None
    assert result.inference.status is TransitionInferenceStatus.CANDIDATES
    assert len(result.inference.candidates) == 3
    assert result.operator_note is not None
    assert result.operator_note.target_sha256 == result.inference.receipt_sha256

    assert result.receipt.rebound_before_snapshot_sha256 is not None
    assert (
        result.receipt.rebound_before_snapshot_sha256
        != original_baseline_snapshot_sha
    )
    action_sha = listener.capture_outcome.observation
    assert action_sha is not None
    rows = ledger.ghostwalk_state_snapshots(
        action_observation_sha256=action_sha.observation_sha256
    )
    assert [row["phase"] for row in rows] == ["BEFORE", "AFTER"]
    assert (
        rows[0]["snapshot_sha256"]
        == result.receipt.rebound_before_snapshot_sha256
    )
    persisted = ledger.recent_transition_coordinator_receipts(1)
    assert persisted[0]["receipt_sha256"] == result.receipt.receipt_sha256


def test_coordinator_002_stale_baseline_holds_and_is_consumed(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    session_id = "ghost:transition:stale"
    _start_session(ledger, session_id)
    frame = _frame()
    backend = SequenceInventoryBackend(
        _scan(_element("save", name="Save"))
    )
    coordinator, pauses = _coordinator(
        ledger=ledger,
        backend=backend,
        frame_provider=SequenceFrameProvider(frame),
        clock=SequenceClock(
            "2026-09-27T04:30:00+00:00",
            "2026-09-27T04:30:02+00:00",
        ),
        max_baseline_age_ms=1000,
    )
    assert coordinator.refresh_baseline(session_id=session_id) is not None

    listener = _listener_outcome(
        ledger=ledger,
        session_id=session_id,
        click_frame=_frame(
            captured_at="2026-09-27T04:30:02+00:00"
        ),
        observed_at="2026-09-27T04:30:02+00:00",
        listener_id="listener:stale",
    )
    result = coordinator.handle_listener_outcome(listener)

    assert result.receipt.status is TransitionCoordinatorStatus.HELD
    assert result.receipt.reason is TransitionCoordinatorReason.BASELINE_STALE
    assert result.receipt.baseline_age_ms == 2000
    assert result.receipt.baseline_consumed is True
    assert coordinator.baseline is None
    assert backend.calls == 1
    assert pauses == []


def test_coordinator_003_scope_drift_holds_before_after_capture(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    session_id = "ghost:transition:scope"
    _start_session(ledger, session_id)
    backend = SequenceInventoryBackend(
        _scan(_element("save", name="Save"))
    )
    coordinator, _ = _coordinator(
        ledger=ledger,
        backend=backend,
        frame_provider=SequenceFrameProvider(_frame()),
        clock=SequenceClock(
            "2026-09-27T04:30:00+00:00",
            "2026-09-27T04:30:00.500000+00:00",
        ),
    )
    assert coordinator.refresh_baseline(session_id=session_id) is not None

    drifted = _frame(
        left=120,
        captured_at="2026-09-27T04:30:00.400000+00:00",
    )
    listener = _listener_outcome(
        ledger=ledger,
        session_id=session_id,
        click_frame=drifted,
        observed_at="2026-09-27T04:30:00.400000+00:00",
        listener_id="listener:scope",
    )
    result = coordinator.handle_listener_outcome(listener)

    assert result.receipt.reason is TransitionCoordinatorReason.BASELINE_SCOPE_DRIFT
    assert result.receipt.status is TransitionCoordinatorStatus.HELD
    assert coordinator.baseline is None
    assert backend.calls == 1


def test_coordinator_004_injected_click_invalidates_baseline_but_is_ignored(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    session_id = "ghost:transition:injected"
    _start_session(ledger, session_id)
    backend = SequenceInventoryBackend(
        _scan(_element("save", name="Save"))
    )
    coordinator, _ = _coordinator(
        ledger=ledger,
        backend=backend,
        frame_provider=SequenceFrameProvider(_frame()),
        clock=SequenceClock(
            "2026-09-27T04:30:00+00:00",
            "2026-09-27T04:30:00.200000+00:00",
        ),
    )
    assert coordinator.refresh_baseline(session_id=session_id) is not None

    listener = _listener_outcome(
        ledger=ledger,
        session_id=session_id,
        click_frame=None,
        observed_at="2026-09-27T04:30:00.100000+00:00",
        flags=LLMHF_INJECTED,
        listener_id="listener:injected",
    )
    result = coordinator.handle_listener_outcome(listener)

    assert result.receipt.status is TransitionCoordinatorStatus.IGNORED
    assert result.receipt.reason is TransitionCoordinatorReason.INJECTED_EVENT
    assert result.receipt.baseline_consumed is True
    assert coordinator.baseline is None


def test_coordinator_005_unrecordable_human_click_consumes_baseline(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    session_id = "ghost:transition:held-click"
    _start_session(ledger, session_id)
    backend = SequenceInventoryBackend(
        _scan(_element("save", name="Save"))
    )
    coordinator, _ = _coordinator(
        ledger=ledger,
        backend=backend,
        frame_provider=SequenceFrameProvider(_frame()),
        clock=SequenceClock(
            "2026-09-27T04:30:00+00:00",
            "2026-09-27T04:30:00.200000+00:00",
        ),
    )
    assert coordinator.refresh_baseline(session_id=session_id) is not None

    listener = _listener_outcome(
        ledger=ledger,
        session_id=session_id,
        click_frame=None,
        observed_at="2026-09-27T04:30:00.100000+00:00",
        listener_id="listener:held-click",
    )
    result = coordinator.handle_listener_outcome(listener)

    assert result.receipt.status is TransitionCoordinatorStatus.HELD
    assert (
        result.receipt.reason
        is TransitionCoordinatorReason.CAPTURE_NOT_RECORDED
    )
    assert result.receipt.baseline_consumed is True
    assert coordinator.baseline is None


def test_coordinator_006_recorded_click_without_baseline_holds(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    session_id = "ghost:transition:no-baseline"
    _start_session(ledger, session_id)
    backend = SequenceInventoryBackend(
        _scan(_element("save", name="Save"))
    )
    coordinator, _ = _coordinator(
        ledger=ledger,
        backend=backend,
        frame_provider=SequenceFrameProvider(_frame()),
        clock=SequenceClock(
            "2026-09-27T04:30:00.200000+00:00",
        ),
    )

    listener = _listener_outcome(
        ledger=ledger,
        session_id=session_id,
        click_frame=_frame(
            captured_at="2026-09-27T04:30:00.100000+00:00"
        ),
        observed_at="2026-09-27T04:30:00.100000+00:00",
        listener_id="listener:no-baseline",
    )
    result = coordinator.handle_listener_outcome(listener)

    assert result.receipt.reason is TransitionCoordinatorReason.NO_BASELINE
    assert result.receipt.baseline_consumed is False
    assert backend.calls == 0


def test_coordinator_007_after_frame_unavailable_holds(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    session_id = "ghost:transition:no-after-frame"
    _start_session(ledger, session_id)
    backend = SequenceInventoryBackend(
        _scan(_element("save", name="Save"))
    )
    coordinator, pauses = _coordinator(
        ledger=ledger,
        backend=backend,
        frame_provider=SequenceFrameProvider(_frame(), None),
        clock=SequenceClock(
            "2026-09-27T04:30:00+00:00",
            "2026-09-27T04:30:00.300000+00:00",
            "2026-09-27T04:30:00.400000+00:00",
        ),
    )
    assert coordinator.refresh_baseline(session_id=session_id) is not None

    listener = _listener_outcome(
        ledger=ledger,
        session_id=session_id,
        click_frame=_frame(
            captured_at="2026-09-27T04:30:00.200000+00:00"
        ),
        observed_at="2026-09-27T04:30:00.200000+00:00",
        listener_id="listener:no-after-frame",
    )
    result = coordinator.handle_listener_outcome(listener)

    assert result.receipt.reason is TransitionCoordinatorReason.AFTER_FRAME_UNAVAILABLE
    assert result.receipt.baseline_consumed is True
    assert pauses == [0.075]


def test_coordinator_008_after_state_hold_stops_inference(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    session_id = "ghost:transition:after-held"
    _start_session(ledger, session_id)
    backend = SequenceInventoryBackend(
        _scan(_element("save", name="Save")),
        RuntimeError("UIA after-state failed"),
    )
    coordinator, _ = _coordinator(
        ledger=ledger,
        backend=backend,
        frame_provider=SequenceFrameProvider(
            _frame(),
            _frame(
                captured_at="2026-09-27T04:30:00.400000+00:00"
            ),
        ),
        clock=SequenceClock(
            "2026-09-27T04:30:00+00:00",
            "2026-09-27T04:30:00.300000+00:00",
            "2026-09-27T04:30:00.400000+00:00",
        ),
    )
    assert coordinator.refresh_baseline(session_id=session_id) is not None

    listener = _listener_outcome(
        ledger=ledger,
        session_id=session_id,
        click_frame=_frame(
            captured_at="2026-09-27T04:30:00.200000+00:00"
        ),
        observed_at="2026-09-27T04:30:00.200000+00:00",
        listener_id="listener:after-held",
    )
    result = coordinator.handle_listener_outcome(listener)

    assert result.receipt.reason is TransitionCoordinatorReason.AFTER_STATE_HELD
    assert result.receipt.after_state_observation_receipt_sha256 is not None
    assert result.inference is None
    assert result.operator_note is None


def test_coordinator_009_failed_baseline_capture_does_not_arm(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    backend = SequenceInventoryBackend(
        RuntimeError("baseline UIA failed")
    )
    coordinator, _ = _coordinator(
        ledger=ledger,
        backend=backend,
        frame_provider=SequenceFrameProvider(_frame()),
        clock=SequenceClock("2026-09-27T04:30:00+00:00"),
    )

    baseline = coordinator.refresh_baseline(
        session_id="ghost:transition:baseline-failed"
    )

    assert baseline is None
    assert coordinator.baseline is None
    state = ledger.recent_uia_state_observation_receipts(1)[0]
    assert state["status"] == "HELD"
    assert state["reason"] == "BACKEND_ERROR"


def test_coordinator_010_click_before_baseline_time_holds(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    session_id = "ghost:transition:time-invalid"
    _start_session(ledger, session_id)
    backend = SequenceInventoryBackend(
        _scan(_element("save", name="Save"))
    )
    coordinator, _ = _coordinator(
        ledger=ledger,
        backend=backend,
        frame_provider=SequenceFrameProvider(_frame()),
        clock=SequenceClock(
            "2026-09-27T04:30:01+00:00",
            "2026-09-27T04:30:01.100000+00:00",
        ),
    )
    assert coordinator.refresh_baseline(session_id=session_id) is not None

    listener = _listener_outcome(
        ledger=ledger,
        session_id=session_id,
        click_frame=_frame(
            captured_at="2026-09-27T04:30:00.900000+00:00"
        ),
        observed_at="2026-09-27T04:30:00.900000+00:00",
        listener_id="listener:time-invalid",
    )
    result = coordinator.handle_listener_outcome(listener)

    assert (
        result.receipt.reason
        is TransitionCoordinatorReason.BASELINE_TIME_INVALID
    )
    assert result.receipt.baseline_consumed is True


def test_coordinator_011_baseline_does_not_bleed_across_cycles(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    session_id = "ghost:transition:cycles"
    _start_session(ledger, session_id)
    before = _scan(_element("save", name="Save"))
    after = _scan(
        _element("save", name="Save"),
        _element("saved", name="Saved"),
    )
    backend = SequenceInventoryBackend(
        before,
        after,
        before,
        after,
    )
    frames = SequenceFrameProvider(
        _frame(captured_at="2026-09-27T04:30:00+00:00"),
        _frame(captured_at="2026-09-27T04:30:00.300000+00:00"),
        _frame(captured_at="2026-09-27T04:30:01+00:00"),
        _frame(captured_at="2026-09-27T04:30:01.300000+00:00"),
    )
    clock = SequenceClock(
        "2026-09-27T04:30:00+00:00",
        "2026-09-27T04:30:00.200000+00:00",
        "2026-09-27T04:30:00.300000+00:00",
        "2026-09-27T04:30:00.400000+00:00",
        "2026-09-27T04:30:00.500000+00:00",
        "2026-09-27T04:30:00.700000+00:00",
        "2026-09-27T04:30:01+00:00",
        "2026-09-27T04:30:01.200000+00:00",
        "2026-09-27T04:30:01.300000+00:00",
        "2026-09-27T04:30:01.400000+00:00",
        "2026-09-27T04:30:01.500000+00:00",
    )
    coordinator, _ = _coordinator(
        ledger=ledger,
        backend=backend,
        frame_provider=frames,
        clock=clock,
    )

    assert coordinator.refresh_baseline(session_id=session_id) is not None
    first_click = _listener_outcome(
        ledger=ledger,
        session_id=session_id,
        click_frame=_frame(
            captured_at="2026-09-27T04:30:00.100000+00:00"
        ),
        observed_at="2026-09-27T04:30:00.100000+00:00",
        listener_id="listener:cycles",
    )
    first = coordinator.handle_listener_outcome(first_click)
    assert first.receipt.status is TransitionCoordinatorStatus.COMPLETED
    assert coordinator.baseline is None

    second_click = _listener_outcome(
        ledger=ledger,
        session_id=session_id,
        click_frame=_frame(
            captured_at="2026-09-27T04:30:00.600000+00:00"
        ),
        observed_at="2026-09-27T04:30:00.600000+00:00",
        listener_id="listener:cycles",
    )
    second = coordinator.handle_listener_outcome(second_click)
    assert second.receipt.reason is TransitionCoordinatorReason.NO_BASELINE
    assert second.inference is None

    assert coordinator.refresh_baseline(session_id=session_id) is not None
    third_click = _listener_outcome(
        ledger=ledger,
        session_id=session_id,
        click_frame=_frame(
            captured_at="2026-09-27T04:30:01.100000+00:00"
        ),
        observed_at="2026-09-27T04:30:01.100000+00:00",
        listener_id="listener:cycles",
    )
    third = coordinator.handle_listener_outcome(third_click)
    assert third.receipt.status is TransitionCoordinatorStatus.COMPLETED

    rows = ledger.recent_transition_coordinator_receipts(10)
    assert [row["status"] for row in rows] == [
        "COMPLETED",
        "HELD",
        "COMPLETED",
    ]


def test_coordinator_012_session_mismatch_consumes_baseline(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    _start_session(ledger, "ghost:transition:A")
    _start_session(ledger, "ghost:transition:B")
    backend = SequenceInventoryBackend(
        _scan(_element("save", name="Save"))
    )
    coordinator, _ = _coordinator(
        ledger=ledger,
        backend=backend,
        frame_provider=SequenceFrameProvider(_frame()),
        clock=SequenceClock(
            "2026-09-27T04:30:00+00:00",
            "2026-09-27T04:30:00.200000+00:00",
        ),
    )
    assert coordinator.refresh_baseline(
        session_id="ghost:transition:A"
    ) is not None

    listener = _listener_outcome(
        ledger=ledger,
        session_id="ghost:transition:B",
        click_frame=_frame(
            captured_at="2026-09-27T04:30:00.100000+00:00"
        ),
        observed_at="2026-09-27T04:30:00.100000+00:00",
        listener_id="listener:session-mismatch",
    )
    result = coordinator.handle_listener_outcome(listener)

    assert result.receipt.reason is TransitionCoordinatorReason.SESSION_MISMATCH
    assert result.receipt.baseline_consumed is True
    assert coordinator.baseline is None
