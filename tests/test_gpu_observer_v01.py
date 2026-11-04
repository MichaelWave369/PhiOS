"""No GPU required: deterministic tests of the observational boundary."""
import subprocess

import pytest

from phios.gpu_observer import compare, observe, parse_nvidia_smi, recommendations


SAMPLE = "RTX 3060, 12288, 12000, 95, 70, 62, 110.5, 170, 575.21\n"


def fake_success(argv, **kwargs):
    assert argv[0] == "nvidia-smi"
    assert kwargs["timeout"] == 4
    assert kwargs["check"] is False
    return subprocess.CompletedProcess(argv, 0, SAMPLE, "")


def test_observation_is_read_only_and_explicit():
    result = observe(runner=fake_success)
    assert result["status"] == "observed"
    assert result["authority"] == "observe-only"
    assert result["devices"][0]["vram_fraction"] > 0.9
    assert result["devices"][0]["advisory_hints"]


def test_no_gpu_is_not_a_fake_zero():
    result = observe(runner=lambda *_a, **_k: (_ for _ in ()).throw(FileNotFoundError()))
    assert result["status"] == "unavailable"
    assert result["devices"] == []


def test_unknown_measurements_stay_null():
    device = parse_nvidia_smi("RTX 3060, N/A, N/A, N/A, N/A, N/A, N/A, N/A, 580\n")[0]
    assert device["vram_fraction"] is None
    assert device["temperature_c"] is None
    assert "cannot distinguish" in recommendations(device)[0]


def test_malformed_and_oversize_fail_closed():
    with pytest.raises(ValueError):
        parse_nvidia_smi("broken")
    with pytest.raises(ValueError):
        parse_nvidia_smi("x" * 32769)


def run(duration):
    return dict(schema="phios.gpu-run.v1", workload="sdxl", gpu="RTX 3060",
                precision="fp16", batch=1, resolution="1024x1024",
                execution_mode="local", duration_ms=duration)


def test_comparison_requires_same_workload_and_valid_durations():
    result = compare(run(2000), run(1000))
    assert result["speedup_ratio"] == 2
    assert result["samples_per_condition"] == 1
    bad = run(1000)
    bad["precision"] = "int8"
    with pytest.raises(ValueError):
        compare(run(2000), bad)
    with pytest.raises(ValueError):
        compare(run(2000), run(float("nan")))
