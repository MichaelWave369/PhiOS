from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Literal, cast

from .intake import AppIntakeResult, inspect_public_github_app

REPO_PROFILE_SCHEMA_VERSION = "phios.repo_profile.v0.1"
REPO_COMPATIBILITY_SCHEMA_VERSION = "phios.repo_compatibility.v0.1"

RepoCompatibilityStatus = Literal[
    "SUPPORTED_AFTER_OPERATOR_APPROVAL",
    "REPOSITORY_DISABLED",
    "ARCHIVED_REPOSITORY_REVIEW",
    "NOT_AN_APPLICATION",
    "MANIFEST_REVIEW_REQUIRED",
    "LICENSE_REVIEW_REQUIRED",
    "SUBMODULE_REQUIRED",
    "LFS_REVIEW_REQUIRED",
    "MISSING_TOOLCHAIN",
    "LOCKFILE_REQUIRED",
    "UNSUPPORTED_RUNTIME",
]

RepoBuildFamily = Literal[
    "static_web",
    "node_npm",
    "node_pnpm",
    "node_yarn",
    "node_bun",
    "node_unlocked",
    "python_pep517",
    "rust_cargo",
    "go_module",
    "unknown",
]

_SHA_RE = re.compile(r"^[0-9a-f]{40,64}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_MIT_LICENSE_IDS = {"MIT", "MIT-0"}
_MANIFEST_REVIEW_STATUSES = {
    "invalid_declared_manifest",
    "declared_source_mismatch",
}
_TOOLCHAIN_BLOCKERS = {
    "node_pnpm",
    "node_yarn",
    "node_bun",
}


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


def _bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def _true(value: Any, label: str) -> bool:
    if value is not True:
        raise ValueError(f"{label} must remain true")
    return True


def _false(value: Any, label: str) -> bool:
    if value is not False:
        raise ValueError(f"{label} must remain false")
    return False


def _canonical_sha256(value: dict[str, Any]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_family(
    runtime: str | None,
    target: str | None,
    root_paths: tuple[str, ...],
) -> RepoBuildFamily:
    roots = set(root_paths)

    if runtime == "static_web":
        return "static_web"

    if runtime == "node":
        if "package-lock.json" in roots or "npm-shrinkwrap.json" in roots:
            return "node_npm"
        if "pnpm-lock.yaml" in roots:
            return "node_pnpm"
        if "yarn.lock" in roots:
            return "node_yarn"
        if "bun.lock" in roots or "bun.lockb" in roots:
            return "node_bun"
        return "node_unlocked"

    if runtime == "python":
        return "python_pep517"

    if runtime == "native":
        if target == "Cargo.toml" or "Cargo.toml" in roots:
            return "rust_cargo"
        if target == "go.mod" or "go.mod" in roots:
            return "go_module"

    return "unknown"


def _manifest_source(intake: AppIntakeResult) -> str:
    if intake.proposal.status == "declared_manifest":
        return "declared"
    if intake.proposal.status == "inferred_candidate":
        return "inferred"
    return "none"


@dataclass(frozen=True)
class RepoProfile:
    repository_url: str
    owner: str
    name: str
    head_sha: str
    archived: bool
    disabled: bool
    intake_status: str
    manifest_source: str
    app_id: str | None
    runtime: str | None
    target: str | None
    license_expression: str
    license_state: str
    build_family: RepoBuildFamily
    root_markers: tuple[str, ...]
    submodule_marker_observed: bool
    gitattributes_marker_observed: bool
    lfs_config_marker_observed: bool
    profile_authority: bool = False
    acquisition_authority: bool = False
    build_authority: bool = False
    install_authority: bool = False
    launch_authority: bool = False
    schema_version: str = REPO_PROFILE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REPO_PROFILE_SCHEMA_VERSION:
            raise ValueError(f"Unsupported repo profile schema: {self.schema_version}")
        _string(self.repository_url, "repository_url", maximum=512)
        _string(self.owner, "owner", maximum=100)
        _string(self.name, "name", maximum=100)
        if not _SHA_RE.fullmatch(self.head_sha):
            raise ValueError("head_sha must be a lowercase hexadecimal commit identifier")
        _bool(self.archived, "archived")
        _bool(self.disabled, "disabled")
        _string(self.intake_status, "intake_status", maximum=64)
        if self.manifest_source not in {"declared", "inferred", "none"}:
            raise ValueError("manifest_source must be declared, inferred, or none")
        if self.app_id is not None:
            _string(self.app_id, "app_id", maximum=64)
        if self.runtime is not None:
            _string(self.runtime, "runtime", maximum=32)
        if self.target is not None:
            _string(self.target, "target", maximum=512)
        _string(self.license_expression, "license_expression", maximum=128)
        if self.license_state not in {"mit_confirmed", "declared_other", "unasserted"}:
            raise ValueError("unsupported license_state")
        if self.build_family not in {
            "static_web",
            "node_npm",
            "node_pnpm",
            "node_yarn",
            "node_bun",
            "node_unlocked",
            "python_pep517",
            "rust_cargo",
            "go_module",
            "unknown",
        }:
            raise ValueError("unsupported build_family")
        if tuple(sorted(set(self.root_markers))) != self.root_markers:
            raise ValueError("root_markers must be sorted and unique")
        _bool(self.submodule_marker_observed, "submodule_marker_observed")
        _bool(self.gitattributes_marker_observed, "gitattributes_marker_observed")
        _bool(self.lfs_config_marker_observed, "lfs_config_marker_observed")
        if any(
            value is not False
            for value in (
                self.profile_authority,
                self.acquisition_authority,
                self.build_authority,
                self.install_authority,
                self.launch_authority,
            )
        ):
            raise ValueError("repository profiling never grants authority")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "repository_url": self.repository_url,
            "owner": self.owner,
            "name": self.name,
            "head_sha": self.head_sha,
            "archived": self.archived,
            "disabled": self.disabled,
            "intake_status": self.intake_status,
            "manifest_source": self.manifest_source,
            "app_id": self.app_id,
            "runtime": self.runtime,
            "target": self.target,
            "license_expression": self.license_expression,
            "license_state": self.license_state,
            "build_family": self.build_family,
            "root_markers": list(self.root_markers),
            "submodule_marker_observed": self.submodule_marker_observed,
            "gitattributes_marker_observed": self.gitattributes_marker_observed,
            "lfs_config_marker_observed": self.lfs_config_marker_observed,
            "profile_authority": False,
            "acquisition_authority": False,
            "build_authority": False,
            "install_authority": False,
            "launch_authority": False,
        }

    def sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["profile_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> RepoProfile:
        if not isinstance(value, dict):
            raise ValueError("repo profile must be an object")
        data = cast(dict[str, Any], value)
        expected = {
            "schema_version",
            "repository_url",
            "owner",
            "name",
            "head_sha",
            "archived",
            "disabled",
            "intake_status",
            "manifest_source",
            "app_id",
            "runtime",
            "target",
            "license_expression",
            "license_state",
            "build_family",
            "root_markers",
            "submodule_marker_observed",
            "gitattributes_marker_observed",
            "lfs_config_marker_observed",
            "profile_authority",
            "acquisition_authority",
            "build_authority",
            "install_authority",
            "launch_authority",
            "profile_sha256",
        }
        if set(data) != expected:
            raise ValueError("repo profile contains missing or unknown fields")
        roots = data["root_markers"]
        if not isinstance(roots, list) or not all(isinstance(item, str) for item in roots):
            raise ValueError("root_markers must be an array of strings")
        profile = cls(
            schema_version=_string(data["schema_version"], "schema_version", maximum=64),
            repository_url=_string(
                data["repository_url"], "repository_url", maximum=512
            ),
            owner=_string(data["owner"], "owner", maximum=100),
            name=_string(data["name"], "name", maximum=100),
            head_sha=_string(data["head_sha"], "head_sha", maximum=64),
            archived=_bool(data["archived"], "archived"),
            disabled=_bool(data["disabled"], "disabled"),
            intake_status=_string(
                data["intake_status"], "intake_status", maximum=64
            ),
            manifest_source=_string(
                data["manifest_source"], "manifest_source", maximum=16
            ),
            app_id=(
                None
                if data["app_id"] is None
                else _string(data["app_id"], "app_id", maximum=64)
            ),
            runtime=(
                None
                if data["runtime"] is None
                else _string(data["runtime"], "runtime", maximum=32)
            ),
            target=(
                None
                if data["target"] is None
                else _string(data["target"], "target", maximum=512)
            ),
            license_expression=_string(
                data["license_expression"], "license_expression", maximum=128
            ),
            license_state=_string(
                data["license_state"], "license_state", maximum=32
            ),
            build_family=cast(RepoBuildFamily, data["build_family"]),
            root_markers=tuple(roots),
            submodule_marker_observed=_bool(
                data["submodule_marker_observed"], "submodule_marker_observed"
            ),
            gitattributes_marker_observed=_bool(
                data["gitattributes_marker_observed"],
                "gitattributes_marker_observed",
            ),
            lfs_config_marker_observed=_bool(
                data["lfs_config_marker_observed"], "lfs_config_marker_observed"
            ),
            profile_authority=_false(
                data["profile_authority"], "profile_authority"
            ),
            acquisition_authority=_false(
                data["acquisition_authority"], "acquisition_authority"
            ),
            build_authority=_false(data["build_authority"], "build_authority"),
            install_authority=_false(
                data["install_authority"], "install_authority"
            ),
            launch_authority=_false(
                data["launch_authority"], "launch_authority"
            ),
        )
        if data["profile_sha256"] != profile.sha256():
            raise ValueError("repo profile digest does not match canonical content")
        return profile


@dataclass(frozen=True)
class RepoCompatibilityAssessment:
    profile_sha256: str
    repository_url: str
    head_sha: str
    status: RepoCompatibilityStatus
    blocking_reasons: tuple[str, ...]
    advisory_notes: tuple[str, ...]
    next_gate: str
    license_policy: str = "mit_only"
    advisory_only: bool = True
    acquisition_authority: bool = False
    build_authority: bool = False
    install_authority: bool = False
    launch_authority: bool = False
    schema_version: str = REPO_COMPATIBILITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REPO_COMPATIBILITY_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported repo compatibility schema: {self.schema_version}"
            )
        _sha256(self.profile_sha256, "profile_sha256")
        _string(self.repository_url, "repository_url", maximum=512)
        if not _SHA_RE.fullmatch(self.head_sha):
            raise ValueError("head_sha must be a lowercase hexadecimal commit identifier")
        if self.status not in {
            "SUPPORTED_AFTER_OPERATOR_APPROVAL",
            "REPOSITORY_DISABLED",
            "ARCHIVED_REPOSITORY_REVIEW",
            "NOT_AN_APPLICATION",
            "MANIFEST_REVIEW_REQUIRED",
            "LICENSE_REVIEW_REQUIRED",
            "SUBMODULE_REQUIRED",
            "LFS_REVIEW_REQUIRED",
            "MISSING_TOOLCHAIN",
            "LOCKFILE_REQUIRED",
            "UNSUPPORTED_RUNTIME",
        }:
            raise ValueError(f"unsupported compatibility status: {self.status}")
        if self.license_policy != "mit_only":
            raise ValueError("v0.58 supports only the mit_only compatibility policy")
        if self.advisory_only is not True:
            raise ValueError("v0.58 compatibility assessments are advisory-only")
        _string(self.next_gate, "next_gate", maximum=128)
        if tuple(sorted(set(self.blocking_reasons))) != self.blocking_reasons:
            raise ValueError("blocking_reasons must be sorted and unique")
        if tuple(sorted(set(self.advisory_notes))) != self.advisory_notes:
            raise ValueError("advisory_notes must be sorted and unique")
        if self.status == "SUPPORTED_AFTER_OPERATOR_APPROVAL" and self.blocking_reasons:
            raise ValueError("supported assessments must not contain blocking reasons")
        if self.status != "SUPPORTED_AFTER_OPERATOR_APPROVAL" and not self.blocking_reasons:
            raise ValueError("blocked/review assessments require a blocking reason")
        if any(
            value is not False
            for value in (
                self.acquisition_authority,
                self.build_authority,
                self.install_authority,
                self.launch_authority,
            )
        ):
            raise ValueError("compatibility assessment never grants authority")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile_sha256": self.profile_sha256,
            "repository_url": self.repository_url,
            "head_sha": self.head_sha,
            "status": self.status,
            "blocking_reasons": list(self.blocking_reasons),
            "advisory_notes": list(self.advisory_notes),
            "next_gate": self.next_gate,
            "license_policy": self.license_policy,
            "advisory_only": True,
            "acquisition_authority": False,
            "build_authority": False,
            "install_authority": False,
            "launch_authority": False,
        }

    def sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["assessment_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> RepoCompatibilityAssessment:
        if not isinstance(value, dict):
            raise ValueError("repo compatibility assessment must be an object")
        data = cast(dict[str, Any], value)
        expected = {
            "schema_version",
            "profile_sha256",
            "repository_url",
            "head_sha",
            "status",
            "blocking_reasons",
            "advisory_notes",
            "next_gate",
            "license_policy",
            "advisory_only",
            "acquisition_authority",
            "build_authority",
            "install_authority",
            "launch_authority",
            "assessment_sha256",
        }
        if set(data) != expected:
            raise ValueError(
                "repo compatibility assessment contains missing or unknown fields"
            )
        reasons = data["blocking_reasons"]
        notes = data["advisory_notes"]
        if not isinstance(reasons, list) or not all(
            isinstance(item, str) for item in reasons
        ):
            raise ValueError("blocking_reasons must be an array of strings")
        if not isinstance(notes, list) or not all(
            isinstance(item, str) for item in notes
        ):
            raise ValueError("advisory_notes must be an array of strings")
        assessment = cls(
            schema_version=_string(data["schema_version"], "schema_version", maximum=64),
            profile_sha256=_sha256(data["profile_sha256"], "profile_sha256"),
            repository_url=_string(
                data["repository_url"], "repository_url", maximum=512
            ),
            head_sha=_string(data["head_sha"], "head_sha", maximum=64),
            status=cast(RepoCompatibilityStatus, data["status"]),
            blocking_reasons=tuple(reasons),
            advisory_notes=tuple(notes),
            next_gate=_string(data["next_gate"], "next_gate", maximum=128),
            license_policy=_string(
                data["license_policy"], "license_policy", maximum=32
            ),
            advisory_only=_true(data["advisory_only"], "advisory_only"),
            acquisition_authority=_false(
                data["acquisition_authority"], "acquisition_authority"
            ),
            build_authority=_false(data["build_authority"], "build_authority"),
            install_authority=_false(
                data["install_authority"], "install_authority"
            ),
            launch_authority=_false(
                data["launch_authority"], "launch_authority"
            ),
        )
        if data["assessment_sha256"] != assessment.sha256():
            raise ValueError(
                "repo compatibility assessment digest does not match canonical content"
            )
        return assessment


@dataclass(frozen=True)
class RepoProfileResult:
    profile: RepoProfile
    compatibility: RepoCompatibilityAssessment

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.to_dict(),
            "compatibility": self.compatibility.to_dict(),
        }


