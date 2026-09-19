from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast

from .build_plan import AcquisitionBinding, BuildPlan, snapshot_source_tree

DEPENDENCY_PLAN_SCHEMA_VERSION = "phios.dependency_plan.v0.1"
DEPENDENCY_PLAN_REVIEW_SCHEMA_VERSION = "phios.dependency_plan_review.v0.1"
DEPENDENCY_RECEIPT_SCHEMA_VERSION = "phios.dependency_receipt.v0.1"

_MAX_LOCKFILE_BYTES = 8 * 1024 * 1024
_MAX_DEPENDENCY_ARTIFACTS = 4096
_MAX_LOCK_KEYS_PER_ARTIFACT = 256
_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
_MAX_TOTAL_STAGE_BYTES = 1024 * 1024 * 1024
_MAX_REDIRECTS = 5
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_HOST_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
_SRI_LENGTHS = {"sha256": 32, "sha384": 48, "sha512": 64}
_SRI_STRENGTH = ("sha512", "sha384", "sha256")


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


def _canonical_host(value: str) -> str:
    host = value.rstrip(".").lower()
    if not _SAFE_HOST_RE.fullmatch(host):
        raise ValueError(f"Invalid dependency host: {value}")
    return host


def _validated_dependency_url(value: Any) -> tuple[str, str]:
    text = _string(value, "dependency resolved URL", maximum=2048)
    parsed = urllib.parse.urlsplit(text)
    if parsed.scheme.lower() != "https":
        raise ValueError("Dependency resolved URL must use HTTPS")
    if not parsed.hostname:
        raise ValueError("Dependency resolved URL must contain a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Dependency resolved URL must not contain credentials")
    if parsed.port not in {None, 443}:
        raise ValueError("Dependency resolved URL must use the default HTTPS port")
    if parsed.query or parsed.fragment:
        raise ValueError("Dependency resolved URL must not contain query or fragment data")
    host = _canonical_host(parsed.hostname)
    canonical = urllib.parse.urlunsplit(
        ("https", host, parsed.path or "/", "", "")
    )
    return canonical, host


def _select_sri(value: Any) -> tuple[str, str]:
    text = _string(value, "dependency integrity", maximum=2048)
    candidates: dict[str, str] = {}
    for token in text.split():
        if "-" not in token:
            continue
        algorithm, encoded = token.split("-", 1)
        if algorithm not in _SRI_LENGTHS or "?" in encoded:
            continue
        try:
            digest = base64.b64decode(encoded, validate=True)
        except ValueError:
            continue
        if len(digest) != _SRI_LENGTHS[algorithm]:
            continue
        candidates[algorithm] = base64.b64encode(digest).decode("ascii")

    for algorithm in _SRI_STRENGTH:
        selected_digest = candidates.get(algorithm)
        if selected_digest is not None:
            return algorithm, selected_digest
    raise ValueError("Dependency integrity lacks a supported valid SHA-256/384/512 SRI digest")


def _verify_sri(content: bytes, algorithm: str, expected_b64: str) -> None:
    digest = hashlib.new(algorithm, content).digest()
    observed = base64.b64encode(digest).decode("ascii")
    if not hmac.compare_digest(observed, expected_b64):
        raise ValueError("Downloaded dependency bytes do not match lockfile SRI integrity")


