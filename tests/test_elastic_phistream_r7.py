"""Synthetic PhiStream V1 audit fixtures exercise PhiOS R7's public boundary.

No checkpoint, CUDA, model download, or background process is used by CI.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from phios.elastic_phistream_r7 import WeightStageReviewError, _read, review


def synthetic_audit() -> dict:
    prompts = [("short_1", 1, 8.040275, 9.825242),
               ("mixed_7", 7, 9.388994, 11.394797),
               ("repeat_12", 12, 10.390424, 12.555416),
               ("spread_24", 24, 13.352226, 16.142352)]
    payload = 269030016
    fixed = 1152
    operations_per_step = 48
    fixed_operations = 1
    cases = []
    for case_id, prompt, stage_sec, decoder_sec in prompts:
        steps = prompt + 31
        cases.append({
            "id": case_id,
            "prompt_tokens": prompt,
            "generated_tokens": 32,
            "single_token_decoder_steps": steps,
            "checkpoint_weight_payload_bytes": payload,
            "recorded_staging_bytes": steps * payload + fixed,
            "recorded_weight_load_operations": steps * operations_per_step + fixed_operations,
            "recorded_staging_seconds": stage_sec,
            "recorded_decoder_seconds": decoder_sec,
            "recorded_staging_fraction": round(stage_sec / decoder_sec, 6),
            "recorded_nonstaging_seconds": round(decoder_sec - stage_sec, 6),
            "staged_bytes_minus_steps_times_payload": fixed,
            "incremental_prompt_restaging_bytes_relative_to_one_token": (prompt - 1) * payload,
            "reference_sha256": "a" * 64,
            "parity_receipt_sha256": "b" * 64,
        })
    fractions = [row["recorded_staging_fraction"] for row in cases]
    return {
        "schema": "PHISTREAM_WEIGHT_STAGE_AUDIT_V1",
        "status": "EXACT_STAGE_COUNTER_LINEARITY_OBSERVED",
        "generated_utc": "2026-10-12T18:00:00+00:00",
        "provenance": "DERIVED_FROM_USER_SUPPLIED_LOCAL_SHA_BOUND_PARITY_RECEIPTS",
        "matrix_status": "MATCHED_LIMITED_FOUR_CASES",
        "source_reference_authenticated": False,
        "model_execution": False,
        "scheduler_policy_changed": False,
        "real_model_optimization_speedup_measured": False,
        "production_ready": False,
        "input_bindings": {
            "manifest_sha256": "c" * 64,
            "matrix_review_sha256": "d" * 64,
            "checkpoint_fingerprint": {"algorithm": "sha256",
                                       "files": {"model.safetensors": "e" * 64}},
        },
        "cases": cases,
        "four_cases": 4,
        "weight_payload_bytes": payload,
        "exact_bytes_step_pattern": True,
        "per_run_fixed_staged_bytes_outside_single_token_steps": fixed,
        "exact_weight_load_operation_count_pattern": True,
        "weight_load_operations_per_decoder_step": operations_per_step,
        "fixed_initial_weight_load_operations": fixed_operations,
        "median_staging_time_fraction_observed": __import__("statistics").median(fractions),
        "max_staging_time_fraction_observed": max(fractions),
        "performance_scope": {
            "timings_descriptive": True,
            "each_case_only_one_run": True,
            "prompt_length_confounded_with_staging_count": True,
            "staging_timer_includes_file_read_cpu_conversion_gpu_transfer_sync_and_python_overhead": True,
            "no_overlapped_or_batched_prefill_executed": True,
            "incremental_prompt_bytes_are_a_counter_fact_not_achieved_savings": True,
            "cannot_infer_transfer_bandwidth_or_gpu_speedup": True,
        },
        "next_falsifiable_experiment": "Test a fixed batched-prefill candidate after parity gates.",
    }


@pytest.fixture
def audit() -> dict:
    return synthetic_audit()


def test_public_stage_import_is_descriptive_and_has_zero_authority(audit: dict) -> None:
    report = review(audit)
    assert report["status"] == "REVIEW_REQUIRED"
    assert report["source_schema"] == "PHISTREAM_WEIGHT_STAGE_AUDIT_V1"
    assert report["summary"]["weight_payload_bytes_per_single_token_step"] == 269030016
    assert report["summary"]["cases"] == 4
    assert [row["case"] for row in report["cases"]] == [
        "short_1", "mixed_7", "repeat_12", "spread_24"]
    assert len(report["source_audit_sha256"]) == len(report["receipt_sha256"]) == 64
    assert report["summary"]["median_staging_share_percent"] > 80
    assert all(report[key] is False for key in (
        "independent_source_verification", "model_reexecuted",
        "transfer_bandwidth_proven", "speedup_proven", "action_authority",
        "execution_authority", "hardware_control",
    ))
    # Private fingerprints and input filenames must not be forwarded.
    assert "model.safetensors" not in json.dumps(report)


def test_reordering_source_cases_does_not_change_review(audit: dict) -> None:
    assert review(audit) == review(copy.deepcopy(audit))
    audit["cases"].reverse()
    assert review(audit)["cases"][0]["case"] == "short_1"


@pytest.mark.parametrize("change", [
    lambda a: a.update(authority=True),
    lambda a: a.update(status="COUNTER_PATTERN_NOT_FULLY_LINEAR"),
    lambda a: a.update(schema="unknown"),
    lambda a: a.update(model_execution=True),
    lambda a: a.update(source_reference_authenticated=True),
    lambda a: a.update(real_model_optimization_speedup_measured=True),
    lambda a: a.update(production_ready=True),
    lambda a: a.update(exact_bytes_step_pattern=False),
    lambda a: a.update(weight_payload_bytes=True),
    lambda a: a.update(four_cases=3),
    lambda a: a.update(fixed_initial_weight_load_operations=-1),
    lambda a: a.update(median_staging_time_fraction_observed=0.99),
    lambda a: a["input_bindings"].update(manifest_sha256="invalid"),
    lambda a: a["input_bindings"].update(checkpoint_fingerprint="secret"),
    lambda a: a["performance_scope"].update(cannot_infer_transfer_bandwidth_or_gpu_speedup=False),
    lambda a: a["cases"][0].update(id="spread_24"),
    lambda a: a["cases"][0].update(prompt_tokens=9),
    lambda a: a["cases"][0].update(generated_tokens=31),
    lambda a: a["cases"][0].update(single_token_decoder_steps=3),
    lambda a: a["cases"][0].update(recorded_staging_bytes=1),
    lambda a: a["cases"][0].update(recorded_weight_load_operations=0),
    lambda a: a["cases"][0].update(staged_bytes_minus_steps_times_payload=10),
    lambda a: a["cases"][0].update(incremental_prompt_restaging_bytes_relative_to_one_token=4),
    lambda a: a["cases"][0].update(recorded_staging_fraction=0.3),
    lambda a: a["cases"][0].update(recorded_nonstaging_seconds=0),
    lambda a: a["cases"][0].update(recorded_decoder_seconds=0.01),
    lambda a: a["cases"][0].update(recorded_staging_seconds=True),
    lambda a: a["cases"][0].update(reference_sha256="notsha"),
    lambda a: a["cases"][0].update(payload_ref="private"),
    lambda a: a["cases"].pop(),
])
def test_invalid_or_unearned_stage_claims_refused(audit: dict, change) -> None:
    change(audit)
    with pytest.raises(WeightStageReviewError):
        review(audit)


@pytest.mark.parametrize("raw", [
    b'{"schema":1,"schema":2}', b'{"x":NaN}', b'{"x":Infinity}',
    b"\xff", b"{", b" " * (128 * 1024 + 1),
])
def test_untrusted_wire_refused(tmp_path: Path, raw: bytes) -> None:
    path = tmp_path / "invalid.json"
    path.write_bytes(raw)
    with pytest.raises(WeightStageReviewError):
        _read(path)


def test_symlink_and_missing_inputs_refused(tmp_path: Path) -> None:
    target = tmp_path / "reference.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "linked.json"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unsupported")
    with pytest.raises(WeightStageReviewError):
        _read(link)
    with pytest.raises(WeightStageReviewError):
        _read(tmp_path / "missing.json")


def test_cli_reads_only_selected_audit_and_does_not_leak_paths(
    tmp_path: Path, audit: dict,
) -> None:
    path = tmp_path / "weight-stage-audit.json"
    path.write_text(json.dumps(audit), encoding="utf-8")
    original = path.read_bytes()
    command = [sys.executable, "-m", "phios.elastic_phistream_r7", "--audit", str(path)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=5)
    assert result.returncode == 0 and result.stderr == ""
    assert json.loads(result.stdout) == review(audit)
    assert path.read_bytes() == original
    assert str(path) not in result.stdout
    path.write_text("{}")
    refused = subprocess.run(command, capture_output=True, text=True, timeout=5)
    assert refused.returncode == 2
    assert json.loads(refused.stdout)["status"] == "UNAVAILABLE"
