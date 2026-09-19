from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Literal, Protocol, cast

from .build_execution import ProcessResult, SubprocessBuildRunner, ToolIdentity
from .manifest import AppManifest
from .package_install import AppInstallReceipt, snapshot_installed_tree
from .sandbox import SandboxBackendIdentity

RUNTIME_SANDBOX_POLICY_SCHEMA_VERSION = "phios.runtime_sandbox_policy.v0.1"
INSTALLED_RUNTIME_PLAN_SCHEMA_VERSION = "phios.installed_runtime_plan.v0.1"
INSTALLED_RUNTIME_REVIEW_SCHEMA_VERSION = "phios.installed_runtime_plan_review.v0.1"
RUNTIME_LAUNCH_RECEIPT_SCHEMA_VERSION = "phios.runtime_launch_receipt.v0.1"

RuntimeNetworkMode = Literal["deny", "inherit"]
RuntimeDataMode = Literal["ephemeral", "persistent"]
RuntimeStatus = Literal[
    "ready_for_review",
    "unsupported_runtime",
    "unsupported_entrypoint",
    "unsupported_permissions",
]

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PERMISSION_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
_SAFE_VERSION_RE = re.compile(r"^[\x20-\x7e]{1,512}$")
_SUPPORTED_RUNTIME_PERMISSIONS = {
    "runtime.network.inherit",
    "runtime.data.persist",
}
_SANDBOX_SYSTEM_ROOTS = (
    "/usr",
    "/bin",
    "/sbin",
    "/lib",
    "/lib64",
    "/opt",
    "/nix/store",
)
_SANDBOX_ETC_PATHS = (
    "/etc/alternatives",
    "/etc/ld.so.cache",
    "/etc/ssl",
    "/etc/pki",
    "/etc/ca-certificates",
    "/etc/nsswitch.conf",
    "/etc/resolv.conf",
    "/etc/hosts",
    "/etc/services",
)
_MIN_MEMORY_BYTES = 128 * 1024 * 1024
_MAX_MEMORY_BYTES = 64 * 1024 * 1024 * 1024
_MIN_FILE_SIZE_BYTES = 1 * 1024 * 1024
_MAX_FILE_SIZE_BYTES = 4 * 1024 * 1024 * 1024


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, Any], value)


def _string(value: Any, label: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    if len(value) > maximum:
        raise ValueError(f"{label} exceeds {maximum} characters")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"{label} contains control characters")
    return value


