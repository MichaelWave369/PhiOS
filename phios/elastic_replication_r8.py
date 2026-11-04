"""PhiOS Elastic R8: join two operator-supplied PhiStream research audits.

This is an offline, no-execution, no-promotion evidence compatibility gate.
It does NOT revalidate original checkpoint bytes, model output, or actual GPU runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Sequence, cast

from phios.elastic_phistream_r7 import (
    WeightStageReviewError,
    _read as read_bounded_local_json,
    review as review_stage,
)

SCHEMA = "phios.elastic.phistream-replication-join.v1"
SOURCE_SCHEMA = "PHISTREAM_REPLICATION_REVIEW_V1"
_STAGE_CASE = "spread_24"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ROOT = {
    "schema", "generated_utc", "status", "model_execution",
    "source_reference_authenticated", "statistical_significance_established",
    "cross_day_calendar_verified_independently", "production_promoted",
    "production_scheduler_unchanged", "general_speedup_proven",
    "original_seed", "original_census_sha256", "original_spread_24",
    "replication", "replication_plan_sha256", "replication_run_sha256",
    "checkpoint_fingerprint", "reference_sha256", "combined",
    "provenance", "scope", "next_gate",
}
_ORIGINAL = {
    "case", "pairs", "measured_executions", "warmup_executions",
    "all_executions_with_complete_parity", "greedy_id_matches",
    "sampled_logit_matches", "median_paired_relative_gain",
    "median_relative_ttft_gain", "candidate_faster_pair_count",
    "median_cumulative_weight_bytes_reduction", "review_thresholds_met",
    "qualification", "caution", "plan_sha256", "run_sha256",
}
_REPLICATION = {
    "case", "seed", "pairs", "model_executions_recorded",
    "measured_executions", "warmups", "greedy_id_matches",
    "sampled_logit_matches", "median_paired_relative_gain",
    "median_relative_ttft_gain", "median_cumulative_weight_bytes_reduction",
    "candidate_faster_pair_count", "review_thresholds_met", "qualification",
}
_COMBINED = {
    "paired_comparisons", "batched_faster_pairs",
    "recorded_executions_including_warmups", "greedy_id_matches",
    "sparse_logit_matches", "cohort_count",
    "replication_minus_original_spread_median_gain_percentage_points",
}
_REVIEW = "CANDIDATE_FOR_REPLICATED_REVIEW_NOT_PROVEN_SPEEDUP"
_INCONCLUSIVE = "INCONCLUSIVE_OR_NO_PERFORMANCE_BENEFIT"


class ReplicationJoinError(ValueError):
    """The R7/R8 source evidence cannot safely be joined."""


def _obj(value: object, required: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != required:
        raise ReplicationJoinError(f"invalid {name} fields")
    return value


def _int(value: object, name: str, *, low: int = 0, high: int = 1000000) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ReplicationJoinError(f"invalid {name}")
    return value


def _num(value: object, name: str, *, low: float = -1000000.0,
         high: float = 1000000.0) -> float:
    if type(value) not in (int, float):
        raise ReplicationJoinError(f"invalid {name}")
    result = float(value)
    if not math.isfinite(result) or not low <= result <= high:
        raise ReplicationJoinError(f"invalid {name}")
    return result


def _sha(value: object, name: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ReplicationJoinError(f"invalid {name} digest")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("ascii")


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _cohort(
    row: dict[str, Any], *, original: bool,
) -> dict[str, object]:
    expected_pairs = 4 if original else 8
    pairs = _int(row["pairs"], "pairs", low=expected_pairs, high=expected_pairs)
    wins = _int(row["candidate_faster_pair_count"], "faster pairs", high=pairs)
    ids = _int(row["greedy_id_matches"], "greedy parity", low=32, high=100000)
    probes = _int(row["sampled_logit_matches"], "logit parity", low=256, high=1000000)
    gain = _num(row["median_paired_relative_gain"], "paired decoder gain",
                low=-100, high=1)
    ttft = _num(row["median_relative_ttft_gain"], "time-to-first-logits gain",
                low=-100, high=1)
    bytes_reduced = _num(row["median_cumulative_weight_bytes_reduction"],
                         "staging-byte delta", low=-1e15, high=1e15)
    qualified = row["review_thresholds_met"]
    if type(qualified) is not bool:
        raise ReplicationJoinError("qualification flag must be boolean")
    # PhiStream's declared further-review threshold is 5% median gain and 75% wins.
    expected_qual = gain >= 0.05 and wins >= math.ceil(.75 * pairs)
    if qualified != expected_qual or row["qualification"] != (
        _REVIEW if qualified else _INCONCLUSIVE
    ):
        raise ReplicationJoinError("source cohort review threshold inconsistent")
    if row["case"] != _STAGE_CASE:
        raise ReplicationJoinError("unexpected prompt case")
    if original:
        if (row["caution"] !=
                "ONE_LOCAL_GPU_ONE_CHECKPOINT_FROZEN_PROMPT_NOT_SPEEDUP_PROOF"):
            raise ReplicationJoinError("missing single-GPU limit")
        _sha(row["plan_sha256"], "original plan")
        _sha(row["run_sha256"], "original run")
        measured = _int(row["measured_executions"], "original executions")
        warmups = _int(row["warmup_executions"], "original warmups")
        total = _int(row["all_executions_with_complete_parity"], "original total")
        if measured != 2 * pairs or warmups != 2 or total != measured + warmups:
            raise ReplicationJoinError("invalid original trial counts")
    else:
        if _int(row["seed"], "replication seed") != 70421:
            raise ReplicationJoinError("unexpected replication seed")
        measured = _int(row["measured_executions"], "replication executions")
        warmups = _int(row["warmups"], "replication warmups")
        total = _int(row["model_executions_recorded"], "replication total")
        if measured != 2 * pairs or warmups != 2 or total != measured + warmups:
            raise ReplicationJoinError("invalid replication trial counts")
    if ids != 32 * total or probes < 32 * 8 * total:
        raise ReplicationJoinError("incomplete declared parity census")
    return {
        "pair_count": pairs,
        "candidate_faster_pairs": wins,
        "measured_executions": measured,
        "warmup_executions": warmups,
        "complete_parity_executions": total,
        "greedy_ids_matched": ids,
        "sparse_logits_matched": probes,
        "median_paired_decoder_gain_percent": round(gain * 100, 4),
        "median_paired_first_logits_gain_percent": round(ttft * 100, 4),
        "median_weight_staging_bytes_reduction": bytes_reduced,
        "review_threshold_met": qualified,
    }


def join(stage_audit: object, replication_audit: object) -> dict[str, object]:
    """Review joined, already-audited source summaries without promoting them."""
    try:
        stage = review_stage(stage_audit)
    except WeightStageReviewError as exc:
        raise ReplicationJoinError("R7 source stage audit invalid") from exc
    if not isinstance(stage_audit, dict):
        raise ReplicationJoinError("invalid stage audit")
    report = _obj(replication_audit, _ROOT, "replication report")
    if report["schema"] != SOURCE_SCHEMA:
        raise ReplicationJoinError("wrong replication schema")
    if (report["provenance"] !=
            "OPERATOR_LOCAL_SHA_BOUND_RECEIPTS_NOT_PUBLISHER_ATTESTATION" or
            report["scope"] !=
            "SMOLLM2_135M_ONE_RTX_5070_ONE_FROZEN_PROMPT_FOR_REPLICATION" or
            report["next_gate"] !=
            "HELD_OUT_PROMPTS_VRAM_SAFETY_OTHER_HARDWARE_SEPARATE_AUTHORIZATION"):
        raise ReplicationJoinError("unsupported replication scope")
    for field in (
        "model_execution", "source_reference_authenticated",
        "statistical_significance_established",
        "cross_day_calendar_verified_independently", "production_promoted",
        "general_speedup_proven",
    ):
        if report[field] is not False:
            raise ReplicationJoinError("unearned source proof or execution claim")
    if report["production_scheduler_unchanged"] is not True:
        raise ReplicationJoinError("source scheduling claims changed")
    if not isinstance(report["generated_utc"], str) or not (
        1 <= len(report["generated_utc"]) <= 80
    ):
        raise ReplicationJoinError("invalid declared source timestamp")
    if _int(report["original_seed"], "original seed") != 369:
        raise ReplicationJoinError("unexpected original seed")
    for field in (
        "original_census_sha256", "replication_plan_sha256",
        "replication_run_sha256", "reference_sha256",
    ):
        _sha(report[field], field)
    stage_binding = _obj(stage_audit["input_bindings"], {
        "manifest_sha256", "matrix_review_sha256", "checkpoint_fingerprint",
    }, "stage source binding")
    if report["checkpoint_fingerprint"] != stage_binding["checkpoint_fingerprint"]:
        raise ReplicationJoinError("stage and replicated model checkpoint disagree")
    stage_cases = stage_audit["cases"]
    stage_spread = next(
        row for row in stage_cases if isinstance(row, dict) and row.get("id") == _STAGE_CASE
    )
    if report["reference_sha256"] != stage_spread["reference_sha256"]:
        raise ReplicationJoinError("stage and replicated reference trace disagree")

    original = _cohort(_obj(report["original_spread_24"], _ORIGINAL, "original cohort"),
                       original=True)
    replication = _cohort(_obj(report["replication"], _REPLICATION, "replication cohort"),
                          original=False)
    if original["review_threshold_met"] is not True:
        raise ReplicationJoinError("original cohort did not meet its historical gate")
    expected_status = ("REPLICATION_REVIEW_CANDIDATE_NOT_SPEEDUP_CERTIFIED"
                       if replication["review_threshold_met"] else
                       "REPLICATION_MATCHED_BUT_PERFORMANCE_NOT_QUALIFIED")
    if report["status"] != expected_status:
        raise ReplicationJoinError("replication status and threshold contradict")
    combined = _obj(report["combined"], _COMBINED, "four-cohort census")
    pairs = _int(combined["paired_comparisons"], "total paired comparisons")
    wins = _int(combined["batched_faster_pairs"], "total faster comparisons")
    executions = _int(combined["recorded_executions_including_warmups"], "total executions")
    greedy = _int(combined["greedy_id_matches"], "total greedy ID matches")
    sparse = _int(combined["sparse_logit_matches"], "total sparse logit matches")
    if (pairs != 20 or executions != 48 or greedy != 32 * executions or
            sparse < 32 * 8 * executions or wins > pairs or
            wins < cast(int, original["candidate_faster_pairs"]) +
                   cast(int, replication["candidate_faster_pairs"]) or
            wins > 8 + cast(int, original["candidate_faster_pairs"]) +
                   cast(int, replication["candidate_faster_pairs"]) or
            _int(combined["cohort_count"], "cohort count") != 4):
        raise ReplicationJoinError("four-cohort combined census inconsistent")
    recorded_delta = _num(
        combined["replication_minus_original_spread_median_gain_percentage_points"],
        "replication difference")
    expected_delta = round(
        float(replication["median_paired_decoder_gain_percent"]) -
        float(original["median_paired_decoder_gain_percent"]), 4)
    if abs(recorded_delta - expected_delta) > 0.00011:
        raise ReplicationJoinError("replication delta disagrees with cohorts")

    stage_summary = cast(dict[str, Any], stage["summary"])
    summary: dict[str, object] = {
        "stage_audit_cases": stage_summary["cases"],
        "stage_median_share_percent": stage_summary["median_staging_share_percent"],
        "single_token_step_staged_weight_bytes":
            stage_summary["weight_payload_bytes_per_single_token_step"],
        "original_spread_24": original,
        "replication_spread_24": replication,
        "combined_matched_pairs": pairs,
        "combined_batched_faster_pairs": wins,
        "combined_reported_complete_parity_executions": executions,
        "combined_reported_greedy_ids_matched": greedy,
        "combined_reported_sparse_logits_matched": sparse,
        "reported_replication_minus_original_gain_percentage_points":
            round(recorded_delta, 4),
    }
    result: dict[str, object] = {
        "schema_version": SCHEMA,
        "status": "REVIEW_REQUIRED" if replication["review_threshold_met"] else "INCONCLUSIVE",
        "scope": "one_operator_supplied_matched_stage_and_replication_audit_pair",
        "stage_audit_sha256": stage["source_audit_sha256"],
        "replication_audit_sha256": _hash(report),
        "case": _STAGE_CASE,
        "summary": summary,
        "next_gate": "held_out_parity_and_vram_budget_trial_with_separate_operator_approval",
        "joint_source_consistency_checked": True,
        "original_checkpoint_bytes_rehashed": False,
        "real_model_executed_here": False,
        "external_reference_authenticated": False,
        "independent_replication_attested": False,
        "statistical_significance_established": False,
        "general_speedup_proven": False,
        "automatic_scheduler_promotion": False,
        "action_authority": False,
        "execution_authority": False,
        "hardware_control": False,
    }
    result["receipt_sha256"] = _hash(result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PhiOS R8 joint PhiStream stage/replication audit")
    parser.add_argument("--stage-audit", type=Path, required=True)
    parser.add_argument("--replication-review", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        stage = read_bounded_local_json(args.stage_audit)
        replication = read_bounded_local_json(args.replication_review)
        result = join(stage, replication)
    except (ReplicationJoinError, WeightStageReviewError, OSError,
            RecursionError, OverflowError):
        print(json.dumps({"schema_version": SCHEMA, "status": "UNAVAILABLE",
                          "action_authority": False, "execution_authority": False},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0 if result["status"] == "REVIEW_REQUIRED" else 3


if __name__ == "__main__":
    sys.exit(main())
