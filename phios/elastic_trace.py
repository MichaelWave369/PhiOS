"""PhiOS Elastic R4: offline workload trace conversion to R3 paired evidence.

Only accepts explicitly selected, untrusted duration observations. It never
executes recorded workloads, talks to hardware, or promotes a resource plan.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import stat
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable, Sequence, TypeVar

from phios.elastic_compare import PairedStudyError, compare

TRACE_SCHEMA = "phios.elastic.trace-study.v1"
RESULT_SCHEMA = "phios.elastic.trace-comparison.v1"
MAX_TRACE_BYTES = 2 * 1024 * 1024
MAX_DURATION_US = 3_600_000_000
MAX_PAIRS = 64
MAX_SAMPLES_PER_ARM = 2048
METRICS = frozenset({"frame_time_p95_ms", "startup_ms", "first_token_ms", "task_elapsed_ms"})
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_T = TypeVar("_T")


class TraceError(ValueError):
    """Malformed, ambiguous, or unsupported workload trace."""


def _object(value: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise TraceError(f"invalid {label} fields")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def measure_call(workload: Callable[[], _T], *,
                 clock_ns: Callable[[], int] | None = None) -> tuple[_T, int]:
    """Opt-in duration around a caller-owned synchronous Python workload.

    Runs the supplied callable exactly once. It can have side effects; callers
    are responsible for its behavior. Exceptions propagate unchanged. No timing
    record is fabricated for failed/incomplete work.
    """
    if not callable(workload):
        raise TraceError("workload must be callable")
    clock = clock_ns if clock_ns is not None else time.perf_counter_ns
    started = clock()
    if type(started) is not int or started < 0:
        raise TraceError("invalid start clock")
    result = workload()
    stopped = clock()
    if type(stopped) is not int or stopped <= started:
        raise TraceError("invalid completed duration")
    # Integer microseconds are portable to browser performance.now() samples.
    elapsed_us = (stopped - started + 999) // 1000
    if not 1 <= elapsed_us <= MAX_DURATION_US:
        raise TraceError("measured duration outside trace bounds")
    return result, elapsed_us


def _duration_samples(value: object, metric: str) -> tuple[list[int], float]:
    if not isinstance(value, list) or not value or len(value) > MAX_SAMPLES_PER_ARM:
        raise TraceError("invalid duration sample count")
    if metric == "frame_time_p95_ms" and len(value) < 100:
        raise TraceError("frame-time p95 requires at least 100 observed frames")
    if any(type(n) is not int or not 1 <= n <= MAX_DURATION_US for n in value):
        raise TraceError("duration must be a positive bounded integer in microseconds")
    samples: list[int] = value
    observed_us: float
    if metric == "frame_time_p95_ms":
        ordered = sorted(samples)
        observed_us = float(ordered[math.ceil(.95 * len(ordered)) - 1])
    else:
        observed_us = float(statistics.median(samples))
    return samples, round(observed_us / 1000.0, 6)


def convert_trace(trace: object) -> dict[str, object]:
    """Derive R3 pairs from raw samples, retaining only descriptive authority."""
    root = _object(trace, {"schema_version", "experiment", "pairs"}, "trace")
    if root["schema_version"] != TRACE_SCHEMA:
        raise TraceError("unknown trace schema")
    experiment = _object(root["experiment"], {
        "scenario", "environment_id", "workload_sha256", "protocol_id", "metric",
        "declared_source",
    }, "experiment")
    metric = experiment["metric"]
    if not isinstance(metric, str) or metric not in METRICS:
        raise TraceError("unsupported R4 trace metric")
    if experiment["declared_source"] != "operator_supplied_unverified":
        raise TraceError("trace provenance cannot be independently asserted")
    pairs = root["pairs"]
    if not isinstance(pairs, list) or not 6 <= len(pairs) <= MAX_PAIRS:
        raise TraceError("R4 needs between 6 and 64 paired runs")
    derived_pairs: list[dict[str, object]] = []
    for pair in pairs:
        item = _object(pair, {"pair_id", "order", "baseline", "candidate"}, "trace pair")
        derived: dict[str, object] = {"pair_id": item["pair_id"], "order": item["order"]}
        for arm in ("baseline", "candidate"):
            arm_data = _object(item[arm], {"durations_us", "passed", "r2_receipt_sha256"},
                               f"{arm} trace")
            if not isinstance(arm_data["passed"], bool):
                raise TraceError("correctness flag must be Boolean")
            link = arm_data["r2_receipt_sha256"]
            if link is not None and (not isinstance(link, str) or not _DIGEST.fullmatch(link)):
                raise TraceError("invalid R2 digest label")
            samples, measurement = _duration_samples(arm_data["durations_us"], metric)
            derived[arm] = {
                "value": measurement,
                "samples": len(samples),
                "passed": arm_data["passed"],
                "r2_receipt_sha256": link,
            }
        derived_pairs.append(derived)
    study: dict[str, object] = {
        "schema_version": "phios.elastic.paired-study.v1",
        "experiment": experiment,
        "pairs": derived_pairs,
    }
    try:
        review = compare(study)
    except PairedStudyError as exc:
        raise TraceError("R3 pairing contract rejected the derived trace") from exc
    report: dict[str, object] = {
        "schema_version": RESULT_SCHEMA,
        "status": review["status"],
        "source": "operator_supplied_unverified",
        "trace_sha256": _hash(trace),
        "aggregation": "nearest_rank_p95" if metric == "frame_time_p95_ms" else "median_duration",
        "paired_comparison": review,
        "trace_provenance_authenticated": False,
        "performance_improvement_proven": False,
        "action_authority": False,
        "execution_authority": False,
        "hardware_control": False,
    }
    report["receipt_sha256"] = _hash(report)
    return report


def _read_trace(path: Path) -> object:
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_TRACE_BYTES:
            raise TraceError("trace must be a bounded regular non-symlink file")
        raw = path.read_bytes()
    except OSError as exc:
        raise TraceError("trace unavailable") from exc
    if len(raw) > MAX_TRACE_BYTES:
        raise TraceError("trace exceeds byte limit")

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        obj: dict[str, object] = {}
        for key, value in items:
            if key in obj:
                raise TraceError("duplicate JSON field")
            obj[key] = value
        return obj

    def reject(_: str) -> None:
        raise TraceError("non-finite JSON constant")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=reject)
    except (UnicodeError, ValueError) as exc:
        raise TraceError("invalid trace JSON") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PhiOS Elastic R4 offline trace-to-R3 reviewer")
    parser.add_argument("--trace", type=Path, required=True,
                        help="explicit local trace JSON, no execution or hardware probes")
    args = parser.parse_args(argv)
    try:
        result = convert_trace(_read_trace(args.trace))
    except (TraceError, RecursionError, OverflowError):
        print(json.dumps({"schema_version": RESULT_SCHEMA, "status": "UNAVAILABLE",
                          "action_authority": False, "execution_authority": False},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 3 if result["status"] == "HELD" else 0


if __name__ == "__main__":
    sys.exit(main())
