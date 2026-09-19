from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tomllib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

from .acquisition import SOURCE_ACQUISITION_RECEIPT_SCHEMA_VERSION, review_intake_for_acquisition
from .manifest import AppManifest

BUILD_PLAN_SCHEMA_VERSION = "phios.build_plan.v0.1"
BUILD_PLAN_REVIEW_SCHEMA_VERSION = "phios.build_plan_review.v0.1"

BuildPlanStatus = Literal["ready_for_review", "review_required", "no_build_required"]

_MAX_METADATA_FILE_BYTES = 262_144
_MAX_SOURCE_FILES = 4096
_MAX_SOURCE_BYTES = 128 * 1024 * 1024
_MAX_SOURCE_DIRECTORIES = 8192
_SHA_RE = re.compile(r"^[0-9a-f]{40,64}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_TOOL_RE = re.compile(r"^[A-Za-z0-9._+-]{1,64}$")
_SAFE_RELATIVE_RE = re.compile(r"^[A-Za-z0-9._/@*+-][A-Za-z0-9._/@*+\-{}]*$")

_BUILD_MARKERS = (
    "package.json",
    "package-lock.json",
    "npm-shrinkwrap.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lock",
    "bun.lockb",
    "pyproject.toml",
    "Cargo.toml",
    "Cargo.lock",
    "go.mod",
    "go.sum",
    "index.html",
    "netlify.toml",
    "vite.config.js",
    "vite.config.ts",
)


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, Any], value)


def _string(value: Any, label: str, *, maximum: int = 1024) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    if len(value) > maximum:
        raise ValueError(f"{label} exceeds {maximum} characters")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"{label} contains control characters")
    return value


