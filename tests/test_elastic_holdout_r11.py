"""R11 research controls: frozen training-only pin selection, all holdouts.

Every test uses invented local route events; no model, CUDA or real weights.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from phios.elastic_holdout_r11 import HoldoutPolicyError, evaluate
from phios.elastic_router_r10 import RouterBridgeError

FIXTURE = (
    Path(__file__).resolve().parents[1] /
    "experiments/elastic/r10_synthetic_pocketrotor_capture.json"
)


@pytest.fixture
def capture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def assess(capture: dict, **changes) -> dict:
    parameters = {
        "layer": 0, "expert_bytes": 4096,
        "capacity_bytes": 16384, "reserve_bytes": 4096, "max_pins": 2,
    }
    parameters.update(changes)
    return evaluate(capture, **parameters)


def capture_with_groups(train: list[list[int]], a: list[list[int]],
                        b: list[list[int]]) -> dict:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["events"] = [
        {"split": split, "layer": 0, "step": step, "experts": list(group)}
        for split, groups in (("train", train), ("holdout_a", a), ("holdout_b", b))
        for step, group in enumerate(groups)
    ]
    return raw


def test_public_fixture_is_not_mistaken_for_real_speedup(capture: dict) -> None:
    result = assess(capture)
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["source_kind"] == "synthetic"
    assert result["training_steps"] == 3
    assert result["training_expert_uses"] == 6
    assert result["selected_train_only_pins"] == 2
    assert result["evaluated_holdouts"] == 2
    assert [row["holdout"] for row in result["holdouts"]] == ["holdout_a", "holdout_b"]
    assert result["summary"]["holdouts_evaluated"] == 2
    assert result["summary"]["total_signed_stage_byte_delta"] == 0
    assert result["summary"]["holdouts_with_equal_logical_bytes"] == 2
    assert result["summary"]["all_holdouts_lower_logical_bytes"] is False
    assert len(result["source_capture_sha256"]) == 64
    assert len(result["frozen_policy_sha256"]) == 64
    assert len(result["receipt_sha256"]) == 64
    for key in ("routing_source_authenticated", "real_model_executed",
                "actual_weight_transfers_measured", "output_parity_checked",
                "speedup_proven", "automatic_promotion", "action_authority",
                "execution_authority", "hardware_control"):
        assert result[key] is False
    # Raw route selections and source strings never appear in the review.
    output = json.dumps(result)
    assert '"experts"' not in output
    assert "fixture-only" not in output


def test_holdout_data_cannot_change_frozen_train_pin_policy(capture: dict) -> None:
    first = assess(capture)
    for event in capture["events"]:
        if event["split"] == "holdout_b":
            event["experts"] = [0, 1]
    second = assess(capture)
    assert first["frozen_policy_sha256"] != second["frozen_policy_sha256"]
    # Full capture SHA is intentionally bound into R10 reports. Extract the
    # stable training-only ranking by comparing the selected pin count and
    # explicit behavior on a frozen holdout.
    assert first["selected_train_only_pins"] == second["selected_train_only_pins"] == 2
    assert first["holdouts"][0]["train_pin_lru_stage_bytes"] == (
        second["holdouts"][0]["train_pin_lru_stage_bytes"]
    )


def test_training_only_policy_can_help_one_holdout_and_hurt_another() -> None:
    source = capture_with_groups(
        [[0], [0], [1]],
        [[0], [1], [2], [0], [1], [2]],
        [[1], [2], [1], [2]],
    )
    result = assess(source, capacity_bytes=8192, reserve_bytes=0, max_pins=1)
    assert result["selected_train_only_pins"] == 1
    assert result["summary"]["holdouts_with_lower_logical_bytes"] == 1
    assert result["summary"]["holdouts_with_higher_logical_bytes"] == 1
    assert result["summary"]["all_holdouts_lower_logical_bytes"] is False
    assert result["summary"]["total_unpinned_lru_stage_bytes"] == 8 * 4096
    assert result["summary"]["total_train_pin_lru_stage_bytes"] == 10 * 4096
    assert result["summary"]["total_signed_stage_byte_delta"] == -2 * 4096
    assert result["summary"]["relative_total_logical_stage_delta_percent"] < 0
    assert result["speedup_proven"] is False


def test_max_pins_zero_is_identical_to_unpinned_lru(capture: dict) -> None:
    result = assess(capture, max_pins=0)
    assert result["selected_train_only_pins"] == 0
    assert result["summary"]["holdouts_with_equal_logical_bytes"] == 2
    assert all(row["stage_byte_delta_vs_unpinned_lru"] == 0
               for row in result["holdouts"])


def test_pin_budget_keeps_one_unpinned_slot(capture: dict) -> None:
    result = assess(capture, max_pins=16, capacity_bytes=3 * 4096,
                    reserve_bytes=0)
    assert result["selected_train_only_pins"] == 2
    assert all(row["train_pin_peak_resident_bytes"] <= 3 * 4096
               for row in result["holdouts"])


def test_two_slot_requirement_holds_without_fake_experiment(capture: dict) -> None:
    result = assess(capture, capacity_bytes=8192, reserve_bytes=4096)
    assert result["status"] == "HELD"
    assert result["evaluated_holdouts"] == 0
    assert "summary" not in result
    assert result["hardware_control"] is False


def test_unauthenticated_native_label_is_not_provenance(capture: dict) -> None:
    capture["source"]["kind"] = "operator_asserted_native"
    result = assess(capture)
    assert result["source_kind"] == "operator_asserted_native"
    assert result["routing_source_authenticated"] is False


def test_repeatable_output(capture: dict) -> None:
    assert assess(capture) == assess(copy.deepcopy(capture))


def test_one_holdout_is_not_multi_holdout_evidence(capture: dict) -> None:
    capture["events"] = [row for row in capture["events"]
                         if row["split"] != "holdout_b"]
    with pytest.raises(HoldoutPolicyError, match="at least two"):
        assess(capture)


@pytest.mark.parametrize("changes", [
    {"layer": 7},
    {"layer": True},
    {"max_pins": -1},
    {"max_pins": 17},
    {"max_pins": True},
    {"expert_bytes": 0},
    {"expert_bytes": True},
    {"capacity_bytes": 0},
    {"capacity_bytes": True},
    {"reserve_bytes": -1},
    {"reserve_bytes": 999999},
    {"reserve_bytes": True},
])
def test_invalid_budget_or_selection_rejected(capture: dict, changes: dict) -> None:
    with pytest.raises(HoldoutPolicyError):
        assess(capture, **changes)


@pytest.mark.parametrize("change", [
    lambda c: c.update(source="authenticated"),
    lambda c: c["source"].update(token_text_recorded=True),
    lambda c: c["events"][0].update(experts=[True]),
    lambda c: c["events"][0].update(step=99),
    lambda c: c["events"].pop(),
])
def test_invalid_native_capture_rejected(capture: dict, change) -> None:
    change(capture)
    with pytest.raises(RouterBridgeError):
        assess(capture)


def test_too_many_holdout_uses_are_refused_not_cherry_picked(capture: dict) -> None:
    capture["events"] = [
        {"split": split, "layer": 0, "step": step, "experts": [0, 1]}
        for split, length in (("train", 2), ("holdout_a", 4096), ("holdout_b", 2))
        for step in range(length)
    ]
    with pytest.raises(RouterBridgeError, match="R9 event budget"):
        assess(capture)


def test_cli_success_held_invalid(tmp_path: Path, capture: dict) -> None:
    path = tmp_path / "routes.json"
    path.write_text(json.dumps(capture), encoding="utf-8")
    original = path.read_bytes()
    cmd = [sys.executable, "-m", "phios.elastic_holdout_r11",
           "--capture", str(path), "--layer", "0",
           "--expert-bytes", "4096", "--capacity-bytes", "16384",
           "--reserve-bytes", "4096", "--max-pins", "2"]
    success = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
    assert success.returncode == 0, success.stderr
    assert json.loads(success.stdout) == assess(capture)
    assert path.read_bytes() == original
    assert str(path) not in success.stdout
    held = subprocess.run(cmd[:-4] + ["--capacity-bytes", "4096"],
                          capture_output=True, text=True, timeout=8)
    assert held.returncode == 3
    assert json.loads(held.stdout)["status"] == "HELD"
    path.write_text("{}", encoding="utf-8")
    invalid = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
    assert invalid.returncode == 2
    assert json.loads(invalid.stdout)["status"] == "UNAVAILABLE"
