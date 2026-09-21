from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, cast

from .build_plan import AcquisitionBinding, BuildPlan, BuildStep, snapshot_source_tree

BUILD_EXECUTION_REQUEST_SCHEMA_VERSION = "phios.build_execution_request.v0.1"
BUILD_EXECUTION_RECEIPT_SCHEMA_VERSION = "phios.build_execution_receipt.v0.1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PERMISSION_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
_MAX_CAPTURE_PREVIEW_BYTES = 0
_MAX_ARTIFACT_FILES = 2048
_MAX_ARTIFACT_FILE_BYTES = 64 * 1024 * 1024
_MAX_ARTIFACT_TOTAL_BYTES = 256 * 1024 * 1024
_DEFAULT_STEP_TIMEOUT_SECONDS = 900

_TOOL_PROBES: dict[str, tuple[str, tuple[str, ...]]] = {
    "npm": ("npm", ("npm", "--version")),
    "node": ("node", ("node", "--version")),
    "pnpm": ("pnpm", ("pnpm", "--version")),
    "yarn": ("yarn", ("yarn", "--version")),
    "bun": ("bun", ("bun", "--version")),
    "python": ("python", ("python", "--version")),
    "python-build": ("python", ("python", "-m", "build", "--version")),
    "cargo": ("cargo", ("cargo", "--version")),
    "rustc": ("rustc", ("rustc", "--version")),
    "go": ("go", ("go", "version")),
}
_EXECUTABLE_TOOLS = {"npm", "pnpm", "yarn", "bun", "python", "cargo", "go"}


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


def _safe_relative(value: str, label: str) -> str:
    text = _string(value, label, maximum=512)
    if "\\" in text or text.startswith("/"):
        raise ValueError(f"{label} must be a relative POSIX path")
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{label} contains unsafe path segments")
    return text


