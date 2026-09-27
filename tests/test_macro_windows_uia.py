from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from phios.macro_ghostwalk import GhostWalkRecorder
from phios.macro_ghostwalk_capture import (
    CaptureReason,
    GhostWalkCaptureAdapter,
    PointerButton,
    PointerClickEvent,
    SemanticLookupStatus,
)
from phios.macro_interaction_guard import WindowFrame
from phios.macro_windows_uia import (
    ComtypesWindowsUiaBackend,
    UiaElementSnapshot,
    UiaLookupDecision,
    WindowsUiaContractError,
    WindowsUiaSemanticProvider,
)
from phios.spine.ledger import RealityLedger

TITLE = "f" * 64


def _ledger(tmp_path: Path) -> RealityLedger:
    return RealityLedger(tmp_path / "ledger" / "receipts.jsonl")


def _frame(*, pid: int = 4242) -> WindowFrame:
    return WindowFrame(
        process_id=f"pid:{pid}",
        window_title_sha256=TITLE,
        left_px=100,
        top_px=50,
        width_px=800,
        height_px=600,
        display_scale_percent=100,
        foreground=True,
        captured_at="2026-09-27T01:40:00+00:00",
    )


def _event() -> PointerClickEvent:
    return PointerClickEvent(
        event_id="click:uia",
        x_px=500,
        y_px=350,
        button=PointerButton.LEFT,
        observed_at="2026-09-27T01:40:01+00:00",
    )


def _snapshot(
    *,
    pid: int = 4242,
    automation_id: str | None = "save-button",
    name: str | None = "Save",
    control_type: int | None = 50000,
    password: bool | None = False,
) -> UiaElementSnapshot:
    return UiaElementSnapshot(
        process_id=pid,
        automation_id=automation_id,
        name_hint=name,
        control_type=control_type,
        class_name="Button",
        framework_id="Win32",
        enabled=True,
        offscreen=False,
        is_password=password,
        bounding_left=450,
        bounding_top=320,
        bounding_right=550,
        bounding_bottom=380,
    )


