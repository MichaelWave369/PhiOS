from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

from .build_plan import BuildPlan
from .manifest import AppManifest
from .npm_offline import NpmOfflineBuildPlan

INSTALL_PLAN_SCHEMA_VERSION = "phios.install_plan.v0.1"
INSTALL_PLAN_REVIEW_SCHEMA_VERSION = "phios.install_plan_review.v0.1"
PACKAGE_MANIFEST_SCHEMA_VERSION = "phios.package_manifest.v0.1"
INSTALL_RECEIPT_SCHEMA_VERSION = "phios.install_receipt.v0.1"
INSTALLED_APP_REGISTRY_SCHEMA_VERSION = "phios.installed_app_registry.v0.1"
UNINSTALL_RECEIPT_SCHEMA_VERSION = "phios.uninstall_receipt.v0.1"

LineageKind = Literal["sandbox_v030", "npm_offline_v032"]

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40,64}$")
_MAX_ARTIFACT_FILES = 2048
_MAX_ARTIFACT_FILE_BYTES = 64 * 1024 * 1024
_MAX_ARTIFACT_TOTAL_BYTES = 256 * 1024 * 1024
_MAX_INSTALLED_FILES = 4096
_MAX_INSTALLED_BYTES = 512 * 1024 * 1024
_INSTALL_FILE_MODE = 0o644
_PACKAGE_METADATA_PATH = ".phios/package-manifest.json"


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


def _integer(
    value: Any,
    label: str,
    *,
    minimum: int = 0,
    maximum: int,
) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return value


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _safe_relative(value: Any, label: str) -> str:
    text = _string(value, label, maximum=512)
    if "\" in text or text.startswith("/"):
        raise ValueError(f"{label} must be a relative POSIX path")
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{label} contains unsafe path segments")
    return text


def _validated_digest_payload(
    value: Any,
    *,
    label: str,
    digest_field: str,
    expected_keys: set[str],
) -> dict[str, Any]:
    data = _mapping(value, label)
    if set(data) != expected_keys | {digest_field}:
        raise ValueError(f"{label} contains missing or unknown fields")
    supplied = _sha256(data[digest_field], f"{label} {digest_field}")
    body = {key: data[key] for key in expected_keys}
    observed = hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()
    if supplied != observed:
        raise ValueError(f"{label} digest does not match canonical receipt")
    return data


def _resolve_regular_file(root: Path, relative: str) -> Path:
    path = root
    for part in PurePosixPath(relative).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f"artifact path contains a symlink: {relative}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"artifact is unavailable: {relative}") from exc
    resolved_root = root.resolve(strict=True)
    if resolved_root != resolved and resolved_root not in resolved.parents:
        raise ValueError(f"artifact escaped execution workspace: {relative}")
    if not resolved.is_file():
        raise ValueError(f"artifact is not a regular file: {relative}")
    return resolved


@dataclass(frozen=True)
class PackageArtifact:
    path: str
    byte_count: int
    sha256: str

    def __post_init__(self) -> None:
        _safe_relative(self.path, "package artifact path")
        if PurePosixPath(self.path).parts[0] == ".phios":
            raise ValueError("package artifact path collides with reserved .phios metadata")
        _integer(
            self.byte_count,
            "package artifact byte_count",
            maximum=_MAX_ARTIFACT_FILE_BYTES,
        )
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
            byte_count=_integer(
                data["byte_count"],
                "package artifact byte_count",
                maximum=_MAX_ARTIFACT_FILE_BYTES,
            ),
            sha256=_sha256(data["sha256"], "package artifact sha256"),
        )


@dataclass(frozen=True)
class BuildExecutionBinding:
    execution_id: str
    app_id: str
    repository_url: str
    commit_sha: str
    plan_sha256: str
    source_snapshot_sha256: str
    execution_workspace_path: Path
    artifacts: tuple[PackageArtifact, ...]
    artifact_set_sha256: str
    status: str
    receipt_sha256: str

    @classmethod
    def from_dict(cls, value: Any) -> BuildExecutionBinding:
        expected = {
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
        }
        data = _validated_digest_payload(
            value,
            label="build execution receipt",
            digest_field="receipt_sha256",
            expected_keys=expected,
        )
        if data["schema_version"] != "phios.build_execution_receipt.v0.1":
            raise ValueError("unsupported build execution receipt schema")
        if data["status"] not in {"success", "no_build_required"}:
            raise ValueError("only successful build execution receipts are installable")
        if data["failure_reason"] is not None:
            raise ValueError("successful build execution receipt must not contain a failure reason")
        if not isinstance(data["network_sandbox_enforced"], bool):
            raise ValueError("build execution network_sandbox_enforced must be Boolean")
        if not isinstance(data["artifacts"], list):
            raise ValueError("build execution artifacts must be an array")
        if not isinstance(data["approved_permissions"], list):
            raise ValueError("build execution approved_permissions must be an array")
        if not isinstance(data["tool_identities"], list) or not isinstance(data["steps"], list):
            raise ValueError("build execution tool/step evidence must be arrays")

        artifacts = tuple(PackageArtifact.from_dict(item) for item in data["artifacts"])
        if not 1 <= len(artifacts) <= _MAX_ARTIFACT_FILES:
            raise ValueError("build execution artifact count is out of bounds")
        paths = tuple(item.path for item in artifacts)
        if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
            raise ValueError("build execution artifacts must have unique sorted paths")
        total = sum(item.byte_count for item in artifacts)
        if total > _MAX_ARTIFACT_TOTAL_BYTES:
            raise ValueError("build execution artifacts exceed bounded total bytes")

        digest = hashlib.sha256()
        for artifact in artifacts:
            digest.update(artifact.canonical_line())
        artifact_set_sha = _sha256(
            data["artifact_set_sha256"],
            "build execution artifact_set_sha256",
        )
        if digest.hexdigest() != artifact_set_sha:
            raise ValueError("build execution artifact-set digest mismatch")

        workspace = Path(
            _string(
                data["execution_workspace_path"],
                "build execution workspace path",
                maximum=4096,
            )
        )
        if not workspace.is_absolute() or workspace.is_symlink():
            raise ValueError("build execution workspace must be an absolute non-symlink path")
        if not _COMMIT_RE.fullmatch(
            _string(data["commit_sha"], "build execution commit_sha", maximum=64)
        ):
            raise ValueError("build execution commit_sha must be lowercase hexadecimal")

        return cls(
            execution_id=_string(
                data["execution_id"],
                "build execution execution_id",
                maximum=64,
            ),
            app_id=_string(data["app_id"], "build execution app_id", maximum=64),
            repository_url=_string(
                data["repository_url"],
                "build execution repository_url",
                maximum=512,
            ),
            commit_sha=data["commit_sha"],
            plan_sha256=_sha256(data["plan_sha256"], "build execution plan_sha256"),
            source_snapshot_sha256=_sha256(
                data["source_snapshot_sha256"],
                "build execution source_snapshot_sha256",
            ),
            execution_workspace_path=workspace,
            artifacts=artifacts,
            artifact_set_sha256=artifact_set_sha,
            status=data["status"],
            receipt_sha256=_sha256(
                data["receipt_sha256"],
                "build execution receipt_sha256",
            ),
        )

    def verify_workspace_artifacts(self) -> None:
        try:
            root = self.execution_workspace_path.resolve(strict=True)
        except OSError as exc:
            raise ValueError("build execution workspace is unavailable") from exc
        if not root.is_dir():
            raise ValueError("build execution workspace is not a directory")
        for artifact in self.artifacts:
            path = _resolve_regular_file(root, artifact.path)
            content = path.read_bytes()
            if len(content) != artifact.byte_count:
                raise ValueError(f"build artifact byte count changed: {artifact.path}")
            if hashlib.sha256(content).hexdigest() != artifact.sha256:
                raise ValueError(f"build artifact SHA-256 changed: {artifact.path}")


