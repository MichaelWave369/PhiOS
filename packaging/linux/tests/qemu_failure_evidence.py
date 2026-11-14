"""Bounded failure-only diagnostics for disposable PhiOS QEMU qualification.

The collector does not change QEMU settings, probe the guest, grant permissions,
or decide whether a failed test passes. Raw guest output stays in its existing
separate serial/QEMU evidence logs; no secrets are copied into JSON diagnostics.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def _file_fingerprint(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"present": False}
    try:
        size = path.stat().st_size
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(65536):
                digest.update(chunk)
        return {"present": True, "bytes": size, "sha256": digest.hexdigest()}
    except OSError as exc:
        return {"present": True, "read_error": type(exc).__name__}


def _recent_guest_markers(path: Path) -> dict[str, bool]:
    markers = {
        "uefi_boot_dispatch_seen": False,
        "linux_kernel_seen": False,
        "phios_boot_marker_seen": False,
        "phios_recovery_marker_seen": False,
        "guest_failed_marker_seen": False,
    }
    try:
        if path.is_file():
            with path.open("rb") as stream:
                stream.seek(max(0, path.stat().st_size - 65536))
                data = stream.read(65536)
            markers = {
                "uefi_boot_dispatch_seen": b"BdsDxe:" in data,
                "linux_kernel_seen": b"Linux version" in data,
                "phios_boot_marker_seen": b"PHIOS_BOOT_OK:" in data,
                "phios_recovery_marker_seen": b"PHIOS_OS_RESTORE_OK:" in data,
                "guest_failed_marker_seen": b"PHIOS_BOOT_FAILED" in data,
            }
    except OSError:
        pass
    return markers


def _memory_events() -> dict[str, int]:
    """Record cgroup-v2 event counters, without claiming they identify this VM."""
    result: dict[str, int] = {}
    try:
        for line in Path("/sys/fs/cgroup/memory.events").read_text().splitlines():
            key, value = line.split()
            if key in {"low", "high", "max", "oom", "oom_kill", "oom_group_kill"}:
                result[key] = int(value)
    except (OSError, ValueError):
        return {}
    return result


def _host_memory() -> dict[str, int]:
    """MemAvailable is a coarse host diagnostic, not proof of resource failure."""
    wanted = {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, value = line.partition(":")
            if key in wanted:
                number = value.strip().split()[0]
                values[key + "_kib"] = int(number)
    except (OSError, ValueError, IndexError):
        return {}
    return values


def snapshot(
    *,
    stage: str,
    process: Any,
    serial_log: Path,
    qemu_log: Path,
    failure: BaseException,
    memory_events_before: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Capture a bounded, data-only diagnostic before a failed VM is terminated."""
    exit_code = process.poll()
    current_events = _memory_events()
    previous = memory_events_before or {}
    delta = {
        key: current_events[key] - previous[key]
        for key in current_events.keys() & previous.keys()
    }
    return {
        "schema": "phios.qemu_failure_diagnostic.v0.1",
        "stage": stage,
        "exception_type": type(failure).__name__,
        "qemu_exit_code_before_cleanup": exit_code,
        "qemu_termination_signal_if_negative": -exit_code if exit_code is not None and exit_code < 0 else None,
        "serial_log": _file_fingerprint(serial_log),
        "qemu_log": _file_fingerprint(qemu_log),
        "recent_serial_markers": _recent_guest_markers(serial_log),
        "cgroup_memory_events": current_events,
        "cgroup_memory_events_delta_during_stage": delta,
        "host_memory": _host_memory(),
        "interpretation": (
            "Observational only: an exit code or cgroup OOM counter is not, by itself, "
            "a verified root cause; no failing qualification is promoted."
        ),
        "action_authority": False,
    }


def memory_events_before_start() -> dict[str, int]:
    return _memory_events()
