from __future__ import annotations

import base64
import hashlib
import json
import re
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol, cast
from urllib.parse import urlsplit

from .manifest import APP_MANIFEST_SCHEMA_VERSION, AppManifest

APP_INTAKE_EVIDENCE_SCHEMA_VERSION = "phios.app_intake_evidence.v0.1"
APP_INTAKE_PROPOSAL_SCHEMA_VERSION = "phios.app_intake_proposal.v0.1"

_MAX_ROOT_ENTRIES = 512
_MAX_DISCOVERY_FILES = 8
_MAX_DISCOVERY_FILE_BYTES = 131_072
_MAX_JSON_RESPONSE_BYTES = 524_288
_MAX_PROVIDER_REQUESTS = 12

_DISCOVERY_FILES = (
    "phios-app.json",
    "package.json",
    "pyproject.toml",
    "index.html",
    "Cargo.toml",
    "go.mod",
    "netlify.toml",
    "vite.config.js",
    "vite.config.ts",
)

_SLUG_RE = re.compile(r"[^a-z0-9._-]+")


@dataclass(frozen=True)
class GitHubRepositoryRef:
    owner: str
    name: str

    @property
    def repository_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}"

    @classmethod
    def parse(cls, value: str) -> GitHubRepositoryRef:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.hostname != "github.com":
            raise ValueError("GitHub intake requires an https://github.com/OWNER/REPO URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("GitHub repository URL must not contain credentials, query, or fragment")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 2:
            raise ValueError("GitHub repository URL must identify exactly one OWNER/REPO")
        owner, name = parts
        if name.endswith(".git"):
            name = name[:-4]
        if not owner or not name:
            raise ValueError("GitHub repository owner and name must not be empty")
        if len(owner) > 100 or len(name) > 100:
            raise ValueError("GitHub repository owner/name exceeds the bounded intake limit")
        return cls(owner=owner, name=name)


class JsonHttpClient(Protocol):
    request_count: int

    def get_json(self, url: str) -> Any: ...


class GitHubJsonClient:
    """Small HTTPS-only GitHub API reader with bounded responses and requests."""

    def __init__(self, *, max_requests: int = _MAX_PROVIDER_REQUESTS) -> None:
        self.max_requests = max_requests
        self.request_count = 0

    def get_json(self, url: str) -> Any:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != "api.github.com":
            raise ValueError("GitHub intake network access is restricted to api.github.com")
        if parsed.username or parsed.password:
            raise ValueError("GitHub API URL must not contain credentials")
        if self.request_count >= self.max_requests:
            raise ValueError("GitHub intake request budget exhausted")
        self.request_count += 1

        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "PhiOS-App-Intake/0.26",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = response.read(_MAX_JSON_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise ValueError(f"GitHub API returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ValueError(f"GitHub API request failed: {exc.reason}") from exc

        if len(payload) > _MAX_JSON_RESPONSE_BYTES:
            raise ValueError("GitHub API response exceeded the bounded intake size")
        try:
            return json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("GitHub API returned invalid bounded JSON") from exc


@dataclass(frozen=True)
class IntakeFile:
    path: str
    sha256: str
    byte_count: int
    content: bytes = field(repr=False, compare=False)


@dataclass(frozen=True)
class RepositorySnapshot:
    repository_url: str
    owner: str
    name: str
    description: str
    default_branch: str
    head_sha: str
    archived: bool
    disabled: bool
    license_spdx: str | None
    root_paths: tuple[str, ...]
    files: tuple[IntakeFile, ...]
    provider_request_count: int


@dataclass(frozen=True)
class AppIntakeEvidence:
    repository_url: str
    owner: str
    name: str
    description: str
    default_branch: str
    head_sha: str
    archived: bool
    disabled: bool
    license_spdx: str | None
    root_paths: tuple[str, ...]
    inspected_files: tuple[dict[str, Any], ...]
    provider_request_count: int
    schema_version: str = APP_INTAKE_EVIDENCE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "repository_url": self.repository_url,
            "owner": self.owner,
            "name": self.name,
            "description": self.description,
            "default_branch": self.default_branch,
            "head_sha": self.head_sha,
            "archived": self.archived,
            "disabled": self.disabled,
            "license_spdx": self.license_spdx,
            "root_paths": list(self.root_paths),
            "inspected_files": [dict(item) for item in self.inspected_files],
            "provider_request_count": self.provider_request_count,
        }


@dataclass(frozen=True)
class AppIntakeProposal:
    repository_url: str
    status: str
    app_id: str | None
    runtime: str | None
    target: str | None
    name: str | None
    version: str | None
    description: str | None
    license_expression: str
    redistribution: str
    permissions: tuple[str, ...]
    permissions_source: str
    basis: tuple[str, ...]
    schema_version: str = APP_INTAKE_PROPOSAL_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "repository_url": self.repository_url,
            "status": self.status,
            "app_id": self.app_id,
            "runtime": self.runtime,
            "target": self.target,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "license_expression": self.license_expression,
            "redistribution": self.redistribution,
            "permissions": list(self.permissions),
            "permissions_source": self.permissions_source,
            "basis": list(self.basis),
        }


@dataclass(frozen=True)
class AppIntakeResult:
    evidence: AppIntakeEvidence
    proposal: AppIntakeProposal
    manifest_candidate: AppManifest | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence": self.evidence.to_dict(),
            "proposal": self.proposal.to_dict(),
            "manifest_candidate": (
                self.manifest_candidate.to_dict() if self.manifest_candidate is not None else None
            ),
        }


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, Any], value)


