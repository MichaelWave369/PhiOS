"""PhiOS Elastic R6: offline audit of separate, self-reported R5 sessions.

Zero host control, no automatic collection, no software/driver changes, and no
claim of independent observations or a real-world performance improvement.
"""

from __future__ import annotations

import argparse
import hmac
import json
import math
import os
import re
import stat
import statistics
import sys
from pathlib import Path
from typing import Any, Sequence

from phios.elastic_residency_r5 import (
    MAX_FILE_BYTES, PROTOCOL, SCHEMA as R5_SCHEMA, _hash_json,
)
from phios.elastic_trace import TraceError, convert_trace

SCHEMA = "phios.elastic.session-review.v1"
MIN_SESSIONS = 3
MAX_SESSIONS = 12
MAX_RECEIPT_BYTES = 256 * 1024
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_R5_KEYS = {
    "schema_version", "status", "study", "scope", "source_filename_recorded",
    "file_bytes", "windows", "window_bytes", "per_arm_selected_bytes",
    "baseline_whole_file_bytes_per_run", "candidate_selected_bytes_per_run",
    "trace", "comparison", "improvement_proven", "action_authority",
    "execution_authority", "hardware_control", "receipt_sha256",
}


class SessionAuditError(ValueError):
    """Malformed receipts, failed integrity, or incomparable sessions."""


