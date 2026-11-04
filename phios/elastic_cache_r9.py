"""PhiOS Elastic R9: deterministic shadow simulation of bounded cache residency.

No checkpoints, CUDA, mmap, services, processes, or host hardware are opened.
All byte sizes and access events are explicit, untrusted declarations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any, Sequence

STUDY_SCHEMA = "phios.elastic.cache-shadow-study.v1"
REPORT_SCHEMA = "phios.elastic.cache-shadow-review.v1"
MAX_INPUT_BYTES = 512 * 1024
MAX_RESOURCES = 128
MAX_ACCESS_EVENTS = 4096
MAX_RESOURCE_BYTES = 16 * 1024**3
MAX_CAPACITY_BYTES = 64 * 1024**3
_IDENTIFIER = re.compile(r"[a-z][a-z0-9._:-]{0,63}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class CacheShadowError(ValueError):
    """Invalid, unsupported or unsafe cache-shadow input."""


def _object(value: object, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise CacheShadowError(f"invalid {label} fields")
    return value


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise CacheShadowError(f"invalid {label}")
    return value


def _integer(value: object, label: str, *, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise CacheShadowError(f"invalid {label}")
    return value


def _hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _parse(study: object) -> tuple[dict[str, object], dict[str, tuple[int, bool]],
                                   list[str], int, int]:
    root = _object(study, {
        "schema_version", "scenario", "workload_sha256", "source",
        "budget", "resources", "accesses",
    }, "study")
    if root["schema_version"] != STUDY_SCHEMA:
        raise CacheShadowError("unsupported study schema")
    scenario = _identifier(root["scenario"], "scenario identifier")
    workload_hash = root["workload_sha256"]
    if not isinstance(workload_hash, str) or not _DIGEST.fullmatch(workload_hash):
        raise CacheShadowError("invalid workload hash")
    if root["source"] != "operator_supplied_unverified":
        raise CacheShadowError("unsupported provenance assertion")
    budget = _object(root["budget"], {"capacity_bytes", "reserve_bytes"}, "budget")
    capacity = _integer(budget["capacity_bytes"], "capacity", low=1,
                        high=MAX_CAPACITY_BYTES)
    reserve = _integer(budget["reserve_bytes"], "reserve", low=0, high=capacity)
    original_resources = root["resources"]
    if (not isinstance(original_resources, list)
            or not 1 <= len(original_resources) <= MAX_RESOURCES):
        raise CacheShadowError("invalid number of resources")
    resources: dict[str, tuple[int, bool]] = {}
    for raw in original_resources:
        entry = _object(raw, {"id", "bytes", "pinned"}, "resource")
        name = _identifier(entry["id"], "resource identifier")
        if name in resources:
            raise CacheShadowError("duplicate resource identifier")
        size = _integer(entry["bytes"], "resource bytes", low=1, high=MAX_RESOURCE_BYTES)
        if type(entry["pinned"]) is not bool:
            raise CacheShadowError("pinned must be Boolean")
        resources[name] = (size, entry["pinned"])
    original_accesses = root["accesses"]
    if (not isinstance(original_accesses, list)
            or not 1 <= len(original_accesses) <= MAX_ACCESS_EVENTS):
        raise CacheShadowError("invalid access trace length")
    accesses: list[str] = []
    for item in original_accesses:
        name = _identifier(item, "access identifier")
        if name not in resources:
            raise CacheShadowError("unknown accessed resource")
        accesses.append(name)
    canonical: dict[str, object] = {
        "schema_version": STUDY_SCHEMA,
        "scenario": scenario,
        "workload_sha256": workload_hash,
        "source": "operator_supplied_unverified",
        "budget": {"capacity_bytes": capacity, "reserve_bytes": reserve},
        "resources": [
            {"id": name, "bytes": size, "pinned": pinned}
            for name, (size, pinned) in sorted(resources.items())
        ],
        "accesses": accesses,
    }
    return canonical, resources, accesses, capacity, reserve


def simulate(study: object) -> dict[str, object]:
    """Compare stream-on-every-use with a pinned+LRU shadow policy.

    A pin is a *hypothetical eager load*, included in candidate byte cost even
    if never accessed. Oversized non-pinned resources are streamed without
    admission; no mandatory pin is ever silently evicted or demoted.
    """
    canonical, resources, accesses, capacity, reserve = _parse(study)
    effective = capacity - reserve
    pinned = {name: size for name, (size, required) in resources.items() if required}
    pinned_bytes = sum(pinned.values())
    baseline_bytes = sum(resources[name][0] for name in accesses)
    source_hash = _hash(canonical)
    common: dict[str, object] = {
        "schema_version": REPORT_SCHEMA,
        "mode": "offline_shadow_simulation",
        "scenario": canonical["scenario"],
        "source": "operator_supplied_unverified",
        "source_sha256": source_hash,
        "access_event_count": len(accesses),
        "resource_count": len(resources),
        "budget_bytes": {
            "capacity": capacity, "reserve": reserve, "effective": effective,
            "mandatory_pinned": pinned_bytes,
        },
        "baseline_logical_staged_bytes": baseline_bytes,
        "physical_transfer_bytes_measured": False,
        "wall_time_measured": False,
        "model_output_parity_checked": False,
        "performance_improvement_proven": False,
        "automatic_promotion": False,
        "action_authority": False,
        "execution_authority": False,
        "hardware_control": False,
    }
    if pinned_bytes > effective:
        result: dict[str, object] = {
            **common, "status": "HELD",
            "reason": "mandatory_pins_exceed_effective_budget",
            "candidate": None,
        }
        result["receipt_sha256"] = _hash(result)
        return result

    # Only this dictionary and OrderedDict represent hypothetical residency.
    # No actual resource is opened, loaded, pinned, copied, or unloaded.
    cache: dict[str, int] = dict(pinned)
    lru: OrderedDict[str, None] = OrderedDict()
    resident = pinned_bytes
    peak = resident
    staged_bytes = pinned_bytes
    hits = misses = evictions = bypassed = 0
    for name in accesses:
        size, is_pinned = resources[name]
        if name in cache:
            hits += 1
            if not is_pinned:
                lru.move_to_end(name)
            continue
        misses += 1
        staged_bytes += size
        if size > effective - pinned_bytes:
            bypassed += 1
            continue
        while resident + size > effective:
            if not lru:
                raise CacheShadowError("LRU state inconsistent with effective budget")
            victim, _ = lru.popitem(last=False)
            resident -= cache.pop(victim)
            evictions += 1
        cache[name] = size
        lru[name] = None
        resident += size
        peak = max(peak, resident)
        if resident > effective:
            raise CacheShadowError("simulator exceeded budget")
    candidate: dict[str, object] = {
        "policy": "mandatory_pins_and_lru",
        "logical_staged_bytes": staged_bytes,
        "logical_stage_operations": len(pinned) + misses,
        "hypothetical_preload_bytes": pinned_bytes,
        "cache_hits": hits,
        "cache_misses": misses,
        "evictions": evictions,
        "uncacheable_accesses": bypassed,
        "peak_hypothetical_resident_bytes": peak,
        "final_hypothetical_resident_bytes": resident,
        "remaining_budget_bytes": effective - resident,
        "logical_stage_bytes_delta_vs_baseline": baseline_bytes - staged_bytes,
        "relative_logical_stage_reduction_percent": round(
            100 * (baseline_bytes - staged_bytes) / baseline_bytes, 4
        ),
    }
    if hits + misses != len(accesses):
        raise CacheShadowError("accounting mismatch")
    result = {**common, "status": "REVIEW_REQUIRED", "reason": "simulation_only",
              "candidate": candidate}
    result["receipt_sha256"] = _hash(result)
    return result


def _read(path: Path) -> object:
    """Read exactly one manually selected bounded regular JSON file."""
    try:
        if path.is_symlink():
            raise CacheShadowError("symlink input refused")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) |
                     getattr(os, "O_NOFOLLOW", 0))
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or not 1 <= info.st_size <= MAX_INPUT_BYTES:
                raise CacheShadowError("invalid input size or file type")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(MAX_INPUT_BYTES + 1)
        finally:
            os.close(fd)
    except OSError as exc:
        raise CacheShadowError("study unavailable") from exc
    if len(raw) > MAX_INPUT_BYTES:
        raise CacheShadowError("input exceeds byte limit")

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        entry: dict[str, object] = {}
        for key, value in items:
            if key in entry:
                raise CacheShadowError("duplicate JSON key")
            entry[key] = value
        return entry

    def reject(_: str) -> None:
        raise CacheShadowError("nonfinite JSON constant")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=reject)
    except (UnicodeError, ValueError) as exc:
        raise CacheShadowError("malformed study JSON") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="PhiOS R9 shadow cache replay: simulation only, no GPU action"
    )
    parser.add_argument("--study", type=Path, required=True,
                        help="explicit local cache-shadow study JSON")
    args = parser.parse_args(argv)
    try:
        report = simulate(_read(args.study))
    except (CacheShadowError, OSError, RecursionError, OverflowError):
        print(json.dumps({"schema_version": REPORT_SCHEMA, "status": "UNAVAILABLE",
                          "action_authority": False, "execution_authority": False},
                         sort_keys=True))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 3 if report["status"] == "HELD" else 0


if __name__ == "__main__":
    sys.exit(main())