@dataclass(frozen=True)
class SandboxBinding:
    receipt_sha256: str
    build_execution_receipt_sha256: str
    app_id: str
    commit_sha: str
    plan_sha256: str
    source_snapshot_sha256: str
    build_status: str
    network_namespace_enforced: bool
    host_network_inherited: bool

    @classmethod
    def from_dict(cls, value: Any) -> SandboxBinding:
        expected = {
            "schema_version",
            "sandbox_receipt_id",
            "timestamp_utc",
            "execution_id",
            "build_execution_receipt_sha256",
            "app_id",
            "commit_sha",
            "plan_sha256",
            "source_snapshot_sha256",
            "policy",
            "backend_identity",
            "controls",
            "containment_level",
            "build_status",
        }
        data = _validated_digest_payload(
            value,
            label="sandbox receipt",
            digest_field="sandbox_receipt_sha256",
            expected_keys=expected,
        )
        if data["schema_version"] != "phios.build_sandbox_receipt.v0.1":
            raise ValueError("unsupported sandbox receipt schema")
        controls = _mapping(data["controls"], "sandbox controls")
        network = controls.get("network_namespace_enforced")
        inherited = controls.get("host_network_inherited")
        if network is not True or inherited is not False:
            raise ValueError(
                "installable build requires enforced network namespace and no host network"
            )
        if data["build_status"] not in {"success", "no_build_required"}:
            raise ValueError("sandbox receipt does not describe a successful build")
        return cls(
            receipt_sha256=_sha256(
                data["sandbox_receipt_sha256"],
                "sandbox receipt sha256",
            ),
            build_execution_receipt_sha256=_sha256(
                data["build_execution_receipt_sha256"],
                "sandbox build_execution_receipt_sha256",
            ),
            app_id=_string(data["app_id"], "sandbox app_id", maximum=64),
            commit_sha=_string(data["commit_sha"], "sandbox commit_sha", maximum=64),
            plan_sha256=_sha256(data["plan_sha256"], "sandbox plan_sha256"),
            source_snapshot_sha256=_sha256(
                data["source_snapshot_sha256"],
                "sandbox source_snapshot_sha256",
            ),
            build_status=data["build_status"],
            network_namespace_enforced=True,
            host_network_inherited=False,
        )