def _sha256(value: Any, label: str) -> str:
    text = _string(value, label, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return text


def _int(value: Any, label: str, *, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return value


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _safe_relative(value: Any, label: str) -> str:
    text = _string(value, label, maximum=512)
    if chr(92) in text or text.startswith("/"):
        raise ValueError(f"{label} must be a relative POSIX path")
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{label} contains unsafe path segments")
    return text


def _path_under(root: Path, candidate: Path, label: str) -> Path:
    resolved_root = root.resolve(strict=True)
    if candidate.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    resolved = candidate.resolve(strict=True)
    if resolved_root != resolved and resolved_root not in resolved.parents:
        raise ValueError(f"{label} escaped configured root")
    return resolved


@dataclass(frozen=True)
class RuntimeSandboxPolicy:
    network_mode: RuntimeNetworkMode = "deny"
    wall_clock_seconds: int = 300
    cpu_seconds: int = 300
    address_space_bytes: int = 2 * 1024 * 1024 * 1024
    max_open_files: int = 512
    max_file_size_bytes: int = 128 * 1024 * 1024
    backend: str = "bubblewrap"
    schema_version: str = RUNTIME_SANDBOX_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_SANDBOX_POLICY_SCHEMA_VERSION:
            raise ValueError(f"Unsupported runtime sandbox policy schema: {self.schema_version}")
        if self.backend != "bubblewrap":
            raise ValueError("v0.34 supports only the bubblewrap runtime backend")
        if self.network_mode not in {"deny", "inherit"}:
            raise ValueError("runtime network_mode must be deny or inherit")
        _int(self.wall_clock_seconds, "wall_clock_seconds", minimum=1, maximum=3600)
        _int(self.cpu_seconds, "cpu_seconds", minimum=1, maximum=3600)
        _int(
            self.address_space_bytes,
            "address_space_bytes",
            minimum=_MIN_MEMORY_BYTES,
            maximum=_MAX_MEMORY_BYTES,
        )
        _int(self.max_open_files, "max_open_files", minimum=32, maximum=8192)
        _int(
            self.max_file_size_bytes,
            "max_file_size_bytes",
            minimum=_MIN_FILE_SIZE_BYTES,
            maximum=_MAX_FILE_SIZE_BYTES,
        )

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "backend": self.backend,
            "network_mode": self.network_mode,
            "wall_clock_seconds": self.wall_clock_seconds,
            "cpu_seconds": self.cpu_seconds,
            "address_space_bytes": self.address_space_bytes,
            "max_open_files": self.max_open_files,
            "max_file_size_bytes": self.max_file_size_bytes,
        }

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["policy_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> RuntimeSandboxPolicy:
        data = _mapping(value, "runtime sandbox policy")
        expected = {
            "schema_version",
            "backend",
            "network_mode",
            "wall_clock_seconds",
            "cpu_seconds",
            "address_space_bytes",
            "max_open_files",
            "max_file_size_bytes",
            "policy_sha256",
        }
        if set(data) != expected:
            raise ValueError("runtime sandbox policy contains missing or unknown fields")
        policy = cls(
            schema_version=data["schema_version"],
            backend=data["backend"],
            network_mode=data["network_mode"],
            wall_clock_seconds=data["wall_clock_seconds"],
            cpu_seconds=data["cpu_seconds"],
            address_space_bytes=data["address_space_bytes"],
            max_open_files=data["max_open_files"],
            max_file_size_bytes=data["max_file_size_bytes"],
        )
        if data["policy_sha256"] != policy.sha256():
            raise ValueError("runtime sandbox policy digest does not match canonical policy")
        return policy


@dataclass(frozen=True)
class InstalledRuntimePlan:
    app_id: str
    app_version: str
    install_receipt_sha256: str
    manifest_sha256: str
    installed_tree_sha256: str
    install_path: str
    runtime_kind: str
    adapter: str
    entrypoint_target: str
    sandbox_entrypoint_path: str | None
    executable_tool: str | None
    runtime_argv: tuple[str, ...]
    requested_runtime_permissions: tuple[str, ...]
    network_mode: RuntimeNetworkMode
    data_mode: RuntimeDataMode
    policy: RuntimeSandboxPolicy
    status: RuntimeStatus
    notes: tuple[str, ...]
    launch_authority: bool = False
    schema_version: str = INSTALLED_RUNTIME_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != INSTALLED_RUNTIME_PLAN_SCHEMA_VERSION:
            raise ValueError(f"Unsupported installed runtime plan schema: {self.schema_version}")
        _string(self.app_id, "runtime app_id", maximum=64)
        _string(self.app_version, "runtime app_version", maximum=128)
        _sha256(self.install_receipt_sha256, "install_receipt_sha256")
        _sha256(self.manifest_sha256, "manifest_sha256")
        _sha256(self.installed_tree_sha256, "installed_tree_sha256")
        install = Path(self.install_path)
        if not install.is_absolute():
            raise ValueError("runtime install_path must be absolute")
        _string(self.runtime_kind, "runtime_kind", maximum=32)
        _string(self.adapter, "runtime adapter", maximum=64)
        _safe_relative(self.entrypoint_target, "runtime entrypoint_target")
        if self.sandbox_entrypoint_path is not None:
            if not self.sandbox_entrypoint_path.startswith("/app/"):
                raise ValueError("sandbox_entrypoint_path must live below /app")
        if len(set(self.requested_runtime_permissions)) != len(
            self.requested_runtime_permissions
        ):
            raise ValueError("runtime permissions must not contain duplicates")
        if tuple(sorted(self.requested_runtime_permissions)) != self.requested_runtime_permissions:
            raise ValueError("runtime permissions must be sorted")
        for permission in self.requested_runtime_permissions:
            if not _PERMISSION_RE.fullmatch(permission):
                raise ValueError(f"Invalid runtime permission: {permission}")
        if self.network_mode not in {"deny", "inherit"}:
            raise ValueError("runtime network_mode must be deny or inherit")
        if self.data_mode not in {"ephemeral", "persistent"}:
            raise ValueError("runtime data_mode must be ephemeral or persistent")
        if self.policy.network_mode != self.network_mode:
            raise ValueError("runtime policy network mode does not match plan")
        has_network = "runtime.network.inherit" in self.requested_runtime_permissions
        if has_network != (self.network_mode == "inherit"):
            raise ValueError("runtime network permission does not match network mode")
        has_data = "runtime.data.persist" in self.requested_runtime_permissions
        if has_data != (self.data_mode == "persistent"):
            raise ValueError("runtime data permission does not match data mode")
        if self.launch_authority is not False:
            raise ValueError("runtime plans do not themselves grant launch authority")
        if self.status == "ready_for_review":
            if self.runtime_kind not in {"node", "python"}:
                raise ValueError("v0.34 ready runtime plan must be node or python")
            if self.adapter not in {"node_direct_v034", "python_direct_v034"}:
                raise ValueError("v0.34 ready runtime plan has unsupported adapter")
            if self.executable_tool is None or not self.runtime_argv:
                raise ValueError("ready runtime plan requires an executable argv")
            if self.runtime_argv[0] != self.executable_tool:
                raise ValueError("runtime argv must begin with executable_tool")
            if self.sandbox_entrypoint_path is None:
                raise ValueError("ready runtime plan requires a sandbox entrypoint path")
            unsupported = set(self.requested_runtime_permissions) - _SUPPORTED_RUNTIME_PERMISSIONS
            if unsupported:
                raise ValueError("ready runtime plan contains unsupported permissions")
        else:
            if self.executable_tool is not None or self.runtime_argv:
                raise ValueError("unsupported runtime plan must not contain executable argv")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app_id": self.app_id,
            "app_version": self.app_version,
            "install_receipt_sha256": self.install_receipt_sha256,
            "manifest_sha256": self.manifest_sha256,
            "installed_tree_sha256": self.installed_tree_sha256,
            "install_path": self.install_path,
            "runtime_kind": self.runtime_kind,
            "adapter": self.adapter,
            "entrypoint_target": self.entrypoint_target,
            "sandbox_entrypoint_path": self.sandbox_entrypoint_path,
            "executable_tool": self.executable_tool,
            "runtime_argv": list(self.runtime_argv),
            "requested_runtime_permissions": list(self.requested_runtime_permissions),
            "network_mode": self.network_mode,
            "data_mode": self.data_mode,
            "policy": self.policy.to_dict(),
            "status": self.status,
            "notes": list(self.notes),
            "launch_authority": self.launch_authority,
        }

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["runtime_plan_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> InstalledRuntimePlan:
        data = _mapping(value, "installed runtime plan")
        expected = {
            "schema_version",
            "app_id",
            "app_version",
            "install_receipt_sha256",
            "manifest_sha256",
            "installed_tree_sha256",
            "install_path",
            "runtime_kind",
            "adapter",
            "entrypoint_target",
            "sandbox_entrypoint_path",
            "executable_tool",
            "runtime_argv",
            "requested_runtime_permissions",
            "network_mode",
            "data_mode",
            "policy",
            "status",
            "notes",
            "launch_authority",
            "runtime_plan_sha256",
        }
        if set(data) != expected:
            raise ValueError("installed runtime plan contains missing or unknown fields")
        argv_value = data["runtime_argv"]
        permissions_value = data["requested_runtime_permissions"]
        notes_value = data["notes"]
        if not isinstance(argv_value, list):
            raise ValueError("runtime_argv must be an array")
        if not isinstance(permissions_value, list):
            raise ValueError("requested_runtime_permissions must be an array")
        if not isinstance(notes_value, list):
            raise ValueError("runtime notes must be an array")
        sandbox_path = data["sandbox_entrypoint_path"]
        if sandbox_path is not None:
            sandbox_path = _string(sandbox_path, "sandbox_entrypoint_path", maximum=1024)
        executable = data["executable_tool"]
        if executable is not None:
            executable = _string(executable, "executable_tool", maximum=64)
        plan = cls(
            schema_version=data["schema_version"],
            app_id=_string(data["app_id"], "runtime app_id", maximum=64),
            app_version=_string(data["app_version"], "runtime app_version", maximum=128),
            install_receipt_sha256=_sha256(
                data["install_receipt_sha256"],
                "install_receipt_sha256",
            ),
            manifest_sha256=_sha256(data["manifest_sha256"], "manifest_sha256"),
            installed_tree_sha256=_sha256(
                data["installed_tree_sha256"],
                "installed_tree_sha256",
            ),
            install_path=_string(data["install_path"], "runtime install_path", maximum=4096),
            runtime_kind=_string(data["runtime_kind"], "runtime_kind", maximum=32),
            adapter=_string(data["adapter"], "runtime adapter", maximum=64),
            entrypoint_target=_safe_relative(
                data["entrypoint_target"],
                "runtime entrypoint_target",
            ),
            sandbox_entrypoint_path=sandbox_path,
            executable_tool=executable,
            runtime_argv=tuple(
                _string(item, "runtime argv item", maximum=2048) for item in argv_value
            ),
            requested_runtime_permissions=tuple(
                _string(item, "runtime permission", maximum=128)
                for item in permissions_value
            ),
            network_mode=data["network_mode"],
            data_mode=data["data_mode"],
            policy=RuntimeSandboxPolicy.from_dict(data["policy"]),
            status=data["status"],
            notes=tuple(_string(item, "runtime note", maximum=512) for item in notes_value),
            launch_authority=data["launch_authority"],
        )
        if data["runtime_plan_sha256"] != plan.sha256():
            raise ValueError("installed runtime plan digest does not match canonical plan")
        return plan


@dataclass(frozen=True)
class InstalledRuntimeReview:
    runtime_plan_sha256: str
    app_id: str
    app_version: str
    install_receipt_sha256: str
    installed_tree_sha256: str
    runtime_kind: str
    adapter: str
    entrypoint_target: str
    runtime_argv: tuple[str, ...]
    requested_runtime_permissions: tuple[str, ...]
    network_mode: RuntimeNetworkMode
    data_mode: RuntimeDataMode
    policy_sha256: str
    status: RuntimeStatus
    launch_authority: bool
    schema_version: str = INSTALLED_RUNTIME_REVIEW_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["runtime_argv"] = list(self.runtime_argv)
        result["requested_runtime_permissions"] = list(self.requested_runtime_permissions)
        return result


@dataclass(frozen=True)
class _VerifiedInstall:
    receipt: AppInstallReceipt
    manifest: AppManifest
    install_root: Path
    install_path: Path
    payload_path: Path


def _verify_install(
    install_receipt_value: Any,
    *,
    install_root: Path,
) -> _VerifiedInstall:
    receipt = AppInstallReceipt.from_dict(install_receipt_value)
    root = install_root.expanduser()
    if root.is_symlink():
        raise ValueError("runtime install root must not be a symlink")
    root = root.resolve(strict=True)
    install = _path_under(root, Path(receipt.install_path), "runtime install path")
    if not install.is_dir():
        raise ValueError("runtime install path must be a directory")

    tree_sha, _, _ = snapshot_installed_tree(install)
    if tree_sha != receipt.installed_tree_sha256:
        raise ValueError("installed tree changed since install receipt")

    payload = _path_under(install, install / "payload", "installed payload")
    if not payload.is_dir():
        raise ValueError("installed payload is unavailable")
    payload_sha, artifact_count, total_bytes = snapshot_installed_tree(payload)
    if payload_sha != receipt.installed_payload_sha256:
        raise ValueError("installed payload changed since install receipt")
    if artifact_count != receipt.artifact_count or total_bytes != receipt.total_bytes:
        raise ValueError("installed payload totals changed since install receipt")

    manifest_path = install / ".phios" / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("installed manifest metadata is unavailable or unsafe")
    manifest = AppManifest.from_json(manifest_path.read_text(encoding="utf-8"))
    if manifest.sha256() != receipt.manifest_sha256:
        raise ValueError("installed manifest does not match install receipt")
    if manifest.app_id != receipt.app_id or manifest.version != receipt.app_version:
        raise ValueError("installed manifest identity does not match install receipt")

    return _VerifiedInstall(
        receipt=receipt,
        manifest=manifest,
        install_root=root,
        install_path=install,
        payload_path=payload,
    )


def _entrypoint_file(payload: Path, target: str) -> Path | None:
    candidate = payload / Path(*PurePosixPath(target).parts)
    if candidate.is_symlink():
        return None
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None
    resolved_payload = payload.resolve(strict=True)
    if resolved_payload != resolved and resolved_payload not in resolved.parents:
        return None
    return resolved if resolved.is_file() else None


def plan_installed_runtime(
    install_receipt_value: Any,
    *,
    install_root: Path,
    wall_clock_seconds: int = 300,
    cpu_seconds: int = 300,
    address_space_bytes: int = 2 * 1024 * 1024 * 1024,
    max_open_files: int = 512,
    max_file_size_bytes: int = 128 * 1024 * 1024,
) -> InstalledRuntimePlan:
    verified = _verify_install(install_receipt_value, install_root=install_root)
    manifest = verified.manifest
    permissions = tuple(sorted(manifest.permissions))
    unsupported_permissions = sorted(set(permissions) - _SUPPORTED_RUNTIME_PERMISSIONS)
    network_mode: RuntimeNetworkMode = (
        "inherit" if "runtime.network.inherit" in permissions else "deny"
    )
    data_mode: RuntimeDataMode = (
        "persistent" if "runtime.data.persist" in permissions else "ephemeral"
    )
    policy = RuntimeSandboxPolicy(
        network_mode=network_mode,
        wall_clock_seconds=wall_clock_seconds,
        cpu_seconds=cpu_seconds,
        address_space_bytes=address_space_bytes,
        max_open_files=max_open_files,
        max_file_size_bytes=max_file_size_bytes,
    )

    target = manifest.entrypoint.target
    runtime_kind = manifest.entrypoint.runtime
    adapter: str
    status: RuntimeStatus
    executable: str | None = None
    sandbox_target: str | None = None
    argv: tuple[str, ...] = ()
    notes: list[str] = []

    entrypoint = _entrypoint_file(verified.payload_path, target)

    if unsupported_permissions:
        adapter = "unsupported_permissions_v034"
        status = "unsupported_permissions"
        notes.append(
            "v0.34 supports only runtime.network.inherit and runtime.data.persist permissions"
        )
    elif runtime_kind == "node":
        if entrypoint is None or PurePosixPath(target).suffix not in {".js", ".mjs", ".cjs"}:
            adapter = "unsupported_node_entrypoint_v034"
            status = "unsupported_entrypoint"
            notes.append(
                "node direct runtime requires an installed .js, .mjs, or .cjs manifest target"
            )
        else:
            adapter = "node_direct_v034"
            status = "ready_for_review"
            executable = "node"
            sandbox_target = f"/app/{target}"
            argv = ("node", sandbox_target)
    elif runtime_kind == "python":
        if entrypoint is None or PurePosixPath(target).suffix != ".py":
            adapter = "unsupported_python_entrypoint_v034"
            status = "unsupported_entrypoint"
            notes.append("python direct runtime requires an installed .py manifest target")
        else:
            adapter = "python_direct_v034"
            status = "ready_for_review"
            executable = "python3"
            sandbox_target = f"/app/{target}"
            argv = ("python3", sandbox_target)
    elif runtime_kind == "native":
        adapter = "unsupported_native_mode_v034"
        status = "unsupported_runtime"
        notes.append(
            "v0.33 install artifacts do not preserve executable mode bits; native launch is deferred"
        )
    elif runtime_kind == "static_web":
        adapter = "unsupported_static_web_v034"
        status = "unsupported_runtime"
        notes.append(
            "static web launch requires a separately governed browser/server adapter"
        )
    elif runtime_kind == "local_http":
        adapter = "unsupported_local_http_v034"
        status = "unsupported_runtime"
        notes.append(
            "local_http describes a loopback service target, not an installed executable"
        )
    else:
        adapter = "unsupported_runtime_v034"
        status = "unsupported_runtime"
        notes.append("runtime kind is not supported by the v0.34 direct-process adapter")

    notes.append("installed payload is mounted read-only at /app")
    if data_mode == "persistent":
        notes.append("persistent app data requires a separately writable /phios/app-data mount")
    else:
        notes.append("no persistent writable app-data mount is requested")
    if network_mode == "deny":
        notes.append("runtime requests a separate network namespace with host network denied")
    else:
        notes.append("runtime requests explicit host-network inheritance")

    return InstalledRuntimePlan(
        app_id=manifest.app_id,
        app_version=manifest.version,
        install_receipt_sha256=verified.receipt.sha256(),
        manifest_sha256=manifest.sha256(),
        installed_tree_sha256=verified.receipt.installed_tree_sha256,
        install_path=str(verified.install_path),
        runtime_kind=runtime_kind,
        adapter=adapter,
        entrypoint_target=target,
        sandbox_entrypoint_path=sandbox_target,
        executable_tool=executable,
        runtime_argv=argv,
        requested_runtime_permissions=permissions,
        network_mode=network_mode,
        data_mode=data_mode,
        policy=policy,
        status=status,
        notes=tuple(notes),
        launch_authority=False,
    )


def review_installed_runtime(value: Any) -> InstalledRuntimeReview:
    plan = InstalledRuntimePlan.from_dict(value)
    return InstalledRuntimeReview(
        runtime_plan_sha256=plan.sha256(),
        app_id=plan.app_id,
        app_version=plan.app_version,
        install_receipt_sha256=plan.install_receipt_sha256,
        installed_tree_sha256=plan.installed_tree_sha256,
        runtime_kind=plan.runtime_kind,
        adapter=plan.adapter,
        entrypoint_target=plan.entrypoint_target,
        runtime_argv=plan.runtime_argv,
        requested_runtime_permissions=plan.requested_runtime_permissions,
        network_mode=plan.network_mode,
        data_mode=plan.data_mode,
        policy_sha256=plan.policy.sha256(),
        status=plan.status,
        launch_authority=plan.launch_authority,
    )


@dataclass(frozen=True)
class RuntimeLaunchRequest:
    plan: InstalledRuntimePlan
    install_receipt: AppInstallReceipt
    approved_runtime_plan_sha256: str
    approved_runtime_permissions: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.plan.status != "ready_for_review":
            raise ValueError("only ready_for_review runtime plans are executable")
        if self.approved_runtime_plan_sha256 != self.plan.sha256():
            raise ValueError("Approved runtime-plan SHA-256 does not match canonical plan")
        if self.install_receipt.sha256() != self.plan.install_receipt_sha256:
            raise ValueError("install receipt does not match runtime plan")
        if self.install_receipt.installed_tree_sha256 != self.plan.installed_tree_sha256:
            raise ValueError("install receipt tree does not match runtime plan")
        approved = tuple(sorted(self.approved_runtime_permissions))
        if approved != self.approved_runtime_permissions:
            raise ValueError("approved runtime permissions must be sorted")
        if len(set(approved)) != len(approved):
            raise ValueError("approved runtime permissions must not contain duplicates")
        if approved != self.plan.requested_runtime_permissions:
            raise ValueError(
                "Approved runtime permissions must exactly match the reviewed runtime plan"
            )

    @classmethod
    def from_payloads(
        cls,
        plan_value: Any,
        install_receipt_value: Any,
        *,
        approved_runtime_plan_sha256: str,
        approved_runtime_permissions: tuple[str, ...],
    ) -> RuntimeLaunchRequest:
        return cls(
            plan=InstalledRuntimePlan.from_dict(plan_value),
            install_receipt=AppInstallReceipt.from_dict(install_receipt_value),
            approved_runtime_plan_sha256=_sha256(
                approved_runtime_plan_sha256,
                "approved_runtime_plan_sha256",
            ),
            approved_runtime_permissions=tuple(sorted(approved_runtime_permissions)),
        )


@dataclass(frozen=True)
class RuntimeControlEvidence:
    mount_namespace_enforced: bool
    user_namespace_enforced: bool
    pid_namespace_enforced: bool
    ipc_namespace_enforced: bool
    uts_namespace_enforced: bool
    private_proc: bool
    private_dev: bool
    private_tmp: bool
    private_home: bool
    installed_payload_read_only: bool
    persistent_data_writable_mount: bool
    host_system_roots_read_only: bool
    network_namespace_enforced: bool
    host_network_inherited: bool
    wall_clock_timeout_enforced: bool
    cpu_rlimit_enforced: bool
    address_space_rlimit_enforced: bool
    open_files_rlimit_enforced: bool
    file_size_rlimit_enforced: bool
    seccomp_enforced: bool
    network_allowlist_enforced: bool
    parent_death_enforced: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Any) -> RuntimeControlEvidence:
        data = _mapping(value, "runtime control evidence")
        expected = set(cls.__dataclass_fields__)
        if set(data) != expected:
            raise ValueError("runtime control evidence contains missing or unknown fields")
        if any(not isinstance(data[key], bool) for key in expected):
            raise ValueError("runtime control evidence fields must be boolean")
        return cls(**data)


class RuntimeProcessRunner(Protocol):
    policy: RuntimeSandboxPolicy

    def preflight(self) -> SandboxBackendIdentity: ...

    def probe_tool(self, executable_tool: str) -> ToolIdentity: ...

    def run(self, plan: InstalledRuntimePlan) -> ProcessResult: ...

    def control_evidence(self) -> RuntimeControlEvidence: ...


class BubblewrapRuntimeRunner:
    def __init__(
        self,
        policy: RuntimeSandboxPolicy,
        *,
        payload_root: Path,
        data_path: Path | None,
        bwrap_path: str | None = None,
        prlimit_path: str | None = None,
    ) -> None:
        self.policy = policy
        self._subprocess = SubprocessBuildRunner()
        if payload_root.is_symlink():
            raise ValueError("runtime payload root must not be a symlink")
        self.payload_root = payload_root.resolve(strict=True)
        if not self.payload_root.is_dir():
            raise ValueError("runtime payload root must be a directory")
        self.data_path: Path | None
        if data_path is not None:
            if data_path.is_symlink():
                raise ValueError("runtime data path must not be a symlink")
            self.data_path = data_path.resolve(strict=True)
            if not self.data_path.is_dir():
                raise ValueError("runtime data path must be a directory")
        else:
            self.data_path = None
        self.bwrap_path = bwrap_path
        self.prlimit_path = prlimit_path
        self._backend_identity: SandboxBackendIdentity | None = None
        self._resolved_tool_dirs: set[str] = set()

    @staticmethod
    def _path_allowed(path: Path) -> bool:
        resolved = path.resolve()
        for root_text in _SANDBOX_SYSTEM_ROOTS:
            root = Path(root_text)
            try:
                resolved.relative_to(root)
            except ValueError:
                continue
            return True
        return False

    @staticmethod
    def _system_bind_args() -> list[str]:
        args: list[str] = []
        for root in _SANDBOX_SYSTEM_ROOTS:
            args.extend(("--ro-bind-try", root, root))
        for path in _SANDBOX_ETC_PATHS:
            args.extend(("--ro-bind-try", path, path))
        return args

    def _resolve_backend_tools(self) -> tuple[str, str]:
        bwrap = self.bwrap_path or shutil.which("bwrap")
        if not bwrap:
            raise ValueError("Bubblewrap runtime backend is unavailable: bwrap was not found")
        prlimit = self.prlimit_path or shutil.which("prlimit")
        if not prlimit:
            raise ValueError("Bubblewrap runtime backend requires prlimit")
        if not Path(bwrap).is_absolute() or not Path(prlimit).is_absolute():
            raise ValueError("Runtime sandbox backend executables must resolve to absolute paths")
        if not self._path_allowed(Path(prlimit)):
            raise ValueError("prlimit is outside runtime sandbox read-only system roots")
        return bwrap, prlimit

    def _sandbox_path(self, current_tool: Path) -> str:
        directories = {
            "/usr/local/sbin",
            "/usr/local/bin",
            "/usr/sbin",
            "/usr/bin",
            "/sbin",
            "/bin",
            str(current_tool.parent),
            *self._resolved_tool_dirs,
        }
        return ":".join(sorted(directories))

    def command_for(
        self,
        *,
        executable_path: str,
        argv_tail: tuple[str, ...],
    ) -> tuple[str, ...]:
        bwrap, prlimit = self._resolve_backend_tools()
        executable = Path(executable_path).resolve()
        if not self._path_allowed(executable):
            raise ValueError(
                f"Runtime executable is outside sandbox read-only system roots: {executable}"
            )

        args: list[str] = [
            bwrap,
            "--die-with-parent",
            "--new-session",
            "--unshare-user",
            "--unshare-ipc",
            "--unshare-pid",
            "--unshare-uts",
        ]
        if self.policy.network_mode == "deny":
            args.append("--unshare-net")
        args.extend(
            [
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--tmpfs",
                "/tmp",
                "--dir",
                "/home",
                "--dir",
                "/home/phios",
            ]
        )
        args.extend(self._system_bind_args())
        if self.data_path is not None:
            args.extend(
                [
                    "--dir",
                    "/phios",
                    "--bind",
                    str(self.data_path),
                    "/phios/app-data",
                ]
            )
        args.extend(
            [
                "--ro-bind",
                str(self.payload_root),
                "/app",
                "--chdir",
                "/app",
                "--clearenv",
                "--setenv",
                "HOME",
                "/home/phios",
                "--setenv",
                "TMPDIR",
                "/tmp",
                "--setenv",
                "TMP",
                "/tmp",
                "--setenv",
                "TEMP",
                "/tmp",
                "--setenv",
                "PHIOS_RUNTIME_EXECUTION",
                "1",
                "--setenv",
                "PHIOS_APP_ROOT",
                "/app",
                "--setenv",
                "PATH",
                self._sandbox_path(executable),
            ]
        )
        if self.data_path is not None:
            args.extend(("--setenv", "PHIOS_APP_DATA", "/phios/app-data"))
        args.extend(
            [
                prlimit,
                f"--cpu={self.policy.cpu_seconds}",
                f"--as={self.policy.address_space_bytes}",
                f"--nofile={self.policy.max_open_files}",
                f"--fsize={self.policy.max_file_size_bytes}",
                "--",
                str(executable),
                *argv_tail,
            ]
        )
        return tuple(args)

    def preflight(self) -> SandboxBackendIdentity:
        if platform.system() != "Linux":
            raise ValueError("v0.34 Bubblewrap runtime is Linux-only")
        bwrap, _ = self._resolve_backend_tools()
        try:
            version_result = subprocess.run(
                (bwrap, "--version"),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError("Bubblewrap runtime version probe failed") from exc
        if version_result.returncode != 0:
            raise ValueError("Bubblewrap runtime version probe returned nonzero")

        raw_version = version_result.stdout or version_result.stderr
        lines = raw_version.decode("utf-8", errors="replace").strip().splitlines()
        version_text = lines[0][:512] if lines else "unknown"
        if not _SAFE_VERSION_RE.fullmatch(version_text):
            version_text = "unprintable-version-output"

        true_path = shutil.which("true")
        if not true_path or not self._path_allowed(Path(true_path)):
            raise ValueError("Runtime sandbox preflight requires a system true executable")
        command = self.command_for(executable_path=true_path, argv_tail=())
        try:
            result = subprocess.run(
                command,
                cwd=self.payload_root,
                env={"PATH": os.environ.get("PATH", "")},
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError("Bubblewrap runtime namespace preflight failed") from exc
        if result.returncode != 0:
            raise ValueError(
                "Bubblewrap runtime namespace preflight returned nonzero; "
                "user namespaces or required mounts may be unavailable"
            )

        combined = hashlib.sha256()
        combined.update(version_result.stdout)
        combined.update(version_result.stderr)
        identity = SandboxBackendIdentity(
            backend="bubblewrap",
            executable_path=str(Path(bwrap).resolve()),
            version=version_text,
            version_output_sha256=combined.hexdigest(),
            platform_system=platform.system(),
            platform_machine=platform.machine(),
        )
        self._backend_identity = identity
        return identity

    def probe_tool(self, executable_tool: str) -> ToolIdentity:
        if self._backend_identity is None:
            raise ValueError("Runtime sandbox runner must pass preflight before tool probe")
        argv = (executable_tool, "--version")
        identity = self._subprocess.probe(
            logical_tool=executable_tool,
            executable_tool=executable_tool,
            argv=argv,
            cwd=self.payload_root,
            env={"PATH": os.environ.get("PATH", "")},
            timeout_seconds=30,
        )
        resolved = Path(identity.executable_path).resolve()
        if not self._path_allowed(resolved):
            raise ValueError("Runtime executable is outside sandbox system roots")
        self._resolved_tool_dirs.add(str(resolved.parent))
        return identity

    def run(self, plan: InstalledRuntimePlan) -> ProcessResult:
        if self._backend_identity is None:
            raise ValueError("Runtime sandbox runner must pass preflight before execution")
        if plan.executable_tool is None:
            raise ValueError("Runtime plan has no executable tool")
        resolved_tool = shutil.which(plan.executable_tool, path=os.environ.get("PATH"))
        if not resolved_tool:
            raise ValueError(f"Required runtime executable is unavailable: {plan.executable_tool}")
        resolved_path = Path(resolved_tool).resolve()
        if not self._path_allowed(resolved_path):
            raise ValueError("Required runtime executable is outside sandbox system roots")
        self._resolved_tool_dirs.add(str(resolved_path.parent))
        command = self.command_for(
            executable_path=str(resolved_path),
            argv_tail=plan.runtime_argv[1:],
        )
        _, result = self._subprocess._execute(
            executable_tool=command[0],
            argv=command,
            cwd=self.payload_root,
            env={"PATH": os.environ.get("PATH", "")},
            timeout_seconds=plan.policy.wall_clock_seconds,
            preview_limit=0,
        )
        return result

    def control_evidence(self) -> RuntimeControlEvidence:
        return RuntimeControlEvidence(
            mount_namespace_enforced=True,
            user_namespace_enforced=True,
            pid_namespace_enforced=True,
            ipc_namespace_enforced=True,
            uts_namespace_enforced=True,
            private_proc=True,
            private_dev=True,
            private_tmp=True,
            private_home=True,
            installed_payload_read_only=True,
            persistent_data_writable_mount=self.data_path is not None,
            host_system_roots_read_only=True,
            network_namespace_enforced=self.policy.network_mode == "deny",
            host_network_inherited=self.policy.network_mode == "inherit",
            wall_clock_timeout_enforced=True,
            cpu_rlimit_enforced=True,
            address_space_rlimit_enforced=True,
            open_files_rlimit_enforced=True,
            file_size_rlimit_enforced=True,
            seccomp_enforced=False,
            network_allowlist_enforced=False,
            parent_death_enforced=True,
        )


@dataclass(frozen=True)
class RuntimeLaunchReceipt:
    receipt_id: str
    timestamp_utc: str
    app_id: str
    app_version: str
    runtime_plan_sha256: str
    install_receipt_sha256: str
    installed_tree_sha256: str
    manifest_sha256: str
    runtime_kind: str
    adapter: str
    entrypoint_target: str
    approved_runtime_permissions: tuple[str, ...]
    network_mode: RuntimeNetworkMode
    data_mode: RuntimeDataMode
    policy: RuntimeSandboxPolicy
    backend_identity: SandboxBackendIdentity
    controls: RuntimeControlEvidence
    tool_identity: ToolIdentity
    exit_code: int
    timed_out: bool
    duration_ms: int
    stdout_byte_count: int
    stdout_sha256: str
    stderr_byte_count: int
    stderr_sha256: str
    status: str
    failure_reason: str | None
    schema_version: str = RUNTIME_LAUNCH_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_LAUNCH_RECEIPT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported runtime launch receipt schema: {self.schema_version}")
        try:
            uuid.UUID(self.receipt_id)
        except ValueError as exc:
            raise ValueError("runtime receipt_id must be a UUID") from exc
        parsed = datetime.fromisoformat(self.timestamp_utc)
        if parsed.tzinfo is None:
            raise ValueError("runtime receipt timestamp must include a timezone")
        for value, label in (
            (self.runtime_plan_sha256, "runtime_plan_sha256"),
            (self.install_receipt_sha256, "install_receipt_sha256"),
            (self.installed_tree_sha256, "installed_tree_sha256"),
            (self.manifest_sha256, "manifest_sha256"),
            (self.stdout_sha256, "stdout_sha256"),
            (self.stderr_sha256, "stderr_sha256"),
        ):
            _sha256(value, label)
        if self.status not in {"exited_success", "exited_failure", "timed_out"}:
            raise ValueError("unsupported runtime launch status")
        if self.network_mode == "deny":
            if not self.controls.network_namespace_enforced:
                raise ValueError("network-denied runtime receipt requires network namespace evidence")
            if self.controls.host_network_inherited:
                raise ValueError("network-denied runtime receipt cannot inherit host network")
        else:
            if not self.controls.host_network_inherited:
                raise ValueError("network-inherit runtime receipt requires host-network evidence")
        if not self.controls.installed_payload_read_only:
            raise ValueError("runtime receipt requires read-only installed payload evidence")
        if self.data_mode == "persistent" and not self.controls.persistent_data_writable_mount:
            raise ValueError("persistent runtime receipt requires writable app-data mount evidence")
        if self.data_mode == "ephemeral" and self.controls.persistent_data_writable_mount:
            raise ValueError("ephemeral runtime receipt cannot contain persistent app-data mount")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "timestamp_utc": self.timestamp_utc,
            "app_id": self.app_id,
            "app_version": self.app_version,
            "runtime_plan_sha256": self.runtime_plan_sha256,
            "install_receipt_sha256": self.install_receipt_sha256,
            "installed_tree_sha256": self.installed_tree_sha256,
            "manifest_sha256": self.manifest_sha256,
            "runtime_kind": self.runtime_kind,
            "adapter": self.adapter,
            "entrypoint_target": self.entrypoint_target,
            "approved_runtime_permissions": list(self.approved_runtime_permissions),
            "network_mode": self.network_mode,
            "data_mode": self.data_mode,
            "policy": self.policy.to_dict(),
            "backend_identity": self.backend_identity.to_dict(),
            "controls": self.controls.to_dict(),
            "tool_identity": self.tool_identity.to_dict(),
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "duration_ms": self.duration_ms,
            "stdout_byte_count": self.stdout_byte_count,
            "stdout_sha256": self.stdout_sha256,
            "stderr_byte_count": self.stderr_byte_count,
            "stderr_sha256": self.stderr_sha256,
            "status": self.status,
            "failure_reason": self.failure_reason,
        }

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["runtime_receipt_sha256"] = self.sha256()
        return result


@dataclass(frozen=True)
class RuntimeLaunchResult:
    receipt: RuntimeLaunchReceipt
    receipt_path: str
    receipt_persisted: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt": self.receipt.to_dict(),
            "receipt_path": self.receipt_path,
            "receipt_persisted": self.receipt_persisted,
        }


RuntimeRunnerFactory = Callable[
    [RuntimeSandboxPolicy, Path, Path | None],
    RuntimeProcessRunner,
]


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(_canonical_json(payload) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


class InstalledRuntimeService:
    def __init__(
        self,
        *,
        runner_factory: RuntimeRunnerFactory | None = None,
    ) -> None:
        self.runner_factory = runner_factory or self._default_runner

    @staticmethod
    def _default_runner(
        policy: RuntimeSandboxPolicy,
        payload_root: Path,
        data_path: Path | None,
    ) -> RuntimeProcessRunner:
        return BubblewrapRuntimeRunner(
            policy,
            payload_root=payload_root,
            data_path=data_path,
        )

    def launch(
        self,
        request: RuntimeLaunchRequest,
        *,
        install_root: Path,
        data_root: Path,
        receipt_root: Path,
    ) -> RuntimeLaunchResult:
        plan = request.plan
        verified = _verify_install(
            request.install_receipt.to_dict(),
            install_root=install_root,
        )
        if verified.receipt.sha256() != plan.install_receipt_sha256:
            raise ValueError("current install receipt does not match runtime plan")
        if verified.receipt.installed_tree_sha256 != plan.installed_tree_sha256:
            raise ValueError("current installed tree does not match runtime plan")
        if verified.manifest.sha256() != plan.manifest_sha256:
            raise ValueError("current installed manifest does not match runtime plan")
        if verified.manifest.entrypoint.runtime != plan.runtime_kind:
            raise ValueError("installed runtime kind changed after runtime-plan review")
        if verified.manifest.entrypoint.target != plan.entrypoint_target:
            raise ValueError("installed entrypoint changed after runtime-plan review")
        entrypoint = _entrypoint_file(verified.payload_path, plan.entrypoint_target)
        if entrypoint is None:
            raise ValueError("reviewed runtime entrypoint is unavailable or unsafe")

        data_path: Path | None = None
        if plan.data_mode == "persistent":
            root = data_root.expanduser()
            if root.is_symlink():
                raise ValueError("runtime data root must not be a symlink")
            root.mkdir(parents=True, exist_ok=True)
            root = root.resolve(strict=True)
            candidate = root / plan.app_id
            if candidate.exists() and candidate.is_symlink():
                raise ValueError("runtime app-data path must not be a symlink")
            candidate.mkdir(parents=True, exist_ok=True)
            data_path = _path_under(root, candidate, "runtime app-data path")

        runner = self.runner_factory(plan.policy, verified.payload_path, data_path)
        backend = runner.preflight()
        assert plan.executable_tool is not None
        tool = runner.probe_tool(plan.executable_tool)
        process = runner.run(plan)
        controls = runner.control_evidence()

        if plan.network_mode == "deny":
            if not controls.network_namespace_enforced or controls.host_network_inherited:
                raise ValueError("runtime runner did not enforce reviewed network denial")
        else:
            if not controls.host_network_inherited:
                raise ValueError("runtime runner did not provide reviewed host-network inheritance")
        if not controls.installed_payload_read_only:
            raise ValueError("runtime runner did not keep installed payload read-only")
        if controls.persistent_data_writable_mount != (plan.data_mode == "persistent"):
            raise ValueError("runtime runner data mount evidence does not match reviewed plan")

        if process.timed_out:
            status = "timed_out"
            failure_reason = "runtime exceeded reviewed wall-clock limit"
        elif process.exit_code == 0:
            status = "exited_success"
            failure_reason = None
        else:
            status = "exited_failure"
            failure_reason = f"runtime exited with code {process.exit_code}"

        receipt = RuntimeLaunchReceipt(
            receipt_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(UTC).isoformat(),
            app_id=plan.app_id,
            app_version=plan.app_version,
            runtime_plan_sha256=plan.sha256(),
            install_receipt_sha256=plan.install_receipt_sha256,
            installed_tree_sha256=plan.installed_tree_sha256,
            manifest_sha256=plan.manifest_sha256,
            runtime_kind=plan.runtime_kind,
            adapter=plan.adapter,
            entrypoint_target=plan.entrypoint_target,
            approved_runtime_permissions=request.approved_runtime_permissions,
            network_mode=plan.network_mode,
            data_mode=plan.data_mode,
            policy=plan.policy,
            backend_identity=backend,
            controls=controls,
            tool_identity=tool,
            exit_code=process.exit_code,
            timed_out=process.timed_out,
            duration_ms=process.duration_ms,
            stdout_byte_count=process.stdout.byte_count,
            stdout_sha256=process.stdout.sha256,
            stderr_byte_count=process.stderr.byte_count,
            stderr_sha256=process.stderr.sha256,
            status=status,
            failure_reason=failure_reason,
        )

        receipts = receipt_root.expanduser()
        if receipts.is_symlink():
            raise ValueError("runtime receipt root must not be a symlink")
        receipts.mkdir(parents=True, exist_ok=True)
        receipts = receipts.resolve(strict=True)
        receipt_path = receipts / f"runtime-{receipt.receipt_id}.json"
        _write_json_atomic(receipt_path, receipt.to_dict())
        return RuntimeLaunchResult(
            receipt=receipt,
            receipt_path=str(receipt_path),
            receipt_persisted=True,
        )
