from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Protocol, cast

from .acquisition import SOURCE_ACQUISITION_RECEIPT_SCHEMA_VERSION
from .build_execution import BuildExecutionRequest, ToolIdentity
from .build_plan import AcquisitionBinding, BuildPlan, BuildStep
from .dependency_broker import DependencyReceipt, StagedDependencyArtifact
from .sandbox import (
    BuildSandboxPolicy,
    BubblewrapSandboxRunner,
    SandboxBuildRunner,
    SandboxedBuildExecutionResult,
    SandboxedBuildExecutionService,
)

NPM_CACHE_RECEIPT_SCHEMA_VERSION = "phios.npm_cache_receipt.v0.1"
NPM_OFFLINE_PLAN_SCHEMA_VERSION = "phios.npm_offline_build_plan.v0.1"
NPM_OFFLINE_PLAN_REVIEW_SCHEMA_VERSION = "phios.npm_offline_build_plan_review.v0.1"
NPM_OFFLINE_BUILD_RECEIPT_SCHEMA_VERSION = "phios.npm_offline_build_receipt.v0.1"

_NPM_CACHE_MOUNT = "/phios/npm-cache"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40,64}$")
_MAX_CACHE_FILES = 65_536
_MAX_CACHE_BYTES = 2 * 1024 * 1024 * 1024
_MAX_COMMAND_SECONDS = 300
_MAX_VERSION_OUTPUT_BYTES = 512
_NPM_ENV = {
    "NPM_CONFIG_OFFLINE": "true",
    "NPM_CONFIG_AUDIT": "false",
    "NPM_CONFIG_FUND": "false",
    "NPM_CONFIG_UPDATE_NOTIFIER": "false",
}


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