@dataclass(frozen=True)
class LineageBinding:
    kind: LineageKind
    receipt_sha256: str

    @classmethod
    def from_build_result(
        cls,
        value: Any,
    ) -> tuple[BuildExecutionBinding, SandboxBinding, LineageBinding]:
        root = _mapping(value, "build result")
        if "sandboxed_build" in root:
            if set(root) != {
                "sandboxed_build",
                "offline_receipt",
                "offline_receipt_path",
                "offline_receipt_persisted",
            }:
                raise ValueError("v0.32 build result contains missing or unknown fields")
            sandboxed = _mapping(root["sandboxed_build"], "sandboxed build result")
            offline = _mapping(root["offline_receipt"], "offline build receipt")
            expected_offline = {
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
            }
            validated_offline = _validated_digest_payload(
                offline,
                label="npm offline build receipt",
                digest_field="npm_offline_build_receipt_sha256",
                expected_keys=expected_offline,
            )
            if validated_offline["schema_version"] != "phios.npm_offline_build_receipt.v0.1":
                raise ValueError("unsupported npm offline build receipt schema")
            if (
                validated_offline["network_mode"] != "deny"
                or validated_offline["network_namespace_enforced"] is not True
            ):
                raise ValueError("npm offline lineage does not prove network denial")
            if validated_offline["build_status"] not in {"success", "no_build_required"}:
                raise ValueError("npm offline lineage does not describe a successful build")
            kind: LineageKind = "npm_offline_v032"
            lineage_sha = _sha256(
                offline["npm_offline_build_receipt_sha256"],
                "npm offline build receipt sha256",
            )
        else:
            sandboxed = root
            validated_offline = None
            kind = "sandbox_v030"
            lineage_sha = ""

        if set(sandboxed) != {
            "execution",
            "sandbox",
            "sandbox_receipt_path",
            "sandbox_receipt_persisted",
        }:
            raise ValueError("sandboxed build result contains missing or unknown fields")
        execution = BuildExecutionBinding.from_dict(sandboxed["execution"])
        sandbox = SandboxBinding.from_dict(sandboxed["sandbox"])
        if sandbox.build_execution_receipt_sha256 != execution.receipt_sha256:
            raise ValueError("sandbox receipt does not bind build execution receipt")
        if sandbox.app_id != execution.app_id or sandbox.commit_sha != execution.commit_sha:
            raise ValueError("sandbox identity does not match build execution")
        if sandbox.plan_sha256 != execution.plan_sha256:
            raise ValueError("sandbox plan does not match build execution")
        if sandbox.source_snapshot_sha256 != execution.source_snapshot_sha256:
            raise ValueError("sandbox source snapshot does not match build execution")
        if sandbox.build_status != execution.status:
            raise ValueError("sandbox build status does not match build execution")

        if validated_offline is not None:
            if validated_offline["build_execution_receipt_sha256"] != execution.receipt_sha256:
                raise ValueError("npm offline receipt does not bind build execution")
            if validated_offline["sandbox_receipt_sha256"] != sandbox.receipt_sha256:
                raise ValueError("npm offline receipt does not bind sandbox receipt")
            if validated_offline["app_id"] != execution.app_id:
                raise ValueError("npm offline receipt app_id does not match execution")
            if validated_offline["commit_sha"] != execution.commit_sha:
                raise ValueError("npm offline receipt commit does not match execution")
        else:
            lineage_sha = sandbox.receipt_sha256

        return execution, sandbox, cls(kind=kind, receipt_sha256=lineage_sha)


def _manifest_from_payload(value: Any) -> AppManifest:
    data = _mapping(value, "manifest source")
    if data.get("schema_version") == "phios.app_manifest.v0.1":
        return AppManifest.from_dict(data)
    manifest = data.get("manifest_candidate")
    if manifest is None:
        raise ValueError("manifest source must be an app manifest or intake result")
    return AppManifest.from_dict(manifest)


def _build_plan_from_payload(value: Any) -> BuildPlan:
    data = _mapping(value, "build plan source")
    schema = data.get("schema_version")
    if schema == "phios.build_plan.v0.1":
        return BuildPlan.from_dict(data)
    if schema == "phios.npm_offline_build_plan.v0.1":
        return NpmOfflineBuildPlan.from_dict(data).derived_build_plan
    raise ValueError("unsupported build plan source for v0.33 install")