@dataclass(frozen=True)
class BuildExecutionRequest:
    plan: BuildPlan
    acquisition: AcquisitionBinding
    approved_plan_sha256: str
    approved_source_snapshot_sha256: str
    approved_permissions: tuple[str, ...]
    release_build_review_sha256: str | None = None
    schema_version: str = BUILD_EXECUTION_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != BUILD_EXECUTION_REQUEST_SCHEMA_VERSION:
            raise ValueError(f"Unsupported build execution request schema: {self.schema_version}")
        if self.plan.status == "review_required":
            raise ValueError("Build plans with review_required status are not executable")
        if self.plan.app_id != self.acquisition.app_id:
            raise ValueError("Build plan app_id does not match acquisition receipt")
        if self.plan.repository_url.lower() != self.acquisition.repository_url.lower():
            raise ValueError("Build plan repository does not match acquisition receipt")
        if self.plan.commit_sha != self.acquisition.commit_sha:
            raise ValueError("Build plan commit does not match acquisition receipt")
        if self.plan.manifest_sha256 != self.acquisition.manifest_sha256:
            raise ValueError("Build plan manifest digest does not match acquisition receipt")
        if self.plan.acquisition_tree_sha256 != self.acquisition.acquisition_tree_sha256:
            raise ValueError("Build plan acquisition tree digest does not match acquisition receipt")
        if self.plan.source_file_count != self.acquisition.file_count:
            raise ValueError("Build plan source file count does not match acquisition receipt")
        if self.plan.source_total_bytes != self.acquisition.total_bytes:
            raise ValueError("Build plan source byte count does not match acquisition receipt")

        if self.approved_plan_sha256 != self.plan.sha256():
            raise ValueError("Approved plan SHA-256 does not match canonical build plan")
        if self.approved_source_snapshot_sha256 != self.plan.source_snapshot_sha256:
            raise ValueError("Approved source snapshot SHA-256 does not match build plan")

        from .release_build_review import release_advancement_sha256_from_plan

        release_advancement_sha256 = release_advancement_sha256_from_plan(self.plan)
        if release_advancement_sha256 is not None:
            if self.release_build_review_sha256 is None:
                raise ValueError(
                    "release build execution requires an exact v0.48 release build review"
                )
            _sha256(
                self.release_build_review_sha256,
                "release_build_review_sha256",
            )
        elif self.release_build_review_sha256 is not None:
            raise ValueError(
                "release build review is valid only for a release-lineage build plan"
            )

        if len(set(self.approved_permissions)) != len(self.approved_permissions):
            raise ValueError("Approved build permissions must not contain duplicates")
        for permission in self.approved_permissions:
            if not _PERMISSION_RE.fullmatch(permission):
                raise ValueError(f"Invalid approved build permission: {permission}")

        requested = set(self.plan.requested_build_permissions)
        approved = set(self.approved_permissions)
        if requested != approved:
            missing = sorted(requested - approved)
            extra = sorted(approved - requested)
            detail: list[str] = []
            if missing:
                detail.append(f"missing={','.join(missing)}")
            if extra:
                detail.append(f"extra={','.join(extra)}")
            raise ValueError(
                "Approved build permissions must exactly match the reviewed plan"
                + (f" ({'; '.join(detail)})" if detail else "")
            )

        if self.plan.steps and "build.process.execute" not in approved:
            raise ValueError("Executable build plan requires build.process.execute approval")
        if self.plan.steps and "build.workspace.write" not in approved:
            raise ValueError("Executable build plan requires build.workspace.write approval")
        if any(step.requires_network for step in self.plan.steps):
            if "build.network.dependencies" not in approved:
                raise ValueError(
                    "Network-requiring build step requires build.network.dependencies approval"
                )

        for step in self.plan.steps:
            if step.tool not in _EXECUTABLE_TOOLS:
                raise ValueError(f"v0.29 does not execute unsupported tool: {step.tool}")
        for tool in self.plan.required_tools:
            if tool not in _TOOL_PROBES:
                raise ValueError(f"v0.29 cannot verify required tool: {tool}")

    @classmethod
    def from_payloads(
        cls,
        plan_value: Any,
        acquisition_receipt_value: Any,
        *,
        approved_plan_sha256: str,
        approved_source_snapshot_sha256: str,
        approved_permissions: tuple[str, ...],
        release_build_review_value: Any | None = None,
        approved_release_build_review_sha256: str | None = None,
    ) -> BuildExecutionRequest:
        plan = BuildPlan.from_dict(plan_value)

        from .release_build_review import (
            release_advancement_sha256_from_plan,
            validate_release_build_review,
        )

        release_advancement_sha256 = release_advancement_sha256_from_plan(plan)
        review_sha256: str | None = None
        if release_advancement_sha256 is not None:
            if (
                release_build_review_value is None
                or approved_release_build_review_sha256 is None
            ):
                raise ValueError(
                    "release build execution requires v0.48 review and exact review approval"
                )
            review = validate_release_build_review(
                plan,
                release_build_review_value,
                approved_release_build_review_sha256=(
                    approved_release_build_review_sha256
                ),
            )
            review_sha256 = review.sha256()
        elif (
            release_build_review_value is not None
            or approved_release_build_review_sha256 is not None
        ):
            raise ValueError(
                "release build review inputs are valid only for a release-lineage build plan"
            )

        return cls(
            plan=plan,
            acquisition=AcquisitionBinding.from_dict(acquisition_receipt_value),
            approved_plan_sha256=_sha256(
                approved_plan_sha256,
                "approved_plan_sha256",
            ),
            approved_source_snapshot_sha256=_sha256(
                approved_source_snapshot_sha256,
                "approved_source_snapshot_sha256",
            ),
            approved_permissions=tuple(sorted(approved_permissions)),
            release_build_review_sha256=review_sha256,
        )


@dataclass(frozen=True)
class StreamCapture:
    byte_count: int
    sha256: str
    preview: str
    preview_truncated: bool


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int
    timed_out: bool
    duration_ms: int
    stdout: StreamCapture
    stderr: StreamCapture


