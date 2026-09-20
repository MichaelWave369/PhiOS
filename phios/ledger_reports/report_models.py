from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, kw_only=True)
class ProjectionArtifact:
    projection_id: str
    snapshot_id: str
    projection_path: str
    projection_sha256: str
    duckdb_version: str
    schema_version: str
    created_at: str
    execution_rows: int
    mandala_rows: int
    sandbox_policy_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "projection_id": self.projection_id,
            "snapshot_id": self.snapshot_id,
            "projection_path": self.projection_path,
            "projection_sha256": self.projection_sha256,
            "duckdb_version": self.duckdb_version,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "execution_rows": self.execution_rows,
            "mandala_rows": self.mandala_rows,
            "sandbox_policy_sha256": self.sandbox_policy_sha256,
        }


@dataclass(frozen=True, kw_only=True)
class LedgerReport:
    report_id: str
    report_name: str
    snapshot_id: str
    projection_id: str
    projection_sha256: str
    query_catalog_version: str
    created_at: str
    rows: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    row_count: int = 0
    truncated: bool = False
    promotion_status: str = "not_promoted"
    action_authority: bool = False
    execution_authority: bool = False
    report_sha256: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "report_id": self.report_id,
            "report_name": self.report_name,
            "snapshot_id": self.snapshot_id,
            "projection_id": self.projection_id,
            "projection_sha256": self.projection_sha256,
            "query_catalog_version": self.query_catalog_version,
            "created_at": self.created_at,
            "rows": [dict(row) for row in self.rows],
            "row_count": self.row_count,
            "truncated": self.truncated,
            "promotion_status": self.promotion_status,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "report_sha256": self.report_sha256,
        }
