#!/usr/bin/env python3
"""PhiVine Rung 10 actual output -> PhiOS Rung 11 held JSON review."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

SOURCE_SHA = "7c9791c6be75e5f069d513db788627e81405d6d1"


def cli(module: str, args: list[str], src: Path, cwd: Path, code: int) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(src.resolve())
    outcome = subprocess.run(
        [sys.executable, "-m", module, *args], cwd=cwd, env=env,
        capture_output=True, text=True, check=False, timeout=30,
    )
    if outcome.returncode != code:
        raise AssertionError(f"{module} exit {outcome.returncode} not {code}: {outcome.stderr[-600:]}")
    return json.loads(outcome.stdout)


def create_fixture(path: Path) -> None:
    """Non-executable PE32+ bytes with D3D11 and WS2_32 import names."""
    import struct
    p = bytearray(0x400)
    p[:2] = b"MZ"
    struct.pack_into("<I", p, 0x3C, 0x80)
    p[0x80:0x84] = b"PE\x00\x00"
    struct.pack_into("<H", p, 0x84, 0x8664)
    struct.pack_into("<H", p, 0x86, 1)
    struct.pack_into("<H", p, 0x94, 0xF0)
    struct.pack_into("<H", p, 0x98, 0x20B)
    struct.pack_into("<I", p, 0x98 + 108, 16)
    struct.pack_into("<II", p, 0x98 + 112 + 8, 0x1000, 60)
    section = 0x98 + 0xF0
    p[section:section + 6] = b".idata"
    struct.pack_into("<IIII", p, section + 8, 0x200, 0x1000, 0x200, 0x200)
    for i, dll in enumerate((b"D3D11.dll", b"WS2_32.dll")):
        struct.pack_into("<I", p, 0x200 + i * 20 + 12, 0x1060 + i * 0x40)
        p[0x260 + i * 0x40:0x260 + i * 0x40 + len(dll) + 1] = dll + b"\x00"
    path.write_bytes(p)


def check_held(review: dict, *, expected_status: str) -> None:
    assert review["schema"] == "phios.phivine_import_triage_review.v0.1"
    assert review["status"] == expected_status
    for name in (
        "source_immutability_verified", "binary_file_read_by_phios",
        "source_repo_profiler_called", "wine_compatibility_verified",
        "network_granted", "app_registry_read_or_modified",
        "phios_install_or_launch_called", "operator_approval_minted",
        "effect_lease_issued", "execution_authorized", "windows_binary_executed",
    ):
        assert review[name] is False, name


def run(producer: Path, receipt: Path) -> None:
    sha = subprocess.check_output(
        ["git", "-C", str(producer), "rev-parse", "HEAD"], text=True, timeout=10
    ).strip()
    if sha != SOURCE_SHA:
        raise AssertionError("PhiVine static triage source differs from reviewed pin")
    phi_os = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="phivine-triage-peer-") as dirname:
        temp = Path(dirname)
        file = temp / "synthetic.exe"
        create_fixture(file)
        evidence = cli(
            "phivine", ["triage-imports", str(file)], producer / "src", temp, 3
        )
        assert evidence["schema"] == "phivine.import_triage.v0.1"
        assert evidence["status"] == "HELD_STATIC_IMPORT_TRIAGE_REVIEW_ONLY"
        assert evidence["source_sha256_observed"] == hashlib.sha256(file.read_bytes()).hexdigest()
        assert evidence["direct_import_dll_count"] == 2

        sample = temp / "triage.json"
        sample.write_text(json.dumps(evidence), encoding="utf-8")
        accepted = cli(
            "phios.apps.cli", ["review-phivine-triage", str(sample)], phi_os, temp, 3
        )
        check_held(accepted, expected_status="HELD_STATIC_DLL_REVIEW_UNTRUSTED")
        assert [x["area"] for x in accepted["review_groups"]] == [
            "graphics_apis", "network_apis",
        ]
        assert accepted["artifact_name_observed"] == "synthetic.exe"

        # An attacker can edit name-only JSON. Neither a claimed permission
        # nor a fabricated category can become validated PhiOS authority.
        forged = json.loads(json.dumps(evidence))
        forged["execution_authorized"] = True
        sample.write_text(json.dumps(forged), encoding="utf-8")
        refused = cli(
            "phios.apps.cli", ["review-phivine-triage", str(sample)], phi_os, temp, 3
        )
        check_held(refused, expected_status="HELD_INVALID_OR_UNTRUSTED_STATIC_TRIAGE")
        assert refused["artifact_name_observed"] is None

        mislabel = json.loads(json.dumps(evidence))
        mislabel["review_areas"][0]["area"] = "network_apis"
        sample.write_text(json.dumps(mislabel), encoding="utf-8")
        bad_category = cli(
            "phios.apps.cli", ["review-phivine-triage", str(sample)], phi_os, temp, 3
        )
        check_held(bad_category, expected_status="HELD_INVALID_OR_UNTRUSTED_STATIC_TRIAGE")
        assert not bad_category["review_groups"]

    record = {
        "schema": "phios.phivine_triage_peer_smoke.v0.1",
        "producer_sha": sha,
        "producer_held_exit": 3,
        "consumer_held_exit": 3,
        "valid_review_status": accepted["status"],
        "forged_authority_status": refused["status"],
        "fabricated_category_status": bad_category["status"],
        "synthetic_executable_run": False,
        "wine_launched": False,
        "app_registered": False,
        "permission_granted": False,
        "compatibility_verified": False,
        "production_qualified": False,
    }
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("PHIVINE_STATIC_TRIAGE_REAL_PEER_HELD_PASS")
    print(json.dumps(record, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--producer", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    run(args.producer.resolve(strict=True), args.receipt)


if __name__ == "__main__":
    main()
