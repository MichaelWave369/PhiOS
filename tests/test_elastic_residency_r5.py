"""R5 real local I/O experiments use disposable test-owned files only."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from phios import elastic_residency_r5 as r5


@pytest.fixture
def source(tmp_path: Path) -> Path:
    target = tmp_path / "unidentifiable-disposable.bin"
    target.write_bytes(bytes(range(256)) * 1024)
    return target


def test_eager_and_mmap_read_identical_selected_content(source: Path) -> None:
    with r5._open_readonly(source) as handle:
        offsets = (0, 4096, 8192, 200000)
        baseline = r5._sparse_digest(
            handle, size=source.stat().st_size, positions=offsets,
            window_bytes=4096, mapped=False)
        candidate = r5._sparse_digest(
            handle, size=source.stat().st_size, positions=offsets,
            window_bytes=4096, mapped=True)
        reference = r5.expected_digest(handle, offsets, 4096)
        assert baseline == candidate == reference
        assert len(reference) == 64


def test_real_local_measurements_feed_r4_and_r3(source: Path) -> None:
    before = source.read_bytes()
    report = r5.benchmark(source)
    assert report["status"] == "REVIEW_REQUIRED"
    assert report["scope"] == "operator_local_unverified_warm_cache"
    assert report["file_bytes"] == len(before)
    assert report["baseline_whole_file_bytes_per_run"] == len(before)
    assert report["candidate_selected_bytes_per_run"] == 65536
    assert report["source_filename_recorded"] is False
    assert report["improvement_proven"] is False
    assert report["comparison"]["paired_comparison"]["pair_count"] == 6
    assert report["comparison"]["status"] == "REVIEW_REQUIRED"
    assert report["comparison"]["aggregation"] == "median_duration"
    assert report["comparison"]["paired_comparison"]["order_counts"] == {"AB": 3, "BA": 3}
    assert [row["order"] for row in report["trace"]["pairs"]] == [
        "AB", "BA", "AB", "BA", "AB", "BA"]
    assert all(report[key] is False for key in (
        "action_authority", "execution_authority", "hardware_control",
    ))
    assert source.read_bytes() == before
    assert len(report["receipt_sha256"]) == 64
    for pair in report["trace"]["pairs"]:
        assert pair["baseline"]["passed"] is True
        assert pair["candidate"]["passed"] is True
        assert pair["baseline"]["durations_us"][0] > 0
        assert pair["candidate"]["durations_us"][0] > 0


@pytest.mark.parametrize("parameter", [
    {"pairs": 5}, {"pairs": 17}, {"pairs": True}, {"pairs": 6.5},
    {"windows": 1}, {"windows": 65}, {"windows": False},
    {"window_bytes": 0}, {"window_bytes": 65537}, {"window_bytes": True},
    {"environment_id": "../secrets"}, {"environment_id": ""},
])
def test_invalid_parameters_refuse_before_reading(source: Path, parameter: dict) -> None:
    with pytest.raises(r5.ResidencyError):
        r5.benchmark(source, **parameter)


def test_small_file_refusal(tmp_path: Path) -> None:
    small = tmp_path / "small.bin"
    small.write_bytes(b"x" * 1024)
    with pytest.raises(r5.ResidencyError, match="too small"):
        r5.benchmark(small)


def test_large_file_refusal_without_allocating_64mb(tmp_path: Path) -> None:
    huge = tmp_path / "too-large.bin"
    with huge.open("wb") as stream:
        stream.truncate(r5.MAX_FILE_BYTES + 1)
    with pytest.raises(r5.ResidencyError, match="64 MiB"):
        r5.benchmark(huge)


def test_nonexistent_directory_and_symlink_refused(source: Path, tmp_path: Path) -> None:
    with pytest.raises(r5.ResidencyError):
        r5.benchmark(tmp_path / "not-here")
    with pytest.raises(r5.ResidencyError):
        r5.benchmark(tmp_path)
    link = tmp_path / "alias.bin"
    try:
        link.symlink_to(source)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(r5.ResidencyError, match="symlink"):
        r5.benchmark(link)


def test_modified_file_is_not_silently_accepted(source: Path, monkeypatch) -> None:
    real_measure = r5.measure_call
    calls = 0

    def measure_and_change(action):
        nonlocal calls
        result = real_measure(action)
        calls += 1
        if calls == 2:
            # A test-owned mutation after the first pair simulates hostile drift.
            with source.open("r+b") as stream:
                stream.seek(3)
                stream.write(b"\x00")
        return result

    monkeypatch.setattr(r5, "measure_call", measure_and_change)
    with pytest.raises(r5.ResidencyError):
        r5.benchmark(source)


def test_mismatched_candidate_content_refused(source: Path, monkeypatch) -> None:
    real = r5._sparse_digest

    def mismatched(handle, *, size, positions, window_bytes, mapped):
        result = real(handle, size=size, positions=positions,
                      window_bytes=window_bytes, mapped=mapped)
        return "f" * 64 if mapped else result

    monkeypatch.setattr(r5, "_sparse_digest", mismatched)
    with pytest.raises(r5.ResidencyError, match="mismatch"):
        r5.benchmark(source)


def test_cli_stdout_receipt_and_no_filename_leak(source: Path) -> None:
    raw = source.read_bytes()
    command = [sys.executable, "-m", "phios.elastic_residency_r5",
               "--file", str(source), "--pairs", "6"]
    result = subprocess.run(command, text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "REVIEW_REQUIRED"
    assert receipt["source_filename_recorded"] is False
    assert str(source) not in result.stdout
    assert source.read_bytes() == raw


def test_cli_unavailable_is_safe(source: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "phios.elastic_residency_r5",
         "--file", str(source), "--pairs", "0"],
        text=True, capture_output=True, timeout=10)
    assert result.returncode == 2
    receipt = json.loads(result.stdout)
    assert receipt == {"schema_version": r5.SCHEMA, "status": "UNAVAILABLE",
                       "action_authority": False, "execution_authority": False}
    assert str(source) not in result.stdout


def test_file_digest_uses_actual_bytes(source: Path) -> None:
    with r5._open_readonly(source) as handle:
        assert r5._digest_file(handle) == hashlib.sha256(source.read_bytes()).hexdigest()
