"""PhiOS Elastic R7: read-only import of PhiStream public weight-stage audit.

Recomputes published stage-counter arithmetic from one self-reported
PhiStream audit. No checkpoint, inference, CUDA or scheduler interaction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import statistics
import sys
from pathlib import Path
from typing import Any, Sequence

SOURCE_SCHEMA = "PHISTREAM_WEIGHT_STAGE_AUDIT_V1"
SCHEMA = "phios.elastic.phistream-stage-review.v1"
MAX_BYTES = 128 * 1024
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_CASES = {"short_1": 1, "mixed_7": 7, "repeat_12": 12, "spread_24": 24}
_ROOT_KEYS = {
    "schema", "status", "generated_utc", "provenance", "matrix_status",
    "source_reference_authenticated", "model_execution", "scheduler_policy_changed",
    "real_model_optimization_speedup_measured", "production_ready",
    "input_bindings", "cases", "four_cases", "weight_payload_bytes",
    "exact_bytes_step_pattern", "per_run_fixed_staged_bytes_outside_single_token_steps",
    "exact_weight_load_operation_count_pattern", "weight_load_operations_per_decoder_step",
    "fixed_initial_weight_load_operations", "median_staging_time_fraction_observed",
    "max_staging_time_fraction_observed", "performance_scope", "next_falsifiable_experiment",
}
_CASE_KEYS = {
    "id", "prompt_tokens", "generated_tokens", "single_token_decoder_steps",
    "checkpoint_weight_payload_bytes", "recorded_staging_bytes",
    "recorded_weight_load_operations", "recorded_staging_seconds",
    "recorded_decoder_seconds", "recorded_staging_fraction",
    "recorded_nonstaging_seconds", "staged_bytes_minus_steps_times_payload",
    "incremental_prompt_restaging_bytes_relative_to_one_token",
    "reference_sha256", "parity_receipt_sha256",
}
_SCOPE_KEYS = {
    "timings_descriptive", "each_case_only_one_run",
    "prompt_length_confounded_with_staging_count",
    "staging_timer_includes_file_read_cpu_conversion_gpu_transfer_sync_and_python_overhead",
    "no_overlapped_or_batched_prefill_executed",
    "incremental_prompt_bytes_are_a_counter_fact_not_achieved_savings",
    "cannot_infer_transfer_bandwidth_or_gpu_speedup",
}


class WeightStageReviewError(ValueError):
    """An audit is unavailable, ambiguous or fails public counter checks."""


def _obj(value: object, keys: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise WeightStageReviewError(f"invalid {name} fields")
    return value


def _integer(value: object, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= 10**15:
        raise WeightStageReviewError(f"invalid {name}")
    return value


def _decimal(value: object, name: str, *, minimum: float = 0.0,
             maximum: float = 10**9) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WeightStageReviewError(f"invalid {name}")
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise WeightStageReviewError(f"invalid {name}")
    return number


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise WeightStageReviewError(f"invalid {name} digest")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def review(audit: object) -> dict[str, object]:
    """Validate one canonical four-case source format and emit bounded advisory.

    This does not rehash the original checkpoint/reference/parity evidence.
    Source data, even when consistent, is user-supplied and unauthenticated.
    """
    data = _obj(audit, _ROOT_KEYS, "PhiStream audit")
    if data["schema"] != SOURCE_SCHEMA or data["status"] != "EXACT_STAGE_COUNTER_LINEARITY_OBSERVED":
        raise WeightStageReviewError("unsupported audit schema or inconclusive stage pattern")
    if (data["provenance"] !=
            "DERIVED_FROM_USER_SUPPLIED_LOCAL_SHA_BOUND_PARITY_RECEIPTS" or
            data["matrix_status"] not in (
                "MATCHED_LIMITED_FOUR_CASES", "MATCHED_LIMITED_LOW_OUTPUT_DIVERSITY"
            )):
        raise WeightStageReviewError("invalid source scope")
    if not isinstance(data["generated_utc"], str) or not 1 <= len(data["generated_utc"]) <= 80:
        raise WeightStageReviewError("invalid declared timestamp")
    if not isinstance(data["next_falsifiable_experiment"], str) or not (
            1 <= len(data["next_falsifiable_experiment"]) <= 1024):
        raise WeightStageReviewError("missing next experiment scope")
    for field in (
        "source_reference_authenticated", "model_execution", "scheduler_policy_changed",
        "real_model_optimization_speedup_measured", "production_ready",
    ):
        if data[field] is not False:
            raise WeightStageReviewError("unsupported source execution or authority claim")
    if (data["exact_bytes_step_pattern"] is not True or
            data["exact_weight_load_operation_count_pattern"] is not True or
            type(data["four_cases"]) is not int or data["four_cases"] != 4):
        raise WeightStageReviewError("nonlinear or incomplete four-case audit")
    scopes = _obj(data["performance_scope"], _SCOPE_KEYS, "scope")
    if any(value is not True for value in scopes.values()):
        raise WeightStageReviewError("missing mandatory limitation")
    bindings = _obj(data["input_bindings"], {
        "manifest_sha256", "matrix_review_sha256", "checkpoint_fingerprint",
    }, "source bindings")
    _digest(bindings["manifest_sha256"], "manifest")
    _digest(bindings["matrix_review_sha256"], "matrix review")
    # PhiStream's checkpoint fingerprint is a composite object containing
    # file digests. Do not forward it into PhiOS review output.
    fingerprint = bindings["checkpoint_fingerprint"]
    if not isinstance(fingerprint, dict) or fingerprint.get("algorithm") != "sha256":
        raise WeightStageReviewError("unsupported checkpoint fingerprint")

    payload = _integer(data["weight_payload_bytes"], "weight payload", minimum=1)
    fixed_bytes = _integer(
        data["per_run_fixed_staged_bytes_outside_single_token_steps"], "fixed bytes"
    )
    per_step_ops = _integer(data["weight_load_operations_per_decoder_step"],
                            "operations per step", minimum=1)
    fixed_ops = _integer(data["fixed_initial_weight_load_operations"], "fixed operations")
    rows = data["cases"]
    if not isinstance(rows, list) or len(rows) != 4:
        raise WeightStageReviewError("expected four fixed prompt cases")
    parsed: list[dict[str, object]] = []
    fractions: list[float] = []
    case_ids: set[str] = set()
    for raw in rows:
        row = _obj(raw, _CASE_KEYS, "case")
        name = row["id"]
        if not isinstance(name, str) or name not in _CASES or name in case_ids:
            raise WeightStageReviewError("unknown or repeated case")
        case_ids.add(name)
        prompt = _integer(row["prompt_tokens"], "prompt tokens", minimum=1)
        generated = _integer(row["generated_tokens"], "generated tokens", minimum=1)
        steps = _integer(row["single_token_decoder_steps"], "decoder steps", minimum=1)
        if prompt != _CASES[name] or generated != 32 or steps != prompt + generated - 1:
            raise WeightStageReviewError("case no longer matches frozen prompt protocol")
        staged_bytes = _integer(row["recorded_staging_bytes"], "staged bytes", minimum=1)
        load_ops = _integer(row["recorded_weight_load_operations"], "load operations")
        stage_sec = _decimal(row["recorded_staging_seconds"], "staging seconds")
        decoder_sec = _decimal(row["recorded_decoder_seconds"], "decoder seconds",
                               minimum=0.000001)
        fraction = _decimal(row["recorded_staging_fraction"], "staging fraction",
                            maximum=1)
        nonstage = _decimal(row["recorded_nonstaging_seconds"], "nonstaging seconds")
        if (row["checkpoint_weight_payload_bytes"] != payload or
                type(row["checkpoint_weight_payload_bytes"]) is not int or
                row["staged_bytes_minus_steps_times_payload"] != fixed_bytes or
                type(row["staged_bytes_minus_steps_times_payload"]) is not int or
                row["incremental_prompt_restaging_bytes_relative_to_one_token"] !=
                (prompt - 1) * payload or
                type(row["incremental_prompt_restaging_bytes_relative_to_one_token"]) is not int or
                staged_bytes != steps * payload + fixed_bytes or
                load_ops != steps * per_step_ops + fixed_ops):
            raise WeightStageReviewError("inconsistent stage-byte or operation counter")
        if stage_sec > decoder_sec or abs(fraction - stage_sec / decoder_sec) > 0.000002:
            raise WeightStageReviewError("inconsistent staging share")
        if abs(nonstage - (decoder_sec - stage_sec)) > 0.000002:
            raise WeightStageReviewError("inconsistent non-staging time")
        _digest(row["reference_sha256"], "reference")
        _digest(row["parity_receipt_sha256"], "parity receipt")
        fractions.append(fraction)
        parsed.append({
            "case": name, "prompt_tokens": prompt, "decoder_steps": steps,
            "staged_bytes": staged_bytes, "staging_seconds": stage_sec,
            "decoder_seconds": decoder_sec, "stage_fraction": fraction,
            "staging_share_percent": round(fraction * 100, 2),
        })
    if case_ids != set(_CASES):
        raise WeightStageReviewError("incomplete frozen case census")
    declared_median = _decimal(data["median_staging_time_fraction_observed"], "median share",
                               maximum=1)
    declared_max = _decimal(data["max_staging_time_fraction_observed"], "max share",
                            maximum=1)
    if (abs(declared_median - statistics.median(fractions)) > 0.000002 or
            abs(declared_max - max(fractions)) > 0.000002):
        raise WeightStageReviewError("inconsistent cross-case staging summary")
    parsed.sort(key=lambda row: _CASES[str(row["case"])])
    result: dict[str, object] = {
        "schema_version": SCHEMA,
        "status": "REVIEW_REQUIRED",
        "scope": "one_operator_supplied_phistream_four_case_audit",
        "source_schema": SOURCE_SCHEMA,
        "source_audit_sha256": _hash(data),
        "cases": parsed,
        "summary": {
            "cases": 4,
            "median_staging_share_percent": round(statistics.median(fractions) * 100, 2),
            "highest_staging_share_percent": round(max(fractions) * 100, 2),
            "weight_payload_bytes_per_single_token_step": payload,
            "weight_load_operations_per_single_token_step": per_step_ops,
            "fixed_staged_bytes_per_run": fixed_bytes,
        },
        "hypothesis": "measure_layer_reuse_and_prefill_before_considering_residency_policy",
        "stage_timing_includes_many_operations": True,
        "independent_source_verification": False,
        "model_reexecuted": False,
        "transfer_bandwidth_proven": False,
        "speedup_proven": False,
        "action_authority": False,
        "execution_authority": False,
        "hardware_control": False,
    }
    result["receipt_sha256"] = _hash(result)
    return result


def _read(path: Path) -> object:
    try:
        if path.is_symlink():
            raise WeightStageReviewError("symlink input is refused")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) |
                     getattr(os, "O_NOFOLLOW", 0))
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or not 1 <= info.st_size <= MAX_BYTES:
                raise WeightStageReviewError("audit must be a bounded regular file")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(MAX_BYTES + 1)
        finally:
            os.close(fd)
    except OSError as exc:
        raise WeightStageReviewError("audit unavailable") from exc
    if len(raw) > MAX_BYTES:
        raise WeightStageReviewError("audit size limit exceeded")

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise WeightStageReviewError("duplicate JSON field")
            result[key] = value
        return result

    def reject(_: str) -> None:
        raise WeightStageReviewError("nonfinite JSON field")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=reject)
    except (ValueError, UnicodeError) as exc:
        raise WeightStageReviewError("invalid audit JSON") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PhiOS R7 offline PhiStream stage audit import")
    parser.add_argument("--audit", type=Path, required=True,
                        help="explicit local PhiStream weight-stage-audit.json")
    args = parser.parse_args(argv)
    try:
        result = review(_read(args.audit))
    except (WeightStageReviewError, OverflowError, RecursionError):
        print(json.dumps({"schema_version": SCHEMA, "status": "UNAVAILABLE",
                          "action_authority": False, "execution_authority": False},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
