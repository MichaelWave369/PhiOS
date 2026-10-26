"""PhiARK R1.3: read-only Linux process and private socket observation.

This is a host evidence *probe*, not an app launcher, readiness attestation,
SO_PEERCRED authentication, PID-owner lease, sandbox proof, or supervisor.
It never creates/removes sockets, opens a network connection, sends signals,
or authorizes a transition of the R1.2 simulated lifecycle.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .phiark_service_plan import _private_directory

_BOOT = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_MAX_PROC_READ = 32768
_MAX_PID = 4194304


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _read_proc(path: Path) -> bytes:
    # /proc files may have zero st_size even when their content is nonempty.
    if path.is_symlink():
        raise ValueError("PhiARK process observation refuses proc symlinks")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("PhiARK proc evidence is not a regular file")
        data = os.read(fd, _MAX_PROC_READ + 1)
        if len(data) > _MAX_PROC_READ:
            raise ValueError("PhiARK proc evidence is oversized")
        return data
    finally:
        os.close(fd)


def _process_identity(pid: int, proc_root: Path, boot_id_path: Path) -> dict[str, Any]:
    if type(pid) is not int or not 1 <= pid <= _MAX_PID:
        raise ValueError("PhiARK probe PID must be a bounded positive integer")
    if proc_root.is_symlink():
        raise ValueError("PhiARK /proc root must not be a symlink")
    pid_dir = proc_root / str(pid)
    if pid_dir.is_symlink():
        raise ValueError("PhiARK process directory must not be a symlink")
    try:
        boot = _read_proc(boot_id_path).decode("ascii").strip()
        stat_text = _read_proc(pid_dir / "stat").decode("utf-8")
        status = _read_proc(pid_dir / "status").decode("utf-8")
    except (FileNotFoundError, ProcessLookupError) as exc:
        raise ValueError("PhiARK process evidence unavailable; no liveness assertion") from exc
    if not _BOOT.fullmatch(boot):
        raise ValueError("invalid Linux boot identity")
    # Linux /proc/<pid>/stat field 2 is a comm string enclosed by
    # parentheses. It can itself contain spaces and right parentheses.
    left = stat_text.find("(")
    right = stat_text.rfind(") ")
    if left <= 0 or right <= left:
        raise ValueError("malformed Linux proc stat record")
    parsed_pid = stat_text[:left].strip()
    fields = stat_text[right + 2:].split()  # starts with field 3
    if parsed_pid != str(pid) or len(fields) < 20:
        raise ValueError("proc stat PID mismatch or truncated fields")
    process_state = fields[0]
    if process_state not in {"R", "S", "D", "T", "t", "I", "Z", "X", "x"}:
        raise ValueError("unexpected Linux process state")
    try:
        start_ticks = int(fields[19])  # starttime: field 22
    except ValueError as exc:
        raise ValueError("invalid process start ticks") from exc
    if start_ticks <= 0:
        raise ValueError("invalid process start ticks")
    uid_line = next((line for line in status.splitlines() if line.startswith("Uid:")), None)
    if uid_line is None:
        raise ValueError("proc status missing UID row")
    uid_values = uid_line.split()[1:]
    if len(uid_values) != 4 or not all(value.isdecimal() for value in uid_values):
        raise ValueError("invalid proc status UID values")
    observed_uids = tuple(int(value) for value in uid_values)
    if any(uid != os.getuid() for uid in observed_uids):
        raise ValueError("PhiARK process must belong exclusively to observing user")
    return {
        "pid": pid,
        "boot_id": boot,
        "pid_start_ticks": start_ticks,
        "uid": observed_uids[0],
        "process_state": process_state,
        "process_non_zombie_observed": process_state not in {"Z", "X", "x"},
    }


def _socket_identity(data_directory: Path) -> dict[str, Any]:
    directory, before = _private_directory(data_directory)
    path = directory / ".phiark.sock"
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {"socket_exists": False, "socket_identity": None}
    if (
        not stat.S_ISSOCK(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
        or info.st_nlink != 1
    ):
        raise ValueError("PhiARK socket path is not a private, owned Unix socket")
    after = directory.lstat()
    if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
        raise ValueError("PhiARK data directory changed during socket observation")
    return {
        "socket_exists": True,
        "socket_identity": {
            "device": info.st_dev,
            "inode": info.st_ino,
            "uid": info.st_uid,
            "permissions": stat.S_IMODE(info.st_mode),
            "private_data_device": before.st_dev,
            "private_data_inode": before.st_ino,
        },
    }


@dataclass(frozen=True)
class PhiARKHostObservation:
    process: dict[str, Any]
    socket: dict[str, Any]
    source: str
    schema: str = "phios.phiark_host_observation.v0.1"

    def to_dict(self) -> dict[str, Any]:
        body = {
            "schema": self.schema,
            "status": "HOST_OBSERVED_NOT_ATTESTED",
            "app_id": "phi.phiark",
            "source": self.source,
            "process": self.process,
            "socket": self.socket,
            "process_socket_peer_authenticated": False,
            "phiark_executable_authenticated": False,
            "linux_network_namespace_verified": False,
            "service_supervision_verified": False,
            "ready_to_launch": False,
            "launch_authority": False,
            "gateway_authority": False,
            "operations_performed": [],
        }
        body["observation_sha256"] = _digest(body)
        return body


def observe_phiark_linux_host(
    *, pid: int, data_directory: Path,
    proc_root: Path = Path("/proc"),
    boot_id_path: Path = Path("/proc/sys/kernel/random/boot_id"),
) -> PhiARKHostObservation:
    """Read observable Linux identities; no process ownership/peer binding."""
    if sys.platform != "linux":
        raise ValueError("PhiARK host observation requires Linux")
    proc = _process_identity(pid, proc_root, boot_id_path)
    sock = _socket_identity(data_directory)
    source = (
        "LIVE_LINUX_OBSERVATION"
        if proc_root == Path("/proc") and boot_id_path == Path("/proc/sys/kernel/random/boot_id")
        else "INJECTED_PROC_FIXTURE"
    )
    return PhiARKHostObservation(process=proc, socket=sock, source=source)


def compare_phiark_observations(
    first: PhiARKHostObservation,
    second: PhiARKHostObservation,
) -> dict[str, Any]:
    """Crosscheck two samples only; no assertion that the process owns the socket."""
    a, b = first.to_dict(), second.to_dict()
    if a["source"] != b["source"]:
        raise ValueError("PhiARK observations came from different evidence sources")
    process_keys = ("pid", "boot_id", "pid_start_ticks", "uid")
    if any(a["process"][key] != b["process"][key] for key in process_keys):
        raise ValueError("PhiARK process identity changed between observations")
    if not a["process"]["process_non_zombie_observed"] or not b["process"]["process_non_zombie_observed"]:
        raise ValueError("PhiARK process is not live in both observations")
    if not a["socket"]["socket_exists"] or not b["socket"]["socket_exists"]:
        raise ValueError("PhiARK socket missing in one or both observations")
    if a["socket"]["socket_identity"] != b["socket"]["socket_identity"]:
        raise ValueError("PhiARK socket identity changed between observations")
    body: dict[str, Any] = {
        "schema": "phios.phiark_host_observation_pair.v0.1",
        "status": "STABLE_HOST_IDENTITIES_UNQUALIFIED",
        "first_sha256": a["observation_sha256"],
        "second_sha256": b["observation_sha256"],
        "same_process_start_identity": True,
        "same_socket_inode": True,
        "socket_connected_to_observed_process": False,
        "process_socket_peer_authenticated": False,
        "linux_network_namespace_verified": False,
        "source_authenticated_against_github": False,
        "service_supervision_verified": False,
        "launch_authority": False,
        "gateway_authority": False,
        "operations_performed": [],
    }
    body["comparison_sha256"] = _digest(body)
    return body
