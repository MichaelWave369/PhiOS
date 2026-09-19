from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from .desktop_launch import DesktopLaunchGrant
from .desktop_update import (
    DesktopRetentionMarker,
    _contained,
    _load_bundle,
    _root,
    _verify_current_bundle,
)
from .package_install import AppInstallReceipt, snapshot_installed_tree

RETAINED_CLEANUP_PLAN_SCHEMA_VERSION = "phios.retained_cleanup_plan.v0.1"
RETAINED_CLEANUP_REVIEW_SCHEMA_VERSION = "phios.retained_cleanup_review.v0.1"
RETAINED_CLEANUP_JOURNAL_SCHEMA_VERSION = "phios.retained_cleanup_journal.v0.1"
RETAINED_CLEANUP_RECEIPT_SCHEMA_VERSION = "phios.retained_cleanup_receipt.v0.1"

CleanupScope = Literal["desktop_bundle_only", "desktop_bundle_and_install"]
CleanupStatus = Literal["cleaned"]

_DESKTOP_CLEANUP_PERMISSION = "desktop.cleanup.retained"
_INSTALL_CLEANUP_PERMISSION = "install.cleanup.retained"
_MAX_JSON_BYTES = 2 * 1024 * 1024


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
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return text


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(_canonical_json(payload) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_json(path: Path, label: str) -> Any:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is unavailable or unsafe")
    if path.stat().st_size > _MAX_JSON_BYTES:
        raise ValueError(f"{label} exceeds bounded size")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is invalid JSON") from exc


def _cleanup_permissions(scope: CleanupScope) -> tuple[str, ...]:
    if scope == "desktop_bundle_only":
        return (_DESKTOP_CLEANUP_PERMISSION,)
    if scope == "desktop_bundle_and_install":
        return (_DESKTOP_CLEANUP_PERMISSION, _INSTALL_CLEANUP_PERMISSION)
    raise ValueError("unsupported retained cleanup scope")


def _verify_marker_uniqueness(
    app_dir: Path,
    selected_marker_path: Path,
    retained_bundle_path: Path,
) -> None:
    matches = 0
    for child in sorted(app_dir.iterdir(), key=lambda path: path.name):
        if (
            child == selected_marker_path
            or (
                child.is_file()
                and not child.is_symlink()
                and child.name.startswith(".retained-")
                and child.name.endswith(".json")
            )
        ):
            try:
                marker = DesktopRetentionMarker.from_dict(
                    _read_json(child, "desktop retention marker")
                )
            except ValueError:
                if child == selected_marker_path:
                    raise
                continue
            if Path(marker.retained_bundle_path) == retained_bundle_path:
                matches += 1
    if matches != 1:
        raise ValueError("retained cleanup target must have exactly one retention marker")


@dataclass(frozen=True)
class RetainedCleanupPlan:
    app_id: str
    retained_version: str
    active_version: str
    scope: CleanupScope
    retained_bundle_path: str
    active_bundle_path: str
    retention_marker_path: str
    desktop_entry_path: str
    retained_desktop_plan_sha256: str
    retained_grant_sha256: str
    retained_install_receipt_sha256: str
    retained_installed_tree_sha256: str
    retained_install_path: str
    active_desktop_plan_sha256: str
    active_grant_sha256: str
    active_entry_sha256: str
    retention_marker_sha256: str
    requested_cleanup_permissions: tuple[str, ...]
    cleanup_authority: bool = False
    rollback_authority: bool = False
    schema_version: str = RETAINED_CLEANUP_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RETAINED_CLEANUP_PLAN_SCHEMA_VERSION:
            raise ValueError(f"Unsupported retained cleanup plan schema: {self.schema_version}")
        _string(self.app_id, "cleanup app_id", maximum=64)
        _string(self.retained_version, "retained_version", maximum=128)
        _string(self.active_version, "active_version", maximum=128)
        if self.retained_version == self.active_version:
            raise ValueError("retained and active versions must differ")
        if self.scope not in {"desktop_bundle_only", "desktop_bundle_and_install"}:
            raise ValueError("unsupported retained cleanup scope")
        for value, label in (
            (self.retained_bundle_path, "retained_bundle_path"),
            (self.active_bundle_path, "active_bundle_path"),
            (self.retention_marker_path, "retention_marker_path"),
            (self.desktop_entry_path, "desktop_entry_path"),
            (self.retained_install_path, "retained_install_path"),
        ):
            if not Path(value).is_absolute():
                raise ValueError(f"{label} must be absolute")
        if self.retained_bundle_path == self.active_bundle_path:
            raise ValueError("retained cleanup cannot target active bundle")
        for value, label in (
            (self.retained_desktop_plan_sha256, "retained_desktop_plan_sha256"),
            (self.retained_grant_sha256, "retained_grant_sha256"),
            (self.retained_install_receipt_sha256, "retained_install_receipt_sha256"),
            (self.retained_installed_tree_sha256, "retained_installed_tree_sha256"),
            (self.active_desktop_plan_sha256, "active_desktop_plan_sha256"),
            (self.active_grant_sha256, "active_grant_sha256"),
            (self.active_entry_sha256, "active_entry_sha256"),
            (self.retention_marker_sha256, "retention_marker_sha256"),
        ):
            _sha256(value, label)
        if self.requested_cleanup_permissions != _cleanup_permissions(self.scope):
            raise ValueError("retained cleanup permission set does not match cleanup scope")
        if not isinstance(self.cleanup_authority, bool) or not isinstance(
            self.rollback_authority, bool
        ):
            raise ValueError("retained cleanup authority fields must be boolean")
        if self.cleanup_authority or self.rollback_authority:
            raise ValueError("retained cleanup plan grants no transition authority")

    def body_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["requested_cleanup_permissions"] = list(
            self.requested_cleanup_permissions
        )
        return result

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["retained_cleanup_plan_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> RetainedCleanupPlan:
        data = _mapping(value, "retained cleanup plan")
        expected = {
            "schema_version",
            "app_id",
            "retained_version",
            "active_version",
            "scope",
            "retained_bundle_path",
            "active_bundle_path",
            "retention_marker_path",
            "desktop_entry_path",
            "retained_desktop_plan_sha256",
            "retained_grant_sha256",
            "retained_install_receipt_sha256",
            "retained_installed_tree_sha256",
            "retained_install_path",
            "active_desktop_plan_sha256",
            "active_grant_sha256",
            "active_entry_sha256",
            "retention_marker_sha256",
            "requested_cleanup_permissions",
            "cleanup_authority",
            "rollback_authority",
            "retained_cleanup_plan_sha256",
        }
        if set(data) != expected:
            raise ValueError("retained cleanup plan contains missing or unknown fields")
        permissions = data["requested_cleanup_permissions"]
        if not isinstance(permissions, list):
            raise ValueError("requested_cleanup_permissions must be an array")
        scope = _string(data["scope"], "cleanup scope", maximum=64)
        if scope not in {"desktop_bundle_only", "desktop_bundle_and_install"}:
            raise ValueError("unsupported retained cleanup scope")
        plan = cls(
            schema_version=data["schema_version"],
            app_id=_string(data["app_id"], "app_id", maximum=64),
            retained_version=_string(
                data["retained_version"],
                "retained_version",
                maximum=128,
            ),
            active_version=_string(
                data["active_version"],
                "active_version",
                maximum=128,
            ),
            scope=cast(CleanupScope, scope),
            retained_bundle_path=_string(
                data["retained_bundle_path"],
                "retained_bundle_path",
                maximum=4096,
            ),
            active_bundle_path=_string(
                data["active_bundle_path"],
                "active_bundle_path",
                maximum=4096,
            ),
            retention_marker_path=_string(
                data["retention_marker_path"],
                "retention_marker_path",
                maximum=4096,
            ),
            desktop_entry_path=_string(
                data["desktop_entry_path"],
                "desktop_entry_path",
                maximum=4096,
            ),
            retained_desktop_plan_sha256=_sha256(
                data["retained_desktop_plan_sha256"],
                "retained_desktop_plan_sha256",
            ),
            retained_grant_sha256=_sha256(
                data["retained_grant_sha256"],
                "retained_grant_sha256",
            ),
            retained_install_receipt_sha256=_sha256(
                data["retained_install_receipt_sha256"],
                "retained_install_receipt_sha256",
            ),
            retained_installed_tree_sha256=_sha256(
                data["retained_installed_tree_sha256"],
                "retained_installed_tree_sha256",
            ),
            retained_install_path=_string(
                data["retained_install_path"],
                "retained_install_path",
                maximum=4096,
            ),
            active_desktop_plan_sha256=_sha256(
                data["active_desktop_plan_sha256"],
                "active_desktop_plan_sha256",
            ),
            active_grant_sha256=_sha256(
                data["active_grant_sha256"],
                "active_grant_sha256",
            ),
            active_entry_sha256=_sha256(
                data["active_entry_sha256"],
                "active_entry_sha256",
            ),
            retention_marker_sha256=_sha256(
                data["retention_marker_sha256"],
                "retention_marker_sha256",
            ),
            requested_cleanup_permissions=tuple(
                _string(item, "cleanup permission", maximum=128)
                for item in permissions
            ),
            cleanup_authority=data["cleanup_authority"],
            rollback_authority=data["rollback_authority"],
        )
        if data["retained_cleanup_plan_sha256"] != plan.sha256():
            raise ValueError("retained cleanup plan digest does not match canonical plan")
        return plan


def plan_retained_cleanup(
    retention_marker_path: Path,
    *,
    scope: CleanupScope,
    install_root: Path,
    desktop_root: Path,
    applications_root: Path,
) -> RetainedCleanupPlan:
    desktop = _root(desktop_root, "desktop app bundle root")
    applications = _root(applications_root, "desktop applications root")
    installed = _root(install_root, "installed app root")

    marker_path = _contained(
        desktop,
        retention_marker_path,
        "desktop retention marker",
    )
    marker = DesktopRetentionMarker.from_dict(
        _read_json(marker_path, "desktop retention marker")
    )
    retained = _load_bundle(Path(marker.retained_bundle_path), desktop_root=desktop)
    active = _load_bundle(Path(marker.active_bundle_path), desktop_root=desktop)

    if retained.plan.app_id != marker.app_id or active.plan.app_id != marker.app_id:
        raise ValueError("retained cleanup marker app identity mismatch")
    if retained.plan.app_id != active.plan.app_id:
        raise ValueError("retained and active bundles belong to different apps")
    if retained.plan.app_version != marker.retained_version:
        raise ValueError("retained cleanup marker retained version mismatch")
    if active.plan.app_version != marker.active_version:
        raise ValueError("retained cleanup marker active version mismatch")
    if retained.plan.sha256() != marker.retained_desktop_plan_sha256:
        raise ValueError("retained cleanup marker retained plan mismatch")
    if retained.grant.sha256() != marker.retained_grant_sha256:
        raise ValueError("retained cleanup marker retained grant mismatch")
    if active.plan.sha256() != marker.active_desktop_plan_sha256:
        raise ValueError("retained cleanup marker active plan mismatch")
    if active.grant.sha256() != marker.active_grant_sha256:
        raise ValueError("retained cleanup marker active grant mismatch")
    if retained.path == active.path:
        raise ValueError("retained cleanup cannot target active bundle")

    expected_marker_name = (
        f".retained-{retained.plan.sha256()[:16]}.json"
    )
    if marker_path.name != expected_marker_name or marker_path.parent != retained.path.parent:
        raise ValueError("retention marker path does not match retained bundle identity")

    _verify_marker_uniqueness(marker_path.parent, marker_path, retained.path)

    _verify_current_bundle(
        active,
        install_root=installed,
        applications_root=applications,
        require_active_entry=True,
    )
    _verify_current_bundle(
        retained,
        install_root=installed,
        applications_root=applications,
        require_active_entry=False,
    )

    active_entry = _contained(
        applications,
        Path(active.grant.desktop_entry_path),
        "active desktop entry",
    )
    if Path(retained.grant.desktop_entry_path) != active_entry:
        raise ValueError("retained grant points to a different desktop entry")
    current_entry_sha = hashlib.sha256(active_entry.read_bytes()).hexdigest()
    if current_entry_sha != active.grant.desktop_entry_sha256:
        raise ValueError("current desktop entry does not match active grant")
    if current_entry_sha == retained.grant.desktop_entry_sha256:
        raise ValueError("cleanup target is still active")

    retained_install = retained.install_receipt
    retained_install_path = _contained(
        installed,
        Path(retained_install.install_path),
        "retained install path",
    )
    retained_tree_sha, _, _ = snapshot_installed_tree(retained_install_path)
    if retained_tree_sha != retained_install.installed_tree_sha256:
        raise ValueError("retained installed tree changed since install receipt")

    return RetainedCleanupPlan(
        app_id=retained.plan.app_id,
        retained_version=retained.plan.app_version,
        active_version=active.plan.app_version,
        scope=scope,
        retained_bundle_path=str(retained.path),
        active_bundle_path=str(active.path),
        retention_marker_path=str(marker_path),
        desktop_entry_path=str(active_entry),
        retained_desktop_plan_sha256=retained.plan.sha256(),
        retained_grant_sha256=retained.grant.sha256(),
        retained_install_receipt_sha256=retained_install.sha256(),
        retained_installed_tree_sha256=retained_install.installed_tree_sha256,
        retained_install_path=str(retained_install_path),
        active_desktop_plan_sha256=active.plan.sha256(),
        active_grant_sha256=active.grant.sha256(),
        active_entry_sha256=current_entry_sha,
        retention_marker_sha256=marker.sha256(),
        requested_cleanup_permissions=_cleanup_permissions(scope),
        cleanup_authority=False,
        rollback_authority=False,
    )


@dataclass(frozen=True)
class RetainedCleanupReview:
    retained_cleanup_plan_sha256: str
    app_id: str
    retained_version: str
    active_version: str
    scope: CleanupScope
    retained_bundle_path: str
    retained_install_path: str
    retained_grant_sha256: str
    active_grant_sha256: str
    retention_marker_sha256: str
    requested_cleanup_permissions: tuple[str, ...]
    cleanup_authority: bool
    rollback_authority: bool
    schema_version: str = RETAINED_CLEANUP_REVIEW_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["requested_cleanup_permissions"] = list(
            self.requested_cleanup_permissions
        )
        return result


def review_retained_cleanup(value: Any) -> RetainedCleanupReview:
    plan = RetainedCleanupPlan.from_dict(value)
    return RetainedCleanupReview(
        retained_cleanup_plan_sha256=plan.sha256(),
        app_id=plan.app_id,
        retained_version=plan.retained_version,
        active_version=plan.active_version,
        scope=plan.scope,
        retained_bundle_path=plan.retained_bundle_path,
        retained_install_path=plan.retained_install_path,
        retained_grant_sha256=plan.retained_grant_sha256,
        active_grant_sha256=plan.active_grant_sha256,
        retention_marker_sha256=plan.retention_marker_sha256,
        requested_cleanup_permissions=plan.requested_cleanup_permissions,
        cleanup_authority=False,
        rollback_authority=False,
    )


@dataclass(frozen=True)
class RetainedCleanupRequest:
    plan: RetainedCleanupPlan
    approved_cleanup_plan_sha256: str
    approved_retained_grant_sha256: str
    approved_active_grant_sha256: str
    approved_retention_marker_sha256: str
    approved_cleanup_permissions: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.approved_cleanup_plan_sha256 != self.plan.sha256():
            raise ValueError("Approved cleanup plan SHA-256 does not match canonical plan")
        if self.approved_retained_grant_sha256 != self.plan.retained_grant_sha256:
            raise ValueError("Approved retained grant SHA-256 does not match cleanup plan")
        if self.approved_active_grant_sha256 != self.plan.active_grant_sha256:
            raise ValueError("Approved active grant SHA-256 does not match cleanup plan")
        if self.approved_retention_marker_sha256 != self.plan.retention_marker_sha256:
            raise ValueError("Approved retention marker SHA-256 does not match cleanup plan")
        if self.approved_cleanup_permissions != self.plan.requested_cleanup_permissions:
            raise ValueError("Approved cleanup permissions must exactly match reviewed plan")

    @classmethod
    def from_payload(
        cls,
        plan_value: Any,
        *,
        approved_cleanup_plan_sha256: str,
        approved_retained_grant_sha256: str,
        approved_active_grant_sha256: str,
        approved_retention_marker_sha256: str,
        approved_cleanup_permissions: tuple[str, ...],
    ) -> RetainedCleanupRequest:
        plan = RetainedCleanupPlan.from_dict(plan_value)
        return cls(
            plan=plan,
            approved_cleanup_plan_sha256=_sha256(
                approved_cleanup_plan_sha256,
                "approved_cleanup_plan_sha256",
            ),
            approved_retained_grant_sha256=_sha256(
                approved_retained_grant_sha256,
                "approved_retained_grant_sha256",
            ),
            approved_active_grant_sha256=_sha256(
                approved_active_grant_sha256,
                "approved_active_grant_sha256",
            ),
            approved_retention_marker_sha256=_sha256(
                approved_retention_marker_sha256,
                "approved_retention_marker_sha256",
            ),
            approved_cleanup_permissions=tuple(sorted(approved_cleanup_permissions)),
        )


@dataclass(frozen=True)
class RetainedCleanupJournal:
    journal_id: str
    timestamp_utc: str
    retained_cleanup_plan_sha256: str
    app_id: str
    retained_version: str
    active_version: str
    scope: CleanupScope
    retained_bundle_path: str
    retained_install_path: str
    retention_marker_path: str
    retained_grant_sha256: str
    active_grant_sha256: str
    retention_marker_sha256: str
    approved_cleanup_permissions: tuple[str, ...]
    status: str = "prepared"
    schema_version: str = RETAINED_CLEANUP_JOURNAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RETAINED_CLEANUP_JOURNAL_SCHEMA_VERSION:
            raise ValueError(f"Unsupported cleanup journal schema: {self.schema_version}")
        try:
            uuid.UUID(self.journal_id)
        except ValueError as exc:
            raise ValueError("cleanup journal_id must be a UUID") from exc
        parsed = datetime.fromisoformat(self.timestamp_utc)
        if parsed.tzinfo is None:
            raise ValueError("cleanup journal timestamp must include timezone")
        if self.scope not in {"desktop_bundle_only", "desktop_bundle_and_install"}:
            raise ValueError("unsupported cleanup journal scope")
        for value, label in (
            (self.retained_cleanup_plan_sha256, "retained_cleanup_plan_sha256"),
            (self.retained_grant_sha256, "retained_grant_sha256"),
            (self.active_grant_sha256, "active_grant_sha256"),
            (self.retention_marker_sha256, "retention_marker_sha256"),
        ):
            _sha256(value, label)
        if self.approved_cleanup_permissions != _cleanup_permissions(self.scope):
            raise ValueError("cleanup journal permission set does not match scope")
        if self.status != "prepared":
            raise ValueError("unsupported cleanup journal status")

    def body_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["approved_cleanup_permissions"] = list(
            self.approved_cleanup_permissions
        )
        return result

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["retained_cleanup_journal_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> RetainedCleanupJournal:
        data = _mapping(value, "retained cleanup journal")
        expected = {
            "schema_version",
            "journal_id",
            "timestamp_utc",
            "retained_cleanup_plan_sha256",
            "app_id",
            "retained_version",
            "active_version",
            "scope",
            "retained_bundle_path",
            "retained_install_path",
            "retention_marker_path",
            "retained_grant_sha256",
            "active_grant_sha256",
            "retention_marker_sha256",
            "approved_cleanup_permissions",
            "status",
            "retained_cleanup_journal_sha256",
        }
        if set(data) != expected:
            raise ValueError("retained cleanup journal contains missing or unknown fields")
        permissions = data["approved_cleanup_permissions"]
        if not isinstance(permissions, list):
            raise ValueError("cleanup journal permissions must be an array")
        scope = _string(data["scope"], "cleanup journal scope", maximum=64)
        if scope not in {"desktop_bundle_only", "desktop_bundle_and_install"}:
            raise ValueError("unsupported cleanup journal scope")
        journal = cls(
            schema_version=data["schema_version"],
            journal_id=_string(data["journal_id"], "journal_id", maximum=64),
            timestamp_utc=_string(data["timestamp_utc"], "timestamp_utc", maximum=128),
            retained_cleanup_plan_sha256=_sha256(
                data["retained_cleanup_plan_sha256"],
                "retained_cleanup_plan_sha256",
            ),
            app_id=_string(data["app_id"], "app_id", maximum=64),
            retained_version=_string(
                data["retained_version"],
                "retained_version",
                maximum=128,
            ),
            active_version=_string(
                data["active_version"],
                "active_version",
                maximum=128,
            ),
            scope=cast(CleanupScope, scope),
            retained_bundle_path=_string(
                data["retained_bundle_path"],
                "retained_bundle_path",
                maximum=4096,
            ),
            retained_install_path=_string(
                data["retained_install_path"],
                "retained_install_path",
                maximum=4096,
            ),
            retention_marker_path=_string(
                data["retention_marker_path"],
                "retention_marker_path",
                maximum=4096,
            ),
            retained_grant_sha256=_sha256(
                data["retained_grant_sha256"],
                "retained_grant_sha256",
            ),
            active_grant_sha256=_sha256(
                data["active_grant_sha256"],
                "active_grant_sha256",
            ),
            retention_marker_sha256=_sha256(
                data["retention_marker_sha256"],
                "retention_marker_sha256",
            ),
            approved_cleanup_permissions=tuple(
                _string(item, "cleanup permission", maximum=128)
                for item in permissions
            ),
            status=_string(data["status"], "cleanup journal status", maximum=32),
        )
        if data["retained_cleanup_journal_sha256"] != journal.sha256():
            raise ValueError("cleanup journal digest does not match canonical journal")
        return journal


@dataclass(frozen=True)
class RetainedCleanupReceipt:
    receipt_id: str
    timestamp_utc: str
    retained_cleanup_plan_sha256: str
    retained_cleanup_journal_sha256: str
    app_id: str
    retained_version: str
    active_version: str
    scope: CleanupScope
    removed_bundle_path: str
    removed_install_path: str | None
    removed_install_receipt_sha256: str | None
    removed_installed_tree_sha256: str | None
    retired_marker_path: str
    retired_marker_sha256: str
    active_bundle_path: str
    active_grant_sha256: str
    cleanup_authority: bool
    rollback_authority: bool
    status: CleanupStatus = "cleaned"
    schema_version: str = RETAINED_CLEANUP_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RETAINED_CLEANUP_RECEIPT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported retained cleanup receipt schema: {self.schema_version}")
        try:
            uuid.UUID(self.receipt_id)
        except ValueError as exc:
            raise ValueError("cleanup receipt_id must be a UUID") from exc
        parsed = datetime.fromisoformat(self.timestamp_utc)
        if parsed.tzinfo is None:
            raise ValueError("cleanup receipt timestamp must include timezone")
        if self.scope not in {"desktop_bundle_only", "desktop_bundle_and_install"}:
            raise ValueError("unsupported cleanup receipt scope")
        for value, label in (
            (self.retained_cleanup_plan_sha256, "retained_cleanup_plan_sha256"),
            (self.retained_cleanup_journal_sha256, "retained_cleanup_journal_sha256"),
            (self.retired_marker_sha256, "retired_marker_sha256"),
            (self.active_grant_sha256, "active_grant_sha256"),
        ):
            _sha256(value, label)
        for value, label in (
            (self.removed_bundle_path, "removed_bundle_path"),
            (self.retired_marker_path, "retired_marker_path"),
            (self.active_bundle_path, "active_bundle_path"),
        ):
            if not Path(value).is_absolute():
                raise ValueError(f"{label} must be absolute")
        if self.scope == "desktop_bundle_only":
            if any(
                value is not None
                for value in (
                    self.removed_install_path,
                    self.removed_install_receipt_sha256,
                    self.removed_installed_tree_sha256,
                )
            ):
                raise ValueError("desktop-only cleanup receipt must not claim install deletion")
        else:
            if self.removed_install_path is None:
                raise ValueError("install cleanup receipt must include removed install path")
            if not Path(self.removed_install_path).is_absolute():
                raise ValueError("removed_install_path must be absolute")
            if self.removed_install_receipt_sha256 is None:
                raise ValueError("install cleanup receipt must bind install receipt")
            if self.removed_installed_tree_sha256 is None:
                raise ValueError("install cleanup receipt must bind installed tree")
            _sha256(
                self.removed_install_receipt_sha256,
                "removed_install_receipt_sha256",
            )
            _sha256(
                self.removed_installed_tree_sha256,
                "removed_installed_tree_sha256",
            )
        if not isinstance(self.cleanup_authority, bool) or not isinstance(
            self.rollback_authority, bool
        ):
            raise ValueError("cleanup receipt authority fields must be boolean")
        if not self.cleanup_authority or self.rollback_authority:
            raise ValueError("cleanup receipt authority state is invalid")
        if self.status != "cleaned":
            raise ValueError("unsupported cleanup status")

    def body_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["retained_cleanup_receipt_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> RetainedCleanupReceipt:
        data = _mapping(value, "retained cleanup receipt")
        expected = {
            "schema_version",
            "receipt_id",
            "timestamp_utc",
            "retained_cleanup_plan_sha256",
            "retained_cleanup_journal_sha256",
            "app_id",
            "retained_version",
            "active_version",
            "scope",
            "removed_bundle_path",
            "removed_install_path",
            "removed_install_receipt_sha256",
            "removed_installed_tree_sha256",
            "retired_marker_path",
            "retired_marker_sha256",
            "active_bundle_path",
            "active_grant_sha256",
            "cleanup_authority",
            "rollback_authority",
            "status",
            "retained_cleanup_receipt_sha256",
        }
        if set(data) != expected:
            raise ValueError("retained cleanup receipt contains missing or unknown fields")
        scope = _string(data["scope"], "cleanup receipt scope", maximum=64)
        if scope not in {"desktop_bundle_only", "desktop_bundle_and_install"}:
            raise ValueError("unsupported cleanup receipt scope")
        receipt = cls(
            schema_version=data["schema_version"],
            receipt_id=_string(data["receipt_id"], "receipt_id", maximum=64),
            timestamp_utc=_string(data["timestamp_utc"], "timestamp_utc", maximum=128),
            retained_cleanup_plan_sha256=_sha256(
                data["retained_cleanup_plan_sha256"],
                "retained_cleanup_plan_sha256",
            ),
            retained_cleanup_journal_sha256=_sha256(
                data["retained_cleanup_journal_sha256"],
                "retained_cleanup_journal_sha256",
            ),
            app_id=_string(data["app_id"], "app_id", maximum=64),
            retained_version=_string(
                data["retained_version"],
                "retained_version",
                maximum=128,
            ),
            active_version=_string(
                data["active_version"],
                "active_version",
                maximum=128,
            ),
            scope=cast(CleanupScope, scope),
            removed_bundle_path=_string(
                data["removed_bundle_path"],
                "removed_bundle_path",
                maximum=4096,
            ),
            removed_install_path=data["removed_install_path"],
            removed_install_receipt_sha256=data["removed_install_receipt_sha256"],
            removed_installed_tree_sha256=data["removed_installed_tree_sha256"],
            retired_marker_path=_string(
                data["retired_marker_path"],
                "retired_marker_path",
                maximum=4096,
            ),
            retired_marker_sha256=_sha256(
                data["retired_marker_sha256"],
                "retired_marker_sha256",
            ),
            active_bundle_path=_string(
                data["active_bundle_path"],
                "active_bundle_path",
                maximum=4096,
            ),
            active_grant_sha256=_sha256(
                data["active_grant_sha256"],
                "active_grant_sha256",
            ),
            cleanup_authority=data["cleanup_authority"],
            rollback_authority=data["rollback_authority"],
            status=data["status"],
        )
        if data["retained_cleanup_receipt_sha256"] != receipt.sha256():
            raise ValueError("retained cleanup receipt digest does not match canonical receipt")
        return receipt


@dataclass(frozen=True)
class RetainedCleanupResult:
    journal: RetainedCleanupJournal
    receipt: RetainedCleanupReceipt
    journal_path: str
    receipt_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "journal": self.journal.to_dict(),
            "receipt": self.receipt.to_dict(),
            "journal_path": self.journal_path,
            "receipt_path": self.receipt_path,
        }


class RetainedCleanupService:
    def execute(
        self,
        request: RetainedCleanupRequest,
        *,
        install_root: Path,
        desktop_root: Path,
        applications_root: Path,
        receipt_root: Path,
    ) -> RetainedCleanupResult:
        current_plan = plan_retained_cleanup(
            Path(request.plan.retention_marker_path),
            scope=request.plan.scope,
            install_root=install_root,
            desktop_root=desktop_root,
            applications_root=applications_root,
        )
        if current_plan.sha256() != request.plan.sha256():
            raise ValueError("retained cleanup binding changed after review")

        desktop = _root(desktop_root, "desktop app bundle root")
        installed = _root(install_root, "installed app root")
        receipts = _root(receipt_root, "retained cleanup receipt root", create=True)

        retained_bundle = _contained(
            desktop,
            Path(request.plan.retained_bundle_path),
            "retained desktop bundle",
        )
        marker_path = _contained(
            desktop,
            Path(request.plan.retention_marker_path),
            "desktop retention marker",
        )
        retained_install_path = _contained(
            installed,
            Path(request.plan.retained_install_path),
            "retained install path",
        )

        retained_install = AppInstallReceipt.from_dict(
            _read_json(
                retained_bundle / "install-receipt.json",
                "retained install receipt",
            )
        )
        if retained_install.sha256() != request.plan.retained_install_receipt_sha256:
            raise ValueError("retained install receipt changed after review")
        tree_sha, _, _ = snapshot_installed_tree(retained_install_path)
        if tree_sha != request.plan.retained_installed_tree_sha256:
            raise ValueError("retained installed tree changed after review")

        journal = RetainedCleanupJournal(
            journal_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(UTC).isoformat(),
            retained_cleanup_plan_sha256=request.plan.sha256(),
            app_id=request.plan.app_id,
            retained_version=request.plan.retained_version,
            active_version=request.plan.active_version,
            scope=request.plan.scope,
            retained_bundle_path=request.plan.retained_bundle_path,
            retained_install_path=request.plan.retained_install_path,
            retention_marker_path=request.plan.retention_marker_path,
            retained_grant_sha256=request.plan.retained_grant_sha256,
            active_grant_sha256=request.plan.active_grant_sha256,
            retention_marker_sha256=request.plan.retention_marker_sha256,
            approved_cleanup_permissions=request.approved_cleanup_permissions,
        )
        journal_path = receipts / f"retained-cleanup-journal-{journal.journal_id}.json"
        _write_json_atomic(journal_path, journal.to_dict())

        # Re-run the complete proof after the durable journal exists and before deletion.
        final_plan = plan_retained_cleanup(
            marker_path,
            scope=request.plan.scope,
            install_root=install_root,
            desktop_root=desktop_root,
            applications_root=applications_root,
        )
        if final_plan.sha256() != request.plan.sha256():
            raise ValueError("retained cleanup state changed after journal persistence")

        # Marker is removed first so catalog discovery cannot continue to describe a
        # soon-to-be-removed bundle as an intentional rollback target.
        marker_path.unlink()
        shutil.rmtree(retained_bundle)

        removed_install_path: str | None = None
        removed_install_receipt_sha256: str | None = None
        removed_installed_tree_sha256: str | None = None
        if request.plan.scope == "desktop_bundle_and_install":
            shutil.rmtree(retained_install_path)
            removed_install_path = str(retained_install_path)
            removed_install_receipt_sha256 = retained_install.sha256()
            removed_installed_tree_sha256 = tree_sha

        receipt = RetainedCleanupReceipt(
            receipt_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(UTC).isoformat(),
            retained_cleanup_plan_sha256=request.plan.sha256(),
            retained_cleanup_journal_sha256=journal.sha256(),
            app_id=request.plan.app_id,
            retained_version=request.plan.retained_version,
            active_version=request.plan.active_version,
            scope=request.plan.scope,
            removed_bundle_path=str(retained_bundle),
            removed_install_path=removed_install_path,
            removed_install_receipt_sha256=removed_install_receipt_sha256,
            removed_installed_tree_sha256=removed_installed_tree_sha256,
            retired_marker_path=str(marker_path),
            retired_marker_sha256=request.plan.retention_marker_sha256,
            active_bundle_path=request.plan.active_bundle_path,
            active_grant_sha256=request.plan.active_grant_sha256,
            cleanup_authority=True,
            rollback_authority=False,
        )
        receipt_path = receipts / f"retained-cleanup-{receipt.receipt_id}.json"
        _write_json_atomic(receipt_path, receipt.to_dict())
        return RetainedCleanupResult(
            journal=journal,
            receipt=receipt,
            journal_path=str(journal_path),
            receipt_path=str(receipt_path),
        )
