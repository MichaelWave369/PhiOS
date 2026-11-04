"""R10: PocketRotor native-route capture compatibility with R9 shadow cache.

All tests use synthetic expert IDs, no pretrained model, GPU or weights.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from phios.elastic_router_r10 import RouterBridgeError, _read, bridge

EXAMPLE = (
    Path(__file__).resolve().parents[1] /
    "experiments/elastic/r10_synthetic_pocketrotor_capture.json"
)


@pytest.fixture
def capture() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def run(capture: dict, **changes) -> dict:
    settings = {
        "layer": 0,
        "holdout": "holdout_a",
        "expert_bytes": 4096,
        "capacity_bytes": 16384,
        "reserve_bytes": 4096,
    }
    settings.update(changes)
    return bridge(capture, **settings)


def test_synthetic_holdout_to_shadow_reuse_counts(capture: dict) -> None:
    result = run(capture)
    shadow = result["shadow"]
    assert result["status"] == shadow["status"] == "REVIEW_REQUIRED"
    assert result["source_kind"] == "synthetic"
    assert result["routing_source_authenticated"] is False
    assert result["selected_layer"] == 0
    assert result["selected_holdout"] == "holdout_a"
    assert result["holdout_steps"] == 3
    assert result["routed_expert_accesses"] == 6
    assert result["unique_accessed_experts"] == 3
    assert shadow["baseline_logical_staged_bytes"] == 6 * 4096
    candidate = shadow["candidate"]
    assert candidate["logical_staged_bytes"] == 3 * 4096
    assert candidate["cache_hits"] == 3
    assert candidate["cache_misses"] == 3
    assert candidate["evictions"] == 0
    assert candidate["relative_logical_stage_reduction_percent"] == 50.0
    assert shadow["budget_bytes"]["effective"] == 12288
    assert len(result["source_capture_sha256"]) == len(result["receipt_sha256"]) == 64
    for flag in (
        "actual_weight_transfers_measured", "model_output_parity_checked",
        "model_execution", "performance_improvement_proven", "action_authority",
        "execution_authority", "hardware_control",
    ):
        assert result[flag] is False
    # Source runtime/model metadata and original expert IDs never leave the importer.
    output = json.dumps(result)
    assert "fixture-only" not in output
    assert '"events"' not in output


def test_one_layer_and_selected_holdout_only(capture: dict) -> None:
    result = run(capture, layer=1, holdout="holdout_b")
    assert result["routed_expert_accesses"] == 4
    assert result["unique_accessed_experts"] == 3
    assert result["selected_layer"] == 1
    assert result["holdout_steps"] == 2
    assert result["shadow"]["access_event_count"] == 4


def test_source_kind_is_not_source_attestation(capture: dict) -> None:
    capture["source"]["kind"] = "operator_asserted_native"
    result = run(capture)
    assert result["source_kind"] == "operator_asserted_native"
    assert result["routing_source_authenticated"] is False
    assert result["model_execution"] is False
    assert result["performance_improvement_proven"] is False


def test_candidate_overbudget_pins_held_not_evicted(capture: dict) -> None:
    result = run(capture, capacity_bytes=8192, reserve_bytes=0,
                 pinned_experts=[0, 1, 2])
    assert result["status"] == "HELD"
    assert result["shadow"]["status"] == "HELD"
    assert result["shadow"]["candidate"] is None
    assert result["hardware_control"] is False


def test_unused_pinned_expert_is_charged_as_preload(capture: dict) -> None:
    base = run(capture, pinned_experts=[])
    pinned = run(capture, pinned_experts=[7])
    assert pinned["pinned_experts_declared_count"] == 1
    assert pinned["shadow"]["candidate"]["hypothetical_preload_bytes"] == 4096
    assert pinned["shadow"]["candidate"]["logical_staged_bytes"] >= (
        base["shadow"]["candidate"]["logical_staged_bytes"] + 4096
    )
    assert pinned["shadow"]["budget_bytes"]["effective"] == 12288


def test_repeated_replay_is_deterministic(capture: dict) -> None:
    assert run(capture) == run(copy.deepcopy(capture))


@pytest.mark.parametrize("mutate", [
    lambda x: x.update(schema="bad"),
    lambda x: x.update(other_field="private"),
    lambda x: x.update(expert_count=True),
    lambda x: x.update(expert_count=257),
    lambda x: x["source"].update(kind="verified_native"),
    lambda x: x["source"].update(runtime="../bad"),
    lambda x: x["source"].update(route_semantics="BEFORE_ROUTER"),
    lambda x: x["source"].update(token_text_recorded=True),
    lambda x: x["source"].update(checkpoint_sha256="invalid"),
    lambda x: x["source"].update(prompt="private"),
    lambda x: x["events"][0].update(layer=True),
    lambda x: x["events"][0].update(step=2),
    lambda x: x["events"][0].update(experts=[]),
    lambda x: x["events"][0].update(experts=[0, 0]),
    lambda x: x["events"][0].update(experts=[256]),
    lambda x: x["events"][0].update(experts=[True]),
    lambda x: x["events"][0].update(token="private"),
    lambda x: x["events"][0].update(split="holdout_a"),
    lambda x: x["events"].pop(0),
    lambda x: x["events"].append(copy.deepcopy(x["events"][0])),
    lambda x: x["events"].pop(),
])
def test_bad_capture_rejected(capture: dict, mutate) -> None:
    mutate(capture)
    with pytest.raises(RouterBridgeError):
        run(capture)


@pytest.mark.parametrize("overrides", [
    {"layer": 2},
    {"layer": True},
    {"holdout": "train"},
    {"holdout": "nonexistent"},
    {"expert_bytes": 0},
    {"expert_bytes": True},
    {"expert_bytes": 16 * 1024 * 1024 + 1},
    {"capacity_bytes": 0},
    {"capacity_bytes": True},
    {"capacity_bytes": 2 * 1024**3 + 1},
    {"reserve_bytes": -1},
    {"reserve_bytes": 20000},
    {"reserve_bytes": True},
    {"pinned_experts": [0, 0]},
    {"pinned_experts": [8]},
    {"pinned_experts": [True]},
    {"pinned_experts": "0"},
])
def test_bad_replay_selections_refused(capture: dict, overrides: dict) -> None:
    with pytest.raises(RouterBridgeError):
        run(capture, **overrides)


def test_overlarge_holdout_is_not_partially_replayed(capture: dict) -> None:
    # Well-formed capture with 4096 token steps and top-2 experts exceeds
    # R9's 4096-access replay bound. It must refuse, never truncate.
    layer0 = capture["events"][0]
    original_layer1 = capture["events"][1]
    source_events = capture["events"]
    # Rewrite train / holdout with exactly one layer and 2..4096 steps.
    capture["events"] = []
    for split, length in (("train", 2), ("holdout_a", 4096)):
        for step in range(length):
            capture["events"].append({
                "split": split, "layer": 0, "step": step,
                "experts": [0, 1],
            })
    assert layer0["layer"] == 0 and original_layer1["layer"] == 1
    assert len(source_events) == 16
    with pytest.raises(RouterBridgeError, match="R9 event budget"):
        run(capture)


@pytest.mark.parametrize("raw", [
    b'{"schema":"A","schema":"B"}', b'{"x":NaN}', b'{"x":Infinity}',
    b"\xff", b"{", b" " * (2 * 1024 * 1024 + 1),
])
def test_invalid_or_oversized_wire_rejected(tmp_path: Path, raw: bytes) -> None:
    path = tmp_path / "invalid.json"
    path.write_bytes(raw)
    with pytest.raises(RouterBridgeError):
        _read(path)


def test_symlink_and_missing_files_refused(tmp_path: Path) -> None:
    real = tmp_path / "capture.json"
    real.write_text("{}", encoding="utf-8")
    alias = tmp_path / "alias.json"
    try:
        alias.symlink_to(real)
    except (NotImplementedError, OSError):
        pytest.skip("symlinks unavailable")
    for path in (alias, tmp_path, tmp_path / "missing.json"):
        with pytest.raises(RouterBridgeError):
            _read(path)


def test_cli_offline_status_codes_and_no_input_mutation(
    tmp_path: Path, capture: dict,
) -> None:
    path = tmp_path / "route.json"
    path.write_text(json.dumps(capture), encoding="utf-8")
    cmd = [
        sys.executable, "-m", "phios.elastic_router_r10",
        "--capture", str(path), "--layer", "0",
        "--holdout", "holdout_a", "--expert-bytes", "4096",
        "--capacity-bytes", "16384", "--reserve-bytes", "4096",
    ]
    before = path.read_bytes()
    success = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
    assert success.returncode == 0 and success.stderr == ""
    assert json.loads(success.stdout) == run(capture)
    assert path.read_bytes() == before
    assert str(path) not in success.stdout
    held = subprocess.run(cmd[:-2] + ["--pin-expert", "0", "--pin-expert", "1",
                                      "--pin-expert", "2", "--capacity-bytes", "8192"],
                          capture_output=True, text=True, timeout=8)
    assert held.returncode == 3
    assert json.loads(held.stdout)["status"] == "HELD"
    path.write_text("{}", encoding="utf-8")
    invalid = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
    assert invalid.returncode == 2
    assert json.loads(invalid.stdout)["status"] == "UNAVAILABLE"
