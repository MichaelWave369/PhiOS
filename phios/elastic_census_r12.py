"""PhiOS Elastic R12: exhaustive all-layer/all-holdout shadow cache census.

Orchestrates the existing, unmodified R11 train-only pin-selection experiment.
Each layer has an INDEPENDENT hypothetical cache budget; summing its stage
counters is NOT a global VRAM placement or real-world bandwidth measurement.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence, cast

from phios.elastic_holdout_r11 import HoldoutPolicyError, evaluate as evaluate_layer
from phios.elastic_router_r10 import RouterBridgeError, _hash, _read, _validate

SCHEMA = "phios.elastic.all-layer-holdout-census.v1"
MAX_CENSUS_LAYERS = 32
MAX_CENSUS_CELLS = 96


class AllLayerCensusError(ValueError):
    """A source capture cannot support a complete bounded layer census."""


def _integer(value: object, label: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise AllLayerCensusError(f"invalid {label}")
    return value


def _flags() -> dict[str, bool]:
    return {
        "routing_source_authenticated": False,
        "model_executed": False,
        "real_weight_transfers_measured": False,
        "model_output_parity_checked": False,
        "wall_time_measured": False,
        "speedup_proven": False,
        "statistical_significance_established": False,
        "automatic_promotion": False,
        "action_authority": False,
        "execution_authority": False,
        "hardware_control": False,
    }


def census(
    capture: object, *, expert_bytes: int, capacity_bytes: int,
    reserve_bytes: int = 0, max_pins: int = 2,
) -> dict[str, object]:
    """Evaluate every declared layer against every holdout; fail as a unit.

    Reuses R11 without allowing per-layer tuning or post-hoc holdout selection.
    Model weights and hardware are never accessed, and no training data
    appears in the reported holdout outcomes.
    """
    checked = _validate(capture)
    size = _integer(expert_bytes, "assumed uniform expert bytes", 1, 16 * 1024 * 1024)
    capacity = _integer(capacity_bytes, "hypothetical per-layer capacity", 1, 2 * 1024**3)
    reserve = _integer(reserve_bytes, "per-layer reserve", 0, capacity)
    requested = _integer(max_pins, "max train-only pins", 0, 16)

    layers: list[int] = checked["layers"]
    splits: list[str] = checked["phases"][1:]
    if len(splits) < 2:
        raise AllLayerCensusError("two or more disjoint holdouts required")
    if (len(layers) > MAX_CENSUS_LAYERS or
            len(layers) * len(splits) > MAX_CENSUS_CELLS):
        raise AllLayerCensusError("census bounds exceeded; never sample layers or holdouts")

    capture_digest = _hash(capture)
    effective = capacity - reserve
    common: dict[str, object] = {
        "schema_version": SCHEMA,
        "scope": "isolated_per_layer_cache_replay_not_shared_vram_budget",
        "source_kind": checked["kind"],
        "source_capture_sha256": capture_digest,
        "routed_layers_declared": len(layers),
        "holdout_splits_declared": len(splits),
        "expected_layer_holdout_cells": len(layers) * len(splits),
        "assumed_uniform_expert_bytes": size,
        "per_layer_budget_bytes": {
            "capacity": capacity, "reserve": reserve, "effective": effective,
        },
        "requested_max_train_only_pins": requested,
        "each_layer_cache_is_independent": True,
        "training_only_selection": True,
        **_flags(),
    }
    if effective < 2 * size:
        held: dict[str, object] = {
            **common,
            "status": "HELD",
            "reason": "each_layer_requires_two_expert_slots",
            "evaluated_layer_holdout_cells": 0,
            "layer_results": None,
            "summary": None,
        }
        held["receipt_sha256"] = _hash(held)
        return held

    rows: list[dict[str, object]] = []
    positive = equal = negative = 0
    layers_positive = layers_equal = layers_negative = 0
    total_baseline = total_candidate = total_preload = 0
    total_uses = total_hits_baseline = total_hits_candidate = 0
    min_delta: int | None = None

    for layer in layers:
        # R11 freezes expert pins from this layer's train split, then evaluates
        # ALL holdouts. We never select a policy based on holdout performance.
        report = evaluate_layer(
            capture, layer=layer, expert_bytes=size, capacity_bytes=capacity,
            reserve_bytes=reserve, max_pins=requested,
        )
        if (report.get("status") != "REVIEW_REQUIRED" or
                report.get("source_capture_sha256") != capture_digest or
                report.get("training_only_selection") is not True):
            raise AllLayerCensusError("incomplete or inconsistent R11 layer replay")
        for flag in ("routing_source_authenticated", "real_model_executed",
                     "actual_weight_transfers_measured", "output_parity_checked",
                     "speedup_proven", "automatic_promotion", "action_authority",
                     "execution_authority", "hardware_control"):
            if report.get(flag) is not False:
                raise AllLayerCensusError("unsupported R11 authority or provenance claim")
        source_rows = report.get("holdouts")
        if not isinstance(source_rows, list) or len(source_rows) != len(splits):
            raise AllLayerCensusError("R11 did not return the complete holdout set")
        frozen = report.get("frozen_policy_sha256")
        if not isinstance(frozen, str) or len(frozen) != 64:
            raise AllLayerCensusError("missing frozen train-only policy digest")
        per_layer_delta = 0
        cells: list[dict[str, object]] = []
        for expected_split, raw in zip(splits, source_rows):
            if not isinstance(raw, dict) or raw.get("holdout") != expected_split:
                raise AllLayerCensusError("R11 holdout order or name changed")
            holdout = cast(dict[str, Any], raw)
            lhs = _integer(holdout.get("unpinned_lru_stage_bytes"),
                           "LRU staged bytes", 1, 10**16)
            rhs = _integer(holdout.get("train_pin_lru_stage_bytes"),
                           "train-pinned staged bytes", 1, 10**16)
            delta = _integer(holdout.get("stage_byte_delta_vs_unpinned_lru"),
                             "signed byte delta", -10**16, 10**16)
            if delta != lhs - rhs:
                raise AllLayerCensusError("R11 cell staging arithmetic inconsistent")
            accesses = _integer(holdout.get("routed_expert_accesses"),
                                "holdout accesses", 1, 4096)
            lru_hits = _integer(holdout.get("unpinned_lru_hits"),
                                "unmodified LRU hits", 0, accesses)
            pin_hits = _integer(holdout.get("train_pin_lru_hits"),
                                "trained pin LRU hits", 0, accesses)
            preload = _integer(holdout.get("train_pin_preload_bytes"),
                               "preload bytes", 0, 16 * size)
            peak = _integer(holdout.get("train_pin_peak_resident_bytes"),
                            "resident peak", 0, effective)
            # R11 sums one independent replay for each holdout; preload is
            # consequently charged once PER holdout, not once per entire run.
            positive += delta > 0
            equal += delta == 0
            negative += delta < 0
            per_layer_delta += delta
            total_baseline += lhs
            total_candidate += rhs
            total_preload += preload
            total_uses += accesses
            total_hits_baseline += lru_hits
            total_hits_candidate += pin_hits
            min_delta = delta if min_delta is None else min(min_delta, delta)
            cells.append({
                "holdout": expected_split,
                "routed_expert_accesses": accesses,
                "unpinned_lru_staged_bytes": lhs,
                "train_pin_lru_staged_bytes": rhs,
                "signed_delta_vs_unpinned_lru_bytes": delta,
                "unpinned_lru_hits": lru_hits,
                "train_pin_lru_hits": pin_hits,
                "train_pin_preload_bytes": preload,
                "train_pin_peak_resident_bytes": peak,
            })
        layers_positive += per_layer_delta > 0
        layers_equal += per_layer_delta == 0
        layers_negative += per_layer_delta < 0
        rows.append({
            "layer": layer,
            "frozen_train_only_policy_sha256": frozen,
            "train_selected_pin_count": report["selected_train_only_pins"],
            "train_steps": report["training_steps"],
            "holdout_cells": cells,
            "layer_signed_byte_delta": per_layer_delta,
        })
    expected_cells = len(layers) * len(splits)
    if positive + equal + negative != expected_cells:
        raise AllLayerCensusError("missing layer-holdout replay cells")
    if total_baseline <= 0:
        raise AllLayerCensusError("invalid total baseline")
    summary: dict[str, object] = {
        "cells": expected_cells,
        "improved_cells": positive,
        "unchanged_cells": equal,
        "regressed_cells": negative,
        "all_cells_have_lower_logical_bytes": positive == expected_cells,
        "layers_with_lower_total_logical_bytes": layers_positive,
        "layers_with_equal_total_logical_bytes": layers_equal,
        "layers_with_higher_total_logical_bytes": layers_negative,
        "worst_single_cell_signed_delta_bytes": min_delta,
        "total_routed_expert_accesses": total_uses,
        "total_unpinned_lru_staged_bytes": total_baseline,
        "total_train_pin_lru_staged_bytes": total_candidate,
        "total_train_pin_preload_bytes_across_independent_replays": total_preload,
        "total_unpinned_lru_hits": total_hits_baseline,
        "total_train_pin_lru_hits": total_hits_candidate,
        "total_signed_logical_staged_bytes_delta": total_baseline - total_candidate,
        "relative_total_logical_stage_delta_percent": round(
            100 * (total_baseline - total_candidate) / total_baseline, 4
        ),
    }
    result: dict[str, object] = {
        **common,
        "status": "REVIEW_REQUIRED",
        "reason": "all_layers_all_holdouts_simulation_only",
        "evaluated_layer_holdout_cells": expected_cells,
        "layer_results": rows,
        "summary": summary,
    }
    result["receipt_sha256"] = _hash(result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="PhiOS R12: all-layer/all-holdout train-only pinning census"
    )
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--expert-bytes", required=True, type=int)
    parser.add_argument("--capacity-bytes", required=True, type=int)
    parser.add_argument("--reserve-bytes", type=int, default=0)
    parser.add_argument("--max-pins", type=int, default=2)
    args = parser.parse_args(argv)
    try:
        result = census(
            _read(args.capture), expert_bytes=args.expert_bytes,
            capacity_bytes=args.capacity_bytes, reserve_bytes=args.reserve_bytes,
            max_pins=args.max_pins,
        )
    except (AllLayerCensusError, HoldoutPolicyError, RouterBridgeError,
            OSError, RecursionError, OverflowError):
        print(json.dumps({"schema_version": SCHEMA, "status": "UNAVAILABLE",
                          "action_authority": False, "execution_authority": False},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 3 if result["status"] == "HELD" else 0


if __name__ == "__main__":
    sys.exit(main())