def _integer(value: Any, label: str, *, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    if value > maximum:
        raise ValueError(f"{label} exceeds the bounded maximum")
    return value


def _sha256(value: Any, label: str) -> str:
    text = _string(value, label, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return text


@dataclass(frozen=True)
class AcquisitionBinding:
    app_id: str
    repository_url: str
    commit_sha: str
    manifest_sha256: str
    acquisition_tree_sha256: str
    archive_sha256: str
    file_count: int
    total_bytes: int
    workspace_path: Path

    @classmethod
    def from_dict(cls, value: Any) -> AcquisitionBinding:
        data = _mapping(value, "acquisition receipt")
        if data.get("schema_version") != SOURCE_ACQUISITION_RECEIPT_SCHEMA_VERSION:
            raise ValueError(
                "Build planning requires a phios.source_acquisition_receipt.v0.1 receipt"
            )
        if data.get("status") != "acquired":
            raise ValueError("Acquisition receipt status must be acquired")

        commit_sha = _string(data.get("commit_sha"), "receipt commit_sha", maximum=64)
        if not _SHA_RE.fullmatch(commit_sha):
            raise ValueError("receipt commit_sha must be a lowercase hexadecimal commit identifier")

        workspace_text = _string(data.get("workspace_path"), "receipt workspace_path", maximum=4096)
        workspace_path = Path(workspace_text).expanduser()
        if not workspace_path.is_absolute():
            raise ValueError("receipt workspace_path must be absolute")

        return cls(
            app_id=_string(data.get("app_id"), "receipt app_id", maximum=64),
            repository_url=_string(
                data.get("repository_url"),
                "receipt repository_url",
                maximum=512,
            ),
            commit_sha=commit_sha,
            manifest_sha256=_sha256(data.get("manifest_sha256"), "receipt manifest_sha256"),
            acquisition_tree_sha256=_sha256(
                data.get("tree_sha256"),
                "receipt tree_sha256",
            ),
            archive_sha256=_sha256(data.get("archive_sha256"), "receipt archive_sha256"),
            file_count=_integer(data.get("file_count"), "receipt file_count", maximum=_MAX_SOURCE_FILES),
            total_bytes=_integer(
                data.get("total_bytes"),
                "receipt total_bytes",
                maximum=_MAX_SOURCE_BYTES,
            ),
            workspace_path=workspace_path,
        )


@dataclass(frozen=True)
class SourceSnapshotEntry:
    path: str
    byte_count: int
    sha256: str

    def canonical_line(self) -> bytes:
        return f"{self.path}\0{self.byte_count}\0{self.sha256}\n".encode("utf-8")


@dataclass(frozen=True)
class ObservedBuildFile:
    path: str
    byte_count: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "byte_count": self.byte_count,
            "sha256": self.sha256,
        }

    @classmethod
    def from_dict(cls, value: Any) -> ObservedBuildFile:
        data = _mapping(value, "observed build file")
        if set(data) != {"path", "byte_count", "sha256"}:
            raise ValueError("observed build file contains missing or unknown fields")
        return cls(
            path=_safe_relative(data["path"], "observed build file path"),
            byte_count=_integer(
                data["byte_count"],
                "observed build file byte_count",
                maximum=_MAX_METADATA_FILE_BYTES,
            ),
            sha256=_sha256(data["sha256"], "observed build file sha256"),
        )


@dataclass(frozen=True)
class BuildStep:
    step_id: str
    phase: str
    tool: str
    argv: tuple[str, ...]
    working_directory: str = "."
    requires_network: bool = False

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", self.step_id):
            raise ValueError(f"Invalid build step id: {self.step_id}")
        if self.phase not in {"dependencies", "build", "package"}:
            raise ValueError(f"Unsupported build step phase: {self.phase}")
        if not _SAFE_TOOL_RE.fullmatch(self.tool):
            raise ValueError(f"Invalid build tool: {self.tool}")
        if not 1 <= len(self.argv) <= 16:
            raise ValueError("Build step argv must contain 1-16 elements")
        if self.argv[0] != self.tool:
            raise ValueError("Build step argv[0] must equal tool")
        for argument in self.argv:
            if not isinstance(argument, str) or not argument or len(argument) > 256:
                raise ValueError("Build step arguments must be bounded non-empty strings")
            if any(ord(char) < 32 for char in argument):
                raise ValueError("Build step arguments must not contain control characters")
        if self.working_directory != ".":
            _safe_relative(self.working_directory, "build step working_directory")

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "phase": self.phase,
            "tool": self.tool,
            "argv": list(self.argv),
            "working_directory": self.working_directory,
            "requires_network": self.requires_network,
        }

    @classmethod
    def from_dict(cls, value: Any) -> BuildStep:
        data = _mapping(value, "build step")
        expected = {
            "step_id",
            "phase",
            "tool",
            "argv",
            "working_directory",
            "requires_network",
        }
        if set(data) != expected:
            raise ValueError("build step contains missing or unknown fields")
        argv = data["argv"]
        if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
            raise ValueError("build step argv must be an array of strings")
        requires_network = data["requires_network"]
        if not isinstance(requires_network, bool):
            raise ValueError("build step requires_network must be Boolean")
        return cls(
            step_id=_string(data["step_id"], "build step step_id", maximum=32),
            phase=_string(data["phase"], "build step phase", maximum=32),
            tool=_string(data["tool"], "build step tool", maximum=64),
            argv=tuple(argv),
            working_directory=_string(
                data["working_directory"],
                "build step working_directory",
                maximum=256,
            ),
            requires_network=requires_network,
        )


