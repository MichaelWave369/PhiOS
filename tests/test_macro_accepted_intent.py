from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from phios.macro_accepted_intent import (
    GhostWalkAcceptedIntentError,
    GhostWalkAcceptedIntentRegistry,
    GhostWalkAcceptedIntentStatus,
    GhostWalkIntentFamily,
)
from phios.macro_operator_log import OperatorLog
from phios.spine.ledger import RealityLedger

ACTION = "b" * 64
_INFERENCE_BODY = {
    "status": "CANDIDATES",
    "session_id": "demo",
    "action_observation_sha256": ACTION,
}
TARGET = hashlib.sha256(
    json.dumps(
        _INFERENCE_BODY,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
).hexdigest()


def _ledger(tmp_path: Path) -> RealityLedger:
    return RealityLedger(tmp_path / "ledger" / "receipts.jsonl")


def _seed(ledger: RealityLedger) -> str:
    ledger.path.parent.mkdir(parents=True, exist_ok=True)
    inference_path = (
        ledger.path.parent / "transition-inference-receipts.jsonl"
    )
    inference_path.write_text(
        json.dumps(
            {
                **_INFERENCE_BODY,
                "receipt_sha256": TARGET,
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
        body="Correction: opened network adapter properties.",
        created_at="2026-09-27T06:50:00+00:00",
        tags=(
            "ghostwalk",
            "operator-interpretation",
            "transition-inference",
        ),
    )
    return note.revision_sha256


def test_accepts_typed_intent_bound_to_current_operator_note(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    note_sha = _seed(ledger)
    registry = GhostWalkAcceptedIntentRegistry(
        ledger=ledger,
        accepted_by="operator:local",
    )

    item = registry.accept(
        target_inference_receipt_sha256=TARGET,
        source_operator_note_revision_sha256=note_sha,
        intent_family=GhostWalkIntentFamily.OPEN,
        intent_code="OPEN_NETWORK_ADAPTER_PROPERTIES",
        expected_current_revision_sha256=None,
        accepted_at="2026-09-27T06:51:00+00:00",
    )

    assert item.revision == 1
    assert item.status is GhostWalkAcceptedIntentStatus.ACTIVE
    assert item.human_intent_confirmed is True
    assert item.causation_proven is False
    assert item.policy_authority is False
    assert item.execution_authority is False


def test_intent_code_must_match_typed_family(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    note_sha = _seed(ledger)
    registry = GhostWalkAcceptedIntentRegistry(
        ledger=ledger,
        accepted_by="operator:local",
    )

    with pytest.raises(
        GhostWalkAcceptedIntentError,
        match="must start with OPEN_",
    ):
        registry.accept(
            target_inference_receipt_sha256=TARGET,
            source_operator_note_revision_sha256=note_sha,
            intent_family=GhostWalkIntentFamily.OPEN,
            intent_code="TOGGLE_NETWORK_ADAPTER_PROPERTIES",
            expected_current_revision_sha256=None,
        )


def test_acceptance_requires_exact_current_operator_note(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    note_sha = _seed(ledger)
    current = OperatorLog(ledger).current(
        note_id=f"ghostwalk-transition:{ACTION}"
    )
    OperatorLog(ledger).edit(
        note_id=current.note_id,
        expected_current_revision_sha256=note_sha,
        author_id="operator:local",
        body="Newer correction.",
        created_at="2026-09-27T06:51:00+00:00",
        tags=current.tags,
    )
    registry = GhostWalkAcceptedIntentRegistry(
        ledger=ledger,
        accepted_by="operator:local",
    )

    with pytest.raises(
        GhostWalkAcceptedIntentError,
        match="operator note revision changed",
    ):
        registry.accept(
            target_inference_receipt_sha256=TARGET,
            source_operator_note_revision_sha256=note_sha,
            intent_family=GhostWalkIntentFamily.OPEN,
            intent_code="OPEN_NETWORK_ADAPTER_PROPERTIES",
            expected_current_revision_sha256=None,
        )


def test_retracted_operator_note_cannot_seed_acceptance(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    note_sha = _seed(ledger)
    current = OperatorLog(ledger).current(
        note_id=f"ghostwalk-transition:{ACTION}"
    )
    from phios.macro_operator_log import OperatorNoteStatus

    retracted = OperatorLog(ledger).edit(
        note_id=current.note_id,
        expected_current_revision_sha256=note_sha,
        author_id="operator:local",
        body="Retracted.",
        created_at="2026-09-27T06:51:00+00:00",
        tags=current.tags,
        status=OperatorNoteStatus.RETRACTED,
    )
    registry = GhostWalkAcceptedIntentRegistry(
        ledger=ledger,
        accepted_by="operator:local",
    )

    with pytest.raises(
        GhostWalkAcceptedIntentError,
        match="ACTIVE operator note",
    ):
        registry.accept(
            target_inference_receipt_sha256=TARGET,
            source_operator_note_revision_sha256=(
                retracted.revision_sha256
            ),
            intent_family=GhostWalkIntentFamily.OPEN,
            intent_code="OPEN_NETWORK_ADAPTER_PROPERTIES",
            expected_current_revision_sha256=None,
        )


def test_reclassification_is_append_only_and_concurrency_guarded(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    note_sha = _seed(ledger)
    registry = GhostWalkAcceptedIntentRegistry(
        ledger=ledger,
        accepted_by="operator:local",
    )
    first = registry.accept(
        target_inference_receipt_sha256=TARGET,
        source_operator_note_revision_sha256=note_sha,
        intent_family=GhostWalkIntentFamily.OPEN,
        intent_code="OPEN_NETWORK_ADAPTER_PROPERTIES",
        expected_current_revision_sha256=None,
        accepted_at="2026-09-27T06:51:00+00:00",
    )
    second = registry.accept(
        target_inference_receipt_sha256=TARGET,
        source_operator_note_revision_sha256=note_sha,
        intent_family=GhostWalkIntentFamily.NAVIGATE,
        intent_code="NAVIGATE_NETWORK_ADAPTER_PROPERTIES",
        expected_current_revision_sha256=first.revision_sha256,
        accepted_at="2026-09-27T06:52:00+00:00",
    )

    assert second.revision == 2
    assert second.supersedes_revision_sha256 == first.revision_sha256
    rows = ledger.ghostwalk_accepted_intent_revisions(
        target_inference_receipt_sha256=TARGET
    )
    assert len(rows) == 2

    with pytest.raises(
        GhostWalkAcceptedIntentError,
        match="revision changed before update",
    ):
        registry.accept(
            target_inference_receipt_sha256=TARGET,
            source_operator_note_revision_sha256=note_sha,
            intent_family=GhostWalkIntentFamily.OPEN,
            intent_code="OPEN_NETWORK_SETTINGS",
            expected_current_revision_sha256=first.revision_sha256,
        )


def test_revoke_appends_without_erasing_accepted_intent(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    note_sha = _seed(ledger)
    registry = GhostWalkAcceptedIntentRegistry(
        ledger=ledger,
        accepted_by="operator:local",
    )
    first = registry.accept(
        target_inference_receipt_sha256=TARGET,
        source_operator_note_revision_sha256=note_sha,
        intent_family=GhostWalkIntentFamily.OPEN,
        intent_code="OPEN_NETWORK_ADAPTER_PROPERTIES",
        expected_current_revision_sha256=None,
    )

    revoked = registry.revoke(
        target_inference_receipt_sha256=TARGET,
        expected_current_revision_sha256=first.revision_sha256,
    )

    assert revoked.status is GhostWalkAcceptedIntentStatus.REVOKED
    assert revoked.revision == 2
    assert len(
        ledger.ghostwalk_accepted_intent_revisions(
            target_inference_receipt_sha256=TARGET
        )
    ) == 2


def test_tampered_accepted_intent_chain_fails_closed(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    note_sha = _seed(ledger)
    registry = GhostWalkAcceptedIntentRegistry(
        ledger=ledger,
        accepted_by="operator:local",
    )
    registry.accept(
        target_inference_receipt_sha256=TARGET,
        source_operator_note_revision_sha256=note_sha,
        intent_family=GhostWalkIntentFamily.OPEN,
        intent_code="OPEN_NETWORK_ADAPTER_PROPERTIES",
        expected_current_revision_sha256=None,
    )

    path = ledger.path.parent / "ghostwalk-accepted-intent-revisions.jsonl"
    row = json.loads(path.read_text(encoding="utf-8"))
    row["intent_code"] = "OPEN_TAMPERED"
    path.write_text(
        json.dumps(row, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        GhostWalkAcceptedIntentError,
        match="revision hash mismatch",
    ):
        registry.current(
            target_inference_receipt_sha256=TARGET
        )


def test_tampered_source_operator_note_invalidates_accepted_intent(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    note_sha = _seed(ledger)
    registry = GhostWalkAcceptedIntentRegistry(
        ledger=ledger,
        accepted_by="operator:local",
    )
    registry.accept(
        target_inference_receipt_sha256=TARGET,
        source_operator_note_revision_sha256=note_sha,
        intent_family=GhostWalkIntentFamily.OPEN,
        intent_code="OPEN_NETWORK_ADAPTER_PROPERTIES",
        expected_current_revision_sha256=None,
    )

    path = ledger.path.parent / "operator-log-revisions.jsonl"
    row = json.loads(path.read_text(encoding="utf-8"))
    row["body"] = "Tampered human interpretation."
    path.write_text(
        json.dumps(row, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        GhostWalkAcceptedIntentError,
        match="source OperatorLog revision is invalid",
    ):
        registry.current(
            target_inference_receipt_sha256=TARGET
        )