def _bounded_string(value: Any, fallback: str, maximum: int) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()[:maximum]
    return fallback[:maximum]


def _canonical_api_url(ref: GitHubRepositoryRef, suffix: str = "") -> str:
    owner = urllib.parse.quote(ref.owner, safe="")
    name = urllib.parse.quote(ref.name, safe="")
    return f"https://api.github.com/repos/{owner}/{name}{suffix}"


def _decode_contents_file(payload: Any, path: str) -> bytes:
    data = _require_dict(payload, f"GitHub contents response for {path}")
    if data.get("type") != "file":
        raise ValueError(f"GitHub contents response for {path} was not a file")
    if data.get("encoding") != "base64" or not isinstance(data.get("content"), str):
        raise ValueError(f"GitHub contents response for {path} did not contain base64 content")
    try:
        raw = base64.b64decode(data["content"], validate=False)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"GitHub contents response for {path} contained invalid base64") from exc
    if len(raw) > _MAX_DISCOVERY_FILE_BYTES:
        raise ValueError(f"Discovery file exceeds {_MAX_DISCOVERY_FILE_BYTES} bytes: {path}")
    return raw


class GitHubPublicRepoProvider:
    """Read a bounded public GitHub repository snapshot. No clone or checkout occurs."""

    def __init__(self, client: JsonHttpClient | None = None) -> None:
        self.client = client or GitHubJsonClient()

    def inspect(self, repository_url: str) -> RepositorySnapshot:
        ref = GitHubRepositoryRef.parse(repository_url)
        metadata = _require_dict(
            self.client.get_json(_canonical_api_url(ref)),
            "GitHub repository metadata",
        )
        if metadata.get("private") is True:
            raise ValueError("PhiOS v0.26 GitHub intake accepts public repositories only")

        default_branch = _bounded_string(metadata.get("default_branch"), "main", 128)
        branch_suffix = f"/branches/{urllib.parse.quote(default_branch, safe='')}"
        branch = _require_dict(
            self.client.get_json(_canonical_api_url(ref, branch_suffix)),
            "GitHub branch metadata",
        )
        commit = _require_dict(branch.get("commit"), "GitHub branch commit")
        head_sha = _bounded_string(commit.get("sha"), "", 64)
        if not re.fullmatch(r"[0-9a-fA-F]{40,64}", head_sha):
            raise ValueError("GitHub branch metadata did not contain a valid head SHA")

        root_suffix = f"/contents?ref={urllib.parse.quote(default_branch, safe='')}"
        root = self.client.get_json(_canonical_api_url(ref, root_suffix))
        if not isinstance(root, list):
            raise ValueError("GitHub repository root must be a directory listing")
        if len(root) > _MAX_ROOT_ENTRIES:
            raise ValueError(f"Repository root exceeds {_MAX_ROOT_ENTRIES} entries")

        root_paths: list[str] = []
        file_names: set[str] = set()
        for entry_value in root:
            entry = _require_dict(entry_value, "GitHub root entry")
            path = entry.get("path")
            entry_type = entry.get("type")
            if isinstance(path, str) and path and len(path) <= 256:
                root_paths.append(path)
                if entry_type == "file":
                    file_names.add(path)

        selected = [name for name in _DISCOVERY_FILES if name in file_names][:_MAX_DISCOVERY_FILES]
        files: list[IntakeFile] = []
        for path in selected:
            suffix = (
                f"/contents/{urllib.parse.quote(path, safe='/')}"
                f"?ref={urllib.parse.quote(default_branch, safe='')}"
            )
            content = _decode_contents_file(self.client.get_json(_canonical_api_url(ref, suffix)), path)
            files.append(
                IntakeFile(
                    path=path,
                    sha256=hashlib.sha256(content).hexdigest(),
                    byte_count=len(content),
                    content=content,
                )
            )

        license_obj = metadata.get("license")
        license_spdx: str | None = None
        if isinstance(license_obj, dict):
            candidate = license_obj.get("spdx_id")
            if isinstance(candidate, str) and candidate and candidate != "NOASSERTION":
                license_spdx = candidate[:128]

        return RepositorySnapshot(
            repository_url=ref.repository_url,
            owner=ref.owner,
            name=ref.name,
            description=_bounded_string(metadata.get("description"), "", 512),
            default_branch=default_branch,
            head_sha=head_sha.lower(),
            archived=metadata.get("archived") is True,
            disabled=metadata.get("disabled") is True,
            license_spdx=license_spdx,
            root_paths=tuple(sorted(root_paths)),
            files=tuple(files),
            provider_request_count=self.client.request_count,
        )