@dataclass(frozen=True)
class DependencyArtifactPlan:
    resolved_url: str
    host: str
    integrity_algorithm: str
    integrity_digest_base64: str
    lock_keys: tuple[str, ...]
    version: str | None

    def __post_init__(self) -> None:
        canonical, host = _validated_dependency_url(self.resolved_url)
        if canonical != self.resolved_url or host != self.host:
            raise ValueError("Dependency artifact URL/host is not canonical")
        if self.integrity_algorithm not in _SRI_LENGTHS:
            raise ValueError("Unsupported dependency integrity algorithm")
        try:
            digest = base64.b64decode(self.integrity_digest_base64, validate=True)
        except ValueError as exc:
            raise ValueError("Dependency integrity digest is invalid base64") from exc
        if len(digest) != _SRI_LENGTHS[self.integrity_algorithm]:
            raise ValueError("Dependency integrity digest has the wrong length")
        if not 1 <= len(self.lock_keys) <= _MAX_LOCK_KEYS_PER_ARTIFACT:
            raise ValueError("Dependency artifact lock key count is out of bounds")
        if tuple(sorted(set(self.lock_keys))) != self.lock_keys:
            raise ValueError("Dependency artifact lock keys must be unique and sorted")
        for key in self.lock_keys:
            _string(key, "dependency lock key", maximum=1024)
        if self.version is not None:
            _string(self.version, "dependency version", maximum=256)

    def body_dict(self) -> dict[str, Any]:
        return {
            "resolved_url": self.resolved_url,
            "host": self.host,
            "integrity_algorithm": self.integrity_algorithm,
            "integrity_digest_base64": self.integrity_digest_base64,
            "lock_keys": list(self.lock_keys),
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, value: Any) -> DependencyArtifactPlan:
        data = _mapping(value, "dependency artifact plan")
        expected = {
            "resolved_url",
            "host",
            "integrity_algorithm",
            "integrity_digest_base64",
            "lock_keys",
            "version",
        }
        if set(data) != expected:
            raise ValueError("dependency artifact plan contains missing or unknown fields")
        keys = data["lock_keys"]
        if not isinstance(keys, list) or not all(isinstance(item, str) for item in keys):
            raise ValueError("dependency artifact lock_keys must be an array of strings")
        version = data["version"]
        if version is not None and not isinstance(version, str):
            raise ValueError("dependency artifact version must be string or null")
        return cls(
            resolved_url=_string(data["resolved_url"], "dependency resolved_url", maximum=2048),
            host=_canonical_host(_string(data["host"], "dependency host", maximum=253)),
            integrity_algorithm=_string(
                data["integrity_algorithm"],
                "dependency integrity_algorithm",
                maximum=16,
            ),
            integrity_digest_base64=_string(
                data["integrity_digest_base64"],
                "dependency integrity_digest_base64",
                maximum=256,
            ),
            lock_keys=tuple(keys),
            version=version,
        )


@dataclass(frozen=True)
class DependencyPlan:
    app_id: str
    repository_url: str
    commit_sha: str
    build_plan_sha256: str
    source_snapshot_sha256: str
    package_manager: str
    lockfile_path: str
    lockfile_sha256: str
    lockfile_version: int
    allowed_hosts: tuple[str, ...]
    artifacts: tuple[DependencyArtifactPlan, ...]
    schema_version: str = DEPENDENCY_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DEPENDENCY_PLAN_SCHEMA_VERSION:
            raise ValueError(f"Unsupported dependency plan schema: {self.schema_version}")
        _sha256(self.build_plan_sha256, "dependency plan build_plan_sha256")
        _sha256(self.source_snapshot_sha256, "dependency plan source_snapshot_sha256")
        _sha256(self.lockfile_sha256, "dependency plan lockfile_sha256")
        if self.package_manager != "npm":
            raise ValueError("v0.31 supports only npm dependency staging")
        if self.lockfile_path not in {"package-lock.json", "npm-shrinkwrap.json"}:
            raise ValueError("v0.31 requires package-lock.json or npm-shrinkwrap.json")
        if self.lockfile_version not in {2, 3}:
            raise ValueError("v0.31 requires npm lockfileVersion 2 or 3")
        if not 1 <= len(self.artifacts) <= _MAX_DEPENDENCY_ARTIFACTS:
            raise ValueError("dependency plan artifact count is out of bounds")
        canonical_hosts = tuple(sorted({_canonical_host(host) for host in self.allowed_hosts}))
        if canonical_hosts != self.allowed_hosts:
            raise ValueError("dependency plan allowed_hosts must be unique and sorted")
        if tuple(sorted({artifact.host for artifact in self.artifacts})) != self.allowed_hosts:
            raise ValueError("dependency plan hosts must exactly match artifact hosts")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app_id": self.app_id,
            "repository_url": self.repository_url,
            "commit_sha": self.commit_sha,
            "build_plan_sha256": self.build_plan_sha256,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "package_manager": self.package_manager,
            "lockfile_path": self.lockfile_path,
            "lockfile_sha256": self.lockfile_sha256,
            "lockfile_version": self.lockfile_version,
            "allowed_hosts": list(self.allowed_hosts),
            "artifacts": [artifact.body_dict() for artifact in self.artifacts],
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
        result["dependency_plan_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> DependencyPlan:
        data = _mapping(value, "dependency plan")
        expected = {
            "schema_version",
            "app_id",
            "repository_url",
            "commit_sha",
            "build_plan_sha256",
            "source_snapshot_sha256",
            "package_manager",
            "lockfile_path",
            "lockfile_sha256",
            "lockfile_version",
            "allowed_hosts",
            "artifacts",
            "dependency_plan_sha256",
        }
        if set(data) != expected:
            raise ValueError("dependency plan contains missing or unknown fields")
        hosts = data["allowed_hosts"]
        artifacts = data["artifacts"]
        if not isinstance(hosts, list) or not all(isinstance(item, str) for item in hosts):
            raise ValueError("dependency plan allowed_hosts must be an array of strings")
        if not isinstance(artifacts, list):
            raise ValueError("dependency plan artifacts must be an array")
        plan = cls(
            schema_version=data["schema_version"],
            app_id=_string(data["app_id"], "dependency plan app_id", maximum=64),
            repository_url=_string(
                data["repository_url"],
                "dependency plan repository_url",
                maximum=512,
            ),
            commit_sha=_string(data["commit_sha"], "dependency plan commit_sha", maximum=64),
            build_plan_sha256=_sha256(
                data["build_plan_sha256"],
                "dependency plan build_plan_sha256",
            ),
            source_snapshot_sha256=_sha256(
                data["source_snapshot_sha256"],
                "dependency plan source_snapshot_sha256",
            ),
            package_manager=_string(
                data["package_manager"],
                "dependency plan package_manager",
                maximum=32,
            ),
            lockfile_path=_string(
                data["lockfile_path"],
                "dependency plan lockfile_path",
                maximum=64,
            ),
            lockfile_sha256=_sha256(
                data["lockfile_sha256"],
                "dependency plan lockfile_sha256",
            ),
            lockfile_version=_integer(
                data["lockfile_version"],
                "dependency plan lockfile_version",
                maximum=10,
            ),
            allowed_hosts=tuple(hosts),
            artifacts=tuple(DependencyArtifactPlan.from_dict(item) for item in artifacts),
        )
        if data["dependency_plan_sha256"] != plan.sha256():
            raise ValueError("dependency plan digest does not match canonical plan")
        return plan


@dataclass(frozen=True)
class DependencyPlanReview:
    dependency_plan_sha256: str
    build_plan_sha256: str
    source_snapshot_sha256: str
    lockfile_path: str
    lockfile_sha256: str
    artifact_count: int
    allowed_hosts: tuple[str, ...]
    schema_version: str = DEPENDENCY_PLAN_REVIEW_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dependency_plan_sha256": self.dependency_plan_sha256,
            "build_plan_sha256": self.build_plan_sha256,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "lockfile_path": self.lockfile_path,
            "lockfile_sha256": self.lockfile_sha256,
            "artifact_count": self.artifact_count,
            "allowed_hosts": list(self.allowed_hosts),
        }


