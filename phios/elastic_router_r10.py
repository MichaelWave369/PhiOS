"""PhiOS Elastic R10: import PocketRotor E2-R selected-expert routing for R9 replay.

Only user-selected, unverified, *post-router* expert IDs are replayed.
No model, weight file, PhiStream code, GPU, service or device is accessed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any, Sequence

from phios.elastic_cache_r9 import CacheShadowError, simulate

CAPTURE_SCHEMA = "PHISTREAM_POCKETROTOR_E2_NATIVE_ROUTE_CAPTURE_V1"
RESULT_SCHEMA = "phios.elastic.pocketrotor-cache-bridge.v1"
MAX_CAPTURE_BYTES = 2 * 1024 * 1024
MAX_EVENTS = 16384
_MAX_EXPERT_BYTES = 16 * 1024 * 1024
_MAX_BUDGET_BYTES = 2 * 1024**3
_SPLIT = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class RouterBridgeError(ValueError):
    """Invalid, unsupported, or unsafe PocketRotor trace or replay selection."""


def _object(value: object, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise RouterBridgeError(f"invalid {label} fields")
    return value


def _int(value: object, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise RouterBridgeError(f"invalid {label}")
    return value


def _hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True, allow_nan=False).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def _validate(capture: object) -> dict[str, Any]:
    root = _object(capture, {"schema", "expert_count", "source", "events"}, "capture")
    if root["schema"] != CAPTURE_SCHEMA:
        raise RouterBridgeError("unsupported native routing capture schema")
    n_experts = _int(root["expert_count"], "expert count", 4, 256)
    source = _object(root["source"], {
        "kind", "runtime", "model_id", "checkpoint_sha256",
        "route_semantics", "token_text_recorded",
    }, "source")
    if source["kind"] not in ("synthetic", "operator_asserted_native"):
        raise RouterBridgeError("source kind must distinguish synthetic/native assertion")
    for field in ("runtime", "model_id"):
        name = source[field]
        if (not isinstance(name, str) or not 1 <= len(name) <= 120 or
                any(not 32 <= ord(letter) <= 126 for letter in name)):
            raise RouterBridgeError("invalid source label")
    sha = source["checkpoint_sha256"]
    if not isinstance(sha, str) or not _DIGEST.fullmatch(sha):
        raise RouterBridgeError("invalid declared checkpoint fingerprint")
    if (source["route_semantics"] != "POST_NATIVE_ROUTER_SELECTED_EXPERT_IDS" or
            source["token_text_recorded"] is not False):
        raise RouterBridgeError("only post-router IDs without text are supported")
    raw_events = root["events"]
    if not isinstance(raw_events, list) or not 4 <= len(raw_events) <= MAX_EVENTS:
        raise RouterBridgeError("invalid capture event count")
    streams: dict[str, dict[int, list[list[int]]]] = {}
    phases: list[str] = []
    for item in raw_events:
        event = _object(item, {"split", "layer", "step", "experts"}, "event")
        split = event["split"]
        if not isinstance(split, str) or not _SPLIT.fullmatch(split):
            raise RouterBridgeError("invalid split label")
        layer = _int(event["layer"], "layer", 0, 127)
        step = _int(event["step"], "step", 0, 4095)
        experts = event["experts"]
        if (not isinstance(experts, list) or not 1 <= len(experts) <= 8 or
                any(type(e) is not int or not 0 <= e < n_experts for e in experts) or
                len(set(experts)) != len(experts)):
            raise RouterBridgeError("invalid selected experts")
        if not phases or phases[-1] != split:
            if split in streams or (not phases and split != "train") or (
                phases and split == "train"
            ):
                raise RouterBridgeError("train/holdout split order invalid")
            phases.append(split)
            streams[split] = {}
        series = streams[split].setdefault(layer, [])
        if step != len(series):
            raise RouterBridgeError("duplicate, skipped or reordered layer event")
        series.append(list(experts))
    if not 2 <= len(phases) <= 9:
        raise RouterBridgeError("requires train and 1–8 holdouts")
    layers = sorted(streams["train"])
    if not layers:
        raise RouterBridgeError("no routed layers")
    for split in phases:
        mapping = streams[split]
        if sorted(mapping) != layers:
            raise RouterBridgeError("split layer coverage differs")
        steps = {len(mapping[layer]) for layer in layers}
        if len(steps) != 1 or not 2 <= next(iter(steps)) <= 4096:
            raise RouterBridgeError("missing or unequal per-layer steps")
    return {
        "kind": source["kind"], "expert_count": n_experts,
        "streams": streams, "layers": layers, "phases": phases,
    }


def bridge(
    capture: object, *, layer: int, holdout: str, expert_bytes: int,
    capacity_bytes: int, reserve_bytes: int = 0, pinned_experts: Sequence[int] = (),
) -> dict[str, object]:
    """Convert one holdout/layer to a deterministic R9 shadow cache simulation."""
    checked = _validate(capture)
    layers = checked["layers"]
    phases = checked["phases"]
    if type(layer) is not int or layer not in layers:
        raise RouterBridgeError("chosen layer not in every split")
    if not isinstance(holdout, str) or holdout not in phases[1:]:
        raise RouterBridgeError("choose a declared holdout, never the training split")
    size = _int(expert_bytes, "assumed expert bytes", 1, _MAX_EXPERT_BYTES)
    capacity = _int(capacity_bytes, "capacity bytes", 1, _MAX_BUDGET_BYTES)
    reserve = _int(reserve_bytes, "reserve bytes", 0, capacity)
    count = checked["expert_count"]
    if (not isinstance(pinned_experts, (list, tuple)) or
            len(pinned_experts) > 128 or
            any(type(e) is not int or not 0 <= e < count for e in pinned_experts) or
            len(set(pinned_experts)) != len(pinned_experts)):
        raise RouterBridgeError("invalid explicitly pinned expert list")

    streams = checked["streams"]
    groups = streams[holdout][layer]
    selected = [expert for experts in groups for expert in experts]
    if not 1 <= len(selected) <= 4096:
        raise RouterBridgeError("selected holdout exceeds R9 event budget")
    resource_numbers = sorted(set(selected) | set(pinned_experts))
    if len(resource_numbers) > 128:
        raise RouterBridgeError("selected working set exceeds R9 resource cap")
    capture_sha = _hash(capture)
    workload = _hash({
        "capture_sha256": capture_sha, "layer": layer, "holdout": holdout,
        "expert_bytes": size,
    })
    study = {
        "schema_version": "phios.elastic.cache-shadow-study.v1",
        "scenario": f"pocketrotor-layer-{layer}-{holdout}",
        "workload_sha256": workload,
        "source": "operator_supplied_unverified",
        "budget": {"capacity_bytes": capacity, "reserve_bytes": reserve},
        "resources": [
            {"id": f"expert-{e}", "bytes": size, "pinned": e in pinned_experts}
            for e in resource_numbers
        ],
        "accesses": [f"expert-{e}" for e in selected],
    }
    try:
        shadow = simulate(study)
    except CacheShadowError as exc:
        raise RouterBridgeError("R9 cache study refused this route") from exc
    result: dict[str, object] = {
        "schema_version": RESULT_SCHEMA,
        "status": shadow["status"],
        "source_capture_schema": CAPTURE_SCHEMA,
        "source_capture_sha256": capture_sha,
        "source_kind": checked["kind"],
        "routing_source_authenticated": False,
        "selected_layer": layer,
        "selected_holdout": holdout,
        "holdout_steps": len(groups),
        "routed_expert_accesses": len(selected),
        "unique_accessed_experts": len(set(selected)),
        "expert_size_assumed_not_measured_bytes": size,
        "pinned_experts_declared_count": len(pinned_experts),
        "shadow": shadow,
        "actual_weight_transfers_measured": False,
        "model_output_parity_checked": False,
        "model_execution": False,
        "performance_improvement_proven": False,
        "action_authority": False,
        "execution_authority": False,
        "hardware_control": False,
    }
    result["receipt_sha256"] = _hash(result)
    return result


def _read(path: Path) -> object:
    try:
        if path.is_symlink():
            raise RouterBridgeError("symlink capture refused")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) |
                     getattr(os, "O_NOFOLLOW", 0))
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or not 1 <= info.st_size <= MAX_CAPTURE_BYTES:
                raise RouterBridgeError("capture must be a bounded regular file")
            with os.fdopen(fd, "rb", closefd=False) as handle:
                raw = handle.read(MAX_CAPTURE_BYTES + 1)
        finally:
            os.close(fd)
    except OSError as exc:
        raise RouterBridgeError("capture file unavailable") from exc
    if len(raw) > MAX_CAPTURE_BYTES:
        raise RouterBridgeError("capture too large")

    def unique(fields: list[tuple[str, object]]) -> dict[str, object]:
        obj: dict[str, object] = {}
        for key, val in fields:
            if key in obj:
                raise RouterBridgeError("duplicate JSON key")
            obj[key] = val
        return obj

    def invalid(_: str) -> None:
        raise RouterBridgeError("nonfinite JSON constant")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                          parse_constant=invalid)
    except (UnicodeError, ValueError) as exc:
        raise RouterBridgeError("invalid capture JSON") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PhiOS R10: offline PocketRotor routing to R9")
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--layer", required=True, type=int)
    parser.add_argument("--holdout", required=True)
    parser.add_argument("--expert-bytes", required=True, type=int)
    parser.add_argument("--capacity-bytes", required=True, type=int)
    parser.add_argument("--reserve-bytes", default=0, type=int)
    parser.add_argument("--pin-expert", type=int, action="append", default=[])
    args = parser.parse_args(argv)
    try:
        report = bridge(
            _read(args.capture), layer=args.layer, holdout=args.holdout,
            expert_bytes=args.expert_bytes, capacity_bytes=args.capacity_bytes,
            reserve_bytes=args.reserve_bytes, pinned_experts=args.pin_expert,
        )
    except (RouterBridgeError, OSError, RecursionError, OverflowError):
        print(json.dumps({"schema_version": RESULT_SCHEMA, "status": "UNAVAILABLE",
                          "action_authority": False, "execution_authority": False},
                         sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
    return 3 if report["status"] == "HELD" else 0


if __name__ == "__main__":
    sys.exit(main())