def _int(value: Any, label: str, *, minimum: int = 0, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return value


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _snapshot_tree(root: Path) -> tuple[str, int, int]:
    if root.is_symlink():
        raise ValueError("npm cache root must not be a symlink")
    resolved = root.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("npm cache root must be a directory")

    records: list[tuple[str, int, str]] = []
    total_bytes = 0
    for path in resolved.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"npm cache contains a symlink: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"npm cache contains a special file: {path}")
        relative = path.relative_to(resolved).as_posix()
        content = path.read_bytes()
        total_bytes += len(content)
        if total_bytes > _MAX_CACHE_BYTES:
            raise ValueError("npm cache exceeds bounded total bytes")
        records.append((relative, len(content), hashlib.sha256(content).hexdigest()))
        if len(records) > _MAX_CACHE_FILES:
            raise ValueError("npm cache exceeds bounded file count")

    if not records:
        raise ValueError("npm cache contains no regular files")

    digest = hashlib.sha256()
    for relative, byte_count, file_sha in sorted(records):
        digest.update(f"{relative}\0{byte_count}\0{file_sha}\n".encode("utf-8"))
    return digest.hexdigest(), len(records), total_bytes


def _verify_artifact(artifact: StagedDependencyArtifact, store_root: Path) -> Path:
    cas_root = (store_root / "cas" / "sha256").resolve(strict=True)
    path = Path(artifact.cas_path)
    if path.is_symlink():
        raise ValueError("dependency CAS artifact must not be a symlink")
    resolved = path.resolve(strict=True)
    if cas_root != resolved and cas_root not in resolved.parents:
        raise ValueError("dependency CAS artifact escaped the receipted store")
    if not resolved.is_file():
        raise ValueError("dependency CAS artifact is not a regular file")
    content = resolved.read_bytes()
    if len(content) != artifact.byte_count:
        raise ValueError("dependency CAS artifact byte count changed")
    if hashlib.sha256(content).hexdigest() != artifact.sha256:
        raise ValueError("dependency CAS artifact SHA-256 changed")
    sri = hashlib.new(artifact.integrity_algorithm, content).digest()
    observed = base64.b64encode(sri).decode("ascii")
    if not hmac.compare_digest(observed, artifact.integrity_digest_base64):
        raise ValueError("dependency CAS artifact no longer matches lockfile SRI")
    return resolved


@dataclass(frozen=True)
class NpmCommandResult:
    exit_code: int
    timed_out: bool
    duration_ms: int


class NpmCommandRunner(Protocol):
    def probe(self, *, cwd: Path, env: dict[str, str]) -> ToolIdentity: ...

    def run(
        self,
        argv: tuple[str, ...],
        *,
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> NpmCommandResult: ...


class SubprocessNpmCommandRunner:
    def _npm_path(self, env: dict[str, str]) -> str:
        resolved = shutil.which("npm", path=env.get("PATH"))
        if not resolved:
            raise ValueError("npm executable is unavailable")
        return str(Path(resolved).resolve())

    def probe(self, *, cwd: Path, env: dict[str, str]) -> ToolIdentity:
        npm = self._npm_path(env)
        try:
            result = subprocess.run(
                (npm, "--version"),
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError("npm version probe failed") from exc
        if result.returncode != 0:
            raise ValueError("npm version probe returned nonzero")
        raw = result.stdout or result.stderr
        if len(raw) > _MAX_VERSION_OUTPUT_BYTES:
            raise ValueError("npm version output exceeded bounded size")
        version = raw.decode("utf-8", errors="replace").strip().splitlines()
        version_text = version[0] if version else "unknown"
        combined = hashlib.sha256()
        combined.update(result.stdout)
        combined.update(result.stderr)
        return ToolIdentity(
            logical_tool="npm",
            executable_path=npm,
            version=version_text[:256],
            version_output_sha256=combined.hexdigest(),
        )

    def run(
        self,
        argv: tuple[str, ...],
        *,
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> NpmCommandResult:
        npm = self._npm_path(env)
        if not argv or argv[0] != "npm":
            raise ValueError("npm adapter command must begin with npm")
        started = time.monotonic()
        try:
            result = subprocess.run(
                (npm, *argv[1:]),
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return NpmCommandResult(
                exit_code=-1,
                timed_out=True,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except OSError as exc:
            raise ValueError("npm cache command failed to launch") from exc
        return NpmCommandResult(
            exit_code=result.returncode,
            timed_out=False,
            duration_ms=int((time.monotonic() - started) * 1000),
        )


@dataclass(frozen=True)
class NpmToolEvidence:
    executable_path: str
    version: str
    version_output_sha256: str

    def __post_init__(self) -> None:
        path = Path(self.executable_path)
        if not path.is_absolute():
            raise ValueError("npm executable_path must be absolute")
        _string(self.version, "npm version", maximum=256)
        _sha256(self.version_output_sha256, "npm version_output_sha256")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_tool_identity(cls, value: ToolIdentity) -> NpmToolEvidence:
        if value.logical_tool != "npm":
            raise ValueError("npm cache adapter requires npm tool identity")
        return cls(
            executable_path=value.executable_path,
            version=value.version,
            version_output_sha256=value.version_output_sha256,
        )

    @classmethod
    def from_dict(cls, value: Any) -> NpmToolEvidence:
        data = _mapping(value, "npm tool evidence")
        if set(data) != {"executable_path", "version", "version_output_sha256"}:
            raise ValueError("npm tool evidence contains missing or unknown fields")
        return cls(
            executable_path=_string(data["executable_path"], "npm executable_path", maximum=4096),
            version=_string(data["version"], "npm version", maximum=256),
            version_output_sha256=_sha256(
                data["version_output_sha256"],
                "npm version_output_sha256",
            ),
        )


@dataclass(frozen=True)
class NpmCacheReceipt:
    receipt_id: str
    timestamp_utc: str
    dependency_receipt_sha256: str
    app_id: str
    repository_url: str
    commit_sha: str
    build_plan_sha256: str
    source_snapshot_sha256: str
    lockfile_sha256: str
    npm_tool: NpmToolEvidence
    cache_path: str
    cache_tree_sha256: str
    cache_file_count: int
    cache_total_bytes: int
    dependency_artifact_count: int
    population_network_control: str
    os_network_namespace_enforced: bool
    status: str
    schema_version: str = NPM_CACHE_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != NPM_CACHE_RECEIPT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported npm cache receipt schema: {self.schema_version}")
        try:
            uuid.UUID(self.receipt_id)
        except ValueError as exc:
            raise ValueError("npm cache receipt_id must be a UUID") from exc
        parsed_time = datetime.fromisoformat(self.timestamp_utc)
        if parsed_time.tzinfo is None:
            raise ValueError("npm cache timestamp must include a timezone")
        if not _COMMIT_RE.fullmatch(self.commit_sha):
            raise ValueError("npm cache commit_sha must be lowercase hexadecimal")
        _sha256(self.dependency_receipt_sha256, "dependency_receipt_sha256")
        _sha256(self.build_plan_sha256, "build_plan_sha256")
        _sha256(self.source_snapshot_sha256, "source_snapshot_sha256")
        _sha256(self.lockfile_sha256, "lockfile_sha256")
        _sha256(self.cache_tree_sha256, "cache_tree_sha256")
        cache = Path(self.cache_path)
        if not cache.is_absolute():
            raise ValueError("npm cache_path must be absolute")
        _int(self.cache_file_count, "cache_file_count", maximum=_MAX_CACHE_FILES)
        _int(self.cache_total_bytes, "cache_total_bytes", maximum=_MAX_CACHE_BYTES)
        _int(
            self.dependency_artifact_count,
            "dependency_artifact_count",
            minimum=1,
            maximum=4096,
        )
        if self.population_network_control != "npm_offline_flag":
            raise ValueError("unsupported npm cache population network control")
        if not isinstance(self.os_network_namespace_enforced, bool):
            raise ValueError("os_network_namespace_enforced must be Boolean")
        if self.status != "ready":
            raise ValueError("npm cache receipt status must be ready")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "timestamp_utc": self.timestamp_utc,
            "dependency_receipt_sha256": self.dependency_receipt_sha256,
            "app_id": self.app_id,
            "repository_url": self.repository_url,
            "commit_sha": self.commit_sha,
            "build_plan_sha256": self.build_plan_sha256,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "lockfile_sha256": self.lockfile_sha256,
            "npm_tool": self.npm_tool.to_dict(),
            "cache_path": self.cache_path,
            "cache_tree_sha256": self.cache_tree_sha256,
            "cache_file_count": self.cache_file_count,
            "cache_total_bytes": self.cache_total_bytes,
            "dependency_artifact_count": self.dependency_artifact_count,
            "population_network_control": self.population_network_control,
            "os_network_namespace_enforced": self.os_network_namespace_enforced,
            "status": self.status,
        }

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["npm_cache_receipt_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> NpmCacheReceipt:
        data = _mapping(value, "npm cache receipt")
        expected = {
            "schema_version",
            "receipt_id",
            "timestamp_utc",
            "dependency_receipt_sha256",
            "app_id",
            "repository_url",
            "commit_sha",
            "build_plan_sha256",
            "source_snapshot_sha256",
            "lockfile_sha256",
            "npm_tool",
            "cache_path",
            "cache_tree_sha256",
            "cache_file_count",
            "cache_total_bytes",
            "dependency_artifact_count",
            "population_network_control",
            "os_network_namespace_enforced",
            "status",
            "npm_cache_receipt_sha256",
        }
        if set(data) != expected:
            raise ValueError("npm cache receipt contains missing or unknown fields")
        receipt = cls(
            schema_version=data["schema_version"],
            receipt_id=_string(data["receipt_id"], "npm cache receipt_id", maximum=64),
            timestamp_utc=_string(data["timestamp_utc"], "npm cache timestamp", maximum=128),
            dependency_receipt_sha256=_sha256(
                data["dependency_receipt_sha256"],
                "dependency_receipt_sha256",
            ),
            app_id=_string(data["app_id"], "npm cache app_id", maximum=64),
            repository_url=_string(
                data["repository_url"],
                "npm cache repository_url",
                maximum=512,
            ),
            commit_sha=_string(data["commit_sha"], "npm cache commit_sha", maximum=64),
            build_plan_sha256=_sha256(data["build_plan_sha256"], "build_plan_sha256"),
            source_snapshot_sha256=_sha256(
                data["source_snapshot_sha256"],
                "source_snapshot_sha256",
            ),
            lockfile_sha256=_sha256(data["lockfile_sha256"], "lockfile_sha256"),
            npm_tool=NpmToolEvidence.from_dict(data["npm_tool"]),
            cache_path=_string(data["cache_path"], "npm cache_path", maximum=4096),
            cache_tree_sha256=_sha256(data["cache_tree_sha256"], "cache_tree_sha256"),
            cache_file_count=_int(
                data["cache_file_count"],
                "cache_file_count",
                maximum=_MAX_CACHE_FILES,
            ),
            cache_total_bytes=_int(
                data["cache_total_bytes"],
                "cache_total_bytes",
                maximum=_MAX_CACHE_BYTES,
            ),
            dependency_artifact_count=_int(
                data["dependency_artifact_count"],
                "dependency_artifact_count",
                minimum=1,
                maximum=4096,
            ),
            population_network_control=_string(
                data["population_network_control"],
                "population_network_control",
                maximum=64,
            ),
            os_network_namespace_enforced=data["os_network_namespace_enforced"],
            status=_string(data["status"], "npm cache status", maximum=32),
        )
        if data["npm_cache_receipt_sha256"] != receipt.sha256():
            raise ValueError("npm cache receipt digest does not match canonical receipt")
        return receipt


@dataclass(frozen=True)
class NpmCachePreparationRequest:
    dependency: DependencyReceipt
    approved_dependency_receipt_sha256: str

    def __post_init__(self) -> None:
        if self.approved_dependency_receipt_sha256 != self.dependency.sha256():
            raise ValueError("Approved dependency receipt SHA-256 does not match receipt")

    @classmethod
    def from_payload(
        cls,
        dependency_receipt_value: Any,
        *,
        approved_dependency_receipt_sha256: str,
    ) -> NpmCachePreparationRequest:
        return cls(
            dependency=DependencyReceipt.from_dict(dependency_receipt_value),
            approved_dependency_receipt_sha256=_sha256(
                approved_dependency_receipt_sha256,
                "approved_dependency_receipt_sha256",
            ),
        )


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(_canonical_json(payload) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


class NpmOfflineCacheService:
    def __init__(
        self,
        *,
        runner: NpmCommandRunner | None = None,
        command_timeout_seconds: int = 120,
    ) -> None:
        self.runner = runner or SubprocessNpmCommandRunner()
        if not 1 <= command_timeout_seconds <= _MAX_COMMAND_SECONDS:
            raise ValueError("npm cache command timeout must be 1-300 seconds")
        self.command_timeout_seconds = command_timeout_seconds

    def prepare(
        self,
        request: NpmCachePreparationRequest,
        *,
        cache_root: Path,
        receipt_root: Path | None = None,
    ) -> NpmCacheReceipt:
        dependency = request.dependency
        store_root = Path(dependency.store_root)
        if store_root.is_symlink():
            raise ValueError("dependency store root must not be a symlink")
        store = store_root.resolve(strict=True)

        verified: list[tuple[StagedDependencyArtifact, Path]] = []
        for artifact in dependency.artifacts:
            verified.append((artifact, _verify_artifact(artifact, store)))

        root = cache_root.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        root = root.resolve(strict=True)
        receipt_id = str(uuid.uuid4())
        final_dir = (
            root
            / dependency.app_id
            / dependency.sha256()
            / receipt_id
            / "npm-cache"
        ).resolve()
        if root != final_dir and root not in final_dir.parents:
            raise ValueError("npm cache destination escaped configured cache root")
        if final_dir.exists():
            raise ValueError("npm cache destination already exists")

        staging_parent = root / ".staging"
        staging_parent.mkdir(parents=True, exist_ok=True)
        staging_dir = Path(
            tempfile.mkdtemp(prefix="npm-cache-", dir=staging_parent)
        ).resolve()
        staging_cache = staging_dir / "cache"
        staging_cache.mkdir()
        input_dir = staging_dir / "inputs"
        input_dir.mkdir()
        home = staging_dir / "home"
        temp_dir = staging_dir / "tmp"
        home.mkdir()
        temp_dir.mkdir()
        npmrc = staging_dir / "npmrc"
        npmrc.write_text("", encoding="utf-8")

        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(home),
            "TMPDIR": str(temp_dir),
            "TMP": str(temp_dir),
            "TEMP": str(temp_dir),
            "NPM_CONFIG_CACHE": str(staging_cache),
            "NPM_CONFIG_USERCONFIG": str(npmrc),
            **_NPM_ENV,
        }

        promoted = False
        try:
            tool = NpmToolEvidence.from_tool_identity(
                self.runner.probe(cwd=staging_dir, env=env)
            )

            for index, (artifact, source) in enumerate(verified):
                local_tarball = input_dir / f"{index:04d}-{artifact.sha256}.tgz"
                shutil.copyfile(source, local_tarball)
                if hashlib.sha256(local_tarball.read_bytes()).hexdigest() != artifact.sha256:
                    raise ValueError("local npm cache input copy changed artifact bytes")
                result = self.runner.run(
                    (
                        "npm",
                        "cache",
                        "add",
                        str(local_tarball),
                        "--cache",
                        str(staging_cache),
                        "--offline",
                    ),
                    cwd=staging_dir,
                    env=env,
                    timeout_seconds=self.command_timeout_seconds,
                )
                if result.timed_out:
                    raise ValueError("npm cache add exceeded execution timeout")
                if result.exit_code != 0:
                    raise ValueError(
                        f"npm cache add exited with code {result.exit_code}"
                    )

            verify_result = self.runner.run(
                (
                    "npm",
                    "cache",
                    "verify",
                    "--cache",
                    str(staging_cache),
                    "--offline",
                ),
                cwd=staging_dir,
                env=env,
                timeout_seconds=self.command_timeout_seconds,
            )
            if verify_result.timed_out:
                raise ValueError("npm cache verify exceeded execution timeout")
            if verify_result.exit_code != 0:
                raise ValueError(
                    f"npm cache verify exited with code {verify_result.exit_code}"
                )

            cache_sha, file_count, total_bytes = _snapshot_tree(staging_cache)
            final_dir.parent.mkdir(parents=True, exist_ok=True)
            staging_cache.replace(final_dir)
            promoted = True
            final_sha, final_count, final_bytes = _snapshot_tree(final_dir)
            if (cache_sha, file_count, total_bytes) != (
                final_sha,
                final_count,
                final_bytes,
            ):
                raise ValueError("promoted npm cache changed after verification")

            receipt = NpmCacheReceipt(
                receipt_id=receipt_id,
                timestamp_utc=datetime.now(UTC).isoformat(),
                dependency_receipt_sha256=dependency.sha256(),
                app_id=dependency.app_id,
                repository_url=dependency.repository_url,
                commit_sha=dependency.commit_sha,
                build_plan_sha256=dependency.build_plan_sha256,
                source_snapshot_sha256=dependency.source_snapshot_sha256,
                lockfile_sha256=dependency.lockfile_sha256,
                npm_tool=tool,
                cache_path=str(final_dir),
                cache_tree_sha256=final_sha,
                cache_file_count=final_count,
                cache_total_bytes=final_bytes,
                dependency_artifact_count=len(dependency.artifacts),
                population_network_control="npm_offline_flag",
                os_network_namespace_enforced=False,
                status="ready",
            )
            receipts = (
                receipt_root or (root / ".phios-receipts")
            ).expanduser().resolve()
            receipt_path = receipts / f"npm-cache-{receipt_id}.json"
            _write_json_atomic(receipt_path, receipt.to_dict())
            return receipt
        except Exception:
            if promoted:
                shutil.rmtree(final_dir.parent, ignore_errors=True)
            raise
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)


@dataclass(frozen=True)
class NpmOfflineBuildPlan:
    original_build_plan_sha256: str
    npm_cache_receipt_sha256: str
    dependency_receipt_sha256: str
    cache_tree_sha256: str
    cache_mount_target: str
    derived_build_plan: BuildPlan
    schema_version: str = NPM_OFFLINE_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != NPM_OFFLINE_PLAN_SCHEMA_VERSION:
            raise ValueError(f"Unsupported npm offline plan schema: {self.schema_version}")
        _sha256(self.original_build_plan_sha256, "original_build_plan_sha256")
        _sha256(self.npm_cache_receipt_sha256, "npm_cache_receipt_sha256")
        _sha256(self.dependency_receipt_sha256, "dependency_receipt_sha256")
        _sha256(self.cache_tree_sha256, "cache_tree_sha256")
        if self.cache_mount_target != _NPM_CACHE_MOUNT:
            raise ValueError("unsupported npm cache mount target")
        if any(step.requires_network for step in self.derived_build_plan.steps):
            raise ValueError("npm offline derived plan must contain no network-requiring steps")
        if "build.network.dependencies" in self.derived_build_plan.requested_build_permissions:
            raise ValueError("npm offline derived plan must not request network permission")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "original_build_plan_sha256": self.original_build_plan_sha256,
            "npm_cache_receipt_sha256": self.npm_cache_receipt_sha256,
            "dependency_receipt_sha256": self.dependency_receipt_sha256,
            "cache_tree_sha256": self.cache_tree_sha256,
            "cache_mount_target": self.cache_mount_target,
            "derived_build_plan": self.derived_build_plan.to_dict(),
        }

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["npm_offline_plan_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> NpmOfflineBuildPlan:
        data = _mapping(value, "npm offline build plan")
        expected = {
            "schema_version",
            "original_build_plan_sha256",
            "npm_cache_receipt_sha256",
            "dependency_receipt_sha256",
            "cache_tree_sha256",
            "cache_mount_target",
            "derived_build_plan",
            "npm_offline_plan_sha256",
        }
        if set(data) != expected:
            raise ValueError("npm offline build plan contains missing or unknown fields")
        plan = cls(
            schema_version=data["schema_version"],
            original_build_plan_sha256=_sha256(
                data["original_build_plan_sha256"],
                "original_build_plan_sha256",
            ),
            npm_cache_receipt_sha256=_sha256(
                data["npm_cache_receipt_sha256"],
                "npm_cache_receipt_sha256",
            ),
            dependency_receipt_sha256=_sha256(
                data["dependency_receipt_sha256"],
                "dependency_receipt_sha256",
            ),
            cache_tree_sha256=_sha256(data["cache_tree_sha256"], "cache_tree_sha256"),
            cache_mount_target=_string(
                data["cache_mount_target"],
                "cache_mount_target",
                maximum=128,
            ),
            derived_build_plan=BuildPlan.from_dict(data["derived_build_plan"]),
        )
        if data["npm_offline_plan_sha256"] != plan.sha256():
            raise ValueError("npm offline build plan digest does not match canonical plan")
        return plan


def derive_npm_offline_build_plan(
    build_plan_value: Any,
    npm_cache_receipt_value: Any,
) -> NpmOfflineBuildPlan:
    original = BuildPlan.from_dict(build_plan_value)
    cache = NpmCacheReceipt.from_dict(npm_cache_receipt_value)

    if original.sha256() != cache.build_plan_sha256:
        raise ValueError("npm cache receipt does not bind the supplied build plan")
    if original.app_id != cache.app_id:
        raise ValueError("npm cache receipt app_id does not match build plan")
    if original.repository_url.lower() != cache.repository_url.lower():
        raise ValueError("npm cache receipt repository does not match build plan")
    if original.commit_sha != cache.commit_sha:
        raise ValueError("npm cache receipt commit does not match build plan")
    if original.source_snapshot_sha256 != cache.source_snapshot_sha256:
        raise ValueError("npm cache receipt source snapshot does not match build plan")
    if original.package_manager != "npm" or original.status != "ready_for_review":
        raise ValueError("v0.32 requires a ready_for_review npm build plan")

    dependency_steps = [
        step
        for step in original.steps
        if step.phase == "dependencies" and step.tool == "npm"
    ]
    if len(dependency_steps) != 1:
        raise ValueError("v0.32 requires exactly one npm dependency step")
    dependency_step = dependency_steps[0]
    if dependency_step.argv != ("npm", "ci"):
        raise ValueError("v0.32 currently rewrites only the exact reviewed npm ci step")
    if not dependency_step.requires_network:
        raise ValueError("v0.32 expects the original npm ci step to require network")

    derived_steps: list[BuildStep] = []
    for step in original.steps:
        if step.step_id == dependency_step.step_id:
            derived_steps.append(
                BuildStep(
                    step_id=step.step_id,
                    phase=step.phase,
                    tool=step.tool,
                    argv=(
                        "npm",
                        "ci",
                        "--offline",
                        "--cache",
                        _NPM_CACHE_MOUNT,
                    ),
                    working_directory=step.working_directory,
                    requires_network=False,
                )
            )
        else:
            derived_steps.append(step)

    permissions = tuple(
        permission
        for permission in original.requested_build_permissions
        if permission != "build.network.dependencies"
    )
    notes = (
        *original.notes,
        f"v0.32 derived from build plan {original.sha256()}",
        f"v0.32 binds npm cache receipt {cache.sha256()}",
        "npm dependency installation is forced offline and cache-mounted at /phios/npm-cache",
    )
    derived = BuildPlan(
        app_id=original.app_id,
        repository_url=original.repository_url,
        commit_sha=original.commit_sha,
        manifest_sha256=original.manifest_sha256,
        acquisition_tree_sha256=original.acquisition_tree_sha256,
        source_snapshot_sha256=original.source_snapshot_sha256,
        source_file_count=original.source_file_count,
        source_total_bytes=original.source_total_bytes,
        runtime=original.runtime,
        strategy=f"{original.strategy}_offline_npm_v032",
        package_manager=original.package_manager,
        working_directory=original.working_directory,
        required_tools=original.required_tools,
        requested_build_permissions=permissions,
        steps=tuple(derived_steps),
        expected_outputs=original.expected_outputs,
        observed_files=original.observed_files,
        status=original.status,
        notes=notes,
    )
    return NpmOfflineBuildPlan(
        original_build_plan_sha256=original.sha256(),
        npm_cache_receipt_sha256=cache.sha256(),
        dependency_receipt_sha256=cache.dependency_receipt_sha256,
        cache_tree_sha256=cache.cache_tree_sha256,
        cache_mount_target=_NPM_CACHE_MOUNT,
        derived_build_plan=derived,
    )


@dataclass(frozen=True)
class NpmOfflineBuildPlanReview:
    npm_offline_plan_sha256: str
    original_build_plan_sha256: str
    derived_build_plan_sha256: str
    npm_cache_receipt_sha256: str
    source_snapshot_sha256: str
    requested_build_permissions: tuple[str, ...]
    cache_mount_target: str
    network_required: bool
    schema_version: str = NPM_OFFLINE_PLAN_REVIEW_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "npm_offline_plan_sha256": self.npm_offline_plan_sha256,
            "original_build_plan_sha256": self.original_build_plan_sha256,
            "derived_build_plan_sha256": self.derived_build_plan_sha256,
            "npm_cache_receipt_sha256": self.npm_cache_receipt_sha256,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "requested_build_permissions": list(self.requested_build_permissions),
            "cache_mount_target": self.cache_mount_target,
            "network_required": self.network_required,
        }


def review_npm_offline_build_plan(value: Any) -> NpmOfflineBuildPlanReview:
    plan = NpmOfflineBuildPlan.from_dict(value)
    derived = plan.derived_build_plan
    return NpmOfflineBuildPlanReview(
        npm_offline_plan_sha256=plan.sha256(),
        original_build_plan_sha256=plan.original_build_plan_sha256,
        derived_build_plan_sha256=derived.sha256(),
        npm_cache_receipt_sha256=plan.npm_cache_receipt_sha256,
        source_snapshot_sha256=derived.source_snapshot_sha256,
        requested_build_permissions=derived.requested_build_permissions,
        cache_mount_target=plan.cache_mount_target,
        network_required=any(step.requires_network for step in derived.steps),
    )


@dataclass(frozen=True)
class NpmOfflineBuildRequest:
    offline_plan: NpmOfflineBuildPlan
    acquisition: AcquisitionBinding
    npm_cache: NpmCacheReceipt
    approved_offline_plan_sha256: str

    def __post_init__(self) -> None:
        plan = self.offline_plan
        derived = plan.derived_build_plan
        cache = self.npm_cache
        if self.approved_offline_plan_sha256 != plan.sha256():
            raise ValueError("Approved npm offline plan SHA-256 does not match canonical plan")
        if cache.sha256() != plan.npm_cache_receipt_sha256:
            raise ValueError("npm cache receipt does not match offline plan")
        if cache.cache_tree_sha256 != plan.cache_tree_sha256:
            raise ValueError("npm cache tree does not match offline plan")
        if cache.app_id != derived.app_id:
            raise ValueError("npm cache app_id does not match derived build plan")
        if cache.repository_url.lower() != derived.repository_url.lower():
            raise ValueError("npm cache repository does not match derived build plan")
        if cache.commit_sha != derived.commit_sha:
            raise ValueError("npm cache commit does not match derived build plan")
        if cache.source_snapshot_sha256 != derived.source_snapshot_sha256:
            raise ValueError("npm cache source snapshot does not match derived build plan")
        if self.acquisition.app_id != derived.app_id:
            raise ValueError("acquisition app_id does not match offline plan")
        if self.acquisition.commit_sha != derived.commit_sha:
            raise ValueError("acquisition commit does not match offline plan")

    @classmethod
    def from_payloads(
        cls,
        offline_plan_value: Any,
        acquisition_receipt_value: Any,
        npm_cache_receipt_value: Any,
        *,
        approved_offline_plan_sha256: str,
    ) -> NpmOfflineBuildRequest:
        acquisition_data = _mapping(acquisition_receipt_value, "acquisition receipt")
        if acquisition_data.get("schema_version") != SOURCE_ACQUISITION_RECEIPT_SCHEMA_VERSION:
            raise ValueError("v0.32 requires a v0.27 acquisition receipt")
        return cls(
            offline_plan=NpmOfflineBuildPlan.from_dict(offline_plan_value),
            acquisition=AcquisitionBinding.from_dict(acquisition_receipt_value),
            npm_cache=NpmCacheReceipt.from_dict(npm_cache_receipt_value),
            approved_offline_plan_sha256=_sha256(
                approved_offline_plan_sha256,
                "approved_offline_plan_sha256",
            ),
        )


@dataclass(frozen=True)
class NpmOfflineBuildReceipt:
    receipt_id: str
    timestamp_utc: str
    app_id: str
    commit_sha: str
    npm_offline_plan_sha256: str
    original_build_plan_sha256: str
    derived_build_plan_sha256: str
    npm_cache_receipt_sha256: str
    cache_tree_sha256: str
    cache_mount_target: str
    build_execution_receipt_sha256: str
    sandbox_receipt_sha256: str
    network_mode: str
    build_status: str
    schema_version: str = NPM_OFFLINE_BUILD_RECEIPT_SCHEMA_VERSION

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "timestamp_utc": self.timestamp_utc,
            "app_id": self.app_id,
            "commit_sha": self.commit_sha,
            "npm_offline_plan_sha256": self.npm_offline_plan_sha256,
            "original_build_plan_sha256": self.original_build_plan_sha256,
            "derived_build_plan_sha256": self.derived_build_plan_sha256,
            "npm_cache_receipt_sha256": self.npm_cache_receipt_sha256,
            "cache_tree_sha256": self.cache_tree_sha256,
            "cache_mount_target": self.cache_mount_target,
            "build_execution_receipt_sha256": self.build_execution_receipt_sha256,
            "sandbox_receipt_sha256": self.sandbox_receipt_sha256,
            "network_mode": self.network_mode,
            "build_status": self.build_status,
        }

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["npm_offline_build_receipt_sha256"] = self.sha256()
        return result


@dataclass(frozen=True)
class NpmOfflineBuildResult:
    sandboxed_build: SandboxedBuildExecutionResult
    offline_receipt: NpmOfflineBuildReceipt
    offline_receipt_path: str | None
    offline_receipt_persisted: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "sandboxed_build": self.sandboxed_build.to_dict(),
            "offline_receipt": self.offline_receipt.to_dict(),
            "offline_receipt_path": self.offline_receipt_path,
            "offline_receipt_persisted": self.offline_receipt_persisted,
        }


SandboxRunnerFactory = Callable[
    [BuildSandboxPolicy, Path],
    SandboxBuildRunner,
]


def _default_sandbox_runner(
    policy: BuildSandboxPolicy,
    working_cache: Path,
) -> SandboxBuildRunner:
    return BubblewrapSandboxRunner(
        policy,
        extra_read_write_binds=((working_cache, _NPM_CACHE_MOUNT),),
        extra_environment={
            **_NPM_ENV,
            "NPM_CONFIG_CACHE": _NPM_CACHE_MOUNT,
        },
    )


class NpmOfflineBuildService:
    def __init__(
        self,
        *,
        runner_factory: SandboxRunnerFactory | None = None,
        sandbox_policy: BuildSandboxPolicy | None = None,
    ) -> None:
        self.runner_factory = runner_factory or _default_sandbox_runner
        self.policy = sandbox_policy or BuildSandboxPolicy(network_mode="deny")
        if self.policy.network_mode != "deny":
            raise ValueError("v0.32 offline build requires sandbox network_mode=deny")

    def execute(
        self,
        request: NpmOfflineBuildRequest,
        *,
        execution_root: Path,
        receipt_root: Path | None = None,
    ) -> NpmOfflineBuildResult:
        offline = request.offline_plan
        derived = offline.derived_build_plan
        cache = request.npm_cache

        cache_path = Path(cache.cache_path)
        if cache_path.is_symlink():
            raise ValueError("receipted npm cache path must not be a symlink")
        source_cache = cache_path.resolve(strict=True)
        current_sha, current_files, current_bytes = _snapshot_tree(source_cache)
        if current_sha != cache.cache_tree_sha256:
            raise ValueError("receipted npm cache tree changed before execution")
        if current_files != cache.cache_file_count or current_bytes != cache.cache_total_bytes:
            raise ValueError("receipted npm cache totals changed before execution")

        root = execution_root.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        root = root.resolve(strict=True)
        cache_work_id = str(uuid.uuid4())
        working_cache = (
            root
            / ".npm-cache-work"
            / derived.app_id
            / offline.sha256()
            / cache_work_id
        ).resolve()
        if root != working_cache and root not in working_cache.parents:
            raise ValueError("npm working cache escaped execution root")
        if working_cache.exists():
            raise ValueError("npm working cache already exists")
        working_cache.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_cache, working_cache, symlinks=True)
        copied_sha, copied_files, copied_bytes = _snapshot_tree(working_cache)
        if (copied_sha, copied_files, copied_bytes) != (
            current_sha,
            current_files,
            current_bytes,
        ):
            shutil.rmtree(working_cache, ignore_errors=True)
            raise ValueError("npm working cache copy does not match receipted cache")

        execution_request = BuildExecutionRequest(
            plan=derived,
            acquisition=request.acquisition,
            approved_plan_sha256=derived.sha256(),
            approved_source_snapshot_sha256=derived.source_snapshot_sha256,
            approved_permissions=derived.requested_build_permissions,
        )
        runner = self.runner_factory(self.policy, working_cache)

        receipts = (
            receipt_root or (root / ".phios-receipts" / "v032")
        ).expanduser().resolve()
        underlying_receipts = receipts / "underlying"

        try:
            sandbox_result = SandboxedBuildExecutionService(
                self.policy,
                runner=runner,
            ).execute(
                execution_request,
                execution_root=root,
                receipt_root=underlying_receipts,
            )
        except Exception:
            shutil.rmtree(working_cache, ignore_errors=True)
            raise

        offline_receipt = NpmOfflineBuildReceipt(
            receipt_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(UTC).isoformat(),
            app_id=derived.app_id,
            commit_sha=derived.commit_sha,
            npm_offline_plan_sha256=offline.sha256(),
            original_build_plan_sha256=offline.original_build_plan_sha256,
            derived_build_plan_sha256=derived.sha256(),
            npm_cache_receipt_sha256=cache.sha256(),
            cache_tree_sha256=cache.cache_tree_sha256,
            cache_mount_target=offline.cache_mount_target,
            build_execution_receipt_sha256=sandbox_result.execution.sha256(),
            sandbox_receipt_sha256=sandbox_result.sandbox.sha256(),
            network_mode="deny",
            build_status=sandbox_result.execution.status,
        )
        offline_path = receipts / f"npm-offline-{offline_receipt.receipt_id}.json"
        persisted = True
        path_text: str | None = str(offline_path)
        try:
            _write_json_atomic(offline_path, offline_receipt.to_dict())
        except OSError:
            persisted = False
            path_text = None

        return NpmOfflineBuildResult(
            sandboxed_build=sandbox_result,
            offline_receipt=offline_receipt,
            offline_receipt_path=path_text,
            offline_receipt_persisted=persisted,
        )
