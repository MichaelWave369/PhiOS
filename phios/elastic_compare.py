"""PhiOS Elastic R3: offline comparison of operator-supplied paired workload data.

A decision-support calculator, not a collector, executor, or proof of speedup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Sequence

INPUT_SCHEMA = "phios.elastic.paired-study.v1"
OUTPUT_SCHEMA = "phios.elastic.paired-comparison.v1"
MAX_BYTES = 262144
MAX_PAIRS = 64
IDENTIFIER = re.compile(r"[a-z][a-z0-9._:-]{0,63}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
METRICS: dict[str, tuple[str, str, int]] = {
    "frame_time_p95_ms": ("ms", "lower", 100),
    "startup_ms": ("ms", "lower", 1),
    "first_token_ms": ("ms", "lower", 1),
    "task_elapsed_ms": ("ms", "lower", 1),
    "tokens_per_second": ("tokens/s", "higher", 1),
    "throughput_ops_per_second": ("ops/s", "higher", 1),
}


class PairedStudyError(ValueError):
    """Invalid or incomparable experiment input."""


def _object(value: object, required: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != required:
        raise PairedStudyError(f"invalid {name} fields")
    return value


def _id(value: object, name: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise PairedStudyError(f"invalid {name}")
    return value


def _sha256(value: object, name: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not DIGEST.fullmatch(value):
        raise PairedStudyError(f"invalid {name} digest")
    return value


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PairedStudyError(f"invalid {name}")
    result = float(value)
    if not math.isfinite(result) or not 0 < result <= 1_000_000_000:
        raise PairedStudyError(f"invalid {name}")
    return result


def _integer(value: object, name: str, *, minimum: int) -> int:
    if type(value) is not int or not minimum <= value <= 10_000_000:
        raise PairedStudyError(f"invalid {name}")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _median(values: list[float]) -> float:
    return round(statistics.median(values), 4)


def compare(payload: object) -> dict[str, object]:
    """Return bounded descriptive paired statistics; never authorize promotion.

    All input values are untrusted, operator-supplied observations. The attached
    R2 digest *labels*, if any, are not verified or authenticated by R3.
    """
    root = _object(payload, {"schema_version", "experiment", "pairs"}, "study")
    if root["schema_version"] != INPUT_SCHEMA:
        raise PairedStudyError("unknown study schema")
    experiment = _object(root["experiment"], {
        "scenario", "environment_id", "workload_sha256", "protocol_id", "metric",
        "declared_source",
    }, "experiment")
    scenario = _id(experiment["scenario"], "scenario")
    environment_id = _id(experiment["environment_id"], "environment")
    protocol = _id(experiment["protocol_id"], "protocol")
    workload_digest = _sha256(experiment["workload_sha256"], "workload")
    metric = experiment["metric"]
    if not isinstance(metric, str) or metric not in METRICS:
        raise PairedStudyError("unsupported workload metric")
    if experiment["declared_source"] != "operator_supplied_unverified":
        raise PairedStudyError("unsupported evidence source")
    unit, better, minimum_samples = METRICS[metric]
    raw_pairs = root["pairs"]
    if not isinstance(raw_pairs, list) or not 6 <= len(raw_pairs) <= MAX_PAIRS:
        raise PairedStudyError("a balanced study needs 6 to 64 pairs")

    pairs: list[dict[str, object]] = []
    seen: set[str] = set()
    orders = {"AB": 0, "BA": 0}
    deltas: list[float] = []
    baselines: list[float] = []
    candidates: list[float] = []
    failed_baseline = 0
    failed_candidate = 0
    r2_links = 0
    wins = ties = losses = 0
    for item in raw_pairs:
        pair = _object(item, {"pair_id", "order", "baseline", "candidate"}, "pair")
        pair_id = _id(pair["pair_id"], "pair id")
        if pair_id in seen:
            raise PairedStudyError("duplicate pair id")
        seen.add(pair_id)
        order = pair["order"]
        if not isinstance(order, str) or order not in orders:
            raise PairedStudyError("invalid crossover order")
        orders[order] += 1
        measures: dict[str, dict[str, object]] = {}
        for arm in ("baseline", "candidate"):
            reading = _object(pair[arm], {"value", "samples", "passed", "r2_receipt_sha256"},
                              f"{arm} reading")
            value = _number(reading["value"], f"{arm} value")
            count = _integer(reading["samples"], f"{arm} samples",
                             minimum=minimum_samples)
            if not isinstance(reading["passed"], bool):
                raise PairedStudyError("passed must be boolean")
            receipt_digest = _sha256(reading["r2_receipt_sha256"], "R2 receipt",
                                     nullable=True)
            if receipt_digest is not None:
                r2_links += 1
            measures[arm] = {"value": value, "samples": count,
                             "passed": reading["passed"],
                             "r2_receipt_sha256": receipt_digest}
        baseline = float(measures["baseline"]["value"])
        candidate = float(measures["candidate"]["value"])
        improvement = ((baseline - candidate) / baseline if better == "lower"
                       else (candidate - baseline) / baseline) * 100.0
        if not math.isfinite(improvement):
            raise PairedStudyError("invalid relative difference")
        deltas.append(improvement)
        baselines.append(baseline)
        candidates.append(candidate)
        if improvement > 0:
            wins += 1
        elif improvement < 0:
            losses += 1
        else:
            ties += 1
        if not measures["baseline"]["passed"]:
            failed_baseline += 1
        if not measures["candidate"]["passed"]:
            failed_candidate += 1
        pairs.append({"pair_id": pair_id, "order": order,
                      "baseline": measures["baseline"], "candidate": measures["candidate"],
                      "improvement_percent": round(improvement, 4)})

    # Within one study, balanced order prevents all candidates from being second.
    if abs(orders["AB"] - orders["BA"]) > 1:
        raise PairedStudyError("crossover ordering is not balanced")
    pairs.sort(key=lambda row: str(row["pair_id"]))
    # A bad run cannot turn into a green recommendation through a fast clock.
    status = "HELD" if failed_baseline or failed_candidate else "REVIEW_REQUIRED"
    normalized = {
        "schema_version": INPUT_SCHEMA,
        "experiment": {"scenario": scenario, "environment_id": environment_id,
                       "workload_sha256": workload_digest, "protocol_id": protocol,
                       "metric": metric, "declared_source": "operator_supplied_unverified"},
        "pairs": [{key: row[key] for key in ("pair_id", "order", "baseline", "candidate")}
                  for row in pairs],
    }
    result: dict[str, object] = {
        "schema_version": OUTPUT_SCHEMA,
        "status": status,
        "scope": "paired_operator_supplied_unverified",
        "scenario": scenario,
        "environment_id": environment_id,
        "protocol_id": protocol,
        "workload_sha256": workload_digest,
        "metric": metric,
        "unit": unit,
        "better": better,
        "pair_count": len(pairs),
        "order_counts": orders,
        "summary": {
            "median_baseline": _median(baselines),
            "median_candidate": _median(candidates),
            "median_paired_improvement_percent": _median(deltas),
            "worst_paired_improvement_percent": round(min(deltas), 4),
            "best_paired_improvement_percent": round(max(deltas), 4),
            "wins": wins, "ties": ties, "losses": losses,
            "baseline_failed": failed_baseline, "candidate_failed": failed_candidate,
            "r2_digest_labels_present": r2_links,
        },
        "pairs": pairs,
        "source_sha256": _hash(normalized),
        "action_authority": False,
        "execution_authority": False,
        "hardware_control": False,
        "statistical_significance_claimed": False,
        "performance_improvement_proven": False,
    }
    result["receipt_sha256"] = _hash(result)
    return result


def _read_study(path: Path) -> object:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
            raise PairedStudyError("study must be a bounded regular non-symlink file")
        raw = path.read_bytes()
    except OSError as exc:
        raise PairedStudyError("study is unavailable") from exc
    if len(raw) > MAX_BYTES:
        raise PairedStudyError("study exceeds byte limit")

    def pairs(entries: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in entries:
            if key in result:
                raise PairedStudyError("duplicate JSON field")
            result[key] = value
        return result

    def reject_constant(_: str) -> None:
        raise PairedStudyError("non-finite JSON constant")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=reject_constant)
    except (UnicodeError, ValueError) as exc:
        raise PairedStudyError("invalid study JSON") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PhiOS Elastic R3 offline paired benchmark review")
    parser.add_argument("--study", required=True, type=Path,
                        help="explicit local paired study JSON; no host interaction")
    args = parser.parse_args(argv)
    try:
        report = compare(_read_study(args.study))
    except (PairedStudyError, RecursionError, OverflowError):
        print(json.dumps({"schema_version": OUTPUT_SCHEMA, "status": "UNAVAILABLE",
                          "action_authority": False, "execution_authority": False},
                         sort_keys=True))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 3 if report["status"] == "HELD" else 0


if __name__ == "__main__":
    sys.exit(main())
