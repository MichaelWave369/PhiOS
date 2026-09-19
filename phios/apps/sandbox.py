from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from .build_execution import (
    BuildExecutionReceipt,
    BuildExecutionRequest,
    BuildExecutionService,
    BuildProcessRunner,
    ProcessResult,
    SubprocessBuildRunner,
    ToolIdentity,
)
from .build_plan import BuildStep

BUILD_SANDBOX_POLICY_SCHEMA_VERSION = "phios.build_sandbox_policy.v0.1"
BUILD_SANDBOX_RECEIPT_SCHEMA_VERSION = "phios.build_sandbox_receipt.v0.1"

NetworkMode = Literal["deny", "inherit"]

_MIN_MEMORY_BYTES = 128 * 1024 * 1024
_MAX_MEMORY_BYTES = 64 * 1024 * 1024 * 1024
_MIN_FILE_SIZE_BYTES = 1 * 1024 * 1024
_MAX_FILE_SIZE_BYTES = 4 * 1024 * 1024 * 1024
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
_SAFE_VERSION_RE = re.compile(r"^[\x20-\x7e]{1,512}$")


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, Any], value)


def _int(value: Any, label: str, *, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True)
class BuildSandboxPolicy:
    network_mode: NetworkMode = "deny"
    wall_clock_seconds: int = 900
    cpu_seconds: int = 600
    address_space_bytes: int = 8 * 1024 * 1024 * 1024
    max_open_files: int = 1024
    max_file_size_bytes: int = 512 * 1024 * 1024
    backend: str = "bubblewrap"
    schema_version: str = BUILD_SANDBOX_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != BUILD_SANDBOX_POLICY_SCHEMA_VERSION:
            raise ValueError(f"Unsupported sandbox policy schema: {self.schema_version}")
        if self.backend != "bubblewrap":
            raise ValueError("v0.30 supports only the bubblewrap backend")
        if self.network_mode not in {"deny", "inherit"}:
            raise ValueError("network_mode must be deny or inherit")
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
        payload = json.dumps(
            self.body_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["policy_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> BuildSandboxPolicy:
        data = _mapping(value, "sandbox policy")
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
            raise ValueError("sandbox policy contains missing or unknown fields")
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
            raise ValueError("sandbox policy digest does not match canonical policy")
        return policy


@dataclass(frozen=True)
class SandboxBackendIdentity:
    backend: str
    executable_path: str
    version: str
    version_output_sha256: str
    platform_system: str
    platform_machine: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SandboxControlEvidence:
    mount_namespace_enforced: bool
    user_namespace_enforced: bool
    pid_namespace_enforced: bool
    ipc_namespace_enforced: bool
    uts_namespace_enforced: bool
    cgroup_namespace_requested: bool
    private_proc: bool
    private_dev: bool
    private_tmp: bool
    private_home: bool
    workspace_only_writable_mount: bool
    host_system_roots_read_only: bool
    network_namespace_enforced: bool
    host_network_inherited: bool
    wall_clock_timeout_enforced: bool
    cpu_rlimit_enforced: bool
    address_space_rlimit_enforced: bool
    open_files_rlimit_enforced: bool
    file_size_rlimit_enforced: bool
    process_count_limit_enforced: bool
    seccomp_enforced: bool
    network_allowlist_enforced: bool
    parent_death_enforced: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BuildSandboxReceipt:
    sandbox_receipt_id: str
    timestamp_utc: str
    execution_id: str
    build_execution_receipt_sha256: str
    app_id: str
    commit_sha: str
    plan_sha256: str
    source_snapshot_sha256: str
    policy: BuildSandboxPolicy
    backend_identity: SandboxBackendIdentity
    controls: SandboxControlEvidence
    containment_level: str
    build_status: str
    schema_version: str = BUILD_SANDBOX_RECEIPT_SCHEMA_VERSION

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sandbox_receipt_id": self.sandbox_receipt_id,
            "timestamp_utc": self.timestamp_utc,
            "execution_id": self.execution_id,
            "build_execution_receipt_sha256": self.build_execution_receipt_sha256,
            "app_id": self.app_id,
            "commit_sha": self.commit_sha,
            "plan_sha256": self.plan_sha256,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "policy": self.policy.to_dict(),
            "backend_identity": self.backend_identity.to_dict(),
            "controls": self.controls.to_dict(),
            "containment_level": self.containment_level,
            "build_status": self.build_status,
        }

    def sha256(self) -> str:
        payload = json.dumps(
            self.body_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["sandbox_receipt_sha256"] = self.sha256()
        return result


@dataclass(frozen=True)
class SandboxedBuildExecutionResult:
    execution: BuildExecutionReceipt
    sandbox: BuildSandboxReceipt
    sandbox_receipt_path: str | None
    sandbox_receipt_persisted: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution": self.execution.to_dict(),
            "sandbox": self.sandbox.to_dict(),
            "sandbox_receipt_path": self.sandbox_receipt_path,
            "sandbox_receipt_persisted": self.sandbox_receipt_persisted,
        }


class SandboxBuildRunner(BuildProcessRunner, Protocol):
    policy: BuildSandboxPolicy
    isolation_mode: str
    network_sandbox_enforced: bool

    def preflight(self) -> SandboxBackendIdentity: ...

    def control_evidence(self) -> SandboxControlEvidence: ...


class BubblewrapSandboxRunner(SubprocessBuildRunner):
    isolation_mode = "bubblewrap_linux_namespaces"

    def __init__(
        self,
        policy: BuildSandboxPolicy,
        *,
        bwrap_path: str | None = None,
        prlimit_path: str | None = None,
    ) -> None:
        self.policy = policy
        self.bwrap_path = bwrap_path
        self.prlimit_path = prlimit_path
        self.network_sandbox_enforced = policy.network_mode == "deny"
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
            raise ValueError("Bubblewrap backend is unavailable: bwrap was not found")
        prlimit = self.prlimit_path or shutil.which("prlimit")
        if not prlimit:
            raise ValueError("Bubblewrap backend requires prlimit for resource limits")
        if not Path(bwrap).is_absolute() or not Path(prlimit).is_absolute():
            raise ValueError("Sandbox backend executables must resolve to absolute paths")
        if not self._path_allowed(Path(prlimit)):
            raise ValueError("prlimit executable is outside the sandbox read-only system roots")
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
        source_root: Path,
        cwd: Path,
    ) -> tuple[str, ...]:
        bwrap, prlimit = self._resolve_backend_tools()
        executable = Path(executable_path).resolve()
        if not self._path_allowed(executable):
            raise ValueError(
                f"Build tool is outside sandbox read-only system roots: {executable}"
            )

        source = source_root.resolve()
        working = cwd.resolve()
        try:
            relative_cwd = working.relative_to(source)
        except ValueError as exc:
            raise ValueError("Sandbox working directory escaped execution source") from exc

        sandbox_cwd = "/workspace"
        if relative_cwd.parts:
            sandbox_cwd += "/" + relative_cwd.as_posix()

        args: list[str] = [
            bwrap,
            "--die-with-parent",
            "--new-session",
            "--unshare-all",
        ]
        if self.policy.network_mode == "inherit":
            args.append("--share-net")

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
        args.extend(
            [
                "--bind",
                str(source),
                "/workspace",
                "--chdir",
                sandbox_cwd,
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
                "PHIOS_BUILD_EXECUTION",
                "1",
                "--setenv",
                "PHIOS_BUILD_SANDBOX",
                "bubblewrap",
                "--setenv",
                "PATH",
                self._sandbox_path(executable),
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
            raise ValueError("v0.30 Bubblewrap sandbox is Linux-only")

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
            raise ValueError("Bubblewrap version probe failed") from exc
        if version_result.returncode != 0:
            raise ValueError("Bubblewrap version probe returned nonzero")

        raw_version = version_result.stdout or version_result.stderr
        version = raw_version.decode("utf-8", errors="replace").strip().splitlines()
        version_text = version[0][:512] if version else "unknown"
        if not _SAFE_VERSION_RE.fullmatch(version_text):
            version_text = "unprintable-version-output"

        true_path = shutil.which("true")
        if not true_path or not self._path_allowed(Path(true_path)):
            raise ValueError("Sandbox preflight requires a system true executable")

        with tempfile.TemporaryDirectory(prefix="phios-sandbox-preflight-") as temp:
            source = Path(temp).resolve()
            command = self.command_for(
                executable_path=true_path,
                argv_tail=(),
                source_root=source,
                cwd=source,
            )
            try:
                result = subprocess.run(
                    command,
                    cwd=source,
                    env={"PATH": os.environ.get("PATH", "")},
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                    timeout=10,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ValueError("Bubblewrap namespace preflight failed") from exc
            if result.returncode != 0:
                raise ValueError(
                    "Bubblewrap namespace preflight returned nonzero; "
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

    def control_evidence(self) -> SandboxControlEvidence:
        return SandboxControlEvidence(
            mount_namespace_enforced=True,
            user_namespace_enforced=True,
            pid_namespace_enforced=True,
            ipc_namespace_enforced=True,
            uts_namespace_enforced=True,
            cgroup_namespace_requested=True,
            private_proc=True,
            private_dev=True,
            private_tmp=True,
            private_home=True,
            workspace_only_writable_mount=True,
            host_system_roots_read_only=True,
            network_namespace_enforced=self.policy.network_mode == "deny",
            host_network_inherited=self.policy.network_mode == "inherit",
            wall_clock_timeout_enforced=True,
            cpu_rlimit_enforced=True,
            address_space_rlimit_enforced=True,
            open_files_rlimit_enforced=True,
            file_size_rlimit_enforced=True,
            process_count_limit_enforced=False,
            seccomp_enforced=False,
            network_allowlist_enforced=False,
            parent_death_enforced=True,
        )

    def _execute(
        self,
        *,
        executable_tool: str,
        argv: tuple[str, ...],
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
        preview_limit: int = 0,
    ) -> tuple[str, ProcessResult]:
        if self._backend_identity is None:
            raise ValueError("Sandbox runner must pass preflight before execution")

        source_text = env.get("PHIOS_EXECUTION_SOURCE")
        if not source_text:
            raise ValueError("Sandbox runner requires PHIOS_EXECUTION_SOURCE")
        source_root = Path(source_text).resolve()

        resolved_tool = shutil.which(executable_tool, path=env.get("PATH"))
        if not resolved_tool:
            raise ValueError(f"Required build executable is unavailable: {executable_tool}")
        resolved_path = Path(resolved_tool).resolve()
        if not self._path_allowed(resolved_path):
            raise ValueError(
                f"Required build executable is outside sandbox system roots: {resolved_path}"
            )
        self._resolved_tool_dirs.add(str(resolved_path.parent))

        command = self.command_for(
            executable_path=str(resolved_path),
            argv_tail=argv[1:],
            source_root=source_root,
            cwd=cwd,
        )

        host_env = {"PATH": os.environ.get("PATH", "")}
        _, result = super()._execute(
            executable_tool=command[0],
            argv=command,
            cwd=source_root,
            env=host_env,
            timeout_seconds=min(timeout_seconds, self.policy.wall_clock_seconds),
            preview_limit=preview_limit,
        )
        return str(resolved_path), result


def _persist_sandbox_receipt(path: Path, receipt: BuildSandboxReceipt) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    payload = json.dumps(
        receipt.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    try:
        temporary.write_text(payload + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


class SandboxedBuildExecutionService:
    def __init__(
        self,
        policy: BuildSandboxPolicy,
        *,
        runner: SandboxBuildRunner | None = None,
    ) -> None:
        self.policy = policy
        self.runner = runner or BubblewrapSandboxRunner(policy)
        if self.runner.policy.sha256() != policy.sha256():
            raise ValueError("Sandbox runner policy does not match service policy")

    def execute(
        self,
        request: BuildExecutionRequest,
        *,
        execution_root: Path,
        receipt_root: Path | None = None,
    ) -> SandboxedBuildExecutionResult:
        if self.policy.network_mode == "inherit":
            if "build.network.dependencies" not in request.approved_permissions:
                raise ValueError(
                    "Host network inheritance requires build.network.dependencies approval"
                )

        backend_identity = self.runner.preflight()
        execution = BuildExecutionService(
            runner=self.runner,
            step_timeout_seconds=self.policy.wall_clock_seconds,
        ).execute(
            request,
            execution_root=execution_root,
            receipt_root=receipt_root,
        )

        controls = self.runner.control_evidence()
        containment_level = (
            "linux_namespaces_network_denied_rlimits"
            if controls.network_namespace_enforced
            else "linux_namespaces_host_network_rlimits"
        )
        sandbox_receipt = BuildSandboxReceipt(
            sandbox_receipt_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(UTC).isoformat(),
            execution_id=execution.execution_id,
            build_execution_receipt_sha256=execution.sha256(),
            app_id=execution.app_id,
            commit_sha=execution.commit_sha,
            plan_sha256=execution.plan_sha256,
            source_snapshot_sha256=execution.source_snapshot_sha256,
            policy=self.policy,
            backend_identity=backend_identity,
            controls=controls,
            containment_level=containment_level,
            build_status=execution.status,
        )

        root = execution_root.expanduser().resolve()
        receipts = (receipt_root or (root / ".phios-receipts")).expanduser().resolve()
        sandbox_path = receipts / f"sandbox-{execution.execution_id}.json"
        persisted = True
        path_text: str | None = str(sandbox_path)
        try:
            _persist_sandbox_receipt(sandbox_path, sandbox_receipt)
        except OSError:
            persisted = False
            path_text = None

        return SandboxedBuildExecutionResult(
            execution=execution,
            sandbox=sandbox_receipt,
            sandbox_receipt_path=path_text,
            sandbox_receipt_persisted=persisted,
        )