@dataclass(frozen=True)
class BuildPlan:
    app_id: str
    repository_url: str
    commit_sha: str
    manifest_sha256: str
    acquisition_tree_sha256: str
    source_snapshot_sha256: str
    source_file_count: int
    source_total_bytes: int
    runtime: str
    strategy: str
    package_manager: str | None
    working_directory: str
    required_tools: tuple[str, ...]
    requested_build_permissions: tuple[str, ...]
    steps: tuple[BuildStep, ...]
    expected_outputs: tuple[str, ...]
    observed_files: tuple[ObservedBuildFile, ...]
    status: BuildPlanStatus
    notes: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = BUILD_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != BUILD_PLAN_SCHEMA_VERSION:
            raise ValueError(f"Unsupported build plan schema: {self.schema_version}")
        if not _SHA_RE.fullmatch(self.commit_sha):
            raise ValueError("build plan commit_sha must be a lowercase hexadecimal identifier")
        _sha256(self.manifest_sha256, "build plan manifest_sha256")
        _sha256(self.acquisition_tree_sha256, "build plan acquisition_tree_sha256")
        _sha256(self.source_snapshot_sha256, "build plan source_snapshot_sha256")
        if self.status not in {"ready_for_review", "review_required", "no_build_required"}:
            raise ValueError(f"Unsupported build plan status: {self.status}")
        if self.package_manager is not None and not _SAFE_TOOL_RE.fullmatch(self.package_manager):
            raise ValueError(f"Invalid package manager: {self.package_manager}")
        if self.working_directory != ".":
            _safe_relative(self.working_directory, "build plan working_directory")
        if len(self.required_tools) > 16 or len(set(self.required_tools)) != len(self.required_tools):
            raise ValueError("required_tools must contain at most 16 unique entries")
        if len(self.requested_build_permissions) > 16 or (
            len(set(self.requested_build_permissions)) != len(self.requested_build_permissions)
        ):
            raise ValueError("requested_build_permissions must contain at most 16 unique entries")
        if len(self.steps) > 8:
            raise ValueError("Build plan may contain at most 8 steps")
        if len(self.expected_outputs) > 16:
            raise ValueError("Build plan may contain at most 16 expected outputs")
        if len(self.observed_files) > len(_BUILD_MARKERS):
            raise ValueError("Build plan observed file count exceeds marker bound")
        if len(self.notes) > 16:
            raise ValueError("Build plan may contain at most 16 notes")

        for tool in self.required_tools:
            if not _SAFE_TOOL_RE.fullmatch(tool):
                raise ValueError(f"Invalid required tool: {tool}")
        for permission in self.requested_build_permissions:
            if not re.fullmatch(r"[a-z0-9][a-z0-9._:-]{0,127}", permission):
                raise ValueError(f"Invalid requested build permission: {permission}")
        for output in self.expected_outputs:
            _safe_output(output)
        for note in self.notes:
            _string(note, "build plan note", maximum=512)

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app_id": self.app_id,
            "repository_url": self.repository_url,
            "commit_sha": self.commit_sha,
            "manifest_sha256": self.manifest_sha256,
            "acquisition_tree_sha256": self.acquisition_tree_sha256,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "source_file_count": self.source_file_count,
            "source_total_bytes": self.source_total_bytes,
            "runtime": self.runtime,
            "strategy": self.strategy,
            "package_manager": self.package_manager,
            "working_directory": self.working_directory,
            "required_tools": list(self.required_tools),
            "requested_build_permissions": list(self.requested_build_permissions),
            "steps": [step.to_dict() for step in self.steps],
            "expected_outputs": list(self.expected_outputs),
            "observed_files": [item.to_dict() for item in self.observed_files],
            "status": self.status,
            "notes": list(self.notes),
        }

    def canonical_json(self) -> str:
        return json.dumps(self.body_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["plan_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> BuildPlan:
        data = _mapping(value, "build plan")
        plan_sha = data.get("plan_sha256")
        expected = {
            "schema_version",
            "app_id",
            "repository_url",
            "commit_sha",
            "manifest_sha256",
            "acquisition_tree_sha256",
            "source_snapshot_sha256",
            "source_file_count",
            "source_total_bytes",
            "runtime",
            "strategy",
            "package_manager",
            "working_directory",
            "required_tools",
            "requested_build_permissions",
            "steps",
            "expected_outputs",
            "observed_files",
            "status",
            "notes",
            "plan_sha256",
        }
        if set(data) != expected:
            raise ValueError("build plan contains missing or unknown fields")
        if data["schema_version"] != BUILD_PLAN_SCHEMA_VERSION:
            raise ValueError(f"Unsupported build plan schema: {data['schema_version']}")

        required_tools = data["required_tools"]
        permissions = data["requested_build_permissions"]
        steps = data["steps"]
        outputs = data["expected_outputs"]
        observed = data["observed_files"]
        notes = data["notes"]
        for sequence, label in (
            (required_tools, "required_tools"),
            (permissions, "requested_build_permissions"),
            (steps, "steps"),
            (outputs, "expected_outputs"),
            (observed, "observed_files"),
            (notes, "notes"),
        ):
            if not isinstance(sequence, list):
                raise ValueError(f"{label} must be an array")

        package_manager = data["package_manager"]
        if package_manager is not None and not isinstance(package_manager, str):
            raise ValueError("package_manager must be string or null")

        plan = cls(
            schema_version=BUILD_PLAN_SCHEMA_VERSION,
            app_id=_string(data["app_id"], "build plan app_id", maximum=64),
            repository_url=_string(
                data["repository_url"],
                "build plan repository_url",
                maximum=512,
            ),
            commit_sha=_string(data["commit_sha"], "build plan commit_sha", maximum=64),
            manifest_sha256=_sha256(
                data["manifest_sha256"],
                "build plan manifest_sha256",
            ),
            acquisition_tree_sha256=_sha256(
                data["acquisition_tree_sha256"],
                "build plan acquisition_tree_sha256",
            ),
            source_snapshot_sha256=_sha256(
                data["source_snapshot_sha256"],
                "build plan source_snapshot_sha256",
            ),
            source_file_count=_integer(
                data["source_file_count"],
                "build plan source_file_count",
                maximum=_MAX_SOURCE_FILES,
            ),
            source_total_bytes=_integer(
                data["source_total_bytes"],
                "build plan source_total_bytes",
                maximum=_MAX_SOURCE_BYTES,
            ),
            runtime=_string(data["runtime"], "build plan runtime", maximum=32),
            strategy=_string(data["strategy"], "build plan strategy", maximum=64),
            package_manager=package_manager,
            working_directory=_string(
                data["working_directory"],
                "build plan working_directory",
                maximum=256,
            ),
            required_tools=tuple(
                _string(item, "required tool", maximum=64) for item in required_tools
            ),
            requested_build_permissions=tuple(
                _string(item, "requested build permission", maximum=128)
                for item in permissions
            ),
            steps=tuple(BuildStep.from_dict(item) for item in steps),
            expected_outputs=tuple(
                _string(item, "expected output", maximum=256) for item in outputs
            ),
            observed_files=tuple(ObservedBuildFile.from_dict(item) for item in observed),
            status=cast(BuildPlanStatus, data["status"]),
            notes=tuple(_string(item, "build plan note", maximum=512) for item in notes),
        )
        if not isinstance(plan_sha, str) or plan.sha256() != plan_sha:
            raise ValueError("Build plan digest does not match canonical plan content")
        return plan


@dataclass(frozen=True)
class BuildPlanReview:
    app_id: str
    commit_sha: str
    plan_sha256: str
    source_snapshot_sha256: str
    status: BuildPlanStatus
    strategy: str
    requested_build_permissions: tuple[str, ...]
    steps: tuple[BuildStep, ...]
    expected_outputs: tuple[str, ...]
    schema_version: str = BUILD_PLAN_REVIEW_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app_id": self.app_id,
            "commit_sha": self.commit_sha,
            "plan_sha256": self.plan_sha256,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "status": self.status,
            "strategy": self.strategy,
            "requested_build_permissions": list(self.requested_build_permissions),
            "steps": [step.to_dict() for step in self.steps],
            "expected_outputs": list(self.expected_outputs),
        }


def review_build_plan(value: Any) -> BuildPlanReview:
    plan = BuildPlan.from_dict(value)
    return BuildPlanReview(
        app_id=plan.app_id,
        commit_sha=plan.commit_sha,
        plan_sha256=plan.sha256(),
        source_snapshot_sha256=plan.source_snapshot_sha256,
        status=plan.status,
        strategy=plan.strategy,
        requested_build_permissions=plan.requested_build_permissions,
        steps=plan.steps,
        expected_outputs=plan.expected_outputs,
    )


def _safe_relative(value: Any, label: str) -> str:
    text = _string(value, label, maximum=256)
    if "\\" in text or text.startswith("/"):
        raise ValueError(f"{label} must be a relative POSIX path")
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{label} must not contain empty, dot, or parent path segments")
    return text


def _safe_output(value: str) -> str:
    text = _string(value, "expected output", maximum=256)
    if text.endswith("/"):
        text = text[:-1]
    if not text:
        raise ValueError("expected output must not be empty")
    if "\\" in text or text.startswith("/"):
        raise ValueError("expected output must be a relative POSIX path or bounded glob")
    if not _SAFE_RELATIVE_RE.fullmatch(text):
        raise ValueError(f"expected output contains unsupported characters: {value}")
    if any(part in {"", ".", ".."} for part in PurePosixPath(text).parts):
        raise ValueError("expected output must not contain unsafe path segments")
    return value


def _source_snapshot(root: Path) -> tuple[str, int, int]:
    if root.is_symlink():
        raise ValueError("Acquired workspace root must not be a symlink")
    if not root.is_dir():
        raise ValueError("Acquired workspace path is not a directory")

    entries: list[SourceSnapshotEntry] = []
    total_bytes = 0
    directory_count = 0
    stack = [root]

    while stack:
        directory = stack.pop()
        directory_count += 1
        if directory_count > _MAX_SOURCE_DIRECTORIES:
            raise ValueError("Acquired source exceeds the bounded directory count")

        with os.scandir(directory) as iterator:
            for item in iterator:
                item_path = Path(item.path)
                if item.is_symlink():
                    raise ValueError(f"Acquired source contains a symlink: {item_path}")
                relative = item_path.relative_to(root).as_posix()
                _safe_relative(relative, "source path")

                if item.is_dir(follow_symlinks=False):
                    stack.append(item_path)
                    continue
                if not item.is_file(follow_symlinks=False):
                    raise ValueError(f"Acquired source contains a special file: {relative}")

                file_stat = item.stat(follow_symlinks=False)
                if not stat.S_ISREG(file_stat.st_mode):
                    raise ValueError(f"Acquired source contains a non-regular file: {relative}")
                if file_stat.st_size > 8 * 1024 * 1024:
                    raise ValueError(f"Acquired source file exceeds the bounded size: {relative}")

                content = item_path.read_bytes()
                if len(content) != file_stat.st_size:
                    raise ValueError(f"Acquired source file changed while planning: {relative}")

                total_bytes += len(content)
                if total_bytes > _MAX_SOURCE_BYTES:
                    raise ValueError("Acquired source exceeds the bounded total byte count")
                entries.append(
                    SourceSnapshotEntry(
                        path=relative,
                        byte_count=len(content),
                        sha256=hashlib.sha256(content).hexdigest(),
                    )
                )
                if len(entries) > _MAX_SOURCE_FILES:
                    raise ValueError("Acquired source exceeds the bounded file count")

    if not entries:
        raise ValueError("Acquired source contains no regular files")

    digest = hashlib.sha256()
    for entry in sorted(entries, key=lambda item: item.path):
        digest.update(entry.canonical_line())
    return digest.hexdigest(), len(entries), total_bytes


def _observe_build_files(root: Path) -> tuple[dict[str, bytes], tuple[ObservedBuildFile, ...]]:
    contents: dict[str, bytes] = {}
    observations: list[ObservedBuildFile] = []
    for name in _BUILD_MARKERS:
        path = root / name
        if not path.exists():
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Build marker is not a regular file: {name}")
        size = path.stat().st_size
        if size > _MAX_METADATA_FILE_BYTES:
            raise ValueError(f"Build marker exceeds {_MAX_METADATA_FILE_BYTES} bytes: {name}")
        content = path.read_bytes()
        if len(content) != size:
            raise ValueError(f"Build marker changed while planning: {name}")
        contents[name] = content
        observations.append(
            ObservedBuildFile(
                path=name,
                byte_count=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
            )
        )
    return contents, tuple(observations)


def _json_metadata(content: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must contain valid bounded UTF-8 JSON") from exc
    return _mapping(value, label)


def _toml_metadata(content: bytes, label: str) -> dict[str, Any]:
    try:
        value = tomllib.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"{label} must contain valid bounded UTF-8 TOML") from exc
    return _mapping(value, label)


def _node_manager(files: dict[str, bytes], package: dict[str, Any]) -> tuple[str, bool, tuple[str, ...]]:
    lock_managers: set[str] = set()
    if "package-lock.json" in files or "npm-shrinkwrap.json" in files:
        lock_managers.add("npm")
    if "pnpm-lock.yaml" in files:
        lock_managers.add("pnpm")
    if "yarn.lock" in files:
        lock_managers.add("yarn")
    if "bun.lock" in files or "bun.lockb" in files:
        lock_managers.add("bun")

    declared_manager: str | None = None
    raw_manager = package.get("packageManager")
    if isinstance(raw_manager, str) and raw_manager:
        declared_manager = raw_manager.split("@", 1)[0]
        if declared_manager not in {"npm", "pnpm", "yarn", "bun"}:
            return "npm", False, (f"Unsupported packageManager declaration: {raw_manager}",)

    if declared_manager is not None and lock_managers and lock_managers != {declared_manager}:
        return declared_manager, False, ("packageManager declaration conflicts with lockfile family",)
    if len(lock_managers) > 1:
        manager = declared_manager or sorted(lock_managers)[0]
        return manager, False, ("multiple package-manager lockfile families observed",)

    if declared_manager is not None:
        return declared_manager, bool(lock_managers), ()
    if lock_managers:
        return next(iter(lock_managers)), True, ()
    return "npm", False, ("no package-manager lockfile or packageManager declaration observed",)


def _node_plan(
    manifest: AppManifest,
    files: dict[str, bytes],
    observed: tuple[ObservedBuildFile, ...],
) -> BuildPlanComponents:
    package_content = files.get("package.json")
    if package_content is None:
        return BuildPlanComponents.review(
            strategy="node_missing_package_metadata",
            observed_files=observed,
            notes=("manifest runtime requires Node-oriented planning but package.json is absent",),
        )

    package = _json_metadata(package_content, "package.json")
    manager, locked, manager_notes = _node_manager(files, package)
    notes = list(manager_notes)
    status: BuildPlanStatus = "ready_for_review" if locked else "review_required"

    scripts = package.get("scripts")
    script_map = scripts if isinstance(scripts, dict) else {}
    build_script = script_map.get("build")
    has_build_script = isinstance(build_script, str) and bool(build_script.strip())

    steps: list[BuildStep] = []
    tools: set[str] = set()
    tools.add(manager)
    if manager != "bun":
        tools.add("node")

    if manager == "npm":
        install_argv = ("npm", "ci") if locked else ("npm", "install")
    elif manager == "pnpm":
        install_argv = (
            ("pnpm", "install", "--frozen-lockfile") if locked else ("pnpm", "install")
        )
    elif manager == "yarn":
        install_argv = (
            ("yarn", "install", "--immutable") if locked else ("yarn", "install")
        )
    else:
        install_argv = (
            ("bun", "install", "--frozen-lockfile") if locked else ("bun", "install")
        )

    steps.append(
        BuildStep(
            step_id="dependencies",
            phase="dependencies",
            tool=manager,
            argv=install_argv,
            requires_network=True,
        )
    )

    expected_outputs: tuple[str, ...] = ()
    if has_build_script:
        steps.append(
            BuildStep(
                step_id="build",
                phase="build",
                tool=manager,
                argv=(manager, "run", "build"),
                requires_network=False,
            )
        )
        dependencies: set[str] = set()
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            value = package.get(key)
            if isinstance(value, dict):
                dependencies.update(str(name) for name in value)

        if "vite.config.js" in files or "vite.config.ts" in files or "vite" in dependencies:
            expected_outputs = ("dist/",)
        elif "next" in dependencies:
            expected_outputs = (".next/",)
        elif "react-scripts" in dependencies:
            expected_outputs = ("build/",)
        else:
            status = "review_required"
            notes.append("build script observed but output location is not deterministically known")
    else:
        notes.append("no package.json build script observed; dependency preparation only")

    strategy = "node_package_manager"
    if manifest.entrypoint.runtime == "static_web" and not has_build_script:
        return BuildPlanComponents(
            strategy="static_web_source",
            package_manager=None,
            required_tools=(),
            requested_permissions=(),
            steps=(),
            expected_outputs=(manifest.entrypoint.target,),
            observed_files=observed,
            status="no_build_required",
            notes=("static web entrypoint is already present in acquired source",),
        )

    return BuildPlanComponents(
        strategy=strategy,
        package_manager=manager,
        required_tools=tuple(sorted(tools)),
        requested_permissions=(
            "build.network.dependencies",
            "build.process.execute",
            "build.workspace.write",
        ),
        steps=tuple(steps),
        expected_outputs=expected_outputs,
        observed_files=observed,
        status=status,
        notes=tuple(notes),
    )


@dataclass(frozen=True)
class BuildPlanComponents:
    strategy: str
    package_manager: str | None
    required_tools: tuple[str, ...]
    requested_permissions: tuple[str, ...]
    steps: tuple[BuildStep, ...]
    expected_outputs: tuple[str, ...]
    observed_files: tuple[ObservedBuildFile, ...]
    status: BuildPlanStatus
    notes: tuple[str, ...]

    @classmethod
    def review(
        cls,
        *,
        strategy: str,
        observed_files: tuple[ObservedBuildFile, ...],
        notes: tuple[str, ...],
    ) -> BuildPlanComponents:
        return cls(
            strategy=strategy,
            package_manager=None,
            required_tools=(),
            requested_permissions=(),
            steps=(),
            expected_outputs=(),
            observed_files=observed_files,
            status="review_required",
            notes=notes,
        )


def _python_plan(
    files: dict[str, bytes],
    observed: tuple[ObservedBuildFile, ...],
) -> BuildPlanComponents:
    pyproject = files.get("pyproject.toml")
    if pyproject is None:
        return BuildPlanComponents.review(
            strategy="python_missing_pyproject",
            observed_files=observed,
            notes=("Python-oriented planning requires pyproject.toml in v0.28",),
        )
    _toml_metadata(pyproject, "pyproject.toml")
    return BuildPlanComponents(
        strategy="python_pep517_wheel",
        package_manager="python-build",
        required_tools=("python", "python-build"),
        requested_permissions=(
            "build.network.dependencies",
            "build.process.execute",
            "build.workspace.write",
        ),
        steps=(
            BuildStep(
                step_id="build",
                phase="build",
                tool="python",
                argv=(
                    "python",
                    "-m",
                    "build",
                    "--wheel",
                    "--outdir",
                    ".phios-build/out",
                    ".",
                ),
                requires_network=True,
            ),
        ),
        expected_outputs=(".phios-build/out/*.whl",),
        observed_files=observed,
        status="ready_for_review",
        notes=("PEP 517 wheel build proposed; isolated build dependencies may require network access",),
    )


def _cargo_plan(
    files: dict[str, bytes],
    observed: tuple[ObservedBuildFile, ...],
) -> BuildPlanComponents:
    cargo = files.get("Cargo.toml")
    if cargo is None:
        return BuildPlanComponents.review(
            strategy="native_missing_cargo_metadata",
            observed_files=observed,
            notes=("Cargo.toml was not observed",),
        )
    _toml_metadata(cargo, "Cargo.toml")
    locked = "Cargo.lock" in files
    argv = ("cargo", "build", "--release", "--locked") if locked else (
        "cargo",
        "build",
        "--release",
    )
    return BuildPlanComponents(
        strategy="rust_cargo_release",
        package_manager="cargo",
        required_tools=("cargo", "rustc"),
        requested_permissions=(
            "build.network.dependencies",
            "build.process.execute",
            "build.workspace.write",
        ),
        steps=(
            BuildStep(
                step_id="build",
                phase="build",
                tool="cargo",
                argv=argv,
                requires_network=True,
            ),
        ),
        expected_outputs=("target/release/",),
        observed_files=observed,
        status="ready_for_review" if locked else "review_required",
        notes=() if locked else ("Cargo.lock absent; dependency resolution is not lockfile-pinned",),
    )


def _go_plan(
    files: dict[str, bytes],
    observed: tuple[ObservedBuildFile, ...],
) -> BuildPlanComponents:
    go_mod = files.get("go.mod")
    if go_mod is None:
        return BuildPlanComponents.review(
            strategy="native_missing_go_metadata",
            observed_files=observed,
            notes=("go.mod was not observed",),
        )
    try:
        go_mod.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("go.mod must contain valid bounded UTF-8 text") from exc

    notes = ["Go package output topology is not inferred in v0.28"]
    if "go.sum" not in files:
        notes.append("go.sum absent; module dependency content is not checksum-pinned by go.sum")
    return BuildPlanComponents(
        strategy="go_module_build",
        package_manager="go",
        required_tools=("go",),
        requested_permissions=(
            "build.network.dependencies",
            "build.process.execute",
            "build.workspace.write",
        ),
        steps=(
            BuildStep(
                step_id="build",
                phase="build",
                tool="go",
                argv=("go", "build", "./..."),
                requires_network=True,
            ),
        ),
        expected_outputs=(),
        observed_files=observed,
        status="review_required",
        notes=tuple(notes),
    )


def _static_plan(
    manifest: AppManifest,
    files: dict[str, bytes],
    observed: tuple[ObservedBuildFile, ...],
) -> BuildPlanComponents:
    if "package.json" in files:
        return _node_plan(manifest, files, observed)
    target = manifest.entrypoint.target
    if not (Path(target).parts and (Path(target)).as_posix()):
        return BuildPlanComponents.review(
            strategy="static_web_invalid_target",
            observed_files=observed,
            notes=("static web entrypoint target is invalid",),
        )
    return BuildPlanComponents(
        strategy="static_web_source",
        package_manager=None,
        required_tools=(),
        requested_permissions=(),
        steps=(),
        expected_outputs=(target,),
        observed_files=observed,
        status="no_build_required",
        notes=("static web source requires no build step in v0.28",),
    )


def _components_for(
    manifest: AppManifest,
    files: dict[str, bytes],
    observed: tuple[ObservedBuildFile, ...],
) -> BuildPlanComponents:
    runtime = manifest.entrypoint.runtime
    if runtime == "node":
        return _node_plan(manifest, files, observed)
    if runtime == "python":
        return _python_plan(files, observed)
    if runtime == "static_web":
        return _static_plan(manifest, files, observed)
    if runtime == "local_http":
        ecosystems = [
            name
            for name, present in (
                ("node", "package.json" in files),
                ("python", "pyproject.toml" in files),
            )
            if present
        ]
        if ecosystems == ["node"]:
            return _node_plan(manifest, files, observed)
        if ecosystems == ["python"]:
            return _python_plan(files, observed)
        return BuildPlanComponents.review(
            strategy="local_http_ambiguous_build_family",
            observed_files=observed,
            notes=(
                "local_http runtime requires exactly one supported root build family in v0.28",
            ),
        )
    if runtime == "native":
        native = [
            name
            for name, present in (
                ("cargo", "Cargo.toml" in files),
                ("go", "go.mod" in files),
            )
            if present
        ]
        if native == ["cargo"]:
            return _cargo_plan(files, observed)
        if native == ["go"]:
            return _go_plan(files, observed)
        return BuildPlanComponents.review(
            strategy="native_ambiguous_build_family",
            observed_files=observed,
            notes=("native runtime requires exactly one supported Cargo or Go root family",),
        )
    return BuildPlanComponents.review(
        strategy="unsupported_runtime",
        observed_files=observed,
        notes=(f"unsupported manifest runtime: {runtime}",),
    )


def plan_build_from_payloads(
    intake_value: Any,
    acquisition_receipt_value: Any,
) -> BuildPlan:
    intake = review_intake_for_acquisition(intake_value)
    binding = AcquisitionBinding.from_dict(acquisition_receipt_value)

    if binding.app_id != intake.manifest.app_id:
        raise ValueError("Acquisition receipt app_id does not match intake manifest")
    if binding.repository_url.lower() != intake.repository_url.lower():
        raise ValueError("Acquisition receipt repository does not match intake evidence")
    if binding.commit_sha != intake.commit_sha:
        raise ValueError("Acquisition receipt commit does not match intake evidence")
    if binding.manifest_sha256 != intake.manifest_sha256:
        raise ValueError("Acquisition receipt manifest digest does not match intake manifest")

    workspace = binding.workspace_path
    if workspace.is_symlink():
        raise ValueError("Acquisition receipt workspace path must not be a symlink")
    try:
        root = workspace.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Acquisition receipt workspace path is unavailable") from exc

    snapshot_sha, file_count, total_bytes = _source_snapshot(root)
    if file_count != binding.file_count:
        raise ValueError("Current source file count does not match acquisition receipt")
    if total_bytes != binding.total_bytes:
        raise ValueError("Current source byte count does not match acquisition receipt")

    files, observed = _observe_build_files(root)
    components = _components_for(intake.manifest, files, observed)

    notes = list(components.notes)
    notes.append(
        "source_snapshot_sha256 identifies current file paths and bytes at planning time; "
        "v0.27 acquisition_tree_sha256 remains separate provenance because executable-mode "
        "metadata is not portable across all supported host filesystems"
    )
    notes.append("build steps are declarative argv arrays; v0.28 executes no process")

    return BuildPlan(
        app_id=intake.manifest.app_id,
        repository_url=intake.repository_url,
        commit_sha=intake.commit_sha,
        manifest_sha256=intake.manifest_sha256,
        acquisition_tree_sha256=binding.acquisition_tree_sha256,
        source_snapshot_sha256=snapshot_sha,
        source_file_count=file_count,
        source_total_bytes=total_bytes,
        runtime=intake.manifest.entrypoint.runtime,
        strategy=components.strategy,
        package_manager=components.package_manager,
        working_directory=".",
        required_tools=components.required_tools,
        requested_build_permissions=components.requested_permissions,
        steps=components.steps,
        expected_outputs=components.expected_outputs,
        observed_files=components.observed_files,
        status=components.status,
        notes=tuple(notes),
    )
