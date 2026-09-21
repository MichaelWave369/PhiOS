import json
from pathlib import Path

import pytest

from phios.ledger_reports import LedgerSnapshotExporter
from phios.mandala import AuthorityContext


def _authority() -> AuthorityContext:
    return AuthorityContext(
        ceiling=("ledger.snapshot.export",),
        grants=("ledger.snapshot.export",),
    )


def _write(path: Path, row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")


def test_gate_authority_and_provenance_are_not_projected(tmp_path: Path) -> None:
    _write(
        tmp_path / "ledger" / "mandala-receipts.jsonl",
        {
            "receipt_id": "gate-1",
            "packet_id": "packet-1",
            "task_id": "task-1",
            "status": "ACCEPTED",
            "produced_by": "test",
            "timestamp_utc": "2026-09-20T21:00:00+00:00",
            "contract_version": "phios.mandala.v0.1",
            "parent_receipt_id": None,
            "receipt_type": "GateReceipt",
            "gate": "ACTION",
            "reason": "allowed",
            "provenance_refs": ["/private/path"],
            "authority": {"ceiling": ["secret"], "grants": ["secret"]},
        },
    )
    snapshot = LedgerSnapshotExporter(state_root=tmp_path).export(authority=_authority())
    row = json.loads(
        (Path(snapshot.snapshot_path) / "mandala.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert row["receipt_type"] == "GateReceipt"
    assert row["reason"] == "allowed"
    assert "authority" not in row
    assert "provenance_refs" not in row


def test_unknown_mandala_receipt_type_rejects_snapshot(tmp_path: Path) -> None:
    _write(
        tmp_path / "ledger" / "mandala-receipts.jsonl",
        {
            "receipt_id": "future-1",
            "packet_id": "packet-1",
            "task_id": "task-1",
            "status": "ACCEPTED",
            "produced_by": "future",
            "timestamp_utc": "2026-09-20T21:00:00+00:00",
            "contract_version": "phios.mandala.v0.1",
            "parent_receipt_id": None,
            "receipt_type": "FutureReceipt",
        },
    )
    with pytest.raises(ValueError, match="unknown Mandala receipt_type"):
        LedgerSnapshotExporter(state_root=tmp_path).export(authority=_authority())


def test_dangling_mandala_parent_is_flagged(tmp_path: Path) -> None:
    _write(
        tmp_path / "ledger" / "mandala-receipts.jsonl",
        {
            "receipt_id": "action-1",
            "packet_id": "packet-1",
            "task_id": "task-1",
            "status": "ACCEPTED",
            "produced_by": "test",
            "timestamp_utc": "2026-09-20T21:00:00+00:00",
            "contract_version": "phios.mandala.v0.1",
            "parent_receipt_id": "missing-gate",
            "receipt_type": "ActionReceipt",
            "approved_grant": ["artifact.write"],
            "side_effect": {"capability_id": "commons.text_artifact"},
            "outcome": "succeeded",
            "external_identifiers": {"artifact_path": "/secret"},
        },
    )
    snapshot = LedgerSnapshotExporter(state_root=tmp_path).export(authority=_authority())
    assert snapshot.coverage.complete is False
    assert snapshot.coverage.dangling_parent_receipts == (
        {
            "receipt_id": "action-1",
            "missing_parent_receipt_id": "missing-gate",
        },
    )


def test_duplicate_json_keys_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "ledger" / "receipts.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"schema_version":"phios.execution_receipt.v0.1",'
        '"schema_version":"phios.execution_receipt.v0.1"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate JSON key"):
        LedgerSnapshotExporter(state_root=tmp_path).export(authority=_authority())



def test_reality_projection_includes_bounded_observability_hashes(
    tmp_path: Path,
) -> None:
    frontier_sha = "a" * 64
    observability_sha = "b" * 64
    _write(
        tmp_path / "ledger" / "mandala-receipts.jsonl",
        {
            "receipt_id": "reality-frontier-1",
            "packet_id": "packet-frontier-1",
            "task_id": "task-frontier-1",
            "status": "ACCEPTED",
            "produced_by": "reality.verifier",
            "timestamp_utc": "2026-09-21T17:30:00+00:00",
            "contract_version": "phios.mandala.v0.1",
            "parent_receipt_id": None,
            "receipt_type": "RealityReceipt",
            "claims_checked": [],
            "evidence_used": [],
            "unresolved_contradictions": [],
            "unresolved_claims": [],
            "verdict_summary": {"SUPPORTED": 1},
            "verification_method": "bounded-evidence-v0.14",
            "promotion_status": "not_promoted",
            "limitations": [],
            "observation_frontier_sha256": frontier_sha,
            "observability_receipt_sha256": observability_sha,
            "observability_status": "BOUNDED",
        },
    )

    snapshot = LedgerSnapshotExporter(state_root=tmp_path).export(
        authority=_authority()
    )
    row = json.loads(
        (Path(snapshot.snapshot_path) / "mandala.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )

    assert row["receipt_type"] == "RealityReceipt"
    assert row["observation_frontier_sha256"] == frontier_sha
    assert row["observability_receipt_sha256"] == observability_sha
    assert row["observability_status"] == "BOUNDED"
    assert "authority" not in row