def review_dependency_plan(value: Any) -> DependencyPlanReview:
    plan = DependencyPlan.from_dict(value)
    return DependencyPlanReview(
        dependency_plan_sha256=plan.sha256(),
        build_plan_sha256=plan.build_plan_sha256,
        source_snapshot_sha256=plan.source_snapshot_sha256,
        lockfile_path=plan.lockfile_path,
        lockfile_sha256=plan.lockfile_sha256,
        artifact_count=len(plan.artifacts),
        allowed_hosts=plan.allowed_hosts,
    )


def _load_lockfile(root: Path, plan: BuildPlan) -> tuple[str, bytes]:
    observed = {item.path: item.sha256 for item in plan.observed_files}
    candidates = [
        name
        for name in ("npm-shrinkwrap.json", "package-lock.json")
        if name in observed
    ]
    if len(candidates) != 1:
        raise ValueError("v0.31 requires exactly one observed npm lockfile")
    name = candidates[0]
    path = root / name
    if path.is_symlink() or not path.is_file():
        raise ValueError("npm lockfile is not a regular acquired source file")
    size = path.stat().st_size
    if size > _MAX_LOCKFILE_BYTES:
        raise ValueError("npm lockfile exceeds the v0.31 bounded size")
    content = path.read_bytes()
    if len(content) != size:
        raise ValueError("npm lockfile changed while dependency planning")
    digest = hashlib.sha256(content).hexdigest()
    if digest != observed[name]:
        raise ValueError("npm lockfile digest no longer matches the reviewed build plan")
    return name, content