@dataclass(frozen=True)
class PackageManifest:
    app_manifest: AppManifest
    app_manifest_sha256: str
    build_plan_sha256: str
    build_execution_receipt_sha256: str
    sandbox_receipt_sha256: str
    lineage_kind: LineageKind
    lineage_receipt_sha256: str
    artifact_set_sha256: str
    artifacts: tuple[PackageArtifact, ...]
    file_mode_policy: str = "0644_non_executable"
    launch_authority: str = "disabled"
    schema_version: str = PACKAGE_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PACKAGE_MANIFEST_SCHEMA_VERSION:
            raise ValueError(f"unsupported package manifest schema: {self.schema_version}")
        if self.app_manifest.sha256() != self.app_manifest_sha256:
            raise ValueError("package manifest app-manifest digest mismatch")
        for value, label in (
            (self.build_plan_sha256, "build_plan_sha256"),
            (self.build_execution_receipt_sha256, "build_execution_receipt_sha256"),
            (self.sandbox_receipt_sha256, "sandbox_receipt_sha256"),
            (self.lineage_receipt_sha256, "lineage_receipt_sha256"),
            (self.artifact_set_sha256, "artifact_set_sha256"),
        ):
            _sha256(value, label)
        if self.lineage_kind not in {"sandbox_v030", "npm_offline_v032"}:
            raise ValueError("unsupported package lineage kind")
        if self.file_mode_policy != "0644_non_executable":
            raise ValueError("unsupported package file-mode policy")
        if self.launch_authority != "disabled":
            raise ValueError("v0.33 packages cannot carry launch authority")
        if not 1 <= len(self.artifacts) <= _MAX_ARTIFACT_FILES:
            raise ValueError("package artifact count is out of bounds")
        paths = tuple(item.path for item in self.artifacts)
        if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
            raise ValueError("package artifacts must have unique sorted paths")
        digest = hashlib.sha256()
        for artifact in self.artifacts:
            digest.update(artifact.canonical_line())
        if digest.hexdigest() != self.artifact_set_sha256:
            raise ValueError("package artifact-set digest mismatch")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app_manifest": self.app_manifest.to_dict(),
            "app_manifest_sha256": self.app_manifest_sha256,
            "build_plan_sha256": self.build_plan_sha256,
            "build_execution_receipt_sha256": self.build_execution_receipt_sha256,
            "sandbox_receipt_sha256": self.sandbox_receipt_sha256,
            "lineage_kind": self.lineage_kind,
            "lineage_receipt_sha256": self.lineage_receipt_sha256,
            "artifact_set_sha256": self.artifact_set_sha256,
            "artifacts": [item.to_dict() for item in self.artifacts],
            "file_mode_policy": self.file_mode_policy,
            "launch_authority": self.launch_authority,
        }

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["package_manifest_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> PackageManifest:
        data = _mapping(value, "package manifest")
        expected = {
            "schema_version",
            "app_manifest",
            "app_manifest_sha256",
            "build_plan_sha256",
            "build_execution_receipt_sha256",
            "sandbox_receipt_sha256",
            "lineage_kind",
            "lineage_receipt_sha256",
            "artifact_set_sha256",
            "artifacts",
            "file_mode_policy",
            "launch_authority",
            "package_manifest_sha256",
        }
        if set(data) != expected:
            raise ValueError("package manifest contains missing or unknown fields")
        artifacts_value = data["artifacts"]
        if not isinstance(artifacts_value, list):
            raise ValueError("package manifest artifacts must be an array")
        lineage = data["lineage_kind"]
        if lineage not in {"sandbox_v030", "npm_offline_v032"}:
            raise ValueError("unsupported package lineage kind")
        package = cls(
            schema_version=data["schema_version"],
            app_manifest=AppManifest.from_dict(data["app_manifest"]),
            app_manifest_sha256=_sha256(
                data["app_manifest_sha256"],
                "app_manifest_sha256",
            ),
            build_plan_sha256=_sha256(
                data["build_plan_sha256"],
                "build_plan_sha256",
            ),
            build_execution_receipt_sha256=_sha256(
                data["build_execution_receipt_sha256"],
                "build_execution_receipt_sha256",
            ),
            sandbox_receipt_sha256=_sha256(
                data["sandbox_receipt_sha256"],
                "sandbox_receipt_sha256",
            ),
            lineage_kind=cast(LineageKind, lineage),
            lineage_receipt_sha256=_sha256(
                data["lineage_receipt_sha256"],
                "lineage_receipt_sha256",
            ),
            artifact_set_sha256=_sha256(
                data["artifact_set_sha256"],
                "artifact_set_sha256",
            ),
            artifacts=tuple(PackageArtifact.from_dict(item) for item in artifacts_value),
            file_mode_policy=_string(
                data["file_mode_policy"],
                "file_mode_policy",
                maximum=64,
            ),
            launch_authority=_string(
                data["launch_authority"],
                "launch_authority",
                maximum=32,
            ),
        )
        if data["package_manifest_sha256"] != package.sha256():
            raise ValueError("package manifest digest does not match canonical manifest")
        return package


@dataclass(frozen=True)
class InstallPlan:
    package: PackageManifest
    package_manifest_sha256: str
    source_execution_workspace_path: str
    target_relative_path: str
    status: str = "ready_for_install"
    schema_version: str = INSTALL_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != INSTALL_PLAN_SCHEMA_VERSION:
            raise ValueError(f"unsupported install plan schema: {self.schema_version}")
        if self.package.sha256() != self.package_manifest_sha256:
            raise ValueError("install plan package-manifest digest mismatch")
        source = Path(self.source_execution_workspace_path)
        if not source.is_absolute():
            raise ValueError("install plan source workspace must be absolute")
        expected_target = f"apps/{self.package.app_manifest.app_id}/{self.package.sha256()}"
        if self.target_relative_path != expected_target:
            raise ValueError("install plan target path does not match immutable package identity")
        _safe_relative(self.target_relative_path, "install plan target path")
        if self.status != "ready_for_install":
            raise ValueError("install plan status must be ready_for_install")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "package": self.package.to_dict(),
            "package_manifest_sha256": self.package_manifest_sha256,
            "source_execution_workspace_path": self.source_execution_workspace_path,
            "target_relative_path": self.target_relative_path,
            "status": self.status,
        }

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["install_plan_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> InstallPlan:
        data = _mapping(value, "install plan")
        expected = {
            "schema_version",
            "package",
            "package_manifest_sha256",
            "source_execution_workspace_path",
            "target_relative_path",
            "status",
            "install_plan_sha256",
        }
        if set(data) != expected:
            raise ValueError("install plan contains missing or unknown fields")
        plan = cls(
            schema_version=data["schema_version"],
            package=PackageManifest.from_dict(data["package"]),
            package_manifest_sha256=_sha256(
                data["package_manifest_sha256"],
                "package_manifest_sha256",
            ),
            source_execution_workspace_path=_string(
                data["source_execution_workspace_path"],
                "source_execution_workspace_path",
                maximum=4096,
            ),
            target_relative_path=_safe_relative(
                data["target_relative_path"],
                "target_relative_path",
            ),
            status=_string(data["status"], "install plan status", maximum=32),
        )
        if data["install_plan_sha256"] != plan.sha256():
            raise ValueError("install plan digest does not match canonical plan")
        return plan


@dataclass(frozen=True)
class InstallPlanReview:
    install_plan_sha256: str
    package_manifest_sha256: str
    app_id: str
    app_version: str
    artifact_set_sha256: str
    artifact_count: int
    lineage_kind: LineageKind
    launch_authority: str
    target_relative_path: str
    schema_version: str = INSTALL_PLAN_REVIEW_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _extract_build_result(value: Any) -> tuple[BuildExecutionBinding, SandboxBinding, LineageBinding]:
    return LineageBinding.from_build_result(value)


def plan_install(
    manifest_source_value: Any,
    build_plan_source_value: Any,
    build_result_value: Any,
) -> InstallPlan:
    manifest = _manifest_from_payload(manifest_source_value)
    plan = _build_plan_from_payload(build_plan_source_value)
    execution, sandbox, lineage = _extract_build_result(build_result_value)

    if plan.sha256() != execution.plan_sha256:
        raise ValueError("build plan does not match build execution receipt")
    if plan.app_id != execution.app_id or manifest.app_id != execution.app_id:
        raise ValueError("app identity does not match across install inputs")
    if plan.repository_url.lower() != execution.repository_url.lower():
        raise ValueError("build plan repository does not match build execution")
    if manifest.source.repository_url.lower() != execution.repository_url.lower():
        raise ValueError("app manifest repository does not match build execution")
    if plan.commit_sha != execution.commit_sha:
        raise ValueError("build plan commit does not match build execution")
    if plan.source_snapshot_sha256 != execution.source_snapshot_sha256:
        raise ValueError("build plan source snapshot does not match build execution")
    if plan.manifest_sha256 != manifest.sha256():
        raise ValueError("build plan manifest digest does not match app manifest")
    if sandbox.receipt_sha256 != (
        lineage.receipt_sha256 if lineage.kind == "sandbox_v030" else sandbox.receipt_sha256
    ):
        raise ValueError("sandbox lineage binding is inconsistent")

    execution.verify_workspace_artifacts()
    package = PackageManifest(
        app_manifest=manifest,
        app_manifest_sha256=manifest.sha256(),
        build_plan_sha256=plan.sha256(),
        build_execution_receipt_sha256=execution.receipt_sha256,
        sandbox_receipt_sha256=sandbox.receipt_sha256,
        lineage_kind=lineage.kind,
        lineage_receipt_sha256=lineage.receipt_sha256,
        artifact_set_sha256=execution.artifact_set_sha256,
        artifacts=execution.artifacts,
    )
    return InstallPlan(
        package=package,
        package_manifest_sha256=package.sha256(),
        source_execution_workspace_path=str(execution.execution_workspace_path),
        target_relative_path=f"apps/{manifest.app_id}/{package.sha256()}",
    )


def review_install_plan(value: Any) -> InstallPlanReview:
    plan = InstallPlan.from_dict(value)
    package = plan.package
    return InstallPlanReview(
        install_plan_sha256=plan.sha256(),
        package_manifest_sha256=package.sha256(),
        app_id=package.app_manifest.app_id,
        app_version=package.app_manifest.version,
        artifact_set_sha256=package.artifact_set_sha256,
        artifact_count=len(package.artifacts),
        lineage_kind=package.lineage_kind,
        launch_authority=package.launch_authority,
        target_relative_path=plan.target_relative_path,
    )


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(_canonical_json(payload) + "\n", encoding="utf-8")
        os.chmod(temporary, _INSTALL_FILE_MODE)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _snapshot_installed_tree(root: Path) -> tuple[str, int, int]:
    if root.is_symlink():
        raise ValueError("installed package root must not be a symlink")
    resolved = root.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("installed package root must be a directory")
    records: list[tuple[str, int, int, str]] = []
    total = 0
    for path in resolved.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"installed package contains a symlink: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"installed package contains a special file: {path}")
        relative = path.relative_to(resolved).as_posix()
        content = path.read_bytes()
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o111:
            raise ValueError(f"installed package file unexpectedly became executable: {relative}")
        total += len(content)
        if total > _MAX_INSTALLED_BYTES:
            raise ValueError("installed package exceeds bounded total bytes")
        records.append(
            (relative, mode, len(content), hashlib.sha256(content).hexdigest())
        )
        if len(records) > _MAX_INSTALLED_FILES:
            raise ValueError("installed package exceeds bounded file count")
    digest = hashlib.sha256()
    for relative, mode, byte_count, file_sha in sorted(records):
        digest.update(
            f"{relative}\0{mode:o}\0{byte_count}\0{file_sha}\n".encode("utf-8")
        )
    return digest.hexdigest(), len(records), total


@dataclass(frozen=True)
class InstallReceipt:
    receipt_id: str
    timestamp_utc: str
    app_id: str
    app_version: str
    app_manifest_sha256: str
    package_manifest_sha256: str
    install_plan_sha256: str
    build_execution_receipt_sha256: str
    sandbox_receipt_sha256: str
    lineage_kind: LineageKind
    lineage_receipt_sha256: str
    artifact_set_sha256: str
    install_path: str
    installed_tree_sha256: str
    installed_file_count: int
    installed_total_bytes: int
    registry_path: str
    launch_authority: str
    status: str
    schema_version: str = INSTALL_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != INSTALL_RECEIPT_SCHEMA_VERSION:
            raise ValueError(f"unsupported install receipt schema: {self.schema_version}")
        try:
            uuid.UUID(self.receipt_id)
        except ValueError as exc:
            raise ValueError("install receipt_id must be a UUID") from exc
        parsed = datetime.fromisoformat(self.timestamp_utc)
        if parsed.tzinfo is None:
            raise ValueError("install receipt timestamp must include a timezone")
        for value, label in (
            (self.app_manifest_sha256, "app_manifest_sha256"),
            (self.package_manifest_sha256, "package_manifest_sha256"),
            (self.install_plan_sha256, "install_plan_sha256"),
            (self.build_execution_receipt_sha256, "build_execution_receipt_sha256"),
            (self.sandbox_receipt_sha256, "sandbox_receipt_sha256"),
            (self.lineage_receipt_sha256, "lineage_receipt_sha256"),
            (self.artifact_set_sha256, "artifact_set_sha256"),
            (self.installed_tree_sha256, "installed_tree_sha256"),
        ):
            _sha256(value, label)
        if self.lineage_kind not in {"sandbox_v030", "npm_offline_v032"}:
            raise ValueError("unsupported install lineage kind")
        for path_value, label in (
            (self.install_path, "install_path"),
            (self.registry_path, "registry_path"),
        ):
            if not Path(path_value).is_absolute():
                raise ValueError(f"{label} must be absolute")
        _integer(
            self.installed_file_count,
            "installed_file_count",
            minimum=1,
            maximum=_MAX_INSTALLED_FILES,
        )
        _integer(
            self.installed_total_bytes,
            "installed_total_bytes",
            minimum=1,
            maximum=_MAX_INSTALLED_BYTES,
        )
        if self.launch_authority != "disabled":
            raise ValueError("v0.33 install receipt cannot carry launch authority")
        if self.status != "installed":
            raise ValueError("install receipt status must be installed")

    def body_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["install_receipt_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> InstallReceipt:
        data = _mapping(value, "install receipt")
        expected = {
            "schema_version",
            "receipt_id",
            "timestamp_utc",
            "app_id",
            "app_version",
            "app_manifest_sha256",
            "package_manifest_sha256",
            "install_plan_sha256",
            "build_execution_receipt_sha256",
            "sandbox_receipt_sha256",
            "lineage_kind",
            "lineage_receipt_sha256",
            "artifact_set_sha256",
            "install_path",
            "installed_tree_sha256",
            "installed_file_count",
            "installed_total_bytes",
            "registry_path",
            "launch_authority",
            "status",
            "install_receipt_sha256",
        }
        if set(data) != expected:
            raise ValueError("install receipt contains missing or unknown fields")
        lineage = data["lineage_kind"]
        if lineage not in {"sandbox_v030", "npm_offline_v032"}:
            raise ValueError("unsupported install lineage kind")
        receipt = cls(
            schema_version=data["schema_version"],
            receipt_id=_string(data["receipt_id"], "install receipt_id", maximum=64),
            timestamp_utc=_string(
                data["timestamp_utc"],
                "install timestamp_utc",
                maximum=128,
            ),
            app_id=_string(data["app_id"], "install app_id", maximum=64),
            app_version=_string(data["app_version"], "install app_version", maximum=64),
            app_manifest_sha256=_sha256(
                data["app_manifest_sha256"],
                "app_manifest_sha256",
            ),
            package_manifest_sha256=_sha256(
                data["package_manifest_sha256"],
                "package_manifest_sha256",
            ),
            install_plan_sha256=_sha256(
                data["install_plan_sha256"],
                "install_plan_sha256",
            ),
            build_execution_receipt_sha256=_sha256(
                data["build_execution_receipt_sha256"],
                "build_execution_receipt_sha256",
            ),
            sandbox_receipt_sha256=_sha256(
                data["sandbox_receipt_sha256"],
                "sandbox_receipt_sha256",
            ),
            lineage_kind=cast(LineageKind, lineage),
            lineage_receipt_sha256=_sha256(
                data["lineage_receipt_sha256"],
                "lineage_receipt_sha256",
            ),
            artifact_set_sha256=_sha256(
                data["artifact_set_sha256"],
                "artifact_set_sha256",
            ),
            install_path=_string(data["install_path"], "install_path", maximum=4096),
            installed_tree_sha256=_sha256(
                data["installed_tree_sha256"],
                "installed_tree_sha256",
            ),
            installed_file_count=_integer(
                data["installed_file_count"],
                "installed_file_count",
                minimum=1,
                maximum=_MAX_INSTALLED_FILES,
            ),
            installed_total_bytes=_integer(
                data["installed_total_bytes"],
                "installed_total_bytes",
                minimum=1,
                maximum=_MAX_INSTALLED_BYTES,
            ),
            registry_path=_string(data["registry_path"], "registry_path", maximum=4096),
            launch_authority=_string(
                data["launch_authority"],
                "launch_authority",
                maximum=32,
            ),
            status=_string(data["status"], "install status", maximum=32),
        )
        if data["install_receipt_sha256"] != receipt.sha256():
            raise ValueError("install receipt digest does not match canonical receipt")
        return receipt


@dataclass(frozen=True)
class InstalledAppEntry:
    app_id: str
    app_version: str
    app_manifest_sha256: str
    package_manifest_sha256: str
    install_receipt_sha256: str
    install_path: str
    launch_authority: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.app_manifest_sha256, "app_manifest_sha256"),
            (self.package_manifest_sha256, "package_manifest_sha256"),
            (self.install_receipt_sha256, "install_receipt_sha256"),
        ):
            _sha256(value, label)
        if not Path(self.install_path).is_absolute():
            raise ValueError("installed app path must be absolute")
        if self.launch_authority != "disabled":
            raise ValueError("v0.33 installed registry cannot grant launch authority")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Any) -> InstalledAppEntry:
        data = _mapping(value, "installed app registry entry")
        expected = {
            "app_id",
            "app_version",
            "app_manifest_sha256",
            "package_manifest_sha256",
            "install_receipt_sha256",
            "install_path",
            "launch_authority",
        }
        if set(data) != expected:
            raise ValueError("installed app registry entry contains missing or unknown fields")
        return cls(
            app_id=_string(data["app_id"], "registry app_id", maximum=64),
            app_version=_string(data["app_version"], "registry app_version", maximum=64),
            app_manifest_sha256=_sha256(
                data["app_manifest_sha256"],
                "registry app_manifest_sha256",
            ),
            package_manifest_sha256=_sha256(
                data["package_manifest_sha256"],
                "registry package_manifest_sha256",
            ),
            install_receipt_sha256=_sha256(
                data["install_receipt_sha256"],
                "registry install_receipt_sha256",
            ),
            install_path=_string(data["install_path"], "registry install_path", maximum=4096),
            launch_authority=_string(
                data["launch_authority"],
                "registry launch_authority",
                maximum=32,
            ),
        )


