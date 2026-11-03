"""PhiOS Elastic Runtime R2: opt-in, read-only system resource samples.

No background service, process listing, authority, driver manipulation or file writes.
The operator starts each capture and chooses what to save from stdout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence, cast

import psutil

SCHEMA = "phios.elastic.observation.v1"
MAX_SAMPLES = 120
MIN_INTERVAL_MS = 100
MAX_INTERVAL_MS = 10000
MAX_INPUT_BYTES = 256 * 1024
_SCENARIO = re.compile(r"[a-z][a-z0-9._-]{0,63}\Z")
_NVIDIA_QUERY = [
    "nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu",
    "--format=csv,noheader,nounits",
]


class ObservationError(ValueError):
    """Invalid capture, unavailable mandatory data, or invalid receipt."""


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
                      allow_nan=False).encode("ascii")


def _sha(value: object) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _finite(value: object, label: str, *, minimum: float = 0,
            maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ObservationError(f"invalid {label}")
    number = float(value)
    if not math.isfinite(number) or number < minimum or (maximum is not None and number > maximum):
        raise ObservationError(f"invalid {label}")
    return number


def _sample_gpu() -> dict[str, int] | None:
    """Optional read-only NVIDIA CLI query, never a driver or GPU configuration change."""
    try:
        process = subprocess.run(_NVIDIA_QUERY, capture_output=True, text=True,
                                 timeout=3, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if process.returncode != 0:
        return None
    lines = process.stdout.strip().splitlines()
    # Do not silently pick one card out of multiple GPUs: R2 has no identity policy.
    if len(lines) != 1:
        return None
    fields = [f.strip() for f in lines[0].split(",")]
    if len(fields) != 3 or any(not field.isascii() or not field.isdecimal() for field in fields):
        return None
    used, total, utilization = (int(field) for field in fields)
    if total <= 0 or used > total or utilization > 100:
        return None
    return {"memory_used_mib": used, "memory_total_mib": total,
            "utilization_percent": utilization}


def _quantile_nearest_rank(values: list[float], p: float) -> float:
    if not values:
        raise ObservationError("no observed samples")
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(p * len(ordered)) - 1)], 2)


def _stats(values: list[float]) -> dict[str, float]:
    return {"p50": _quantile_nearest_rank(values, .50),
            "p95": _quantile_nearest_rank(values, .95),
            "p99": _quantile_nearest_rank(values, .99)}


def collect(
    *, scenario: str, samples: int = 10, interval_ms: int = 200,
    include_gpu: bool = False,
    cpu_probe: Callable[[float], float] | None = None,
    memory_probe: Callable[[], Any] | None = None,
    gpu_probe: Callable[[], dict[str, int] | None] | None = None,
    clock_ns: Callable[[], int] | None = None,
    utc_now: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """Perform a bounded capture only when explicitly called.

    Injection points enable CI tests with synthetic probes; default probes read
    host-wide counters only. A sample is not a latency/performance benchmark.
    """
    if not isinstance(scenario, str) or not _SCENARIO.fullmatch(scenario):
        raise ObservationError("invalid scenario label")
    if type(samples) is not int or not 1 <= samples <= MAX_SAMPLES:
        raise ObservationError("invalid bounded sample count")
    if type(interval_ms) is not int or not MIN_INTERVAL_MS <= interval_ms <= MAX_INTERVAL_MS:
        raise ObservationError("invalid bounded interval")
    if not isinstance(include_gpu, bool):
        raise ObservationError("GPU capture option must be boolean")
    cpu = cpu_probe if cpu_probe is not None else lambda interval: psutil.cpu_percent(interval=interval)
    memory = memory_probe if memory_probe is not None else psutil.virtual_memory
    gpu = gpu_probe if gpu_probe is not None else _sample_gpu
    monotonic = clock_ns if clock_ns is not None else time.monotonic_ns
    now = utc_now if utc_now is not None else lambda: datetime.now(timezone.utc)
    timestamp = now()
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ObservationError("capture timestamp must be timezone-aware")
    started = monotonic()
    rows: list[dict[str, object]] = []
    missing_gpu = 0
    for index in range(samples):
        try:
            cpu_percent = _finite(cpu(interval_ms / 1000), "CPU percentage", maximum=100)
            mem = memory()
            total = _finite(mem.total, "total RAM bytes")
            available = _finite(mem.available, "available RAM bytes")
            if total <= 0 or available > total:
                raise ObservationError("inconsistent RAM counters")
            # Rather than 'used', which varies by OS semantics, use total-available
            # as a stable *approximation* of memory under pressure.
            pressure_mib = round((total - available) / 1048576, 2)
            ram_total_mib = round(total / 1048576, 2)
            available_mib = round(available / 1048576, 2)
            elapsed = monotonic() - started
            if type(elapsed) is not int or elapsed < 0:
                raise ObservationError("invalid monotonic clock")
            row: dict[str, object] = {
                "index": index, "elapsed_ms": round(elapsed / 1_000_000, 2),
                "cpu_percent": round(cpu_percent, 2),
                "ram_pressure_mib": pressure_mib, "ram_available_mib": available_mib,
                "ram_total_mib": ram_total_mib,
            }
            if include_gpu:
                observed_gpu = gpu()
                if observed_gpu is None:
                    row["gpu"] = None
                    missing_gpu += 1
                else:
                    if not isinstance(observed_gpu, dict) or set(observed_gpu) != {
                        "memory_used_mib", "memory_total_mib", "utilization_percent"
                    }:
                        raise ObservationError("invalid GPU observation")
                    used = observed_gpu["memory_used_mib"]
                    capacity = observed_gpu["memory_total_mib"]
                    utilization = observed_gpu["utilization_percent"]
                    if any(type(n) is not int for n in (used, capacity, utilization)) or not (
                        0 <= used <= capacity and capacity > 0 and 0 <= utilization <= 100
                    ):
                        raise ObservationError("inconsistent GPU counters")
                    row["gpu"] = dict(observed_gpu)
            rows.append(row)
        except (AttributeError, OSError) as exc:
            raise ObservationError("mandatory host counters unavailable") from exc

    cpu_stats = _stats([cast(float, row["cpu_percent"]) for row in rows])
    ram_stats = _stats([cast(float, row["ram_pressure_mib"]) for row in rows])
    gpu_rows = [cast(dict[str, int], row["gpu"]) for row in rows
                if include_gpu and row["gpu"] is not None]
    gpu_stats: dict[str, object] | None = None
    if gpu_rows:
        gpu_stats = {
            "memory_used_mib": _stats([float(g["memory_used_mib"]) for g in gpu_rows]),
            "utilization_percent": _stats([float(g["utilization_percent"]) for g in gpu_rows]),
        }
    receipt: dict[str, object] = {
        "schema_version": SCHEMA,
        "status": "PARTIAL" if missing_gpu else "OBSERVED",
        "source": "operator_local_unverified",
        "scope": "bounded_samples_not_continuous_monitoring",
        "captured_at_utc": timestamp.astimezone(timezone.utc).isoformat(),
        "scenario": scenario,
        "requested": {"samples": samples, "interval_ms": interval_ms,
                      "gpu": include_gpu},
        "measurements": {
            "cpu": "psutil_total_cpu_percent",
            "ram": "psutil_total_minus_available_approximation",
            "gpu": "nvidia_smi_query" if include_gpu else "not_requested",
        },
        "samples": rows,
        "summary": {"cpu_percent": cpu_stats, "ram_pressure_mib": ram_stats,
                    "gpu": gpu_stats, "gpu_samples_unavailable": missing_gpu},
        "action_authority": False,
        "execution_authority": False,
        "hardware_control": False,
        "performance_improvement_proven": False,
    }
    receipt["receipt_sha256"] = _sha(receipt)
    return receipt


def verify_receipt(data: object) -> dict[str, object]:
    """Validate an exported R2 receipt's shape and accidental-integrity digest.

    This is not attestation: a local sender can recompute its own digest.
    """
    if not isinstance(data, dict) or set(data) != {
        "schema_version", "status", "source", "scope", "captured_at_utc", "scenario",
        "requested", "measurements", "samples", "summary", "action_authority",
        "execution_authority", "hardware_control", "performance_improvement_proven",
        "receipt_sha256",
    }:
        raise ObservationError("invalid receipt shape")
    if data["schema_version"] != SCHEMA or data["status"] not in {"OBSERVED", "PARTIAL"}:
        raise ObservationError("unexpected receipt schema or status")
    if any(data[key] is not False for key in (
        "action_authority", "execution_authority", "hardware_control",
        "performance_improvement_proven",
    )):
        raise ObservationError("unexpected authority or performance assertion")
    digest = data["receipt_sha256"]
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ObservationError("invalid receipt digest")
    values = {key: value for key, value in data.items() if key != "receipt_sha256"}
    if _sha(values) != digest:
        raise ObservationError("receipt integrity check failed")
    # Receipts are self-reported and untrusted. No promotion of their fields.
    return data


def _read_json(path: Path) -> object:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
        raise ObservationError("receipt must be a bounded, regular, non-symlink file")
    raw = path.read_bytes()

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ObservationError("duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(_: str) -> None:
        raise ObservationError("non-finite JSON constant")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=reject_constant)
    except (UnicodeError, ValueError) as exc:
        raise ObservationError("invalid JSON") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PhiOS Elastic R2 opt-in resource observations")
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("collect", help="sample current host; stdout JSON only")
    capture.add_argument("--scenario", required=True)
    capture.add_argument("--samples", type=int, default=10)
    capture.add_argument("--interval-ms", type=int, default=200)
    capture.add_argument("--gpu", action="store_true", help="opt in to read-only nvidia-smi query")
    review = commands.add_parser("verify", help="verify bounded exported JSON receipt")
    review.add_argument("--input", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "collect":
            result = collect(scenario=args.scenario, samples=args.samples,
                             interval_ms=args.interval_ms, include_gpu=args.gpu)
        else:
            result = verify_receipt(_read_json(args.input))
    except (OSError, ObservationError, OverflowError):
        print(json.dumps({"schema_version": SCHEMA, "status": "UNAVAILABLE",
                          "action_authority": False, "execution_authority": False},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0 if result["status"] == "OBSERVED" else 3


if __name__ == "__main__":
    sys.exit(main())
