from __future__ import annotations

import json
from typing import Any

PROJECTION_SCHEMA_VERSION = "phios.ledger_projection.v0.1"
DUCKDB_VERSION = "1.5.5"

EXECUTION_COLUMNS = (
    "receipt_id",
    "timestamp_utc",
    "capability_id",
    "planner",
    "input_sha256",
    "permissions_requested_json",
    "permission_status",
    "execution_status",
    "artifact_sha256",
    "packet_id",
    "gate_receipt_id",
    "action_receipt_id",
    "mandala_status",
    "governed_provenance_json",
    "source_line",
    "source_byte_start",
    "source_byte_end",
    "source_row_sha256",
)

MANDALA_COLUMNS = (
    "contract_version",
    "receipt_type",
    "receipt_id",
    "packet_id",
    "task_id",
    "status",
    "produced_by",
    "timestamp_utc",
    "parent_receipt_id",
    "gate",
    "reason",
    "route_mode",
    "fallback_count",
    "acuity_status",
    "media_type",
    "acquisition_method",
    "acquisition_status",
    "capture_attempts",
    "recovery_step_count",
    "engine",
    "engine_version",
    "language",
    "page_segmentation_mode",
    "character_count",
    "token_count",
    "confidence_count",
    "interpretation_status",
    "verdict_summary_json",
    "verification_method",
    "promotion_status",
    "outcome",
    "capability_id",
    "approved_grant_json",
    "operation",
    "canonical_status",
    "index_status",
    "error_code",
    "action_authority",
    "execution_authority",
    "index_generation",
    "durability_reason",
    "conflict_result",
    "terminal_reason_present",
    "source_line",
    "source_byte_start",
    "source_byte_end",
    "source_row_sha256",
)

EXECUTION_CREATE_SQL = """
CREATE TABLE execution_receipts (
    receipt_id VARCHAR PRIMARY KEY,
    timestamp_utc VARCHAR NOT NULL,
    capability_id VARCHAR NOT NULL,
    planner VARCHAR NOT NULL,
    input_sha256 VARCHAR NOT NULL,
    permissions_requested_json VARCHAR NOT NULL,
    permission_status VARCHAR NOT NULL,
    execution_status VARCHAR NOT NULL,
    artifact_sha256 VARCHAR,
    packet_id VARCHAR,
    gate_receipt_id VARCHAR,
    action_receipt_id VARCHAR,
    mandala_status VARCHAR,
    governed_provenance_json VARCHAR,
    source_line BIGINT NOT NULL,
    source_byte_start BIGINT NOT NULL,
    source_byte_end BIGINT NOT NULL,
    source_row_sha256 VARCHAR NOT NULL
)
"""

MANDALA_CREATE_SQL = """
CREATE TABLE mandala_receipts (
    contract_version VARCHAR NOT NULL,
    receipt_type VARCHAR NOT NULL,
    receipt_id VARCHAR PRIMARY KEY,
    packet_id VARCHAR NOT NULL,
    task_id VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    produced_by VARCHAR NOT NULL,
    timestamp_utc VARCHAR NOT NULL,
    parent_receipt_id VARCHAR,
    gate VARCHAR,
    reason VARCHAR,
    route_mode VARCHAR,
    fallback_count BIGINT,
    acuity_status VARCHAR,
    media_type VARCHAR,
    acquisition_method VARCHAR,
    acquisition_status VARCHAR,
    capture_attempts BIGINT,
    recovery_step_count BIGINT,
    engine VARCHAR,
    engine_version VARCHAR,
    language VARCHAR,
    page_segmentation_mode BIGINT,
    character_count BIGINT,
    token_count BIGINT,
    confidence_count BIGINT,
    interpretation_status VARCHAR,
    verdict_summary_json VARCHAR,
    verification_method VARCHAR,
    promotion_status VARCHAR,
    outcome VARCHAR,
    capability_id VARCHAR,
    approved_grant_json VARCHAR,
    operation VARCHAR,
    canonical_status VARCHAR,
    index_status VARCHAR,
    error_code VARCHAR,
    action_authority BOOLEAN,
    execution_authority BOOLEAN,
    index_generation VARCHAR,
    durability_reason VARCHAR,
    conflict_result VARCHAR,
    terminal_reason_present BOOLEAN,
    source_line BIGINT NOT NULL,
    source_byte_start BIGINT NOT NULL,
    source_byte_end BIGINT NOT NULL,
    source_row_sha256 VARCHAR NOT NULL
)
"""

METADATA_CREATE_SQL = """
CREATE TABLE projection_metadata (
    snapshot_id VARCHAR PRIMARY KEY,
    execution_rows BIGINT NOT NULL,
    mandala_rows BIGINT NOT NULL,
    coverage_complete BOOLEAN NOT NULL,
    missing_execution_links BIGINT NOT NULL,
    dangling_parent_receipts BIGINT NOT NULL
)
"""


