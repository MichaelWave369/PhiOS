"""PhiARK R1.5 live Linux process executable/netns observation tests."""
from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
from pathlib import Path

import pytest

from phios.apps.phiark_peer_credentials import probe_phiark_socket_peer
from phios.apps.phiark_process_executable import inspect_phiark_process_executable

_LINUX = pytest.mark.skipif(sys.platform != "linux", reason="Linux /proc observations")


def _fixture(tmp_path: Path) -> tuple[Path, socket.socket]:
    root = tmp_path / "private-vault"
    root.mkdir(mode=0o700)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(root / ".phiark.sock"))
    (root / ".phiark.sock").chmod(0o600)
    listener.listen(4)
    return root, listener


def _peer_and_binary(tmp_path: Path) -> tuple[Path, socket.socket, dict, str]:
    root, listener = _fixture(tmp_path)
    peer = probe_phiark_socket_peer(
        expected_pid=os.getpid(), data_directory=root, operator_requested=True,
    )
    executable_digest = hashlib.sha256(Path("/proc/self/exe").read_bytes()).hexdigest()
    return root, listener, peer, executable_digest


def _clean(root: Path, listener: socket.socket) -> None:
    listener.close()
    (root / ".phiark.sock").unlink()


def _digest(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


@_LINUX
def test_running_binary_and_netns_match_prior_live_peer_without_authority(tmp_path: Path) -> None:
    root, listener, peer, executable_digest = _peer_and_binary(tmp_path)
    try:
        result = inspect_phiark_process_executable(
            expected_pid=os.getpid(),
            expected_executable_sha256=executable_digest,
            peer_receipt_value=peer,
        )
        assert result["status"] == "EXECUTABLE_HASH_MATCHES_CALLER_INPUT_UNQUALIFIED"
        assert result["pid"] == os.getpid()
        assert result["uid"] == os.getuid()
        assert result["boot_id"] == peer["boot_id"]
        assert result["pid_start_ticks"] == peer["expected_process_start_ticks"]
        assert result["peer_receipt_sha256"] == peer["receipt_sha256"]
        assert result["observed_executable_sha256"] == executable_digest
        assert result["expected_executable_sha256"] == executable_digest
        assert result["executable_byte_count"] > 0
        assert result["network_namespace_relation"] == "SAME_AS_OBSERVER"
        assert result["network_access_denial_verified"] is False
        assert result["executable_pin_independently_authenticated"] is False
        assert result["peer_receipt_is_signed_or_fresh"] is False
        assert result["source_authenticated_against_github"] is False
        assert result["service_supervision_verified"] is False
        assert result["launch_authority"] is False
        assert result["gateway_authority"] is False
        assert result["operations_performed"] == []
        unsigned = dict(result)
        assert unsigned.pop("receipt_sha256") == _digest(unsigned)
    finally:
        _clean(root, listener)


@_LINUX
def test_wrong_executable_digest_is_rejected(tmp_path: Path) -> None:
    root, listener, peer, _ = _peer_and_binary(tmp_path)
    try:
        with pytest.raises(ValueError, match="executable SHA-256 differs"):
            inspect_phiark_process_executable(
                expected_pid=os.getpid(),
                expected_executable_sha256="0" * 64,
                peer_receipt_value=peer,
            )
    finally:
        _clean(root, listener)


@_LINUX
def test_forged_or_replayed_peer_receipt_cannot_override_live_process(tmp_path: Path) -> None:
    root, listener, peer, expected_sha = _peer_and_binary(tmp_path)
    try:
        bad_digest = dict(peer, peer_pid=55555)
        with pytest.raises(ValueError, match="canonical hash mismatch"):
            inspect_phiark_process_executable(
                expected_pid=os.getpid(),
                expected_executable_sha256=expected_sha,
                peer_receipt_value=bad_digest,
            )
        bad_pid = dict(peer, peer_pid=55555)
        bad_pid.pop("receipt_sha256")
        bad_pid["receipt_sha256"] = _digest(bad_pid)
        with pytest.raises(ValueError, match="incompatible or asserts authority"):
            inspect_phiark_process_executable(
                expected_pid=os.getpid(),
                expected_executable_sha256=expected_sha,
                peer_receipt_value=bad_pid,
            )
        altered_claim = dict(peer, expected_process_start_ticks=peer["expected_process_start_ticks"] + 1)
        altered_claim.pop("receipt_sha256")
        altered_claim["receipt_sha256"] = _digest(altered_claim)
        with pytest.raises(ValueError, match="no longer matches earlier peer"):
            inspect_phiark_process_executable(
                expected_pid=os.getpid(),
                expected_executable_sha256=expected_sha,
                peer_receipt_value=altered_claim,
            )
        forged_authority = dict(peer, launch_authority=True)
        forged_authority.pop("receipt_sha256")
        forged_authority["receipt_sha256"] = _digest(forged_authority)
        with pytest.raises(ValueError, match="incompatible or asserts authority"):
            inspect_phiark_process_executable(
                expected_pid=os.getpid(),
                expected_executable_sha256=expected_sha,
                peer_receipt_value=forged_authority,
            )
    finally:
        _clean(root, listener)


@_LINUX
def test_inspector_rejects_missing_pid_and_invalid_expected_digest(tmp_path: Path) -> None:
    root, listener, peer, digest = _peer_and_binary(tmp_path)
    try:
        with pytest.raises(ValueError, match="exact expected executable SHA-256"):
            inspect_phiark_process_executable(
                expected_pid=os.getpid(),
                expected_executable_sha256="not-a-digest",
                peer_receipt_value=peer,
            )
        with pytest.raises(ValueError, match="incompatible or asserts authority"):
            inspect_phiark_process_executable(
                expected_pid=os.getpid() + 1234567,
                expected_executable_sha256=digest,
                peer_receipt_value=peer,
            )
    finally:
        _clean(root, listener)


@_LINUX
def test_namespace_changes_block_even_if_executable_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from phios.apps import phiark_process_executable as module

    root, listener, peer, digest = _peer_and_binary(tmp_path)
    original = module._netns_identity
    calls = 0

    def changed(pid: int):
        nonlocal calls
        calls += 1
        result = original(pid)
        if calls == 2:
            return (result[0][0], result[0][1] + 1), result[1]
        return result

    monkeypatch.setattr(module, "_netns_identity", changed)
    try:
        with pytest.raises(ValueError, match="namespace identity changed"):
            inspect_phiark_process_executable(
                expected_pid=os.getpid(),
                expected_executable_sha256=digest,
                peer_receipt_value=peer,
            )
        assert calls == 2
    finally:
        _clean(root, listener)
