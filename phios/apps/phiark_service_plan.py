"""PhiARK R0.9: fail-closed installed-tree service command preview.

This module performs no installation, privilege escalation, launch, socket
cleanup or network access. A command preview is not launch authority and
does not qualify real Bubblewrap isolation or a Node toolchain.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runtime import BubblewrapRuntimeRunner, InstalledRuntimePlan, plan_installed_runtime

APP_ID = "phi.phiark"
SOURCE = "https://github.com/MichaelWave369/PhiARK"
ENTRYPOINT = "src/server.mjs"
DATA = "/phios/app-data"
SOCKET = "/phios/app-data/.phiark.sock"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")


def _canonical(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _private_directory(value: Path) -> tuple[Path, os.stat_result]:
    if not value.is_absolute():
        raise ValueError("PhiARK data directory must be absolute")
    path = Path(os.path.abspath(value))
    root_info: os.stat_result | None = None
    for component in (path, *path.parents):
        info = component.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise ValueError("PhiARK data directory contains a symlink or unsafe component")
        if component == path:
            if info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError("PhiARK data directory must be private (0700) and owner-controlled")
            root_info = info
    if root_info is None:
        raise ValueError("PhiARK private directory validation failed")
    return path, root_info


def _socket_absent(directory: Path) -> None:
    path = directory / ".phiark.sock"
    try:
        path.lstat()
    except FileNotFoundError:
        return
    raise ValueError("PhiARK socket path already exists; manual operator recovery required")


@dataclass(frozen=True)
class PhiARKServicePreview:
    source_commit_candidate: str
    runtime_plan_sha256: str
    installed_tree_sha256: str
    install_receipt_sha256: str
    install_path: str
    data_directory: str
    data_device: int
    data_inode: int
    schema: str = "phios.phiark_service_preview.v0.1"
    status: str = "HELD_FOR_OPERATOR_REVIEW"

    def __post_init__(self) -> None:
        if not _SHA40.fullmatch(self.source_commit_candidate):
            raise ValueError("reviewed source commit candidate must be a full 40-character SHA")
        if not all(
            re.fullmatch(r"[0-9a-f]{64}", item)
            for item in (
                self.runtime_plan_sha256,
                self.installed_tree_sha256,
                self.install_receipt_sha256,
            )
        ):
            raise ValueError("invalid installed runtime digest")
        if self.data_device < 0 or self.data_inode <= 0:
            raise ValueError("invalid private data-root identity")

    def to_dict(self) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "schema": self.schema,
            "status": self.status,
            "app_id": APP_ID,
            "source_repository": SOURCE,
            "source_commit_candidate": self.source_commit_candidate,
            "source_commit_attested_to_installed_tree": False,
            "runtime_plan_sha256": self.runtime_plan_sha256,
            "install_receipt_sha256": self.install_receipt_sha256,
            "installed_tree_sha256": self.installed_tree_sha256,
            "installed_path": self.install_path,
            "private_data_directory": self.data_directory,
            "data_device": self.data_device,
            "data_inode": self.data_inode,
            "guest_environment": {
                "PHIARK_DATA_DIR": DATA,
                "PHIARK_SOCKET_PATH": SOCKET,
            },
            "network_mode": "deny",
            "host_network_inherited": False,
            "toolchain_attested": False,
            "physical_network_isolation_qualified": False,
            "service_supervised": False,
            "install_authority": False,
            "launch_authority": False,
            "gateway_authority": False,
        }
        fields["preview_sha256"] = hashlib.sha256(_canonical(fields).encode()).hexdigest()
        return fields


def _validated_runtime(receipt: dict[str, Any], install_root: Path) -> InstalledRuntimePlan:
    # plan_installed_runtime rechecks the actual installed tree, manifest and
    # receipt. No caller-supplied manifest or authority flag is trusted.
    plan = plan_installed_runtime(receipt, install_root=install_root)
    manifest_file = Path(plan.install_path) / ".phios" / "manifest.json"
    # These are additional PhiARK-specific restrictions beyond the generic
    # installed-runtime rules, not an alternative verification mechanism.
    from .manifest import AppManifest

    manifest = AppManifest.from_json(manifest_file.read_text(encoding="utf-8"))
    if (
        plan.app_id != APP_ID
        or manifest.source.repository_url != SOURCE
        or manifest.source.license_expression != "MIT"
        or plan.runtime_kind != "node"
        or plan.entrypoint_target != ENTRYPOINT
        or plan.status != "ready_for_review"
        or plan.adapter != "node_direct_v034"
        or plan.network_mode != "deny"
        or plan.data_mode != "persistent"
        or plan.requested_runtime_permissions != ("runtime.data.persist",)
        or plan.runtime_argv != ("node", "/app/src/server.mjs")
        or plan.sandbox_entrypoint_path != "/app/src/server.mjs"
    ):
        raise ValueError("installed PhiARK manifest requests unsupported runtime or authority")
    return plan


def inspect_phiark_service(
    receipt: dict[str, Any], *, install_root: Path, data_directory: Path,
    source_commit_candidate: str,
) -> PhiARKServicePreview:
    if os.name != "posix" or not hasattr(os, "getuid"):
        raise ValueError("PhiARK service preview requires a POSIX host")
    runtime = _validated_runtime(receipt, install_root)
    directory, data_info = _private_directory(data_directory)
    install_path = Path(runtime.install_path)
    if directory == install_path or install_path in directory.parents or directory in install_path.parents:
        raise ValueError("PhiARK writable data cannot overlap the installed executable tree")
    _socket_absent(directory)
    return PhiARKServicePreview(
        source_commit_candidate=source_commit_candidate,
        runtime_plan_sha256=runtime.sha256(),
        installed_tree_sha256=runtime.installed_tree_sha256,
        install_receipt_sha256=runtime.install_receipt_sha256,
        install_path=runtime.install_path,
        data_directory=str(directory),
        data_device=data_info.st_dev,
        data_inode=data_info.st_ino,
    )


def command_preview(
    receipt: dict[str, Any], *, install_root: Path, data_directory: Path,
    source_commit_candidate: str, reviewed_preview_sha256: str,
    node_binary: Path, bwrap_binary: Path, prlimit_binary: Path,
) -> tuple[str, ...]:
    """Assemble bounded Bubblewrap argv but do not run or authorize it."""
    if not re.fullmatch(r"[0-9a-f]{64}", reviewed_preview_sha256):
        raise ValueError("exact reviewed preview SHA-256 required")
    preview = inspect_phiark_service(
        receipt, install_root=install_root, data_directory=data_directory,
        source_commit_candidate=source_commit_candidate,
    )
    if preview.to_dict()["preview_sha256"] != reviewed_preview_sha256:
        raise ValueError("PhiARK preview changed after operator review")
    runtime = _validated_runtime(receipt, install_root)
    if runtime.sha256() != preview.runtime_plan_sha256:
        raise ValueError("installed runtime plan changed")
    if node_binary.name != "node" or not node_binary.is_absolute():
        raise ValueError("exact absolute node executable must be selected for review")
    if not bwrap_binary.is_absolute() or not prlimit_binary.is_absolute():
        raise ValueError("absolute sandbox executables must be selected for review")
    runner = BubblewrapRuntimeRunner(
        runtime.policy,
        payload_root=Path(runtime.install_path) / "payload",
        data_path=Path(preview.data_directory),
        bwrap_path=str(bwrap_binary),
        prlimit_path=str(prlimit_binary),
    )
    command = list(
        runner.command_for(
            executable_path=str(node_binary), argv_tail=("/app/src/server.mjs",),
        )
    )
    data_mount = ["--bind", preview.data_directory, DATA]
    for ix in range(len(command) - len(data_mount) + 1):
        if command[ix:ix + len(data_mount)] == data_mount:
            break
    else:
        raise ValueError("PhiARK private data mount missing from runtime")
    if "--unshare-net" not in command or "--share-net" in command:
        raise ValueError("PhiARK sandbox did not deny ambient networking")
    if ["--ro-bind", str(Path(runtime.install_path) / "payload"), "/app"] not in [
        command[i:i + 3] for i in range(len(command) - 2)
    ]:
        raise ValueError("PhiARK executable tree is not mounted read-only")
    guest_data = ["--setenv", "PHIOS_APP_DATA", DATA]
    index = next(
        (i for i in range(len(command) - 2) if command[i:i + 3] == guest_data),
        None,
    )
    if index is None or "--clearenv" not in command:
        raise ValueError("PhiARK runtime environment isolation unavailable")
    command[index + 3:index + 3] = [
        "--setenv", "PHIARK_DATA_DIR", DATA,
        "--setenv", "PHIARK_SOCKET_PATH", SOCKET,
    ]
    # Confirm no network-related PhiARK variables were injected into the guest.
    if any(name in command for name in ("PHIARK_HOST", "PHIARK_PORT", "PHIARK_ALLOW_LAN")):
        raise ValueError("PhiARK TCP/LAN settings must not enter the sandbox")
    if command[-3:] != ["--", str(node_binary.resolve()), "/app/src/server.mjs"]:
        raise ValueError("PhiARK sandbox command tail was unexpected")
    return tuple(command)