class InstalledAppRegistry:
    def __init__(self, entries: tuple[InstalledAppEntry, ...] = ()) -> None:
        keys = [(entry.app_id, entry.package_manifest_sha256) for entry in entries]
        if len(keys) != len(set(keys)):
            raise ValueError("installed app registry contains duplicate package identities")
        self._entries = tuple(
            sorted(entries, key=lambda item: (item.app_id, item.package_manifest_sha256))
        )

    def list(self) -> tuple[InstalledAppEntry, ...]:
        return self._entries

    def add(self, entry: InstalledAppEntry) -> InstalledAppRegistry:
        if any(
            item.app_id == entry.app_id
            and item.package_manifest_sha256 == entry.package_manifest_sha256
            for item in self._entries
        ):
            raise ValueError("package is already installed")
        return InstalledAppRegistry((*self._entries, entry))

    def remove(
        self,
        *,
        app_id: str,
        package_manifest_sha256: str,
        install_receipt_sha256: str,
    ) -> InstalledAppRegistry:
        matches = [
            item
            for item in self._entries
            if item.app_id == app_id
            and item.package_manifest_sha256 == package_manifest_sha256
        ]
        if len(matches) != 1:
            raise ValueError("installed package is not uniquely present in registry")
        if matches[0].install_receipt_sha256 != install_receipt_sha256:
            raise ValueError("installed registry receipt binding does not match uninstall request")
        return InstalledAppRegistry(
            tuple(item for item in self._entries if item is not matches[0])
        )

    def to_dict(self) -> dict[str, Any]:
        body = {
            "schema_version": INSTALLED_APP_REGISTRY_SCHEMA_VERSION,
            "entries": [item.to_dict() for item in self._entries],
        }
        body["registry_sha256"] = hashlib.sha256(
            _canonical_json(body).encode("utf-8")
        ).hexdigest()
        return body

    @classmethod
    def load(cls, path: Path) -> InstalledAppRegistry:
        if not path.exists():
            return cls()
        data = _mapping(
            json.loads(path.read_text(encoding="utf-8")),
            "installed app registry",
        )
        if set(data) != {"schema_version", "entries", "registry_sha256"}:
            raise ValueError("installed app registry contains missing or unknown fields")
        if data["schema_version"] != INSTALLED_APP_REGISTRY_SCHEMA_VERSION:
            raise ValueError("unsupported installed app registry schema")
        entries_value = data["entries"]
        if not isinstance(entries_value, list):
            raise ValueError("installed app registry entries must be an array")
        body = {
            "schema_version": data["schema_version"],
            "entries": entries_value,
        }
        if data["registry_sha256"] != hashlib.sha256(
            _canonical_json(body).encode("utf-8")
        ).hexdigest():
            raise ValueError("installed app registry digest mismatch")
        return cls(tuple(InstalledAppEntry.from_dict(item) for item in entries_value))

    def save(self, path: Path) -> None:
        _write_json_atomic(path, self.to_dict())


