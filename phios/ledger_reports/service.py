from __future__ import annotations

import importlib.metadata
import os
import re
import shutil
import stat
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from phios.mandala import AuthorityContext

from .projection_schema import (
    DUCKDB_VERSION,
    PROJECTION_SCHEMA_VERSION,
    normalize_execution_row,
    normalize_mandala_row,
)
from .queries import MAX_REPORT_ROWS, QUERY_CATALOG_VERSION, get_named_query
from .report_models import LedgerReport, ProjectionArtifact
from .runner import LedgerWorkerRunner
from .snapshot_input import load_validated_snapshot
from .validation import canonical_json_bytes, sha256_bytes, sha256_json, strict_json_loads

_PROJECTION_KIND = "phios.ledger_projection.v0.1"
_REPORT_KIND = "phios.ledger_report.v0.1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_PROJECTION_BYTES = 256 * 1024 * 1024
_MAX_RESULT_BYTES = 8 * 1024 * 1024


class LedgerReportService:
    def __init__(
        self,
        *,
        state_root: Path,
        runner: LedgerWorkerRunner | None = None,
    ) -> None:
        self.state_root = state_root.expanduser().resolve()
        self.runner = runner or LedgerWorkerRunner()

    def build_projection(
        self,
        *,
        snapshot_id: str,
        authority: AuthorityContext,
    ) -> ProjectionArtifact:
        if not authority.allows("ledger.report.build"):
            raise PermissionError("ledger.report.build permission is required")
        self._require_backend_version()

        snapshot = load_validated_snapshot(
            state_root=self.state_root,
            snapshot_id=snapshot_id,
        )
        projection_id = self._projection_id(snapshot_id)
        final_dir = (
            self.state_root
            / "derived"
            / "ledger-projections"
            / snapshot_id
            / projection_id
        )
        if final_dir.exists():
            return self._load_projection(final_dir, snapshot_id, projection_id)

        execution_rows = [
            normalize_execution_row(row) for row in snapshot.execution_rows
        ]
        mandala_rows = [
            normalize_mandala_row(row) for row in snapshot.mandala_rows
        ]
        request = {
            "operation": "build",
            "projection_schema_version": PROJECTION_SCHEMA_VERSION,
            "snapshot_id": snapshot_id,
            "execution_rows": execution_rows,
            "mandala_rows": mandala_rows,
            "coverage": {
                "complete": snapshot.coverage_complete,
                "missing_execution_links": snapshot.missing_execution_links,
                "dangling_parent_receipts": snapshot.dangling_parent_receipts,
            },
        }

        parent = final_dir.parent
        parent.mkdir(parents=True, exist_ok=True)
        workspace: Path | None = Path(
            tempfile.mkdtemp(prefix=".projection-", dir=str(parent))
        )
        try:
            assert workspace is not None
            self._write_json(workspace / "request.json", request)
            worker_run = self.runner.run_build(workspace)
            database = workspace / "projection.duckdb"
            projection_sha256 = self._hash_regular_file(
                database,
                label="worker projection",
            )
            created_at = datetime.now(UTC).isoformat()
            manifest = {
                "artifact_kind": _PROJECTION_KIND,
                "projection_id": projection_id,
                "snapshot_id": snapshot_id,
                "projection_sha256": projection_sha256,
                "duckdb_version": DUCKDB_VERSION,
                "schema_version": PROJECTION_SCHEMA_VERSION,
                "created_at": created_at,
                "execution_rows": len(execution_rows),
                "mandala_rows": len(mandala_rows),
                "sandbox_policy_sha256": worker_run.sandbox_policy_sha256,
                "sandbox_backend": worker_run.backend_identity.to_dict(),
                "promotion_status": "not_promoted",
                "action_authority": False,
                "execution_authority": False,
            }
            (workspace / "request.json").unlink(missing_ok=True)
            self._write_json(workspace / "manifest.json", manifest)
            try:
                workspace.rename(final_dir)
            except FileExistsError:
                return self._load_projection(final_dir, snapshot_id, projection_id)
            workspace = None
            return ProjectionArtifact(
                projection_id=projection_id,
                snapshot_id=snapshot_id,
                projection_path=str(final_dir / "projection.duckdb"),
                projection_sha256=projection_sha256,
                duckdb_version=DUCKDB_VERSION,
                schema_version=PROJECTION_SCHEMA_VERSION,
                created_at=created_at,
                execution_rows=len(execution_rows),
                mandala_rows=len(mandala_rows),
                sandbox_policy_sha256=worker_run.sandbox_policy_sha256,
            )
        finally:
            if workspace is not None and workspace.exists():
                shutil.rmtree(workspace)

    def run_report(
        self,
        *,
        snapshot_id: str,
        report_name: str,
        authority: AuthorityContext,
        limit: int = 100,
    ) -> LedgerReport:
        if not authority.allows("ledger.report.read"):
            raise PermissionError("ledger.report.read permission is required")
        get_named_query(report_name)
        if isinstance(limit, bool) or not isinstance(limit, int) or not (1 <= limit <= MAX_REPORT_ROWS):
            raise ValueError(f"limit must be between 1 and {MAX_REPORT_ROWS}")
        self._require_backend_version()

        projection_id = self._projection_id(snapshot_id)
        projection_dir = (
            self.state_root
            / "derived"
            / "ledger-projections"
            / snapshot_id
            / projection_id
        )
        projection = self._load_projection(
            projection_dir,
            snapshot_id,
            projection_id,
        )

        work_root = self.state_root / "derived" / "ledger-worker"
        work_root.mkdir(parents=True, exist_ok=True)
        workspace = Path(tempfile.mkdtemp(prefix=".query-", dir=str(work_root)))
        try:
            source_database = Path(projection.projection_path)
            worker_database = workspace / "projection.duckdb"
            shutil.copyfile(source_database, worker_database)
            if (
                self._hash_regular_file(worker_database, label="worker projection copy")
                != projection.projection_sha256
            ):
                raise RuntimeError("worker projection copy hash mismatch")

            request = {
                "operation": "query",
                "query_catalog_version": QUERY_CATALOG_VERSION,
                "report_name": report_name,
                "limit": limit,
            }
            self._write_json(workspace / "request.json", request)
            self.runner.run_query(workspace)
            result = self._load_worker_result(workspace / "result.json", report_name, limit)
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

        core = {
            "artifact_kind": _REPORT_KIND,
            "report_name": report_name,
            "snapshot_id": snapshot_id,
            "projection_id": projection.projection_id,
            "projection_sha256": projection.projection_sha256,
            "query_catalog_version": QUERY_CATALOG_VERSION,
            "limit": limit,
            "rows": result["rows"],
            "row_count": result["row_count"],
            "truncated": result["truncated"],
            "promotion_status": "not_promoted",
            "action_authority": False,
            "execution_authority": False,
        }
        report_id = sha256_json(core)
        created_at = self._publish_report(report_id, core)
        return LedgerReport(
            report_id=report_id,
            report_name=report_name,
            snapshot_id=snapshot_id,
            projection_id=projection.projection_id,
            projection_sha256=projection.projection_sha256,
            query_catalog_version=QUERY_CATALOG_VERSION,
            created_at=created_at,
            rows=tuple(dict(row) for row in result["rows"]),
            row_count=int(result["row_count"]),
            truncated=bool(result["truncated"]),
            report_sha256=report_id,
        )

    def _projection_id(self, snapshot_id: str) -> str:
        if not _SHA256_RE.fullmatch(snapshot_id):
            raise ValueError("snapshot_id must be a lowercase SHA-256 hex digest")
        return sha256_json(
            {
                "artifact_kind": _PROJECTION_KIND,
                "snapshot_id": snapshot_id,
                "duckdb_version": DUCKDB_VERSION,
                "schema_version": PROJECTION_SCHEMA_VERSION,
            }
        )

    def _load_projection(
        self,
        directory: Path,
        snapshot_id: str,
        projection_id: str,
    ) -> ProjectionArtifact:
        if directory.is_symlink():
            raise RuntimeError("projection directory must not be a symlink")
        try:
            resolved = directory.resolve(strict=True)
        except OSError as exc:
            raise RuntimeError("validated Ledger projection is unavailable") from exc
        manifest = self._load_json_object(
            resolved / "manifest.json",
            max_bytes=1024 * 1024,
            label="projection manifest",
        )
        required = {
            "artifact_kind",
            "projection_id",
            "snapshot_id",
            "projection_sha256",
            "duckdb_version",
            "schema_version",
            "created_at",
            "execution_rows",
            "mandala_rows",
            "sandbox_policy_sha256",
            "sandbox_backend",
            "promotion_status",
            "action_authority",
            "execution_authority",
        }
        if set(manifest) != required:
            raise RuntimeError("projection manifest fields are invalid")
        if manifest["artifact_kind"] != _PROJECTION_KIND:
            raise RuntimeError("projection artifact kind mismatch")
        if manifest["projection_id"] != projection_id or manifest["snapshot_id"] != snapshot_id:
            raise RuntimeError("projection identity mismatch")
        if manifest["duckdb_version"] != DUCKDB_VERSION:
            raise RuntimeError("projection DuckDB version mismatch")
        if manifest["schema_version"] != PROJECTION_SCHEMA_VERSION:
            raise RuntimeError("projection schema version mismatch")
        if not isinstance(manifest["sandbox_backend"], dict):
            raise RuntimeError("projection sandbox backend identity is invalid")
        if manifest["promotion_status"] != "not_promoted":
            raise RuntimeError("projection promotion status is invalid")
        if manifest["action_authority"] is not False or manifest["execution_authority"] is not False:
            raise RuntimeError("projection carries forbidden authority")

        database = resolved / "projection.duckdb"
        projection_sha256 = self._hash_regular_file(database, label="projection database")
        if projection_sha256 != manifest["projection_sha256"]:
            raise RuntimeError("projection database hash mismatch")
        for field in ("execution_rows", "mandala_rows"):
            value = manifest[field]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RuntimeError(f"projection {field} is invalid")
        policy_sha = manifest["sandbox_policy_sha256"]
        if not isinstance(policy_sha, str) or not _SHA256_RE.fullmatch(policy_sha):
            raise RuntimeError("projection sandbox policy hash is invalid")
        created_at = manifest["created_at"]
        if not isinstance(created_at, str) or not created_at:
            raise RuntimeError("projection created_at is invalid")
        return ProjectionArtifact(
            projection_id=projection_id,
            snapshot_id=snapshot_id,
            projection_path=str(database),
            projection_sha256=projection_sha256,
            duckdb_version=DUCKDB_VERSION,
            schema_version=PROJECTION_SCHEMA_VERSION,
            created_at=created_at,
            execution_rows=int(manifest["execution_rows"]),
            mandala_rows=int(manifest["mandala_rows"]),
            sandbox_policy_sha256=policy_sha,
        )

    def _load_worker_result(
        self,
        path: Path,
        report_name: str,
        limit: int,
    ) -> dict[str, Any]:
        result = self._load_json_object(
            path,
            max_bytes=_MAX_RESULT_BYTES,
            label="worker report result",
        )
        expected = {
            "query_catalog_version",
            "report_name",
            "limit",
            "rows",
            "row_count",
            "truncated",
        }
        if set(result) != expected:
            raise RuntimeError("worker report result fields are invalid")
        if result["query_catalog_version"] != QUERY_CATALOG_VERSION:
            raise RuntimeError("worker query catalog version mismatch")
        if result["report_name"] != report_name or result["limit"] != limit:
            raise RuntimeError("worker report request identity mismatch")
        rows = result["rows"]
        if not isinstance(rows, list) or len(rows) > limit:
            raise RuntimeError("worker report rows are invalid")
        if any(not isinstance(row, dict) for row in rows):
            raise RuntimeError("worker report row must be an object")
        row_count = result["row_count"]
        if isinstance(row_count, bool) or not isinstance(row_count, int) or row_count != len(rows):
            raise RuntimeError("worker report row_count mismatch")
        if not isinstance(result["truncated"], bool):
            raise RuntimeError("worker report truncated flag is invalid")
        return result

    def _publish_report(self, report_id: str, core: dict[str, Any]) -> str:
        root = self.state_root / "derived" / "ledger-reports"
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{report_id}.json"
        if path.exists():
            existing = self._load_json_object(path, max_bytes=_MAX_RESULT_BYTES, label="report")
            if (
                existing.get("report_id") != report_id
                or existing.get("report_sha256") != report_id
                or existing.get("core") != core
            ):
                raise RuntimeError("existing report artifact mismatch")
            created_at = existing.get("created_at")
            if not isinstance(created_at, str) or not created_at:
                raise RuntimeError("existing report created_at is invalid")
            return created_at

        created_at = datetime.now(UTC).isoformat()
        payload = {
            "report_id": report_id,
            "report_sha256": report_id,
            "created_at": created_at,
            "core": core,
        }
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        self._write_json(temporary, payload)
        try:
            temporary.replace(path)
        except OSError:
            temporary.unlink(missing_ok=True)
            if path.exists():
                return self._publish_report(report_id, core)
            raise
        return created_at

    @staticmethod
    def _require_backend_version() -> None:
        try:
            installed = importlib.metadata.version("duckdb")
        except importlib.metadata.PackageNotFoundError as exc:
            raise RuntimeError("DuckDB report backend is not installed") from exc
        if installed != DUCKDB_VERSION:
            raise RuntimeError(
                f"DuckDB version mismatch: expected {DUCKDB_VERSION}, found {installed}"
            )

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        data = canonical_json_bytes(value) + b"\n"
        with path.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _load_json_object(path: Path, *, max_bytes: int, label: str) -> dict[str, Any]:
        if path.is_symlink():
            raise RuntimeError(f"{label} must not be a symlink")
        try:
            metadata = path.stat()
        except OSError as exc:
            raise RuntimeError(f"{label} is unavailable") from exc
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > max_bytes:
            raise RuntimeError(f"{label} is invalid or too large")
        value = strict_json_loads(path.read_bytes())
        if not isinstance(value, dict):
            raise RuntimeError(f"{label} must be an object")
        return value

    @staticmethod
    def _hash_regular_file(path: Path, *, label: str) -> str:
        if path.is_symlink():
            raise RuntimeError(f"{label} must not be a symlink")
        try:
            metadata = path.stat()
        except OSError as exc:
            raise RuntimeError(f"{label} is unavailable") from exc
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError(f"{label} must be a regular file")
        if metadata.st_size > _MAX_PROJECTION_BYTES:
            raise RuntimeError(f"{label} exceeds size limit")
        return sha256_bytes(path.read_bytes())