@dataclass(frozen=True)
class ToolIdentity:
    logical_tool: str
    executable_path: str
    version: str
    version_output_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BuildProcessRunner(Protocol):
    def probe(
        self,
        *,
        logical_tool: str,
        executable_tool: str,
        argv: tuple[str, ...],
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> ToolIdentity: ...

    def run(
        self,
        step: BuildStep,
        *,
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> ProcessResult: ...


class _CaptureBuffer:
    def __init__(self, *, preview_limit: int = _MAX_CAPTURE_PREVIEW_BYTES) -> None:
        self.preview_limit = preview_limit
        self.byte_count = 0
        self.digest = hashlib.sha256()
        self.preview = bytearray()

    def feed(self, chunk: bytes) -> None:
        self.byte_count += len(chunk)
        self.digest.update(chunk)
        if len(self.preview) < self.preview_limit:
            remaining = self.preview_limit - len(self.preview)
            self.preview.extend(chunk[:remaining])

    def result(self) -> StreamCapture:
        return StreamCapture(
            byte_count=self.byte_count,
            sha256=self.digest.hexdigest(),
            preview=self.preview.decode("utf-8", errors="replace"),
            preview_truncated=self.byte_count > len(self.preview),
        )


class SubprocessBuildRunner:
    """Run reviewed argv without a shell. This is not an OS sandbox."""

    isolation_mode = "isolated_working_copy_no_os_sandbox"
    network_sandbox_enforced = False

    def _execute(
        self,
        *,
        executable_tool: str,
        argv: tuple[str, ...],
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
        preview_limit: int = _MAX_CAPTURE_PREVIEW_BYTES,
    ) -> tuple[str, ProcessResult]:
        resolved = shutil.which(executable_tool, path=env.get("PATH"))
        if resolved is None:
            raise ValueError(f"Required build executable is unavailable: {executable_tool}")

        command = (resolved, *argv[1:])
        started = time.monotonic()
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
        assert process.stdout is not None
        assert process.stderr is not None

        stdout_capture = _CaptureBuffer(preview_limit=preview_limit)
        stderr_capture = _CaptureBuffer(preview_limit=preview_limit)

        def drain(stream: Any, capture: _CaptureBuffer) -> None:
            while True:
                chunk = stream.read(65_536)
                if not chunk:
                    break
                capture.feed(chunk)

        stdout_thread = threading.Thread(
            target=drain,
            args=(process.stdout, stdout_capture),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=drain,
            args=(process.stderr, stderr_capture),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        timed_out = False
        try:
            exit_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            exit_code = process.wait()

        stdout_thread.join()
        stderr_thread.join()
        duration_ms = int((time.monotonic() - started) * 1000)
        return resolved, ProcessResult(
            exit_code=exit_code,
            timed_out=timed_out,
            duration_ms=duration_ms,
            stdout=stdout_capture.result(),
            stderr=stderr_capture.result(),
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
        resolved, result = self._execute(
            executable_tool=executable_tool,
            argv=argv,
            cwd=cwd,
            env=env,
            timeout_seconds=timeout_seconds,
            preview_limit=512,
        )
        if result.timed_out or result.exit_code != 0:
            raise ValueError(f"Required build tool probe failed: {logical_tool}")

        version_text = result.stdout.preview or result.stderr.preview
        version = version_text.strip().splitlines()[0] if version_text.strip() else "output-not-retained"
        version = version[:512]
        combined = hashlib.sha256()
        combined.update(result.stdout.sha256.encode("ascii"))
        combined.update(result.stderr.sha256.encode("ascii"))
        return ToolIdentity(
            logical_tool=logical_tool,
            executable_path=resolved,
            version=version,
            version_output_sha256=combined.hexdigest(),
        )

    def run(
        self,
        step: BuildStep,
        *,
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> ProcessResult:
        _, result = self._execute(
            executable_tool=step.tool,
            argv=step.argv,
            cwd=cwd,
            env=env,
            timeout_seconds=timeout_seconds,
            preview_limit=0,
        )
        return result


@dataclass(frozen=True)
class BuildStepExecutionReceipt:
    step_id: str
    phase: str
    tool: str
    argv: tuple[str, ...]
    working_directory: str
    requires_network: bool
    exit_code: int
    timed_out: bool
    duration_ms: int
    stdout_byte_count: int
    stdout_sha256: str
    stderr_byte_count: int
    stderr_sha256: str
    status: str

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["argv"] = list(self.argv)
        return result


@dataclass(frozen=True)
class BuildArtifact:
    path: str
    byte_count: int
    sha256: str

    def canonical_line(self) -> bytes:
        return f"{self.path}\0{self.byte_count}\0{self.sha256}\n".encode("utf-8")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BuildExecutionReceipt:
    execution_id: str
    timestamp_utc: str
    app_id: str
    repository_url: str
    commit_sha: str
    plan_sha256: str
    source_snapshot_sha256: str
    acquisition_tree_sha256: str
    approved_permissions: tuple[str, ...]
    isolation_mode: str
    network_sandbox_enforced: bool
    source_workspace_path: str
    execution_workspace_path: str
    tool_identities: tuple[ToolIdentity, ...]
    steps: tuple[BuildStepExecutionReceipt, ...]
    artifacts: tuple[BuildArtifact, ...]
    artifact_set_sha256: str
    status: str
    failure_reason: str | None
    schema_version: str = BUILD_EXECUTION_RECEIPT_SCHEMA_VERSION

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "execution_id": self.execution_id,
            "timestamp_utc": self.timestamp_utc,
            "app_id": self.app_id,
            "repository_url": self.repository_url,
            "commit_sha": self.commit_sha,
            "plan_sha256": self.plan_sha256,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "acquisition_tree_sha256": self.acquisition_tree_sha256,
            "approved_permissions": list(self.approved_permissions),
            "isolation_mode": self.isolation_mode,
            "network_sandbox_enforced": self.network_sandbox_enforced,
            "source_workspace_path": self.source_workspace_path,
            "execution_workspace_path": self.execution_workspace_path,
            "tool_identities": [item.to_dict() for item in self.tool_identities],
            "steps": [item.to_dict() for item in self.steps],
            "artifacts": [item.to_dict() for item in self.artifacts],
            "artifact_set_sha256": self.artifact_set_sha256,
            "status": self.status,
            "failure_reason": self.failure_reason,
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
        result["receipt_sha256"] = self.sha256()
        return result


def _clean_environment(execution_source: Path) -> dict[str, str]:
    environment_root = execution_source.parent / ".phios-env"
    home = environment_root / "home"
    temp = environment_root / "tmp"
    home.mkdir(parents=True, exist_ok=True)
    temp.mkdir(parents=True, exist_ok=True)

    env: dict[str, str] = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        "TMPDIR": str(temp),
        "TEMP": str(temp),
        "TMP": str(temp),
        "PHIOS_BUILD_EXECUTION": "1",
        "PHIOS_EXECUTION_SOURCE": str(execution_source.resolve()),
    }
    for key in ("SystemRoot", "WINDIR", "PATHEXT", "COMSPEC", "LANG", "LC_ALL"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    return env


def _copy_source_exact(source: Path, destination: Path, expected_snapshot: str) -> None:
    if destination.exists():
        raise ValueError("Execution source destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, symlinks=True)
    snapshot, _, _ = snapshot_source_tree(destination)
    if snapshot != expected_snapshot:
        shutil.rmtree(destination.parent, ignore_errors=True)
        raise ValueError("Execution source copy does not match approved source snapshot")


def _working_directory(root: Path, relative: str) -> Path:
    if relative == ".":
        return root
    _safe_relative(relative, "build step working_directory")
    target = (root / Path(*PurePosixPath(relative).parts)).resolve()
    resolved_root = root.resolve()
    if resolved_root != target and resolved_root not in target.parents:
        raise ValueError("Build step working directory escaped execution source root")
    if not target.is_dir():
        raise ValueError(f"Build step working directory does not exist: {relative}")
    return target


def _artifact_paths(root: Path, spec: str) -> list[Path]:
    raw = spec[:-1] if spec.endswith("/") else spec
    _safe_relative(raw, "expected output")
    wildcard = any(character in raw for character in "*?[")

    if wildcard:
        matches = [Path(path) for path in glob.glob(str(root / raw), recursive=False)]
    else:
        path = root / Path(*PurePosixPath(raw).parts)
        matches = [path] if path.exists() else []

    files: list[Path] = []
    for match in matches:
        if match.is_symlink():
            raise ValueError(f"Build output contains a symlink: {match}")
        if match.is_dir():
            for candidate in match.rglob("*"):
                if candidate.is_symlink():
                    raise ValueError(f"Build output contains a symlink: {candidate}")
                if candidate.is_dir():
                    continue
                if not candidate.is_file():
                    raise ValueError(f"Build output contains a special file: {candidate}")
                files.append(candidate)
        elif match.is_file():
            files.append(match)
        elif match.exists():
            raise ValueError(f"Build output is not a regular file or directory: {match}")
    return files


def _collect_artifacts(root: Path, expected_outputs: tuple[str, ...]) -> tuple[tuple[BuildArtifact, ...], str]:
    artifacts: dict[str, BuildArtifact] = {}
    total_bytes = 0

    for spec in expected_outputs:
        paths = _artifact_paths(root, spec)
        if not paths:
            raise ValueError(f"Expected build output was not produced: {spec}")
        for path in paths:
            relative = path.relative_to(root).as_posix()
            _safe_relative(relative, "artifact path")
            size = path.stat().st_size
            if size > _MAX_ARTIFACT_FILE_BYTES:
                raise ValueError(f"Build artifact exceeds bounded per-file size: {relative}")
            content = path.read_bytes()
            if len(content) != size:
                raise ValueError(f"Build artifact changed while hashing: {relative}")

            total_bytes += len(content)
            if total_bytes > _MAX_ARTIFACT_TOTAL_BYTES:
                raise ValueError("Build artifacts exceed bounded total byte count")

            artifacts[relative] = BuildArtifact(
                path=relative,
                byte_count=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
            )
            if len(artifacts) > _MAX_ARTIFACT_FILES:
                raise ValueError("Build artifacts exceed bounded file count")

    ordered = tuple(artifacts[path] for path in sorted(artifacts))
    digest = hashlib.sha256()
    for artifact in ordered:
        digest.update(artifact.canonical_line())
    return ordered, digest.hexdigest()


def _write_receipt(path: Path, receipt: BuildExecutionReceipt) -> None:
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


class BuildExecutionService:
    def __init__(
        self,
        *,
        runner: BuildProcessRunner | None = None,
        step_timeout_seconds: int = _DEFAULT_STEP_TIMEOUT_SECONDS,
    ) -> None:
        if not 1 <= step_timeout_seconds <= 3600:
            raise ValueError("step_timeout_seconds must be between 1 and 3600")
        self.runner = runner or SubprocessBuildRunner()
        self.step_timeout_seconds = step_timeout_seconds

    def execute(
        self,
        request: BuildExecutionRequest,
        *,
        execution_root: Path,
        receipt_root: Path | None = None,
    ) -> BuildExecutionReceipt:
        plan = request.plan
        source = request.acquisition.workspace_path
        if source.is_symlink():
            raise ValueError("Acquired source workspace must not be a symlink")
        try:
            source_root = source.resolve(strict=True)
        except OSError as exc:
            raise ValueError("Acquired source workspace is unavailable") from exc

        snapshot, file_count, total_bytes = snapshot_source_tree(source_root)
        if snapshot != plan.source_snapshot_sha256:
            raise ValueError("Source snapshot changed after build plan review")
        if file_count != plan.source_file_count:
            raise ValueError("Source file count changed after build plan review")
        if total_bytes != plan.source_total_bytes:
            raise ValueError("Source byte count changed after build plan review")

        root = execution_root.expanduser().resolve()
        execution_id = str(uuid.uuid4())
        execution_dir = (root / plan.app_id / plan.sha256() / execution_id).resolve()
        source_copy = execution_dir / "source"
        if root != execution_dir and root not in execution_dir.parents:
            raise ValueError("Execution workspace escaped configured execution root")
        if source_copy == source_root or source_root in source_copy.parents:
            raise ValueError("Execution workspace must remain outside the acquired source tree")
        if source_copy in source_root.parents:
            raise ValueError("Execution workspace must not contain the acquired source tree")

        receipts = (receipt_root or (root / ".phios-receipts")).expanduser().resolve()
        if receipts == source_root or source_root in receipts.parents:
            raise ValueError("Receipt root must remain outside the acquired source tree")
        if receipts == source_copy or source_copy in receipts.parents:
            raise ValueError("Receipt root must remain outside the execution source tree")

        _copy_source_exact(source_root, source_copy, plan.source_snapshot_sha256)
        env = _clean_environment(source_copy)

        identities: list[ToolIdentity] = []
        step_receipts: list[BuildStepExecutionReceipt] = []
        artifacts: tuple[BuildArtifact, ...] = ()
        artifact_set_sha256 = hashlib.sha256(b"").hexdigest()
        status = "success" if plan.steps else "no_build_required"
        failure_reason: str | None = None

        try:
            for tool in plan.required_tools:
                executable_tool, probe_argv = _TOOL_PROBES[tool]
                identities.append(
                    self.runner.probe(
                        logical_tool=tool,
                        executable_tool=executable_tool,
                        argv=probe_argv,
                        cwd=source_copy,
                        env=env,
                        timeout_seconds=min(self.step_timeout_seconds, 30),
                    )
                )

            for step in plan.steps:
                cwd = _working_directory(source_copy, step.working_directory)
                result = self.runner.run(
                    step,
                    cwd=cwd,
                    env=env,
                    timeout_seconds=self.step_timeout_seconds,
                )
                step_status = (
                    "timed_out"
                    if result.timed_out
                    else ("succeeded" if result.exit_code == 0 else "failed")
                )
                step_receipts.append(
                    BuildStepExecutionReceipt(
                        step_id=step.step_id,
                        phase=step.phase,
                        tool=step.tool,
                        argv=step.argv,
                        working_directory=step.working_directory,
                        requires_network=step.requires_network,
                        exit_code=result.exit_code,
                        timed_out=result.timed_out,
                        duration_ms=result.duration_ms,
                        stdout_byte_count=result.stdout.byte_count,
                        stdout_sha256=result.stdout.sha256,
                        stderr_byte_count=result.stderr.byte_count,
                        stderr_sha256=result.stderr.sha256,
                        status=step_status,
                    )
                )
                if result.timed_out:
                    status = "failed"
                    failure_reason = f"step {step.step_id} exceeded execution timeout"
                    break
                if result.exit_code != 0:
                    status = "failed"
                    failure_reason = f"step {step.step_id} exited with code {result.exit_code}"
                    break

            if status in {"success", "no_build_required"}:
                try:
                    artifacts, artifact_set_sha256 = _collect_artifacts(
                        source_copy,
                        plan.expected_outputs,
                    )
                except ValueError as exc:
                    status = "failed"
                    failure_reason = str(exc)

            receipt = BuildExecutionReceipt(
                execution_id=execution_id,
                timestamp_utc=datetime.now(UTC).isoformat(),
                app_id=plan.app_id,
                repository_url=plan.repository_url,
                commit_sha=plan.commit_sha,
                plan_sha256=plan.sha256(),
                source_snapshot_sha256=plan.source_snapshot_sha256,
                acquisition_tree_sha256=plan.acquisition_tree_sha256,
                approved_permissions=request.approved_permissions,
                isolation_mode=str(
                    getattr(
                        self.runner,
                        "isolation_mode",
                        "isolated_working_copy_no_os_sandbox",
                    )
                ),
                network_sandbox_enforced=bool(
                    getattr(self.runner, "network_sandbox_enforced", False)
                ),
                source_workspace_path=str(source_root),
                execution_workspace_path=str(source_copy),
                tool_identities=tuple(identities),
                steps=tuple(step_receipts),
                artifacts=artifacts,
                artifact_set_sha256=artifact_set_sha256,
                status=status,
                failure_reason=failure_reason,
            )

            receipt_path = receipts / f"{execution_id}.json"
            try:
                _write_receipt(receipt_path, receipt)
            except Exception:
                shutil.rmtree(execution_dir, ignore_errors=True)
                raise
            return receipt
        except Exception:
            if not step_receipts:
                shutil.rmtree(execution_dir, ignore_errors=True)
            raise