class InstallService:
    def install(
        self,
        plan_value: Any,
        *,
        approved_install_plan_sha256: str,
        install_root: Path,
        receipt_root: Path | None = None,
        registry_path: Path | None = None,
    ) -> InstallReceipt:
        plan = InstallPlan.from_dict(plan_value)
        approved = _sha256(
            approved_install_plan_sha256,
            "approved_install_plan_sha256",
        )
        if approved != plan.sha256():
            raise ValueError("approved install-plan SHA-256 does not match canonical plan")

        source = Path(plan.source_execution_workspace_path)
        if source.is_symlink():
            raise ValueError("install source workspace must not be a symlink")
        source_root = source.resolve(strict=True)
        for artifact in plan.package.artifacts:
            path = _resolve_regular_file(source_root, artifact.path)
            content = path.read_bytes()
            if len(content) != artifact.byte_count:
                raise ValueError(f"build artifact byte count changed: {artifact.path}")
            if hashlib.sha256(content).hexdigest() != artifact.sha256:
                raise ValueError(f"build artifact SHA-256 changed: {artifact.path}")

        root = install_root.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        root = root.resolve(strict=True)
        if root.is_symlink():
            raise ValueError("install root must not be a symlink")

        final = (root / Path(*PurePosixPath(plan.target_relative_path).parts)).resolve()
        if root != final and root not in final.parents:
            raise ValueError("install destination escaped configured install root")
        if final.exists():
            raise ValueError("immutable package destination already exists")

        metadata_root = root / ".phios"
        staging_root = metadata_root / "staging"
        receipts = (receipt_root or (metadata_root / "receipts")).expanduser().resolve()
        registry = (registry_path or (metadata_root / "installed-registry.json")).expanduser().resolve()
        for controlled in (staging_root.resolve(), receipts, registry.parent):
            if root != controlled and root not in controlled.parents:
                raise ValueError("install metadata path escaped configured install root")

        current_registry = InstalledAppRegistry.load(registry)
        if any(
            item.app_id == plan.package.app_manifest.app_id
            and item.package_manifest_sha256 == plan.package.sha256()
            for item in current_registry.list()
        ):
            raise ValueError("package is already installed")

        staging_root.mkdir(parents=True, exist_ok=True)
        staging = (staging_root / f"install-{uuid.uuid4()}").resolve()
        if staging.exists():
            raise ValueError("install staging path already exists")
        staging.mkdir()
        promoted = False
        receipt_path: Path | None = None

        try:
            for artifact in plan.package.artifacts:
                source_file = _resolve_regular_file(source_root, artifact.path)
                destination = staging / Path(*PurePosixPath(artifact.path).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_file, destination)
                os.chmod(destination, _INSTALL_FILE_MODE)

            package_metadata = staging / _PACKAGE_METADATA_PATH
            package_metadata.parent.mkdir(parents=True, exist_ok=True)
            _write_json_atomic(package_metadata, plan.package.to_dict())

            tree_sha, file_count, total_bytes = _snapshot_installed_tree(staging)
            final.parent.mkdir(parents=True, exist_ok=True)
            staging.replace(final)
            promoted = True
            final_tree_sha, final_count, final_bytes = _snapshot_installed_tree(final)
            if (tree_sha, file_count, total_bytes) != (
                final_tree_sha,
                final_count,
                final_bytes,
            ):
                raise ValueError("installed package changed during atomic promotion")

            receipt = InstallReceipt(
                receipt_id=str(uuid.uuid4()),
                timestamp_utc=datetime.now(UTC).isoformat(),
                app_id=plan.package.app_manifest.app_id,
                app_version=plan.package.app_manifest.version,
                app_manifest_sha256=plan.package.app_manifest_sha256,
                package_manifest_sha256=plan.package.sha256(),
                install_plan_sha256=plan.sha256(),
                build_execution_receipt_sha256=plan.package.build_execution_receipt_sha256,
                sandbox_receipt_sha256=plan.package.sandbox_receipt_sha256,
                lineage_kind=plan.package.lineage_kind,
                lineage_receipt_sha256=plan.package.lineage_receipt_sha256,
                artifact_set_sha256=plan.package.artifact_set_sha256,
                install_path=str(final),
                installed_tree_sha256=final_tree_sha,
                installed_file_count=final_count,
                installed_total_bytes=final_bytes,
                registry_path=str(registry),
                launch_authority="disabled",
                status="installed",
            )
            receipt_path = receipts / f"install-{receipt.receipt_id}.json"
            _write_json_atomic(receipt_path, receipt.to_dict())

            entry = InstalledAppEntry(
                app_id=receipt.app_id,
                app_version=receipt.app_version,
                app_manifest_sha256=receipt.app_manifest_sha256,
                package_manifest_sha256=receipt.package_manifest_sha256,
                install_receipt_sha256=receipt.sha256(),
                install_path=receipt.install_path,
                launch_authority="disabled",
            )
            updated_registry = current_registry.add(entry)
            try:
                updated_registry.save(registry)
            except Exception:
                receipt_path.unlink(missing_ok=True)
                raise
            return receipt
        except Exception:
            if promoted:
                shutil.rmtree(final, ignore_errors=True)
            else:
                shutil.rmtree(staging, ignore_errors=True)
            raise


