import json
from pathlib import Path

import pytest

from phios.ledger_reports import LedgerReportService, LedgerSnapshotExporter
from phios.ledger_reports.worker import _connect
from phios.mandala import AuthorityContext
from phios.spine.runtime import PhiOSSpine


def _authority(*permissions: str) -> AuthorityContext:
    return AuthorityContext(ceiling=tuple(permissions), grants=tuple(permissions))


def _snapshot(tmp_path: Path) -> tuple[Path, str]:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=("artifact.write",),
        task_id="report-test",
    )
    succeeded = spine.run(
        "commons.text_artifact",
        {"text": "one", "name": "one"},
    )
    assert succeeded.execution_status == "succeeded"

    denied_spine = PhiOSSpine(state_root=tmp_path, task_id="report-denied")
    denied = denied_spine.run(
        "commons.text_artifact",
        {"text": "two", "name": "two"},
    )
    assert denied.permission_status == "denied"

    snapshot = LedgerSnapshotExporter(state_root=tmp_path).export(
        authority=_authority("ledger.snapshot.export")
    )
    return tmp_path, snapshot.snapshot_id


def test_real_worker_builds_projection_and_named_reports(tmp_path: Path) -> None:
    state_root, snapshot_id = _snapshot(tmp_path)
    service = LedgerReportService(state_root=state_root)

    projection = service.build_projection(
        snapshot_id=snapshot_id,
        authority=_authority("ledger.report.build"),
    )
    assert Path(projection.projection_path).is_file()
    assert projection.duckdb_version == "1.5.5"
    assert projection.execution_rows == 2

    outcomes = service.run_report(
        snapshot_id=snapshot_id,
        report_name="execution_outcomes_v1",
        authority=_authority("ledger.report.read"),
    )
    assert outcomes.action_authority is False
    assert outcomes.execution_authority is False
    assert outcomes.promotion_status == "not_promoted"
    assert outcomes.row_count == 2
    statuses = {
        (row["permission_status"], row["execution_status"])
        for row in outcomes.rows
    }
    assert statuses == {("allowed", "succeeded"), ("denied", "not_executed")}

    denials = service.run_report(
        snapshot_id=snapshot_id,
        report_name="permission_denials_v1",
        authority=_authority("ledger.report.read"),
    )
    assert denials.row_count == 1
    assert denials.rows[0]["denial_count"] == 1

    coverage = service.run_report(
        snapshot_id=snapshot_id,
        report_name="coverage_v1",
        authority=_authority("ledger.report.read"),
    )
    assert coverage.row_count == 1
    assert coverage.rows[0]["snapshot_id"] == snapshot_id
    assert coverage.rows[0]["coverage_complete"] is True


def test_projection_database_tamper_is_detected_before_query(tmp_path: Path) -> None:
    state_root, snapshot_id = _snapshot(tmp_path)
    service = LedgerReportService(state_root=state_root)
    projection = service.build_projection(
        snapshot_id=snapshot_id,
        authority=_authority("ledger.report.build"),
    )
    path = Path(projection.projection_path)
    with path.open("ab") as handle:
        handle.write(b"tamper")

    with pytest.raises(RuntimeError, match="hash mismatch"):
        service.run_report(
            snapshot_id=snapshot_id,
            report_name="coverage_v1",
            authority=_authority("ledger.report.read"),
        )


def test_configured_duckdb_denies_external_access_and_config_upgrade(tmp_path: Path) -> None:
    database = tmp_path / "security.duckdb"
    connection = _connect(database, read_only=False)
    try:
        connection.execute("CREATE TABLE safe(value INTEGER)")
        with pytest.raises(Exception):
            connection.execute("SELECT * FROM read_csv_auto('/etc/passwd')")
        with pytest.raises(Exception):
            connection.execute("INSTALL httpfs")
        with pytest.raises(Exception):
            connection.execute("SET enable_external_access = true")
        with pytest.raises(Exception):
            connection.execute("SET threads = 4")
    finally:
        connection.close()


def test_read_only_connection_refuses_projection_mutation(tmp_path: Path) -> None:
    database = tmp_path / "readonly.duckdb"
    writable = _connect(database, read_only=False)
    try:
        writable.execute("CREATE TABLE evidence(value INTEGER)")
        writable.execute("INSERT INTO evidence VALUES (1)")
        writable.execute("CHECKPOINT")
    finally:
        writable.close()

    readonly = _connect(database, read_only=True)
    try:
        assert readonly.execute("SELECT value FROM evidence").fetchone()[0] == 1
        with pytest.raises(Exception):
            readonly.execute("INSERT INTO evidence VALUES (2)")
    finally:
        readonly.close()


def test_report_artifact_contains_no_authority_escalation_fields(tmp_path: Path) -> None:
    state_root, snapshot_id = _snapshot(tmp_path)
    service = LedgerReportService(state_root=state_root)
    service.build_projection(
        snapshot_id=snapshot_id,
        authority=_authority("ledger.report.build"),
    )
    report = service.run_report(
        snapshot_id=snapshot_id,
        report_name="coverage_v1",
        authority=_authority("ledger.report.read"),
    )
    path = state_root / "derived" / "ledger-reports" / f"{report.report_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    core = payload["core"]
    assert core["promotion_status"] == "not_promoted"
    assert core["action_authority"] is False
    assert core["execution_authority"] is False
