from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .build_execution import ProcessResult, StreamCapture, ToolIdentity
from .build_plan import BuildStep
from .toolchain_acquisition import CapsuleAcquisitionReceipt
from .toolchain_attestation import (
    ToolProbeObservation,
    ToolchainAttestation,
    ToolchainSandboxPlan,
)
from .toolchain_capsule import ToolchainCapsule
from .toolchain_runtime import (
    OciRuntimeAdapterIdentity,
    OciRuntimeControlEvidence,
)

PODMAN_ROOTLESS_ADAPTER_ID = "phios.podman-rootless"
PODMAN_ROOTLESS_ADAPTER_VERSION = "0.1.0"

_IMAGE_ID_RE = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$")
_SHA256_LINE_RE = re.compile(r"^([0-9a-f]{64})[ \t]+")
_MAX_CAPTURE_PREVIEW_BYTES = 512
_DEFAULT_TIMEOUT_SECONDS = 900


@dataclass(frozen=True)
class PodmanCommandResult:
    exit_code: int
    timed_out: bool
    duration_ms: int
    stdout: bytes
    stderr: bytes


class PodmanCommandExecutor(Protocol):
    def run(
        self,
        argv: tuple[str, ...],
        *,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> PodmanCommandResult: ...


class SubprocessPodmanCommandExecutor:
    def run(
        self,
        argv: tuple[str, ...],
        *,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> PodmanCommandResult:
        started = time.monotonic()
        try:
            result = subprocess.run(
                argv,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return PodmanCommandResult(
                exit_code=-1,
                timed_out=True,
                duration_ms=int((time.monotonic() - started) * 1000),
                stdout=exc.stdout or b"",
                stderr=exc.stderr or b"",
            )
        return PodmanCommandResult(
            exit_code=result.returncode,
            timed_out=False,
            duration_ms=int((time.monotonic() - started) * 1000),
            stdout=result.stdout,
            stderr=result.stderr,
        )


def _capture(data: bytes, *, preview_limit: int) -> StreamCapture:
    preview = data[:preview_limit]
    return StreamCapture(
        byte_count=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        preview=preview.decode("utf-8", errors="replace"),
        preview_truncated=len(data) > len(preview),
    )


def _process_result(
    result: PodmanCommandResult,
    *,
    preview_limit: int,
) -> ProcessResult:
    return ProcessResult(
        exit_code=result.exit_code,
        timed_out=result.timed_out,
        duration_ms=result.duration_ms,
        stdout=_capture(result.stdout, preview_limit=preview_limit),
        stderr=_capture(result.stderr, preview_limit=preview_limit),
    )


def _probe_digest(result: ProcessResult) -> str:
    combined = hashlib.sha256()
    combined.update(result.stdout.sha256.encode("ascii"))
    combined.update(result.stderr.sha256.encode("ascii"))
    return combined.hexdigest()


def _probe_version(result: ProcessResult) -> str:
    text = result.stdout.preview or result.stderr.preview
    lines = text.strip().splitlines()
    return lines[0][:96] if lines else "output-not-retained"


def _hash_regular_file(path: Path) -> str:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise ValueError(f"Podman executable is unavailable: {path}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError("Podman executable must be a regular non-symlink file")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


class PodmanRootlessOciRunner:
    """Concrete rootless Podman adapter for the v0.54 OCI runtime protocol."""

    isolation_mode = "podman_rootless_network_none"
    network_sandbox_enforced = True

    def __init__(
        self,
        *,
        capsule: ToolchainCapsule,
        acquisition: CapsuleAcquisitionReceipt,
        sandbox_plan: ToolchainSandboxPlan,
        reviewed_attestation: ToolchainAttestation,
        state_root: Path,
        podman_path: str | None = None,
        executor: PodmanCommandExecutor | None = None,
        command_timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if sandbox_plan.status != "ready_for_runtime_adapter_review":
            raise ValueError(
                "Podman v0.55 requires ready_for_runtime_adapter_review status"
            )
        if sandbox_plan.sandbox_policy.network_mode != "deny":
            raise ValueError("Podman v0.55 accepts only network-denied sandbox plans")
        if sandbox_plan.capsule_sha256 != capsule.sha256():
            raise ValueError("Podman sandbox plan does not match reviewed capsule")
        if sandbox_plan.acquisition_receipt_sha256 != acquisition.sha256():
            raise ValueError("Podman sandbox plan does not match capsule acquisition")
        if sandbox_plan.attestation_sha256 != reviewed_attestation.sha256():
            raise ValueError("Podman sandbox plan does not match reviewed attestation")
        if sandbox_plan.capsule_artifact_sha256 != capsule.artifact_sha256:
            raise ValueError("Podman sandbox plan artifact digest does not match capsule")
        if Path(sandbox_plan.capsule_storage_path) != Path(acquisition.storage_path):
            raise ValueError("Podman sandbox plan storage path does not match acquisition")
        if not 1 <= command_timeout_seconds <= 3600:
            raise ValueError("command_timeout_seconds must be between 1 and 3600")

        self.capsule = capsule
        self.acquisition = acquisition
        self.sandbox_plan = sandbox_plan
        self.reviewed_attestation = reviewed_attestation
        self.state_root = state_root.expanduser().absolute()
        self.podman_path = podman_path
        self.executor = executor or SubprocessPodmanCommandExecutor()
        self.command_timeout_seconds = command_timeout_seconds

        self.capsule_artifact_sha256 = capsule.artifact_sha256
        self.capsule_storage_path = acquisition.storage_path
        self.sandbox_plan_sha256 = sandbox_plan.sha256()
        self.policy_sha256 = sandbox_plan.sandbox_policy.sha256()

        self._resolved_podman: Path | None = None
        self._image_id: str | None = None
        self._runtime_identity: OciRuntimeAdapterIdentity | None = None

    @property
    def graph_root(self) -> Path:
        return self.state_root / "graphroot"

    @property
    def run_root(self) -> Path:
        return self.state_root / "runroot"

    @property
    def temp_root(self) -> Path:
        return self.state_root / "tmp"

    def _host_environment(self) -> dict[str, str]:
        env: dict[str, str] = {}
        for key in ("HOME", "XDG_RUNTIME_DIR", "LANG", "LC_ALL", "PATH"):
            value = os.environ.get(key)
            if value:
                env[key] = value
        env["TMPDIR"] = str(self.temp_root)
        return env

    def _resolve_podman(self) -> Path:
        if self._resolved_podman is not None:
            return self._resolved_podman
        raw = self.podman_path or shutil.which("podman")
        if not raw:
            raise ValueError("Podman rootless backend is unavailable: podman was not found")
        path = Path(raw)
        if not path.is_absolute():
            raise ValueError("Podman executable must resolve to an absolute path")
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise ValueError("Podman executable is unavailable") from exc
        self._resolved_podman = resolved
        return resolved

    def _base_argv(self) -> tuple[str, ...]:
        return (
            str(self._resolve_podman()),
            "--root",
            str(self.graph_root),
            "--runroot",
            str(self.run_root),
            "--storage-driver=vfs",
        )

    def _podman(
        self,
        *args: str,
        timeout_seconds: int | None = None,
    ) -> PodmanCommandResult:
        result = self.executor.run(
            (*self._base_argv(), *args),
            env=self._host_environment(),
            timeout_seconds=timeout_seconds or self.command_timeout_seconds,
        )
        if result.timed_out:
            raise ValueError(f"Podman command timed out: {args[0] if args else 'unknown'}")
        if result.exit_code != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()[:512]
            raise ValueError(
                f"Podman command failed: {args[0] if args else 'unknown'}"
                + (f": {detail}" if detail else "")
            )
        return result

    def _require_preflight(self) -> str:
        if self._image_id is None or self._runtime_identity is None:
            raise ValueError("Podman runner must pass preflight before runtime use")
        return self._image_id

    def _container_argv(
        self,
        command: tuple[str, ...],
        *,
        source_root: Path | None = None,
        cwd: Path | None = None,
    ) -> tuple[str, ...]:
        image_id = self._require_preflight()
        argv: list[str] = [
            "run",
            "--rm",
            "--pull=never",
            "--network=none",
            "--read-only",
            "--read-only-tmpfs=true",
            "--cap-drop=all",
            "--security-opt=no-new-privileges",
            "--pids-limit=256",
            "--userns=keep-id",
        ]

        if source_root is not None:
            source = source_root.resolve()
            working = (cwd or source).resolve()
            try:
                relative = working.relative_to(source)
            except ValueError as exc:
                raise ValueError("Podman working directory escaped execution source") from exc

            argv.extend(
                (
                    "--mount",
                    f"type=bind,src={source},target=/workspace,rw",
                    "--workdir",
                    "/workspace" if not relative.parts else f"/workspace/{relative.as_posix()}",
                    "--env",
                    "HOME=/tmp/phios-home",
                    "--env",
                    "TMPDIR=/tmp",
                    "--env",
                    "PHIOS_BUILD_EXECUTION=1",
                    "--env",
                    "PHIOS_TOOLCHAIN_RUNTIME=podman-rootless",
                    "--env",
                    "PHIOS_EXECUTION_SOURCE=/workspace",
                )
            )

        argv.append(image_id)
        argv.extend(command)
        return tuple(argv)

    def _run_container(
        self,
        command: tuple[str, ...],
        *,
        source_root: Path | None = None,
        cwd: Path | None = None,
        timeout_seconds: int | None = None,
        preview_limit: int = _MAX_CAPTURE_PREVIEW_BYTES,
    ) -> ProcessResult:
        result = self.executor.run(
            (*self._base_argv(), *self._container_argv(
                command,
                source_root=source_root,
                cwd=cwd,
            )),
            env=self._host_environment(),
            timeout_seconds=timeout_seconds or self.command_timeout_seconds,
        )
        return _process_result(result, preview_limit=preview_limit)

    def preflight(self) -> OciRuntimeAdapterIdentity:
        if self._runtime_identity is not None:
            return self._runtime_identity
        if platform.system() != "Linux":
            raise ValueError("Podman v0.55 rootless backend is Linux-only")
        geteuid = getattr(os, "geteuid", None)
        if geteuid is None or geteuid() == 0:
            raise ValueError("Podman v0.55 backend requires a non-root host user")

        if self.state_root.exists():
            if self.state_root.is_symlink():
                raise ValueError("Podman state root must not be a symlink")
            if any(self.state_root.iterdir()):
                raise ValueError("Podman v0.55 requires a fresh empty state root")
        self.graph_root.mkdir(parents=True, exist_ok=True)
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.temp_root.mkdir(parents=True, exist_ok=True)

        podman = self._resolve_podman()
        binary_sha256 = _hash_regular_file(podman)

        version_result = self._podman("--version", timeout_seconds=30)
        version_lines = version_result.stdout.decode(
            "utf-8", errors="replace"
        ).strip().splitlines()
        version = version_lines[0][:192] if version_lines else "unknown"

        info_result = self._podman("info", "--format", "json", timeout_seconds=30)
        try:
            info = json.loads(info_result.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Podman info did not return valid JSON") from exc
        rootless = (
            info.get("host", {})
            .get("security", {})
            .get("rootless")
        )
        if rootless is not True:
            raise ValueError("Podman backend refused non-rootless runtime")

        self._podman(
            "load",
            "--quiet",
            "--input",
            str(Path(self.acquisition.storage_path)),
        )
        image_result = self._podman("images", "--quiet", "--no-trunc")
        image_ids: set[str] = set()
        for raw in image_result.stdout.decode("utf-8", errors="replace").splitlines():
            text = raw.strip()
            if not text:
                continue
            match = _IMAGE_ID_RE.fullmatch(text)
            if match is None:
                raise ValueError("Podman image listing returned an unexpected image ID")
            image_ids.add(match.group(1))
        if len(image_ids) != 1:
            raise ValueError("Podman v0.55 requires the isolated store to contain one image")
        self._image_id = next(iter(image_ids))

        identity = OciRuntimeAdapterIdentity(
            adapter_id=PODMAN_ROOTLESS_ADAPTER_ID,
            adapter_version=PODMAN_ROOTLESS_ADAPTER_VERSION,
            backend="podman",
            backend_version=version,
            backend_binary_sha256=binary_sha256,
            platform_system=platform.system(),
            platform_machine=platform.machine(),
        )
        self._runtime_identity = identity
        return identity

    def control_evidence(self) -> OciRuntimeControlEvidence:
        self._require_preflight()
        return OciRuntimeControlEvidence(
            rootfs_read_only=True,
            workspace_bind_read_write=True,
            network_namespace_enforced=True,
            host_network_inherited=False,
            host_control_plane_mounted=False,
            privileged_mode=False,
            capabilities_dropped=True,
            no_new_privileges=True,
            shell_invocation=False,
        )

    def _observe_tool(self, reviewed: ToolProbeObservation) -> ToolProbeObservation:
        if not reviewed.subject_locator.startswith("/"):
            raise ValueError(
                "Podman v0.55 requires an absolute subject locator for runtime recheck"
            )

        hash_result = self._run_container(
            ("sha256sum", reviewed.subject_locator),
            timeout_seconds=30,
        )
        if hash_result.timed_out or hash_result.exit_code != 0:
            raise ValueError(f"Podman subject hash probe failed for {reviewed.name}")
        first = hash_result.stdout.preview.strip().splitlines()
        match = _SHA256_LINE_RE.match(first[0]) if first else None
        if match is None:
            raise ValueError(f"Podman subject hash output is invalid for {reviewed.name}")
        subject_sha256 = match.group(1)

        version_result = self._run_container(
            reviewed.probe_argv,
            timeout_seconds=30,
        )
        if version_result.timed_out or version_result.exit_code != 0:
            raise ValueError(f"Podman version probe failed for {reviewed.name}")

        return ToolProbeObservation(
            name=reviewed.name,
            probe_argv=reviewed.probe_argv,
            observed_version=_probe_version(version_result),
            subject_locator=reviewed.subject_locator,
            subject_sha256=subject_sha256,
            probe_output_sha256=_probe_digest(version_result),
        )

    def runtime_observations(self) -> tuple[ToolProbeObservation, ...]:
        self._require_preflight()
        return tuple(
            self._observe_tool(item)
            for item in sorted(
                self.reviewed_attestation.observations,
                key=lambda observation: observation.name,
            )
        )

    def probe(
        self,
        *,
        logical_tool: str,
        executable_tool: str,
        argv: tuple[str, ...],
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> ToolIdentity:
        del executable_tool
        source_text = env.get("PHIOS_EXECUTION_SOURCE")
        if not source_text:
            raise ValueError("Podman probe requires PHIOS_EXECUTION_SOURCE")
        reviewed = {
            item.name: item for item in self.reviewed_attestation.observations
        }.get(logical_tool)
        if reviewed is None:
            raise ValueError(f"Podman probe has no reviewed observation for {logical_tool}")
        if argv != reviewed.probe_argv:
            raise ValueError(f"Podman probe argv changed for {logical_tool}")

        result = self._run_container(
            argv,
            source_root=Path(source_text),
            cwd=cwd,
            timeout_seconds=timeout_seconds,
        )
        if result.timed_out or result.exit_code != 0:
            raise ValueError(f"Podman build-tool probe failed for {logical_tool}")
        return ToolIdentity(
            logical_tool=logical_tool,
            executable_path=reviewed.subject_locator,
            version=_probe_version(result),
            version_output_sha256=_probe_digest(result),
        )

    def run(
        self,
        step: BuildStep,
        *,
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> ProcessResult:
        if step.requires_network:
            raise ValueError("Podman v0.55 refuses network-requiring build steps")
        source_text = env.get("PHIOS_EXECUTION_SOURCE")
        if not source_text:
            raise ValueError("Podman build step requires PHIOS_EXECUTION_SOURCE")
        return self._run_container(
            step.argv,
            source_root=Path(source_text),
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            preview_limit=0,
        )
