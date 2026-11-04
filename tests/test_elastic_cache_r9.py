"""R9 simulated cache accounting, refusal and CLI tests.

Uses only explicit synthetic metadata, never host RAM, GPU, checkpoints or CUDA.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from phios.elastic_cache_r9 import CacheShadowError, _read, simulate

FIXTURE = Path(__file__).resolve().parents[1] / "experiments/elastic/r9_synthetic_cache.json"


@pytest.fixture
def study() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_known_reuse_is_accounted_without_a_speed_claim(study: dict) -> None:
    result = simulate(study)
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["baseline_logical_staged_bytes"] == 20
    assert result["budget_bytes"] == {
        "capacity": 9, "reserve": 0, "effective": 9, "mandatory_pinned": 2,
    }
    candidate = result["candidate"]
    assert candidate["logical_staged_bytes"] == 9
    assert candidate["logical_stage_bytes_delta_vs_baseline"] == 11
    assert candidate["relative_logical_stage_reduction_percent"] == 55.0
    assert candidate["hypothetical_preload_bytes"] == 2
    assert candidate["cache_hits"] == 4
    assert candidate["cache_misses"] == 2
    assert candidate["evictions"] == 0
    assert candidate["uncacheable_accesses"] == 0
    assert candidate["peak_hypothetical_resident_bytes"] == 9
    assert candidate["final_hypothetical_resident_bytes"] == 9
    assert len(result["source_sha256"]) == len(result["receipt_sha256"]) == 64
    assert all(result[key] is False for key in (
        "physical_transfer_bytes_measured", "wall_time_measured",
        "model_output_parity_checked", "performance_improvement_proven",
        "automatic_promotion", "action_authority",
        "execution_authority", "hardware_control",
    ))
    # No original resource IDs or trace entries appear in public summaries.
    assert "layer-a" not in json.dumps(result)


def test_resource_list_order_does_not_change_receipt(study: dict) -> None:
    expected = simulate(study)
    study["resources"].reverse()
    assert simulate(study) == expected
    assert simulate(copy.deepcopy(study)) == expected


def test_pins_exceed_effective_budget_hold_without_eviction(study: dict) -> None:
    study["budget"]["capacity_bytes"] = 5
    study["resources"][0]["pinned"] = True
    result = simulate(study)
    assert result["status"] == "HELD"
    assert result["reason"] == "mandatory_pins_exceed_effective_budget"
    assert result["budget_bytes"]["mandatory_pinned"] == 6
    assert result["candidate"] is None
    assert result["action_authority"] is False


def test_reserved_capacity_is_never_spent(study: dict) -> None:
    study["budget"] = {"capacity_bytes": 12, "reserve_bytes": 3}
    result = simulate(study)
    assert result["budget_bytes"]["effective"] == 9
    assert result["candidate"]["peak_hypothetical_resident_bytes"] == 9


def test_true_lru_eviction_protects_pins(study: dict) -> None:
    study["budget"]["capacity_bytes"] = 7
    study["accesses"] = ["layer-a", "layer-b", "layer-a", "layer-c", "layer-b"]
    report = simulate(study)
    item = report["candidate"]
    assert report["baseline_logical_staged_bytes"] == 16
    assert item["logical_staged_bytes"] == 16
    assert item["evictions"] == 3
    assert item["cache_hits"] == 1
    assert item["cache_misses"] == 4
    assert item["peak_hypothetical_resident_bytes"] <= 7
    assert item["final_hypothetical_resident_bytes"] >= 2
    assert item["relative_logical_stage_reduction_percent"] == 0


def test_oversize_unpinned_resource_bypasses_cache(study: dict) -> None:
    study["budget"]["capacity_bytes"] = 5
    study["accesses"] = ["layer-a", "layer-a", "layer-b", "layer-b", "layer-c"]
    report = simulate(study)
    item = report["candidate"]
    assert item["uncacheable_accesses"] == 2
    assert item["cache_misses"] == 3
    assert item["cache_hits"] == 2
    assert item["logical_staged_bytes"] == 13
    assert item["peak_hypothetical_resident_bytes"] == 5
    assert item["evictions"] == 0


def test_unused_pin_makes_candidate_worse(study: dict) -> None:
    study["budget"]["capacity_bytes"] = 7
    study["resources"] = [
        {"id": "layer-a", "bytes": 4, "pinned": True},
        {"id": "layer-b", "bytes": 3, "pinned": False},
    ]
    study["accesses"] = ["layer-b"]
    report = simulate(study)
    assert report["baseline_logical_staged_bytes"] == 3
    assert report["candidate"]["logical_staged_bytes"] == 7
    assert report["candidate"]["logical_stage_bytes_delta_vs_baseline"] == -4
    assert report["candidate"]["relative_logical_stage_reduction_percent"] < 0


@pytest.mark.parametrize("change", [
    lambda x: x.update(schema_version="unknown"),
    lambda x: x.update(scheduler_authority=True),
    lambda x: x.update(source="verified_hardware"),
    lambda x: x.update(workload_sha256="not-a-digest"),
    lambda x: x.update(scenario="../../secret"),
    lambda x: x["budget"].update(capacity_bytes=0),
    lambda x: x["budget"].update(capacity_bytes=True),
    lambda x: x["budget"].update(reserve_bytes=-1),
    lambda x: x["budget"].update(reserve_bytes=10),
    lambda x: x["budget"].update(other_gpu_memory=9000),
    lambda x: x.update(resources=[]),
    lambda x: x["resources"].append(copy.deepcopy(x["resources"][0])),
    lambda x: x["resources"][0].update(id="missing/file"),
    lambda x: x["resources"][0].update(bytes=0),
    lambda x: x["resources"][0].update(bytes=2**40),
    lambda x: x["resources"][0].update(bytes=True),
    lambda x: x["resources"][0].update(pinned=1),
    lambda x: x["resources"][0].update(path="/private/model"),
    lambda x: x.update(accesses=[]),
    lambda x: x.update(accesses=["missing"]),
    lambda x: x.update(accesses=["layer-a"] * 4097),
    lambda x: x.update(accesses=[True]),
    lambda x: x.update(accesses="layer-a"),
])
def test_bad_schema_budget_or_trace_refuses(study: dict, change) -> None:
    change(study)
    with pytest.raises(CacheShadowError):
        simulate(study)


@pytest.mark.parametrize("wire", [
    b'{"x":1,"x":2}', b'{"v":NaN}', b'{"v":Infinity}',
    b"\xff", b"{", b" " * (512 * 1024 + 1),
])
def test_untrusted_json_refused(tmp_path: Path, wire: bytes) -> None:
    path = tmp_path / "bad.json"
    path.write_bytes(wire)
    with pytest.raises(CacheShadowError):
        _read(path)


def test_symlink_directory_and_missing_path_refuse(tmp_path: Path) -> None:
    original = tmp_path / "real.json"
    original.write_text("{}", encoding="utf-8")
    alias = tmp_path / "alias.json"
    try:
        alias.symlink_to(original)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unsupported")
    for path in (alias, tmp_path, tmp_path / "missing.json"):
        with pytest.raises(CacheShadowError):
            _read(path)


def test_cli_success_hold_and_invalid_exit_codes(study: dict, tmp_path: Path) -> None:
    path = tmp_path / "study.json"
    path.write_text(json.dumps(study), encoding="utf-8")
    command = [sys.executable, "-m", "phios.elastic_cache_r9", "--study", str(path)]
    before = path.read_bytes()
    success = subprocess.run(command, text=True, capture_output=True, timeout=8)
    assert success.returncode == 0, success.stderr
    assert json.loads(success.stdout) == simulate(study)
    assert str(path) not in success.stdout
    assert path.read_bytes() == before

    study["budget"]["capacity_bytes"] = 1
    path.write_text(json.dumps(study), encoding="utf-8")
    held = subprocess.run(command, text=True, capture_output=True, timeout=8)
    assert held.returncode == 3
    assert json.loads(held.stdout)["status"] == "HELD"

    study["budget"]["capacity_bytes"] = 0
    path.write_text(json.dumps(study), encoding="utf-8")
    refused = subprocess.run(command, text=True, capture_output=True, timeout=8)
    assert refused.returncode == 2
    assert json.loads(refused.stdout)["status"] == "UNAVAILABLE"