class StaticUiaBackend:
    backend_id = "test.uia"

    def __init__(
        self,
        snapshot: UiaElementSnapshot | None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.error = error
        self.calls = 0

    def element_from_point(
        self,
        *,
        x_px: int,
        y_px: int,
    ) -> UiaElementSnapshot | None:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.snapshot


class StaticWindowProvider:
    provider_id = "test.window"

    def frame_for_click(
        self,
        event: PointerClickEvent,
    ) -> WindowFrame | None:
        return _frame()


def test_uia_001_strong_automation_id_becomes_semantic_target(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    backend = StaticUiaBackend(_snapshot())
    provider = WindowsUiaSemanticProvider(
        ledger=ledger,
        backend=backend,
    )

    target = provider.target_for_click(
        event=_event(),
        frame=_frame(),
    )

    assert target is not None
    assert target.provider == "windows.uia.v0.16"
    selector = json.loads(target.selector)
    assert selector == {
        "automation_id": "save-button",
        "control_type": 50000,
    }
    assert target.role == "uia.control_type.50000"
    assert target.name_hint == "Save"

    snapshots = ledger.uia_element_snapshots()
    receipts = ledger.recent_uia_lookup_receipts(1)
    assert len(snapshots) == 1
    assert receipts[0]["decision"] == "FOUND"
    assert receipts[0]["snapshot_sha256"] == (
        snapshots[0]["snapshot_sha256"]
    )
    assert receipts[0]["semantic_target_sha256"] == target.target_sha256


def test_uia_002_missing_automation_id_is_ambiguous_pixel_fallback(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    provider = WindowsUiaSemanticProvider(
        ledger=ledger,
        backend=StaticUiaBackend(
            _snapshot(automation_id=None)
        ),
    )

    target = provider.target_for_click(
        event=_event(),
        frame=_frame(),
    )

    assert target is None
    rows = ledger.recent_uia_lookup_receipts(1)
    assert rows[0]["decision"] == "AMBIGUOUS"
    assert rows[0]["reason"] == "automation_id_missing"
    assert rows[0]["semantic_target_sha256"] is None
    assert len(ledger.uia_element_snapshots()) == 1


def test_uia_003_process_mismatch_is_not_promoted(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    provider = WindowsUiaSemanticProvider(
        ledger=ledger,
        backend=StaticUiaBackend(_snapshot(pid=9999)),
    )

    target = provider.target_for_click(
        event=_event(),
        frame=_frame(pid=4242),
    )

    assert target is None
    rows = ledger.recent_uia_lookup_receipts(1)
    assert rows[0]["decision"] == "FRAME_MISMATCH"
    assert rows[0]["reason"] == (
        "uia_process_does_not_match_window_frame"
    )


def test_uia_004_password_control_redacts_name_hint_from_target(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    provider = WindowsUiaSemanticProvider(
        ledger=ledger,
        backend=StaticUiaBackend(
            _snapshot(
                automation_id="password-field",
                name="Password",
                control_type=50004,
                password=True,
            )
        ),
    )

    target = provider.target_for_click(
        event=_event(),
        frame=_frame(),
    )

    assert target is not None
    assert target.name_hint is None
    selector = json.loads(target.selector)
    assert selector["automation_id"] == "password-field"


def test_uia_005_no_element_records_no_element_receipt(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    provider = WindowsUiaSemanticProvider(
        ledger=ledger,
        backend=StaticUiaBackend(None),
    )

    target = provider.target_for_click(
        event=_event(),
        frame=_frame(),
    )

    assert target is None
    rows = ledger.recent_uia_lookup_receipts(1)
    assert rows[0]["decision"] == "NO_ELEMENT"
    assert rows[0]["snapshot_sha256"] is None
    assert ledger.uia_element_snapshots() == []


def test_uia_006_backend_error_is_receipted_then_re_raised(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    provider = WindowsUiaSemanticProvider(
        ledger=ledger,
        backend=StaticUiaBackend(
            None,
            error=RuntimeError("COM failure"),
        ),
    )

    with pytest.raises(RuntimeError, match="COM failure"):
        provider.target_for_click(
            event=_event(),
            frame=_frame(),
        )

    rows = ledger.recent_uia_lookup_receipts(1)
    assert rows[0]["decision"] == "ERROR"
    assert rows[0]["reason"] == "uia_backend_error"


def test_uia_007_v014_capture_falls_back_when_uia_is_ambiguous(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    GhostWalkRecorder(ledger).start(
        session_id="ghost:uia-ambiguous",
        recorder_id="operator:mikey",
        started_at="2026-09-27T01:40:00+00:00",
    )
    provider = WindowsUiaSemanticProvider(
        ledger=ledger,
        backend=StaticUiaBackend(
            _snapshot(automation_id=None)
        ),
    )
    adapter = GhostWalkCaptureAdapter(
        ledger=ledger,
        window_provider=StaticWindowProvider(),
        semantic_provider=provider,
    )

    outcome = adapter.capture_click(
        session_id="ghost:uia-ambiguous",
        event=_event(),
    )

    assert (
        outcome.receipt.semantic_lookup_status
        is SemanticLookupStatus.NOT_FOUND
    )
    assert outcome.observation is not None
    assert outcome.observation.semantic_target is None
    assert (
        outcome.observation.preferred_strategy.value
        == "WINDOW_RELATIVE_PIXEL"
    )


def test_uia_008_v014_capture_survives_uia_backend_error(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    GhostWalkRecorder(ledger).start(
        session_id="ghost:uia-error",
        recorder_id="operator:mikey",
        started_at="2026-09-27T01:40:00+00:00",
    )
    provider = WindowsUiaSemanticProvider(
        ledger=ledger,
        backend=StaticUiaBackend(
            None,
            error=RuntimeError("UIA offline"),
        ),
    )
    adapter = GhostWalkCaptureAdapter(
        ledger=ledger,
        window_provider=StaticWindowProvider(),
        semantic_provider=provider,
    )

    outcome = adapter.capture_click(
        session_id="ghost:uia-error",
        event=_event(),
    )

    assert outcome.receipt.reason is CaptureReason.SEMANTIC_LOOKUP_ERROR
    assert (
        outcome.receipt.semantic_lookup_status
        is SemanticLookupStatus.ERROR
    )
    assert outcome.observation is not None
    assert outcome.observation.semantic_target is None
    assert ledger.recent_uia_lookup_receipts(1)[0]["decision"] == "ERROR"


def test_uia_009_snapshot_contains_identity_not_control_value() -> None:
    snapshot = _snapshot()
    payload = snapshot.to_dict()

    assert "value" not in payload
    assert "text" not in payload
    assert "help_text" not in payload
    assert payload["automation_id"] == "save-button"
    assert payload["name_hint"] == "Save"
    assert snapshot.operational_authority is False
    assert snapshot.action_authority is False
    assert snapshot.execution_authority is False


def test_uia_010_comtypes_backend_rejects_non_windows() -> None:
    if os.name == "nt":
        pytest.skip("non-Windows contract test")
    with pytest.raises(
        WindowsUiaContractError,
        match="requires Windows",
    ):
        ComtypesWindowsUiaBackend()


def test_uia_011_v014_capture_prefers_strong_uia_target(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    GhostWalkRecorder(ledger).start(
        session_id="ghost:uia-strong",
        recorder_id="operator:mikey",
        started_at="2026-09-27T01:40:00+00:00",
    )
    provider = WindowsUiaSemanticProvider(
        ledger=ledger,
        backend=StaticUiaBackend(_snapshot()),
    )
    adapter = GhostWalkCaptureAdapter(
        ledger=ledger,
        window_provider=StaticWindowProvider(),
        semantic_provider=provider,
    )

    outcome = adapter.capture_click(
        session_id="ghost:uia-strong",
        event=_event(),
    )

    assert (
        outcome.receipt.semantic_lookup_status
        is SemanticLookupStatus.FOUND
    )
    assert outcome.observation is not None
    assert outcome.observation.semantic_target is not None
    assert outcome.observation.preferred_strategy.value == "SEMANTIC"
    assert (
        outcome.observation.semantic_target.provider
        == "windows.uia.v0.16"
    )
