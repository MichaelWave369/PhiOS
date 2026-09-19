from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from .browser_session import BrowserSessionPlan
from .desktop_launch import DesktopAppPlan, DesktopLaunchGrant, plan_desktop_app
from .desktop_update import DesktopRetentionMarker
from .package_install import AppInstallReceipt
from .static_web import StaticWebAdapterPlan

DESKTOP_CATALOG_SNAPSHOT_SCHEMA_VERSION = "phios.desktop_catalog_snapshot.v0.1"
DESKTOP_CATALOG_REVIEW_SCHEMA_VERSION = "phios.desktop_catalog_review.v0.1"
DESKTOP_CATALOG_RECEIPT_SCHEMA_VERSION = "phios.desktop_catalog_receipt.v0.1"

DesktopCatalogItemStatus = Literal["ready", "blocked"]
DesktopCatalogIssueCode = Literal[
    "unsafe_bundle",
    "bundle_name_invalid",
    "bundle_layout_invalid",
    "desktop_plan_invalid",
    "browser_plan_invalid",
    "static_plan_invalid",
    "install_receipt_invalid",
    "grant_invalid",
    "binding_mismatch",
    "desktop_entry_missing",
    "desktop_entry_unsafe",
    "desktop_entry_outside_root",
    "desktop_entry_digest_mismatch",
    "installed_app_drift",
    "duplicate_app_identity",
    "retained_inactive",
]
DesktopCatalogRootIssueCode = Literal[
    "unsafe_app_directory",
    "unexpected_root_entry",
    "unexpected_app_entry",
    "invalid_retention_marker",
]

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BUNDLE_NAME_RE = re.compile(r"^[0-9a-f]{16}$")
_EXPECTED_BUNDLE_FILES = {
    "desktop-plan.json",
    "browser-plan.json",
    "static-plan.json",
    "install-receipt.json",
    "grant.json",
}
_MAX_APP_DIRS = 512
_MAX_BUNDLES = 1024
_MAX_METADATA_BYTES = 2 * 1024 * 1024


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


def _read_json(path: Path, label: str) -> Any:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is unavailable or unsafe")
    size = path.stat().st_size
    if size > _MAX_METADATA_BYTES:
        raise ValueError(f"{label} exceeds bounded size")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is invalid JSON") from exc


def _root_path(path: Path, label: str, *, allow_missing: bool) -> tuple[Path, bool]:
    expanded = path.expanduser()
    if expanded.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    if not expanded.exists():
        if not allow_missing:
            raise ValueError(f"{label} is unavailable")
        return expanded.absolute(), False
    resolved = expanded.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError(f"{label} must be a directory")
    return resolved, True


def _under_root(root: Path, candidate: Path) -> bool:
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        return False
    return root == resolved or root in resolved.parents


@dataclass(frozen=True)
class DesktopCatalogIssue:
    code: DesktopCatalogIssueCode

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code}

    @classmethod
    def from_dict(cls, value: Any) -> DesktopCatalogIssue:
        data = _mapping(value, "desktop catalog issue")
        if set(data) != {"code"}:
            raise ValueError("desktop catalog issue contains missing or unknown fields")
        code = _string(data["code"], "desktop catalog issue code", maximum=64)
        allowed = {
            "unsafe_bundle",
            "bundle_name_invalid",
            "bundle_layout_invalid",
            "desktop_plan_invalid",
            "browser_plan_invalid",
            "static_plan_invalid",
            "install_receipt_invalid",
            "grant_invalid",
            "binding_mismatch",
            "desktop_entry_missing",
            "desktop_entry_unsafe",
            "desktop_entry_outside_root",
            "desktop_entry_digest_mismatch",
            "installed_app_drift",
            "duplicate_app_identity",
            "retained_inactive",
        }
        if code not in allowed:
            raise ValueError("unsupported desktop catalog issue code")
        return cls(code=cast(DesktopCatalogIssueCode, code))


