from __future__ import annotations

import json
from pathlib import Path

import pytest

from phios.macro_operator_log import (
    OperatorLog,
    OperatorLogContractError,
    OperatorNoteStatus,
)
from phios.spine.ledger import RealityLedger

TARGET = "a" * 64


def _ledger(tmp_path: Path) -> RealityLedger:
    return RealityLedger(tmp_path / "ledger" / "receipts.jsonl")


def test_operator_log_001_create_and_read_current(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    log = OperatorLog(ledger)

    created = log.create(
        note_id="note:1",
        target_sha256=TARGET,
        author_id="operator:mikey",
        body="Popup interrupted cycle 46.",
        created_at="2026-09-27T00:30:00+00:00",
        tags=("interference",),
    )

    current = log.current(note_id="note:1")
    assert current == created
    assert current.revision == 1
    assert current.operational_authority is False
    assert current.action_authority is False
    assert current.execution_authority is False


def test_operator_log_002_edit_appends_revision_without_rewriting(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    log = OperatorLog(ledger)
    first = log.create(
        note_id="note:edit",
        target_sha256=TARGET,
        author_id="operator:mikey",
        body="Popup was Chrome.",
        created_at="2026-09-27T00:30:00+00:00",
    )

    second = log.edit(
        note_id="note:edit",
        expected_current_revision_sha256=first.revision_sha256,
        author_id="operator:mikey",
        body="Correction: popup was NVIDIA.",
        created_at="2026-09-27T00:31:00+00:00",
        tags=("correction", "interference"),
    )

    rows = ledger.operator_log_revisions(note_id="note:edit")
    assert len(rows) == 2
    assert rows[0]["body"] == "Popup was Chrome."
    assert rows[1]["body"] == "Correction: popup was NVIDIA."
    assert second.revision == 2
    assert second.supersedes_revision_sha256 == first.revision_sha256
    assert log.current(note_id="note:edit") == second


def test_operator_log_003_stale_edit_is_rejected(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    log = OperatorLog(ledger)
    first = log.create(
        note_id="note:stale",
        target_sha256=TARGET,
        author_id="operator:a",
        body="Initial.",
        created_at="2026-09-27T00:30:00+00:00",
    )
    second = log.edit(
        note_id="note:stale",
        expected_current_revision_sha256=first.revision_sha256,
        author_id="operator:b",
        body="Second.",
        created_at="2026-09-27T00:31:00+00:00",
    )

    with pytest.raises(
        OperatorLogContractError,
        match="revision changed before edit",
    ):
        log.edit(
            note_id="note:stale",
            expected_current_revision_sha256=first.revision_sha256,
            author_id="operator:a",
            body="Conflicting third.",
            created_at="2026-09-27T00:32:00+00:00",
        )
    assert log.current(note_id="note:stale") == second


def test_operator_log_004_retraction_is_a_revision(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    log = OperatorLog(ledger)
    first = log.create(
        note_id="note:retract",
        target_sha256=TARGET,
        author_id="operator:mikey",
        body="Bad note.",
        created_at="2026-09-27T00:30:00+00:00",
    )
    retracted = log.edit(
        note_id="note:retract",
        expected_current_revision_sha256=first.revision_sha256,
        author_id="operator:mikey",
        body="Retracted: inaccurate note.",
        created_at="2026-09-27T00:31:00+00:00",
        status=OperatorNoteStatus.RETRACTED,
    )

    assert retracted.status is OperatorNoteStatus.RETRACTED
    assert len(ledger.operator_log_revisions(note_id="note:retract")) == 2


def test_operator_log_005_tampered_revision_fails_closed(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    log = OperatorLog(ledger)
    log.create(
        note_id="note:tamper",
        target_sha256=TARGET,
        author_id="operator:mikey",
        body="Original.",
        created_at="2026-09-27T00:30:00+00:00",
    )

    path = tmp_path / "ledger" / "operator-log-revisions.jsonl"
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    rows[0]["body"] = "Changed behind the ledger."
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        OperatorLogContractError,
        match="revision hash mismatch",
    ):
        OperatorLog(ledger).current(note_id="note:tamper")
