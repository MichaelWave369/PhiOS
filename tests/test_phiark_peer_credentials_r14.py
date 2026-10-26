"""PhiARK R1.4: explicit Linux AF_UNIX peer proof, no PhiARK launch."""
from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from phios.apps.phiark_peer_credentials import probe_phiark_socket_peer

_LINUX = pytest.mark.skipif(sys.platform != "linux", reason="Linux SO_PEERCRED only")


def _vault(tmp_path: Path) -> Path:
    root = tmp_path / "private-vault"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    return root


def _listener(root: Path) -> socket.socket:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(root / ".phiark.sock"))
    os.chmod(root / ".phiark.sock", 0o600)
    sock.listen(4)
    return sock


@_LINUX
def test_real_local_peer_probe_has_no_application_payload_and_no_launch(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    listener = _listener(root)
    try:
        result = probe_phiark_socket_peer(
            expected_pid=os.getpid(), data_directory=root, operator_requested=True,
        )
        assert result["status"] == "LOCAL_PEER_CREDENTIALS_MATCH_UNQUALIFIED"
        assert result["peer_pid"] == os.getpid()
        assert result["peer_uid"] == os.getuid()
        assert result["application_bytes_sent"] == 0
        assert result["stable_process_and_socket_observations"] is True
        assert result["listener_authenticated_as_phiark"] is False
        assert result["network_namespace_verified"] is False
        assert result["source_authenticated_against_github"] is False
        assert result["gateway_authority"] is False
        assert result["launch_authority"] is False
        assert result["service_started_or_stopped"] is False
        body = dict(result)
        sha = body.pop("receipt_sha256")
        assert hashlib.sha256(json.dumps(
            body, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode()).hexdigest() == sha
        # Kernel peer credentials alone DO NOT establish that this is PhiARK:
        # this listening process is a Python pytest fixture.
    finally:
        listener.close()
    assert (root / ".phiark.sock").exists()
    (root / ".phiark.sock").unlink()


@_LINUX
def test_active_probe_requires_explicit_opt_in_without_connecting(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    listener = _listener(root)
    try:
        with pytest.raises(ValueError, match="explicit operator request"):
            probe_phiark_socket_peer(expected_pid=os.getpid(), data_directory=root)
        with pytest.raises(ValueError, match="explicit operator request"):
            probe_phiark_socket_peer(
                expected_pid=os.getpid(), data_directory=root, operator_requested=1,
            )
    finally:
        listener.close()
        (root / ".phiark.sock").unlink()


@_LINUX
def test_explicit_probe_rejects_other_live_pid_even_when_socket_is_private(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    listener = _listener(root)
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        with pytest.raises(ValueError, match="peer PID/UID differs"):
            probe_phiark_socket_peer(
                expected_pid=child.pid, data_directory=root, operator_requested=True,
            )
    finally:
        child.terminate()
        try:
            child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=3)
        listener.close()
        (root / ".phiark.sock").unlink()


@_LINUX
def test_active_probe_detects_pid_replacement_between_observations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from phios.apps import phiark_peer_credentials as module
    real_observe = module.observe_phiark_linux_host
    root = _vault(tmp_path)
    listener = _listener(root)
    counter = 0

    def switched(**kwargs: object):
        nonlocal counter
        counter += 1
        snapshot = real_observe(**kwargs)
        if counter == 2:
            return replace(snapshot, process={
                **snapshot.process,
                "pid_start_ticks": snapshot.process["pid_start_ticks"] + 1,
            })
        return snapshot

    monkeypatch.setattr(module, "observe_phiark_linux_host", switched)
    try:
        with pytest.raises(ValueError, match="process identity changed"):
            probe_phiark_socket_peer(
                expected_pid=os.getpid(), data_directory=root, operator_requested=True,
            )
        assert counter == 2
    finally:
        listener.close()
        (root / ".phiark.sock").unlink()


@_LINUX
def test_active_probe_refuses_missing_stale_or_overbroad_socket(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    with pytest.raises(ValueError, match="absent"):
        probe_phiark_socket_peer(
            expected_pid=os.getpid(), data_directory=root, operator_requested=True,
        )
    path = root / ".phiark.sock"
    path.write_text("stale", encoding="utf-8")
    with pytest.raises(ValueError, match="private, owned Unix socket"):
        probe_phiark_socket_peer(
            expected_pid=os.getpid(), data_directory=root, operator_requested=True,
        )
    path.unlink()
    listener = _listener(root)
    try:
        path.chmod(0o666)
        with pytest.raises(ValueError, match="private, owned Unix socket"):
            probe_phiark_socket_peer(
                expected_pid=os.getpid(), data_directory=root, operator_requested=True,
            )
    finally:
        listener.close()
        path.unlink()