def _parse_npm_lockfile(content: bytes) -> tuple[int, tuple[DependencyArtifactPlan, ...]]:
    try:
        raw = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("npm lockfile must contain valid bounded UTF-8 JSON") from exc
    lock = _mapping(raw, "npm lockfile")
    version = lock.get("lockfileVersion")
    if version not in {2, 3}:
        raise ValueError("v0.31 supports npm lockfileVersion 2 or 3")
    packages = _mapping(lock.get("packages"), "npm lockfile packages")

    grouped: dict[tuple[str, str, str, str | None], list[str]] = {}
    package_entry_count = 0
    for lock_key, value in packages.items():
        if not isinstance(lock_key, str):
            raise ValueError("npm lockfile package keys must be strings")
        if lock_key == "":
            continue
        entry = _mapping(value, f"npm lockfile package {lock_key}")
        if entry.get("link") is True:
            continue

        resolved = entry.get("resolved")
        integrity = entry.get("integrity")
        if resolved is None and integrity is None:
            raise ValueError(
                f"npm package entry lacks exact resolved/integrity evidence: {lock_key}"
            )
        if resolved is None or integrity is None:
            raise ValueError(
                f"npm package entry has incomplete resolved/integrity evidence: {lock_key}"
            )

        canonical_url, host = _validated_dependency_url(resolved)
        algorithm, digest_b64 = _select_sri(integrity)
        raw_version = entry.get("version")
        package_version = raw_version if isinstance(raw_version, str) and raw_version else None
        group_key = (canonical_url, algorithm, digest_b64, package_version)
        grouped.setdefault(group_key, []).append(lock_key)
        package_entry_count += 1
        if package_entry_count > _MAX_DEPENDENCY_ARTIFACTS * 8:
            raise ValueError("npm lockfile contains too many dependency package entries")

    artifacts: list[DependencyArtifactPlan] = []
    for (url, algorithm, digest_b64, package_version), keys in grouped.items():
        unique_keys = tuple(sorted(set(keys)))
        if len(unique_keys) > _MAX_LOCK_KEYS_PER_ARTIFACT:
            raise ValueError("too many lockfile locations reference one dependency artifact")
        _, host = _validated_dependency_url(url)
        artifacts.append(
            DependencyArtifactPlan(
                resolved_url=url,
                host=host,
                integrity_algorithm=algorithm,
                integrity_digest_base64=digest_b64,
                lock_keys=unique_keys,
                version=package_version,
            )
        )

    if not artifacts:
        raise ValueError("npm lockfile contains no externally staged dependency artifacts")
    if len(artifacts) > _MAX_DEPENDENCY_ARTIFACTS:
        raise ValueError("npm dependency artifact count exceeds the bounded maximum")

    artifacts.sort(
        key=lambda item: (
            item.resolved_url,
            item.integrity_algorithm,
            item.integrity_digest_base64,
            item.version or "",
        )
    )
    return int(version), tuple(artifacts)


def plan_npm_dependencies(
    build_plan_value: Any,
    acquisition_receipt_value: Any,
) -> DependencyPlan:
    plan = BuildPlan.from_dict(build_plan_value)
    binding = AcquisitionBinding.from_dict(acquisition_receipt_value)

    if plan.status != "ready_for_review":
        raise ValueError("v0.31 dependency planning requires a ready_for_review build plan")
    if plan.package_manager != "npm":
        raise ValueError("v0.31 dependency planning currently supports only npm")
    if plan.app_id != binding.app_id:
        raise ValueError("Build plan app_id does not match acquisition receipt")
    if plan.repository_url.lower() != binding.repository_url.lower():
        raise ValueError("Build plan repository does not match acquisition receipt")
    if plan.commit_sha != binding.commit_sha:
        raise ValueError("Build plan commit does not match acquisition receipt")
    if plan.acquisition_tree_sha256 != binding.acquisition_tree_sha256:
        raise ValueError("Build plan acquisition tree does not match acquisition receipt")
    if plan.source_file_count != binding.file_count or plan.source_total_bytes != binding.total_bytes:
        raise ValueError("Build plan source totals do not match acquisition receipt")

    if binding.workspace_path.is_symlink():
        raise ValueError("Acquisition workspace must not be a symlink")
    root = binding.workspace_path.resolve(strict=True)
    snapshot, file_count, total_bytes = snapshot_source_tree(root)
    if snapshot != plan.source_snapshot_sha256:
        raise ValueError("Source snapshot changed after build-plan review")
    if file_count != plan.source_file_count or total_bytes != plan.source_total_bytes:
        raise ValueError("Source totals changed after build-plan review")

    lock_name, lock_content = _load_lockfile(root, plan)
    lock_version, artifacts = _parse_npm_lockfile(lock_content)
    hosts = tuple(sorted({artifact.host for artifact in artifacts}))

    return DependencyPlan(
        app_id=plan.app_id,
        repository_url=plan.repository_url,
        commit_sha=plan.commit_sha,
        build_plan_sha256=plan.sha256(),
        source_snapshot_sha256=plan.source_snapshot_sha256,
        package_manager="npm",
        lockfile_path=lock_name,
        lockfile_sha256=hashlib.sha256(lock_content).hexdigest(),
        lockfile_version=lock_version,
        allowed_hosts=hosts,
        artifacts=artifacts,
    )


