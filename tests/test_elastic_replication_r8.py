"""R8 contract tests use invented synthetic JSON, not actual model receipts."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from phios.elastic_replication_r8 import ReplicationJoinError, join

EXAMPLE = Path(__file__).resolve().parents[1] / "experiments/elastic/r8_illustrative_joint.json"


@pytest.fixture
def inputs() -> tuple[dict, dict]:
    raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert raw["fixture_notice"] == "SYNTHETIC_TEST_ONLY_NOT_MEASURED"
    return raw["stage"], raw["replication"]


def test_joint_review_binds_reference_checkpoint_and_conserves_counts(
    inputs: tuple[dict, dict],
) -> None:
    stage, replication = inputs
    result = join(stage, replication)
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["summary"]["stage_audit_cases"] == 4
    assert result["summary"]["combined_matched_pairs"] == 20
    assert result["summary"]["combined_reported_complete_parity_executions"] == 48
    assert result["summary"]["combined_reported_greedy_ids_matched"] == 1536
    assert result["summary"]["combined_reported_sparse_logits_matched"] == 13774
    assert result["summary"]["original_spread_24"]["median_paired_decoder_gain_percent"] == 39.684
    assert result["summary"]["replication_spread_24"]["median_paired_decoder_gain_percent"] == 40.5861
    assert result["summary"]["reported_replication_minus_original_gain_percentage_points"] == 0.9021
    assert result["summary"]["stage_median_share_percent"] > 80
    assert len(result["receipt_sha256"]) == 64
    assert all(result[field] is False for field in (
        "original_checkpoint_bytes_rehashed", "real_model_executed_here",
        "external_reference_authenticated", "independent_replication_attested",
        "statistical_significance_established", "general_speedup_proven",
        "automatic_scheduler_promotion", "action_authority",
        "execution_authority", "hardware_control",
    ))
    dumped = json.dumps(result)
    assert "model.safetensors" not in dumped
    assert '"checkpoint_fingerprint"' not in dumped


def test_deterministic_same_inputs(inputs: tuple[dict, dict]) -> None:
    a, b = inputs
    assert join(a, b) == join(copy.deepcopy(a), copy.deepcopy(b))


def test_source_cases_permutation_keeps_case_summary(inputs: tuple[dict, dict]) -> None:
    a, b = inputs
    baseline = join(a, b)
    a["cases"].reverse()
    result = join(a, b)
    assert result["summary"] == baseline["summary"]
    assert result["stage_audit_sha256"] != baseline["stage_audit_sha256"]


def test_nonqualifying_replication_is_inconclusive_not_success(
    inputs: tuple[dict, dict],
) -> None:
    a, b = inputs
    b["replication"]["candidate_faster_pair_count"] = 4
    b["replication"]["review_thresholds_met"] = False
    b["replication"]["qualification"] = "INCONCLUSIVE_OR_NO_PERFORMANCE_BENEFIT"
    b["status"] = "REPLICATION_MATCHED_BUT_PERFORMANCE_NOT_QUALIFIED"
    b["combined"]["batched_faster_pairs"] = 16
    result = join(a, b)
    assert result["status"] == "INCONCLUSIVE"
    assert result["summary"]["replication_spread_24"]["review_threshold_met"] is False
    assert result["general_speedup_proven"] is False


@pytest.mark.parametrize("change", [
    lambda a, b: b.update(status="PROVEN_GLOBAL_SPEEDUP"),
    lambda a, b: b.update(schema="WRONG"),
    lambda a, b: b.update(production_promoted=True),
    lambda a, b: b.update(statistical_significance_established=True),
    lambda a, b: b.update(production_scheduler_unchanged=False),
    lambda a, b: b.update(model_execution=True),
    lambda a, b: b.update(original_seed=0),
    lambda a, b: b.update(source_reference_authenticated=True),
    lambda a, b: b.update(extra="private"),
    lambda a, b: b.update(reference_sha256="0" * 64),
    lambda a, b: b.update(checkpoint_fingerprint={"algorithm": "sha256", "files": {}}),
    lambda a, b: b.update(replication_plan_sha256="not-a-hash"),
    lambda a, b: b["original_spread_24"].update(pairs=5),
    lambda a, b: b["original_spread_24"].update(candidate_faster_pair_count=5),
    lambda a, b: b["original_spread_24"].update(greedy_id_matches=0),
    lambda a, b: b["original_spread_24"].update(review_thresholds_met=False),
    lambda a, b: b["original_spread_24"].update(median_paired_relative_gain=float("nan")),
    lambda a, b: b["original_spread_24"].update(median_paired_relative_gain=True),
    lambda a, b: b["replication"].update(seed=369),
    lambda a, b: b["replication"].update(warmups=0),
    lambda a, b: b["replication"].update(greedy_id_matches=200),
    lambda a, b: b["replication"].update(review_thresholds_met=False),
    lambda a, b: b["combined"].update(greedy_id_matches=100),
    lambda a, b: b["combined"].update(sparse_logit_matches=100),
    lambda a, b: b["combined"].update(batched_faster_pairs=2),
    lambda a, b: b["combined"].update(paired_comparisons=19),
    lambda a, b: b["combined"].update(
        replication_minus_original_spread_median_gain_percentage_points=20),
    lambda a, b: a.update(model_execution=True),
    lambda a, b: a["cases"][-1].update(reference_sha256="9" * 64),
])
def test_mismatched_or_unsafe_reports_refuse(
    inputs: tuple[dict, dict], change,
) -> None:
    a, b = inputs
    change(a, b)
    with pytest.raises(ReplicationJoinError):
        join(a, b)


def test_cli_keeps_local_files_unchanged_and_hides_paths(
    inputs: tuple[dict, dict], tmp_path: Path,
) -> None:
    a, b = inputs
    first = tmp_path / "original-stage.json"
    second = tmp_path / "original-replication.json"
    first.write_text(json.dumps(a), encoding="utf-8")
    second.write_text(json.dumps(b), encoding="utf-8")
    before = first.read_bytes(), second.read_bytes()
    command = [sys.executable, "-m", "phios.elastic_replication_r8",
               "--stage-audit", str(first), "--replication-review", str(second)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=8)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == join(a, b)
    assert (first.read_bytes(), second.read_bytes()) == before
    assert str(tmp_path) not in result.stdout
    b["reference_sha256"] = "a" * 63
    second.write_text(json.dumps(b), encoding="utf-8")
    error = subprocess.run(command, capture_output=True, text=True, timeout=8)
    assert error.returncode == 2
    assert json.loads(error.stdout)["status"] == "UNAVAILABLE"


def test_nonregular_and_duplicate_json_files_are_refused(
    inputs: tuple[dict, dict], tmp_path: Path,
) -> None:
    a, b = inputs
    first = tmp_path / "stage.json"
    first.write_text(json.dumps(a), encoding="utf-8")
    link = tmp_path / "link.json"
    try:
        link.symlink_to(first)
    except (OSError, NotImplementedError):
        pytest.skip("symlink not available")
    bfile = tmp_path / "replication.json"
    bfile.write_text(json.dumps(b), encoding="utf-8")
    cmd = [sys.executable, "-m", "phios.elastic_replication_r8",
           "--stage-audit", str(link), "--replication-review", str(bfile)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
    assert result.returncode == 2
    bfile.write_text('{"schema": "A", "schema": "B"}', encoding="utf-8")
    cmd[4] = str(first)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
    assert result.returncode == 2
