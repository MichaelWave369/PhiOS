"""R3 tests use illustrative values; never benchmark a host or execute a workload."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from phios.elastic_compare import PairedStudyError, _read_study, compare


EXAMPLE = Path(__file__).resolve().parents[1] / "experiments/elastic/r3_pairs.json"


@pytest.fixture
def study() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_stable_descriptive_report_has_no_execution_authority(study: dict) -> None:
    result = compare(study)
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["pair_count"] == 6
    assert result["order_counts"] == {"AB": 3, "BA": 3}
    assert result["summary"]["wins"] == 5
    assert result["summary"]["losses"] == 1
    assert result["summary"]["r2_digest_labels_present"] == 0
    assert result["better"] == "lower"
    assert result["unit"] == "ms"
    assert len(result["source_sha256"]) == len(result["receipt_sha256"]) == 64
    assert all(result[key] is False for key in (
        "action_authority", "execution_authority", "hardware_control",
        "statistical_significance_claimed", "performance_improvement_proven",
    ))


def test_pair_order_in_manifest_does_not_change_receipt(study: dict) -> None:
    first = compare(study)
    study["pairs"].reverse()
    assert compare(study) == first


def test_higher_is_better_has_correct_sign(study: dict) -> None:
    study["experiment"]["metric"] = "tokens_per_second"
    for pair in study["pairs"]:
        pair["baseline"]["samples"] = 1
        pair["candidate"]["samples"] = 1
    result = compare(study)
    assert result["better"] == "higher"
    assert result["summary"]["wins"] == 1
    assert result["summary"]["losses"] == 5
    assert result["summary"]["median_paired_improvement_percent"] < 0


def test_failed_quality_gate_is_held_even_with_faster_metrics(study: dict) -> None:
    study["pairs"][0]["candidate"]["passed"] = False
    report = compare(study)
    assert report["status"] == "HELD"
    assert report["summary"]["candidate_failed"] == 1
    assert report["performance_improvement_proven"] is False


def test_r2_digest_labels_are_not_claimed_authenticated(study: dict) -> None:
    study["pairs"][0]["baseline"]["r2_receipt_sha256"] = "b" * 64
    report = compare(study)
    assert report["summary"]["r2_digest_labels_present"] == 1
    assert report["scope"] == "paired_operator_supplied_unverified"


@pytest.mark.parametrize("change", [
    lambda x: x.update(authorization=True),
    lambda x: x.update(schema_version="unknown"),
    lambda x: x["experiment"].update(source="independently_verified"),
    lambda x: x["experiment"].update(metric="my-preferred-score"),
    lambda x: x["experiment"].update(declared_source="verified"),
    lambda x: x["experiment"].update(workload_sha256="bad"),
    lambda x: x["pairs"].pop(),
    lambda x: x["pairs"].append(copy.deepcopy(x["pairs"][0])),
    lambda x: x["pairs"][0].update(order="AA"),
    lambda x: x["pairs"][0].update(pair_id="../bad"),
    lambda x: x["pairs"][0]["baseline"].update(value=0),
    lambda x: x["pairs"][0]["baseline"].update(value=True),
    lambda x: x["pairs"][0]["baseline"].update(value=-1),
    lambda x: x["pairs"][0]["baseline"].update(value=float("nan")),
    lambda x: x["pairs"][0]["candidate"].update(samples=99),
    lambda x: x["pairs"][0]["candidate"].update(samples=True),
    lambda x: x["pairs"][0]["candidate"].update(passed="true"),
    lambda x: x["pairs"][0]["candidate"].update(r2_receipt_sha256="unverified"),
    lambda x: [p.update(order="AB") for p in x["pairs"]],
])
def test_malformed_or_unbalanced_studies_refuse(study: dict, change) -> None:
    change(study)
    with pytest.raises(PairedStudyError):
        compare(study)


@pytest.mark.parametrize("raw", [
    b'{"schema_version":1,"schema_version":2}',
    b'{"x": NaN}', b'{"x":Infinity}', b'{', b'\xff',
    b' ' * 262145,
])
def test_malformed_wire_or_oversized_data_refuses(tmp_path: Path, raw: bytes) -> None:
    path = tmp_path / "study.json"
    path.write_bytes(raw)
    with pytest.raises(PairedStudyError):
        _read_study(path)


def test_cli_uses_only_explicit_local_input_and_returns_nonzero_on_invalid(
    tmp_path: Path, study: dict,
) -> None:
    path = tmp_path / "study.json"
    path.write_text(json.dumps(study), encoding="utf-8")
    previous = path.read_bytes()
    cmd = [sys.executable, "-m", "phios.elastic_compare", "--study", str(path)]
    output = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    assert output.returncode == 0
    assert json.loads(output.stdout) == compare(study)
    assert path.read_bytes() == previous
    assert str(path) not in output.stdout
    study["pairs"][1]["baseline"]["passed"] = False
    path.write_text(json.dumps(study), encoding="utf-8")
    held = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    assert held.returncode == 3
    assert json.loads(held.stdout)["status"] == "HELD"
    missing = subprocess.run(cmd[:-1] + [str(tmp_path / "missing")], capture_output=True,
                             text=True, timeout=5)
    assert missing.returncode == 2
    assert json.loads(missing.stdout)["status"] == "UNAVAILABLE"


def test_symlink_refusal(tmp_path: Path, study: dict) -> None:
    target = tmp_path / "actual.json"
    target.write_text(json.dumps(study), encoding="utf-8")
    linked = tmp_path / "linked.json"
    linked.symlink_to(target)
    with pytest.raises(PairedStudyError):
        _read_study(linked)
