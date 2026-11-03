"""Deterministic contract tests for advisory-only Elastic Runtime R1."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from phios.elastic_runtime import ElasticContractError, _decode, advise


@pytest.fixture
def sample() -> dict:
    def bubble(name: str, *, state: str = "cold", demanded: bool = False,
               pinned: bool = False, prefetch: bool = False, priority: int = 50,
               deps: list[str] | None = None, ram: int = 100,
               warm: int = 20, vram: int = 10) -> dict:
        return {"id": name, "kind": "service", "observed_state": state,
                "demanded": demanded, "pinned": pinned, "prefetch": prefetch,
                "priority": priority, "dependencies": deps or [],
                "warm_ram_mib": warm, "active_ram_mib": ram,
                "active_vram_mib": vram}

    return {"schema_version": "phios.elastic.snapshot.v1",
            "budget": {"ram_mib": 260, "vram_mib": 30},
            "bubbles": [
                bubble("kernel", state="pinned", pinned=True, ram=80, vram=0),
                bubble("xr", demanded=True, deps=["gpu"], ram=80, vram=10),
                bubble("gpu", ram=70, vram=20),
                bubble("model", prefetch=True, priority=80, warm=25),
                bubble("browser", prefetch=True, priority=40, warm=20),
            ]}


def test_dependency_closure_warm_admission_and_no_authority(sample: dict) -> None:
    result = advise(sample)
    assert result["status"] == "ADVISORY"
    assert result["estimated_mib"] == {"ram": 255, "vram": 30}
    states = {d["id"]: d["suggested_state"] for d in result["decisions"]}
    assert states == {"browser": "cold", "gpu": "active", "kernel": "pinned",
                      "model": "warm", "xr": "active"}
    assert all(result[key] is False for key in
               ("action_authority", "execution_authority", "os_driver_control",
                "inputs_are_measurements"))
    assert len(result["receipt_sha256"]) == 64


def test_mandatory_overrun_held_not_evicted(sample: dict) -> None:
    sample["budget"]["vram_mib"] = 19
    result = advise(sample)
    assert result["status"] == "HELD"
    assert result["mandatory_mib"]["vram"] == 30
    assert all(d["suggested_state"] is None for d in result["decisions"])


def test_order_independent_receipt(sample: dict) -> None:
    first = advise(sample)
    sample["bubbles"].reverse()
    assert advise(sample) == first


@pytest.mark.parametrize("change", [
    lambda x: x.update(unknown="unreviewed"),
    lambda x: x["bubbles"][0].update(action_authority=True),
    lambda x: x["bubbles"][0].update(priority=True),
    lambda x: x["bubbles"][0].update(warm_ram_mib=200),
    lambda x: x["bubbles"][0].update(dependencies=["missing"]),
    lambda x: x["bubbles"][0].update(dependencies=["kernel"]),
    lambda x: x["bubbles"][0].update(observed_state="active"),
    lambda x: x["bubbles"][0].update(id="../escape"),
    lambda x: x["bubbles"][1].update(dependencies=["gpu", "gpu"]),
    lambda x: x["bubbles"][2].update(dependencies=["xr"]),
    lambda x: x["bubbles"].append(copy.deepcopy(x["bubbles"][0])),
    lambda x: x["budget"].update(ram_mib=-1),
    lambda x: x["budget"].update(ram_mib=1.5),
    lambda x: x["budget"].update(ram_mib=True),
])
def test_malformed_snapshots_fail_closed(sample: dict, change) -> None:
    change(sample)
    with pytest.raises(ElasticContractError):
        advise(sample)


@pytest.mark.parametrize("raw", [
    b'{"schema_version":1,"schema_version":2}', b'{"x":NaN}',
    b'{"x":Infinity}', b'\xff', b'{', b'x' * 65537,
])
def test_ambiguous_json_refused(raw: bytes) -> None:
    with pytest.raises(ElasticContractError):
        _decode(raw)


def test_cli_readonly_and_held_exit(tmp_path: Path, sample: dict) -> None:
    source = tmp_path / "sample.json"
    source.write_text(json.dumps(sample))
    before = source.read_bytes()
    command = [sys.executable, "-m", "phios.elastic_runtime", "--snapshot", str(source)]
    first = subprocess.run(command, capture_output=True, text=True, timeout=5)
    assert first.returncode == 0 and first.stderr == ""
    assert json.loads(first.stdout) == advise(sample)
    assert source.read_bytes() == before
    sample["budget"]["ram_mib"] = 1
    source.write_text(json.dumps(sample))
    held = subprocess.run(command, capture_output=True, text=True, timeout=5)
    assert held.returncode == 3 and json.loads(held.stdout)["status"] == "HELD"
    missing = subprocess.run(command[:-1] + [str(tmp_path / "missing")],
                             capture_output=True, text=True, timeout=5)
    assert missing.returncode == 2
    assert json.loads(missing.stdout)["status"] == "UNAVAILABLE"
