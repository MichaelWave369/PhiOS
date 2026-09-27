from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from phios.macro_ghostwalk_operator_editor import (
    GhostWalkOperatorEditor,
    GhostWalkOperatorEditorError,
)
from phios.macro_operator_log import OperatorLog, OperatorNoteStatus
from phios.spine.ledger import RealityLedger

TARGET = "a" * 64
ACTION = "b" * 64


def _ledger(tmp_path: Path) -> RealityLedger:
    return RealityLedger(tmp_path / "ledger" / "receipts.jsonl")


def _seed(ledger: RealityLedger) -> str:
    path = ledger.path.parent / "transition-inference-receipts.jsonl"
    path.write_text(
        json.dumps(
            {
                "receipt_sha256": TARGET,
                "status": "CANDIDATES",
                "session_id": "demo",
                "action_observation_sha256": ACTION,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    note = OperatorLog(ledger).create(
        note_id=f"ghostwalk-transition:{ACTION}",
        target_sha256=TARGET,
        author_id="operator:local",
        body="Machine-generated candidate summary.",
        created_at="2026-09-27T06:30:00+00:00",
        tags=("ghostwalk", "transition-inference"),
    )
    return note.revision_sha256


def test_editor_reads_current_note_bound_to_inference(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    first_sha = _seed(ledger)
    editor = GhostWalkOperatorEditor(
        ledger=ledger,
        author_id="operator:local",
    )

    view = editor.view(
        target_inference_receipt_sha256=TARGET
    )

    assert view.revision == 1
    assert view.revision_sha256 == first_sha
    assert view.target_inference_receipt_sha256 == TARGET
    assert view.inference_status == "CANDIDATES"
    assert view.action_observation_sha256 == ACTION
    assert view.execution_authority is False


def test_editor_appends_human_correction_without_rewriting_inference(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    first_sha = _seed(ledger)
    editor = GhostWalkOperatorEditor(
        ledger=ledger,
        author_id="operator:mikey",
    )

    outcome = editor.edit(
        target_inference_receipt_sha256=TARGET,
        expected_current_revision_sha256=first_sha,
        body="Correction: I opened network adapter properties.",
        created_at="2026-09-27T06:31:00+00:00",
    )

    assert outcome.note.revision == 2
    assert outcome.note.author_id == "operator:mikey"
    assert "operator-interpretation" in outcome.note.tags
    rows = ledger.operator_log_revisions()
    assert rows[0]["body"] == "Machine-generated candidate summary."
    assert rows[1]["body"].startswith("Correction:")
    inference = ledger.transition_inference_receipt(
        receipt_sha256=TARGET
    )
    assert inference is not None
    assert inference["status"] == "CANDIDATES"


def test_editor_rejects_stale_revision(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    first_sha = _seed(ledger)
    editor = GhostWalkOperatorEditor(
        ledger=ledger,
        author_id="operator:local",
    )
    editor.edit(
        target_inference_receipt_sha256=TARGET,
        expected_current_revision_sha256=first_sha,
        body="First human edit.",
        created_at="2026-09-27T06:31:00+00:00",
    )

    with pytest.raises(
        GhostWalkOperatorEditorError,
        match="revision changed before edit",
    ):
        editor.edit(
            target_inference_receipt_sha256=TARGET,
            expected_current_revision_sha256=first_sha,
            body="Stale competing edit.",
            created_at="2026-09-27T06:32:00+00:00",
        )


def test_editor_retraction_is_append_only(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    first_sha = _seed(ledger)
    editor = GhostWalkOperatorEditor(
        ledger=ledger,
        author_id="operator:local",
    )

    outcome = editor.edit(
        target_inference_receipt_sha256=TARGET,
        expected_current_revision_sha256=first_sha,
        body="Retracted: this interpretation was inaccurate.",
        status=OperatorNoteStatus.RETRACTED,
        created_at="2026-09-27T06:31:00+00:00",
    )

    assert outcome.note.status is OperatorNoteStatus.RETRACTED
    assert len(ledger.operator_log_revisions()) == 2


def test_editor_serializes_competing_expected_revision_edits(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    first_sha = _seed(ledger)
    editor = GhostWalkOperatorEditor(
        ledger=ledger,
        author_id="operator:local",
    )
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def worker(body: str) -> None:
        barrier.wait()
        try:
            result = editor.edit(
                target_inference_receipt_sha256=TARGET,
                expected_current_revision_sha256=first_sha,
                body=body,
                created_at="2026-09-27T06:31:00+00:00",
            )
            outcomes.append(result.result.value)
        except GhostWalkOperatorEditorError:
            outcomes.append("REJECTED")

    first = threading.Thread(target=worker, args=("Edit A",))
    second = threading.Thread(target=worker, args=("Edit B",))
    first.start()
    second.start()
    first.join()
    second.join()

    assert sorted(outcomes) == ["APPLIED", "REJECTED"]
    assert len(ledger.operator_log_revisions()) == 2


def test_editor_rejects_unknown_inference_target(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    editor = GhostWalkOperatorEditor(
        ledger=ledger,
        author_id="operator:local",
    )

    with pytest.raises(
        GhostWalkOperatorEditorError,
        match="inference receipt does not exist",
    ):
        editor.view(
            target_inference_receipt_sha256="f" * 64
        )