@dataclass(frozen=True)
class UninstallReceipt:
    receipt_id: str
    timestamp_utc: str
    app_id: str
    package_manifest_sha256: str
    install_receipt_sha256: str
    installed_tree_sha256: str
    original_install_path: str
    quarantine_path: str
    registry_path: str
    launch_authority: str
    status: str
    schema_version: str = UNINSTALL_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != UNINSTALL_RECEIPT_SCHEMA_VERSION:
            raise ValueError(f"unsupported uninstall receipt schema: {self.schema_version}")
        try:
            uuid.UUID(self.receipt_id)
        except ValueError as exc:
            raise ValueError("uninstall receipt_id must be a UUID") from exc
        parsed = datetime.fromisoformat(self.timestamp_utc)
        if parsed.tzinfo is None:
            raise ValueError("uninstall receipt timestamp must include a timezone")
        for value, label in (
            (self.package_manifest_sha256, "package_manifest_sha256"),
            (self.install_receipt_sha256, "install_receipt_sha256"),
            (self.installed_tree_sha256, "installed_tree_sha256"),
        ):
            _sha256(value, label)
        for path_value, label in (
            (self.original_install_path, "original_install_path"),
            (self.quarantine_path, "quarantine_path"),
            (self.registry_path, "registry_path"),
        ):
            if not Path(path_value).is_absolute():
                raise ValueError(f"{label} must be absolute")
        if self.launch_authority != "disabled":
            raise ValueError("uninstalled package cannot carry launch authority")
        if self.status != "uninstalled_quarantined":
            raise ValueError("unsupported uninstall status")

    def body_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["uninstall_receipt_sha256"] = self.sha256()
        return result


