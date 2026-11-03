"""PhiOS Elastic Runtime R1: deterministic, read-only bubble residency advisor.

This module parses caller-provided hypothetical observations. It does not inspect,
allocate, suspend, start, stop or otherwise interact with host resources.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

SNAPSHOT_SCHEMA = "phios.elastic.snapshot.v1"
RECEIPT_SCHEMA = "phios.elastic.advisory.v1"
MAX_SNAPSHOT_BYTES = 65536
MAX_BUBBLES = 64
MAX_DEPENDENCIES = 16
MAX_MIB = 1048576
_ID = re.compile(r"[a-z][a-z0-9._:-]{0,63}\Z")
_STATES = frozenset({"cold", "warm", "active", "pinned"})
_KINDS = frozenset({"service", "application", "model", "renderer", "hardware"})


class ElasticContractError(ValueError):
    """Invalid, ambiguous or unsupported advisory inputs."""


def _object(value: object, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields or any(
        not isinstance(key, str) for key in value
    ):
        raise ElasticContractError(f"invalid {label} fields")
    return value


def _ident(value: object, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ElasticContractError(f"invalid {label} identifier")
    return value


def _number(value: object, label: str) -> int:
    if type(value) is not int or not 0 <= value <= MAX_MIB:
        raise ElasticContractError(f"invalid {label} MiB quantity")
    return value


def _bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ElasticContractError(f"invalid {label} boolean")
    return value


def _priority(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 100:
        raise ElasticContractError("invalid priority")
    return value


@dataclass(frozen=True)
class Bubble:
    identifier: str
    kind: str
    observed_state: str
    demanded: bool
    pinned: bool
    prefetch: bool
    priority: int
    dependencies: tuple[str, ...]
    warm_ram_mib: int
    active_ram_mib: int
    active_vram_mib: int

    @classmethod
    def parse(cls, value: object) -> "Bubble":
        item = _object(value, {
            "id", "kind", "observed_state", "demanded", "pinned", "prefetch",
            "priority", "dependencies", "warm_ram_mib", "active_ram_mib", "active_vram_mib",
        }, "bubble")
        identifier = _ident(item["id"], "bubble")
        kind = item["kind"]
        state = item["observed_state"]
        if not isinstance(kind, str) or kind not in _KINDS:
            raise ElasticContractError("invalid bubble kind")
        if not isinstance(state, str) or state not in _STATES:
            raise ElasticContractError("invalid observed state")
        if not isinstance(item["dependencies"], list) or len(item["dependencies"]) > MAX_DEPENDENCIES:
            raise ElasticContractError("invalid dependencies")
        deps = tuple(_ident(dep, "dependency") for dep in item["dependencies"])
        if len(set(deps)) != len(deps) or identifier in deps:
            raise ElasticContractError("duplicate or self dependency")
        warm = _number(item["warm_ram_mib"], "warm RAM")
        active = _number(item["active_ram_mib"], "active RAM")
        if warm > active:
            raise ElasticContractError("warm RAM must not exceed active RAM")
        pinned = _bool(item["pinned"], "pinned")
        if pinned != (state == "pinned"):
            # Pinning is an operator-declared hard floor, not inferred automatically.
            raise ElasticContractError("pinned flag must match observed pinned state")
        return cls(
            identifier=identifier,
            kind=kind,
            observed_state=state,
            demanded=_bool(item["demanded"], "demanded"),
            pinned=pinned,
            prefetch=_bool(item["prefetch"], "prefetch"),
            priority=_priority(item["priority"]),
            dependencies=deps,
            warm_ram_mib=warm,
            active_ram_mib=active,
            active_vram_mib=_number(item["active_vram_mib"], "active VRAM"),
        )


def _decode(raw: bytes) -> object:
    if len(raw) > MAX_SNAPSHOT_BYTES:
        raise ElasticContractError("snapshot exceeds byte limit")

    def pairs(entries: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, val in entries:
            if key in result:
                raise ElasticContractError("duplicate JSON field")
            result[key] = val
        return result

    def reject_constant(_: str) -> None:
        raise ElasticContractError("non-finite JSON constant")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=reject_constant)
    except (UnicodeError, ValueError) as exc:
        raise ElasticContractError("invalid snapshot JSON") from exc


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _checked(snapshot: object) -> tuple[dict[str, Bubble], int, int]:
    source = _object(snapshot, {"schema_version", "budget", "bubbles"}, "snapshot")
    if source["schema_version"] != SNAPSHOT_SCHEMA:
        raise ElasticContractError("unknown snapshot schema")
    budget = _object(source["budget"], {"ram_mib", "vram_mib"}, "budget")
    ram = _number(budget["ram_mib"], "budget RAM")
    vram = _number(budget["vram_mib"], "budget VRAM")
    raw = source["bubbles"]
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_BUBBLES:
        raise ElasticContractError("invalid bubble count")
    bubbles = [Bubble.parse(entry) for entry in raw]
    ids = [item.identifier for item in bubbles]
    if len(set(ids)) != len(ids):
        raise ElasticContractError("duplicate bubble id")
    by_id = {item.identifier: item for item in bubbles}
    for bubble in bubbles:
        if any(dep not in by_id for dep in bubble.dependencies):
            raise ElasticContractError("unresolved dependency")
    # Validate entire graph, including dormant bubbles, so unexpected activation
    # can never bypass a latent cycle.
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in visiting:
            raise ElasticContractError("cyclic dependencies")
        if identifier in visited:
            return
        visiting.add(identifier)
        for dep in by_id[identifier].dependencies:
            visit(dep)
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in sorted(by_id):
        visit(identifier)
    return by_id, ram, vram


def advise(snapshot: object) -> dict[str, object]:
    """Recommend residency states without any host observation or system effects.

    Cost values are untrusted manifest estimates, not measured physical usage.
    Essential active/pinned demand is never silently demoted to fit a budget.
    """
    bubbles, ram_limit, vram_limit = _checked(snapshot)
    required = {bubble.identifier for bubble in bubbles.values() if bubble.demanded or bubble.pinned}
    stack = list(sorted(required))
    while stack:
        name = stack.pop()
        for dependency in bubbles[name].dependencies:
            if dependency not in required:
                required.add(dependency)
                stack.append(dependency)

    mandatory_ram = sum(bubbles[name].active_ram_mib for name in required)
    mandatory_vram = sum(bubbles[name].active_vram_mib for name in required)
    status = "HELD" if mandatory_ram > ram_limit or mandatory_vram > vram_limit else "ADVISORY"
    if status == "HELD":
        # A bad budget is a review blocker, never a license to evict essentials.
        rows: list[dict[str, object]] = []
        for name, bubble in sorted(bubbles.items()):
            rows.append({"id": name, "observed_state": bubble.observed_state,
                         "suggested_state": None, "reason": "mandatory_budget_overrun"})
        total_ram, total_vram = mandatory_ram, mandatory_vram
    else:
        targets: dict[str, tuple[str, str]] = {}
        for name in required:
            bubble = bubbles[name]
            targets[name] = ("pinned" if bubble.pinned else "active",
                             "pinned_floor" if bubble.pinned else "demand_or_dependency")
        total_ram, total_vram = mandatory_ram, mandatory_vram
        # Warm proposals are optional; admit highest priority first and only
        # when they fit. Nothing here predicts startup cost or actual reuse.
        optional = sorted((bubble for name, bubble in bubbles.items() if name not in required),
                          key=lambda b: (-b.priority, b.identifier))
        for bubble in optional:
            if bubble.prefetch and total_ram + bubble.warm_ram_mib <= ram_limit:
                targets[bubble.identifier] = ("warm", "prefetch_fits_ram_budget")
                total_ram += bubble.warm_ram_mib
            elif bubble.prefetch:
                targets[bubble.identifier] = ("cold", "warm_exceeds_ram_budget")
            else:
                targets[bubble.identifier] = ("cold", "no_declared_demand")
        rows = [{"id": name, "observed_state": bubble.observed_state,
                 "suggested_state": targets[name][0], "reason": targets[name][1]}
                for name, bubble in sorted(bubbles.items())]
    result: dict[str, object] = {
        "schema_version": RECEIPT_SCHEMA,
        "status": status,
        "mode": "offline_advisory_only",
        "inputs_are_measurements": False,
        "estimated_mib": {"ram": total_ram, "vram": total_vram},
        "budget_mib": {"ram": ram_limit, "vram": vram_limit},
        "mandatory_mib": {"ram": mandatory_ram, "vram": mandatory_vram},
        "decisions": rows,
        "action_authority": False,
        "execution_authority": False,
        "os_driver_control": False,
    }
    # Bind the validated input content and advisory output. Order-insensitive
    # to bubble/dependency ordering; includes all untrusted input values.
    input_canonical = {
        "schema_version": SNAPSHOT_SCHEMA,
        "budget": {"ram_mib": ram_limit, "vram_mib": vram_limit},
        "bubbles": [
            {"id": item.identifier, "kind": item.kind,
             "observed_state": item.observed_state, "demanded": item.demanded,
             "pinned": item.pinned, "prefetch": item.prefetch,
             "priority": item.priority, "dependencies": sorted(item.dependencies),
             "warm_ram_mib": item.warm_ram_mib,
             "active_ram_mib": item.active_ram_mib,
             "active_vram_mib": item.active_vram_mib}
            for _, item in sorted(bubbles.items())
        ],
    }
    result["snapshot_sha256"] = hashlib.sha256(_canonical(input_canonical)).hexdigest()
    result["receipt_sha256"] = hashlib.sha256(_canonical(result)).hexdigest()
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only PhiOS Elastic Runtime R1 planning")
    parser.add_argument("--snapshot", type=Path, required=True,
                        help="explicit local JSON fixture, no host sampling")
    args = parser.parse_args(argv)
    try:
        # CLI rejects giant files before reading into memory. No network, writes,
        # subprocesses, user identity lookup or live service interactions.
        if not args.snapshot.is_file() or args.snapshot.is_symlink():
            raise ElasticContractError("snapshot must be a regular non-symlink file")
        if args.snapshot.stat().st_size > MAX_SNAPSHOT_BYTES:
            raise ElasticContractError("snapshot exceeds byte limit")
        receipt = advise(_decode(args.snapshot.read_bytes()))
    except (OSError, ElasticContractError, RecursionError):
        print(json.dumps({"schema_version": RECEIPT_SCHEMA, "status": "UNAVAILABLE",
                          "action_authority": False, "execution_authority": False},
                         sort_keys=True))
        return 2
    print(json.dumps(receipt, sort_keys=True, indent=2))
    return 0 if receipt["status"] == "ADVISORY" else 3


if __name__ == "__main__":
    sys.exit(main())
