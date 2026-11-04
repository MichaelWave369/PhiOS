"""PhiOS Elastic R13: shared-budget, size-aware offline expert residency replay.

One hypothetical cache spans all routed layers in each holdout. It accounts
for atomic routed groups, pinned preloads, LRU evictions and explicit
operator-declared expert sizes. No checkpoint, GPU, model or OS action.
"""

from __future__ import annotations

import argparse
from collections import Counter, OrderedDict
from functools import cmp_to_key
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from phios.elastic_router_r10 import RouterBridgeError, _hash, _read, _validate

MANIFEST_SCHEMA = "phios.elastic.expert-footprints.v1"
REVIEW_SCHEMA = "phios.elastic.shared-cache-replay.v1"
MAX_LAYERS = 32
MAX_TOTAL_ACCESSES = 16384
MAX_ACCESS_PER_HOLDOUT = 8192
MAX_PINS = 32
MAX_EXPERT_BYTES = 16 * 1024**2
MAX_CAPACITY_BYTES = 64 * 1024**3
_SIZE_BASES = frozenset({
    "estimated",
    "operator_reported_tensor_shapes_unverified",
})
Resource = tuple[int, int]
RouteEvent = tuple[Resource, ...]


class SharedCacheError(ValueError):
    """Invalid, incomplete or unsupported bounded shadow research data."""


