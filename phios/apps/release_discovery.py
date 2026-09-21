from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from .desktop_update import _contained, _load_bundle, _read_json, _root, _verify_current_bundle
from .intake import (
    AppIntakeAnalyzer,
    AppIntakeResult,
    GitHubJsonClient,
    GitHubPublicRepoProvider,
    GitHubRepositoryRef,
    JsonHttpClient,
)
from .manifest import AppManifest

RELEASE_DISCOVERY_SCHEMA_VERSION = "phios.release_discovery.v0.1"
RELEASE_CANDIDATE_SELECTION_SCHEMA_VERSION = "phios.release_candidate_selection.v0.1"
RELEASE_CANDIDATE_INTAKE_SCHEMA_VERSION = "phios.release_candidate_intake.v0.1"

_MAX_RELEASES = 8
_MAX_TAG_DEREFERENCE_DEPTH = 4
_SHA_RE = re.compile(r"^[0-9a-f]{40,64}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, Any], value)


def _string(value: Any, label: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    if len(value) > maximum:
        raise ValueError(f"{label} exceeds {maximum} characters")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"{label} contains control characters")
    return value


def _optional_string(value: Any, label: str, *, maximum: int = 512) -> str | None:
    if value is None:
        return None
    return _string(value, label, maximum=maximum)


def _bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
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


def _api_url(ref: GitHubRepositoryRef, suffix: str) -> str:
    owner = urllib.parse.quote(ref.owner, safe="")
    name = urllib.parse.quote(ref.name, safe="")
    return f"https://api.github.com/repos/{owner}/{name}{suffix}"


@dataclass(frozen=True)
class ReleaseEvidence:
    release_id: int
    provider_position: int
    tag_name: str
    name: str | None
    published_at: str | None
    prerelease: bool
    draft: bool
    commit_sha: str

    def __post_init__(self) -> None:
        if self.release_id <= 0:
            raise ValueError("release_id must be positive")
        if self.provider_position < 0:
            raise ValueError("provider_position must be non-negative")
        _string(self.tag_name, "tag_name", maximum=256)
        if self.name is not None:
            _string(self.name, "release name", maximum=512)
        if self.published_at is not None:
            _string(self.published_at, "published_at", maximum=128)
        if not isinstance(self.prerelease, bool) or not isinstance(self.draft, bool):
            raise ValueError("release prerelease/draft fields must be boolean")
        _sha(self.commit_sha, "commit_sha")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Any) -> ReleaseEvidence:
        data = _mapping(value, "release evidence")
        expected = {
            "release_id",
            "provider_position",
            "tag_name",
            "name",
            "published_at",
            "prerelease",
            "draft",
            "commit_sha",
        }
        if set(data) != expected:
            raise ValueError("release evidence contains missing or unknown fields")
        return cls(
            release_id=_integer(data["release_id"], "release_id"),
            provider_position=_integer(data["provider_position"], "provider_position"),
            tag_name=_string(data["tag_name"], "tag_name", maximum=256),
            name=_optional_string(data["name"], "release name", maximum=512),
            published_at=_optional_string(data["published_at"], "published_at", maximum=128),
            prerelease=_bool(data["prerelease"], "prerelease"),
            draft=_bool(data["draft"], "draft"),
            commit_sha=_sha(data["commit_sha"], "commit_sha"),
        )


