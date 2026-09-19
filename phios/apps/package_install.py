from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, cast

from .manifest import AppManifest
from .registry import AppRegistry

BUILD_PACKAGE_PLAN_SCHEMA_VERSION = "phios.build_package_plan.v0.1"
BUILD_PACKAGE_REVIEW_SCHEMA_VERSION = "phios.build_package_plan_review.v0.1"
APP_INSTALL_RECEIPT_SCHEMA_VERSION = "phios.app_install_receipt.v0.1"
APP_UNINSTALL_RECEIPT_SCHEMA_VERSION = "phios.app_uninstall_receipt.v0.1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40,64}$")
_MAX_ARTIFACTS = 2048
_MAX_FILE_BYTES = 64 * 1024 * 1024
_MAX_TOTAL_BYTES = 256 * 1024 * 1024


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


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _safe_relative(value: Any, label: str) -> str:
    text = _string(value, label, maximum=1024)
    if "\\" in text or text.startswith("/"):
        raise ValueError(f"{label} must be a relative POSIX path")
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{label} contains unsafe path segments")
    return text


@dataclass(frozen=True)
class PackageArtifact:
    path: str
    byte_count: int
    sha256: str

    def __post_init__(self) -> None:
        _safe_relative(self.path, "package artifact path")
        if not isinstance(self.byte_count, int) or isinstance(self.byte_count, bool):
            raise ValueError("package artifact byte_count must be an integer")
        if not 0 <= self.byte_count <= _MAX_FILE_BYTES:
            raise ValueError("package artifact byte_count is out of bounds")
        _sha256(self.sha256, "package artifact sha256")

    def canonical_line(self) -> bytes:
        return f"{self.path}\0{self.byte_count}\0{self.sha256}\n".encode("utf-8")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Any) -> PackageArtifact:
        data = _mapping(value, "package artifact")
        if set(data) != {"path", "byte_count", "sha256"}:
            raise ValueError("package artifact contains missing or unknown fields")
        return cls(
            path=_safe_relative(data["path"], "package artifact path"),
            byte_count=data["byte_count"],
            sha256=_sha256(data["sha256"], "package artifact sha256"),
        )


def _artifact_set_sha256(artifacts: tuple[PackageArtifact, ...]) -> str:
    digest = hashlib.sha256()
    for artifact in sorted(artifacts, key=lambda item: item.path):
        digest.update(artifact.canonical_line())
    return digest.hexdigest()


