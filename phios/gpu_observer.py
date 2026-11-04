"""Read-only, bounded GPU observation and comparable-run analysis for PhiOS.

No driver writes, unlocks, clocks, power changes, uploads, or benchmark load.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
from pathlib import Path
from typing import Any, Callable

SCHEMA = "phios.gpu-observation.v1"
FIELDS = (
    "name", "memory.total", "memory.used", "utilization.gpu",
    "utilization.memory", "temperature.gpu", "power.draw",
    "power.limit", "driver_version",
)
QUERY = ["nvidia-smi", "--query-gpu=" + ",".join(FIELDS), "--format=csv,noheader,nounits"]
COMPARISON_KEYS = ("workload", "gpu", "precision", "batch", "resolution", "execution_mode")


def _number(value: str) -> float | None:
    try:
        number = float(value.strip())
        return number if math.isfinite(number) and number >= 0 else None
    except (TypeError, ValueError):
        return None


def parse_nvidia_smi(output: str) -> list[dict[str, Any]]:
    """Parse only known query columns; unavailable readings remain null."""
    if len(output) > 32768:
        raise ValueError("GPU response exceeds 32 KiB limit")
    rows = list(csv.reader(output.splitlines()))
    if len(rows) > 16:
        raise ValueError("More than 16 GPU rows are not supported")
    devices: list[dict[str, Any]] = []
    for row in rows:
        if len(row) != len(FIELDS):
            raise ValueError("Unexpected NVIDIA query format")
        name, total, used, compute, memory, temp, draw, limit, driver = (v.strip() for v in row)
        total_mb, used_mb = _number(total), _number(used)
        gpu_util, memory_util = _number(compute), _number(memory)
        pressure = (used_mb / total_mb) if total_mb and used_mb is not None else None
        devices.append({
            "name": name[:128], "driver": driver[:64],
            "vram_total_mib": total_mb, "vram_used_mib": used_mb,
            "vram_fraction": round(pressure, 4) if pressure is not None else None,
            "gpu_utilization_percent": gpu_util,
            "memory_controller_utilization_percent": memory_util,
            "temperature_c": _number(temp), "power_w": _number(draw),
            "power_limit_w": _number(limit),
        })
    return devices


def recommendations(device: dict[str, Any]) -> list[str]:
    """Hints, not conclusive diagnoses from a single utilization sample."""
    hints: list[str] = []
    fraction = device.get("vram_fraction")
    busy = device.get("gpu_utilization_percent")
    if fraction is not None and fraction >= 0.9:
        hints.append("VRAM near capacity: consider smaller batches or quantization; compare actual runtimes.")
    if busy is not None and busy >= 90:
        hints.append("GPU busy at this instant: profile kernels before calling it compute-bound.")
    if not hints:
        hints.append("One snapshot cannot distinguish compute, bandwidth, CPU or I/O bottlenecks.")
    return hints


def observe(*, runner: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    try:
        result = runner(QUERY, capture_output=True, text=True, timeout=4, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"schema": SCHEMA, "source": "nvidia-smi", "status": "unavailable",
                "devices": [], "reason": type(exc).__name__, "authority": "observe-only"}
    if result.returncode != 0:
        return {"schema": SCHEMA, "source": "nvidia-smi", "status": "unavailable",
                "devices": [], "reason": "query_failed", "authority": "observe-only"}
    try:
        devices = parse_nvidia_smi(result.stdout)
    except ValueError:
        return {"schema": SCHEMA, "source": "nvidia-smi", "status": "unavailable",
                "devices": [], "reason": "malformed_response", "authority": "observe-only"}
    for device in devices:
        device["advisory_hints"] = recommendations(device)
    return {"schema": SCHEMA, "source": "nvidia-smi", "status": "observed" if devices else "unavailable",
            "devices": devices, "authority": "observe-only",
            "limitations": ["A single sampled utilization snapshot is not a bottleneck proof.",
                            "No Tensor Core throughput or memory bandwidth is measured."]}


def compare(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compare *user-supplied* wall-clock observations without inventing benchmarks."""
    if any(before.get(key) is None or before.get(key) != after.get(key) for key in COMPARISON_KEYS):
        raise ValueError("Comparison requires identical workload, GPU, precision, batch, resolution and mode")
    if before.get("schema") != "phios.gpu-run.v1" or after.get("schema") != "phios.gpu-run.v1":
        raise ValueError("Both measurements must use phios.gpu-run.v1")
    first_raw, second_raw = before.get("duration_ms"), after.get("duration_ms")
    if (isinstance(first_raw, bool) or isinstance(second_raw, bool)
            or not isinstance(first_raw, (int, float))
            or not isinstance(second_raw, (int, float))):
        raise ValueError("Duration must be a positive, finite number of milliseconds")
    first, second = float(first_raw), float(second_raw)
    if not math.isfinite(first) or not math.isfinite(second) or first <= 0 or second <= 0:
        raise ValueError("Duration must be a positive, finite number of milliseconds")
    return {"schema": "phios.gpu-comparison.v1",
            "workload": before["workload"], "gpu": before["gpu"],
            "speedup_ratio": round(first / second, 4),
            "elapsed_time_reduction_percent": round((1 - second / first) * 100, 2),
            "samples_per_condition": 1, "confidence": "single-pair; repeat trials required",
            "authority": "advisory-only"}


def _read_json(path: str) -> dict[str, Any]:
    if Path(path).stat().st_size > 32768:
        raise ValueError("Input larger than 32 KiB")
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="PhiOS GPU Observatory: read-only local observations")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("observe", help="Inspect local NVIDIA GPU status, when available")
    pair = sub.add_parser("compare", help="Compare user-supplied compatible runtime measurements")
    pair.add_argument("before")
    pair.add_argument("after")
    args = parser.parse_args()
    try:
        payload = observe() if args.command == "observe" else compare(
            _read_json(args.before), _read_json(args.after))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, "GPU observation refused: " + str(exc) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