def normalize_execution_row(row: dict[str, Any]) -> dict[str, Any]:
    source = _source(row)
    permissions = row.get("permissions_requested")
    if not isinstance(permissions, list) or any(not isinstance(item, str) for item in permissions):
        raise ValueError("execution permissions_requested is invalid")
    provenance = row.get("governed_provenance")
    if provenance is not None and not isinstance(provenance, dict):
        raise ValueError("execution governed_provenance is invalid")
    return {
        "receipt_id": _required_str(row, "receipt_id"),
        "timestamp_utc": _required_str(row, "timestamp_utc"),
        "capability_id": _required_str(row, "capability_id"),
        "planner": _required_str(row, "planner"),
        "input_sha256": _required_str(row, "input_sha256"),
        "permissions_requested_json": _json_text(permissions),
        "permission_status": _required_str(row, "permission_status"),
        "execution_status": _required_str(row, "execution_status"),
        "artifact_sha256": _optional_str(row, "artifact_sha256"),
        "packet_id": _optional_str(row, "packet_id"),
        "gate_receipt_id": _optional_str(row, "gate_receipt_id"),
        "action_receipt_id": _optional_str(row, "action_receipt_id"),
        "mandala_status": _optional_str(row, "mandala_status"),
        "governed_provenance_json": _json_text(provenance) if provenance is not None else None,
        **source,
    }


def normalize_mandala_row(row: dict[str, Any]) -> dict[str, Any]:
    source = _source(row)
    verdict = row.get("verdict_summary")
    grants = row.get("approved_grant")
    if verdict is not None and not isinstance(verdict, dict):
        raise ValueError("Mandala verdict_summary is invalid")
    if grants is not None and (
        not isinstance(grants, list) or any(not isinstance(item, str) for item in grants)
    ):
        raise ValueError("Mandala approved_grant is invalid")
    return {
        "contract_version": _required_str(row, "contract_version"),
        "receipt_type": _required_str(row, "receipt_type"),
        "receipt_id": _required_str(row, "receipt_id"),
        "packet_id": _required_str(row, "packet_id"),
        "task_id": _required_str(row, "task_id"),
        "status": _required_str(row, "status"),
        "produced_by": _required_str(row, "produced_by"),
        "timestamp_utc": _required_str(row, "timestamp_utc"),
        "parent_receipt_id": _optional_str(row, "parent_receipt_id"),
        "gate": _optional_str(row, "gate"),
        "reason": _optional_str(row, "reason"),
        "route_mode": _optional_str(row, "route_mode"),
        "fallback_count": _optional_int(row, "fallback_count"),
        "acuity_status": _optional_str(row, "acuity_status"),
        "media_type": _optional_str(row, "media_type"),
        "acquisition_method": _optional_str(row, "acquisition_method"),
        "acquisition_status": _optional_str(row, "acquisition_status"),
        "capture_attempts": _optional_int(row, "capture_attempts"),
        "recovery_step_count": _optional_int(row, "recovery_step_count"),
        "engine": _optional_str(row, "engine"),
        "engine_version": _optional_str(row, "engine_version"),
        "language": _optional_str(row, "language"),
        "page_segmentation_mode": _optional_int(row, "page_segmentation_mode"),
        "character_count": _optional_int(row, "character_count"),
        "token_count": _optional_int(row, "token_count"),
        "confidence_count": _optional_int(row, "confidence_count"),
        "interpretation_status": _optional_str(row, "interpretation_status"),
        "verdict_summary_json": _json_text(verdict) if verdict is not None else None,
        "verification_method": _optional_str(row, "verification_method"),
        "promotion_status": _optional_str(row, "promotion_status"),
        "outcome": _optional_str(row, "outcome"),
        "capability_id": _optional_str(row, "capability_id"),
        "approved_grant_json": _json_text(grants) if grants is not None else None,
        "operation": _optional_str(row, "operation"),
        "canonical_status": _optional_str(row, "canonical_status"),
        "index_status": _optional_str(row, "index_status"),
        "error_code": _optional_str(row, "error_code"),
        "action_authority": _optional_bool(row, "action_authority"),
        "execution_authority": _optional_bool(row, "execution_authority"),
        "index_generation": _optional_str(row, "index_generation"),
        "durability_reason": _optional_str(row, "durability_reason"),
        "conflict_result": _optional_str(row, "conflict_result"),
        "terminal_reason_present": _optional_bool(row, "terminal_reason_present"),
        **source,
    }


def _source(row: dict[str, Any]) -> dict[str, int | str]:
    source = row.get("_source")
    if not isinstance(source, dict):
        raise ValueError("projected row has no source metadata")
    return {
        "source_line": _required_int(source, "line"),
        "source_byte_start": _required_int(source, "byte_start"),
        "source_byte_end": _required_int(source, "byte_end"),
        "source_row_sha256": _required_str(source, "row_sha256"),
    }


def _required_str(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_str(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string or null")
    return value


def _required_int(row: dict[str, Any], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return value


def _optional_int(row: dict[str, Any], key: str) -> int | None:
    value = row.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer or null")
    return value


def _optional_bool(row: dict[str, Any], key: str) -> bool | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean or null")
    return value


def _json_text(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
