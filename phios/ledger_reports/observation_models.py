from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, kw_only=True)
class ObservationSnapshot:
    snapshot_id: str
    snapshot_path: str
    created_at: str
    kernel_rows: int
    dispatch_rows: int
    reflex_shadow_rows: int
    reflex_calibration_rows: int
    source_digest: str
    promotion_status: str = "not_promoted"
    action_authority: bool = False
    execution_authority: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "snapshot_path": self.snapshot_path,
            "created_at": self.created_at,
            "kernel_rows": self.kernel_rows,
            "dispatch_rows": self.dispatch_rows,
            "reflex_shadow_rows": self.reflex_shadow_rows,
            "reflex_calibration_rows": self.reflex_calibration_rows,
            "source_digest": self.source_digest,
            "promotion_status": self.promotion_status,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }


@dataclass(frozen=True, kw_only=True)
class ObservationReport:
    report_id: str
    report_name: str
    snapshot_id: str
    created_at: str
    rows: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    promotion_status: str = "not_promoted"
    action_authority: bool = False
    execution_authority: bool = False
    report_sha256: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "report_id": self.report_id,
            "report_name": self.report_name,
            "snapshot_id": self.snapshot_id,
            "created_at": self.created_at,
            "rows": [dict(row) for row in self.rows],
            "promotion_status": self.promotion_status,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "report_sha256": self.report_sha256,
        }
