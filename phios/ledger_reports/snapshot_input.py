from __future__ import annotations

import json
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .mapping import MAPPING_VERSION
from .validation import sha256_bytes, sha256_json, strict_json_loads

_SNAPSHOT_ID_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_PROJECTED_BYTES = 64 * 1024 * 1024
_MAX_PROJECTED_ROWS = 200_000


@dataclass(frozen=True, kw_only=True)
class ValidatedSnapshot:
    snapshot_id: str
    snapshot_path: Path
    core: dict[str, Any]
    execution_rows: tuple[dict[str, Any], ...]
    mandala_rows: tuple[dict[str, Any], ...]
    coverage_complete: bool
    missing_execution_links: int
    dangling_parent_receipts: int


def load_validated_snapshot(*, state_root: Path, snapshot_id: str) -> ValidatedSnapshot:
    if not _SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        raise ValueError("snapshot_id must be a lowercase SHA-256 hex digest")
    root = state_root.expanduser().resolve()
    snapshot_path = root / "derived" / "ledger-snapshots" / snapshot_id
    if snapshot_path.is_symlink():
        raise ValueError("snapshot directory must not be a symlink")
    try:
        resolved = snapshot_path.resolve(strict=True)
    except OSError as exc:
        raise ValueError("snapshot does not exist") from exc
    expected_parent = (root / "derived" / "ledger-snapshots").resolve()
    try:
        resolved.relative_to(expected_parent)
    except ValueError as exc:
        raise ValueError("snapshot path escaped the derived snapshot root") from exc

    manifest = _load_object(resolved / "manifest.json", label="snapshot manifest")
    if manifest.get("snapshot_id") != snapshot_id:
        raise ValueError("snapshot manifest ID mismatch")
    core = manifest.get("core")
    if not isinstance(core, dict):
        raise ValueError("snapshot core must be an object")
    if sha256_json(core) != snapshot_id:
        raise ValueError("snapshot core hash does not match snapshot_id")
    if core.get("artifact_kind") != "phios.ledger_snapshot.v0.1":
        raise ValueError("unsupported snapshot artifact kind")
    if core.get("mapping_version") != MAPPING_VERSION:
        raise ValueError("unsupported snapshot mapping version")
    if core.get("promotion_status") != "not_promoted":
        raise ValueError("snapshot promotion status is invalid")
    if core.get("action_authority") is not False or core.get("execution_authority") is not False:
        raise ValueError("snapshot carries forbidden authority")

    stream_entries = core.get("streams")
    if not isinstance(stream_entries, list) or len(stream_entries) != 2:
        raise ValueError("snapshot must declare exactly two streams")
    streams: dict[str, dict[str, Any]] = {}
    for item in stream_entries:
        if not isinstance(item, dict):
            raise ValueError("snapshot stream manifest must be an object")
        name = item.get("stream")
        if name not in {"execution", "mandala"} or name in streams:
            raise ValueError("snapshot stream manifest names are invalid")
        streams[str(name)] = item

    execution_rows = _load_projection(
        resolved / "execution.jsonl",
        expected_sha256=_required_digest(streams["execution"], "projection_sha256"),
        expected_rows=_required_nonnegative_int(streams["execution"], "line_count"),
        label="execution projection",
    )
    mandala_rows = _load_projection(
        resolved / "mandala.jsonl",
        expected_sha256=_required_digest(streams["mandala"], "projection_sha256"),
        expected_rows=_required_nonnegative_int(streams["mandala"], "line_count"),
        label="Mandala projection",
    )
    for row in execution_rows:
        _validate_source_metadata(row, label="execution row")
        if row.get("schema_version") != "phios.execution_receipt.v0.1":
            raise ValueError("execution projection contains an unsupported schema")
    for row in mandala_rows:
        _validate_source_metadata(row, label="Mandala row")
        if row.get("contract_version") != "phios.mandala.v0.1":
            raise ValueError("Mandala projection contains an unsupported contract")

    coverage = core.get("coverage")
    if not isinstance(coverage, dict):
        raise ValueError("snapshot coverage must be an object")
    coverage_complete = coverage.get("complete")
    if not isinstance(coverage_complete, bool):
        raise ValueError("snapshot coverage complete must be boolean")
    if _required_nonnegative_int(coverage, "execution_rows") != len(execution_rows):
        raise ValueError("snapshot execution row count mismatch")
    if _required_nonnegative_int(coverage, "mandala_rows") != len(mandala_rows):
        raise ValueError("snapshot Mandala row count mismatch")
    missing = coverage.get("missing_execution_links")
    dangling = coverage.get("dangling_parent_receipts")
    if not isinstance(missing, list) or not isinstance(dangling, list):
        raise ValueError("snapshot coverage link lists are invalid")

    return ValidatedSnapshot(
        snapshot_id=snapshot_id,
        snapshot_path=resolved,
        core=core,
        execution_rows=execution_rows,
        mandala_rows=mandala_rows,
        coverage_complete=coverage_complete,
        missing_execution_links=len(missing),
        dangling_parent_receipts=len(dangling),
    )


def _load_object(path: Path, *, label: str) -> dict[str, Any]:
    raw = _read_bounded_regular_file(path, label=label)
    value = strict_json_loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _load_projection(
    path: Path,
    *,
    expected_sha256: str,
    expected_rows: int,
    label: str,
) -> tuple[dict[str, Any], ...]:
    raw = _read_bounded_regular_file(path, label=label)
    if sha256_bytes(raw) != expected_sha256:
        raise ValueError(f"{label} hash mismatch")
    lines = raw.splitlines()
    if len(lines) > _MAX_PROJECTED_ROWS or len(lines) != expected_rows:
        raise ValueError(f"{label} row count mismatch")
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        value = strict_json_loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{label} line {index} must be an object")
        rows.append(value)
    return tuple(rows)


def _read_bounded_regular_file(path: Path, *, label: str) -> bytes:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    try:
        metadata = path.stat()
    except OSError as exc:
        raise ValueError(f"{label} is unavailable") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{label} must be a regular file")
    if metadata.st_size > _MAX_PROJECTED_BYTES:
        raise ValueError(f"{label} exceeds size limit")
    return path.read_bytes()


def _validate_source_metadata(row: dict[str, Any], *, label: str) -> None:
    source = row.get("_source")
    if not isinstance(source, dict):
        raise ValueError(f"{label} has no source metadata")
    receipt_id = source.get("receipt_id")
    row_hash = source.get("row_sha256")
    line = source.get("line")
    byte_start = source.get("byte_start")
    byte_end = source.get("byte_end")
    if not isinstance(receipt_id, str) or not receipt_id:
        raise ValueError(f"{label} source receipt_id is invalid")
    if row.get("receipt_id") != receipt_id:
        raise ValueError(f"{label} source receipt_id mismatch")
    if not isinstance(row_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", row_hash):
        raise ValueError(f"{label} source row hash is invalid")
    for field, value in (("line", line), ("byte_start", byte_start), ("byte_end", byte_end)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{label} source {field} is invalid")


def _required_digest(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{key} must be a SHA-256 digest")
    return value


def _required_nonnegative_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return value
