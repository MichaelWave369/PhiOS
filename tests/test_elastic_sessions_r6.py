"""R6 audit tests on disposable, explicitly created R5 receipts only."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from phios import elastic_residency_r5 as r5
from phios.elastic_sessions_r6 import (
    MAX_RECEIPT_BYTES, SessionAuditError, _read_receipt, review_sessions,
)
from phios.elastic_trace import convert_trace


@pytest.fixture
def receipts(tmp_path: Path) -> list[dict]:
    source = tmp_path / "test-only.bin"
    source.write_bytes(bytes(range(256)) * 1024)
    observed = r5.benchmark(source)
    source.unlink()
    # Test-owned synthetic variations. These do not represent independent host
    # sessions and are never used as evidence for a performance speedup.
    result = []
    for variant in range(3):
        item = copy.deepcopy(observed)
        for pair in item["trace"]["pairs"]:
            pair["baseline"]["durations_us"] = [10000 + variant * 100]
            pair["candidate"]["durations_us"] = [9000 + variant * 100]
        _reseal(item)
        result.append(item)
    return result


def _reseal(report: dict) -> None:
    report["comparison"] = convert_trace(report["trace"])
    report["status"] = report["comparison"]["status"]
    report["receipt_sha256"] = r5._hash_json({
        key: value for key, value in report.items() if key != "receipt_sha256"
    })


def test_three_sessions_are_review_required_not_a_speedup_claim(receipts: list[dict]) -> None:
    result = review_sessions(receipts)
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["session_count"] == 3
    assert result["summary"]["positive_sessions"] == 3
    assert result["summary"]["direction"] == "all_positive"
    assert result["summary"]["median_of_session_median_improvements_percent"] > 0
    assert len(result["receipt_sha256"]) == 64
    assert all(result[key] is False for key in (
        "independent_sessions_verified", "host_provenance_authenticated",
        "cold_cache_measured", "performance_improvement_proven",
        "action_authority", "execution_authority", "hardware_control",
    ))


def test_input_order_does_not_change_output(receipts: list[dict]) -> None:
    assert review_sessions(receipts) == review_sessions(list(reversed(receipts)))


def test_mixed_directions_reported_without_promotion(receipts: list[dict]) -> None:
    for pair in receipts[2]["trace"]["pairs"]:
        pair["candidate"]["durations_us"] = [13000]
    _reseal(receipts[2])
    report = review_sessions(receipts)
    assert report["summary"]["positive_sessions"] == 2
    assert report["summary"]["negative_sessions"] == 1
    assert report["summary"]["direction"] == "mixed"
    assert report["performance_improvement_proven"] is False


@pytest.mark.parametrize("field, value", [
    ("status", "HELD"),
    ("scope", "cold_cache_claimed"),
    ("improvement_proven", True),
    ("action_authority", True),
    ("hardware_control", True),
    ("source_filename_recorded", True),
    ("window_bytes", 0),
    ("baseline_whole_file_bytes_per_run", True),
])
def test_invalid_claims_fail_closed(receipts: list[dict], field: str, value: object) -> None:
    receipts[0][field] = value
    _reseal(receipts[0])
    with pytest.raises(SessionAuditError):
        review_sessions(receipts)


@pytest.mark.parametrize("kind", [
    "report-tamper", "nested-tamper", "workload", "environment", "file-size",
    "window-count", "invalid-metric", "failed-correctness", "unknown",
])
def test_mismatch_or_tampering_refused(receipts: list[dict], kind: str) -> None:
    item = receipts[1]
    if kind == "report-tamper":
        item["file_bytes"] += 1
    elif kind == "nested-tamper":
        item["comparison"]["paired_comparison"]["summary"]["wins"] = 999
    elif kind == "workload":
        item["trace"]["experiment"]["workload_sha256"] = "a" * 64
        _reseal(item)
    elif kind == "environment":
        item["trace"]["experiment"]["environment_id"] = "other-host"
        _reseal(item)
    elif kind == "file-size":
        item["file_bytes"] += 4096
        item["baseline_whole_file_bytes_per_run"] += 4096
        _reseal(item)
    elif kind == "window-count":
        item["windows"] += 1
        item["per_arm_selected_bytes"] += item["window_bytes"]
        item["candidate_selected_bytes_per_run"] += item["window_bytes"]
        _reseal(item)
    elif kind == "invalid-metric":
        item["trace"]["experiment"]["metric"] = "tokens_per_second"
        _reseal(item) if False else None
        item["receipt_sha256"] = r5._hash_json({
            key: value for key, value in item.items() if key != "receipt_sha256"
        })
    elif kind == "failed-correctness":
        item["trace"]["pairs"][0]["candidate"]["passed"] = False
        _reseal(item)
    else:
        item["unknown"] = "unsupported"
        _reseal(item)
    with pytest.raises(SessionAuditError):
        review_sessions(receipts)


def test_duplicate_receipts_or_wrong_count_refused(receipts: list[dict]) -> None:
    with pytest.raises(SessionAuditError, match="duplicate"):
        review_sessions([receipts[0], receipts[0], receipts[2]])
    with pytest.raises(SessionAuditError):
        review_sessions(receipts[:2])
    with pytest.raises(SessionAuditError):
        review_sessions(receipts * 5)


@pytest.mark.parametrize("wire", [
    b'{"status":"first","status":"second"}', b'{"value":NaN}', b'\xff', b'{',
    b' ' * (MAX_RECEIPT_BYTES + 1),
])
def test_invalid_receipt_files_refused(tmp_path: Path, wire: bytes) -> None:
    path = tmp_path / "bad.json"
    path.write_bytes(wire)
    with pytest.raises(SessionAuditError):
        _read_receipt(path)


def test_symlinks_and_missing_files_refused(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    alias = tmp_path / "alias.json"
    try:
        alias.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unsupported")
    with pytest.raises(SessionAuditError):
        _read_receipt(alias)
    with pytest.raises(SessionAuditError):
        _read_receipt(tmp_path / "absent.json")


def test_cli_reads_explicit_local_receipts_and_never_reports_paths(
    tmp_path: Path, receipts: list[dict],
) -> None:
    paths = []
    for index, item in enumerate(receipts):
        path = tmp_path / f"local-session-{index}.json"
        path.write_text(json.dumps(item), encoding="utf-8")
        paths.append(path)
    before = [path.read_bytes() for path in paths]
    command = [sys.executable, "-m", "phios.elastic_sessions_r6"]
    for path in paths:
        command.extend(["--receipt", str(path)])
    result = subprocess.run(command, text=True, capture_output=True, timeout=10)
    assert result.returncode == 0 and result.stderr == ""
    assert json.loads(result.stdout) == review_sessions(receipts)
    assert [path.read_bytes() for path in paths] == before
    assert str(tmp_path) not in result.stdout
    # A single receipt is not independent replication.
    bad = subprocess.run(command[:4], text=True, capture_output=True, timeout=10)
    assert bad.returncode == 2
    assert json.loads(bad.stdout)["status"] == "UNAVAILABLE"