def _file_map(snapshot: RepositorySnapshot) -> dict[str, IntakeFile]:
    return {item.path: item for item in snapshot.files}


def _safe_app_id(snapshot: RepositorySnapshot) -> str:
    raw = f"github.{snapshot.owner}.{snapshot.name}".lower()
    slug = _SLUG_RE.sub("-", raw).strip(".-_") or "github.app"
    if len(slug) <= 64:
        return slug
    digest = hashlib.sha256(slug.encode("utf-8")).hexdigest()[:10]
    return f"{slug[:53].rstrip('.-_')}-{digest}"


def _json_file(item: IntakeFile) -> dict[str, Any]:
    try:
        parsed = json.loads(item.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{item.path} is not valid UTF-8 JSON") from exc
    return _require_dict(parsed, item.path)


def _toml_file(item: IntakeFile) -> dict[str, Any]:
    try:
        parsed = tomllib.loads(item.content.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"{item.path} is not valid UTF-8 TOML") from exc
    return _require_dict(parsed, item.path)


def _manifest_from_inferred(
    *,
    snapshot: RepositorySnapshot,
    runtime: str,
    target: str,
    name: str,
    version: str,
    description: str,
) -> AppManifest:
    return AppManifest.from_dict(
        {
            "schema_version": APP_MANIFEST_SCHEMA_VERSION,
            "app_id": _safe_app_id(snapshot),
            "name": name,
            "version": version,
            "description": description,
            "source": {
                "repository_url": snapshot.repository_url,
                "license_expression": snapshot.license_spdx or "NOASSERTION",
                "redistribution": "unknown",
            },
            "entrypoint": {"runtime": runtime, "target": target},
            "permissions": [],
        }
    )


class AppIntakeAnalyzer:
    """Turn a bounded repository snapshot into evidence plus a non-authoritative proposal."""

    def analyze(self, snapshot: RepositorySnapshot) -> AppIntakeResult:
        files = _file_map(snapshot)
        evidence = AppIntakeEvidence(
            repository_url=snapshot.repository_url,
            owner=snapshot.owner,
            name=snapshot.name,
            description=snapshot.description,
            default_branch=snapshot.default_branch,
            head_sha=snapshot.head_sha,
            archived=snapshot.archived,
            disabled=snapshot.disabled,
            license_spdx=snapshot.license_spdx,
            root_paths=snapshot.root_paths,
            inspected_files=tuple(
                {
                    "path": item.path,
                    "sha256": item.sha256,
                    "byte_count": item.byte_count,
                }
                for item in snapshot.files
            ),
            provider_request_count=snapshot.provider_request_count,
        )

        if snapshot.disabled:
            return self._no_manifest(
                evidence,
                snapshot,
                status="repository_disabled",
                basis=("GitHub repository metadata reports disabled=true",),
            )

        declared = files.get("phios-app.json")
        if declared is not None:
            try:
                manifest = AppManifest.from_dict(_json_file(declared))
            except ValueError as exc:
                return self._no_manifest(
                    evidence,
                    snapshot,
                    status="invalid_declared_manifest",
                    basis=(f"phios-app.json rejected: {exc}",),
                )
            declared_ref = GitHubRepositoryRef.parse(manifest.source.repository_url)
            if declared_ref.repository_url.lower() != snapshot.repository_url.lower():
                return self._no_manifest(
                    evidence,
                    snapshot,
                    status="declared_source_mismatch",
                    basis=("phios-app.json source repository does not match inspected repository",),
                )
            proposal = AppIntakeProposal(
                repository_url=snapshot.repository_url,
                status="declared_manifest",
                app_id=manifest.app_id,
                runtime=manifest.entrypoint.runtime,
                target=manifest.entrypoint.target,
                name=manifest.name,
                version=manifest.version,
                description=manifest.description,
                license_expression=manifest.source.license_expression,
                redistribution=manifest.source.redistribution,
                permissions=manifest.permissions,
                permissions_source="phios-app.json",
                basis=("valid phios-app.json observed at repository root",),
            )
            return AppIntakeResult(evidence=evidence, proposal=proposal, manifest_candidate=manifest)

        inferred_manifest, basis = self._infer_manifest(snapshot, files)
        if inferred_manifest is None:
            return self._no_manifest(
                evidence,
                snapshot,
                status="insufficient_metadata",
                basis=basis,
            )

        proposal = AppIntakeProposal(
            repository_url=snapshot.repository_url,
            status="inferred_candidate",
            app_id=inferred_manifest.app_id,
            runtime=inferred_manifest.entrypoint.runtime,
            target=inferred_manifest.entrypoint.target,
            name=inferred_manifest.name,
            version=inferred_manifest.version,
            description=inferred_manifest.description,
            license_expression=inferred_manifest.source.license_expression,
            redistribution=inferred_manifest.source.redistribution,
            permissions=(),
            permissions_source="not_declared",
            basis=basis
            + (
                "permissions were not inferred; operator declaration is required before execution",
                "redistribution remains unknown despite public repository visibility",
            ),
        )
        return AppIntakeResult(
            evidence=evidence,
            proposal=proposal,
            manifest_candidate=inferred_manifest,
        )

    def _infer_manifest(
        self,
        snapshot: RepositorySnapshot,
        files: dict[str, IntakeFile],
    ) -> tuple[AppManifest | None, tuple[str, ...]]:
        package = files.get("package.json")
        if package is not None:
            try:
                data = _json_file(package)
            except ValueError as exc:
                return None, (f"package.json rejected: {exc}",)
            manifest = _manifest_from_inferred(
                snapshot=snapshot,
                runtime="node",
                target="package.json",
                name=_bounded_string(data.get("name"), snapshot.name, 96),
                version=_bounded_string(data.get("version"), "0.0.0", 64),
                description=_bounded_string(data.get("description"), snapshot.description, 512),
            )
            return manifest, ("package.json observed and parsed", "Node runtime candidate proposed")

        pyproject = files.get("pyproject.toml")
        if pyproject is not None:
            try:
                data = _toml_file(pyproject)
            except ValueError as exc:
                return None, (f"pyproject.toml rejected: {exc}",)
            project = data.get("project")
            project_data = project if isinstance(project, dict) else {}
            manifest = _manifest_from_inferred(
                snapshot=snapshot,
                runtime="python",
                target="pyproject.toml",
                name=_bounded_string(project_data.get("name"), snapshot.name, 96),
                version=_bounded_string(project_data.get("version"), "0.0.0", 64),
                description=_bounded_string(
                    project_data.get("description"),
                    snapshot.description,
                    512,
                ),
            )
            return manifest, ("pyproject.toml observed and parsed", "Python runtime candidate proposed")

        if "index.html" in files:
            manifest = _manifest_from_inferred(
                snapshot=snapshot,
                runtime="static_web",
                target="index.html",
                name=snapshot.name,
                version="0.0.0",
                description=snapshot.description,
            )
            return manifest, ("index.html observed", "static web runtime candidate proposed")

        if "Cargo.toml" in files:
            manifest = _manifest_from_inferred(
                snapshot=snapshot,
                runtime="native",
                target="Cargo.toml",
                name=snapshot.name,
                version="0.0.0",
                description=snapshot.description,
            )
            return manifest, ("Cargo.toml observed", "native Rust build candidate proposed")

        if "go.mod" in files:
            manifest = _manifest_from_inferred(
                snapshot=snapshot,
                runtime="native",
                target="go.mod",
                name=snapshot.name,
                version="0.0.0",
                description=snapshot.description,
            )
            return manifest, ("go.mod observed", "native Go build candidate proposed")

        return None, ("no supported root runtime marker was observed",)

    @staticmethod
    def _no_manifest(
        evidence: AppIntakeEvidence,
        snapshot: RepositorySnapshot,
        *,
        status: str,
        basis: tuple[str, ...],
    ) -> AppIntakeResult:
        proposal = AppIntakeProposal(
            repository_url=snapshot.repository_url,
            status=status,
            app_id=None,
            runtime=None,
            target=None,
            name=None,
            version=None,
            description=None,
            license_expression=snapshot.license_spdx or "NOASSERTION",
            redistribution="unknown",
            permissions=(),
            permissions_source="not_declared",
            basis=basis,
        )
        return AppIntakeResult(evidence=evidence, proposal=proposal, manifest_candidate=None)


def inspect_public_github_app(
    repository_url: str,
    *,
    provider: GitHubPublicRepoProvider | None = None,
    analyzer: AppIntakeAnalyzer | None = None,
) -> AppIntakeResult:
    intake_provider = provider or GitHubPublicRepoProvider()
    intake_analyzer = analyzer or AppIntakeAnalyzer()
    return intake_analyzer.analyze(intake_provider.inspect(repository_url))
