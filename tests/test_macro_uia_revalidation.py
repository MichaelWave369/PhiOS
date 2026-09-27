from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from phios.macro_ghostwalk import SemanticTarget
from phios.macro_interaction_guard import WindowFrame
from phios.macro_uia_revalidation import (
    ComtypesWindowsUiaReplayBackend,
    SemanticReplayRevalidator,
    SemanticRevalidationContractError,
    SemanticRevalidationDecision,
    SemanticRevalidationReason,
)
from phios.macro_windows_uia import UiaElementSnapshot
from phios.spine.ledger import RealityLedger

TITLE = "1" * 64


def _ledger(tmp_path: Path) -> RealityLedger:
    return RealityLedger(tmp_path / "ledger" / "receipts.jsonl")


def _frame(
    *,
    pid: int = 4242,
    title: str = TITLE,
    foreground: bool = True,
) -> WindowFrame:
    return WindowFrame(
        process_id=f"pid:{pid}",
        window_title_sha256=title,
        left_px=100,
        top_px=50,
        width_px=800,
        height_px=600,
        display_scale_percent=100,
        foreground=foreground,
        captured_at="2026-09-27T02:00:00+00:00",
    )


def _target(
    *,
    provider: str = "windows.uia.v0.16",
    automation_id: str = "save-button",
    control_type: int | None = 50000,
) -> SemanticTarget:
    return SemanticTarget(
        provider=provider,
        selector=json.dumps(
            {
                "automation_id": automation_id,
                "control_type": control_type,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        role=(
            None
            if control_type is None
            else f"uia.control_type.{control_type}"
        ),
        name_hint="Save",
    )


def _candidate(
    *,
    pid: int = 4242,
    automation_id: str | None = "save-button",
    control_type: int | None = 50000,
    enabled: bool | None = True,
    offscreen: bool | None = False,
    left: int | None = 450,
    top: int | None = 320,
    right: int | None = 550,
    bottom: int | None = 380,
) -> UiaElementSnapshot:
    return UiaElementSnapshot(
        process_id=pid,
        automation_id=automation_id,
        name_hint="Save",
        control_type=control_type,
        class_name="Button",
        framework_id="Win32",
        enabled=enabled,
        offscreen=offscreen,
        is_password=False,
        bounding_left=left,
        bounding_top=top,
        bounding_right=right,
        bounding_bottom=bottom,
    )


class StaticReplayBackend:
    backend_id = "test.replay"

    def __init__(
        self,
        candidates: tuple[UiaElementSnapshot, ...] = (),
        *,
        error: Exception | None = None,
    ) -> None:
        self.candidates = candidates
        self.error = error
        self.calls = 0

    def find_matches(
        self,
        *,
        frame: WindowFrame,
        selector,
    ) -> tuple[UiaElementSnapshot, ...]:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.candidates


def _assess(
    tmp_path: Path,
    *,
    backend: StaticReplayBackend,
    target: SemanticTarget | None = None,
    frame: WindowFrame | None = None,
    expected_process_id: str = "pid:4242",
    expected_window_title_sha256: str = TITLE,
):
    ledger = _ledger(tmp_path)
    receipt = SemanticReplayRevalidator(
        ledger=ledger,
        backend=backend,
    ).assess(
        target=target or _target(),
        expected_process_id=expected_process_id,
        expected_window_title_sha256=expected_window_title_sha256,
        frame=frame or _frame(),
        observed_at="2026-09-27T02:00:01+00:00",
    )
    return ledger, receipt


def test_revalidation_001_unique_valid_target_clears(
    tmp_path: Path,
) -> None:
    ledger, receipt = _assess(
        tmp_path,
        backend=StaticReplayBackend((_candidate(),)),
    )

    assert receipt.decision is SemanticRevalidationDecision.CLEAR
    assert receipt.reason is SemanticRevalidationReason.TARGET_CLEAR
    assert receipt.match_count == 1
    assert receipt.resolved_x_px == 500
    assert receipt.resolved_y_px == 350
    assert receipt.selected_snapshot_sha256 is not None
    assert len(ledger.uia_element_snapshots()) == 1


def test_revalidation_002_zero_matches_holds_missing(
    tmp_path: Path,
) -> None:
    _, receipt = _assess(
        tmp_path,
        backend=StaticReplayBackend(()),
    )

    assert receipt.decision is SemanticRevalidationDecision.HOLD
    assert receipt.reason is SemanticRevalidationReason.TARGET_MISSING
    assert receipt.match_count == 0


def test_revalidation_003_two_matches_hold_ambiguous(
    tmp_path: Path,
) -> None:
    candidate = _candidate()
    _, receipt = _assess(
        tmp_path,
        backend=StaticReplayBackend((candidate, candidate)),
    )

    assert receipt.decision is SemanticRevalidationDecision.HOLD
    assert receipt.reason is SemanticRevalidationReason.TARGET_AMBIGUOUS
    assert receipt.match_count == 2
    assert len(receipt.candidate_snapshot_sha256s) == 2
    assert (
        receipt.candidate_snapshot_sha256s[0]
        == receipt.candidate_snapshot_sha256s[1]
    )


def test_revalidation_004_wrong_process_holds_before_backend(
    tmp_path: Path,
) -> None:
    backend = StaticReplayBackend((_candidate(),))
    _, receipt = _assess(
        tmp_path,
        backend=backend,
        frame=_frame(pid=9999),
    )

    assert receipt.reason is SemanticRevalidationReason.PROCESS_MISMATCH
    assert backend.calls == 0


def test_revalidation_005_wrong_window_holds_before_backend(
    tmp_path: Path,
) -> None:
    backend = StaticReplayBackend((_candidate(),))
    _, receipt = _assess(
        tmp_path,
        backend=backend,
        frame=_frame(title="2" * 64),
    )

    assert receipt.reason is SemanticRevalidationReason.WINDOW_MISMATCH
    assert backend.calls == 0


def test_revalidation_006_background_window_holds(
    tmp_path: Path,
) -> None:
    backend = StaticReplayBackend((_candidate(),))
    _, receipt = _assess(
        tmp_path,
        backend=backend,
        frame=_frame(foreground=False),
    )

    assert receipt.reason is SemanticRevalidationReason.NOT_FOREGROUND
    assert backend.calls == 0


@pytest.mark.parametrize(
    ("candidate", "reason"),
    [
        (
            _candidate(pid=9999),
            SemanticRevalidationReason.CANDIDATE_PROCESS_MISMATCH,
        ),
        (
            _candidate(automation_id="other"),
            SemanticRevalidationReason.AUTOMATION_ID_MISMATCH,
        ),
        (
            _candidate(control_type=50001),
            SemanticRevalidationReason.CONTROL_TYPE_MISMATCH,
        ),
        (
            _candidate(enabled=None),
            SemanticRevalidationReason.ENABLED_UNKNOWN,
        ),
        (
            _candidate(enabled=False),
            SemanticRevalidationReason.DISABLED,
        ),
        (
            _candidate(offscreen=None),
            SemanticRevalidationReason.OFFSCREEN_UNKNOWN,
        ),
        (
            _candidate(offscreen=True),
            SemanticRevalidationReason.OFFSCREEN,
        ),
        (
            _candidate(left=None, top=None, right=None, bottom=None),
            SemanticRevalidationReason.BOUNDS_UNKNOWN,
        ),
        (
            _candidate(left=50, top=20, right=150, bottom=80),
            SemanticRevalidationReason.BOUNDS_OUTSIDE_WINDOW,
        ),
    ],
)
def test_revalidation_007_candidate_safety_holds(
    tmp_path: Path,
    candidate: UiaElementSnapshot,
    reason: SemanticRevalidationReason,
) -> None:
    _, receipt = _assess(
        tmp_path,
        backend=StaticReplayBackend((candidate,)),
    )

    assert receipt.decision is SemanticRevalidationDecision.HOLD
    assert receipt.reason is reason
    assert receipt.selected_snapshot_sha256 is None
    assert receipt.resolved_x_px is None
    assert receipt.resolved_y_px is None


def test_revalidation_008_backend_error_holds(
    tmp_path: Path,
) -> None:
    _, receipt = _assess(
        tmp_path,
        backend=StaticReplayBackend(
            error=RuntimeError("UIA replay failed")
        ),
    )

    assert receipt.reason is SemanticRevalidationReason.BACKEND_ERROR


def test_revalidation_009_unsupported_provider_holds(
    tmp_path: Path,
) -> None:
    backend = StaticReplayBackend((_candidate(),))
    _, receipt = _assess(
        tmp_path,
        backend=backend,
        target=_target(provider="other.provider"),
    )

    assert receipt.reason is SemanticRevalidationReason.PROVIDER_UNSUPPORTED
    assert backend.calls == 0


def test_revalidation_010_invalid_selector_holds(
    tmp_path: Path,
) -> None:
    backend = StaticReplayBackend((_candidate(),))
    target = SemanticTarget(
        provider="windows.uia.v0.16",
        selector='{"automation_id":"save-button","extra":true}',
    )
    _, receipt = _assess(
        tmp_path,
        backend=backend,
        target=target,
    )

    assert receipt.reason is SemanticRevalidationReason.SELECTOR_INVALID
    assert backend.calls == 0


def test_revalidation_011_receipt_persists_and_is_zero_authority(
    tmp_path: Path,
) -> None:
    ledger, receipt = _assess(
        tmp_path,
        backend=StaticReplayBackend((_candidate(),)),
    )
    rows = ledger.recent_semantic_revalidation_receipts(1)

    assert rows[0]["receipt_sha256"] == receipt.receipt_sha256
    assert rows[0]["decision"] == "CLEAR"
    assert receipt.operational_authority is False
    assert receipt.action_authority is False
    assert receipt.execution_authority is False
    assert ledger.recent() == []


def test_revalidation_012_real_backend_rejects_non_windows() -> None:
    if os.name == "nt":
        pytest.skip("non-Windows contract test")
    with pytest.raises(
        SemanticRevalidationContractError,
        match="requires Windows",
    ):
        ComtypesWindowsUiaReplayBackend()
