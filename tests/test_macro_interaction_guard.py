from __future__ import annotations

from pathlib import Path

import pytest

from phios.macro_interaction_guard import (
    GuardDecision,
    GuardReason,
    InteractionGuard,
    InteractionGuardContractError,
    InteractionSnapshot,
    PixelAnchor,
    WindowFrame,
)
from phios.spine.ledger import RealityLedger

TITLE = "b" * 64


def _ledger(tmp_path: Path) -> RealityLedger:
    return RealityLedger(tmp_path / "ledger" / "receipts.jsonl")


def _frame(
    *,
    process_id: str = "app:editor",
    title: str = TITLE,
    left: int = 100,
    top: int = 50,
    width: int = 800,
    height: int = 600,
    foreground: bool = True,
) -> WindowFrame:
    return WindowFrame(
        process_id=process_id,
        window_title_sha256=title,
        left_px=left,
        top_px=top,
        width_px=width,
        height_px=height,
        display_scale_percent=100,
        foreground=foreground,
        captured_at="2026-09-27T00:40:00+00:00",
    )


def _snapshot(
    frame: WindowFrame,
    *,
    moved: bool = False,
    operator: bool = False,
    overlay: bool = False,
) -> InteractionSnapshot:
    return InteractionSnapshot(
        frame=frame,
        pointer_x_px=frame.left_px,
        pointer_y_px=frame.top_px,
        pointer_moved_since_anchor=moved,
        operator_input_detected=operator,
        unexpected_overlay_detected=overlay,
    )


def test_guard_001_ghost_click_resolves_after_window_move_resize(
    tmp_path: Path,
) -> None:
    source = _frame()
    anchor = PixelAnchor.from_observed_click(
        anchor_id="anchor:save",
        frame=source,
        x_px=500,
        y_px=350,
        semantic_hint="Save button",
    )
    moved = _frame(left=300, top=200, width=1000, height=800)

    receipt = InteractionGuard(_ledger(tmp_path)).assess(
        anchor=anchor,
        snapshot=_snapshot(moved),
        observed_at="2026-09-27T00:41:00+00:00",
    )

    assert receipt.decision is GuardDecision.CLEAR
    assert receipt.reasons == (GuardReason.FRAME_MATCH,)
    assert receipt.resolved_x_px == 800
    assert receipt.resolved_y_px == 600
    assert receipt.execution_authority is False


@pytest.mark.parametrize(
    ("snapshot", "reason"),
    [
        (_snapshot(_frame(process_id="app:wrong")), GuardReason.PROCESS_MISMATCH),
        (_snapshot(_frame(title="c" * 64)), GuardReason.WINDOW_MISMATCH),
        (_snapshot(_frame(foreground=False)), GuardReason.NOT_FOREGROUND),
        (_snapshot(_frame(), overlay=True), GuardReason.OVERLAY_DETECTED),
        (_snapshot(_frame(), operator=True), GuardReason.OPERATOR_INPUT_DETECTED),
        (_snapshot(_frame(), moved=True), GuardReason.POINTER_MOVED),
    ],
)
def test_guard_002_interference_holds(
    tmp_path: Path,
    snapshot: InteractionSnapshot,
    reason: GuardReason,
) -> None:
    anchor = PixelAnchor.from_observed_click(
        anchor_id="anchor:target",
        frame=_frame(),
        x_px=500,
        y_px=350,
    )

    receipt = InteractionGuard(_ledger(tmp_path)).assess(
        anchor=anchor,
        snapshot=snapshot,
        observed_at="2026-09-27T00:41:00+00:00",
    )

    assert receipt.decision is GuardDecision.HOLD
    assert reason in receipt.reasons
    assert receipt.resolved_x_px is None
    assert receipt.resolved_y_px is None


def test_guard_003_outside_source_click_is_rejected() -> None:
    with pytest.raises(
        InteractionGuardContractError,
        match="outside source window frame",
    ):
        PixelAnchor.from_observed_click(
            anchor_id="anchor:outside",
            frame=_frame(),
            x_px=50,
            y_px=20,
        )


def test_guard_004_guard_receipt_is_persisted(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    frame = _frame()
    anchor = PixelAnchor.from_observed_click(
        anchor_id="anchor:persist",
        frame=frame,
        x_px=500,
        y_px=350,
    )

    receipt = InteractionGuard(ledger).assess(
        anchor=anchor,
        snapshot=_snapshot(frame, overlay=True),
        observed_at="2026-09-27T00:41:00+00:00",
    )
    rows = ledger.recent_interaction_guard_receipts(1)

    assert rows[0]["receipt_sha256"] == receipt.receipt_sha256
    assert rows[0]["decision"] == "HOLD"


def test_guard_005_pixel_anchor_is_zero_authority() -> None:
    anchor = PixelAnchor.from_observed_click(
        anchor_id="anchor:zero",
        frame=_frame(),
        x_px=500,
        y_px=350,
    )
    assert anchor.operational_authority is False
    assert anchor.action_authority is False
    assert anchor.execution_authority is False
