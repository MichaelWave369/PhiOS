from pathlib import Path

import pytest

from phios.ledger_reports import LedgerReportService
from phios.mandala import AuthorityContext


def _authority(*permissions: str) -> AuthorityContext:
    return AuthorityContext(ceiling=tuple(permissions), grants=tuple(permissions))


def test_projection_build_denies_before_backend_or_snapshot_access(tmp_path: Path) -> None:
    service = LedgerReportService(state_root=tmp_path)
    with pytest.raises(PermissionError, match="ledger.report.build"):
        service.build_projection(
            snapshot_id="0" * 64,
            authority=_authority(),
        )


def test_report_read_denies_before_projection_access(tmp_path: Path) -> None:
    service = LedgerReportService(state_root=tmp_path)
    with pytest.raises(PermissionError, match="ledger.report.read"):
        service.run_report(
            snapshot_id="0" * 64,
            report_name="coverage_v1",
            authority=_authority(),
        )


def test_arbitrary_report_name_is_rejected_before_backend_use(tmp_path: Path) -> None:
    service = LedgerReportService(state_root=tmp_path)
    with pytest.raises(ValueError, match="unknown Ledger report name"):
        service.run_report(
            snapshot_id="0" * 64,
            report_name="SELECT * FROM secrets",
            authority=_authority("ledger.report.read"),
        )


def test_report_limit_is_bounded_before_backend_use(tmp_path: Path) -> None:
    service = LedgerReportService(state_root=tmp_path)
    with pytest.raises(ValueError, match="limit must be between"):
        service.run_report(
            snapshot_id="0" * 64,
            report_name="coverage_v1",
            authority=_authority("ledger.report.read"),
            limit=1001,
        )
