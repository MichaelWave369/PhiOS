"""PhiOS Elastic R11: frozen train-only expert pinning, evaluated on holdouts.

A deliberately narrow, offline research replay. The output cannot change
model routing, residency, GPU allocations, or any real host resource.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import sys
from pathlib import Path
from typing import Any, Sequence, cast

from phios.elastic_router_r10 import (
    RouterBridgeError,
    _hash,
    _read,
    _validate,
    bridge,
)

SCHEMA = "phios.elastic.train-holdout-cache-review.v1"
MAX_PINS = 16


class HoldoutPolicyError(ValueError):
    """Invalid research design or unsupported replay configuration."""


def _integer(value: object, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise HoldoutPolicyError(f"invalid {name}")
    return value


def _learn(groups: list[list[int]], maximum: int) -> list[int]:
    """Freeze frequency ranking using only TRAINING data; break ties by ID."""
    counts = Counter(expert for group in groups for expert in group)
    ranked = sorted(counts, key=lambda expert: (-counts[expert], expert))
    return ranked[:maximum]


def evaluate(
    capture: object, *, layer: int, expert_bytes: int, capacity_bytes: int,
    reserve_bytes: int = 0, max_pins: int = 2,
) -> dict[str, object]:
    """Compare a frozen training-only pin choice to no-pins LRU on ALL holdouts.

    No holdout event contributes to the pin ranking. No holdout is selected
    after viewing an outcome: every declared holdout is evaluated or the whole
    study is rejected.
    """
    checked = _validate(capture)
    if type(layer) is not int or layer not in checked["layers"]:
        raise HoldoutPolicyError("layer must be in all splits")
    size = _integer(expert_bytes, "assumed expert size", 1, 16 * 1024 * 1024)
    capacity = _integer(capacity_bytes, "hypothetical capacity", 1, 2 * 1024**3)
    reserve = _integer(reserve_bytes, "reserve", 0, capacity)
    requested = _integer(max_pins, "maximum pins", 0, MAX_PINS)

    phases: list[str] = checked["phases"]
    groups: dict[str, dict[int, list[list[int]]]] = checked["streams"]
    holdouts = phases[1:]
    if len(holdouts) < 2:
        raise HoldoutPolicyError("at least two disjoint holdout splits required")
    # A single slot always stays unpinned for ordinary demand. A policy with
    # zero spare slots cannot be compared fairly against baseline LRU.
    effective = capacity - reserve
    if effective < 2 * size:
        result: dict[str, object] = {
            "schema_version": SCHEMA,
            "status": "HELD",
            "reason": "effective_capacity_needs_two_expert_slots",
            "source_capture_sha256": _hash(capture),
            "source_kind": checked["kind"],
            "selected_layer": layer,
            "evaluated_holdouts": 0,
            "training_only_selection": True,
            "routing_source_authenticated": False,
            "real_model_executed": False,
            "actual_weight_transfers_measured": False,
            "output_parity_checked": False,
            "speedup_proven": False,
            "automatic_promotion": False,
            "action_authority": False,
            "execution_authority": False,
            "hardware_control": False,
        }
        result["receipt_sha256"] = _hash(result)
        return result

    max_fittable = min(requested, effective // size - 1)
    train_groups = groups["train"][layer]
    pins = _learn(train_groups, max_fittable)
    training_uses = sum(len(group) for group in train_groups)
    frozen_policy_sha256 = _hash({
        "algorithm": "train_frequency_descending_id_tiebreak_v1",
        "selected_layer": layer,
        "train_groups_sha256": _hash(train_groups),
        "chosen_expert_ids": pins,
        "expert_bytes": size,
        "capacity_bytes": capacity,
        "reserve_bytes": reserve,
    })
    reports: list[dict[str, object]] = []
    total_baseline = 0
    total_candidate = 0
    total_events = 0
    improved = unchanged = regressed = 0
    for name in holdouts:
        baseline = bridge(
            capture, layer=layer, holdout=name, expert_bytes=size,
            capacity_bytes=capacity, reserve_bytes=reserve, pinned_experts=(),
        )
        candidate = bridge(
            capture, layer=layer, holdout=name, expert_bytes=size,
            capacity_bytes=capacity, reserve_bytes=reserve, pinned_experts=pins,
        )
        if not isinstance(baseline["shadow"], dict) or not isinstance(
            candidate["shadow"], dict
        ):
            raise HoldoutPolicyError("missing shadow replay outputs")
        left = cast(dict[str, Any], baseline["shadow"])
        right = cast(dict[str, Any], candidate["shadow"])
        if (baseline["status"] != "REVIEW_REQUIRED" or
                candidate["status"] != "REVIEW_REQUIRED" or
                left["baseline_logical_staged_bytes"] !=
                right["baseline_logical_staged_bytes"]):
            raise HoldoutPolicyError("paired shadow replay did not complete")
        lru = left["candidate"]
        pinned = right["candidate"]
        if not isinstance(lru, dict) or not isinstance(pinned, dict):
            raise HoldoutPolicyError("missing paired shadow candidate")
        baseline_bytes = lru["logical_staged_bytes"]
        selected_bytes = pinned["logical_staged_bytes"]
        if type(baseline_bytes) is not int or type(selected_bytes) is not int:
            raise HoldoutPolicyError("invalid shadow staging quantities")
        change = baseline_bytes - selected_bytes
        improved += change > 0
        regressed += change < 0
        unchanged += change == 0
        total_baseline += baseline_bytes
        total_candidate += selected_bytes
        total_events += _integer(baseline["routed_expert_accesses"], "routed uses", 1, 4096)
        reports.append({
            "holdout": name,
            "steps": baseline["holdout_steps"],
            "routed_expert_accesses": baseline["routed_expert_accesses"],
            "unique_experts": baseline["unique_accessed_experts"],
            "unpinned_lru_stage_bytes": baseline_bytes,
            "train_pin_lru_stage_bytes": selected_bytes,
            "stage_byte_delta_vs_unpinned_lru": change,
            "unpinned_lru_hits": lru["cache_hits"],
            "train_pin_lru_hits": pinned["cache_hits"],
            "train_pin_preload_bytes": pinned["hypothetical_preload_bytes"],
            "train_pin_peak_resident_bytes": pinned["peak_hypothetical_resident_bytes"],
        })
    summary: dict[str, object] = {
        "holdouts_evaluated": len(reports),
        "holdouts_with_lower_logical_bytes": improved,
        "holdouts_with_equal_logical_bytes": unchanged,
        "holdouts_with_higher_logical_bytes": regressed,
        "all_holdouts_lower_logical_bytes": improved == len(reports),
        "access_events": total_events,
        "total_unpinned_lru_stage_bytes": total_baseline,
        "total_train_pin_lru_stage_bytes": total_candidate,
        "total_signed_stage_byte_delta": total_baseline - total_candidate,
        "relative_total_logical_stage_delta_percent": round(
            100 * (total_baseline - total_candidate) / total_baseline, 4
        ),
    }
    result = {
        "schema_version": SCHEMA,
        "status": "REVIEW_REQUIRED",
        "reason": "simulation_only_no_promotion",
        "source_capture_sha256": _hash(capture),
        "source_kind": checked["kind"],
        "selected_layer": layer,
        "assumed_expert_bytes": size,
        "budget_bytes": {
            "capacity": capacity, "reserve": reserve, "effective": effective,
        },
        "training_steps": len(train_groups),
        "training_expert_uses": training_uses,
        "training_only_selection": True,
        "selection_rule": "frequency_descending_expert_id_tiebreak",
        "requested_max_pins": requested,
        "selected_train_only_pins": len(pins),
        "frozen_policy_sha256": frozen_policy_sha256,
        "evaluated_holdouts": len(reports),
        "holdouts": reports,
        "summary": summary,
        "routing_source_authenticated": False,
        "real_model_executed": False,
        "actual_weight_transfers_measured": False,
        "output_parity_checked": False,
        "speedup_proven": False,
        "automatic_promotion": False,
        "action_authority": False,
        "execution_authority": False,
        "hardware_control": False,
    }
    result["receipt_sha256"] = _hash(result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="PhiOS R11: train-only expert pinning versus plain LRU on every holdout"
    )
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--layer", type=int, required=True)
    parser.add_argument("--expert-bytes", type=int, required=True)
    parser.add_argument("--capacity-bytes", type=int, required=True)
    parser.add_argument("--reserve-bytes", type=int, default=0)
    parser.add_argument("--max-pins", type=int, default=2)
    args = parser.parse_args(argv)
    try:
        result = evaluate(
            _read(args.capture), layer=args.layer, expert_bytes=args.expert_bytes,
            capacity_bytes=args.capacity_bytes, reserve_bytes=args.reserve_bytes,
            max_pins=args.max_pins,
        )
    except (HoldoutPolicyError, RouterBridgeError, OSError,
            RecursionError, OverflowError):
        print(json.dumps({"schema_version": SCHEMA, "status": "UNAVAILABLE",
                          "action_authority": False, "execution_authority": False},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 3 if result["status"] == "HELD" else 0


if __name__ == "__main__":
    sys.exit(main())
