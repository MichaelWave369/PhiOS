from __future__ import annotations

import json
from pathlib import Path

import pytest

from phios.macro_ghostwalk import (
    GhostWalkContractError,
    GhostWalkRecorder,
    SemanticTarget,
    TargetStrategy,
)
from phios.macro_graph import DoStep, MacroGraphPlanner
from phios.macro_interaction_guard import WindowFrame
from phios.spine.ledger import RealityLedger

TITLE = "a" * 64


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
        process_id="app:editor",
        window_title_sha256=TITLE,
        left_px=left,
        top_px=top,
        width_px=width,
        height_px=height,
        display_scale_percent=100,
        foreground=True,
        captured_at="2026-09-27T00:50:00+00:00",
    )


def _semantic() -> SemanticTarget:
    return SemanticTarget(
        provider="uia",
        selector="automation_id=save-button",
        role="button",
        name_hint="Save",
    )


def _start(recorder: GhostWalkRecorder, session_id: str = "ghost:one") -> None:
    recorder.start(
        session_id=session_id,
        recorder_id="operator:mikey",
        started_at="2026-09-27T00:50:00+00:00",
    )


def test_ghostwalk_001_semantic_target_is_preferred_in_draft(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    recorder = GhostWalkRecorder(ledger)
    _start(recorder)

    observation = recorder.record_click(
        session_id="ghost:one",
        frame=_frame(),
        x_px=500,
        y_px=350,
        observed_at="2026-09-27T00:50:01+00:00",
        semantic_target=_semantic(),
        semantic_hint="Save button",
    )
    draft = recorder.compile_draft(
        session_id="ghost:one",
        macro_id="macro:ghost-save",
        macro_version="0.13.0",
    )

    assert observation.preferred_strategy is TargetStrategy.SEMANTIC
    assert draft.receipt.semantic_preferred_count == 1
    assert draft.receipt.pixel_fallback_count == 0
    assert draft.definition.operational_authority is False
    assert draft.definition.action_authority is False
    assert draft.definition.execution_authority is False

    step = draft.definition.steps[0]
    assert isinstance(step, DoStep)
    operation = step.operation
    assert operation.adapter_id == "desktop.interaction"
    assert operation.action == "click"
    assert operation.required_capabilities == ("ui.interact",)
    assert operation.inputs["preferred_strategy"] == "SEMANTIC"
    assert operation.inputs["guard_required"] is True
    assert operation.inputs["absolute_pixel_is_evidence_only"] is True
    assert operation.inputs["semantic_target"] is not None
    assert operation.inputs["pixel_anchor"] is not None

    plan = MacroGraphPlanner().plan(draft.definition)
    assert plan.instructions[0].payload["adapter_id"] == "desktop.interaction"
    assert ledger.recent() == []


def test_ghostwalk_002_pixel_anchor_is_fallback_without_semantics(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    recorder = GhostWalkRecorder(ledger)
    _start(recorder, "ghost:pixel")

    observation = recorder.record_click(
        session_id="ghost:pixel",
        frame=_frame(),
        x_px=300,
        y_px=200,
        observed_at="2026-09-27T00:51:00+00:00",
    )
    draft = recorder.compile_draft(
        session_id="ghost:pixel",
        macro_id="macro:ghost-pixel",
        macro_version="0.13.0",
    )

    assert (
        observation.preferred_strategy
        is TargetStrategy.WINDOW_RELATIVE_PIXEL
    )
    assert draft.receipt.semantic_preferred_count == 0
    assert draft.receipt.pixel_fallback_count == 1

    step = draft.definition.steps[0]
    assert isinstance(step, DoStep)
    assert step.operation.inputs["preferred_strategy"] == (
        "WINDOW_RELATIVE_PIXEL"
    )
    assert step.operation.inputs["semantic_target"] is None


def test_ghostwalk_003_observation_chain_is_contiguous_and_deterministic(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    recorder = GhostWalkRecorder(ledger)
    _start(recorder, "ghost:chain")

    first = recorder.record_click(
        session_id="ghost:chain",
        frame=_frame(),
        x_px=200,
        y_px=150,
        observed_at="2026-09-27T00:52:00+00:00",
    )
    second = recorder.record_click(
        session_id="ghost:chain",
        frame=_frame(),
        x_px=600,
        y_px=450,
        observed_at="2026-09-27T00:52:01+00:00",
        semantic_target=_semantic(),
    )

    loaded = recorder.observations(session_id="ghost:chain")
    assert [item.sequence for item in loaded] == [0, 1]
    assert first.previous_observation_sha256 is None
    assert second.previous_observation_sha256 == first.observation_sha256
    assert loaded == (first, second)

    one = recorder.compile_draft(
        session_id="ghost:chain",
        macro_id="macro:ghost-chain",
        macro_version="0.13.0",
    )
    two = recorder.compile_draft(
        session_id="ghost:chain",
        macro_id="macro:ghost-chain",
        macro_version="0.13.0",
    )
    assert one.definition.definition_sha256 == two.definition.definition_sha256
    assert one.receipt.receipt_sha256 == two.receipt.receipt_sha256


def test_ghostwalk_004_tampered_observation_fails_closed(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    recorder = GhostWalkRecorder(ledger)
    _start(recorder, "ghost:tamper")
    recorder.record_click(
        session_id="ghost:tamper",
        frame=_frame(),
        x_px=500,
        y_px=350,
        observed_at="2026-09-27T00:53:00+00:00",
    )

    path = tmp_path / "ledger" / "ghostwalk-observations.jsonl"
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    rows[0]["pixel_anchor"]["x_ppm"] = 123
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        GhostWalkContractError,
        match="pixel anchor hash mismatch",
    ):
        GhostWalkRecorder(ledger).observations(
            session_id="ghost:tamper"
        )


def test_ghostwalk_005_duplicate_session_id_is_rejected(
    tmp_path: Path,
) -> None:
    recorder = GhostWalkRecorder(_ledger(tmp_path))
    _start(recorder, "ghost:duplicate")

    with pytest.raises(
        GhostWalkContractError,
        match="session_id already exists",
    ):
        _start(recorder, "ghost:duplicate")


def test_ghostwalk_006_empty_session_cannot_compile(
    tmp_path: Path,
) -> None:
    recorder = GhostWalkRecorder(_ledger(tmp_path))
    _start(recorder, "ghost:empty")

    with pytest.raises(
        GhostWalkContractError,
        match="requires at least one observation",
    ):
        recorder.compile_draft(
            session_id="ghost:empty",
            macro_id="macro:empty",
            macro_version="0.13.0",
        )


def test_ghostwalk_007_negative_desktop_coordinates_are_valid_evidence(
    tmp_path: Path,
) -> None:
    recorder = GhostWalkRecorder(_ledger(tmp_path))
    _start(recorder, "ghost:negative")
    frame = _frame(left=-1200, top=-100, width=1000, height=700)

    observation = recorder.record_click(
        session_id="ghost:negative",
        frame=frame,
        x_px=-700,
        y_px=250,
        observed_at="2026-09-27T00:54:00+00:00",
    )

    assert observation.pixel_anchor.observed_x_px == -700
    assert observation.pixel_anchor.observed_y_px == 250
    assert observation.pixel_anchor.x_ppm == 500_000
    assert observation.pixel_anchor.y_ppm == 500_000


def test_ghostwalk_008_demo_and_draft_remain_zero_authority(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    recorder = GhostWalkRecorder(ledger)
    session = recorder.start(
        session_id="ghost:zero",
        recorder_id="operator:mikey",
        started_at="2026-09-27T00:55:00+00:00",
    )
    observation = recorder.record_click(
        session_id="ghost:zero",
        frame=_frame(),
        x_px=500,
        y_px=350,
        observed_at="2026-09-27T00:55:01+00:00",
    )
    draft = recorder.compile_draft(
        session_id="ghost:zero",
        macro_id="macro:zero",
        macro_version="0.13.0",
    )

    assert session.operational_authority is False
    assert observation.action_authority is False
    assert draft.receipt.execution_authority is False
    assert ledger.recent() == []