class UninstallService:
    def uninstall(
        self,
        install_receipt_value: Any,
        *,
        approved_install_receipt_sha256: str,
        install_root: Path,
        receipt_root: Path | None = None,
        registry_path: Path | None = None,
    ) -> UninstallReceipt:
        install_receipt = InstallReceipt.from_dict(install_receipt_value)
        approved = _sha256(
            approved_install_receipt_sha256,
            "approved_install_receipt_sha256",
        )
        if approved != install_receipt.sha256():
            raise ValueError("approved install-receipt SHA-256 does not match receipt")

        root = install_root.expanduser().resolve(strict=True)
        metadata_root = root / ".phios"
        registry = (registry_path or (metadata_root / "installed-registry.json")).expanduser().resolve()
        if str(registry) != install_receipt.registry_path:
            raise ValueError("uninstall registry path does not match install receipt")
        current_registry = InstalledAppRegistry.load(registry)

        install_path = Path(install_receipt.install_path)
        if install_path.is_symlink():
            raise ValueError("installed package path must not be a symlink")
        resolved_install = install_path.resolve(strict=True)
        if root != resolved_install and root not in resolved_install.parents:
            raise ValueError("installed package escaped configured install root")
        tree_sha, file_count, total_bytes = _snapshot_installed_tree(resolved_install)
        if tree_sha != install_receipt.installed_tree_sha256:
            raise ValueError("installed package tree changed after installation")
        if file_count != install_receipt.installed_file_count:
            raise ValueError("installed package file count changed after installation")
        if total_bytes != install_receipt.installed_total_bytes:
            raise ValueError("installed package byte count changed after installation")

        updated_registry = current_registry.remove(
            app_id=install_receipt.app_id,
            package_manifest_sha256=install_receipt.package_manifest_sha256,
            install_receipt_sha256=install_receipt.sha256(),
        )

        quarantine_root = (metadata_root / "quarantine").resolve()
        quarantine_root.mkdir(parents=True, exist_ok=True)
        quarantine = (
            quarantine_root
            / f"{install_receipt.app_id}-{install_receipt.package_manifest_sha256}-{uuid.uuid4()}"
        ).resolve()
        if quarantine.exists():
            raise ValueError("uninstall quarantine destination already exists")
        if root != quarantine and root not in quarantine.parents:
            raise ValueError("uninstall quarantine escaped configured install root")

        resolved_install.replace(quarantine)
        receipt_id = str(uuid.uuid4())
        uninstall_receipt = UninstallReceipt(
            receipt_id=receipt_id,
            timestamp_utc=datetime.now(UTC).isoformat(),
            app_id=install_receipt.app_id,
            package_manifest_sha256=install_receipt.package_manifest_sha256,
            install_receipt_sha256=install_receipt.sha256(),
            installed_tree_sha256=install_receipt.installed_tree_sha256,
            original_install_path=str(resolved_install),
            quarantine_path=str(quarantine),
            registry_path=str(registry),
            launch_authority="disabled",
            status="uninstalled_quarantined",
        )
        receipts = (receipt_root or (metadata_root / "receipts")).expanduser().resolve()
        uninstall_path = receipts / f"uninstall-{receipt_id}.json"

        registry_saved = False
        try:
            updated_registry.save(registry)
            registry_saved = True
            _write_json_atomic(uninstall_path, uninstall_receipt.to_dict())
        except Exception:
            if registry_saved:
                current_registry.save(registry)
            if quarantine.exists() and not resolved_install.exists():
                resolved_install.parent.mkdir(parents=True, exist_ok=True)
                quarantine.replace(resolved_install)
            raise

        return uninstall_receipt
