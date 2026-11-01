#!/usr/bin/env python3
"""Real PhiVine -> PhiOS CLI contract, strictly non-authorizing.

Exercises only synthetic PE bytes and versioned JSON. Never starts Wine,
Windows programs, installers, a runtime broker or an App Platform grant.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

PHIVINE_PIN = "31d5056fb2b24fdf8cbe9e84bc408039f1de355f"
FALSE_FLAGS = (
    "app_registry_read_or_modified",
    "phios_install_or_launch_called",
    "operator_approval_minted",
    "effect_lease_issued",
    "execution_authorized",
    "windows_binary_executed",
)


def invoke(args: list[str], env: dict[str, str], cwd: Path, exit_code: int) -> dict:
    command = subprocess.run(
        [sys.executable, *args],
        env=env, cwd=cwd, capture_output=True, text=True,
        timeout=30, check=False,
    )
    if command.returncode != exit_code:
        raise AssertionError(
            f"Expected held/plan exit {exit_code}, got {command.returncode} "
            f"from {' '.join(args[:3])}. stderr excerpt: {command.stderr[-500:]}"
        )
    result = json.loads(command.stdout)
    if not isinstance(result, dict):
        raise AssertionError("CLI must emit a JSON object")
    return result


def synthetic_pe() -> bytes:
    # Deliberately nonfunctional header-only 256-byte test fixture.
    data = bytearray(256)
    data[:2] = b"MZ"
    data[0x3C:0x40] = (128).to_bytes(4, "little")
    data[128:132] = b"PE\x00\x00"
    data[132:134] = (0x8664).to_bytes(2, "little")
    return bytes(data)


def record_sha(record: dict) -> str:
    canonical = json.dumps(
        {k: v for k, v in record.items() if k != "handoff_id"},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
    )
    return "pha-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def assert_held(value: dict, *, status: str, artifact_allowed: bool) -> None:
    if value.get("schema") != "phios.phivine_advisory_review.v0.1":
        raise AssertionError("Unexpected PhiOS review schema")
    if value.get("status") != status:
        raise AssertionError(f"Expected HELD status {status}, got {value.get('status')}")
    if value.get("input_kind") != "untrusted_local_windows_binary_advisory":
        raise AssertionError("Unexpected input kind")
    for flag in FALSE_FLAGS:
        if value.get(flag) is not False:
            raise AssertionError(f"PhiOS cannot grant authority: {flag}")
    if artifact_allowed:
        if value.get("artifact", {}).get("name") != "synthetic.exe":
            raise AssertionError("Candidate display data not preserved")
    elif value.get("artifact") is not None:
        raise AssertionError("Untrusted or forged artifact was displayed")
    if len(value.get("unmet_execution_gates", [])) != 9:
        raise AssertionError("Unmet execution gates must never disappear")


def run(producer: Path, receipt: Path) -> None:
    source_sha = subprocess.check_output(
        ["git", "-C", str(producer), "rev-parse", "HEAD"], text=True, timeout=10
    ).strip()
    if source_sha != PHIVINE_PIN:
        raise AssertionError("PhiVine source drift: require immutable producer pin")
    env = os.environ.copy()
    env["PYTHONPATH"] = str((producer / "src").resolve())
    repo = Path(__file__).resolve().parents[1]
    consumer_env = os.environ.copy()
    consumer_env["PYTHONPATH"] = str(repo)

    with tempfile.TemporaryDirectory(prefix="phivine-phios-contract-") as name:
        root = Path(name)
        artifact = root / "synthetic.exe"
        artifact.write_bytes(synthetic_pe())

        plan = invoke(["-m", "phivine", "plan", str(artifact)], env, root, 0)
        if plan.get("schema") != "phivine.launch_plan.v0.1":
            raise AssertionError("Unexpected PhiVine plan")
        if plan.get("decision", {}).get("execution_authorized") is not False:
            raise AssertionError("PhiVine plan incorrectly grants execution")
        proposal = root / "plan.json"
        proposal.write_text(json.dumps(plan), encoding="utf-8")

        handoff = invoke(
            ["-m", "phivine", "phios-handoff", str(proposal)], env, root, 3
        )
        if handoff.get("schema") != "phivine.phios_advisory.v0.1":
            raise AssertionError("PhiVine handoff schema drift")
        if handoff.get("status") != "HELD_PHIOS_BINARY_INTAKE_NOT_IMPLEMENTED":
            raise AssertionError("PhiVine no longer holds native intake")
        if handoff.get("handoff_id") != record_sha(handoff):
            raise AssertionError("PhiVine handoff checksum drift")
        if handoff.get("artifact", {}).get("name") != "synthetic.exe":
            raise AssertionError("Path-redacted artifact identity missing")
        if handoff.get("observations", {}).get("source_bytes_match_observed") is not True:
            raise AssertionError("Synthetic source observation unexpectedly failed")
        if any(value is not False for value in handoff.get("authority", {}).values()):
            raise AssertionError("Producer emitted an approval value")
        if len(handoff.get("required_before_execution", [])) != 9:
            raise AssertionError("Producer dropped a required authority gate")

        handoff_path = root / "handoff.json"
        handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
        consumer = invoke(
            ["-m", "phios.apps.cli", "review-phivine", str(handoff_path)],
            consumer_env, repo, 3,
        )
        assert_held(
            consumer,
            status="HELD_NATIVE_WINDOWS_BINARY_INTAKE_UNAVAILABLE",
            artifact_allowed=True,
        )

        # A forged approval remains untrusted, EVEN IF an attacker computes
        # the unkeyed SHA-based identifier again.
        forged = json.loads(json.dumps(handoff))
        forged["authority"]["execution_authorized"] = True
        forged["handoff_id"] = record_sha(forged)
        handoff_path.write_text(json.dumps(forged), encoding="utf-8")
        blocked = invoke(
            ["-m", "phios.apps.cli", "review-phivine", str(handoff_path)],
            consumer_env, repo, 3,
        )
        assert_held(
            blocked,
            status="HELD_INVALID_OR_UNTRUSTED_PHIVINE_ADVISORY",
            artifact_allowed=False,
        )

        # A changed input digest with stale checksum also fails closed.
        tampered = json.loads(json.dumps(handoff))
        tampered["artifact"]["sha256_observed"] = "0" * 64
        handoff_path.write_text(json.dumps(tampered), encoding="utf-8")
        blocked_tamper = invoke(
            ["-m", "phios.apps.cli", "review-phivine", str(handoff_path)],
            consumer_env, repo, 3,
        )
        assert_held(
            blocked_tamper,
            status="HELD_INVALID_OR_UNTRUSTED_PHIVINE_ADVISORY",
            artifact_allowed=False,
        )

    evidence = {
        "schema": "phios.phivine_real_producer_consumer_smoke.v0.1",
        "phi_vine_source_sha": source_sha,
        "producer_plan_exit": 0,
        "producer_handoff_exit": 3,
        "phi_app_review_exit": 3,
        "observed_status": consumer["status"],
        "forged_approval_status": blocked["status"],
        "tampered_checksum_status": blocked_tamper["status"],
        "producer_source_revalidation_observed": True,
        "synthetic_windows_binary_executed": False,
        "phios_app_installed": False,
        "phios_permission_granted": False,
        "wine_executed": False,
        "security_sandbox_proven": False,
        "release_authorized": False,
    }
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("PHIVINE_PHIOS_REAL_PRODUCER_HANDOFF_HELD_PASS")
    print(json.dumps(evidence, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--producer", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    run(args.producer.resolve(strict=True), args.receipt)


if __name__ == "__main__":
    main()
