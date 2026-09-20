from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from phios.mandala import AuthorityContext

from .mapping import MAPPING_VERSION, project_execution_row, project_mandala_row
from .models import LedgerSnapshot, ProjectedRow, SnapshotCoverage, SnapshotStreamManifest
from .policy import LedgerSnapshotPolicy
from .validation import canonical_json_bytes, sha256_bytes, sha256_json, strict_json_loads

MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_LINE_BYTES = 1024 * 1024
MAX_LINES = 200_000


@dataclass(frozen=True, kw_only=True)
class _CapturedStream:
    manifest: SnapshotStreamManifest
    projected_rows: tuple[ProjectedRow, ...]
    projected_bytes: bytes


class LedgerSnapshotExporter:
    """Export stable, filtered prefixes of the two canonical receipt streams only."""

    def __init__(
        self,
        *,
        state_root: Path,
        output_root: Path | None = None,
        policy: LedgerSnapshotPolicy | None = None,
    ) -> None:
        self.state_root = state_root.expanduser().resolve()
        self.output_root = (
            output_root.expanduser().resolve()
            if output_root is not None
            else self.state_root / "analytics" / "snapshots"
        )
        self.policy = policy or LedgerSnapshotPolicy()

    def export(self, *, authority: AuthorityContext) -> LedgerSnapshot:
        if not self.policy.authorize(authority):
            raise PermissionError("ledger.analytics.export permission is required")

        execution = self._capture(
            stream="execution",
            path=self.state_root / "ledger" / "receipts.jsonl",
            logical_source="ledger/receipts.jsonl",
            projector=project_execution_row,
        )
        mandala = self._capture(
            stream="mandala",
            path=self.state_root / "ledger" / "mandala-receipts.jsonl",
            logical_source="ledger/mandala-receipts.jsonl",
            projector=project_mandala_row,
        )
        coverage = self._coverage(execution.projected_rows, mandala.projected_rows)
        stream_manifests = (execution.manifest, mandala.manifest)
        core = {
            "artifact_kind": "phios.analytics.ledger_snapshot.v0.1",
            "mapping_version": MAPPING_VERSION,
            "policy_sha256": self.policy.policy_sha256,
            "streams": [item.to_dict() for item in stream_manifests],
            "coverage": coverage.to_dict(),
            "promotion_status": "not_promoted",
            "action_authority": False,
            "execution_authority": False,
        }
        snapshot_id = sha256_json(core)
        created_at = datetime.now(UTC).isoformat()
        final_dir = self.output_root / snapshot_id

        manifest = {
            "snapshot_id": snapshot_id,
            "created_at": created_at,
            "core": core,
        }
        effective_created_at = self._publish_snapshot(
            final_dir=final_dir,
            manifest=manifest,
            execution_bytes=execution.projected_bytes,
            mandala_bytes=mandala.projected_bytes,
        )
        return LedgerSnapshot(
            snapshot_id=snapshot_id,
            snapshot_path=str(final_dir),
            created_at=effective_created_at,
            mapping_version=MAPPING_VERSION,
            policy_sha256=self.policy.policy_sha256,
            streams=stream_manifests,
            coverage=coverage,
        )

    def _capture(
        self,
        *,
        stream: str,
        path: Path,
        logical_source: str,
        projector: Callable[..., ProjectedRow],
    ) -> _CapturedStream:
        if stream not in {"execution", "mandala"}:
            raise ValueError("unknown ledger stream")
        captured, identity_sha256, source_size, partial_tail = self._stable_prefix(
            path,
            logical_source=logical_source,
        )
        rows: list[ProjectedRow] = []
        projected_lines: list[bytes] = []
        byte_cursor = 0
        receipt_ids: set[str] = set()

        if captured:
            lines = captured.splitlines(keepends=True)
            if len(lines) > MAX_LINES:
                raise ValueError(f"{logical_source} exceeds maximum complete-line count")
            for index, line in enumerate(lines, start=1):
                if len(line) > MAX_LINE_BYTES:
                    raise ValueError(f"{logical_source} line {index} exceeds maximum row size")
                if not line.endswith(b"\n"):
                    raise ValueError("internal snapshot prefix invariant violated")
                raw_row = line[:-1]
                value = strict_json_loads(raw_row)
                if not isinstance(value, dict):
                    raise ValueError(f"{logical_source} line {index} must be a JSON object")
                row = projector(
                    value,
                    raw_row=raw_row,
                    line_number=index,
                    byte_start=byte_cursor,
                    byte_end=byte_cursor + len(line),
                    policy=self.policy,
                )
                if row.source_receipt_id in receipt_ids:
                    raise ValueError(
                        f"{logical_source} contains duplicate receipt_id "
                        f"{row.source_receipt_id!r}"
                    )
                receipt_ids.add(row.source_receipt_id)
                rows.append(row)
                projected_lines.append(canonical_json_bytes(row.to_dict()) + b"\n")
                byte_cursor += len(line)

        projected_bytes = b"".join(projected_lines)
        manifest = SnapshotStreamManifest(
            stream=stream,  # type: ignore[arg-type]
            logical_source=logical_source,
            source_identity_sha256=identity_sha256,
            source_size_at_capture=source_size,
            captured_bytes=len(captured),
            partial_tail_bytes=partial_tail,
            line_count=len(rows),
            captured_sha256=sha256_bytes(captured),
            projection_sha256=sha256_bytes(projected_bytes),
        )
        return _CapturedStream(
            manifest=manifest,
            projected_rows=tuple(rows),
            projected_bytes=projected_bytes,
        )

    def _stable_prefix(
        self,
        path: Path,
        *,
        logical_source: str,
    ) -> tuple[bytes, str, int, int]:
        if path.is_symlink():
            raise ValueError(f"{logical_source} must not be a symlink")
        if not path.exists():
            identity = sha256_json({"logical_source": logical_source, "state": "absent"})
            return b"", identity, 0, 0

        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags)
        try:
            with os.fdopen(fd, "rb", closefd=False) as handle:
                before = os.fstat(handle.fileno())
                if not stat.S_ISREG(before.st_mode):
                    raise ValueError(f"{logical_source} is not a regular file")
                if before.st_size > MAX_SOURCE_BYTES:
                    raise ValueError(f"{logical_source} exceeds maximum source size")
                source_size = int(before.st_size)
                raw = handle.read(source_size)
                after = os.fstat(handle.fileno())
                if len(raw) != source_size:
                    raise RuntimeError(f"{logical_source} changed during capture")
                if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                    raise RuntimeError(f"{logical_source} identity changed during capture")
                if after.st_size < source_size:
                    raise RuntimeError(f"{logical_source} shrank during capture")
        finally:
            try:
                os.close(fd)
            except OSError:
                pass

        identity_sha256 = sha256_json(
            {
                "logical_source": logical_source,
                "device": int(before.st_dev),
                "inode": int(before.st_ino),
            }
        )
        complete_end = raw.rfind(b"\n") + 1
        captured = raw[:complete_end]
        partial_tail = source_size - complete_end
        return captured, identity_sha256, source_size, partial_tail

    @staticmethod
    def _coverage(
        execution_rows: tuple[ProjectedRow, ...],
        mandala_rows: tuple[ProjectedRow, ...],
    ) -> SnapshotCoverage:
        mandala_ids = {row.source_receipt_id for row in mandala_rows}
        missing_execution_links: list[dict[str, str]] = []
        for row in execution_rows:
            receipt_id = row.source_receipt_id
            for field in ("gate_receipt_id", "action_receipt_id"):
                linked = row.payload.get(field)
                if isinstance(linked, str) and linked and linked not in mandala_ids:
                    missing_execution_links.append(
                        {
                            "execution_receipt_id": receipt_id,
                            "field": field,
                            "missing_receipt_id": linked,
                        }
                    )

        dangling_parents: list[dict[str, str]] = []
        for row in mandala_rows:
            parent = row.payload.get("parent_receipt_id")
            if isinstance(parent, str) and parent and parent not in mandala_ids:
                dangling_parents.append(
                    {
                        "receipt_id": row.source_receipt_id,
                        "missing_parent_receipt_id": parent,
                    }
                )

        return SnapshotCoverage(
            execution_rows=len(execution_rows),
            mandala_rows=len(mandala_rows),
            missing_execution_links=tuple(missing_execution_links),
            dangling_parent_receipts=tuple(dangling_parents),
        )

    def _publish_snapshot(
        self,
        *,
        final_dir: Path,
        manifest: dict[str, Any],
        execution_bytes: bytes,
        mandala_bytes: bytes,
    ) -> str:
        self.output_root.mkdir(parents=True, exist_ok=True)
        if final_dir.exists():
            return self._validate_existing_snapshot(final_dir, manifest)

        temp_dir = Path(
            tempfile.mkdtemp(prefix=".snapshot-", dir=str(self.output_root))
        )
        try:
            self._write_fsync(temp_dir / "execution.jsonl", execution_bytes)
            self._write_fsync(temp_dir / "mandala.jsonl", mandala_bytes)
            self._write_fsync(
                temp_dir / "manifest.json",
                json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False).encode("utf-8")
                + b"\n",
            )
            try:
                temp_dir.rename(final_dir)
            except FileExistsError:
                return self._validate_existing_snapshot(final_dir, manifest)
            return str(manifest["created_at"])
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

    @staticmethod
    def _write_fsync(path: Path, data: bytes) -> None:
        with path.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _validate_existing_snapshot(
        final_dir: Path,
        expected_manifest: dict[str, Any],
    ) -> str:
        manifest_path = final_dir / "manifest.json"
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise RuntimeError("existing snapshot directory is incomplete or corrupt") from exc
        if not isinstance(existing, dict):
            raise RuntimeError("existing snapshot manifest is invalid")
        if existing.get("snapshot_id") != expected_manifest.get("snapshot_id"):
            raise RuntimeError("existing snapshot ID mismatch")
        if existing.get("core") != expected_manifest.get("core"):
            raise RuntimeError("existing snapshot core mismatch")
        core = existing.get("core")
        if not isinstance(core, dict):
            raise RuntimeError("existing snapshot core is invalid")
        if sha256_json(core) != existing.get("snapshot_id"):
            raise RuntimeError("existing snapshot manifest hash mismatch")
        streams = core.get("streams")
        if not isinstance(streams, list):
            raise RuntimeError("existing snapshot stream manifest is invalid")
        projection_files = {
            "execution": final_dir / "execution.jsonl",
            "mandala": final_dir / "mandala.jsonl",
        }
        for stream in streams:
            if not isinstance(stream, dict):
                raise RuntimeError("existing snapshot stream entry is invalid")
            name = stream.get("stream")
            expected_hash = stream.get("projection_sha256")
            if name not in projection_files or not isinstance(expected_hash, str):
                raise RuntimeError("existing snapshot stream metadata is invalid")
            try:
                actual_hash = sha256_bytes(projection_files[name].read_bytes())
            except FileNotFoundError as exc:
                raise RuntimeError("existing snapshot projection is missing") from exc
            if actual_hash != expected_hash:
                raise RuntimeError("existing snapshot projection hash mismatch")
        created_at = existing.get("created_at")
        if not isinstance(created_at, str) or not created_at:
            raise RuntimeError("existing snapshot created_at is invalid")
        return created_at