def _license_state(expression: str) -> str:
    normalized = expression.strip()
    if normalized in _MIT_LICENSE_IDS:
        return "mit_confirmed"
    if not normalized or normalized == "NOASSERTION":
        return "unasserted"
    return "declared_other"


def profile_intake_result(intake: AppIntakeResult) -> RepoProfileResult:
    roots = tuple(sorted(set(intake.evidence.root_paths)))
    runtime = intake.proposal.runtime
    target = intake.proposal.target
    license_expression = intake.proposal.license_expression or "NOASSERTION"

    profile = RepoProfile(
        repository_url=intake.evidence.repository_url,
        owner=intake.evidence.owner,
        name=intake.evidence.name,
        head_sha=intake.evidence.head_sha,
        archived=intake.evidence.archived,
        disabled=intake.evidence.disabled,
        intake_status=intake.proposal.status,
        manifest_source=_manifest_source(intake),
        app_id=intake.proposal.app_id,
        runtime=runtime,
        target=target,
        license_expression=license_expression,
        license_state=_license_state(license_expression),
        build_family=_build_family(runtime, target, roots),
        root_markers=roots,
        submodule_marker_observed=".gitmodules" in roots,
        gitattributes_marker_observed=".gitattributes" in roots,
        lfs_config_marker_observed=".lfsconfig" in roots,
    )

    status: RepoCompatibilityStatus
    reasons: list[str] = []
    notes: list[str] = []
    next_gate: str

    if profile.disabled:
        status = "REPOSITORY_DISABLED"
        reasons.append("GitHub reports disabled=true for the repository")
        next_gate = "repository_reenable_or_operator_review"
    elif profile.intake_status in _MANIFEST_REVIEW_STATUSES:
        status = "MANIFEST_REVIEW_REQUIRED"
        reasons.append(f"intake status is {profile.intake_status}")
        next_gate = "repair_declared_manifest"
    elif profile.manifest_source == "none" or profile.runtime is None:
        status = "NOT_AN_APPLICATION"
        reasons.append("bounded intake found no supported root application marker")
        next_gate = "add_phios_app_manifest_or_supported_root_marker"
    elif profile.license_state != "mit_confirmed":
        status = "LICENSE_REVIEW_REQUIRED"
        reasons.append(
            "v0.58 mit_only policy requires an MIT or MIT-0 license assertion"
        )
        next_gate = "license_review"
    elif profile.submodule_marker_observed:
        status = "SUBMODULE_REQUIRED"
        reasons.append(
            "repository root contains .gitmodules but v0.27 exact source "
            "acquisition does not acquire submodule content"
        )
        next_gate = "submodule_acquisition_adapter"
    elif profile.lfs_config_marker_observed or profile.gitattributes_marker_observed:
        status = "LFS_REVIEW_REQUIRED"
        reasons.append(
            "repository contains Git attributes/LFS markers that bounded intake "
            "does not prove are ordinary source bytes"
        )
        next_gate = "git_lfs_review"
    elif profile.build_family in _TOOLCHAIN_BLOCKERS:
        status = "MISSING_TOOLCHAIN"
        reasons.append(
            f"v0.51 toolchain capsules do not yet support {profile.build_family}"
        )
        next_gate = "add_toolchain_capsule_adapter"
    elif profile.build_family == "node_unlocked":
        status = "LOCKFILE_REQUIRED"
        reasons.append(
            "Node repository has no supported deterministic root lockfile for "
            "the governed dependency path"
        )
        next_gate = "add_supported_lockfile_or_declared_no_dependency_path"
    elif profile.runtime == "native":
        status = "UNSUPPORTED_RUNTIME"
        reasons.append(
            "current installed runtime path does not launch native Rust/Go application artifacts"
        )
        next_gate = "native_runtime_adapter"
    elif profile.runtime == "python" and (
        profile.manifest_source != "declared"
        or profile.target is None
        or not profile.target.endswith(".py")
    ):
        status = "UNSUPPORTED_RUNTIME"
        reasons.append(
            "current direct Python runtime requires a declared executable .py "
            "entrypoint rather than inferred pyproject.toml"
        )
        next_gate = "declare_python_entrypoint_or_add_python_package_runtime_adapter"
    elif profile.runtime not in {"node", "python", "static_web"}:
        status = "UNSUPPORTED_RUNTIME"
        reasons.append(
            f"current app runtime path does not support runtime={profile.runtime}"
        )
        next_gate = "runtime_adapter"
    else:
        status = "SUPPORTED_AFTER_OPERATOR_APPROVAL"
        next_gate = "v0.27_source_acquisition_review"
        notes.append(
            "profile support means no v0.58 blocker was observed; later acquisition, "
            "build, dependency, runtime, install and launch gates still apply"
        )

    if profile.archived:
        notes.append("GitHub reports archived=true")
        if status == "SUPPORTED_AFTER_OPERATOR_APPROVAL":
            status = "ARCHIVED_REPOSITORY_REVIEW"
            reasons.append(
                "archived repositories require explicit operator review before acquisition"
            )
            next_gate = "archived_repository_review"

    if profile.manifest_source == "inferred":
        notes.append(
            "manifest was inferred; permissions and redistribution remain unproven"
        )
    if profile.manifest_source == "declared":
        notes.append("valid root phios-app.json was observed by bounded intake")

    assessment = RepoCompatibilityAssessment(
        profile_sha256=profile.sha256(),
        repository_url=profile.repository_url,
        head_sha=profile.head_sha,
        status=status,
        blocking_reasons=tuple(sorted(set(reasons))),
        advisory_notes=tuple(sorted(set(notes))),
        next_gate=next_gate,
    )
    return RepoProfileResult(profile=profile, compatibility=assessment)


def profile_public_github_repository(repository_url: str) -> RepoProfileResult:
    return profile_intake_result(inspect_public_github_app(repository_url))