@dataclass(frozen=True)
class SuccessfulBuildBinding:
    execution_id: str
    execution_receipt_sha256: str
    offline_build_receipt_sha256: str
    app_id: str
    repository_url: str
    commit_sha: str
    build_plan_sha256: str
    source_snapshot_sha256: str
    artifact_set_sha256: str
    execution_workspace_path: str
    artifacts: tuple[PackageArtifact, ...]
    network_sandbox_enforced: bool

    @classmethod
    def from_payloads(
        cls,
        build_execution_receipt_value: Any,
        offline_build_receipt_value: Any,
    ) -> SuccessfulBuildBinding:
        execution = _mapping(build_execution_receipt_value, "build execution receipt")
        offline = _mapping(offline_build_receipt_value, "offline build receipt")

        required_execution = {
            "schema_version",
            "execution_id",
            "timestamp_utc",
            "app_id",
            "repository_url",
            "commit_sha",
            "plan_sha256",
            "source_snapshot_sha256",
            "acquisition_tree_sha256",
            "approved_permissions",
            "isolation_mode",
            "network_sandbox_enforced",
            "source_workspace_path",
            "execution_workspace_path",
            "tool_identities",
            "steps",
            "artifacts",
            "artifact_set_sha256",
            "status",
            "failure_reason",
            "receipt_sha256",
        }
        if set(execution) != required_execution:
            raise ValueError("build execution receipt contains missing or unknown fields")
        if execution["schema_version"] != "phios.build_execution_receipt.v0.1":
            raise ValueError("v0.33 requires a v0.29 build execution receipt")
        if execution["status"] != "success":
            raise ValueError("v0.33 packages only successful builds")
        if execution["failure_reason"] is not None:
            raise ValueError("successful build receipt must not contain failure_reason")
        if execution["network_sandbox_enforced"] is not True:
            raise ValueError("v0.33 requires network-sandboxed build evidence")

        execution_body = dict(execution)
        supplied_execution_sha = _sha256(
            execution_body.pop("receipt_sha256"),
            "build execution receipt_sha256",
        )
        observed_execution_sha = hashlib.sha256(
            _canonical_json(execution_body).encode("utf-8")
        ).hexdigest()
        if supplied_execution_sha != observed_execution_sha:
            raise ValueError("build execution receipt digest does not match canonical receipt")

        raw_artifacts = execution["artifacts"]
        if not isinstance(raw_artifacts, list):
            raise ValueError("build execution artifacts must be an array")
        artifacts = tuple(PackageArtifact.from_dict(item) for item in raw_artifacts)
        if not 1 <= len(artifacts) <= _MAX_ARTIFACTS:
            raise ValueError("build execution artifact count is out of bounds")
        if tuple(sorted(item.path for item in artifacts)) != tuple(item.path for item in artifacts):
            raise ValueError("build execution artifacts must be sorted by path")
        if len({item.path for item in artifacts}) != len(artifacts):
            raise ValueError("build execution artifacts contain duplicate paths")
        if sum(item.byte_count for item in artifacts) > _MAX_TOTAL_BYTES:
            raise ValueError("build execution artifacts exceed bounded total bytes")
        if _artifact_set_sha256(artifacts) != execution["artifact_set_sha256"]:
            raise ValueError("build execution artifact-set digest does not match artifacts")

        required_offline = {
            "schema_version",
            "receipt_id",
            "timestamp_utc",
            "app_id",
            "commit_sha",
            "npm_offline_plan_sha256",
            "original_build_plan_sha256",
            "derived_build_plan_sha256",
            "npm_cache_receipt_sha256",
            "cache_tree_sha256",
            "cache_mount_target",
            "build_execution_receipt_sha256",
            "sandbox_receipt_sha256",
            "network_mode",
            "network_namespace_enforced",
            "build_status",
            "npm_offline_build_receipt_sha256",
        }
        if set(offline) != required_offline:
            raise ValueError("offline build receipt contains missing or unknown fields")
        if offline["schema_version"] != "phios.npm_offline_build_receipt.v0.1":
            raise ValueError("v0.33 requires a v0.32 npm offline build receipt")
        offline_body = dict(offline)
        supplied_offline_sha = _sha256(
            offline_body.pop("npm_offline_build_receipt_sha256"),
            "npm offline build receipt sha256",
        )
        observed_offline_sha = hashlib.sha256(
            _canonical_json(offline_body).encode("utf-8")
        ).hexdigest()
        if supplied_offline_sha != observed_offline_sha:
            raise ValueError("offline build receipt digest does not match canonical receipt")
        if offline["build_status"] != "success":
            raise ValueError("v0.33 requires successful offline build status")
        if offline["network_mode"] != "deny" or offline["network_namespace_enforced"] is not True:
            raise ValueError("v0.33 requires enforced network-denied build evidence")
        if offline["build_execution_receipt_sha256"] != supplied_execution_sha:
            raise ValueError("offline build receipt does not bind supplied execution receipt")
        if offline["app_id"] != execution["app_id"]:
            raise ValueError("offline build app_id does not match execution receipt")
        if offline["commit_sha"] != execution["commit_sha"]:
            raise ValueError("offline build commit does not match execution receipt")
        if offline["derived_build_plan_sha256"] != execution["plan_sha256"]:
            raise ValueError("offline build derived plan does not match execution receipt")

        commit = _string(execution["commit_sha"], "build commit_sha", maximum=64)
        if not _COMMIT_RE.fullmatch(commit):
            raise ValueError("build commit_sha must be lowercase hexadecimal")
        workspace = Path(
            _string(
                execution["execution_workspace_path"],
                "execution_workspace_path",
                maximum=4096,
            )
        )
        if not workspace.is_absolute():
            raise ValueError("execution_workspace_path must be absolute")

        return cls(
            execution_id=_string(execution["execution_id"], "execution_id", maximum=64),
            execution_receipt_sha256=supplied_execution_sha,
            offline_build_receipt_sha256=supplied_offline_sha,
            app_id=_string(execution["app_id"], "build app_id", maximum=64),
            repository_url=_string(
                execution["repository_url"],
                "build repository_url",
                maximum=512,
            ),
            commit_sha=commit,
            build_plan_sha256=_sha256(execution["plan_sha256"], "build plan_sha256"),
            source_snapshot_sha256=_sha256(
                execution["source_snapshot_sha256"],
                "source snapshot sha256",
            ),
            artifact_set_sha256=_sha256(
                execution["artifact_set_sha256"],
                "artifact_set_sha256",
            ),
            execution_workspace_path=str(workspace),
            artifacts=artifacts,
            network_sandbox_enforced=True,
        )