@dataclass(frozen=True)
class DependencyStageRequest:
    plan: DependencyPlan
    approved_dependency_plan_sha256: str
    approved_hosts: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.approved_dependency_plan_sha256 != self.plan.sha256():
            raise ValueError("Approved dependency plan SHA-256 does not match canonical plan")
        canonical_hosts = tuple(sorted({_canonical_host(host) for host in self.approved_hosts}))
        if canonical_hosts != self.approved_hosts:
            raise ValueError("Approved dependency hosts must be unique and sorted")
        if self.approved_hosts != self.plan.allowed_hosts:
            raise ValueError("Approved dependency hosts must exactly match the reviewed plan")

    @classmethod
    def from_payload(
        cls,
        value: Any,
        *,
        approved_dependency_plan_sha256: str,
        approved_hosts: tuple[str, ...],
    ) -> DependencyStageRequest:
        return cls(
            plan=DependencyPlan.from_dict(value),
            approved_dependency_plan_sha256=_sha256(
                approved_dependency_plan_sha256,
                "approved dependency plan sha256",
            ),
            approved_hosts=tuple(sorted(approved_hosts)),
        )


class DependencyDownloader(Protocol):
    def download(
        self,
        artifact: DependencyArtifactPlan,
        *,
        approved_hosts: tuple[str, ...],
    ) -> bytes: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


class HttpsDependencyDownloader:
    def __init__(self, *, timeout_seconds: int = 60) -> None:
        if not 1 <= timeout_seconds <= 300:
            raise ValueError("dependency download timeout must be 1-300 seconds")
        self.timeout_seconds = timeout_seconds
        self.opener = urllib.request.build_opener(_NoRedirect())

    def download(
        self,
        artifact: DependencyArtifactPlan,
        *,
        approved_hosts: tuple[str, ...],
    ) -> bytes:
        allowed = set(approved_hosts)
        url = artifact.resolved_url
        for redirect_count in range(_MAX_REDIRECTS + 1):
            canonical, host = _validated_dependency_url(url)
            if host not in allowed:
                raise ValueError(f"Dependency download host is not approved: {host}")
            request = urllib.request.Request(
                canonical,
                headers={
                    "User-Agent": "PhiOS-Dependency-Broker/0.31",
                    "Accept": "application/octet-stream",
                },
                method="GET",
            )
            try:
                response = self.opener.open(request, timeout=self.timeout_seconds)
            except urllib.error.HTTPError as exc:
                if exc.code not in {301, 302, 303, 307, 308}:
                    raise ValueError(f"Dependency download failed with HTTP {exc.code}") from exc
                if redirect_count >= _MAX_REDIRECTS:
                    raise ValueError("Dependency download exceeded redirect bound") from exc
                location = exc.headers.get("Location")
                if not location:
                    raise ValueError("Dependency redirect omitted Location") from exc
                url = urllib.parse.urljoin(canonical, location)
                continue
            except urllib.error.URLError as exc:
                raise ValueError("Dependency download failed") from exc

            with response:
                final_url, final_host = _validated_dependency_url(response.geturl())
                if final_host not in allowed:
                    raise ValueError("Dependency response escaped approved hosts")
                if final_url != canonical:
                    raise ValueError("Dependency downloader observed an unreviewed redirect")
                length_header = response.headers.get("Content-Length")
                if length_header is not None:
                    try:
                        content_length = int(length_header)
                    except ValueError as exc:
                        raise ValueError("Dependency Content-Length is invalid") from exc
                    if content_length < 0 or content_length > _MAX_ARTIFACT_BYTES:
                        raise ValueError("Dependency artifact exceeds bounded size")

                buffer = bytearray()
                while True:
                    chunk = response.read(65_536)
                    if not chunk:
                        break
                    buffer.extend(chunk)
                    if len(buffer) > _MAX_ARTIFACT_BYTES:
                        raise ValueError("Dependency artifact exceeds bounded size")
                return bytes(buffer)
        raise ValueError("Dependency redirect loop exhausted")