@dataclass(frozen=True)
class ReleaseDiscovery:
    app_id: str
    installed_version: str
    repository_url: str
    active_bundle_path: str
    active_grant_sha256: str
    repository_archived: bool
    releases: tuple[ReleaseEvidence, ...]
    provider_request_count: int
    ordering_semantics: str = "provider_order_only"
    selection_authority: bool = False
    acquisition_authority: bool = False
    update_authority: bool = False
    schema_version: str = RELEASE_DISCOVERY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RELEASE_DISCOVERY_SCHEMA_VERSION:
            raise ValueError("unsupported release discovery schema")
        _string(self.app_id, "app_id", maximum=64)
        _string(self.installed_version, "installed_version", maximum=128)
        GitHubRepositoryRef.parse(self.repository_url)
        if not Path(self.active_bundle_path).is_absolute():
            raise ValueError("active_bundle_path must be absolute")
        _sha256(self.active_grant_sha256, "active_grant_sha256")
        if not isinstance(self.repository_archived, bool):
            raise ValueError("repository_archived must be boolean")
        if len(self.releases) > _MAX_RELEASES:
            raise ValueError("release discovery exceeds bounded release count")
        if tuple(item.provider_position for item in self.releases) != tuple(
            range(len(self.releases))
        ):
            raise ValueError("release provider positions must be contiguous and ordered")
        if self.provider_request_count < 0:
            raise ValueError("provider_request_count must be non-negative")
        if self.ordering_semantics != "provider_order_only":
            raise ValueError("release discovery does not support version ranking")
        if any(
            not isinstance(value, bool)
            for value in (
                self.selection_authority,
                self.acquisition_authority,
                self.update_authority,
            )
        ):
            raise ValueError("release discovery authority fields must be boolean")
        if self.selection_authority or self.acquisition_authority or self.update_authority:
            raise ValueError("release discovery grants no authority")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app_id": self.app_id,
            "installed_version": self.installed_version,
            "repository_url": self.repository_url,
            "active_bundle_path": self.active_bundle_path,
            "active_grant_sha256": self.active_grant_sha256,
            "repository_archived": self.repository_archived,
            "releases": [item.to_dict() for item in self.releases],
            "provider_request_count": self.provider_request_count,
            "ordering_semantics": self.ordering_semantics,
            "selection_authority": self.selection_authority,
            "acquisition_authority": self.acquisition_authority,
            "update_authority": self.update_authority,
        }

    def sha256(self) -> str:
        return _digest(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["release_discovery_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> ReleaseDiscovery:
        data = _mapping(value, "release discovery")
        expected = {
            "schema_version",
            "app_id",
            "installed_version",
            "repository_url",
            "active_bundle_path",
            "active_grant_sha256",
            "repository_archived",
            "releases",
            "provider_request_count",
            "ordering_semantics",
            "selection_authority",
            "acquisition_authority",
            "update_authority",
            "release_discovery_sha256",
        }
        if set(data) != expected:
            raise ValueError("release discovery contains missing or unknown fields")
        releases = data["releases"]
        if not isinstance(releases, list):
            raise ValueError("release discovery releases must be an array")
        discovery = cls(
            schema_version=data["schema_version"],
            app_id=_string(data["app_id"], "app_id", maximum=64),
            installed_version=_string(
                data["installed_version"],
                "installed_version",
                maximum=128,
            ),
            repository_url=_string(data["repository_url"], "repository_url", maximum=512),
            active_bundle_path=_string(
                data["active_bundle_path"],
                "active_bundle_path",
                maximum=4096,
            ),
            active_grant_sha256=_sha256(
                data["active_grant_sha256"],
                "active_grant_sha256",
            ),
            repository_archived=_bool(
                data["repository_archived"],
                "repository_archived",
            ),
            releases=tuple(ReleaseEvidence.from_dict(item) for item in releases),
            provider_request_count=_integer(
                data["provider_request_count"],
                "provider_request_count",
            ),
            ordering_semantics=_string(
                data["ordering_semantics"],
                "ordering_semantics",
                maximum=64,
            ),
            selection_authority=_bool(
                data["selection_authority"],
                "selection_authority",
            ),
            acquisition_authority=_bool(
                data["acquisition_authority"],
                "acquisition_authority",
            ),
            update_authority=_bool(data["update_authority"], "update_authority"),
        )
        if data["release_discovery_sha256"] != discovery.sha256():
            raise ValueError("release discovery digest does not match canonical discovery")
        return discovery


@dataclass(frozen=True)
class ReleaseCandidateSelection:
    release_discovery_sha256: str
    app_id: str
    installed_version: str
    repository_url: str
    release_id: int
    tag_name: str
    commit_sha: str
    prerelease: bool
    candidate_selected: bool = True
    acquisition_authority: bool = False
    build_authority: bool = False
    install_authority: bool = False
    update_authority: bool = False
    schema_version: str = RELEASE_CANDIDATE_SELECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RELEASE_CANDIDATE_SELECTION_SCHEMA_VERSION:
            raise ValueError("unsupported release candidate selection schema")
        _sha256(self.release_discovery_sha256, "release_discovery_sha256")
        _string(self.app_id, "app_id", maximum=64)
        _string(self.installed_version, "installed_version", maximum=128)
        GitHubRepositoryRef.parse(self.repository_url)
        if self.release_id <= 0:
            raise ValueError("release_id must be positive")
        _string(self.tag_name, "tag_name", maximum=256)
        _sha(self.commit_sha, "commit_sha")
        if not isinstance(self.prerelease, bool) or self.candidate_selected is not True:
            raise ValueError("release candidate selection fields are invalid")
        if any(
            not isinstance(value, bool)
            for value in (
                self.acquisition_authority,
                self.build_authority,
                self.install_authority,
                self.update_authority,
            )
        ):
            raise ValueError("release selection authority fields must be boolean")
        if (
            self.acquisition_authority
            or self.build_authority
            or self.install_authority
            or self.update_authority
        ):
            raise ValueError("release selection grants no mutation authority")

    def body_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["release_candidate_selection_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> ReleaseCandidateSelection:
        data = _mapping(value, "release candidate selection")
        expected = {
            "schema_version",
            "release_discovery_sha256",
            "app_id",
            "installed_version",
            "repository_url",
            "release_id",
            "tag_name",
            "commit_sha",
            "prerelease",
            "candidate_selected",
            "acquisition_authority",
            "build_authority",
            "install_authority",
            "update_authority",
            "release_candidate_selection_sha256",
        }
        if set(data) != expected:
            raise ValueError(
                "release candidate selection contains missing or unknown fields"
            )
        selection = cls(
            schema_version=data["schema_version"],
            release_discovery_sha256=_sha256(
                data["release_discovery_sha256"],
                "release_discovery_sha256",
            ),
            app_id=_string(data["app_id"], "app_id", maximum=64),
            installed_version=_string(
                data["installed_version"],
                "installed_version",
                maximum=128,
            ),
            repository_url=_string(data["repository_url"], "repository_url", maximum=512),
            release_id=_integer(data["release_id"], "release_id"),
            tag_name=_string(data["tag_name"], "tag_name", maximum=256),
            commit_sha=_sha(data["commit_sha"], "commit_sha"),
            prerelease=_bool(data["prerelease"], "prerelease"),
            candidate_selected=_bool(data["candidate_selected"], "candidate_selected"),
            acquisition_authority=_bool(
                data["acquisition_authority"],
                "acquisition_authority",
            ),
            build_authority=_bool(data["build_authority"], "build_authority"),
            install_authority=_bool(data["install_authority"], "install_authority"),
            update_authority=_bool(data["update_authority"], "update_authority"),
        )
        if data["release_candidate_selection_sha256"] != selection.sha256():
            raise ValueError(
                "release candidate selection digest does not match canonical selection"
            )
        return selection


class ReleaseProvider(Protocol):
    request_count: int

    def discover(self, repository_url: str) -> tuple[bool, tuple[ReleaseEvidence, ...]]: ...


class GitHubReleaseProvider:
    """Read a bounded public GitHub Releases view and resolve tags to exact commits."""

    def __init__(self, client: JsonHttpClient | None = None) -> None:
        self.client = client or GitHubJsonClient(max_requests=32)

    @property
    def request_count(self) -> int:
        return self.client.request_count

    def discover(self, repository_url: str) -> tuple[bool, tuple[ReleaseEvidence, ...]]:
        ref = GitHubRepositoryRef.parse(repository_url)
        metadata = _mapping(
            self.client.get_json(_api_url(ref, "")),
            "GitHub repository metadata",
        )
        if metadata.get("private") is True:
            raise ValueError("release discovery accepts public repositories only")
        if metadata.get("disabled") is True:
            raise ValueError("release discovery is unavailable for a disabled repository")
        archived = metadata.get("archived") is True

        payload = self.client.get_json(
            _api_url(ref, f"/releases?per_page={_MAX_RELEASES}")
        )
        if not isinstance(payload, list):
            raise ValueError("GitHub releases response must be an array")
        if len(payload) > _MAX_RELEASES:
            raise ValueError("GitHub releases response exceeded bounded release count")

        releases: list[ReleaseEvidence] = []
        for position, raw in enumerate(payload):
            data = _mapping(raw, "GitHub release")
            release_id = _integer(data.get("id"), "GitHub release id")
            if release_id <= 0:
                raise ValueError("GitHub release id must be positive")
            tag = _string(data.get("tag_name"), "GitHub release tag", maximum=256)
            draft = _bool(data.get("draft"), "GitHub release draft")
            prerelease = _bool(data.get("prerelease"), "GitHub release prerelease")
            commit_sha = self._resolve_tag(ref, tag)
            releases.append(
                ReleaseEvidence(
                    release_id=release_id,
                    provider_position=position,
                    tag_name=tag,
                    name=_optional_string(
                        data.get("name"),
                        "GitHub release name",
                        maximum=512,
                    ),
                    published_at=_optional_string(
                        data.get("published_at"),
                        "GitHub release published_at",
                        maximum=128,
                    ),
                    prerelease=prerelease,
                    draft=draft,
                    commit_sha=commit_sha,
                )
            )
        return archived, tuple(releases)

    def _resolve_tag(self, ref: GitHubRepositoryRef, tag_name: str) -> str:
        encoded_tag = urllib.parse.quote(tag_name, safe="")
        ref_payload = _mapping(
            self.client.get_json(_api_url(ref, f"/git/ref/tags/{encoded_tag}")),
            "GitHub tag ref",
        )
        obj = _mapping(ref_payload.get("object"), "GitHub tag ref object")
        object_type = _string(obj.get("type"), "GitHub tag object type", maximum=32)
        object_sha = _sha(obj.get("sha"), "GitHub tag object SHA")

        for _depth in range(_MAX_TAG_DEREFERENCE_DEPTH + 1):
            if object_type == "commit":
                return object_sha
            if object_type != "tag":
                raise ValueError("GitHub release tag does not resolve to a commit or tag")
            tag_payload = _mapping(
                self.client.get_json(_api_url(ref, f"/git/tags/{object_sha}")),
                "GitHub annotated tag",
            )
            obj = _mapping(tag_payload.get("object"), "GitHub annotated tag object")
            object_type = _string(
                obj.get("type"),
                "GitHub annotated tag object type",
                maximum=32,
            )
            object_sha = _sha(obj.get("sha"), "GitHub annotated tag object SHA")
        raise ValueError("GitHub annotated tag exceeded bounded dereference depth")


@dataclass(frozen=True)
class _ActiveAppSource:
    app_id: str
    version: str
    repository_url: str
    bundle_path: str
    grant_sha256: str


def _active_app_source(
    active_bundle_path: Path,
    *,
    install_root: Path,
    desktop_root: Path,
    applications_root: Path,
) -> _ActiveAppSource:
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
    repository_url = GitHubRepositoryRef.parse(
        manifest.source.repository_url
    ).repository_url
    return _ActiveAppSource(
        app_id=manifest.app_id,
        version=manifest.version,
        repository_url=repository_url,
        bundle_path=str(bundle.path),
        grant_sha256=bundle.grant.sha256(),
    )


class ReleaseDiscoveryService:
    def __init__(self, provider: ReleaseProvider | None = None) -> None:
        self.provider = provider or GitHubReleaseProvider()

    def discover(
        self,
        active_bundle_path: Path,
        *,
        install_root: Path,
        desktop_root: Path,
        applications_root: Path,
    ) -> ReleaseDiscovery:
        source = _active_app_source(
            active_bundle_path,
            install_root=install_root,
            desktop_root=desktop_root,
            applications_root=applications_root,
        )
        archived, releases = self.provider.discover(source.repository_url)
        return ReleaseDiscovery(
            app_id=source.app_id,
            installed_version=source.version,
            repository_url=source.repository_url,
            active_bundle_path=source.bundle_path,
            active_grant_sha256=source.grant_sha256,
            repository_archived=archived,
            releases=releases,
            provider_request_count=self.provider.request_count,
        )


def select_release_candidate(
    discovery_value: Any,
    *,
    tag_name: str,
    approved_release_discovery_sha256: str,
    allow_prerelease: bool = False,
) -> ReleaseCandidateSelection:
    discovery = ReleaseDiscovery.from_dict(discovery_value)
    if _sha256(
        approved_release_discovery_sha256,
        "approved_release_discovery_sha256",
    ) != discovery.sha256():
        raise ValueError("approved release discovery digest does not match discovery")
    selected = [item for item in discovery.releases if item.tag_name == tag_name]
    if len(selected) != 1:
        raise ValueError("selected release tag must identify exactly one discovered release")
    release = selected[0]
    if release.draft:
        raise ValueError("draft GitHub releases cannot be selected")
    if release.prerelease and not allow_prerelease:
        raise ValueError("prerelease selection requires explicit allow_prerelease")
    return ReleaseCandidateSelection(
        release_discovery_sha256=discovery.sha256(),
        app_id=discovery.app_id,
        installed_version=discovery.installed_version,
        repository_url=discovery.repository_url,
        release_id=release.release_id,
        tag_name=release.tag_name,
        commit_sha=release.commit_sha,
        prerelease=release.prerelease,
    )


@dataclass(frozen=True)
class ReleaseCandidateIntake:
    selection: ReleaseCandidateSelection
    intake: AppIntakeResult
    schema_version: str = RELEASE_CANDIDATE_INTAKE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RELEASE_CANDIDATE_INTAKE_SCHEMA_VERSION:
            raise ValueError("unsupported release candidate intake schema")
        evidence = self.intake.evidence
        if (
            GitHubRepositoryRef.parse(evidence.repository_url).repository_url.lower()
            != self.selection.repository_url.lower()
        ):
            raise ValueError("release candidate intake repository mismatch")
        if evidence.head_sha.lower() != self.selection.commit_sha:
            raise ValueError("release candidate intake commit mismatch")
        if (
            self.intake.manifest_candidate is not None
            and self.intake.manifest_candidate.app_id != self.selection.app_id
        ):
            raise ValueError("release candidate manifest app_id changed")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "selection": self.selection.to_dict(),
            "intake": self.intake.to_dict(),
        }

    def sha256(self) -> str:
        return _digest(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["release_candidate_intake_sha256"] = self.sha256()
        return result


def inspect_selected_release(
    selection_value: Any,
    *,
    approved_release_candidate_selection_sha256: str,
    provider: GitHubPublicRepoProvider | None = None,
    analyzer: AppIntakeAnalyzer | None = None,
) -> ReleaseCandidateIntake:
    selection = ReleaseCandidateSelection.from_dict(selection_value)
    if _sha256(
        approved_release_candidate_selection_sha256,
        "approved_release_candidate_selection_sha256",
    ) != selection.sha256():
        raise ValueError("approved release selection digest does not match selection")
    intake_provider = provider or GitHubPublicRepoProvider()
    intake_analyzer = analyzer or AppIntakeAnalyzer()
    snapshot = intake_provider.inspect_at_commit(
        selection.repository_url,
        selection.commit_sha,
    )
    intake = intake_analyzer.analyze(snapshot)
    return ReleaseCandidateIntake(selection=selection, intake=intake)


def unwrap_release_candidate_intake(value: Any) -> dict[str, Any]:
    """Validate a v0.44 envelope and return its v0.26-compatible intake payload."""

    data = _mapping(value, "release candidate intake")
    expected = {
        "schema_version",
        "selection",
        "intake",
        "release_candidate_intake_sha256",
    }
    if set(data) != expected:
        raise ValueError("release candidate intake contains missing or unknown fields")
    if data["schema_version"] != RELEASE_CANDIDATE_INTAKE_SCHEMA_VERSION:
        raise ValueError("unsupported release candidate intake schema")
    selection = ReleaseCandidateSelection.from_dict(data["selection"])
    intake = _mapping(data["intake"], "release candidate nested intake")
    body = {
        "schema_version": data["schema_version"],
        "selection": data["selection"],
        "intake": intake,
    }
    if _sha256(
        data["release_candidate_intake_sha256"],
        "release_candidate_intake_sha256",
    ) != _digest(body):
        raise ValueError("release candidate intake digest does not match canonical envelope")

    evidence = _mapping(intake.get("evidence"), "release candidate intake evidence")
    proposal = _mapping(intake.get("proposal"), "release candidate intake proposal")
    repository_url = GitHubRepositoryRef.parse(
        _string(evidence.get("repository_url"), "intake repository_url", maximum=512)
    ).repository_url
    if repository_url.lower() != selection.repository_url.lower():
        raise ValueError("release candidate envelope repository mismatch")
    if _sha(evidence.get("head_sha"), "intake head_sha") != selection.commit_sha:
        raise ValueError("release candidate envelope commit mismatch")
    if proposal.get("app_id") is not None and proposal.get("app_id") != selection.app_id:
        raise ValueError("release candidate envelope app_id mismatch")
    manifest = intake.get("manifest_candidate")
    if manifest is not None:
        candidate = AppManifest.from_dict(manifest)
        if candidate.app_id != selection.app_id:
            raise ValueError("release candidate envelope manifest app_id mismatch")
    return intake