@dataclass(frozen=True)
class BuildPackagePlan:
    app_id: str
    app_version: str
    manifest_sha256: str
    registry_snapshot_sha256: str
    repository_url: str
    commit_sha: str
    build_plan_sha256: str
    execution_receipt_sha256: str
    offline_build_receipt_sha256: str
    artifact_set_sha256: str
    artifacts: tuple[PackageArtifact, ...]
    install_relative_path: str
    launch_authority: bool = False
    schema_version: str = BUILD_PACKAGE_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != BUILD_PACKAGE_PLAN_SCHEMA_VERSION:
            raise ValueError(f"Unsupported build package plan schema: {self.schema_version}")
        _string(self.app_id, "package app_id", maximum=64)
        _string(self.app_version, "package app_version", maximum=128)
        for value, label in (
            (self.manifest_sha256, "manifest_sha256"),
            (self.registry_snapshot_sha256, "registry_snapshot_sha256"),
            (self.build_plan_sha256, "build_plan_sha256"),
            (self.execution_receipt_sha256, "execution_receipt_sha256"),
            (self.offline_build_receipt_sha256, "offline_build_receipt_sha256"),
            (self.artifact_set_sha256, "artifact_set_sha256"),
        ):
            _sha256(value, label)
        if not _COMMIT_RE.fullmatch(self.commit_sha):
            raise ValueError("package commit_sha must be lowercase hexadecimal")
        if not 1 <= len(self.artifacts) <= _MAX_ARTIFACTS:
            raise ValueError("package artifact count is out of bounds")
        if _artifact_set_sha256(self.artifacts) != self.artifact_set_sha256:
            raise ValueError("package artifact-set digest mismatch")
        _safe_relative(self.install_relative_path, "install_relative_path")
        if self.launch_authority is not False:
            raise ValueError("v0.33 package plans never grant launch authority")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app_id": self.app_id,
            "app_version": self.app_version,
            "manifest_sha256": self.manifest_sha256,
            "registry_snapshot_sha256": self.registry_snapshot_sha256,
            "repository_url": self.repository_url,
            "commit_sha": self.commit_sha,
            "build_plan_sha256": self.build_plan_sha256,
            "execution_receipt_sha256": self.execution_receipt_sha256,
            "offline_build_receipt_sha256": self.offline_build_receipt_sha256,
            "artifact_set_sha256": self.artifact_set_sha256,
            "artifacts": [item.to_dict() for item in self.artifacts],
            "install_relative_path": self.install_relative_path,
            "launch_authority": self.launch_authority,
        }

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["package_plan_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> BuildPackagePlan:
        data = _mapping(value, "build package plan")
        expected = {
            "schema_version",
            "app_id",
            "app_version",
            "manifest_sha256",
            "registry_snapshot_sha256",
            "repository_url",
            "commit_sha",
            "build_plan_sha256",
            "execution_receipt_sha256",
            "offline_build_receipt_sha256",
            "artifact_set_sha256",
            "artifacts",
            "install_relative_path",
            "launch_authority",
            "package_plan_sha256",
        }
        if set(data) != expected:
            raise ValueError("build package plan contains missing or unknown fields")
        raw_artifacts = data["artifacts"]
        if not isinstance(raw_artifacts, list):
            raise ValueError("build package plan artifacts must be an array")
        plan = cls(
            schema_version=data["schema_version"],
            app_id=_string(data["app_id"], "package app_id", maximum=64),
            app_version=_string(data["app_version"], "package app_version", maximum=128),
            manifest_sha256=_sha256(data["manifest_sha256"], "manifest_sha256"),
            registry_snapshot_sha256=_sha256(
                data["registry_snapshot_sha256"],
                "registry_snapshot_sha256",
            ),
            repository_url=_string(
                data["repository_url"],
                "package repository_url",
                maximum=512,
            ),
            commit_sha=_string(data["commit_sha"], "package commit_sha", maximum=64),
            build_plan_sha256=_sha256(data["build_plan_sha256"], "build_plan_sha256"),
            execution_receipt_sha256=_sha256(
                data["execution_receipt_sha256"],
                "execution_receipt_sha256",
            ),
            offline_build_receipt_sha256=_sha256(
                data["offline_build_receipt_sha256"],
                "offline_build_receipt_sha256",
            ),
            artifact_set_sha256=_sha256(
                data["artifact_set_sha256"],
                "artifact_set_sha256",
            ),
            artifacts=tuple(PackageArtifact.from_dict(item) for item in raw_artifacts),
            install_relative_path=_safe_relative(
                data["install_relative_path"],
                "install_relative_path",
            ),
            launch_authority=data["launch_authority"],
        )
        if data["package_plan_sha256"] != plan.sha256():
            raise ValueError("build package plan digest does not match canonical plan")
        return plan


@dataclass(frozen=True)
class BuildPackageReview:
    package_plan_sha256: str
    app_id: str
    app_version: str
    manifest_sha256: str
    registry_snapshot_sha256: str
    artifact_set_sha256: str
    artifact_count: int
    install_relative_path: str
    launch_authority: bool
    schema_version: str = BUILD_PACKAGE_REVIEW_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def plan_build_package(
    manifest_value: Any,
    registry: AppRegistry,
    build_execution_receipt_value: Any,
    offline_build_receipt_value: Any,
) -> BuildPackagePlan:
    manifest = AppManifest.from_dict(manifest_value)
    binding = SuccessfulBuildBinding.from_payloads(
        build_execution_receipt_value,
        offline_build_receipt_value,
    )
    if manifest.app_id != binding.app_id:
        raise ValueError("manifest app_id does not match successful build")
    if manifest.source.repository_url.lower() != binding.repository_url.lower():
        raise ValueError("manifest repository does not match successful build")
    registered = registry.get(manifest.app_id)
    if registered.sha256() != manifest.sha256():
        raise ValueError("registry manifest does not match supplied manifest")

    install_relative = PurePosixPath(
        manifest.app_id,
        manifest.version,
        binding.artifact_set_sha256[:16],
    ).as_posix()
    return BuildPackagePlan(
        app_id=manifest.app_id,
        app_version=manifest.version,
        manifest_sha256=manifest.sha256(),
        registry_snapshot_sha256=registry.snapshot_sha256(),
        repository_url=binding.repository_url,
        commit_sha=binding.commit_sha,
        build_plan_sha256=binding.build_plan_sha256,
        execution_receipt_sha256=binding.execution_receipt_sha256,
        offline_build_receipt_sha256=binding.offline_build_receipt_sha256,
        artifact_set_sha256=binding.artifact_set_sha256,
        artifacts=binding.artifacts,
        install_relative_path=install_relative,
        launch_authority=False,
    )


def review_build_package(value: Any) -> BuildPackageReview:
    plan = BuildPackagePlan.from_dict(value)
    return BuildPackageReview(
        package_plan_sha256=plan.sha256(),
        app_id=plan.app_id,
        app_version=plan.app_version,
        manifest_sha256=plan.manifest_sha256,
        registry_snapshot_sha256=plan.registry_snapshot_sha256,
        artifact_set_sha256=plan.artifact_set_sha256,
        artifact_count=len(plan.artifacts),
        install_relative_path=plan.install_relative_path,
        launch_authority=plan.launch_authority,
    )


@dataclass(frozen=True)
class AppInstallReceipt:
    receipt_id: str
    timestamp_utc: str
    app_id: str
    app_version: str
    package_plan_sha256: str
    manifest_sha256: str
    registry_snapshot_sha256: str
    build_plan_sha256: str
    execution_receipt_sha256: str
    offline_build_receipt_sha256: str
    artifact_set_sha256: str
    installed_payload_sha256: str
    artifact_count: int
    total_bytes: int
    install_path: str
    launch_authority: bool
    status: str
    schema_version: str = APP_INSTALL_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != APP_INSTALL_RECEIPT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported app install receipt schema: {self.schema_version}")
        if self.launch_authority is not False:
            raise ValueError("v0.33 install receipts never grant launch authority")
        if self.status != "installed":
            raise ValueError("v0.33 install receipt status must be installed")

    def body_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["install_receipt_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> AppInstallReceipt:
        data = _mapping(value, "app install receipt")
        expected = {
            "schema_version",
            "receipt_id",
            "timestamp_utc",
            "app_id",
            "app_version",
            "package_plan_sha256",
            "manifest_sha256",
            "registry_snapshot_sha256",
            "build_plan_sha256",
            "execution_receipt_sha256",
            "offline_build_receipt_sha256",
            "artifact_set_sha256",
            "installed_payload_sha256",
            "artifact_count",
            "total_bytes",
            "install_path",
            "launch_authority",
            "status",
            "install_receipt_sha256",
        }
        if set(data) != expected:
            raise ValueError("app install receipt contains missing or unknown fields")
        receipt = cls(
            schema_version=data["schema_version"],
            receipt_id=_string(data["receipt_id"], "install receipt_id", maximum=64),
            timestamp_utc=_string(data["timestamp_utc"], "install timestamp", maximum=128),
            app_id=_string(data["app_id"], "install app_id", maximum=64),
            app_version=_string(data["app_version"], "install app_version", maximum=128),
            package_plan_sha256=_sha256(data["package_plan_sha256"], "package_plan_sha256"),
            manifest_sha256=_sha256(data["manifest_sha256"], "manifest_sha256"),
            registry_snapshot_sha256=_sha256(
                data["registry_snapshot_sha256"],
                "registry_snapshot_sha256",
            ),
            build_plan_sha256=_sha256(data["build_plan_sha256"], "build_plan_sha256"),
            execution_receipt_sha256=_sha256(
                data["execution_receipt_sha256"],
                "execution_receipt_sha256",
            ),
            offline_build_receipt_sha256=_sha256(
                data["offline_build_receipt_sha256"],
                "offline_build_receipt_sha256",
            ),
            artifact_set_sha256=_sha256(
                data["artifact_set_sha256"],
                "artifact_set_sha256",
            ),
            installed_payload_sha256=_sha256(
                data["installed_payload_sha256"],
                "installed_payload_sha256",
            ),
            artifact_count=data["artifact_count"],
            total_bytes=data["total_bytes"],
            install_path=_string(data["install_path"], "install_path", maximum=4096),
            launch_authority=data["launch_authority"],
            status=_string(data["status"], "install status", maximum=32),
        )
        if data["install_receipt_sha256"] != receipt.sha256():
            raise ValueError("app install receipt digest does not match canonical receipt")
        return receipt


def _verify_source_artifacts(
    execution_workspace: Path,
    artifacts: tuple[PackageArtifact, ...],
) -> tuple[int, int]:
    if execution_workspace.is_symlink():
        raise ValueError("execution workspace must not be a symlink")
    root = execution_workspace.resolve(strict=True)
    total = 0
    for artifact in artifacts:
        path = (root / Path(*PurePosixPath(artifact.path).parts)).resolve()
        if root != path and root not in path.parents:
            raise ValueError("artifact source path escaped execution workspace")
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"artifact source is unavailable or unsafe: {artifact.path}")
        content = path.read_bytes()
        if len(content) != artifact.byte_count:
            raise ValueError(f"artifact byte count changed: {artifact.path}")
        if hashlib.sha256(content).hexdigest() != artifact.sha256:
            raise ValueError(f"artifact digest changed: {artifact.path}")
        total += len(content)
    return len(artifacts), total


def _snapshot_payload(root: Path) -> tuple[str, int, int]:
    resolved = root.resolve(strict=True)
    artifacts: list[PackageArtifact] = []
    total = 0
    for path in resolved.rglob("*"):
        if path.is_symlink():
            raise ValueError("installed payload contains a symlink")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("installed payload contains a special file")
        relative = path.relative_to(resolved).as_posix()
        content = path.read_bytes()
        total += len(content)
        if total > _MAX_TOTAL_BYTES:
            raise ValueError("installed payload exceeds bounded total bytes")
        artifacts.append(
            PackageArtifact(
                path=relative,
                byte_count=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
            )
        )
        if len(artifacts) > _MAX_ARTIFACTS:
            raise ValueError("installed payload exceeds bounded file count")
    if not artifacts:
        raise ValueError("installed payload is empty")
    ordered = tuple(sorted(artifacts, key=lambda item: item.path))
    return _artifact_set_sha256(ordered), len(ordered), total


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(_canonical_json(payload) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


class AppInstallService:
    def install(
        self,
        plan_value: Any,
        registry: AppRegistry,
        build_execution_receipt_value: Any,
        offline_build_receipt_value: Any,
        *,
        approved_package_plan_sha256: str,
        install_root: Path,
        receipt_root: Path | None = None,
    ) -> AppInstallReceipt:
        plan = BuildPackagePlan.from_dict(plan_value)
        if _sha256(
            approved_package_plan_sha256,
            "approved_package_plan_sha256",
        ) != plan.sha256():
            raise ValueError("Approved package-plan SHA-256 does not match canonical plan")

        if registry.snapshot_sha256() != plan.registry_snapshot_sha256:
            raise ValueError("App registry changed after package-plan review")
        registered = registry.get(plan.app_id)
        if registered.sha256() != plan.manifest_sha256:
            raise ValueError("Registered manifest changed after package-plan review")

        binding = SuccessfulBuildBinding.from_payloads(
            build_execution_receipt_value,
            offline_build_receipt_value,
        )
        if binding.execution_receipt_sha256 != plan.execution_receipt_sha256:
            raise ValueError("execution receipt does not match package plan")
        if binding.offline_build_receipt_sha256 != plan.offline_build_receipt_sha256:
            raise ValueError("offline build receipt does not match package plan")
        if binding.artifact_set_sha256 != plan.artifact_set_sha256:
            raise ValueError("artifact set does not match package plan")

        source = Path(binding.execution_workspace_path)
        source_count, source_bytes = _verify_source_artifacts(source, plan.artifacts)

        root = install_root.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        root = root.resolve(strict=True)
        final_dir = (
            root / Path(*PurePosixPath(plan.install_relative_path).parts)
        ).resolve()
        if root != final_dir and root not in final_dir.parents:
            raise ValueError("install destination escaped configured install root")
        if final_dir.exists():
            raise ValueError("install destination already exists")

        staging_root = root / ".staging"
        staging_root.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(prefix=f"{plan.app_id}-", dir=staging_root)
        ).resolve()
        payload = staging / "payload"
        payload.mkdir()
        promoted = False
        try:
            source_root = source.resolve(strict=True)
            for artifact in plan.artifacts:
                src = (
                    source_root / Path(*PurePosixPath(artifact.path).parts)
                ).resolve(strict=True)
                dest = payload / Path(*PurePosixPath(artifact.path).parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dest)

            payload_sha, installed_count, installed_bytes = _snapshot_payload(payload)
            if payload_sha != plan.artifact_set_sha256:
                raise ValueError("staged install payload does not match package artifact set")
            if installed_count != source_count or installed_bytes != source_bytes:
                raise ValueError("staged install payload totals do not match build artifacts")

            metadata_dir = staging / ".phios"
            metadata_dir.mkdir()
            _write_json_atomic(metadata_dir / "package-plan.json", plan.to_dict())
            _write_json_atomic(metadata_dir / "manifest.json", registered.to_dict())

            final_dir.parent.mkdir(parents=True, exist_ok=True)
            staging.replace(final_dir)
            promoted = True

            final_payload = final_dir / "payload"
            final_sha, final_count, final_bytes = _snapshot_payload(final_payload)
            if (final_sha, final_count, final_bytes) != (
                payload_sha,
                installed_count,
                installed_bytes,
            ):
                raise ValueError("installed payload changed after atomic promotion")

            receipt = AppInstallReceipt(
                receipt_id=str(uuid.uuid4()),
                timestamp_utc=datetime.now(UTC).isoformat(),
                app_id=plan.app_id,
                app_version=plan.app_version,
                package_plan_sha256=plan.sha256(),
                manifest_sha256=plan.manifest_sha256,
                registry_snapshot_sha256=plan.registry_snapshot_sha256,
                build_plan_sha256=plan.build_plan_sha256,
                execution_receipt_sha256=plan.execution_receipt_sha256,
                offline_build_receipt_sha256=plan.offline_build_receipt_sha256,
                artifact_set_sha256=plan.artifact_set_sha256,
                installed_payload_sha256=final_sha,
                artifact_count=final_count,
                total_bytes=final_bytes,
                install_path=str(final_dir),
                launch_authority=False,
                status="installed",
            )
            receipts = (
                receipt_root or (root / ".phios-receipts")
            ).expanduser().resolve()
            _write_json_atomic(
                receipts / f"install-{receipt.receipt_id}.json",
                receipt.to_dict(),
            )
            return receipt
        except Exception:
            if promoted:
                shutil.rmtree(final_dir, ignore_errors=True)
            else:
                shutil.rmtree(staging, ignore_errors=True)
            raise


@dataclass(frozen=True)
class AppUninstallReceipt:
    receipt_id: str
    timestamp_utc: str
    app_id: str
    install_receipt_sha256: str
    removed_install_path: str
    removed_payload_sha256: str
    status: str
    schema_version: str = APP_UNINSTALL_RECEIPT_SCHEMA_VERSION

    def body_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["uninstall_receipt_sha256"] = self.sha256()
        return result


class AppUninstallService:
    def uninstall(
        self,
        install_receipt_value: Any,
        *,
        approved_install_receipt_sha256: str,
        install_root: Path,
        receipt_root: Path | None = None,
    ) -> AppUninstallReceipt:
        receipt = AppInstallReceipt.from_dict(install_receipt_value)
        if _sha256(
            approved_install_receipt_sha256,
            "approved_install_receipt_sha256",
        ) != receipt.sha256():
            raise ValueError("Approved install-receipt SHA-256 does not match receipt")

        root = install_root.expanduser().resolve(strict=True)
        target = Path(receipt.install_path)
        if target.is_symlink():
            raise ValueError("install target must not be a symlink")
        resolved = target.resolve(strict=True)
        if root != resolved and root not in resolved.parents:
            raise ValueError("install receipt path escaped configured install root")
        payload = resolved / "payload"
        payload_sha, _, _ = _snapshot_payload(payload)
        if payload_sha != receipt.installed_payload_sha256:
            raise ValueError("installed payload changed since install receipt")

        shutil.rmtree(resolved)
        uninstall = AppUninstallReceipt(
            receipt_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(UTC).isoformat(),
            app_id=receipt.app_id,
            install_receipt_sha256=receipt.sha256(),
            removed_install_path=str(resolved),
            removed_payload_sha256=payload_sha,
            status="uninstalled",
        )
        receipts = (
            receipt_root or (root / ".phios-receipts")
        ).expanduser().resolve()
        _write_json_atomic(
            receipts / f"uninstall-{uninstall.receipt_id}.json",
            uninstall.to_dict(),
        )
        return uninstall