def _int(value: object, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise SharedCacheError(f"invalid {label}")
    return value


def _obj(value: object, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise SharedCacheError(f"invalid {label} fields")
    return value


def _footprints(
    manifest: object, capture: object, layers: list[int], expert_count: int,
) -> tuple[dict[Resource, int], str]:
    root = _obj(manifest, {
        "schema_version", "source", "size_basis",
        "source_capture_sha256", "checkpoint_sha256", "layers",
    }, "expert-size manifest")
    if (root["schema_version"] != MANIFEST_SCHEMA or
            root["source"] != "operator_supplied_unverified" or
            root["size_basis"] not in _SIZE_BASES):
        raise SharedCacheError("unsupported footprint source or basis")
    if not isinstance(capture, dict):
        raise SharedCacheError("capture missing for footprint binding")
    source = capture.get("source")
    if not isinstance(source, dict):
        raise SharedCacheError("capture source unavailable")
    if (root["source_capture_sha256"] != _hash(capture) or
            root["checkpoint_sha256"] != source.get("checkpoint_sha256")):
        raise SharedCacheError("manifest does not bind selected capture/checkpoint")
    raw = root["layers"]
    if not isinstance(raw, list) or len(raw) != len(layers):
        raise SharedCacheError("footprints must cover every captured layer")
    sizes: dict[Resource, int] = {}
    seen: set[int] = set()
    for entry in raw:
        record = _obj(entry, {"layer", "expert_sizes_bytes"}, "layer footprint")
        index = _int(record["layer"], "layer", 0, 127)
        if index not in layers or index in seen:
            raise SharedCacheError("missing, duplicate or unknown layer")
        seen.add(index)
        vector = record["expert_sizes_bytes"]
        if not isinstance(vector, list) or len(vector) != expert_count:
            raise SharedCacheError("all experts need declared individual sizes")
        for expert_id, value in enumerate(vector):
            sizes[(index, expert_id)] = _int(
                value, "expert bytes", 1, MAX_EXPERT_BYTES,
            )
    if seen != set(layers):
        raise SharedCacheError("incomplete layer sizes")
    return sizes, str(root["size_basis"])


def _split_events(
    capture: object, layers: list[int], phases: list[str],
) -> dict[str, list[RouteEvent]]:
    """Require canonical step-major layer order, never invent event chronology.

    The E2-R schema records per-layer step indices but no host/GPU wall time.
    Enforce an unambiguous step-major order for this shadow *logical* replay.
    """
    if not isinstance(capture, dict) or not isinstance(capture.get("events"), list):
        raise SharedCacheError("capture events missing")
    by_split: dict[str, list[RouteEvent]] = {name: [] for name in phases}
    positions: dict[str, list[tuple[int, int]]] = {name: [] for name in phases}
    for raw in capture["events"]:
        if not isinstance(raw, dict):
            raise SharedCacheError("invalid event")
        split = raw["split"]
        layer = raw["layer"]
        step = raw["step"]
        experts = raw["experts"]
        if split not in by_split or not isinstance(experts, list):
            raise SharedCacheError("invalid event")
        positions[split].append((step, layer))
        by_split[split].append(tuple((layer, e) for e in experts))
    for name in phases:
        events = by_split[name]
        if len(events) % len(layers):
            raise SharedCacheError("incomplete layer event coverage")
        steps = len(events) // len(layers)
        if positions[name] != [
            (step, layer) for step in range(steps) for layer in layers
        ]:
            raise SharedCacheError("noncanonical cross-layer ordering; refuse to reorder")
    return by_split


def _rank_train(
    train: list[RouteEvent], sizes: dict[Resource, int],
) -> list[Resource]:
    counts = Counter(resource for event in train for resource in event)

    def order(a: Resource, b: Resource) -> int:
        # Cross-multiply rather than use floating point for exact
        # frequency-per-byte tie handling.
        left = counts[a] * sizes[b]
        right = counts[b] * sizes[a]
        if left != right:
            return -1 if left > right else 1
        return -1 if a < b else (1 if a > b else 0)

    return sorted(counts, key=cmp_to_key(order))


def _simulate(
    events: list[RouteEvent], sizes: dict[Resource, int],
    effective: int, pins: tuple[Resource, ...],
) -> dict[str, int]:
    """Replay an atomic expert group with global pinned+LRU residency.

    Every expert in one routed event must simultaneously fit, alongside the
    declared pins. All cache state is ephemeral Python bookkeeping only.
    """
    pinned_set = set(pins)
    resident_sizes: dict[Resource, int] = {key: sizes[key] for key in pins}
    lru: OrderedDict[Resource, None] = OrderedDict()
    resident = sum(resident_sizes.values())
    if resident > effective:
        raise SharedCacheError("mandatory pins exceed the shared budget")
    staged = resident
    preload = resident
    hits = misses = evictions = uses = 0
    peak = resident
    for event in events:
        group = set(event)
        if sum(sizes[key] for key in group | pinned_set) > effective:
            raise SharedCacheError("atomic routed expert group exceeds shared capacity")
        for key in event:
            uses += 1
            if key in resident_sizes:
                hits += 1
                if key not in pinned_set:
                    lru.move_to_end(key)
                continue
            misses += 1
            size = sizes[key]
            while resident + size > effective:
                victim = next((item for item in lru if item not in group), None)
                if victim is None:
                    raise SharedCacheError("no evictable victim for atomic expert group")
                lru.pop(victim)
                resident -= resident_sizes.pop(victim)
                evictions += 1
            resident_sizes[key] = size
            lru[key] = None
            resident += size
            staged += size
            peak = max(peak, resident)
        if resident > effective:
            raise SharedCacheError("simulated cache exceeded effective budget")
    if uses != hits + misses:
        raise SharedCacheError("accounting mismatch")
    return {
        "logical_staged_bytes": staged,
        "pinned_preload_bytes": preload,
        "demand_cache_hits": hits,
        "demand_cache_misses": misses,
        "evictions": evictions,
        "peak_hypothetical_resident_bytes": peak,
        "final_hypothetical_resident_bytes": resident,
        "routed_expert_accesses": uses,
    }


def evaluate(
    capture: object, footprints: object, *, capacity_bytes: int,
    reserve_bytes: int = 0, max_pins: int = 4,
) -> dict[str, object]:
    """Compare global pinned+LRU vs global unpinned LRU on ALL holdouts.

    Learning uses only train events and declared sizes. Size configuration,
    budgets and ranking are frozen before any holdout is replayed.
    """
    checked = _validate(capture)
    layers: list[int] = checked["layers"]
    phases: list[str] = checked["phases"]
    if len(layers) > MAX_LAYERS or len(phases) < 3:
        raise SharedCacheError("requires up to 32 layers and at least two holdouts")
    sizes, basis = _footprints(
        footprints, capture, layers, checked["expert_count"],
    )
    capacity = _int(capacity_bytes, "shared cache capacity", 1, MAX_CAPACITY_BYTES)
    reserve = _int(reserve_bytes, "global reserve", 0, capacity)
    request_pins = _int(max_pins, "train-only pin maximum", 0, MAX_PINS)
    effective = capacity - reserve
    by_split = _split_events(capture, layers, phases)
    holdouts = phases[1:]
    event_count = 0
    for holdout in holdouts:
        accesses = sum(len(event) for event in by_split[holdout])
        if accesses > MAX_ACCESS_PER_HOLDOUT:
            raise SharedCacheError("single holdout exceeds shared replay access budget")
        event_count += accesses
    if event_count > MAX_TOTAL_ACCESSES:
        raise SharedCacheError("complete holdout census exceeds shared replay limit")

    # Headroom is computed solely from the *declared shape vector*, not any
    # holdout trace. This avoids using holdout outcomes to pick pin capacity.
    largest_atomic = max(
        sum(sorted(
            (sizes[(layer, expert)] for expert in range(checked["expert_count"])),
            reverse=True,
        )[:8])
        for layer in layers
    )
    capture_sha = _hash(capture)
    footprint_sha = _hash(footprints)
    common: dict[str, object] = {
        "schema_version": REVIEW_SCHEMA,
        "scope": "one_shared_hypothetical_cache_across_layers_per_holdout",
        "source_capture_sha256": capture_sha,
        "footprint_manifest_sha256": footprint_sha,
        "source_kind": checked["kind"],
        "expert_size_basis": basis,
        "layers": len(layers),
        "holdout_count": len(holdouts),
        "declared_expert_count_per_layer": checked["expert_count"],
        "shared_capacity_bytes": capacity,
        "reserved_bytes": reserve,
        "effective_shared_capacity_bytes": effective,
        "maximum_possible_eight_expert_group_bytes": largest_atomic,
        "complete_holdout_accesses": event_count,
        "requested_max_train_only_pins": request_pins,
        "training_only_selection": True,
        "routing_source_authenticated": False,
        "weights_rehashed_here": False,
        "expert_size_independently_measured_here": False,
        "model_executed": False,
        "physical_transfer_bytes_measured": False,
        "wall_time_measured": False,
        "model_output_parity_checked": False,
        "speedup_proven": False,
        "automatic_promotion": False,
        "action_authority": False,
        "execution_authority": False,
        "hardware_control": False,
    }
    if largest_atomic > effective:
        result: dict[str, object] = {
            **common, "status": "HELD",
            "reason": "atomic_eight_expert_headroom_exceeds_effective_cache",
            "evaluated_holdouts": 0,
            "selected_pins_count": 0,
            "holdouts": None,
            "summary": None,
        }
        result["receipt_sha256"] = _hash(result)
        return result

    pin_capacity = effective - largest_atomic
    ranks = _rank_train(by_split["train"], sizes)
    pins: list[Resource] = []
    charged = 0
    for resource in ranks:
        if len(pins) >= request_pins:
            break
        size = sizes[resource]
        if charged + size <= pin_capacity:
            pins.append(resource)
            charged += size
    chosen = tuple(pins)
    policy_sha = _hash({
        "rule": "global_train_frequency_per_byte_desc_id_asc_v1",
        "train_events_sha256": _hash(by_split["train"]),
        "pinned_resources": [list(key) for key in chosen],
        "footprint_manifest_sha256": footprint_sha,
        "capacity": capacity, "reserve": reserve,
        "atomic_group_headroom_bytes": largest_atomic,
    })

    rows: list[dict[str, object]] = []
    lower = equal = higher = 0
    total_baseline = total_candidate = total_uses = total_preload = 0
    worst: int | None = None
    for name in holdouts:
        baseline = _simulate(by_split[name], sizes, effective, ())
        candidate = _simulate(by_split[name], sizes, effective, chosen)
        if baseline["routed_expert_accesses"] != candidate["routed_expert_accesses"]:
            raise SharedCacheError("paired holdout access census disagrees")
        delta = baseline["logical_staged_bytes"] - candidate["logical_staged_bytes"]
        lower += delta > 0
        equal += delta == 0
        higher += delta < 0
        worst = delta if worst is None else min(worst, delta)
        total_baseline += baseline["logical_staged_bytes"]
        total_candidate += candidate["logical_staged_bytes"]
        total_uses += baseline["routed_expert_accesses"]
        total_preload += candidate["pinned_preload_bytes"]
        rows.append({
            "holdout": name,
            "routed_expert_accesses": baseline["routed_expert_accesses"],
            "global_unpinned_lru": baseline,
            "global_train_pinned_lru": candidate,
            "signed_logical_stage_delta_bytes": delta,
        })
    if total_baseline <= 0 or total_uses != event_count:
        raise SharedCacheError("incomplete shared holdout accounting")
    summary: dict[str, object] = {
        "holdouts_lower_logical_bytes": lower,
        "holdouts_equal_logical_bytes": equal,
        "holdouts_higher_logical_bytes": higher,
        "all_holdouts_lower_logical_bytes": lower == len(holdouts),
        "worst_holdout_signed_delta_bytes": worst,
        "total_unpinned_lru_logical_staged_bytes": total_baseline,
        "total_train_pinned_lru_logical_staged_bytes": total_candidate,
        "total_pin_preloads_across_fresh_holdouts_bytes": total_preload,
        "total_signed_logical_stage_delta_bytes": total_baseline - total_candidate,
        "relative_logical_stage_delta_percent": round(
            100 * (total_baseline - total_candidate) / total_baseline, 4
        ),
    }
    result = {
        **common, "status": "REVIEW_REQUIRED", "reason": "simulation_only",
        "evaluated_holdouts": len(rows),
        "selected_pins_count": len(chosen),
        "frozen_global_train_only_policy_sha256": policy_sha,
        "holdouts": rows,
        "summary": summary,
    }
    result["receipt_sha256"] = _hash(result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="PhiOS R13: offline shared-budget native expert cache study"
    )
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--footprints", type=Path, required=True)
    parser.add_argument("--capacity-bytes", type=int, required=True)
    parser.add_argument("--reserve-bytes", type=int, default=0)
    parser.add_argument("--max-pins", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        result = evaluate(
            _read(args.capture), _read(args.footprints),
            capacity_bytes=args.capacity_bytes, reserve_bytes=args.reserve_bytes,
            max_pins=args.max_pins,
        )
    except (SharedCacheError, RouterBridgeError, OSError,
            RecursionError, OverflowError):
        print(json.dumps({"schema_version": REVIEW_SCHEMA, "status": "UNAVAILABLE",
                          "action_authority": False, "execution_authority": False},
                         sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 3 if result["status"] == "HELD" else 0


if __name__ == "__main__":
    sys.exit(main())
