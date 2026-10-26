"""PhiARK R1.4: opt-in AF_UNIX peer credential identity probe.

An explicit local connection (not a passive inspection) obtains SO_PEERCRED
on Linux and cross-checks R1.3 process/socket observations. It sends no
application bytes, starts/stops no service, and never confers launch or
gateway authority. Peer credentials identify the connected listener process
at connect time, not source provenance, sandbox isolation, or PhiARK identity.
"""
from __future__ import annotations

import hashlib
import json
import socket
import struct
import sys
from pathlib import Path
from typing import Any

from .phiark_linux_observation import (
    compare_phiark_observations,
    observe_phiark_linux_host,
)

_UCRED = "3i"
_UCRED_BYTES = struct.calcsize(_UCRED)


def _receipt_digest(data: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def probe_phiark_socket_peer(
    *, expected_pid: int, data_directory: Path, operator_requested: bool = False,
) -> dict[str, Any]:
    """Actively connect once to the already-existing local socket, with no payload.

    The mandatory opt-in is only consent for this diagnostic connection.
    It is *never* authority to run PhiARK, create a gateway or expose a port.
    """
    if operator_requested is not True:
        raise ValueError("explicit operator request required for active PhiARK peer probe")
    if sys.platform != "linux" or not hasattr(socket, "SO_PEERCRED"):
        raise ValueError("PhiARK peer credential probe requires Linux SO_PEERCRED")
    # R1.3 observes process start ticks and socket device/inode, with restrictive
    # owner permissions, before the local connection attempt.
    initial = observe_phiark_linux_host(pid=expected_pid, data_directory=data_directory)
    first = initial.to_dict()
    if not first["process"]["process_non_zombie_observed"]:
        raise ValueError("PhiARK expected process is not live")
    if not first["socket"]["socket_exists"]:
        raise ValueError("PhiARK private Unix socket is absent")
    root = Path(data_directory)
    path = root / ".phiark.sock"
    link = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        link.settimeout(1.0)
        link.connect(str(path))
        raw = link.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, _UCRED_BYTES)
        if len(raw) != _UCRED_BYTES:
            raise ValueError("Linux SO_PEERCRED returned a truncated credential record")
        peer_pid, peer_uid, peer_gid = struct.unpack(_UCRED, raw)
        if peer_pid != expected_pid or peer_uid != first["process"]["uid"]:
            raise ValueError("PhiARK Unix-socket peer PID/UID differs from expected process")
        if peer_pid <= 0 or peer_gid < 0:
            raise ValueError("PhiARK Unix-socket peer credential fields are invalid")
        # Recheck while the connected descriptor is still held. The pathname
        # may be replaced independently; a stable tuple does not eliminate all
        # races, does not prove SO_PEERCRED's listener is the running app, and
        # does not authenticate its executable.
        second = observe_phiark_linux_host(pid=expected_pid, data_directory=data_directory)
        stable = compare_phiark_observations(initial, second)
    except (OSError, TimeoutError) as exc:
        raise ValueError("PhiARK local peer connection or identity inspection failed") from exc
    finally:
        link.close()

    report: dict[str, Any] = {
        "schema": "phios.phiark_peer_credential_observation.v0.1",
        "status": "LOCAL_PEER_CREDENTIALS_MATCH_UNQUALIFIED",
        "app_id": "phi.phiark",
        "observation_kind": "EXPLICIT_AF_UNIX_CONNECT_NO_APPLICATION_PAYLOAD",
        "expected_pid": expected_pid,
        "peer_pid": peer_pid,
        "peer_uid": peer_uid,
        "peer_gid": peer_gid,
        "expected_process_start_ticks": first["process"]["pid_start_ticks"],
        "boot_id": first["process"]["boot_id"],
        "peer_pid_uid_equal_expected_process": True,
        "stable_process_and_socket_observations": True,
        "first_observation_sha256": first["observation_sha256"],
        "second_observation_sha256": second.to_dict()["observation_sha256"],
        "stability_comparison_sha256": stable["comparison_sha256"],
        "application_bytes_sent": 0,
        "listener_authenticated_as_phiark": False,
        "source_authenticated_against_github": False,
        "toolchain_attested": False,
        "network_namespace_verified": False,
        "process_supervision_verified": False,
        "install_authority": False,
        "launch_authority": False,
        "gateway_authority": False,
        "service_started_or_stopped": False,
    }
    report["receipt_sha256"] = _receipt_digest(report)
    return report
