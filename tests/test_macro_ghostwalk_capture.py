from __future__ import annotations

import os
from pathlib import Path

import pytest

from phios.macro_ghostwalk import (
    GhostWalkRecorder,
    SemanticTarget,
    TargetStrategy,
)
from phios.macro_ghostwalk_capture import (
    CaptureReason,
    CaptureStatus,
    GhostWalkCaptureAdapter,
    GhostWalkCaptureContractError,
    PointerButton,
    PointerClickEvent,
    SemanticLookupStatus,
    WindowsWindowFrameProvider,
)
from phios.macro_interaction_guard import WindowFrame
from phios.spine.ledger import RealityLedger

TITLE = "d" * 64


def _ledger(tmp_path: Path) -> RealityLedger:
    return RealityLedger(tmp_path / "ledger" / "receipts.jsonl")


def _frame(
    *,
    left: int = 100,
    top: int = 50,
    width: int = 800,
    height: int = 600,
) -> WindowFrame:
    return WindowFrame(
        process_id="pid:4242",
        window_title_sha256=TITLE,
        left_px=left,
        top_px=top,
        width_px=width,
        height_px=height,
        display_scale_percent=100,
        foreground=True,
        captured_at="2026-09-27T01:00:00+00:00",
    )


def _event(
    *,
    event_id: str = "click:1",
    x: int = 500,
    y: int = 350,
    button: PointerButton = PointerButton.LEFT,
    injected: bool = False,
) -> PointerClickEvent:
    return PointerClickEvent(
        event_id=event_id,
        x_px=x,
        y_px=y,
        button=button,
        observed_at="2026-09-27T01:00:01+00:00",
        injected=injected,
    )


def _semantic() -> SemanticTarget:
    return SemanticTarget(
        provider="uia",
        selector="automation_id=save",
        role="button",
        name_hint="Save",
    )


class StaticWindowProvider:
    provider_id = "test.window"

    def __init__(self, frame: WindowFrame | None) -> None:
        self.frame = frame
        self.calls = 0

    def frame_for_click(
        self,
        event: PointerClickEvent,
    ) -> WindowFrame | None:
        self.calls += 1
        return self.frame


class StaticSemanticProvider:
    provider_id = "test.semantic"

    def __init__(
        self,
        target: SemanticTarget | None = None,
        *,
        fail: bool = False,
    ) -> None:
        self.target = target
        self.fail = fail
        self.calls = 0

    def target_for_click(
        self,
        *,
        event: PointerClickEvent,
        frame: WindowFrame,
    ) -> SemanticTarget | None:
        self.calls += 1
        if self.fail:
            raise RuntimeError("semantic provider unavailable")
        return self.target


def _session(ledger: RealityLedger, session_id: str) -> None:
    GhostWalkRecorder(ledger).start(
        session_id=session_id,
        recorder_id="operator:mikey",
        started_at="2026-09-27T01:00:00+00:00",
    )


