from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from .desktop_update import _contained, _load_bundle, _read_json, _root, _verify_current_bundle
from .intake import GitHubJsonClient, GitHubRepositoryRef, JsonHttpClient
from .manifest import AppManifest
from .release_discovery import unwrap_release_candidate_intake

RELEASE_CHANGE_EVIDENCE_SCHEMA_VERSION = "phios.release_change_evidence.v0.1"

_MAX_ROOT_ENTRIES = 512
_SHA_RE = re.compile(r"^[0-9a-f]{40,64}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

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


def _string(value: Any, label: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    if len(value) > maximum:
        raise ValueError(f"{label} exceeds {maximum} characters")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"{label} contains control characters")
    return value


def _sha(value: Any, label: str) -> str:
    text = _string(value, label, maximum=64).lower()
    if not _SHA_RE.fullmatch(text):
        raise ValueError(f"{label} must be a 40-64 character hexadecimal commit")
    return text


def _sha256(value: Any, label: str) -> str:
    text = _string(value, label, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return text


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _api_url(ref: GitHubRepositoryRef, commit_sha: str) -> str:
    owner = urllib.parse.quote(ref.owner, safe="")
    name = urllib.parse.quote(ref.name, safe="")
    commit = urllib.parse.quote(commit_sha, safe="")
    return f"https://api.github.com/repos/{owner}/{name}/contents?ref={commit}"


@dataclass(frozen=True)
class SourceMarker:
    path: str
    provider_object_type: str
    byte_count: int | None
    provider_blob_id: str | None

    def __post_init__(self) -> None:
        if self.path not in _BUILD_MARKERS:
            raise ValueError(f"unsupported build marker path: {self.path}")
        if self.provider_object_type not in {"file", "dir", "symlink", "submodule"}:
            raise ValueError("unsupported GitHub contents object type")
        if self.byte_count is not None and (
            isinstance(self.byte_count, bool)
            or not isinstance(self.byte_count, int)
            or self.byte_count < 0
        ):
            raise ValueError("source marker byte_count must be non-negative or null")
        if self.provider_blob_id is not None:
            if not re.fullmatch(r"[0-9a-fA-F]{40,64}", self.provider_blob_id):
                raise ValueError("source marker provider_blob_id is invalid")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SourceMarkerChange:
    path: str
    change: str
    active: SourceMarker | None
    candidate: SourceMarker | None

    def __post_init__(self) -> None:
        if self.path not in _BUILD_MARKERS:
            raise ValueError("unsupported source marker change path")
        if self.change not in {"added", "removed", "changed", "unchanged", "type_changed"}:
            raise ValueError("unsupported source marker change type")

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "change": self.change,
            "active": self.active.to_dict() if self.active is not None else None,
            "candidate": self.candidate.to_dict() if self.candidate is not None else None,
        }


class BuildMarkerProvider(Protocol):
    request_count: int

    def observe(
        self,
        repository_url: str,
        commit_sha: str,
    ) -> tuple[SourceMarker, ...]: ...


class GitHubBuildMarkerProvider:
    """Observe a closed root-level build-marker set at one exact Git commit."""

    def __init__(self, client: JsonHttpClient | None = None) -> None:
        self.client = client or GitHubJsonClient(max_requests=8)

    @property
    def request_count(self) -> int:
        return self.client.request_count

    def observe(
        self,
        repository_url: str,
        commit_sha: str,
    ) -> tuple[SourceMarker, ...]:
        ref = GitHubRepositoryRef.parse(repository_url)
        commit = _sha(commit_sha, "build marker commit_sha")
        root = self.client.get_json(_api_url(ref, commit))
        if not isinstance(root, list):
            raise ValueError("GitHub exact-commit root listing must be an array")
        if len(root) > _MAX_ROOT_ENTRIES:
            raise ValueError("GitHub exact-commit root listing exceeds bounded entry count")

        markers: list[SourceMarker] = []
        seen: set[str] = set()
        for raw in root:
            entry = _mapping(raw, "GitHub exact-commit root entry")
            path = entry.get("path")
            if path not in _BUILD_MARKERS:
                continue
            if path in seen:
                raise ValueError("GitHub exact-commit root contains duplicate build marker")
            seen.add(path)
            object_type = _string(
                entry.get("type"),
                "GitHub build marker object type",
                maximum=32,
            )
            size = entry.get("size")
            byte_count: int | None
            if size is None:
                byte_count = None
            elif isinstance(size, bool) or not isinstance(size, int) or size < 0:
                raise ValueError("GitHub build marker size is invalid")
            else:
                byte_count = size
            raw_sha = entry.get("sha")
            blob_id = None
            if raw_sha is not None:
                blob_id = _string(
                    raw_sha,
                    "GitHub build marker provider blob id",
                    maximum=64,
                ).lower()
            markers.append(
                SourceMarker(
                    path=path,
                    provider_object_type=object_type,
                    byte_count=byte_count,
                    provider_blob_id=blob_id,
                )
            )
        return tuple(sorted(markers, key=lambda item: item.path))


@dataclass(frozen=True)
class ActiveReleaseBaseline:
    app_id: str
    version: str
    repository_url: str
    commit_sha: str
    manifest: AppManifest
    manifest_sha256: str
    active_bundle_path: str
    active_grant_sha256: str


def _active_baseline(
    active_bundle_path: Path,
    *,
    install_root: Path,
    desktop_root: Path,
    applications_root: Path,
) -> ActiveReleaseBaseline:
    desktop = _root(desktop_root, "desktop app bundle root")
    installed = _root(install_root, "installed app root")
    applications = _root(applications_root, "desktop applications root")
    bundle = _load_bundle(active_bundle_path, desktop_root=desktop)
    _verify_current_bundle(
        bundle,
        install_root=installed,
        applications_root=applications,
        require_active_entry=True,
    )

    install_path = _contained(
        installed,
        Path(bundle.install_receipt.install_path),
        "active installed app",
    )
    manifest = AppManifest.from_dict(
        _read_json(install_path / ".phios" / "manifest.json", "active app manifest")
    )
    if manifest.sha256() != bundle.install_receipt.manifest_sha256:
        raise ValueError("active app manifest changed since install receipt")
    if manifest.app_id != bundle.plan.app_id or manifest.version != bundle.plan.app_version:
        raise ValueError("active app manifest identity does not match desktop bundle")
    if (
        GitHubRepositoryRef.parse(manifest.source.repository_url).repository_url.lower()
        != GitHubRepositoryRef.parse(bundle.install_receipt.repository_url).repository_url.lower()
    ):
        raise ValueError("active manifest repository does not match install receipt")
    commit_sha = _sha(bundle.install_receipt.commit_sha, "active install commit_sha")
    return ActiveReleaseBaseline(
        app_id=manifest.app_id,
        version=manifest.version,
        repository_url=GitHubRepositoryRef.parse(
            manifest.source.repository_url
        ).repository_url,
        commit_sha=commit_sha,
        manifest=manifest,
        manifest_sha256=manifest.sha256(),
        active_bundle_path=str(bundle.path),
        active_grant_sha256=bundle.grant.sha256(),
    )


@dataclass(frozen=True)
class ReleaseChangeEvidence:
    app_id: str
    repository_url: str
    active_version: str
    candidate_version: str
    active_commit_sha: str
    candidate_commit_sha: str
    active_manifest_sha256: str
    candidate_manifest_sha256: str
    release_candidate_intake_sha256: str
    active_bundle_path: str
    active_grant_sha256: str
    manifest_changes: tuple[str, ...]
    permissions_added: tuple[str, ...]
    permissions_removed: tuple[str, ...]
    source_marker_changes: tuple[SourceMarkerChange, ...]
    provider_request_count: int
    compatibility_verdict: str = "not_assessed"
    build_authority: bool = False
    install_authority: bool = False
    update_authority: bool = False
    schema_version: str = RELEASE_CHANGE_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RELEASE_CHANGE_EVIDENCE_SCHEMA_VERSION:
            raise ValueError("unsupported release change evidence schema")
        _string(self.app_id, "app_id", maximum=64)
        GitHubRepositoryRef.parse(self.repository_url)
        _string(self.active_version, "active_version", maximum=128)
        _string(self.candidate_version, "candidate_version", maximum=128)
        _sha(self.active_commit_sha, "active_commit_sha")
        _sha(self.candidate_commit_sha, "candidate_commit_sha")
        _sha256(self.active_manifest_sha256, "active_manifest_sha256")
        _sha256(self.candidate_manifest_sha256, "candidate_manifest_sha256")
        _sha256(
            self.release_candidate_intake_sha256,
            "release_candidate_intake_sha256",
        )
        _sha256(self.active_grant_sha256, "active_grant_sha256")
        if not Path(self.active_bundle_path).is_absolute():
            raise ValueError("active_bundle_path must be absolute")
        if self.compatibility_verdict != "not_assessed":
            raise ValueError("v0.45 does not issue a compatibility verdict")
        if any(
            not isinstance(value, bool)
            for value in (
                self.build_authority,
                self.install_authority,
                self.update_authority,
            )
        ):
            raise ValueError("release change evidence authority fields must be boolean")
        if self.build_authority or self.install_authority or self.update_authority:
            raise ValueError("release change evidence grants no mutation authority")
        if self.provider_request_count < 0:
            raise ValueError("provider_request_count must be non-negative")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app_id": self.app_id,
            "repository_url": self.repository_url,
            "active_version": self.active_version,
            "candidate_version": self.candidate_version,
            "active_commit_sha": self.active_commit_sha,
            "candidate_commit_sha": self.candidate_commit_sha,
            "active_manifest_sha256": self.active_manifest_sha256,
            "candidate_manifest_sha256": self.candidate_manifest_sha256,
            "release_candidate_intake_sha256": self.release_candidate_intake_sha256,
            "active_bundle_path": self.active_bundle_path,
            "active_grant_sha256": self.active_grant_sha256,
            "manifest_changes": list(self.manifest_changes),
            "permissions_added": list(self.permissions_added),
            "permissions_removed": list(self.permissions_removed),
            "source_marker_changes": [
                item.to_dict() for item in self.source_marker_changes
            ],
            "provider_request_count": self.provider_request_count,
            "compatibility_verdict": self.compatibility_verdict,
            "build_authority": self.build_authority,
            "install_authority": self.install_authority,
            "update_authority": self.update_authority,
        }

    def sha256(self) -> str:
        return _digest(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["release_change_evidence_sha256"] = self.sha256()
        return result


def _manifest_changes(
    active: AppManifest,
    candidate: AppManifest,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    changes: list[str] = []
    if active.version != candidate.version:
        changes.append("version_changed")
    if active.name != candidate.name:
        changes.append("name_changed")
    if active.description != candidate.description:
        changes.append("description_changed")
    if active.entrypoint.runtime != candidate.entrypoint.runtime:
        changes.append("runtime_changed")
    if active.entrypoint.target != candidate.entrypoint.target:
        changes.append("entrypoint_target_changed")
    if active.source.license_expression != candidate.source.license_expression:
        changes.append("license_expression_changed")
    if active.source.redistribution != candidate.source.redistribution:
        changes.append("redistribution_changed")

    active_permissions = set(active.permissions)
    candidate_permissions = set(candidate.permissions)
    added = tuple(sorted(candidate_permissions - active_permissions))
    removed = tuple(sorted(active_permissions - candidate_permissions))
    if added or removed:
        changes.append("permissions_changed")
    return tuple(changes), added, removed


def _marker_changes(
    active: tuple[SourceMarker, ...],
    candidate: tuple[SourceMarker, ...],
) -> tuple[SourceMarkerChange, ...]:
    active_map = {item.path: item for item in active}
    candidate_map = {item.path: item for item in candidate}
    changes: list[SourceMarkerChange] = []
    for path in sorted(set(active_map) | set(candidate_map)):
        left = active_map.get(path)
        right = candidate_map.get(path)
        if left is None:
            kind = "added"
        elif right is None:
            kind = "removed"
        elif left.provider_object_type != right.provider_object_type:
            kind = "type_changed"
        elif (
            left.provider_blob_id == right.provider_blob_id
            and left.byte_count == right.byte_count
        ):
            kind = "unchanged"
        else:
            kind = "changed"
        changes.append(
            SourceMarkerChange(
                path=path,
                change=kind,
                active=left,
                candidate=right,
            )
        )
    return tuple(changes)


class ReleaseChangeEvidenceService:
    def __init__(self, provider: BuildMarkerProvider | None = None) -> None:
        self.provider = provider or GitHubBuildMarkerProvider()

    def compare(
        self,
        active_bundle_path: Path,
        candidate_intake_value: Any,
        *,
        approved_release_candidate_intake_sha256: str,
        install_root: Path,
        desktop_root: Path,
        applications_root: Path,
    ) -> ReleaseChangeEvidence:
        baseline = _active_baseline(
            active_bundle_path,
            install_root=install_root,
            desktop_root=desktop_root,
            applications_root=applications_root,
        )
        candidate_envelope = _mapping(
            candidate_intake_value,
            "release candidate intake",
        )
        supplied_digest = _sha256(
            candidate_envelope.get("release_candidate_intake_sha256"),
            "release_candidate_intake_sha256",
        )
        if (
            _sha256(
                approved_release_candidate_intake_sha256,
                "approved_release_candidate_intake_sha256",
            )
            != supplied_digest
        ):
            raise ValueError(
                "approved release candidate intake digest does not match candidate envelope"
            )
        intake = unwrap_release_candidate_intake(candidate_envelope)
        selection = _mapping(candidate_envelope.get("selection"), "release candidate selection")
        candidate_commit = _sha(selection.get("commit_sha"), "candidate commit_sha")
        candidate_repository = GitHubRepositoryRef.parse(
            _string(selection.get("repository_url"), "candidate repository_url", maximum=512)
        ).repository_url
        candidate_app_id = _string(selection.get("app_id"), "candidate app_id", maximum=64)

        if candidate_app_id != baseline.app_id:
            raise ValueError("candidate app_id does not match active app")
        if candidate_repository.lower() != baseline.repository_url.lower():
            raise ValueError("candidate repository does not match active app repository")

        manifest_value = intake.get("manifest_candidate")
        if manifest_value is None:
            raise ValueError("candidate intake has no manifest candidate")
        candidate_manifest = AppManifest.from_dict(manifest_value)
        if candidate_manifest.app_id != baseline.app_id:
            raise ValueError("candidate manifest app_id does not match active app")
        if (
            GitHubRepositoryRef.parse(candidate_manifest.source.repository_url)
            .repository_url.lower()
            != baseline.repository_url.lower()
        ):
            raise ValueError("candidate manifest repository does not match active app")

        evidence = _mapping(intake.get("evidence"), "candidate intake evidence")
        if _sha(evidence.get("head_sha"), "candidate intake head_sha") != candidate_commit:
            raise ValueError("candidate intake head SHA does not match selected commit")

        active_markers = self.provider.observe(
            baseline.repository_url,
            baseline.commit_sha,
        )
        candidate_markers = self.provider.observe(
            baseline.repository_url,
            candidate_commit,
        )
        manifest_changes, added, removed = _manifest_changes(
            baseline.manifest,
            candidate_manifest,
        )
        return ReleaseChangeEvidence(
            app_id=baseline.app_id,
            repository_url=baseline.repository_url,
            active_version=baseline.version,
            candidate_version=candidate_manifest.version,
            active_commit_sha=baseline.commit_sha,
            candidate_commit_sha=candidate_commit,
            active_manifest_sha256=baseline.manifest_sha256,
            candidate_manifest_sha256=candidate_manifest.sha256(),
            release_candidate_intake_sha256=supplied_digest,
            active_bundle_path=baseline.active_bundle_path,
            active_grant_sha256=baseline.active_grant_sha256,
            manifest_changes=manifest_changes,
            permissions_added=added,
            permissions_removed=removed,
            source_marker_changes=_marker_changes(active_markers, candidate_markers),
            provider_request_count=self.provider.request_count,
        )
