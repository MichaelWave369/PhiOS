from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


StreamName = Literal["execution", "mandala"]


@dataclass(frozen=True, kw_only=True)
class SnapshotStreamManifest:
    stream: StreamName
    logical_source: str
    source_identity_sha256: str
    source_size_at_capture: int
    captured_bytes: int
    partial_tail_bytes: int
    line_count: int
    captured_sha256: str
    projection_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "stream": self.stream,
            "logical_source": self.logical_source,
            "source_identity_sha256": self.source_identity_sha256,
            "source_size_at_capture": self.source_size_at_capture,
            "captured_bytes": self.captured_bytes,
            "partial_tail_bytes": self.partial_tail_bytes,
            "line_count": self.line_count,
            "captured_sha256": self.captured_sha256,
            "projection_sha256": self.projection_sha256,
        }


@dataclass(frozen=True, kw_only=True)
class SnapshotCoverage:
    execution_rows: int
    mandala_rows: int
    missing_execution_links: tuple[dict[str, str], ...] = field(default_factory=tuple)
    dangling_parent_receipts: tuple[dict[str, str], ...] = field(default_factory=tuple)

    @property
    def complete(self) -> bool:
        return not self.missing_execution_links and not self.dangling_parent_receipts

    def to_dict(self) -> dict[str, object]:
        return {
            "execution_rows": self.execution_rows,
            "mandala_rows": self.mandala_rows,
            "complete": self.complete,
            "missing_execution_links": [dict(item) for item in self.missing_execution_links],
            "dangling_parent_receipts": [dict(item) for item in self.dangling_parent_receipts],
        }


@dataclass(frozen=True, kw_only=True)
class LedgerSnapshot:
    snapshot_id: str
    snapshot_path: str
    created_at: str
    mapping_version: str
    policy_sha256: str
    streams: tuple[SnapshotStreamManifest, ...]
    coverage: SnapshotCoverage

    def to_dict(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "snapshot_path": self.snapshot_path,
            "created_at": self.created_at,
            "mapping_version": self.mapping_version,
            "policy_sha256": self.policy_sha256,
            "streams": [item.to_dict() for item in self.streams],
            "coverage": self.coverage.to_dict(),
        }


@dataclass(frozen=True, kw_only=True)
class ProjectedRow:
    payload: dict[str, Any]
    source_receipt_id: str
    source_line: int
    source_byte_start: int
    source_byte_end: int
    source_row_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.payload,
            "_source": {
                "receipt_id": self.source_receipt_id,
                "line": self.source_line,
                "byte_start": self.source_byte_start,
                "byte_end": self.source_byte_end,
                "row_sha256": self.source_row_sha256,
            },
        }