def test_capture_001_real_left_click_records_semantic_observation(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    _session(ledger, "capture:semantic")
    window = StaticWindowProvider(_frame())
    semantic = StaticSemanticProvider(_semantic())
    adapter = GhostWalkCaptureAdapter(
        ledger=ledger,
        window_provider=window,
        semantic_provider=semantic,
    )

    outcome = adapter.capture_click(
        session_id="capture:semantic",
        event=_event(),
    )

    assert outcome.receipt.status is CaptureStatus.RECORDED
    assert outcome.receipt.reason is CaptureReason.OBSERVATION_RECORDED
    assert (
        outcome.receipt.semantic_lookup_status
        is SemanticLookupStatus.FOUND
    )
    assert outcome.observation is not None
    assert outcome.observation.preferred_strategy is TargetStrategy.SEMANTIC
    assert outcome.receipt.semantic_target_sha256 == (
        outcome.observation.semantic_target.target_sha256
        if outcome.observation.semantic_target is not None
        else None
    )
    assert window.calls == 1
    assert semantic.calls == 1


def test_capture_002_no_semantics_records_pixel_fallback(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    _session(ledger, "capture:pixel")
    adapter = GhostWalkCaptureAdapter(
        ledger=ledger,
        window_provider=StaticWindowProvider(_frame()),
        semantic_provider=StaticSemanticProvider(None),
    )

    outcome = adapter.capture_click(
        session_id="capture:pixel",
        event=_event(event_id="click:pixel"),
    )

    assert outcome.receipt.status is CaptureStatus.RECORDED
    assert (
        outcome.receipt.semantic_lookup_status
        is SemanticLookupStatus.NOT_FOUND
    )
    assert outcome.observation is not None
    assert (
        outcome.observation.preferred_strategy
        is TargetStrategy.WINDOW_RELATIVE_PIXEL
    )


def test_capture_003_injected_click_is_held_before_window_lookup(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    _session(ledger, "capture:injected")
    window = StaticWindowProvider(_frame())
    adapter = GhostWalkCaptureAdapter(
        ledger=ledger,
        window_provider=window,
    )

    outcome = adapter.capture_click(
        session_id="capture:injected",
        event=_event(event_id="click:injected", injected=True),
    )

    assert outcome.receipt.status is CaptureStatus.HELD
    assert outcome.receipt.reason is CaptureReason.INJECTED_EVENT
    assert outcome.observation is None
    assert window.calls == 0
    assert GhostWalkRecorder(ledger).observations(
        session_id="capture:injected"
    ) == ()


def test_capture_004_non_left_click_is_held(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    _session(ledger, "capture:right")
    window = StaticWindowProvider(_frame())
    adapter = GhostWalkCaptureAdapter(
        ledger=ledger,
        window_provider=window,
    )

    outcome = adapter.capture_click(
        session_id="capture:right",
        event=_event(
            event_id="click:right",
            button=PointerButton.RIGHT,
        ),
    )

    assert outcome.receipt.status is CaptureStatus.HELD
    assert outcome.receipt.reason is CaptureReason.UNSUPPORTED_BUTTON
    assert window.calls == 0


def test_capture_005_window_unavailable_is_held(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    _session(ledger, "capture:no-window")
    adapter = GhostWalkCaptureAdapter(
        ledger=ledger,
        window_provider=StaticWindowProvider(None),
    )

    outcome = adapter.capture_click(
        session_id="capture:no-window",
        event=_event(event_id="click:no-window"),
    )

    assert outcome.receipt.status is CaptureStatus.HELD
    assert outcome.receipt.reason is CaptureReason.WINDOW_UNAVAILABLE
    assert outcome.observation is None


def test_capture_006_click_outside_reported_window_is_held(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    _session(ledger, "capture:outside")
    adapter = GhostWalkCaptureAdapter(
        ledger=ledger,
        window_provider=StaticWindowProvider(_frame()),
    )

    outcome = adapter.capture_click(
        session_id="capture:outside",
        event=_event(
            event_id="click:outside",
            x=20,
            y=20,
        ),
    )

    assert outcome.receipt.status is CaptureStatus.HELD
    assert outcome.receipt.reason is CaptureReason.CLICK_OUTSIDE_WINDOW
    assert outcome.receipt.frame_sha256 == _frame().frame_sha256
    assert outcome.observation is None


def test_capture_007_semantic_failure_keeps_pixel_observation(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    _session(ledger, "capture:semantic-error")
    semantic = StaticSemanticProvider(fail=True)
    adapter = GhostWalkCaptureAdapter(
        ledger=ledger,
        window_provider=StaticWindowProvider(_frame()),
        semantic_provider=semantic,
    )

    outcome = adapter.capture_click(
        session_id="capture:semantic-error",
        event=_event(event_id="click:semantic-error"),
    )

    assert outcome.receipt.status is CaptureStatus.RECORDED
    assert outcome.receipt.reason is CaptureReason.SEMANTIC_LOOKUP_ERROR
    assert (
        outcome.receipt.semantic_lookup_status
        is SemanticLookupStatus.ERROR
    )
    assert outcome.observation is not None
    assert outcome.observation.semantic_target is None
    assert (
        outcome.observation.preferred_strategy
        is TargetStrategy.WINDOW_RELATIVE_PIXEL
    )


def test_capture_008_receipt_is_persisted_and_zero_authority(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    _session(ledger, "capture:receipt")
    adapter = GhostWalkCaptureAdapter(
        ledger=ledger,
        window_provider=StaticWindowProvider(_frame()),
    )

    outcome = adapter.capture_click(
        session_id="capture:receipt",
        event=_event(event_id="click:receipt"),
    )
    rows = ledger.recent_ghostwalk_capture_receipts(1)

    assert rows[0]["receipt_sha256"] == outcome.receipt.receipt_sha256
    assert rows[0]["status"] == "RECORDED"
    assert outcome.receipt.operational_authority is False
    assert outcome.receipt.action_authority is False
    assert outcome.receipt.execution_authority is False
    assert ledger.recent() == []


def test_capture_009_windows_provider_rejects_non_windows() -> None:
    if os.name == "nt":
        pytest.skip("non-Windows contract test")
    with pytest.raises(
        GhostWalkCaptureContractError,
        match="requires Windows",
    ):
        WindowsWindowFrameProvider()


def test_capture_010_pointer_event_is_zero_authority() -> None:
    event = _event()
    assert event.operational_authority is False
    assert event.action_authority is False
    assert event.execution_authority is False
    assert len(event.event_sha256) == 64
