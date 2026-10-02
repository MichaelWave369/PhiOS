from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from phios.adapters.nbga import MemoryReceipt, NBGContractError
from phios.adapters.nbga_observation import (
    MAX_DOCUMENT_BYTES,
    PACKET_FILENAME,
    PINNED_PACKET_SHA256,
    observe,
)

ROOT = Path(__file__).parents[1]
EVIDENCE = ROOT / "docs/os/evidence"
LATEST = "bubble:phios:virtualbox:launcher-0f17bac1"


@pytest.fixture
def packet_root(tmp_path: Path) -> Path:
    packet = json.loads((EVIDENCE / PACKET_FILENAME).read_bytes())
    shutil.copyfile(EVIDENCE / PACKET_FILENAME, tmp_path / PACKET_FILENAME)
    for item in packet["evidence"]:
        shutil.copyfile(EVIDENCE / item["filename"], tmp_path / item["filename"])
    return tmp_path


def changed_packet(root: Path, change) -> str:
    packet = json.loads((root / PACKET_FILENAME).read_bytes())
    change(packet)
    raw = (json.dumps(packet, ensure_ascii=False, allow_nan=False) + "\n").encode()
    (root / PACKET_FILENAME).write_bytes(raw)
    # Test-owned pins permit schema refusal tests to reach the parser. Production
    # uses the independent code pin, never a digest read from the packet itself.
    return hashlib.sha256(raw).hexdigest()


def test_real_packet_preserves_failures_sources_and_reported_trust():
    result = observe(EVIDENCE)
    payload = result.to_payload()
    assert len(result.evidence) == len(result.receipts) == 4
    assert result.packet_sha256 == PINNED_PACKET_SHA256
    original, failure, automatic, latest = result.receipts
    assert "renderer failed with 3D off" in original.observable
    assert "WLR_NO_HARDWARE_CURSORS=1 restored the pointer" in original.observable
    assert "restarting the session target restored PhiShell/Waybar" in original.observable
    assert "installation/recovery was skipped" in failure.observable
    assert failure.trust_state == "reviewed-ci-record"
    assert "wrong-password refusal/PAM unlock was not tested" in automatic.observable
    assert "8635a5f1277ca01ef7174b6e3b325e3cf9e972572070eb84d7395b9cec3dcd08" in latest.observable
    assert "canonical history unavailable" in latest.observable
    assert latest.trust_state == "owner-reported" and latest.confidence is None
    assert len(latest.gear_path) == 3 and latest.gear_path[-1].destination == LATEST
    assert payload["bubble_zero"] == {"availability": "unavailable", "reason": "no continuity backend"}
    assert payload["release_ready"] is payload["publication_authority"] is False
    for receipt in payload["observations"]:
        assert MemoryReceipt.from_payload(receipt).provenance_root.startswith("sha256:")


def test_repeated_reads_are_deterministic_and_create_no_files(packet_root: Path):
    before = {p.name: p.read_bytes() for p in packet_root.iterdir()}
    first = observe(packet_root).to_payload()
    assert observe(packet_root).to_payload() == first
    assert {p.name: p.read_bytes() for p in packet_root.iterdir()} == before
    assert observe(packet_root, bubble_id=LATEST).receipts == (observe(packet_root).receipts[-1],)


@pytest.mark.parametrize("alteration", ["missing", "content", "size", "symlink", "directory", "large"])
def test_unavailable_or_changed_prior_failure_blocks_latest_query(packet_root: Path, alteration: str):
    path = packet_root / "virtualbox-compatibility-attempts.json"
    if alteration == "content":
        raw = path.read_bytes()
        path.write_bytes(raw.replace(b"failed at", b"passed at", 1))
    elif alteration == "size":
        path.write_bytes(path.read_bytes() + b" ")
    elif alteration == "large":
        path.write_bytes(b"x" * (MAX_DOCUMENT_BYTES + 1))
    else:
        path.unlink()
        if alteration == "symlink":
            path.symlink_to(EVIDENCE / path.name)
        elif alteration == "directory":
            path.mkdir()
    with pytest.raises(NBGContractError):
        observe(packet_root, bubble_id=LATEST)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO refusal is a POSIX case")
def test_fifo_evidence_is_refused_without_waiting_for_a_writer(packet_root: Path):
    path = packet_root / "virtualbox-compatibility-attempts.json"
    path.unlink()
    os.mkfifo(path)
    with pytest.raises(NBGContractError):
        observe(packet_root)


def test_packet_cannot_self_assert_its_own_pin(packet_root: Path):
    changed_packet(packet_root, lambda packet: packet["observations"][-1].update(trust_state="verified"))
    with pytest.raises(NBGContractError, match="packet integrity"):
        observe(packet_root)


@pytest.mark.parametrize("field", ["raw_state", "payload_ref", "authority_grant", "unknown"])
@pytest.mark.parametrize("level", ["packet", "observation", "evidence", "gear"])
def test_private_authority_or_unknown_fields_fail_closed(packet_root: Path, field: str, level: str):
    def change(packet):
        target = {"packet": packet, "observation": packet["observations"][-1],
                  "evidence": packet["evidence"][0], "gear": packet["observations"][-1]["gear_path"][0]}[level]
        target[field] = "must-not-cross"
    expected = changed_packet(packet_root, change)
    with pytest.raises(NBGContractError):
        observe(packet_root, expected_packet_sha256=expected)


