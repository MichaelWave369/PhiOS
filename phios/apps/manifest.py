from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Literal, cast
from urllib.parse import urlsplit

APP_MANIFEST_SCHEMA_VERSION = "phios.app_manifest.v0.1"

RuntimeKind = Literal["static_web", "node", "python", "local_http", "native"]
DistributionState = Literal["permitted", "restricted", "unknown"]

_RUNTIME_KINDS = {"static_web", "node", "python", "local_http", "native"}
_DISTRIBUTION_STATES = {"permitted", "restricted", "unknown"}
_APP_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?$")
_PERMISSION_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _expect_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, Any], value)


def _expect_keys(data: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(data) - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"{label} contains unknown fields: {names}")


def _bounded_text(value: Any, label: str, *, maximum: int, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    if not allow_empty and not value.strip():
        raise ValueError(f"{label} must not be empty")
    if len(value) > maximum:
        raise ValueError(f"{label} exceeds {maximum} characters")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"{label} contains control characters")
    return value


def _validate_repository_url(value: Any) -> str:
    url = _bounded_text(value, "source.repository_url", maximum=512)
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("source.repository_url must be an absolute https URL")
    if parsed.username or parsed.password:
        raise ValueError("source.repository_url must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("source.repository_url must not contain query or fragment data")
    if parsed.path in {"", "/"}:
        raise ValueError("source.repository_url must identify a repository path")
    return url


def _validate_relative_target(value: Any) -> str:
    target = _bounded_text(value, "entrypoint.target", maximum=256)
    if "\\" in target:
        raise ValueError("entrypoint.target must use POSIX path separators")
    path = PurePosixPath(target)
    if path.is_absolute() or target.startswith("/"):
        raise ValueError("entrypoint.target must be relative to the app root")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("entrypoint.target must not contain empty, dot, or parent segments")
    return target


def _validate_loopback_target(value: Any) -> str:
    target = _bounded_text(value, "entrypoint.target", maximum=512)
    parsed = urlsplit(target)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("local_http entrypoint.target must use http or https")
    if parsed.hostname not in _LOOPBACK_HOSTS:
        raise ValueError("local_http entrypoint.target must be loopback-only")
    if parsed.username or parsed.password:
        raise ValueError("local_http entrypoint.target must not contain credentials")
    if parsed.fragment:
        raise ValueError("local_http entrypoint.target must not contain a fragment")
    return target


@dataclass(frozen=True)
class AppSource:
    repository_url: str
    license_expression: str
    redistribution: DistributionState

    def __post_init__(self) -> None:
        _validate_repository_url(self.repository_url)
        _bounded_text(self.license_expression, "source.license_expression", maximum=128)
        if self.redistribution not in _DISTRIBUTION_STATES:
            raise ValueError(f"Unsupported redistribution state: {self.redistribution}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository_url": self.repository_url,
            "license_expression": self.license_expression,
            "redistribution": self.redistribution,
        }

    @classmethod
    def from_dict(cls, value: Any) -> AppSource:
        data = _expect_mapping(value, "source")
        _expect_keys(
            data,
            {"repository_url", "license_expression", "redistribution"},
            "source",
        )
        missing = {"repository_url", "license_expression", "redistribution"} - set(data)
        if missing:
            raise ValueError(f"source missing required fields: {', '.join(sorted(missing))}")
        redistribution = data["redistribution"]
        if redistribution not in _DISTRIBUTION_STATES:
            raise ValueError(f"Unsupported redistribution state: {redistribution}")
        return cls(
            repository_url=_validate_repository_url(data["repository_url"]),
            license_expression=_bounded_text(
                data["license_expression"],
                "source.license_expression",
                maximum=128,
            ),
            redistribution=cast(DistributionState, redistribution),
        )


@dataclass(frozen=True)
class AppEntrypoint:
    runtime: RuntimeKind
    target: str

    def __post_init__(self) -> None:
        if self.runtime not in _RUNTIME_KINDS:
            raise ValueError(f"Unsupported runtime kind: {self.runtime}")
        if self.runtime == "local_http":
            _validate_loopback_target(self.target)
        else:
            _validate_relative_target(self.target)

    def to_dict(self) -> dict[str, str]:
        return {"runtime": self.runtime, "target": self.target}

    @classmethod
    def from_dict(cls, value: Any) -> AppEntrypoint:
        data = _expect_mapping(value, "entrypoint")
        _expect_keys(data, {"runtime", "target"}, "entrypoint")
        missing = {"runtime", "target"} - set(data)
        if missing:
            raise ValueError(f"entrypoint missing required fields: {', '.join(sorted(missing))}")
        runtime = data["runtime"]
        if runtime not in _RUNTIME_KINDS:
            raise ValueError(f"Unsupported runtime kind: {runtime}")
        target = (
            _validate_loopback_target(data["target"])
            if runtime == "local_http"
            else _validate_relative_target(data["target"])
        )
        return cls(runtime=cast(RuntimeKind, runtime), target=target)


@dataclass(frozen=True)
class AppManifest:
    app_id: str
    name: str
    version: str
    description: str
    source: AppSource
    entrypoint: AppEntrypoint
    permissions: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = APP_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != APP_MANIFEST_SCHEMA_VERSION:
            raise ValueError(f"Unsupported app manifest schema: {self.schema_version}")
        if not _APP_ID_RE.fullmatch(self.app_id):
            raise ValueError(
                "app_id must be 1-64 lowercase characters using letters, numbers, '.', '_' or '-'"
            )
        _bounded_text(self.name, "name", maximum=96)
        _bounded_text(self.version, "version", maximum=64)
        _bounded_text(self.description, "description", maximum=512, allow_empty=True)
        if len(self.permissions) > 32:
            raise ValueError("permissions may contain at most 32 entries")
        if len(set(self.permissions)) != len(self.permissions):
            raise ValueError("permissions must not contain duplicates")
        for permission in self.permissions:
            if not _PERMISSION_RE.fullmatch(permission):
                raise ValueError(f"Invalid permission identifier: {permission}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app_id": self.app_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "source": self.source.to_dict(),
            "entrypoint": self.entrypoint.to_dict(),
            "permissions": sorted(self.permissions),
        }

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, value: Any) -> AppManifest:
        data = _expect_mapping(value, "manifest")
        allowed = {
            "schema_version",
            "app_id",
            "name",
            "version",
            "description",
            "source",
            "entrypoint",
            "permissions",
        }
        _expect_keys(data, allowed, "manifest")
        required = {
            "schema_version",
            "app_id",
            "name",
            "version",
            "description",
            "source",
            "entrypoint",
            "permissions",
        }
        missing = required - set(data)
        if missing:
            raise ValueError(f"manifest missing required fields: {', '.join(sorted(missing))}")
        if data["schema_version"] != APP_MANIFEST_SCHEMA_VERSION:
            raise ValueError(f"Unsupported app manifest schema: {data['schema_version']}")
        app_id = _bounded_text(data["app_id"], "app_id", maximum=64)
        if not _APP_ID_RE.fullmatch(app_id):
            raise ValueError(
                "app_id must be 1-64 lowercase characters using letters, numbers, '.', '_' or '-'"
            )
        permissions_value = data["permissions"]
        if not isinstance(permissions_value, list):
            raise ValueError("permissions must be an array")
        permissions = tuple(
            _bounded_text(item, "permission", maximum=128) for item in permissions_value
        )
        return cls(
            schema_version=APP_MANIFEST_SCHEMA_VERSION,
            app_id=app_id,
            name=_bounded_text(data["name"], "name", maximum=96),
            version=_bounded_text(data["version"], "version", maximum=64),
            description=_bounded_text(
                data["description"],
                "description",
                maximum=512,
                allow_empty=True,
            ),
            source=AppSource.from_dict(data["source"]),
            entrypoint=AppEntrypoint.from_dict(data["entrypoint"]),
            permissions=permissions,
        )

    @classmethod
    def from_json(cls, text: str) -> AppManifest:
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid app manifest JSON: {exc.msg}") from exc
        return cls.from_dict(value)
