"""Live Linux PhiARK identity observations: no service launch or socket cleanup."""
from __future__ import annotations

import hashlib
import json
import os
import socket
import stat
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from phios.apps.phiark_linux_observation import (
    compare_phiark_observations,
    observe_phiark_linux_host,
)

_LINUX = pytest.mark.skipif(sys.platform != "linux", reason="Linux /proc and AF_UNIX")


def _private_vault(tmp_path: Path) -> Path:
    root = tmp_path / "phiark-vault"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    return root


def _listening_socket(root: Path) -> socket.socket:
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(root / ".phiark.sock"))
    os.chmod(root / ".phiark.sock", 0o600)
    listener.listen()
    return listener


def _digest_record(record: dict[str, object], digest_field: str) -> None:
    data = dict(record)
    actual = data.pop(digest_field)
    expected = hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    assert actual == expected


@_LINUX
def test_read_only_live_linux_proc_and_socket_identity(tmp_path: Path) -> None:
    root = _private_vault(tmp_path)
    server = _listening_socket(root)
    try:
        first = observe_phiark_linux_host(pid=os.getpid(), data_directory=root)
        second = observe_phiark_linux_host(pid=os.getpid(), data_directory=root)
        a = first.to_dict()
        assert a["source"] == "LIVE_LINUX_OBSERVATION"
        assert a["process"]["pid"] == os.getpid()
        assert a["process"]["uid"] == os.getuid()
        assert a["process"]["pid_start_ticks"] > 0
        assert a["socket"]["socket_exists"]
        assert a["socket"]["socket_identity"]["permissions"] == 0o600
        assert a["socket"]["socket_identity"]["inode"] > 0
        assert a["process_socket_peer_authenticated"] is False
        assert a["launch_authority"] is False
        assert a["operations_performed"] == []
        _digest_record(a, "observation_sha256")
        compared = compare_phiark_observations(first, second)
        assert compared["status"] == "STABLE_HOST_IDENTITIES_UNQUALIFIED"
        assert compared["same_process_start_identity"]
        assert compared["same_socket_inode"]
        assert compared["socket_connected_to_observed_process"] is False
        assert compared["linux_network_namespace_verified"] is False
        assert compared["launch_authority"] is False
        _digest_record(compared, "comparison_sha256")
        # This test process is NOT PhiARK. The comparator must never say so.
    finally:
        server.close()
    assert (root / ".phiark.sock").exists()  # probe did not unlink
    (root / ".phiark.sock").unlink()


@_LINUX
def test_observation_rejects_non_socket_stale_file_or_symlink(tmp_path: Path) -> None:
    root = _private_vault(tmp_path)
    path = root / ".phiark.sock"
    path.write_bytes(b"stale!")
    with pytest.raises(ValueError, match="private, owned Unix socket"):
        observe_phiark_linux_host(pid=os.getpid(), data_directory=root)
    path.unlink()
    path.symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="private, owned Unix socket"):
        observe_phiark_linux_host(pid=os.getpid(), data_directory=root)
    path.unlink()

    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        observe_phiark_linux_host(pid=os.getpid(), data_directory=alias)


@_LINUX
def test_observation_rejects_unprivate_data_or_socket(tmp_path: Path) -> None:
    root = _private_vault(tmp_path)
    root.chmod(0o755)
    with pytest.raises(ValueError, match="private"):
        observe_phiark_linux_host(pid=os.getpid(), data_directory=root)
    root.chmod(0o700)
    listener = _listening_socket(root)
    try:
        (root / ".phiark.sock").chmod(0o666)
        with pytest.raises(ValueError, match="private, owned Unix socket"):
            observe_phiark_linux_host(pid=os.getpid(), data_directory=root)
    finally:
        listener.close()
        (root / ".phiark.sock").unlink()


def _fake_process(
    tmp_path: Path, *, pid: int = 4321, ticks: int = 987,
    state: str = "S", status_uid: int | None = None,
) -> tuple[Path, Path]:
    proc_root = tmp_path / "proc"
    pid_dir = proc_root / str(pid)
    pid_dir.mkdir(parents=True)
    fields = [state] + ["1"] * 18 + [str(ticks), "0"]
    (pid_dir / "stat").write_text(
        str(pid) + " (nested) process name) " + " ".join(fields) + "\n"
    )
    uid = os.getuid() if status_uid is None else status_uid
    (pid_dir / "status").write_text("Name:\tfake\nUid:\t" + "\t".join([str(uid)] * 4) + "\n")
    boot = proc_root / "boot_id"
    boot.write_text("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n")
    return proc_root, boot


@_LINUX
def test_fixture_proc_identity_detects_pid_reuse_and_zombie_state(tmp_path: Path) -> None:
    root = _private_vault(tmp_path)
    listener = _listening_socket(root)
    try:
        proc, boot = _fake_process(tmp_path)
        one = observe_phiark_linux_host(
            pid=4321, data_directory=root, proc_root=proc, boot_id_path=boot,
        )
        assert one.to_dict()["source"] == "INJECTED_PROC_FIXTURE"
        assert one.to_dict()["process"]["pid_start_ticks"] == 987
        (proc / "4321" / "stat").write_text(
            "4321 (recycled) S " + " ".join(["1"] * 18 + ["998", "0"]) + "\n"
        )
        two = observe_phiark_linux_host(
            pid=4321, data_directory=root, proc_root=proc, boot_id_path=boot,
        )
        with pytest.raises(ValueError, match="process identity changed"):
            compare_phiark_observations(one, two)
        (proc / "4321" / "stat").write_text(
            "4321 (zombie) Z " + " ".join(["1"] * 18 + ["998", "0"]) + "\n"
        )
        zombie = observe_phiark_linux_host(
            pid=4321, data_directory=root, proc_root=proc, boot_id_path=boot,
        )
        assert zombie.to_dict()["process"]["process_non_zombie_observed"] is False
        with pytest.raises(ValueError, match="not live"):
            compare_phiark_observations(zombie, zombie)
        with pytest.raises(ValueError, match="different evidence sources"):
            compare_phiark_observations(
                one, observe_phiark_linux_host(pid=os.getpid(), data_directory=root),
            )
    finally:
        listener.close()
        (root / ".phiark.sock").unlink()


@_LINUX
def test_proc_rejects_bad_owner_truncation_and_nonexistent_pid(tmp_path: Path) -> None:
    root = _private_vault(tmp_path)
    proc, boot = _fake_process(tmp_path, status_uid=os.getuid() + 1)
    with pytest.raises(ValueError, match="observing user"):
        observe_phiark_linux_host(
            pid=4321, data_directory=root, proc_root=proc, boot_id_path=boot,
        )
    (proc / "4321" / "status").write_text(
        "Uid:\t" + "\t".join([str(os.getuid())] * 4) + "\n"
    )
    (proc / "4321" / "stat").write_text("4321 (bad) S 1\n")
    with pytest.raises(ValueError, match="truncated"):
        observe_phiark_linux_host(
            pid=4321, data_directory=root, proc_root=proc, boot_id_path=boot,
        )
    with pytest.raises(ValueError, match="unavailable"):
        observe_phiark_linux_host(
            pid=4322, data_directory=root, proc_root=proc, boot_id_path=boot,
        )
    with pytest.raises(ValueError, match="bounded positive integer"):
        observe_phiark_linux_host(pid=0, data_directory=root)