@pytest.mark.parametrize("filename", ["../outside.json", "/outside.json", "sub/file.json", "sub\\file.json", "https://example.test/file.json"])
def test_evidence_filenames_cannot_escape_the_selected_directory(packet_root: Path, filename: str):
    expected = changed_packet(packet_root, lambda packet: packet["evidence"][0].update(filename=filename))
    with pytest.raises(NBGContractError, match="filename"):
        observe(packet_root, expected_packet_sha256=expected)


@pytest.mark.parametrize("case", ["unknown-schema", "duplicate-id", "duplicate-file", "duplicate-bubble", "missing-ref", "missing-lineage", "repeated-ref", "head", "trust", "confidence", "version-bool", "size-bool", "digest", "disconnected", "cycle", "unknown-bubble", "wrong-end", "conflicting-gear", "unreferenced", "oversized-array", "oversized-text"])
def test_malformed_lineage_and_unearned_verification_are_refused(packet_root: Path, case: str):
    def change(packet):
        latest = packet["observations"][-1]
        if case == "unknown-schema":
            packet["schema_version"] += "-unknown"
        elif case == "duplicate-id":
            packet["evidence"][1]["id"] = packet["evidence"][0]["id"]
        elif case == "duplicate-file":
            packet["evidence"][1]["filename"] = packet["evidence"][0]["filename"]
        elif case == "duplicate-bubble":
            latest["bubble_id"] = packet["observations"][0]["bubble_id"]
        elif case == "missing-ref":
            latest["evidence"][0] = "document:missing"
        elif case == "missing-lineage":
            latest["evidence"].pop(0)
        elif case == "repeated-ref":
            latest["evidence"][0] = latest["evidence"][1]
        elif case == "head":
            latest["event_head"] = "document:missing"
        elif case == "trust":
            latest["trust_state"] = "verified"
        elif case == "confidence":
            latest["confidence"] = 1.0
        elif case == "version-bool":
            latest["bubble_version"] = True
        elif case == "size-bool":
            packet["evidence"][0]["size_bytes"] = True
        elif case == "digest":
            packet["evidence"][0]["sha256"] = "sha256:..."
        elif case == "disconnected":
            latest["gear_path"][1]["source"] = latest["bubble_id"]
        elif case == "cycle":
            latest["gear_path"][1]["destination"] = latest["gear_path"][0]["source"]
        elif case == "unknown-bubble":
            latest["gear_path"][0]["source"] = "bubble:missing"
        elif case == "wrong-end":
            latest["gear_path"].pop()
        elif case == "conflicting-gear":
            latest["gear_path"][-1]["gear_id"] = latest["gear_path"][0]["gear_id"]
        elif case == "unreferenced":
            packet["observations"].pop()
        elif case == "oversized-array":
            packet["observations"] *= 65
        elif case == "oversized-text":
            latest["observable"] = "x" * 4097
    expected = changed_packet(packet_root, change)
    with pytest.raises(NBGContractError):
        observe(packet_root, expected_packet_sha256=expected)


@pytest.mark.parametrize("wire", [b'{"schema_version":1,"schema_version":2}', b'{"value":NaN}', b'\xff', b'{'])
def test_ambiguous_nonfinite_or_invalid_json_is_refused(packet_root: Path, wire: bytes):
    (packet_root / PACKET_FILENAME).write_bytes(wire)
    with pytest.raises(NBGContractError):
        observe(packet_root, expected_packet_sha256=hashlib.sha256(wire).hexdigest())


@pytest.mark.parametrize("pin", ["", "sha256:...", "A" * 64])
def test_explicit_pin_must_be_a_complete_canonical_digest(packet_root: Path, pin: str):
    with pytest.raises(NBGContractError, match="SHA-256"):
        observe(packet_root, expected_packet_sha256=pin)


def test_cli_success_refusal_and_no_host_path_disclosure(packet_root: Path):
    command = [sys.executable, "-m", "phios.adapters.nbga_observation", "--evidence-root", str(packet_root)]
    success = subprocess.run(command + ["--bubble-id", LATEST], capture_output=True, text=True, timeout=5)
    assert success.returncode == 0 and success.stderr == ""
    assert len(json.loads(success.stdout)["observations"]) == 1
    unknown = subprocess.run(command + ["--bubble-id", "bubble:missing"], capture_output=True, text=True, timeout=5)
    assert unknown.returncode == 2 and "observations" not in json.loads(unknown.stdout)
    (packet_root / "virtualbox-compatibility-attempts.json").unlink()
    failed = subprocess.run(command + ["--bubble-id", LATEST], capture_output=True, text=True, timeout=5)
    payload = json.loads(failed.stdout)
    assert failed.returncode == 2 and failed.stderr == ""
    assert payload["availability"] == "unavailable" and "observations" not in payload
    assert str(packet_root) not in failed.stdout
    assert payload["publication_authority"] is False