@dataclass(frozen=True)
class StagedDependencyArtifact:
    resolved_url: str
    host: str
    integrity_algorithm: str
    integrity_digest_base64: str
    byte_count: int
    sha256: str
    cas_path: str
    lock_keys: tuple[str, ...]
    version: str | None

    def __post_init__(self) -> None:
        canonical, host = _validated_dependency_url(self.resolved_url)
        if canonical != self.resolved_url or host != self.host:
            raise ValueError("Staged dependency URL/host is not canonical")
        if self.integrity_algorithm not in _SRI_LENGTHS:
            raise ValueError("Unsupported staged dependency integrity algorithm")
        try:
            digest = base64.b64decode(self.integrity_digest_base64, validate=True)
        except ValueError as exc:
            raise ValueError("Staged dependency integrity digest is invalid base64") from exc
        if len(digest) != _SRI_LENGTHS[self.integrity_algorithm]:
            raise ValueError("Staged dependency integrity digest has the wrong length")
        _integer(self.byte_count, "staged dependency byte_count", maximum=_MAX_ARTIFACT_BYTES)
        _sha256(self.sha256, "staged dependency sha256")
        cas = Path(_string(self.cas_path, "staged dependency cas_path", maximum=4096))
        if not cas.is_absolute():
            raise ValueError("staged dependency cas_path must be absolute")
        if not 1 <= len(self.lock_keys) <= _MAX_LOCK_KEYS_PER_ARTIFACT:
            raise ValueError("staged dependency lock key count is out of bounds")
        if tuple(sorted(set(self.lock_keys))) != self.lock_keys:
            raise ValueError("staged dependency lock keys must be unique and sorted")
        if self.version is not None:
            _string(self.version, "staged dependency version", maximum=256)

    def body_dict(self) -> dict[str, Any]:
        return {
            "resolved_url": self.resolved_url,
            "host": self.host,
            "integrity_algorithm": self.integrity_algorithm,
            "integrity_digest_base64": self.integrity_digest_base64,
            "byte_count": self.byte_count,
            "sha256": self.sha256,
            "cas_path": self.cas_path,
            "lock_keys": list(self.lock_keys),
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, value: Any) -> StagedDependencyArtifact:
        data = _mapping(value, "staged dependency artifact")
        expected = {
            "resolved_url",
            "host",
            "integrity_algorithm",
            "integrity_digest_base64",
            "byte_count",
            "sha256",
            "cas_path",
            "lock_keys",
            "version",
        }
        if set(data) != expected:
            raise ValueError("staged dependency artifact contains missing or unknown fields")
        keys = data["lock_keys"]
        if not isinstance(keys, list) or not all(isinstance(item, str) for item in keys):
            raise ValueError("staged dependency lock_keys must be an array of strings")
        version = data["version"]
        if version is not None and not isinstance(version, str):
            raise ValueError("staged dependency version must be string or null")
        return cls(
            resolved_url=_string(data["resolved_url"], "staged dependency resolved_url", maximum=2048),
            host=_canonical_host(_string(data["host"], "staged dependency host", maximum=253)),
            integrity_algorithm=_string(
                data["integrity_algorithm"],
                "staged dependency integrity_algorithm",
                maximum=16,
            ),
            integrity_digest_base64=_string(
                data["integrity_digest_base64"],
                "staged dependency integrity_digest_base64",
                maximum=256,
            ),
            byte_count=_integer(
                data["byte_count"],
                "staged dependency byte_count",
                maximum=_MAX_ARTIFACT_BYTES,
            ),
            sha256=_sha256(data["sha256"], "staged dependency sha256"),
            cas_path=_string(data["cas_path"], "staged dependency cas_path", maximum=4096),
            lock_keys=tuple(keys),
            version=version,
        )


