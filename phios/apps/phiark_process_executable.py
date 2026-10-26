"""PhiARK R1.5: process-executable fingerprint and netns comparison.

Read-only Linux observations joined to a prior R1.4 peer-credential report.
The peer report is unsigned and potentially replayable; its digest and the
caller's expected executable digest are NOT trusted roots of authority.
This module neither connects to sockets nor runs/kills processes.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

from .phiark_linux_observation import _process_identity

_SHA = re.compile(r"^[0-9a-f]{64}$")
_MAX_EXECUTABLE_BYTES = 128 * 1024 * 1024
_PROC = Path("/proc")
_BOOT_ID = Path("/proc/sys/kernel/random/boot_id")


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _peer_receipt(peer: Any, expected_pid: int) -> dict[str, Any]:
    if not isinstance(peer, dict):
        raise ValueError("R1.5 requires a PhiARK peer receipt object")
    provided = peer.get("receipt_sha256")
    if not isinstance(provided, str) or not _SHA.fullmatch(provided):
        raise ValueError("PhiARK peer receipt digest is missing or malformed")
    body = dict(peer)
    body.pop("receipt_sha256")
    if _digest(body) != provided:
        raise ValueError("PhiARK peer receipt canonical hash mismatch")
    if (
        body.get("schema") != "phios.phiark_peer_credential_observation.v0.1"
        or body.get("status") != "LOCAL_PEER_CREDENTIALS_MATCH_UNQUALIFIED"
        or body.get("app_id") != "phi.phiark"
        or type(body.get("expected_pid")) is not int
        or body["expected_pid"] != expected_pid
        or type(body.get("peer_pid")) is not int
        or body["peer_pid"] != expected_pid
        or type(body.get("peer_uid")) is not int
        or type(body.get("expected_process_start_ticks")) is not int
        or type(body.get("boot_id")) is not str
        or body.get("peer_pid_uid_equal_expected_process") is not True
        or body.get("stable_process_and_socket_observations") is not True
        or body.get("application_bytes_sent") != 0
        or body.get("listener_authenticated_as_phiark") is not False
        or body.get("source_authenticated_against_github") is not False
        or body.get("toolchain_attested") is not False
        or body.get("network_namespace_verified") is not False
        or body.get("process_supervision_verified") is not False
        or body.get("launch_authority") is not False
        or body.get("gateway_authority") is not False
    ):
        raise ValueError("PhiARK peer receipt is incompatible or asserts authority")
    return body


def _hash_running_executable(pid: int) -> tuple[str, int]:
    """Hash kernel procfs exe descriptor, never an untrusted claimed pathname."""
    fd = os.open(
        _PROC / str(pid) / "exe",
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or not 0 < before.st_size <= _MAX_EXECUTABLE_BYTES
        ):
            raise ValueError("PhiARK running executable is not a bounded regular file")
        digest = hashlib.sha256()
        count = 0
        while True:
            block = os.read(fd, min(1024 * 1024, _MAX_EXECUTABLE_BYTES - count + 1))
            if not block:
                break
            count += len(block)
            if count > _MAX_EXECUTABLE_BYTES:
                raise ValueError("PhiARK executable exceeds bounded hash limit")
            digest.update(block)
        after = os.fstat(fd)
        if (
            count != before.st_size
            or (before.st_dev, before.st_ino, before.st_size)
            != (after.st_dev, after.st_ino, after.st_size)
        ):
            raise ValueError("PhiARK executable changed during descriptor inspection")
        return digest.hexdigest(), count
    finally:
        os.close(fd)


def _netns_identity(pid: int) -> tuple[tuple[int, int], tuple[int, int]]:
    """Read two kernel namespace identities, NOT proof of outbound denial."""
    observed = os.stat(_PROC / str(pid) / "ns" / "net")
    caller = os.stat(_PROC / "self" / "ns" / "net")
    if not stat.S_ISREG(observed.st_mode) or not stat.S_ISREG(caller.st_mode):
        raise ValueError("Linux network namespace identity is not available")
    return (observed.st_dev, observed.st_ino), (caller.st_dev, caller.st_ino)


def inspect_phiark_process_executable(
    *, expected_pid: int, expected_executable_sha256: str,
    peer_receipt_value: Any,
) -> dict[str, Any]:
    """Inspect a pre-existing process, compare a caller-supplied hash and R1.4 receipt.

    There is no signature, trusted pin store, time-bound nonce, executable name
    check, proven sandbox, or origin authentication in this API.
    """
    if sys.platform != "linux":
        raise ValueError("PhiARK process executable inspection requires Linux")
    if not isinstance(expected_executable_sha256, str) or not _SHA.fullmatch(
        expected_executable_sha256
    ):
        raise ValueError("an exact expected executable SHA-256 is required")
    peer = _peer_receipt(peer_receipt_value, expected_pid)
    try:
        first = _process_identity(expected_pid, _PROC, _BOOT_ID)
        if not first["process_non_zombie_observed"]:
            raise ValueError("PhiARK expected process is a zombie")
        if (
            peer["boot_id"] != first["boot_id"]
            or peer["peer_uid"] != first["uid"]
            or peer["expected_process_start_ticks"] != first["pid_start_ticks"]
        ):
            raise ValueError("PhiARK process no longer matches earlier peer observation")
        ns_before, observer_ns = _netns_identity(expected_pid)
        actual_sha, byte_count = _hash_running_executable(expected_pid)
        if actual_sha != expected_executable_sha256:
            raise ValueError("PhiARK executable SHA-256 differs from expected candidate")
        ns_after, observer_again = _netns_identity(expected_pid)
        second = _process_identity(expected_pid, _PROC, _BOOT_ID)
        if (
            first["boot_id"] != second["boot_id"]
            or first["pid"] != second["pid"]
            or first["pid_start_ticks"] != second["pid_start_ticks"]
            or first["uid"] != second["uid"]
            or not second["process_non_zombie_observed"]
        ):
            raise ValueError("PhiARK process identity changed while inspecting executable")
        if ns_before != ns_after or observer_ns != observer_again:
            raise ValueError("Linux namespace identity changed during observation")
    except (OSError, UnicodeError) as exc:
        raise ValueError("PhiARK process executable or network namespace unavailable") from exc

    body: dict[str, Any] = {
        "schema": "phios.phiark_process_executable_observation.v0.1",
        "status": "EXECUTABLE_HASH_MATCHES_CALLER_INPUT_UNQUALIFIED",
        "app_id": "phi.phiark",
        "peer_receipt_sha256": peer_receipt_value["receipt_sha256"],
        "pid": expected_pid,
        "boot_id": first["boot_id"],
        "pid_start_ticks": first["pid_start_ticks"],
        "uid": first["uid"],
        "expected_executable_sha256": expected_executable_sha256,
        "observed_executable_sha256": actual_sha,
        "executable_byte_count": byte_count,
        "linux_process_netns_dev": ns_before[0],
        "linux_process_netns_inode": ns_before[1],
        "linux_observer_netns_dev": observer_ns[0],
        "linux_observer_netns_inode": observer_ns[1],
        "network_namespace_relation": (
            "SAME_AS_OBSERVER"
            if ns_before == observer_ns
            else "DIFFERENT_FROM_OBSERVER_UNQUALIFIED"
        ),
        "peer_receipt_is_signed_or_fresh": False,
        "executable_pin_independently_authenticated": False,
        "source_authenticated_against_github": False,
        "network_access_denial_verified": False,
        "toolchain_attested": False,
        "service_supervision_verified": False,
        "launch_authority": False,
        "gateway_authority": False,
        "operations_performed": [],
    }
    body["receipt_sha256"] = _digest(body)
    return body
