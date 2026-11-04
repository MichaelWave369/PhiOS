"""R13 shared-budget shadow cache tests. All source IDs/sizes are synthetic.

No model, GPU, network, checkpoint, allocator or physical transfers used.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from phios.elastic_router_r10 import RouterBridgeError, _hash
from phios.elastic_shared_r13 import SharedCacheError, evaluate

ROOT = Path(__file__).resolve().parents[1] / "experiments/elastic"
CAPTURE = ROOT / "r10_synthetic_pocketrotor_capture.json"
FOOTPRINTS = ROOT / "r13_synthetic_expert_footprints.json"
ARGS = {"capacity_bytes": 81920, "reserve_bytes": 8192, "max_pins": 4}


@pytest.fixture
def source() -> tuple[dict, dict]:
    return (json.loads(CAPTURE.read_text(encoding="utf-8")),
            json.loads(FOOTPRINTS.read_text(encoding="utf-8")))


def make_many_layers(layers: int, *, holdout_steps: int = 2,
                     top_k: int = 2) -> tuple[dict, dict]:
    cap = json.loads(CAPTURE.read_text(encoding="utf-8"))
    cap["events"] = [
        {"split": split, "layer": layer, "step": step,
         "experts": [((layer * 2) + (step * top_k) + expert) % 8
                     for expert in range(top_k)]}
        for split, count in (("train", 2), ("holdout_a", holdout_steps),
                             ("holdout_b", 2))
        for step in range(count)
        for layer in range(layers)
    ]
    manifest = {
        "schema_version": "phios.elastic.expert-footprints.v1",
        "source": "operator_supplied_unverified",
        "size_basis": "estimated",
        "source_capture_sha256": _hash(cap),
        "checkpoint_sha256": cap["source"]["checkpoint_sha256"],
        "layers": [
            {"layer": layer, "expert_sizes_bytes": [4096] * 8}
            for layer in range(layers)
        ],
    }
    return cap, manifest


def test_two_layer_shared_budget_counts_wasted_pin_preloads(
    source: tuple[dict, dict],
) -> None:
    cap, footprints = source
    assert footprints["source_capture_sha256"] == _hash(cap)
    result = evaluate(cap, footprints, **ARGS)
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["layers"] == 2
    assert result["holdout_count"] == result["evaluated_holdouts"] == 2
    assert result["effective_shared_capacity_bytes"] == 73728
    assert result["maximum_possible_eight_expert_group_bytes"] == 49152
    assert result["selected_pins_count"] == 4
    assert result["complete_holdout_accesses"] == 20
    assert [item["holdout"] for item in result["holdouts"]] == [
        "holdout_a", "holdout_b",
    ]
    summary = result["summary"]
    assert summary["total_unpinned_lru_logical_staged_bytes"] == 67584
    assert summary["total_train_pinned_lru_logical_staged_bytes"] == 73728
    assert summary["total_signed_logical_stage_delta_bytes"] == -6144
    assert summary["relative_logical_stage_delta_percent"] < 0
    assert summary["holdouts_equal_logical_bytes"] == 1
    assert summary["holdouts_higher_logical_bytes"] == 1
    assert summary["all_holdouts_lower_logical_bytes"] is False
    assert summary["total_pin_preloads_across_fresh_holdouts_bytes"] == 40960
    assert len(result["receipt_sha256"]) == 64
    assert len(result["frozen_global_train_only_policy_sha256"]) == 64
    assert all(result[field] is False for field in (
        "routing_source_authenticated", "weights_rehashed_here",
        "expert_size_independently_measured_here", "model_executed",
        "physical_transfer_bytes_measured", "wall_time_measured",
        "model_output_parity_checked", "speedup_proven", "automatic_promotion",
        "action_authority", "execution_authority", "hardware_control",
    ))
    output = json.dumps(result)
    assert "fixture-only" not in output
    assert '"checkpoint_sha256"' not in output
    assert '"experts"' not in output


def test_holdout_changes_do_not_change_frozen_train_policy(
    source: tuple[dict, dict],
) -> None:
    cap, footprints = source
    first = evaluate(cap, footprints, **ARGS)
    for event in cap["events"]:
        if event["split"] == "holdout_b":
            event["experts"] = [0, 1]
    footprints["source_capture_sha256"] = _hash(cap)
    second = evaluate(cap, footprints, **ARGS)
    assert first["source_capture_sha256"] != second["source_capture_sha256"]
    assert first["footprint_manifest_sha256"] != second["footprint_manifest_sha256"]
    assert first["frozen_global_train_only_policy_sha256"] == (
        second["frozen_global_train_only_policy_sha256"]
    )


def test_size_changes_affect_policy_and_accounting(source: tuple[dict, dict]) -> None:
    cap, footprints = source
    first = evaluate(cap, footprints, **ARGS)
    footprints["layers"][0]["expert_sizes_bytes"][0] = 8192
    second = evaluate(cap, footprints, **ARGS)
    assert first["footprint_manifest_sha256"] != second["footprint_manifest_sha256"]
    assert first["frozen_global_train_only_policy_sha256"] != (
        second["frozen_global_train_only_policy_sha256"]
    )
    assert first["summary"]["total_unpinned_lru_logical_staged_bytes"] != (
        second["summary"]["total_unpinned_lru_logical_staged_bytes"]
    )


def test_zero_pins_replays_same_global_lru(source: tuple[dict, dict]) -> None:
    cap, footprints = source
    result = evaluate(cap, footprints, **{**ARGS, "max_pins": 0})
    assert result["selected_pins_count"] == 0
    assert result["summary"]["total_signed_logical_stage_delta_bytes"] == 0
    assert result["summary"]["holdouts_equal_logical_bytes"] == 2
    assert all(item["global_unpinned_lru"] == item["global_train_pinned_lru"]
               for item in result["holdouts"])


def test_single_global_budget_causes_cross_layer_evictions() -> None:
    cap, footprints = make_many_layers(3)
    result = evaluate(cap, footprints, capacity_bytes=32768, max_pins=0)
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["layers"] == 3
    assert result["effective_shared_capacity_bytes"] == 32768
    row = result["holdouts"][0]["global_unpinned_lru"]
    assert row["peak_hypothetical_resident_bytes"] == 32768
    assert row["evictions"] > 0
    assert result["summary"]["total_signed_logical_stage_delta_bytes"] == 0


def test_24_layer_census_still_uses_one_global_budget() -> None:
    cap, footprints = make_many_layers(24)
    result = evaluate(cap, footprints, capacity_bytes=32768, max_pins=0)
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["layers"] == 24
    assert result["evaluated_holdouts"] == 2
    assert result["complete_holdout_accesses"] == 24 * 2 * 2 * 2
    assert all(item["global_unpinned_lru"]["peak_hypothetical_resident_bytes"]
               <= 32768 for item in result["holdouts"])
    assert result["summary"]["total_signed_logical_stage_delta_bytes"] == 0


def test_held_when_eight_expert_group_headroom_cannot_fit(
    source: tuple[dict, dict],
) -> None:
    cap, footprints = source
    result = evaluate(cap, footprints, capacity_bytes=49151, max_pins=0)
    assert result["status"] == "HELD"
    assert result["reason"] == "atomic_eight_expert_headroom_exceeds_effective_cache"
    assert result["evaluated_holdouts"] == 0
    assert result["holdouts"] is None
    assert result["summary"] is None
    assert result["automatic_promotion"] is False


def test_noncanonical_cross_layer_order_is_rejected(
    source: tuple[dict, dict],
) -> None:
    cap, footprints = source
    cap["events"][0], cap["events"][1] = cap["events"][1], cap["events"][0]
    footprints["source_capture_sha256"] = _hash(cap)
    with pytest.raises(SharedCacheError, match="noncanonical cross-layer"):
        evaluate(cap, footprints, **ARGS)


def test_one_holdout_is_not_generalization_evidence(source: tuple[dict, dict]) -> None:
    cap, footprints = source
    cap["events"] = [e for e in cap["events"] if e["split"] != "holdout_b"]
    footprints["source_capture_sha256"] = _hash(cap)
    with pytest.raises(SharedCacheError, match="at least two"):
        evaluate(cap, footprints, **ARGS)


def test_refuses_to_sample_excessive_layers_or_access_events() -> None:
    cap, footprint = make_many_layers(33)
    with pytest.raises(SharedCacheError, match="up to 32"):
        evaluate(cap, footprint, capacity_bytes=32768)
    cap, footprint = make_many_layers(1, holdout_steps=2048, top_k=8)
    with pytest.raises(SharedCacheError, match="access budget"):
        evaluate(cap, footprint, capacity_bytes=32768)


@pytest.mark.parametrize("mutate", [
    lambda x: x.update(schema_version="wrong"),
    lambda x: x.update(source="verified_native"),
    lambda x: x.update(size_basis="cryptographically_attested"),
    lambda x: x.update(size_basis=[]),
    lambda x: x.update(extra="private"),
    lambda x: x.update(source_capture_sha256="0" * 64),
    lambda x: x.update(checkpoint_sha256="0" * 64),
    lambda x: x.update(layers=[]),
    lambda x: x["layers"].append(copy.deepcopy(x["layers"][0])),
    lambda x: x["layers"][0].update(layer=99),
    lambda x: x["layers"][0].update(unknown="private"),
    lambda x: x["layers"][0].update(expert_sizes_bytes=[1]),
    lambda x: x["layers"][0]["expert_sizes_bytes"].__setitem__(0, 0),
    lambda x: x["layers"][0]["expert_sizes_bytes"].__setitem__(0, True),
    lambda x: x["layers"][0]["expert_sizes_bytes"].__setitem__(0, 16 * 1024**2 + 1),
])
def test_invalid_footprints_refused(
    source: tuple[dict, dict], mutate,
) -> None:
    cap, footprints = source
    mutate(footprints)
    with pytest.raises(SharedCacheError):
        evaluate(cap, footprints, **ARGS)


@pytest.mark.parametrize("opts", [
    {"capacity_bytes": 0},
    {"capacity_bytes": True},
    {"capacity_bytes": 64 * 1024**3 + 1},
    {"capacity_bytes": 81920, "reserve_bytes": -1},
    {"capacity_bytes": 81920, "reserve_bytes": True},
    {"capacity_bytes": 81920, "reserve_bytes": 81921},
    {"capacity_bytes": 81920, "max_pins": -1},
    {"capacity_bytes": 81920, "max_pins": True},
    {"capacity_bytes": 81920, "max_pins": 33},
])
def test_invalid_global_budget_refused(
    source: tuple[dict, dict], opts: dict,
) -> None:
    with pytest.raises(SharedCacheError):
        evaluate(*source, **opts)


def test_invalid_native_source_refused(source: tuple[dict, dict]) -> None:
    cap, footprints = source
    cap["events"][0]["experts"] = [True]
    with pytest.raises(RouterBridgeError):
        evaluate(cap, footprints, **ARGS)


def test_operator_reported_sizes_not_authenticated(
    source: tuple[dict, dict],
) -> None:
    cap, footprints = source
    footprints["size_basis"] = "operator_reported_tensor_shapes_unverified"
    result = evaluate(cap, footprints, **ARGS)
    assert result["expert_size_basis"] == "operator_reported_tensor_shapes_unverified"
    assert result["expert_size_independently_measured_here"] is False
    assert result["weights_rehashed_here"] is False


def test_stable_output_and_file_bound_cli(
    source: tuple[dict, dict], tmp_path: Path,
) -> None:
    cap, footprints = source
    assert evaluate(cap, footprints, **ARGS) == evaluate(
        copy.deepcopy(cap), copy.deepcopy(footprints), **ARGS
    )
    capture_file = tmp_path / "capture.json"
    size_file = tmp_path / "sizes.json"
    capture_file.write_text(json.dumps(cap), encoding="utf-8")
    size_file.write_text(json.dumps(footprints), encoding="utf-8")
    originals = capture_file.read_bytes(), size_file.read_bytes()
    command = [
        sys.executable, "-m", "phios.elastic_shared_r13",
        "--capture", str(capture_file), "--footprints", str(size_file),
        "--capacity-bytes", "81920", "--reserve-bytes", "8192",
        "--max-pins", "4",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=15)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == evaluate(cap, footprints, **ARGS)
    assert (capture_file.read_bytes(), size_file.read_bytes()) == originals
    assert str(tmp_path) not in completed.stdout
    held = subprocess.run(command[:-6] + ["--capacity-bytes", "49151"],
                          capture_output=True, text=True, timeout=15)
    assert held.returncode == 3
    assert json.loads(held.stdout)["status"] == "HELD"
    size_file.write_text("{}", encoding="utf-8")
    invalid = subprocess.run(command, capture_output=True, text=True, timeout=15)
    assert invalid.returncode == 2
    assert json.loads(invalid.stdout)["status"] == "UNAVAILABLE"