def _object(value: object, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise SessionAuditError(f"invalid {label} fields")
    return value


def _integer(value: object, label: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise SessionAuditError(f"invalid {label}")
    return value


def _digest(value: object) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise SessionAuditError("invalid receipt digest")
    return value


def _validated(receipt: object) -> dict[str, Any]:
    report = _object(receipt, _R5_KEYS, "R5 receipt")
    if report["schema_version"] != R5_SCHEMA or report["status"] != "REVIEW_REQUIRED":
        raise SessionAuditError("R5 session not eligible for comparison")
    if (report["study"] != "eager_full_file_vs_read_only_mmap_sparse_windows" or
            report["scope"] != "operator_local_unverified_warm_cache"):
        raise SessionAuditError("unexpected R5 experiment scope")
    for field in ("source_filename_recorded", "improvement_proven",
                  "action_authority", "execution_authority", "hardware_control"):
        if report[field] is not False:
            raise SessionAuditError("R5 receipt asserts unsupported authority or provenance")

    file_bytes = _integer(report["file_bytes"], "file bytes", 1, MAX_FILE_BYTES)
    windows = _integer(report["windows"], "windows", 2, 64)
    window_bytes = _integer(report["window_bytes"], "window bytes", 1, 65536)
    selected = windows * window_bytes
    if (selected > file_bytes or
            report["per_arm_selected_bytes"] != selected or
            report["baseline_whole_file_bytes_per_run"] != file_bytes or
            report["candidate_selected_bytes_per_run"] != selected or
            any(type(report[key]) is not int for key in (
                "per_arm_selected_bytes", "baseline_whole_file_bytes_per_run",
                "candidate_selected_bytes_per_run",
            ))):
        raise SessionAuditError("inconsistent declared R5 file/window quantities")

    receipt_hash = _digest(report["receipt_sha256"])
    unsealed = {key: value for key, value in report.items() if key != "receipt_sha256"}
    if not hmac.compare_digest(receipt_hash, _hash_json(unsealed)):
        raise SessionAuditError("R5 receipt self-integrity mismatch")

    trace = _object(report["trace"], {"schema_version", "experiment", "pairs"}, "trace")
    experiment = _object(trace["experiment"], {
        "scenario", "environment_id", "workload_sha256", "protocol_id",
        "metric", "declared_source",
    }, "experiment")
    if (trace["schema_version"] != "phios.elastic.trace-study.v1" or
            experiment["scenario"] != "residency-sparse-read" or
            experiment["protocol_id"] != PROTOCOL or
            experiment["metric"] != "task_elapsed_ms" or
            experiment["declared_source"] != "operator_supplied_unverified"):
        raise SessionAuditError("R5 trace protocol mismatch")
    try:
        recalculated = convert_trace(trace)
    except (TraceError, ValueError, OverflowError, RecursionError) as exc:
        raise SessionAuditError("R5 nested trace does not validate") from exc
    if report["comparison"] != recalculated or recalculated["status"] != "REVIEW_REQUIRED":
        raise SessionAuditError("R5 nested comparison is inconsistent")
    return report


def review_sessions(reports: Sequence[object]) -> dict[str, object]:
    """Review only structurally valid, matching R5 receipts.

    Identical input receipts are refused. Distinct hashes *do not* establish
    distinct machines, dates, runs, or independent provenance.
    """
    if not isinstance(reports, (list, tuple)) or not MIN_SESSIONS <= len(reports) <= MAX_SESSIONS:
        raise SessionAuditError("three to twelve explicitly selected receipts required")
    checked = [_validated(report) for report in reports]
    digests = [str(report["receipt_sha256"]) for report in checked]
    if len(set(digests)) != len(digests):
        raise SessionAuditError("duplicate receipt, not a separate session")
    first = checked[0]
    baseline = first["trace"]["experiment"]
    expected = (
        baseline["workload_sha256"], baseline["environment_id"],
        first["file_bytes"], first["windows"], first["window_bytes"],
        first["per_arm_selected_bytes"],
    )
    for report in checked[1:]:
        experiment = report["trace"]["experiment"]
        actual = (
            experiment["workload_sha256"], experiment["environment_id"],
            report["file_bytes"], report["windows"], report["window_bytes"],
            report["per_arm_selected_bytes"],
        )
        if actual != expected:
            raise SessionAuditError("mismatched workload, environment or window configuration")

    session_rows: list[dict[str, object]] = []
    values: list[float] = []
    for report in checked:
        summary = report["comparison"]["paired_comparison"]["summary"]
        pct = summary["median_paired_improvement_percent"]
        if (isinstance(pct, bool) or not isinstance(pct, (int, float)) or
                not math.isfinite(float(pct))):
            raise SessionAuditError("invalid nested improvement statistic")
        validated_percent = float(pct)
        values.append(validated_percent)
        session_rows.append({
            "r5_receipt_sha256": report["receipt_sha256"],
            "pair_count": report["comparison"]["paired_comparison"]["pair_count"],
            "median_paired_improvement_percent": pct,
            "wins": summary["wins"], "ties": summary["ties"], "losses": summary["losses"],
        })
    # The original R5 output has no timestamps. Sorting by digest makes report
    # hashes stable across argument order without pretending to know chronology.
    session_rows.sort(key=lambda row: str(row["r5_receipt_sha256"]))
    positives = sum(value > 0 for value in values)
    negatives = sum(value < 0 for value in values)
    zeros = len(values) - positives - negatives
    direction = ("all_positive" if positives == len(values) else
                 "all_negative" if negatives == len(values) else
                 "all_zero" if zeros == len(values) else "mixed")
    result: dict[str, object] = {
        "schema_version": SCHEMA,
        "status": "REVIEW_REQUIRED",
        "scope": "self_reported_warm_cache_sessions",
        "environment_id": baseline["environment_id"],
        "workload_sha256": baseline["workload_sha256"],
        "file_bytes": first["file_bytes"],
        "windows": first["windows"],
        "window_bytes": first["window_bytes"],
        "session_count": len(session_rows),
        "sessions": session_rows,
        "summary": {
            "median_of_session_median_improvements_percent": round(statistics.median(values), 4),
            "minimum_session_median_improvement_percent": round(min(values), 4),
            "maximum_session_median_improvement_percent": round(max(values), 4),
            "positive_sessions": positives, "negative_sessions": negatives,
            "zero_sessions": zeros, "direction": direction,
        },
        "independent_sessions_verified": False,
        "host_provenance_authenticated": False,
        "cold_cache_measured": False,
        "performance_improvement_proven": False,
        "action_authority": False,
        "execution_authority": False,
        "hardware_control": False,
    }
    result["receipt_sha256"] = _hash_json(result)
    return result


def _read_receipt(path: Path) -> object:
    """Read only an explicit local regular file, with a hard size bound."""
    try:
        if path.is_symlink():
            raise SessionAuditError("symlink receipt refused")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) |
                     getattr(os, "O_NOFOLLOW", 0))
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_RECEIPT_BYTES:
                raise SessionAuditError("invalid receipt file size or type")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(MAX_RECEIPT_BYTES + 1)
        finally:
            os.close(fd)
    except OSError as exc:
        raise SessionAuditError("receipt file unavailable") from exc
    if len(raw) > MAX_RECEIPT_BYTES:
        raise SessionAuditError("receipt exceeds size limit")

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        obj: dict[str, object] = {}
        for key, value in items:
            if key in obj:
                raise SessionAuditError("duplicate JSON key")
            obj[key] = value
        return obj

    def reject(_: str) -> None:
        raise SessionAuditError("nonfinite JSON value")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=reject)
    except (ValueError, UnicodeError) as exc:
        raise SessionAuditError("invalid receipt JSON") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PhiOS Elastic R6 offline multi-session evidence audit")
    parser.add_argument("--receipt", type=Path, action="append", required=True,
                        help="explicit local R5 JSON receipt, repeat 3–12 times")
    args = parser.parse_args(argv)
    try:
        result = review_sessions([_read_receipt(path) for path in args.receipt])
    except (SessionAuditError, RecursionError, OverflowError):
        print(json.dumps({"schema_version": SCHEMA, "status": "UNAVAILABLE",
                          "action_authority": False, "execution_authority": False},
                         sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
