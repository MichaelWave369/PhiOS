"""R12 all-layer census tests use synthetic, local-only PocketRotor captures."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from phios.elastic_census_r12 import AllLayerCensusError, census
from phios.elastic_holdout_r11 import evaluate as evaluate_layer
from phios.elastic_router_r10 import RouterBridgeError

FIXTURE = (
    Path(__file__).resolve().parents[1] /
    "experiments/elastic/r10_synthetic_pocketrotor_capture.json"
)
PARAMETERS = {
    "expert_bytes": 4096,
    "capacity_bytes": 16384,
    "reserve_bytes": 4096,
    "max_pins": 2,
}


@pytest.fixture
def capture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def make_capture(layers: int, holdouts: int = 2) -> dict:
    """Complete, gapless synthetic capture with every layer in every split."""
    result = json.loads(FIXTURE.read_text(encoding="utf-8"))
    splits = ["train"] + [f"holdout_{i}" for i in range(holdouts)]
    result["events"] = [
        {"split": split, "layer": layer, "step": step,
         "experts": [(layer + step) % 8, (layer + step + 1) % 8]}
        for split in splits
        for step in range(2)
        for layer in range(layers)
    ]
    return result


def test_every_declared_layer_and_holdout_are_reported(capture: dict) -> None:
    report = census(capture, **PARAMETERS)
    assert report["status"] == "REVIEW_REQUIRED"
    assert report["routed_layers_declared"] == 2
    assert report["holdout_splits_declared"] == 2
    assert report["expected_layer_holdout_cells"] == 4
    assert report["evaluated_layer_holdout_cells"] == 4
    assert report["scope"] == "isolated_per_layer_cache_replay_not_shared_vram_budget"
    assert report["each_layer_cache_is_independent"] is True
    assert [layer["layer"] for layer in report["layer_results"]] == [0, 1]
    assert [cell["holdout"] for cell in report["layer_results"][0]["holdout_cells"]] == [
        "holdout_a", "holdout_b",
    ]
    assert report["summary"]["cells"] == 4
    assert (report["summary"]["improved_cells"] + report["summary"]["unchanged_cells"] +
            report["summary"]["regressed_cells"]) == 4
    assert len(report["source_capture_sha256"]) == len(report["receipt_sha256"]) == 64
    for field in (
        "routing_source_authenticated", "model_executed",
        "real_weight_transfers_measured", "model_output_parity_checked",
        "wall_time_measured", "speedup_proven", "statistical_significance_established",
        "automatic_promotion", "action_authority", "execution_authority",
        "hardware_control",
    ):
        assert report[field] is False
    serialized = json.dumps(report)
    assert "fixture-only" not in serialized
    assert '"experts"' not in serialized
    assert "model.safetensors" not in serialized


def test_census_matches_every_unmodified_r11_layer_receipt(capture: dict) -> None:
    all_layers = census(capture, **PARAMETERS)
    totals = {"left": 0, "right": 0, "delta": 0, "preload": 0}
    for row in all_layers["layer_results"]:
        independent = evaluate_layer(capture, layer=row["layer"], **PARAMETERS)
        assert independent["frozen_policy_sha256"] == row["frozen_train_only_policy_sha256"]
        assert independent["selected_train_only_pins"] == row["train_selected_pin_count"]
        assert len(independent["holdouts"]) == len(row["holdout_cells"])
        for original, rendered in zip(independent["holdouts"], row["holdout_cells"]):
            assert original["holdout"] == rendered["holdout"]
            assert original["unpinned_lru_stage_bytes"] == rendered["unpinned_lru_staged_bytes"]
            assert original["train_pin_lru_stage_bytes"] == rendered["train_pin_lru_staged_bytes"]
            assert original["stage_byte_delta_vs_unpinned_lru"] == (
                rendered["signed_delta_vs_unpinned_lru_bytes"]
            )
            totals["left"] += rendered["unpinned_lru_staged_bytes"]
            totals["right"] += rendered["train_pin_lru_staged_bytes"]
            totals["preload"] += rendered["train_pin_preload_bytes"]
        totals["delta"] += row["layer_signed_byte_delta"]
    result = all_layers["summary"]
    assert result["total_unpinned_lru_staged_bytes"] == totals["left"]
    assert result["total_train_pin_lru_staged_bytes"] == totals["right"]
    assert result["total_train_pin_preload_bytes_across_independent_replays"] == (
        totals["preload"]
    )
    assert result["total_signed_logical_staged_bytes_delta"] == totals["delta"]
    assert totals["left"] - totals["right"] == totals["delta"]


def test_all_layer_policy_is_holdout_blind(capture: dict) -> None:
    first = census(capture, **PARAMETERS)
    for event in capture["events"]:
        if event["split"] == "holdout_b":
            event["experts"] = [0, 1]
    second = census(capture, **PARAMETERS)
    assert first["source_capture_sha256"] != second["source_capture_sha256"]
    assert [row["frozen_train_only_policy_sha256"] for row in first["layer_results"]] == [
        row["frozen_train_only_policy_sha256"] for row in second["layer_results"]
    ]
    assert [row["train_selected_pin_count"] for row in first["layer_results"]] == [
        row["train_selected_pin_count"] for row in second["layer_results"]
    ]


def test_zero_pins_is_all_layer_noop_control(capture: dict) -> None:
    result = census(capture, **{**PARAMETERS, "max_pins": 0})
    assert all(row["train_selected_pin_count"] == 0 for row in result["layer_results"])
    assert result["summary"]["total_signed_logical_staged_bytes_delta"] == 0
    assert result["summary"]["unchanged_cells"] == 4


def test_full_24_layer_census_does_not_sample(capture: dict) -> None:
    result = census(make_capture(24), **PARAMETERS)
    assert result["routed_layers_declared"] == 24
    assert result["evaluated_layer_holdout_cells"] == 48
    assert len(result["layer_results"]) == 24
    assert sum(len(row["holdout_cells"]) for row in result["layer_results"]) == 48
    assert all(row["train_selected_pin_count"] <= 2 for row in result["layer_results"])


def test_maximum_layer_or_matrix_bounds_fail_instead_of_truncating(capture: dict) -> None:
    with pytest.raises(AllLayerCensusError, match="census bounds"):
        census(make_capture(33), **PARAMETERS)
    with pytest.raises(AllLayerCensusError, match="census bounds"):
        census(make_capture(16, holdouts=8), **PARAMETERS)


def test_two_slot_budget_hold_has_no_partial_layer_outcomes(capture: dict) -> None:
    result = census(capture, **{**PARAMETERS, "capacity_bytes": 4096,
                               "reserve_bytes": 0})
    assert result["status"] == "HELD"
    assert result["evaluated_layer_holdout_cells"] == 0
    assert result["layer_results"] is None
    assert result["summary"] is None
    assert result["hardware_control"] is False
    assert result["automatic_promotion"] is False


def test_capture_with_one_holdout_is_rejected(capture: dict) -> None:
    capture["events"] = [
        event for event in capture["events"] if event["split"] != "holdout_b"
    ]
    with pytest.raises(AllLayerCensusError, match="two or more"):
        census(capture, **PARAMETERS)


def test_too_many_accesses_in_one_cell_fail_whole_study(capture: dict) -> None:
    capture["events"] = [
        {"split": split, "layer": layer, "step": step, "experts": [0, 1]}
        for split, count in (
            ("train", 2), ("holdout_a", 2), ("holdout_b", 4096)
        )
        for step in range(count)
        for layer in range(2)
    ]
    with pytest.raises(RouterBridgeError, match="R9 event budget"):
        census(capture, **PARAMETERS)


def test_no_hindsight_based_on_layer_results(capture: dict) -> None:
    first = census(capture, **PARAMETERS)
    altered = copy.deepcopy(capture)
    altered["events"] = [
        e for e in altered["events"] if e["split"] != "holdout_b"
    ]
    with pytest.raises(AllLayerCensusError):
        census(altered, **PARAMETERS)
    assert first["expected_layer_holdout_cells"] == 4


@pytest.mark.parametrize("changes", [
    {"expert_bytes": 0},
    {"expert_bytes": True},
    {"expert_bytes": 16 * 1024 * 1024 + 1},
    {"capacity_bytes": 0},
    {"capacity_bytes": True},
    {"capacity_bytes": 2 * 1024**3 + 1},
    {"reserve_bytes": -1},
    {"reserve_bytes": True},
    {"reserve_bytes": 16385},
    {"max_pins": -1},
    {"max_pins": True},
    {"max_pins": 17},
])
def test_invalid_parameters_refused(capture: dict, changes: dict) -> None:
    with pytest.raises(AllLayerCensusError):
        census(capture, **{**PARAMETERS, **changes})


@pytest.mark.parametrize("edit", [
    lambda c: c.update(provenance="certified"),
    lambda c: c["source"].update(token_text_recorded=True),
    lambda c: c["events"][0].update(experts=[0, 0]),
    lambda c: c["events"][0].update(step=9),
    lambda c: c["events"].pop(),
])
def test_invalid_source_capture_refused(capture: dict, edit) -> None:
    edit(capture)
    with pytest.raises(RouterBridgeError):
        census(capture, **PARAMETERS)


def test_cli_returns_utf8_json_and_does_not_modify_inputs(
    tmp_path: Path, capture: dict,
) -> None:
    location = tmp_path / "native-router-input.json"
    location.write_text(json.dumps(capture), encoding="utf-8")
    before = location.read_bytes()
    cmd = [
        sys.executable, "-m", "phios.elastic_census_r12",
        "--capture", str(location), "--expert-bytes", "4096",
        "--capacity-bytes", "16384", "--reserve-bytes", "4096",
        "--max-pins", "2",
    ]
    r = subprocess.run(cmd, text=True, capture_output=True, timeout=15)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == census(capture, **PARAMETERS)
    assert before == location.read_bytes()
    assert str(location) not in r.stdout
    held = subprocess.run(
        cmd[:-4] + ["--capacity-bytes", "4096", "--reserve-bytes", "0"],
        text=True, capture_output=True, timeout=15,
    )
    assert held.returncode == 3
    assert json.loads(held.stdout)["status"] == "HELD"
    location.write_text("{}", encoding="utf-8")
    invalid = subprocess.run(cmd, text=True, capture_output=True, timeout=15)
    assert invalid.returncode == 2
    assert json.loads(invalid.stdout)["status"] == "UNAVAILABLE"
