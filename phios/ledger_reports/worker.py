from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
from typing import Any

from .projection_schema import (
    EXECUTION_COLUMNS,
    EXECUTION_CREATE_SQL,
    MANDALA_COLUMNS,
    MANDALA_CREATE_SQL,
    METADATA_CREATE_SQL,
    PROJECTION_SCHEMA_VERSION,
)
from .queries import MAX_REPORT_ROWS, QUERY_CATALOG_VERSION, get_named_query
from .validation import strict_json_loads

DUCKDB_VERSION = "1.5.5"


def _duckdb() -> Any:
    try:
        import duckdb  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("DuckDB report backend is not installed") from exc
    installed = importlib.metadata.version("duckdb")
    if installed != DUCKDB_VERSION:
        raise RuntimeError(
            f"DuckDB version mismatch: expected {DUCKDB_VERSION}, found {installed}"
        )
    return duckdb


def _connect(database: Path, *, read_only: bool) -> Any:
    duckdb = _duckdb()
    connection = duckdb.connect(
        database=str(database),
        read_only=read_only,
        config={
            "enable_external_access": "false",
            "autoinstall_known_extensions": "false",
            "autoload_known_extensions": "false",
            "allow_community_extensions": "false",
            "allow_unsigned_extensions": "false",
            "allow_persistent_secrets": "false",
            "enable_global_s3_configuration": "false",
            "enable_logging": "false",
            "threads": "1",
            "memory_limit": "512MB",
            "max_temp_directory_size": "64MB",
        },
    )
    connection.execute("SET lock_configuration = true")
    return connection


def build_projection(request_path: Path, output_path: Path) -> None:
    request = _load_request(request_path)
    expected = {
        "operation",
        "projection_schema_version",
        "snapshot_id",
        "execution_rows",
        "mandala_rows",
        "coverage",
    }
    if set(request) != expected or request.get("operation") != "build":
        raise ValueError("invalid projection build request")
    if request.get("projection_schema_version") != PROJECTION_SCHEMA_VERSION:
        raise ValueError("unsupported projection schema version")
    snapshot_id = _required_str(request, "snapshot_id")
    execution_rows = _rows(request.get("execution_rows"), EXECUTION_COLUMNS, "execution_rows")
    mandala_rows = _rows(request.get("mandala_rows"), MANDALA_COLUMNS, "mandala_rows")
    coverage = request.get("coverage")
    if not isinstance(coverage, dict):
        raise ValueError("coverage must be an object")
    coverage_complete = coverage.get("complete")
    missing = coverage.get("missing_execution_links")
    dangling = coverage.get("dangling_parent_receipts")
    if not isinstance(coverage_complete, bool):
        raise ValueError("coverage.complete must be boolean")
    for label, value in (
        ("coverage.missing_execution_links", missing),
        ("coverage.dangling_parent_receipts", dangling),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{label} must be a non-negative integer")

    if output_path.exists():
        raise ValueError("projection output already exists")
    connection = _connect(output_path, read_only=False)
    try:
        connection.execute(EXECUTION_CREATE_SQL)
        connection.execute(MANDALA_CREATE_SQL)
        connection.execute(METADATA_CREATE_SQL)
        if execution_rows:
            marks = ",".join("?" for _ in EXECUTION_COLUMNS)
            connection.executemany(
                f"INSERT INTO execution_receipts VALUES ({marks})",
                [[row[column] for column in EXECUTION_COLUMNS] for row in execution_rows],
            )
        if mandala_rows:
            marks = ",".join("?" for _ in MANDALA_COLUMNS)
            connection.executemany(
                f"INSERT INTO mandala_receipts VALUES ({marks})",
                [[row[column] for column in MANDALA_COLUMNS] for row in mandala_rows],
            )
        connection.execute(
            "INSERT INTO projection_metadata VALUES (?, ?, ?, ?, ?, ?)",
            [
                snapshot_id,
                len(execution_rows),
                len(mandala_rows),
                coverage_complete,
                missing,
                dangling,
            ],
        )
        connection.execute("CHECKPOINT")
    finally:
        connection.close()


def run_query(request_path: Path, database_path: Path, output_path: Path) -> None:
    request = _load_request(request_path)
    expected = {"operation", "query_catalog_version", "report_name", "limit"}
    if set(request) != expected or request.get("operation") != "query":
        raise ValueError("invalid report query request")
    if request.get("query_catalog_version") != QUERY_CATALOG_VERSION:
        raise ValueError("unsupported query catalog version")
    report_name = _required_str(request, "report_name")
    query = get_named_query(report_name)
    limit = request.get("limit")
    if isinstance(limit, bool) or not isinstance(limit, int) or not (1 <= limit <= MAX_REPORT_ROWS):
        raise ValueError(f"limit must be between 1 and {MAX_REPORT_ROWS}")

    connection = _connect(database_path, read_only=True)
    try:
        cursor = connection.execute(query.sql, [limit])
        columns = [item[0] for item in cursor.description]
        values = cursor.fetchall()
    finally:
        connection.close()

    rows: list[dict[str, Any]] = []
    for record in values:
        rows.append({column: value for column, value in zip(columns, record)})
    output = {
        "query_catalog_version": QUERY_CATALOG_VERSION,
        "report_name": report_name,
        "limit": limit,
        "rows": rows,
        "row_count": len(rows),
        "truncated": len(rows) >= limit,
    }
    output_path.write_text(
        json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _load_request(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) > 128 * 1024 * 1024:
        raise ValueError("worker request exceeds size limit")
    value = strict_json_loads(raw)
    if not isinstance(value, dict):
        raise ValueError("worker request must be an object")
    return value


def _rows(value: Any, columns: tuple[str, ...], label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 200_000:
        raise ValueError(f"{label} must be a bounded array")
    rows: list[dict[str, Any]] = []
    expected = set(columns)
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != expected:
            raise ValueError(f"{label}[{index}] has invalid columns")
        rows.append(item)
    return rows


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="phios-ledger-worker")
    sub = parser.add_subparsers(dest="operation", required=True)

    build = sub.add_parser("build")
    build.add_argument("--request", required=True)
    build.add_argument("--output", required=True)

    query = sub.add_parser("query")
    query.add_argument("--request", required=True)
    query.add_argument("--database", required=True)
    query.add_argument("--output", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.operation == "build":
        build_projection(Path(args.request), Path(args.output))
        return 0
    if args.operation == "query":
        run_query(Path(args.request), Path(args.database), Path(args.output))
        return 0
    raise RuntimeError("unknown worker operation")


if __name__ == "__main__":
    raise SystemExit(main())
