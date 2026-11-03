"""Hermetic tests: no live host probes, nvidia commands, or user file modification."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from phios.elastic_observation import (
    ObservationError, _read_json, _sample_gpu, collect, verify_receipt,
)


@pytest.fixture
def probes():
    counts = {"cpu": 0, "mem": 0, "clock": 0, "gpu": 0}

    def cpu(interval: float) -> float:
        assert interval == .1
        counts["cpu"] += 1
        return 12.5 + counts["cpu"]

    def memory():
        counts["mem"] += 1
        return SimpleNamespace(total=4096 * 1048576, available=2048 * 1048576)

    def clock() -> int:
        counts["clock"] += 1
        return counts["clock"] * 100_000_000

    def gpu():
        counts["gpu"] += 1
        return {"memory_used_mib": 800 + counts["gpu"],
                "memory_total_mib": 12288, "utilization_percent": 25}

    return {"cpu_probe": cpu, "memory_probe": memory, "gpu_probe": gpu,
            "clock_ns": clock,
            "utc_now": lambda: datetime(2026, 11, 3, tzinfo=timezone.utc)}, counts


def test_capture_is_explicit_bounded_and_deterministic(probes):
    handles, counts = probes
    report = collect(scenario="btm-vr", samples=3, interval_ms=100,
                     include_gpu=True, **handles)
    assert report["status"] == "OBSERVED"
    assert counts == {"cpu": 3, "mem": 3, "clock": 4, "gpu": 3}
    assert report["summary"]["cpu_percent"] == {"p50": 14.5, "p95": 15.5, "p99": 15.5}
    assert report["summary"]["ram_pressure_mib"]["p99"] == 2048
    assert report["summary"]["gpu"]["memory_used_mib"]["p99"] == 803
    assert report["samples"][0]["elapsed_ms"] == 100
    assert report["measurements"]["ram"] == "psutil_total_minus_available_approximation"
    assert all(report[key] is False for key in (
        "action_authority", "execution_authority", "hardware_control",
        "performance_improvement_proven",
    ))
    assert verify_receipt(report) == report
    changed = copy.deepcopy(report)
    changed["samples"][0]["cpu_percent"] = 1
    with pytest.raises(ObservationError, match="integrity"):
        verify_receipt(changed)


def test_cpu_ram_only_never_invokes_nvidia(probes):
    handles, counts = probes
    result = collect(scenario="idle", samples=1, interval_ms=100,
                     include_gpu=False, **handles)
    assert result["status"] == "OBSERVED"
    assert counts["gpu"] == 0
    assert result["summary"]["gpu"] is None
    assert "gpu" not in result["samples"][0]


def test_gpu_unavailable_is_partial_not_zero(probes):
    handles, _ = probes
    handles["gpu_probe"] = lambda: None
    result = collect(scenario="idle", samples=2, interval_ms=100,
                     include_gpu=True, **handles)
    assert result["status"] == "PARTIAL"
    assert result["summary"]["gpu"] is None
    assert result["summary"]["gpu_samples_unavailable"] == 2
    assert all(row["gpu"] is None for row in result["samples"])


@pytest.mark.parametrize("bad", ["", "INVALID", "../home", "has space", "a" * 70])
def test_invalid_scenario_rejected_before_sampling(bad, probes):
    handles, counts = probes
    with pytest.raises(ObservationError):
        collect(scenario=bad, samples=1, interval_ms=100, **handles)
    assert counts["cpu"] == 0


@pytest.mark.parametrize("quantity, interval", [(0, 100), (121, 100), (True, 100),
                                                 (1, 99), (1, 10001), (1, True)])
def test_invalid_limits_fail_before_sampling(quantity, interval, probes):
    handles, counts = probes
    with pytest.raises(ObservationError):
        collect(scenario="idle", samples=quantity, interval_ms=interval, **handles)
    assert counts["cpu"] == 0


@pytest.mark.parametrize("cpu_percent, available", [(float("nan"), 0),
                                                      (101, 0), (5, -1),
                                                      (5, 50000000000), (True, 0)])
def test_invalid_counters_not_exported(cpu_percent, available, probes):
    handles, _ = probes
    handles["cpu_probe"] = lambda _: cpu_percent
    handles["memory_probe"] = lambda: SimpleNamespace(total=4096 * 1048576,
                                                        available=available)
    with pytest.raises(ObservationError):
        collect(scenario="idle", samples=1, interval_ms=100, **handles)


def test_unavailable_cpu_probe_is_not_interpreted_as_idle(probes):
    handles, _ = probes

    def broken(_):
        raise OSError("no counters")

    handles["cpu_probe"] = broken
    with pytest.raises(ObservationError, match="mandatory"):
        collect(scenario="idle", samples=1, interval_ms=100, **handles)


@pytest.mark.parametrize("value", [
    {"memory_used_mib": 13000, "memory_total_mib": 12000, "utilization_percent": 40},
    {"memory_used_mib": True, "memory_total_mib": 12000, "utilization_percent": 40},
    {"memory_used_mib": 800, "memory_total_mib": 12000, "utilization_percent": 101},
    {"wrong": 800},
])
def test_invalid_gpu_observations_rejected(value, probes):
    handles, _ = probes
    handles["gpu_probe"] = lambda: value
    with pytest.raises(ObservationError):
        collect(scenario="idle", samples=1, interval_ms=100, include_gpu=True, **handles)


@pytest.mark.parametrize("text, expected", [
    ("1024, 12288, 30\n", True), ("1024 MiB, 12288 MiB, 30 %", False),
    ("1024, 12288, 30\n500, 12288, 12\n", False),
    ("13000, 12288, 30", False), ("10, 12288, 101", False),
])
def test_nvidia_parser_refuses_ambiguous_output(monkeypatch, text, expected):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=text)

    monkeypatch.setattr(subprocess, "run", fake_run)
    reading = _sample_gpu()
    assert (reading is not None) == expected
    assert calls[0][0][0] == "nvidia-smi"
    assert calls[0][1]["timeout"] == 3
    assert "shell" not in calls[0][1]


def test_export_verification_and_no_path_leak(tmp_path: Path, probes):
    handles, _ = probes
    result = collect(scenario="idle", samples=1, interval_ms=100, **handles)
    path = tmp_path / "reading.json"
    path.write_text(json.dumps(result))
    before = path.read_bytes()
    cli = [sys.executable, "-m", "phios.elastic_observation", "verify", "--input", str(path)]
    verification = subprocess.run(cli, capture_output=True, text=True, timeout=5)
    assert verification.returncode == 0
    assert json.loads(verification.stdout) == result
    assert path.read_bytes() == before
    assert str(tmp_path) not in verification.stdout
    path.write_text('{"status": "OBSERVED", "status": "PARTIAL"}')
    with pytest.raises(ObservationError):
        _read_json(path)
    path.unlink()
    path.symlink_to(tmp_path / "somewhere")
    with pytest.raises(ObservationError):
        _read_json(path)


def test_receipt_authority_never_promoted(probes):
    handles, _ = probes
    result = collect(scenario="idle", samples=1, interval_ms=100, **handles)
    for key in ("action_authority", "execution_authority", "hardware_control",
                "performance_improvement_proven"):
        altered = copy.deepcopy(result)
        altered[key] = True
        with pytest.raises(ObservationError):
            verify_receipt(altered)