@dataclass(frozen=True)
class DependencyReceipt:
    receipt_id: str
    timestamp_utc: str
    app_id: str
    repository_url: str
    commit_sha: str
    package_manager: str
    lockfile_version: int
    build_plan_sha256: str
    source_snapshot_sha256: str
    dependency_plan_sha256: str
    lockfile_path: str
    lockfile_sha256: str
    approved_hosts: tuple[str, ...]
    artifacts: tuple[StagedDependencyArtifact, ...]
    total_bytes: int
    store_root: str
    schema_version: str = DEPENDENCY_RECEIPT_SCHEMA_VERSION

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "timestamp_utc": self.timestamp_utc,
            "app_id": self.app_id,
            "repository_url": self.repository_url,
            "commit_sha": self.commit_sha,
            "package_manager": self.package_manager,
            "lockfile_version": self.lockfile_version,
            "build_plan_sha256": self.build_plan_sha256,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "dependency_plan_sha256": self.dependency_plan_sha256,
            "lockfile_path": self.lockfile_path,
            "lockfile_sha256": self.lockfile_sha256,
            "approved_hosts": list(self.approved_hosts),
            "artifacts": [artifact.body_dict() for artifact in self.artifacts],
            "total_bytes": self.total_bytes,
            "store_root": self.store_root,
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
        result["dependency_receipt_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> DependencyReceipt:
        data = _mapping(value, "dependency receipt")
        expected = {
            "schema_version",
            "receipt_id",
            "timestamp_utc",
            "app_id",
            "repository_url",
            "commit_sha",
            "package_manager",
            "lockfile_version",
            "build_plan_sha256",
            "source_snapshot_sha256",
            "dependency_plan_sha256",
            "lockfile_path",
            "lockfile_sha256",
            "approved_hosts",
            "artifacts",
            "total_bytes",
            "store_root",
            "dependency_receipt_sha256",
        }
        if set(data) != expected:
            raise ValueError("dependency receipt contains missing or unknown fields")
        if data["schema_version"] != DEPENDENCY_RECEIPT_SCHEMA_VERSION:
            raise ValueError("Unsupported dependency receipt schema")
        hosts = data["approved_hosts"]
        artifacts_value = data["artifacts"]
        if not isinstance(hosts, list) or not all(isinstance(item, str) for item in hosts):
            raise ValueError("dependency receipt approved_hosts must be an array of strings")
        if not isinstance(artifacts_value, list):
            raise ValueError("dependency receipt artifacts must be an array")
        artifacts = tuple(StagedDependencyArtifact.from_dict(item) for item in artifacts_value)
        if not 1 <= len(artifacts) <= _MAX_DEPENDENCY_ARTIFACTS:
            raise ValueError("dependency receipt artifact count is out of bounds")
        canonical_hosts = tuple(sorted({_canonical_host(host) for host in hosts}))
        if canonical_hosts != tuple(hosts):
            raise ValueError("dependency receipt approved_hosts must be unique and sorted")
        if tuple(sorted({artifact.host for artifact in artifacts})) != canonical_hosts:
            raise ValueError("dependency receipt hosts must exactly match staged artifact hosts")
        total_bytes = _integer(
            data["total_bytes"],
            "dependency receipt total_bytes",
            maximum=_MAX_TOTAL_STAGE_BYTES,
        )
        if total_bytes != sum(item.byte_count for item in artifacts):
            raise ValueError("dependency receipt total_bytes does not match artifacts")
        store_root = Path(_string(data["store_root"], "dependency receipt store_root", maximum=4096))
        if not store_root.is_absolute():
            raise ValueError("dependency receipt store_root must be absolute")
        resolved_store = store_root.resolve()
        cas_root = resolved_store / "cas" / "sha256"
        for artifact in artifacts:
            cas_path = Path(artifact.cas_path).resolve()
            if cas_root != cas_path and cas_root not in cas_path.parents:
                raise ValueError("dependency receipt artifact CAS path escaped store root")
            if cas_path.name != f"{artifact.sha256}.blob":
                raise ValueError("dependency receipt artifact CAS filename does not match SHA-256")
        receipt = cls(
            schema_version=data["schema_version"],
            receipt_id=_string(data["receipt_id"], "dependency receipt receipt_id", maximum=64),
            timestamp_utc=_string(
                data["timestamp_utc"],
                "dependency receipt timestamp_utc",
                maximum=128,
            ),
            app_id=_string(data["app_id"], "dependency receipt app_id", maximum=64),
            repository_url=_string(
                data["repository_url"],
                "dependency receipt repository_url",
                maximum=512,
            ),
            commit_sha=_string(data["commit_sha"], "dependency receipt commit_sha", maximum=64),
            package_manager=_string(
                data["package_manager"],
                "dependency receipt package_manager",
                maximum=32,
            ),
            lockfile_version=_integer(
                data["lockfile_version"],
                "dependency receipt lockfile_version",
                maximum=10,
            ),
            build_plan_sha256=_sha256(
                data["build_plan_sha256"],
                "dependency receipt build_plan_sha256",
            ),
            source_snapshot_sha256=_sha256(
                data["source_snapshot_sha256"],
                "dependency receipt source_snapshot_sha256",
            ),
            dependency_plan_sha256=_sha256(
                data["dependency_plan_sha256"],
                "dependency receipt dependency_plan_sha256",
            ),
            lockfile_path=_string(
                data["lockfile_path"],
                "dependency receipt lockfile_path",
                maximum=64,
            ),
            lockfile_sha256=_sha256(
                data["lockfile_sha256"],
                "dependency receipt lockfile_sha256",
            ),
            approved_hosts=canonical_hosts,
            artifacts=artifacts,
            total_bytes=total_bytes,
            store_root=str(resolved_store),
        )
        if receipt.package_manager != "npm" or receipt.lockfile_version not in {2, 3}:
            raise ValueError("Unsupported dependency receipt package-manager/lockfile version")
        if data["dependency_receipt_sha256"] != receipt.sha256():
            raise ValueError("dependency receipt digest does not match canonical receipt")
        return receipt


def _verify_existing_cas(path: Path, expected_sha256: str, expected_bytes: int) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Existing dependency CAS entry is not a regular file")
    if path.stat().st_size != expected_bytes:
        raise ValueError("Existing dependency CAS entry byte count does not match")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected_sha256:
        raise ValueError("Existing dependency CAS entry digest does not match")


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


class DependencyStagingService:
    def __init__(self, *, downloader: DependencyDownloader | None = None) -> None:
        self.downloader = downloader or HttpsDependencyDownloader()

    def stage(
        self,
        request: DependencyStageRequest,
        *,
        store_root: Path,
        receipt_root: Path | None = None,
    ) -> DependencyReceipt:
        plan = request.plan
        root = store_root.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        root = root.resolve(strict=True)
        cas_candidate = root / "cas" / "sha256"
        cas_candidate.mkdir(parents=True, exist_ok=True)
        cas_root = cas_candidate.resolve(strict=True)
        if root != cas_root and root not in cas_root.parents:
            raise ValueError("Dependency CAS tree escaped configured store root")

        receipts = (receipt_root or (root / ".phios-receipts")).expanduser().resolve()
        if receipts == cas_root or cas_root in receipts.parents:
            raise ValueError("Dependency receipt root must remain outside the CAS tree")

        staged: list[StagedDependencyArtifact] = []
        total_bytes = 0
        receipt_id = str(uuid.uuid4())

        for artifact in plan.artifacts:
            content = self.downloader.download(
                artifact,
                approved_hosts=request.approved_hosts,
            )
            if len(content) > _MAX_ARTIFACT_BYTES:
                raise ValueError("Dependency artifact exceeds bounded size")
            total_bytes += len(content)
            if total_bytes > _MAX_TOTAL_STAGE_BYTES:
                raise ValueError("Dependency staging exceeds bounded total bytes")
            _verify_sri(
                content,
                artifact.integrity_algorithm,
                artifact.integrity_digest_base64,
            )
            digest = hashlib.sha256(content).hexdigest()
            destination = cas_root / digest[:2] / f"{digest}.blob"
            destination.parent.mkdir(parents=True, exist_ok=True)
            resolved_parent = destination.parent.resolve(strict=True)
            if cas_root != resolved_parent and cas_root not in resolved_parent.parents:
                raise ValueError("Dependency CAS shard escaped configured CAS root")
            destination = resolved_parent / destination.name

            if destination.exists():
                _verify_existing_cas(destination, digest, len(content))
            else:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    prefix=".dependency-",
                    dir=destination.parent,
                    delete=False,
                ) as temp:
                    temp.write(content)
                    temp_path = Path(temp.name)
                try:
                    os.chmod(temp_path, 0o444)
                    temp_path.replace(destination)
                finally:
                    if temp_path.exists():
                        temp_path.unlink()

            staged.append(
                StagedDependencyArtifact(
                    resolved_url=artifact.resolved_url,
                    host=artifact.host,
                    integrity_algorithm=artifact.integrity_algorithm,
                    integrity_digest_base64=artifact.integrity_digest_base64,
                    byte_count=len(content),
                    sha256=digest,
                    cas_path=str(destination),
                    lock_keys=artifact.lock_keys,
                    version=artifact.version,
                )
            )

        receipt = DependencyReceipt(
            receipt_id=receipt_id,
            timestamp_utc=datetime.now(UTC).isoformat(),
            app_id=plan.app_id,
            repository_url=plan.repository_url,
            commit_sha=plan.commit_sha,
            package_manager=plan.package_manager,
            lockfile_version=plan.lockfile_version,
            build_plan_sha256=plan.build_plan_sha256,
            source_snapshot_sha256=plan.source_snapshot_sha256,
            dependency_plan_sha256=plan.sha256(),
            lockfile_path=plan.lockfile_path,
            lockfile_sha256=plan.lockfile_sha256,
            approved_hosts=request.approved_hosts,
            artifacts=tuple(staged),
            total_bytes=total_bytes,
            store_root=str(root),
            )
        receipt_path = receipts / f"dependency-{receipt_id}.json"
        _write_json_atomic(receipt_path, receipt.to_dict())
        return receipt