@dataclass(frozen=True)
class DesktopCatalogRootIssue:
    code: DesktopCatalogRootIssueCode
    relative_path: str

    def __post_init__(self) -> None:
        _string(self.relative_path, "catalog root issue relative_path", maximum=512)
        path = Path(self.relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("catalog root issue path must be relative and contained")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Any) -> DesktopCatalogRootIssue:
        data = _mapping(value, "desktop catalog root issue")
        if set(data) != {"code", "relative_path"}:
            raise ValueError("desktop catalog root issue contains missing or unknown fields")
        code = _string(data["code"], "desktop catalog root issue code", maximum=64)
        if code not in {
            "unsafe_app_directory",
            "unexpected_root_entry",
            "unexpected_app_entry",
            "invalid_retention_marker",
        }:
            raise ValueError("unsupported desktop catalog root issue code")
        return cls(
            code=cast(DesktopCatalogRootIssueCode, code),
            relative_path=_string(
                data["relative_path"],
                "catalog root issue relative_path",
                maximum=512,
            ),
        )


@dataclass(frozen=True)
class DesktopCatalogItem:
    catalog_key: str
    bundle_path: str
    app_id: str | None
    app_version: str | None
    desktop_name: str | None
    desktop_icon: str | None
    desktop_entry_path: str | None
    desktop_app_plan_sha256: str | None
    desktop_launch_grant_sha256: str | None
    grant_status: str | None
    identity_verified: bool
    persistent_launch_grant_present: bool
    icon_asset_state: str
    status: DesktopCatalogItemStatus
    issues: tuple[DesktopCatalogIssue, ...]
    catalog_launch_authority: bool = False
    catalog_revoke_authority: bool = False

    def __post_init__(self) -> None:
        _string(self.catalog_key, "desktop catalog key", maximum=512)
        if not Path(self.bundle_path).is_absolute():
            raise ValueError("desktop catalog bundle_path must be absolute")
        optional_strings = (
            (self.app_id, "catalog app_id", 64),
            (self.app_version, "catalog app_version", 128),
            (self.desktop_name, "catalog desktop_name", 96),
            (self.desktop_icon, "catalog desktop_icon", 128),
            (self.desktop_entry_path, "catalog desktop_entry_path", 4096),
            (self.grant_status, "catalog grant_status", 64),
        )
        for value, label, maximum in optional_strings:
            if value is not None:
                _string(value, label, maximum=maximum)
        for value, label in (
            (self.desktop_app_plan_sha256, "desktop_app_plan_sha256"),
            (self.desktop_launch_grant_sha256, "desktop_launch_grant_sha256"),
        ):
            if value is not None:
                _sha256(value, label)
        bool_fields = (
            self.identity_verified,
            self.persistent_launch_grant_present,
            self.catalog_launch_authority,
            self.catalog_revoke_authority,
        )
        if any(not isinstance(value, bool) for value in bool_fields):
            raise ValueError("desktop catalog item authority/state fields must be boolean")
        if self.icon_asset_state != "metadata_only":
            raise ValueError("v0.39 supports only metadata_only icon state")
        if self.status not in {"ready", "blocked"}:
            raise ValueError("unsupported desktop catalog item status")
        if tuple(sorted(issue.code for issue in self.issues)) != tuple(
            issue.code for issue in self.issues
        ):
            raise ValueError("desktop catalog issues must be sorted")
        if len({issue.code for issue in self.issues}) != len(self.issues):
            raise ValueError("desktop catalog issues must be unique")
        if self.status == "ready":
            if self.issues:
                raise ValueError("ready desktop catalog item must not contain issues")
            if not self.identity_verified or not self.persistent_launch_grant_present:
                raise ValueError("ready desktop catalog item requires verified grant identity")
            if None in {
                self.app_id,
                self.app_version,
                self.desktop_name,
                self.desktop_icon,
                self.desktop_entry_path,
                self.desktop_app_plan_sha256,
                self.desktop_launch_grant_sha256,
                self.grant_status,
            }:
                raise ValueError("ready desktop catalog item is missing verified metadata")
            if self.grant_status != "enabled":
                raise ValueError("ready desktop catalog item requires enabled grant")
        else:
            if not self.issues:
                raise ValueError("blocked desktop catalog item requires issue evidence")
        if self.catalog_launch_authority or self.catalog_revoke_authority:
            raise ValueError("catalog items do not grant launch or revoke authority")

    def body_dict(self) -> dict[str, Any]:
        return {
            "catalog_key": self.catalog_key,
            "bundle_path": self.bundle_path,
            "app_id": self.app_id,
            "app_version": self.app_version,
            "desktop_name": self.desktop_name,
            "desktop_icon": self.desktop_icon,
            "desktop_entry_path": self.desktop_entry_path,
            "desktop_app_plan_sha256": self.desktop_app_plan_sha256,
            "desktop_launch_grant_sha256": self.desktop_launch_grant_sha256,
            "grant_status": self.grant_status,
            "identity_verified": self.identity_verified,
            "persistent_launch_grant_present": self.persistent_launch_grant_present,
            "icon_asset_state": self.icon_asset_state,
            "status": self.status,
            "issues": [issue.to_dict() for issue in self.issues],
            "catalog_launch_authority": self.catalog_launch_authority,
            "catalog_revoke_authority": self.catalog_revoke_authority,
        }

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["catalog_item_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> DesktopCatalogItem:
        data = _mapping(value, "desktop catalog item")
        expected = {
            "catalog_key",
            "bundle_path",
            "app_id",
            "app_version",
            "desktop_name",
            "desktop_icon",
            "desktop_entry_path",
            "desktop_app_plan_sha256",
            "desktop_launch_grant_sha256",
            "grant_status",
            "identity_verified",
            "persistent_launch_grant_present",
            "icon_asset_state",
            "status",
            "issues",
            "catalog_launch_authority",
            "catalog_revoke_authority",
            "catalog_item_sha256",
        }
        if set(data) != expected:
            raise ValueError("desktop catalog item contains missing or unknown fields")
        raw_issues = data["issues"]
        if not isinstance(raw_issues, list):
            raise ValueError("desktop catalog item issues must be an array")
        status = _string(data["status"], "desktop catalog item status", maximum=32)
        if status not in {"ready", "blocked"}:
            raise ValueError("unsupported desktop catalog item status")
        item = cls(
            catalog_key=_string(data["catalog_key"], "catalog_key", maximum=512),
            bundle_path=_string(data["bundle_path"], "bundle_path", maximum=4096),
            app_id=data["app_id"],
            app_version=data["app_version"],
            desktop_name=data["desktop_name"],
            desktop_icon=data["desktop_icon"],
            desktop_entry_path=data["desktop_entry_path"],
            desktop_app_plan_sha256=data["desktop_app_plan_sha256"],
            desktop_launch_grant_sha256=data["desktop_launch_grant_sha256"],
            grant_status=data["grant_status"],
            identity_verified=data["identity_verified"],
            persistent_launch_grant_present=data["persistent_launch_grant_present"],
            icon_asset_state=_string(
                data["icon_asset_state"],
                "icon_asset_state",
                maximum=64,
            ),
            status=cast(DesktopCatalogItemStatus, status),
            issues=tuple(DesktopCatalogIssue.from_dict(issue) for issue in raw_issues),
            catalog_launch_authority=data["catalog_launch_authority"],
            catalog_revoke_authority=data["catalog_revoke_authority"],
        )
        if data["catalog_item_sha256"] != item.sha256():
            raise ValueError("desktop catalog item digest does not match canonical item")
        return item


def _blocked_item(
    *,
    catalog_key: str,
    bundle_path: Path,
    issue_codes: set[DesktopCatalogIssueCode],
    plan: DesktopAppPlan | None = None,
    grant: DesktopLaunchGrant | None = None,
) -> DesktopCatalogItem:
    return DesktopCatalogItem(
        catalog_key=catalog_key,
        bundle_path=str(bundle_path),
        app_id=plan.app_id if plan is not None else None,
        app_version=plan.app_version if plan is not None else None,
        desktop_name=plan.desktop_name if plan is not None else None,
        desktop_icon=plan.desktop_icon if plan is not None else None,
        desktop_entry_path=grant.desktop_entry_path if grant is not None else None,
        desktop_app_plan_sha256=plan.sha256() if plan is not None else None,
        desktop_launch_grant_sha256=grant.sha256() if grant is not None else None,
        grant_status=grant.status if grant is not None else None,
        identity_verified=plan is not None,
        persistent_launch_grant_present=grant is not None,
        icon_asset_state="metadata_only",
        status="blocked",
        issues=tuple(
            DesktopCatalogIssue(code=code) for code in sorted(issue_codes)
        ),
    )


def _inspect_bundle(
    bundle: Path,
    *,
    desktop_root: Path,
    applications_root: Path,
    applications_present: bool,
    install_root: Path,
    retention_marker: DesktopRetentionMarker | None = None,
) -> DesktopCatalogItem:
    catalog_key = bundle.relative_to(desktop_root).as_posix()
    if bundle.is_symlink() or not bundle.is_dir():
        return _blocked_item(
            catalog_key=catalog_key,
            bundle_path=bundle.absolute(),
            issue_codes={"unsafe_bundle"},
        )
    bundle = bundle.resolve(strict=True)
    if not _BUNDLE_NAME_RE.fullmatch(bundle.name):
        return _blocked_item(
            catalog_key=catalog_key,
            bundle_path=bundle,
            issue_codes={"bundle_name_invalid"},
        )
    children = sorted(bundle.iterdir(), key=lambda path: path.name)
    if (
        {child.name for child in children} != _EXPECTED_BUNDLE_FILES
        or any(child.is_symlink() or not child.is_file() for child in children)
    ):
        return _blocked_item(
            catalog_key=catalog_key,
            bundle_path=bundle,
            issue_codes={"bundle_layout_invalid"},
        )

    try:
        plan = DesktopAppPlan.from_dict(
            _read_json(bundle / "desktop-plan.json", "desktop plan")
        )
    except ValueError:
        return _blocked_item(
            catalog_key=catalog_key,
            bundle_path=bundle,
            issue_codes={"desktop_plan_invalid"},
        )
    if bundle.parent.name != plan.app_id or bundle.name != plan.sha256()[:16]:
        return _blocked_item(
            catalog_key=catalog_key,
            bundle_path=bundle,
            issue_codes={"binding_mismatch"},
            plan=plan,
        )

    try:
        browser = BrowserSessionPlan.from_dict(
            _read_json(bundle / "browser-plan.json", "browser plan")
        )
    except ValueError:
        return _blocked_item(
            catalog_key=catalog_key,
            bundle_path=bundle,
            issue_codes={"browser_plan_invalid"},
            plan=plan,
        )
    try:
        static = StaticWebAdapterPlan.from_dict(
            _read_json(bundle / "static-plan.json", "static plan")
        )
    except ValueError:
        return _blocked_item(
            catalog_key=catalog_key,
            bundle_path=bundle,
            issue_codes={"static_plan_invalid"},
            plan=plan,
        )
    try:
        install_receipt = AppInstallReceipt.from_dict(
            _read_json(bundle / "install-receipt.json", "install receipt")
        )
    except ValueError:
        return _blocked_item(
            catalog_key=catalog_key,
            bundle_path=bundle,
            issue_codes={"install_receipt_invalid"},
            plan=plan,
        )
    try:
        grant = DesktopLaunchGrant.from_dict(
            _read_json(bundle / "grant.json", "desktop launch grant")
        )
    except ValueError:
        return _blocked_item(
            catalog_key=catalog_key,
            bundle_path=bundle,
            issue_codes={"grant_invalid"},
            plan=plan,
        )

    issues: set[DesktopCatalogIssueCode] = set()
    if (
        Path(grant.bundle_path) != bundle
        or grant.app_id != plan.app_id
        or grant.app_version != plan.app_version
        or grant.desktop_app_plan_sha256 != plan.sha256()
        or grant.browser_session_plan_sha256 != browser.sha256()
        or grant.static_web_plan_sha256 != static.sha256()
        or grant.install_receipt_sha256 != install_receipt.sha256()
        or plan.browser_session_plan_sha256 != browser.sha256()
        or plan.static_web_plan_sha256 != static.sha256()
        or plan.install_receipt_sha256 != install_receipt.sha256()
        or plan.installed_tree_sha256 != install_receipt.installed_tree_sha256
        or browser.static_web_plan_sha256 != static.sha256()
    ):
        issues.add("binding_mismatch")

    entry = Path(grant.desktop_entry_path)
    if not applications_present:
        issues.add("desktop_entry_missing")
    elif entry.is_symlink():
        issues.add("desktop_entry_unsafe")
    elif not entry.exists():
        issues.add("desktop_entry_missing")
    elif not entry.is_file():
        issues.add("desktop_entry_unsafe")
    elif not _under_root(applications_root, entry):
        issues.add("desktop_entry_outside_root")
    else:
        entry = entry.resolve(strict=True)
        if entry.name != plan.desktop_entry_filename:
            issues.add("binding_mismatch")
        try:
            entry_digest = hashlib.sha256(entry.read_bytes()).hexdigest()
        except OSError:
            issues.add("desktop_entry_unsafe")
        else:
            if entry_digest != grant.desktop_entry_sha256:
                retained = False
                if retention_marker is not None:
                    try:
                        active_bundle = Path(retention_marker.active_bundle_path)
                        if (
                            Path(retention_marker.retained_bundle_path) == bundle
                            and retention_marker.retained_desktop_plan_sha256
                            == plan.sha256()
                            and retention_marker.retained_grant_sha256 == grant.sha256()
                            and active_bundle.parent == bundle.parent
                            and active_bundle.is_dir()
                            and not active_bundle.is_symlink()
                        ):
                            active_grant = DesktopLaunchGrant.from_dict(
                                _read_json(
                                    active_bundle / "grant.json",
                                    "active retained-marker grant",
                                )
                            )
                            retained = (
                                active_grant.sha256()
                                == retention_marker.active_grant_sha256
                                and Path(active_grant.bundle_path) == active_bundle
                                and active_grant.app_id == plan.app_id
                                and entry_digest == active_grant.desktop_entry_sha256
                            )
                    except (OSError, ValueError):
                        retained = False
                issues.add(
                    "retained_inactive"
                    if retained
                    else "desktop_entry_digest_mismatch"
                )

    try:
        current_plan = plan_desktop_app(
            browser.to_dict(),
            static.to_dict(),
            install_receipt.to_dict(),
            install_root=install_root,
        )
    except (OSError, ValueError):
        issues.add("installed_app_drift")
    else:
        if current_plan.sha256() != plan.sha256():
            issues.add("installed_app_drift")

    if issues:
        return _blocked_item(
            catalog_key=catalog_key,
            bundle_path=bundle,
            issue_codes=issues,
            plan=plan,
            grant=grant,
        )

    return DesktopCatalogItem(
        catalog_key=catalog_key,
        bundle_path=str(bundle),
        app_id=plan.app_id,
        app_version=plan.app_version,
        desktop_name=plan.desktop_name,
        desktop_icon=plan.desktop_icon,
        desktop_entry_path=grant.desktop_entry_path,
        desktop_app_plan_sha256=plan.sha256(),
        desktop_launch_grant_sha256=grant.sha256(),
        grant_status=grant.status,
        identity_verified=True,
        persistent_launch_grant_present=True,
        icon_asset_state="metadata_only",
        status="ready",
        issues=(),
    )


@dataclass(frozen=True)
class DesktopCatalogSnapshot:
    desktop_root: str
    applications_root: str
    install_root: str
    root_issues: tuple[DesktopCatalogRootIssue, ...]
    items: tuple[DesktopCatalogItem, ...]
    item_count: int
    ready_count: int
    blocked_count: int
    catalog_launch_authority: bool = False
    catalog_revoke_authority: bool = False
    schema_version: str = DESKTOP_CATALOG_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DESKTOP_CATALOG_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported desktop catalog schema: {self.schema_version}")
        for value, label in (
            (self.desktop_root, "catalog desktop_root"),
            (self.applications_root, "catalog applications_root"),
            (self.install_root, "catalog install_root"),
        ):
            if not Path(value).is_absolute():
                raise ValueError(f"{label} must be absolute")
        count_values = (self.item_count, self.ready_count, self.blocked_count)
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in count_values
        ):
            raise ValueError("desktop catalog counts must be nonnegative integers")
        if any(
            not isinstance(value, bool)
            for value in (
                self.catalog_launch_authority,
                self.catalog_revoke_authority,
            )
        ):
            raise ValueError("desktop catalog authority fields must be boolean")
        keys = tuple(item.catalog_key for item in self.items)
        if keys != tuple(sorted(keys)):
            raise ValueError("desktop catalog items must be sorted by catalog_key")
        if len(set(keys)) != len(keys):
            raise ValueError("desktop catalog items must have unique keys")
        root_keys = tuple((issue.relative_path, issue.code) for issue in self.root_issues)
        if root_keys != tuple(sorted(root_keys)):
            raise ValueError("desktop catalog root issues must be sorted")
        if self.item_count != len(self.items):
            raise ValueError("desktop catalog item_count mismatch")
        if self.ready_count != sum(item.status == "ready" for item in self.items):
            raise ValueError("desktop catalog ready_count mismatch")
        if self.blocked_count != sum(item.status == "blocked" for item in self.items):
            raise ValueError("desktop catalog blocked_count mismatch")
        if self.ready_count + self.blocked_count != self.item_count:
            raise ValueError("desktop catalog status counts do not cover all items")
        if self.catalog_launch_authority or self.catalog_revoke_authority:
            raise ValueError("desktop catalog snapshot does not grant action authority")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "desktop_root": self.desktop_root,
            "applications_root": self.applications_root,
            "install_root": self.install_root,
            "root_issues": [issue.to_dict() for issue in self.root_issues],
            "items": [item.to_dict() for item in self.items],
            "item_count": self.item_count,
            "ready_count": self.ready_count,
            "blocked_count": self.blocked_count,
            "catalog_launch_authority": self.catalog_launch_authority,
            "catalog_revoke_authority": self.catalog_revoke_authority,
        }

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["desktop_catalog_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> DesktopCatalogSnapshot:
        data = _mapping(value, "desktop catalog snapshot")
        expected = {
            "schema_version",
            "desktop_root",
            "applications_root",
            "install_root",
            "root_issues",
            "items",
            "item_count",
            "ready_count",
            "blocked_count",
            "catalog_launch_authority",
            "catalog_revoke_authority",
            "desktop_catalog_sha256",
        }
        if set(data) != expected:
            raise ValueError("desktop catalog snapshot contains missing or unknown fields")
        raw_items = data["items"]
        raw_root_issues = data["root_issues"]
        if not isinstance(raw_items, list) or not isinstance(raw_root_issues, list):
            raise ValueError("desktop catalog arrays are malformed")
        snapshot = cls(
            schema_version=data["schema_version"],
            desktop_root=_string(data["desktop_root"], "desktop_root", maximum=4096),
            applications_root=_string(
                data["applications_root"],
                "applications_root",
                maximum=4096,
            ),
            install_root=_string(data["install_root"], "install_root", maximum=4096),
            root_issues=tuple(
                DesktopCatalogRootIssue.from_dict(issue) for issue in raw_root_issues
            ),
            items=tuple(DesktopCatalogItem.from_dict(item) for item in raw_items),
            item_count=data["item_count"],
            ready_count=data["ready_count"],
            blocked_count=data["blocked_count"],
            catalog_launch_authority=data["catalog_launch_authority"],
            catalog_revoke_authority=data["catalog_revoke_authority"],
        )
        if data["desktop_catalog_sha256"] != snapshot.sha256():
            raise ValueError("desktop catalog digest does not match canonical snapshot")
        return snapshot


def snapshot_desktop_catalog(
    *,
    desktop_root: Path,
    applications_root: Path,
    install_root: Path,
) -> DesktopCatalogSnapshot:
    desktop, desktop_present = _root_path(
        desktop_root,
        "desktop app bundle root",
        allow_missing=True,
    )
    applications, applications_present = _root_path(
        applications_root,
        "desktop applications root",
        allow_missing=True,
    )
    install, _ = _root_path(
        install_root,
        "installed app root",
        allow_missing=True,
    )

    if not desktop_present:
        return DesktopCatalogSnapshot(
            desktop_root=str(desktop),
            applications_root=str(applications),
            install_root=str(install),
            root_issues=(),
            items=(),
            item_count=0,
            ready_count=0,
            blocked_count=0,
        )

    app_entries = sorted(desktop.iterdir(), key=lambda path: path.name)
    if len(app_entries) > _MAX_APP_DIRS:
        raise ValueError("desktop catalog exceeds maximum app directory count")

    items: list[DesktopCatalogItem] = []
    root_issues: list[DesktopCatalogRootIssue] = []
    bundle_count = 0

    for app_entry in app_entries:
        rel_app = app_entry.relative_to(desktop).as_posix()
        if app_entry.is_symlink():
            root_issues.append(
                DesktopCatalogRootIssue(
                    code="unsafe_app_directory",
                    relative_path=rel_app,
                )
            )
            continue
        if not app_entry.is_dir():
            root_issues.append(
                DesktopCatalogRootIssue(
                    code="unexpected_root_entry",
                    relative_path=rel_app,
                )
            )
            continue

        child_entries = sorted(app_entry.iterdir(), key=lambda path: path.name)
        retention_markers: dict[str, DesktopRetentionMarker] = {}
        bundle_entries: list[Path] = []
        for child in child_entries:
            rel_child = child.relative_to(desktop).as_posix()
            if child.is_file() and not child.is_symlink() and re.fullmatch(
                r"\.retained-[0-9a-f]{16}\.json",
                child.name,
            ):
                try:
                    parsed_marker = DesktopRetentionMarker.from_dict(
                        _read_json(child, "desktop retention marker")
                    )
                    retained_path = Path(parsed_marker.retained_bundle_path)
                    if (
                        parsed_marker.app_id != app_entry.name
                        or retained_path.parent != app_entry.resolve(strict=True)
                        or child.name
                        != f".retained-{parsed_marker.retained_desktop_plan_sha256[:16]}.json"
                    ):
                        raise ValueError("retention marker path/app binding mismatch")
                except (OSError, ValueError):
                    root_issues.append(
                        DesktopCatalogRootIssue(
                            code="invalid_retention_marker",
                            relative_path=rel_child,
                        )
                    )
                else:
                    retention_markers[str(retained_path)] = parsed_marker
                continue
            if not child.is_dir() and not child.is_symlink():
                root_issues.append(
                    DesktopCatalogRootIssue(
                        code="unexpected_app_entry",
                        relative_path=rel_child,
                    )
                )
                continue
            bundle_entries.append(child)

        for child in bundle_entries:
            bundle_count += 1
            if bundle_count > _MAX_BUNDLES:
                raise ValueError("desktop catalog exceeds maximum bundle count")
            retained_marker = retention_markers.get(str(child.resolve(strict=False)))
            items.append(
                _inspect_bundle(
                    child,
                    desktop_root=desktop,
                    applications_root=applications,
                    applications_present=applications_present,
                    install_root=install,
                    retention_marker=retained_marker,
                )
            )

    identity_groups: dict[tuple[str, str], list[int]] = {}
    for index, item in enumerate(items):
        if item.status == "ready" and item.app_id is not None and item.app_version is not None:
            identity_groups.setdefault((item.app_id, item.app_version), []).append(index)
    for indexes in identity_groups.values():
        if len(indexes) > 1:
            for index in indexes:
                item = items[index]
                items[index] = replace(
                    item,
                    status="blocked",
                    issues=(DesktopCatalogIssue(code="duplicate_app_identity"),),
                )

    items.sort(key=lambda item: item.catalog_key)
    root_issues.sort(key=lambda issue: (issue.relative_path, issue.code))
    return DesktopCatalogSnapshot(
        desktop_root=str(desktop),
        applications_root=str(applications),
        install_root=str(install),
        root_issues=tuple(root_issues),
        items=tuple(items),
        item_count=len(items),
        ready_count=sum(item.status == "ready" for item in items),
        blocked_count=sum(item.status == "blocked" for item in items),
    )


@dataclass(frozen=True)
class DesktopCatalogReview:
    desktop_catalog_sha256: str
    item_count: int
    ready_count: int
    blocked_count: int
    root_issue_count: int
    ready_app_ids: tuple[str, ...]
    catalog_launch_authority: bool
    catalog_revoke_authority: bool
    schema_version: str = DESKTOP_CATALOG_REVIEW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _sha256(self.desktop_catalog_sha256, "desktop_catalog_sha256")
        if self.ready_app_ids != tuple(sorted(self.ready_app_ids)):
            raise ValueError("ready_app_ids must be sorted")
        if self.catalog_launch_authority or self.catalog_revoke_authority:
            raise ValueError("desktop catalog review does not grant action authority")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["ready_app_ids"] = list(self.ready_app_ids)
        return result


def review_desktop_catalog(value: Any) -> DesktopCatalogReview:
    snapshot = DesktopCatalogSnapshot.from_dict(value)
    return DesktopCatalogReview(
        desktop_catalog_sha256=snapshot.sha256(),
        item_count=snapshot.item_count,
        ready_count=snapshot.ready_count,
        blocked_count=snapshot.blocked_count,
        root_issue_count=len(snapshot.root_issues),
        ready_app_ids=tuple(
            sorted(
                cast(str, item.app_id)
                for item in snapshot.items
                if item.status == "ready" and item.app_id is not None
            )
        ),
        catalog_launch_authority=False,
        catalog_revoke_authority=False,
    )


@dataclass(frozen=True)
class DesktopCatalogReceipt:
    receipt_id: str
    timestamp_utc: str
    desktop_catalog_sha256: str
    desktop_root: str
    applications_root: str
    install_root: str
    item_count: int
    ready_count: int
    blocked_count: int
    root_issue_count: int
    launch_authority: bool = False
    revoke_authority: bool = False
    schema_version: str = DESKTOP_CATALOG_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DESKTOP_CATALOG_RECEIPT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported desktop catalog receipt schema: {self.schema_version}")
        try:
            uuid.UUID(self.receipt_id)
        except ValueError as exc:
            raise ValueError("desktop catalog receipt_id must be a UUID") from exc
        parsed = datetime.fromisoformat(self.timestamp_utc)
        if parsed.tzinfo is None:
            raise ValueError("desktop catalog receipt timestamp must include timezone")
        _sha256(self.desktop_catalog_sha256, "desktop_catalog_sha256")
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in (
                self.item_count,
                self.ready_count,
                self.blocked_count,
                self.root_issue_count,
            )
        ):
            raise ValueError("desktop catalog receipt counts must be nonnegative integers")
        if self.ready_count + self.blocked_count != self.item_count:
            raise ValueError("desktop catalog receipt status counts do not match item_count")
        if any(
            not isinstance(value, bool)
            for value in (self.launch_authority, self.revoke_authority)
        ):
            raise ValueError("desktop catalog receipt authority fields must be boolean")
        if self.launch_authority or self.revoke_authority:
            raise ValueError("desktop catalog receipt does not grant action authority")

    def body_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["desktop_catalog_receipt_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> DesktopCatalogReceipt:
        data = _mapping(value, "desktop catalog receipt")
        expected = {
            "schema_version",
            "receipt_id",
            "timestamp_utc",
            "desktop_catalog_sha256",
            "desktop_root",
            "applications_root",
            "install_root",
            "item_count",
            "ready_count",
            "blocked_count",
            "root_issue_count",
            "launch_authority",
            "revoke_authority",
            "desktop_catalog_receipt_sha256",
        }
        if set(data) != expected:
            raise ValueError("desktop catalog receipt contains missing or unknown fields")
        receipt = cls(
            schema_version=data["schema_version"],
            receipt_id=_string(data["receipt_id"], "receipt_id", maximum=64),
            timestamp_utc=_string(data["timestamp_utc"], "timestamp_utc", maximum=128),
            desktop_catalog_sha256=_sha256(
                data["desktop_catalog_sha256"],
                "desktop_catalog_sha256",
            ),
            desktop_root=_string(data["desktop_root"], "desktop_root", maximum=4096),
            applications_root=_string(
                data["applications_root"],
                "applications_root",
                maximum=4096,
            ),
            install_root=_string(data["install_root"], "install_root", maximum=4096),
            item_count=data["item_count"],
            ready_count=data["ready_count"],
            blocked_count=data["blocked_count"],
            root_issue_count=data["root_issue_count"],
            launch_authority=data["launch_authority"],
            revoke_authority=data["revoke_authority"],
        )
        if data["desktop_catalog_receipt_sha256"] != receipt.sha256():
            raise ValueError("desktop catalog receipt digest does not match canonical receipt")
        return receipt


@dataclass(frozen=True)
class DesktopCatalogResult:
    snapshot: DesktopCatalogSnapshot
    receipt: DesktopCatalogReceipt

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot": self.snapshot.to_dict(),
            "receipt": self.receipt.to_dict(),
        }


class DesktopCatalogService:
    def snapshot(
        self,
        *,
        desktop_root: Path,
        applications_root: Path,
        install_root: Path,
    ) -> DesktopCatalogResult:
        snapshot = snapshot_desktop_catalog(
            desktop_root=desktop_root,
            applications_root=applications_root,
            install_root=install_root,
        )
        receipt = DesktopCatalogReceipt(
            receipt_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(UTC).isoformat(),
            desktop_catalog_sha256=snapshot.sha256(),
            desktop_root=snapshot.desktop_root,
            applications_root=snapshot.applications_root,
            install_root=snapshot.install_root,
            item_count=snapshot.item_count,
            ready_count=snapshot.ready_count,
            blocked_count=snapshot.blocked_count,
            root_issue_count=len(snapshot.root_issues),
            launch_authority=False,
            revoke_authority=False,
        )
        return DesktopCatalogResult(snapshot=snapshot, receipt=receipt)
