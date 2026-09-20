import json
from pathlib import Path

import pytest

from phios.analytics import LedgerSnapshotExporter
from phios.mandala import AuthorityContext
from phios.spine.runtime import PhiOSSpine


def _authority(*permissions: str) -> AuthorityContext:
    return AuthorityContext(ceiling=tuple(permissions), grants=tuple(permissions))


def _execution_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "schema_version": "phios.execution_receipt.v0.1",
        "receipt_id": "exec-1",
        "timestamp_utc": "2026-09-20T21:00:00+00:00",
        "capability_id": "commons.text_artifact",
        "planner": "test",
        "input_sha256": "a" * 64,
        "permissions_requested": ["artifact.write"],
        "permission_status": "allowed",
        "execution_status": "succeeded",
        "artifact_path": "/sensitive/path/proof.txt",
        "artifact_sha256": "b" * 64,
        "error": "sensitive error text",
        "packet_id": "packet-1",
        "gate_receipt_id": "gate-1",
        "action_receipt_id": "action-1",
        "mandala_status": "ACCEPTED",
        "governed_provenance": None,
    }
    row.update(overrides)
    return row


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_export_requires_explicit_analytics_permission_before_reading_sources(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "ledger" / "receipts.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text("{ definitely malformed }\n", encoding="utf-8")
    exporter = LedgerSnapshotExporter(state_root=tmp_path)
    with pytest.raises(PermissionError, match="ledger.analytics.export"):
        exporter.export(authority=_authority())


def test_snapshot_projects_safe_fields_and_excludes_binding_claims(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("artifact.write",),
        task_id="snapshot-task",
    )
    receipt = spine.run(
        "commons.text_artifact",
        {"text": "snapshot", "name": "snapshot-proof"},
    )
    assert receipt.execution_status == "succeeded"

    claim_dir = tmp_path / "ledger" / "binding-claims"
    claim_dir.mkdir(parents=True, exist_ok=True)
    (claim_dir / "not-a-receipt.claim").write_text("SECRET_BINDING_STATE\n", encoding="utf-8")

    exporter = LedgerSnapshotExporter(state_root=tmp_path)
    snapshot = exporter.export(authority=_authority("ledger.analytics.export"))
    root = Path(snapshot.snapshot_path)

    execution_rows = [
        json.loads(line)
        for line in (root / "execution.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    mandala_rows = [
        json.loads(line)
        for line in (root / "mandala.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(execution_rows) == 1
    assert len(mandala_rows) == 2
    assert "artifact_path" not in execution_rows[0]
    assert "error" not in execution_rows[0]
    assert execution_rows[0]["artifact_sha256"] == receipt.artifact_sha256
    assert all("authority" not in row for row in mandala_rows)
    assert all("external_identifiers" not in row for row in mandala_rows)
    assert "SECRET_BINDING_STATE" not in (root / "execution.jsonl").read_text(encoding="utf-8")
    assert "SECRET_BINDING_STATE" not in (root / "mandala.jsonl").read_text(encoding="utf-8")

    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["core"]["action_authority"] is False
    assert manifest["core"]["execution_authority"] is False
    assert manifest["core"]["promotion_status"] == "not_promoted"
    assert snapshot.coverage.complete is True


def test_snapshot_id_is_stable_for_same_stream_bytes_policy_and_mapper(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "ledger" / "receipts.jsonl", [_execution_row(
        gate_receipt_id=None,
        action_receipt_id=None,
    )])
    exporter = LedgerSnapshotExporter(state_root=tmp_path)
    a = exporter.export(authority=_authority("ledger.analytics.export"))
    b = exporter.export(authority=_authority("ledger.analytics.export"))
    assert a.snapshot_id == b.snapshot_id
    assert a.snapshot_path == b.snapshot_path


def test_partial_tail_is_excluded_not_interpreted(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger" / "receipts.jsonl"
    ledger.parent.mkdir(parents=True)
    first = json.dumps(
        _execution_row(gate_receipt_id=None, action_receipt_id=None),
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    partial = b'{"schema_version":"phios.execution_receipt.v0.1"'
    ledger.write_bytes(first + partial)

    snapshot = LedgerSnapshotExporter(state_root=tmp_path).export(
        authority=_authority("ledger.analytics.export")
    )
    stream = next(item for item in snapshot.streams if item.stream == "execution")
    assert stream.line_count == 1
    assert stream.captured_bytes == len(first)
    assert stream.partial_tail_bytes == len(partial)


def test_malformed_complete_row_rejects_snapshot(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger" / "receipts.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_bytes(b"{not-json}\n")
    with pytest.raises(ValueError, match="malformed JSON"):
        LedgerSnapshotExporter(state_root=tmp_path).export(
            authority=_authority("ledger.analytics.export")
        )


def test_unknown_execution_schema_rejects_snapshot(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "ledger" / "receipts.jsonl",
        [_execution_row(schema_version="phios.execution_receipt.v999")],
    )
    with pytest.raises(ValueError, match="unknown execution receipt"):
        LedgerSnapshotExporter(state_root=tmp_path).export(
            authority=_authority("ledger.analytics.export")
        )


def test_missing_cross_stream_links_are_flagged_not_invented(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "ledger" / "receipts.jsonl",
        [_execution_row(gate_receipt_id="missing-gate", action_receipt_id="missing-action")],
    )
    snapshot = LedgerSnapshotExporter(state_root=tmp_path).export(
        authority=_authority("ledger.analytics.export")
    )
    assert snapshot.coverage.complete is False
    assert len(snapshot.coverage.missing_execution_links) == 2
