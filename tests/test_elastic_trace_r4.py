"""R4 trace contract tests: no subprocess, hardware sampler or workload execution."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from phios.elastic_trace import TraceError, _read_trace, convert_trace, measure_call

ROOT = Path(__file__).resolve().parents[1]
TRACE = ROOT / "experiments/elastic/r4_illustrative_trace.json"


@pytest.fixture
def trace() -> dict:
    return json.loads(TRACE.read_text(encoding="utf-8"))


def test_trace_into_r3_with_zero_authority(trace: dict) -> None:
    result = convert_trace(trace)
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["aggregation"] == "nearest_rank_p95"
    assert len(result["trace_sha256"]) == len(result["receipt_sha256"]) == 64
    assert result["paired_comparison"]["pair_count"] == 6
    assert result["paired_comparison"]["summary"]["wins"] == 5
    assert result["paired_comparison"]["summary"]["losses"] == 1
    assert result["paired_comparison"]["order_counts"] == {"AB": 3, "BA": 3}
    assert result["paired_comparison"]["pairs"][0]["baseline"]["samples"] == 100
    assert result["paired_comparison"]["pairs"][0]["baseline"]["value"] > 0
    for key in ("trace_provenance_authenticated", "performance_improvement_proven",
                "action_authority", "execution_authority", "hardware_control"):
        assert result[key] is False


def test_source_order_does_not_modify_comparison(trace: dict) -> None:
    first = convert_trace(trace)
    trace["pairs"].reverse()
    altered = convert_trace(trace)
    assert first["paired_comparison"] == altered["paired_comparison"]
    # R4 binds exact raw data including pair sequence; R3 normalizes pair order.
    assert first["trace_sha256"] != altered["trace_sha256"]


def test_correctness_failure_held(trace: dict) -> None:
    trace["pairs"][0]["candidate"]["passed"] = False
    result = convert_trace(trace)
    assert result["status"] == "HELD"
    assert result["paired_comparison"]["summary"]["candidate_failed"] == 1


def test_median_timing_metric(trace: dict) -> None:
    trace["experiment"]["metric"] = "startup_ms"
    for pair in trace["pairs"]:
        pair["baseline"]["durations_us"] = [1000, 3000, 9000]
        pair["candidate"]["durations_us"] = [1000, 2000, 6000]
    result = convert_trace(trace)
    assert result["aggregation"] == "median_duration"
    assert result["paired_comparison"]["pairs"][0]["baseline"]["value"] == 3.0
    assert result["paired_comparison"]["pairs"][0]["candidate"]["value"] == 2.0
    assert result["paired_comparison"]["summary"]["wins"] == 6


def test_nearest_rank_p95_is_not_mean(trace: dict) -> None:
    trace["pairs"][0]["baseline"]["durations_us"] = [10_000] * 94 + [50_000] * 6
    result = convert_trace(trace)
    assert result["paired_comparison"]["pairs"][0]["baseline"]["value"] == 50.0


@pytest.mark.parametrize("change", [
    lambda x: x.update(authority=True),
    lambda x: x.update(schema_version="unknown"),
    lambda x: x["experiment"].update(metric="tokens_per_second"),
    lambda x: x["experiment"].update(declared_source="independently_verified"),
    lambda x: x["pairs"].pop(),
    lambda x: x["pairs"][0].update(order="BA"),
    lambda x: x["pairs"][0]["baseline"].update(passed="yes"),
    lambda x: x["pairs"][0]["baseline"].update(r2_receipt_sha256="short"),
    lambda x: x["pairs"][0]["baseline"].update(durations_us=[]),
    lambda x: x["pairs"][0]["baseline"].update(durations_us=[1] * 99),
    lambda x: x["pairs"][0]["baseline"].update(durations_us=[0] * 100),
    lambda x: x["pairs"][0]["baseline"].update(durations_us=[True] * 100),
    lambda x: x["pairs"][0]["baseline"].update(durations_us=[float("nan")] * 100),
    lambda x: x["pairs"][0]["baseline"].update(durations_us=[-1] * 100),
    lambda x: x["pairs"][0]["baseline"].update(durations_us=[1] * 2049),
    lambda x: x["pairs"][0]["baseline"].update(unknown=123),
    lambda x: x["pairs"][0].update(pair_id="../path"),
    lambda x: x["pairs"][0].update(pair_id=x["pairs"][1]["pair_id"]),
])
def test_invalid_traces_refuse(trace: dict, change) -> None:
    change(trace)
    with pytest.raises(TraceError):
        convert_trace(trace)


@pytest.mark.parametrize("raw", [
    b'{"x":1,"x":2}', b'{"x":NaN}', b'\xff', b'{', b' ' * (2 * 1024 * 1024 + 1),
])
def test_unsafe_json_refused(tmp_path: Path, raw: bytes) -> None:
    p = tmp_path / "bad.json"
    p.write_bytes(raw)
    with pytest.raises(TraceError):
        _read_trace(p)


def test_symlink_and_nonexistent_refused(tmp_path: Path) -> None:
    f = tmp_path / "trace.json"
    link = tmp_path / "link.json"
    f.write_text("{}", encoding="utf-8")
    link.symlink_to(f)
    with pytest.raises(TraceError):
        _read_trace(link)
    with pytest.raises(TraceError):
        _read_trace(tmp_path / "not-found.json")


def test_callable_execution_is_once_and_synchronous() -> None:
    observed: list[int] = []
    clocks = iter([1_000, 3_501])

    def work() -> str:
        observed.append(1)
        return "complete"

    result, duration_us = measure_call(work, clock_ns=lambda: next(clocks))
    assert result == "complete" and duration_us == 3
    assert observed == [1]


def test_callable_exceptions_propagate_without_fake_success() -> None:
    def broken() -> None:
        raise RuntimeError("incomplete")

    with pytest.raises(RuntimeError, match="incomplete"):
        measure_call(broken, clock_ns=lambda: 1000)


def test_nonadvancing_clock_fails() -> None:
    with pytest.raises(TraceError, match="duration"):
        measure_call(lambda: None, clock_ns=lambda: 1)


def test_cli_round_trip_and_nonzero_refusal(tmp_path: Path, trace: dict) -> None:
    path = tmp_path / "trace.json"
    path.write_text(json.dumps(trace), encoding="utf-8")
    before = path.read_bytes()
    command = [sys.executable, "-m", "phios.elastic_trace", "--trace", str(path)]
    good = subprocess.run(command, text=True, capture_output=True, timeout=5)
    assert good.returncode == 0 and good.stderr == ""
    assert json.loads(good.stdout) == convert_trace(trace)
    assert path.read_bytes() == before
    assert str(path) not in good.stdout
    trace["pairs"][0]["candidate"]["passed"] = False
    path.write_text(json.dumps(trace), encoding="utf-8")
    held = subprocess.run(command, text=True, capture_output=True, timeout=5)
    assert held.returncode == 3
    trace["pairs"][0]["baseline"]["durations_us"] = []
    path.write_text(json.dumps(trace), encoding="utf-8")
    invalid = subprocess.run(command, text=True, capture_output=True, timeout=5)
    assert invalid.returncode == 2
    assert json.loads(invalid.stdout)["status"] == "UNAVAILABLE"
