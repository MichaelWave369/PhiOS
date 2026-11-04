"""Deterministic offline tests for a deliberately synthetic advisory comparator."""
import json
import math
import subprocess
import sys

import pytest

from phios.optical_path_r1 import (
    ILLUSTRATIVE_COPPER, LinkAssumptions,
    compare_paths, estimate_transfer,
)


def test_fixed_serialization_and_accounting():
    spec = LinkAssumptions("simple", 8.0, 2.0, 1.0, 1.0, 0.0, 0.0)
    row = estimate_transfer(1000, spec)
    assert row["serialization_us"] == pytest.approx(1.0)
    assert row["latency_us"] == pytest.approx(4.0)
    assert row["energy_uj"] == pytest.approx(4.0)


def test_small_packet_conversion_overhead_is_visible():
    report = compare_paths([64])
    result = report["cases"][0]
    assert result["latency_winner_synthetic"] == "electrical"
    assert result["energy_winner_synthetic"] == "electrical"
    assert report["authority"] == "advisory_only"
    assert report["hardware_access"] is False


def test_large_transfer_can_change_synthetic_latency_winner():
    result = compare_paths([1_048_576])["cases"][0]
    assert result["latency_winner_synthetic"] == "optical"
    assert result["optical"]["serialization_us"] < result["electrical"]["serialization_us"]


def test_determinism_and_no_fabricated_measurement():
    a = compare_paths([64, 4096, 1_048_576])
    assert a == compare_paths([64, 4096, 1_048_576])
    assert a["evidence_class"] == "illustrative_synthetic_unmeasured"
    assert a["automatic_routing"] is False


@pytest.mark.parametrize("value", [0, -1, 1_000_000_001, True, 2.5])
def test_payload_bounds(value):
    with pytest.raises(ValueError):
        estimate_transfer(value, ILLUSTRATIVE_COPPER)


def test_refuse_nonfinite_hardware_assumptions():
    invalid = LinkAssumptions("bad", math.nan, 0, 0, 1, 10, 0)
    with pytest.raises(ValueError):
        compare_paths([64], optical=invalid)
    invalid = LinkAssumptions("bad", 10, 0, -1, 1, 10, 0)
    with pytest.raises(ValueError):
        estimate_transfer(64, invalid)


def test_cli_produces_marked_synthetic_json_without_external_io():
    result = subprocess.run(
        [sys.executable, "-m", "phios.optical_path_r1", "--sizes", "64,4096"],
        capture_output=True, text=True, check=True, timeout=15,
    )
    report = json.loads(result.stdout)
    assert [case["payload_bytes"] for case in report["cases"]] == [64, 4096]
    assert report["evidence_class"] == "illustrative_synthetic_unmeasured"
