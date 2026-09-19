from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Mapping, cast

from .browser_session import BrowserSessionPlan, plan_browser_session
from .package_install import AppInstallReceipt
from .runtime import _verify_install
from .static_web import StaticWebAdapterPlan, plan_static_web_adapter
from .visible_browser import (
    VisibleBrowserSessionRequest,
    VisibleBrowserSessionResult,
    VisibleBrowserSessionService,
    WaylandSocketIdentity,
    inspect_wayland_socket,
    plan_visible_browser_session,
)

DESKTOP_APP_PLAN_SCHEMA_VERSION = "phios.desktop_app_plan.v0.1"
DESKTOP_APP_REVIEW_SCHEMA_VERSION = "phios.desktop_app_plan_review.v0.1"
DESKTOP_LAUNCH_GRANT_SCHEMA_VERSION = "phios.desktop_launch_grant.v0.1"
DESKTOP_LAUNCH_RECEIPT_SCHEMA_VERSION = "phios.desktop_launch_receipt.v0.1"
DESKTOP_REVOKE_RECEIPT_SCHEMA_VERSION = "phios.desktop_revoke_receipt.v0.1"

DesktopDisplaySelector = Literal["current_user_wayland_env"]
DesktopLaunchStatus = Literal["completed", "timed_out", "browser_failed"]
DesktopGrantStatus = Literal["enabled"]
DesktopRevokeStatus = Literal["revoked"]

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DISPLAY_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_DESKTOP_PERMISSIONS = (
    "browser.display.wayland",
    "browser.network.inherit",
    "browser.page.execute",
    "desktop.launch.persist",
)
_VISIBLE_PERMISSIONS = (
    "browser.display.wayland",
    "browser.network.inherit",
    "browser.page.execute",
)
_DEFAULT_DESKTOP_ICON = "phios-app"


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


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(_canonical_json(payload) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _path_root(path: Path, label: str) -> Path:
    expanded = path.expanduser()
    if expanded.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    expanded.mkdir(parents=True, exist_ok=True)
    resolved = expanded.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError(f"{label} must be a directory")
    return resolved


def _path_under(root: Path, candidate: Path, label: str) -> Path:
    if candidate.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    resolved = candidate.resolve(strict=True)
    if root != resolved and root not in resolved.parents:
        raise ValueError(f"{label} escaped configured root")
    return resolved


def _desktop_value(value: str) -> str:
    if any(ord(char) < 32 for char in value):
        raise ValueError("desktop entry values must not contain control characters")
    return value.replace("\\", "\\\\")


def _desktop_exec_quote(value: str) -> str:
    if any(ord(char) < 32 for char in value):
        raise ValueError("desktop Exec argument contains control characters")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace(chr(96), "\\" + chr(96)).replace("$", "\\$")
    return f'"{escaped}"'


def _desktop_filename(app_id: str) -> str:
    return f"phios-{app_id}.desktop"


@dataclass(frozen=True)
class DesktopAppPlan:
    app_id: str
    app_version: str
    desktop_name: str
    desktop_comment: str
    desktop_icon: str
    manifest_sha256: str
    install_receipt_sha256: str
    installed_tree_sha256: str
    static_web_plan_sha256: str
    browser_session_plan_sha256: str
    loopback_url: str
    browser_tool: str
    session_seconds: int
    readiness_timeout_ms: int
    display_selector: DesktopDisplaySelector
    desktop_entry_filename: str
    requested_desktop_permissions: tuple[str, ...]
    persistent_launch_grant_authority: bool = False
    display_authority: bool = False
    schema_version: str = DESKTOP_APP_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DESKTOP_APP_PLAN_SCHEMA_VERSION:
            raise ValueError(f"Unsupported desktop-app plan schema: {self.schema_version}")
        _string(self.app_id, "desktop app_id", maximum=64)
        _string(self.app_version, "desktop app_version", maximum=128)
        _string(self.desktop_name, "desktop name", maximum=96)
        if len(self.desktop_comment) > 512 or any(
            ord(char) < 32 for char in self.desktop_comment
        ):
            raise ValueError("desktop comment is invalid")
        if self.desktop_icon != _DEFAULT_DESKTOP_ICON:
            raise ValueError("v0.38 desktop icon is fixed to the generic PhiOS app icon")
        for value, label in (
            (self.manifest_sha256, "manifest_sha256"),
            (self.install_receipt_sha256, "install_receipt_sha256"),
            (self.installed_tree_sha256, "installed_tree_sha256"),
            (self.static_web_plan_sha256, "static_web_plan_sha256"),
            (self.browser_session_plan_sha256, "browser_session_plan_sha256"),
        ):
            _sha256(value, label)
        if (
            not self.loopback_url.startswith("http://127.0.0.1:")
            or not self.loopback_url.endswith("/")
        ):
            raise ValueError("desktop plan loopback URL must be reviewed 127.0.0.1 HTTP")
        if self.browser_tool not in {"chromium", "chromium-browser"}:
            raise ValueError("desktop plan browser tool must be Chromium-family")
        if not 1 <= self.session_seconds <= 300:
            raise ValueError("desktop session_seconds out of bounds")
        if not 250 <= self.readiness_timeout_ms <= 10_000:
            raise ValueError("desktop readiness_timeout_ms out of bounds")
        if self.display_selector != "current_user_wayland_env":
            raise ValueError("v0.38 supports only current_user_wayland_env")
        if self.desktop_entry_filename != _desktop_filename(self.app_id):
            raise ValueError("desktop entry filename does not match app identity")
        if self.requested_desktop_permissions != _DESKTOP_PERMISSIONS:
            raise ValueError("desktop permission set does not match the v0.38 contract")
        if self.persistent_launch_grant_authority is not False:
            raise ValueError("desktop plans do not themselves grant persistent launch authority")
        if self.display_authority is not False:
            raise ValueError("desktop plans do not themselves grant display authority")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app_id": self.app_id,
            "app_version": self.app_version,
            "desktop_name": self.desktop_name,
            "desktop_comment": self.desktop_comment,
            "desktop_icon": self.desktop_icon,
            "manifest_sha256": self.manifest_sha256,
            "install_receipt_sha256": self.install_receipt_sha256,
            "installed_tree_sha256": self.installed_tree_sha256,
            "static_web_plan_sha256": self.static_web_plan_sha256,
            "browser_session_plan_sha256": self.browser_session_plan_sha256,
            "loopback_url": self.loopback_url,
            "browser_tool": self.browser_tool,
            "session_seconds": self.session_seconds,
            "readiness_timeout_ms": self.readiness_timeout_ms,
            "display_selector": self.display_selector,
            "desktop_entry_filename": self.desktop_entry_filename,
            "requested_desktop_permissions": list(self.requested_desktop_permissions),
            "persistent_launch_grant_authority": self.persistent_launch_grant_authority,
            "display_authority": self.display_authority,
        }

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["desktop_app_plan_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> DesktopAppPlan:
        data = _mapping(value, "desktop app plan")
        expected = {
            "schema_version",
            "app_id",
            "app_version",
            "desktop_name",
            "desktop_comment",
            "desktop_icon",
            "manifest_sha256",
            "install_receipt_sha256",
            "installed_tree_sha256",
            "static_web_plan_sha256",
            "browser_session_plan_sha256",
            "loopback_url",
            "browser_tool",
            "session_seconds",
            "readiness_timeout_ms",
            "display_selector",
            "desktop_entry_filename",
            "requested_desktop_permissions",
            "persistent_launch_grant_authority",
            "display_authority",
            "desktop_app_plan_sha256",
        }
        if set(data) != expected:
            raise ValueError("desktop app plan contains missing or unknown fields")
        permissions = data["requested_desktop_permissions"]
        if not isinstance(permissions, list):
            raise ValueError("requested_desktop_permissions must be an array")
        comment = data["desktop_comment"]
        if not isinstance(comment, str):
            raise ValueError("desktop_comment must be a string")
        plan = cls(
            schema_version=data["schema_version"],
            app_id=_string(data["app_id"], "desktop app_id", maximum=64),
            app_version=_string(data["app_version"], "desktop app_version", maximum=128),
            desktop_name=_string(data["desktop_name"], "desktop name", maximum=96),
            desktop_comment=comment,
            desktop_icon=_string(data["desktop_icon"], "desktop icon", maximum=128),
            manifest_sha256=_sha256(data["manifest_sha256"], "manifest_sha256"),
            install_receipt_sha256=_sha256(
                data["install_receipt_sha256"],
                "install_receipt_sha256",
            ),
            installed_tree_sha256=_sha256(
                data["installed_tree_sha256"],
                "installed_tree_sha256",
            ),
            static_web_plan_sha256=_sha256(
                data["static_web_plan_sha256"],
                "static_web_plan_sha256",
            ),
            browser_session_plan_sha256=_sha256(
                data["browser_session_plan_sha256"],
                "browser_session_plan_sha256",
            ),
            loopback_url=_string(data["loopback_url"], "loopback_url", maximum=256),
            browser_tool=_string(data["browser_tool"], "browser_tool", maximum=64),
            session_seconds=data["session_seconds"],
            readiness_timeout_ms=data["readiness_timeout_ms"],
            display_selector=data["display_selector"],
            desktop_entry_filename=_string(
                data["desktop_entry_filename"],
                "desktop_entry_filename",
                maximum=128,
            ),
            requested_desktop_permissions=tuple(
                _string(item, "desktop permission", maximum=128) for item in permissions
            ),
            persistent_launch_grant_authority=data["persistent_launch_grant_authority"],
            display_authority=data["display_authority"],
        )
        if data["desktop_app_plan_sha256"] != plan.sha256():
            raise ValueError("desktop app plan digest does not match canonical plan")
        return plan


def plan_desktop_app(
    browser_session_plan_value: Any,
    static_web_plan_value: Any,
    install_receipt_value: Any,
    *,
    install_root: Path,
) -> DesktopAppPlan:
    browser = BrowserSessionPlan.from_dict(browser_session_plan_value)
    static = StaticWebAdapterPlan.from_dict(static_web_plan_value)
    receipt = AppInstallReceipt.from_dict(install_receipt_value)
    if browser.static_web_plan_sha256 != static.sha256():
        raise ValueError("browser plan does not bind supplied static-web plan")
    if receipt.sha256() != browser.install_receipt_sha256:
        raise ValueError("install receipt does not match browser plan")
    if receipt.sha256() != static.install_receipt_sha256:
        raise ValueError("install receipt does not match static-web plan")

    verified = _verify_install(receipt.to_dict(), install_root=install_root)
    current_static = plan_static_web_adapter(
        receipt.to_dict(),
        install_root=install_root,
        loopback_port=static.loopback_port,
        serve_seconds=static.serve_seconds,
    )
    if current_static.sha256() != static.sha256():
        raise ValueError("static-web install binding changed before desktop planning")
    current_browser = plan_browser_session(
        static.to_dict(),
        browser_tool=browser.browser_tool,
        session_seconds=browser.session_seconds,
        readiness_timeout_ms=browser.readiness_timeout_ms,
    )
    if current_browser.sha256() != browser.sha256():
        raise ValueError("browser-session binding changed before desktop planning")

    return DesktopAppPlan(
        app_id=verified.manifest.app_id,
        app_version=verified.manifest.version,
        desktop_name=verified.manifest.name,
        desktop_comment=verified.manifest.description,
        desktop_icon=_DEFAULT_DESKTOP_ICON,
        manifest_sha256=verified.manifest.sha256(),
        install_receipt_sha256=receipt.sha256(),
        installed_tree_sha256=receipt.installed_tree_sha256,
        static_web_plan_sha256=static.sha256(),
        browser_session_plan_sha256=browser.sha256(),
        loopback_url=browser.loopback_url,
        browser_tool=browser.browser_tool,
        session_seconds=browser.session_seconds,
        readiness_timeout_ms=browser.readiness_timeout_ms,
        display_selector="current_user_wayland_env",
        desktop_entry_filename=_desktop_filename(verified.manifest.app_id),
        requested_desktop_permissions=_DESKTOP_PERMISSIONS,
    )


@dataclass(frozen=True)
class DesktopAppReview:
    desktop_app_plan_sha256: str
    app_id: str
    app_version: str
    desktop_name: str
    desktop_icon: str
    install_receipt_sha256: str
    static_web_plan_sha256: str
    browser_session_plan_sha256: str
    display_selector: str
    desktop_entry_filename: str
    requested_desktop_permissions: tuple[str, ...]
    persistent_launch_grant_authority: bool
    display_authority: bool
    schema_version: str = DESKTOP_APP_REVIEW_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["requested_desktop_permissions"] = list(self.requested_desktop_permissions)
        return result


def review_desktop_app(value: Any) -> DesktopAppReview:
    plan = DesktopAppPlan.from_dict(value)
    return DesktopAppReview(
        desktop_app_plan_sha256=plan.sha256(),
        app_id=plan.app_id,
        app_version=plan.app_version,
        desktop_name=plan.desktop_name,
        desktop_icon=plan.desktop_icon,
        install_receipt_sha256=plan.install_receipt_sha256,
        static_web_plan_sha256=plan.static_web_plan_sha256,
        browser_session_plan_sha256=plan.browser_session_plan_sha256,
        display_selector=plan.display_selector,
        desktop_entry_filename=plan.desktop_entry_filename,
        requested_desktop_permissions=plan.requested_desktop_permissions,
        persistent_launch_grant_authority=plan.persistent_launch_grant_authority,
        display_authority=plan.display_authority,
    )


@dataclass(frozen=True)
class DesktopAppRegistrationRequest:
    plan: DesktopAppPlan
    browser_plan: BrowserSessionPlan
    static_plan: StaticWebAdapterPlan
    install_receipt: AppInstallReceipt
    approved_desktop_app_plan_sha256: str
    approved_desktop_permissions: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.approved_desktop_app_plan_sha256 != self.plan.sha256():
            raise ValueError("Approved desktop-app plan SHA-256 does not match canonical plan")
        if self.browser_plan.sha256() != self.plan.browser_session_plan_sha256:
            raise ValueError("desktop plan does not bind supplied browser plan")
        if self.static_plan.sha256() != self.plan.static_web_plan_sha256:
            raise ValueError("desktop plan does not bind supplied static-web plan")
        if self.browser_plan.static_web_plan_sha256 != self.static_plan.sha256():
            raise ValueError("browser plan does not bind supplied static-web plan")
        if self.install_receipt.sha256() != self.plan.install_receipt_sha256:
            raise ValueError("desktop plan does not bind supplied install receipt")
        approved = tuple(sorted(self.approved_desktop_permissions))
        if approved != self.approved_desktop_permissions:
            raise ValueError("approved desktop permissions must be sorted")
        if approved != self.plan.requested_desktop_permissions:
            raise ValueError("Approved desktop permissions must exactly match reviewed plan")

    @classmethod
    def from_payloads(
        cls,
        plan_value: Any,
        browser_plan_value: Any,
        static_plan_value: Any,
        install_receipt_value: Any,
        *,
        approved_desktop_app_plan_sha256: str,
        approved_desktop_permissions: tuple[str, ...],
    ) -> DesktopAppRegistrationRequest:
        return cls(
            plan=DesktopAppPlan.from_dict(plan_value),
            browser_plan=BrowserSessionPlan.from_dict(browser_plan_value),
            static_plan=StaticWebAdapterPlan.from_dict(static_plan_value),
            install_receipt=AppInstallReceipt.from_dict(install_receipt_value),
            approved_desktop_app_plan_sha256=_sha256(
                approved_desktop_app_plan_sha256,
                "approved_desktop_app_plan_sha256",
            ),
            approved_desktop_permissions=tuple(sorted(approved_desktop_permissions)),
        )


@dataclass(frozen=True)
class DesktopLaunchGrant:
    grant_id: str
    timestamp_utc: str
    app_id: str
    app_version: str
    desktop_app_plan_sha256: str
    browser_session_plan_sha256: str
    static_web_plan_sha256: str
    install_receipt_sha256: str
    approved_desktop_permissions: tuple[str, ...]
    display_selector: str
    bundle_path: str
    desktop_entry_path: str
    desktop_entry_sha256: str
    persistent_launch_grant_authority: bool
    status: DesktopGrantStatus = "enabled"
    schema_version: str = DESKTOP_LAUNCH_GRANT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DESKTOP_LAUNCH_GRANT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported desktop launch grant schema: {self.schema_version}")
        try:
            uuid.UUID(self.grant_id)
        except ValueError as exc:
            raise ValueError("desktop grant_id must be a UUID") from exc
        parsed = datetime.fromisoformat(self.timestamp_utc)
        if parsed.tzinfo is None:
            raise ValueError("desktop grant timestamp must include timezone")
        for value, label in (
            (self.desktop_app_plan_sha256, "desktop_app_plan_sha256"),
            (self.browser_session_plan_sha256, "browser_session_plan_sha256"),
            (self.static_web_plan_sha256, "static_web_plan_sha256"),
            (self.install_receipt_sha256, "install_receipt_sha256"),
            (self.desktop_entry_sha256, "desktop_entry_sha256"),
        ):
            _sha256(value, label)
        if self.approved_desktop_permissions != _DESKTOP_PERMISSIONS:
            raise ValueError("desktop grant permissions do not match v0.38")
        if self.display_selector != "current_user_wayland_env":
            raise ValueError("desktop grant has unsupported display selector")
        if not Path(self.bundle_path).is_absolute() or not Path(self.desktop_entry_path).is_absolute():
            raise ValueError("desktop grant paths must be absolute")
        if self.persistent_launch_grant_authority is not True:
            raise ValueError("desktop grant must record persistent launch authority")
        if self.status != "enabled":
            raise ValueError("unsupported desktop grant status")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "grant_id": self.grant_id,
            "timestamp_utc": self.timestamp_utc,
            "app_id": self.app_id,
            "app_version": self.app_version,
            "desktop_app_plan_sha256": self.desktop_app_plan_sha256,
            "browser_session_plan_sha256": self.browser_session_plan_sha256,
            "static_web_plan_sha256": self.static_web_plan_sha256,
            "install_receipt_sha256": self.install_receipt_sha256,
            "approved_desktop_permissions": list(self.approved_desktop_permissions),
            "display_selector": self.display_selector,
            "bundle_path": self.bundle_path,
            "desktop_entry_path": self.desktop_entry_path,
            "desktop_entry_sha256": self.desktop_entry_sha256,
            "persistent_launch_grant_authority": self.persistent_launch_grant_authority,
            "status": self.status,
        }

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["desktop_launch_grant_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> DesktopLaunchGrant:
        data = _mapping(value, "desktop launch grant")
        expected = {
            "schema_version",
            "grant_id",
            "timestamp_utc",
            "app_id",
            "app_version",
            "desktop_app_plan_sha256",
            "browser_session_plan_sha256",
            "static_web_plan_sha256",
            "install_receipt_sha256",
            "approved_desktop_permissions",
            "display_selector",
            "bundle_path",
            "desktop_entry_path",
            "desktop_entry_sha256",
            "persistent_launch_grant_authority",
            "status",
            "desktop_launch_grant_sha256",
        }
        if set(data) != expected:
            raise ValueError("desktop launch grant contains missing or unknown fields")
        permissions = data["approved_desktop_permissions"]
        if not isinstance(permissions, list):
            raise ValueError("approved_desktop_permissions must be an array")
        grant = cls(
            schema_version=data["schema_version"],
            grant_id=_string(data["grant_id"], "grant_id", maximum=64),
            timestamp_utc=_string(data["timestamp_utc"], "timestamp_utc", maximum=128),
            app_id=_string(data["app_id"], "app_id", maximum=64),
            app_version=_string(data["app_version"], "app_version", maximum=128),
            desktop_app_plan_sha256=_sha256(
                data["desktop_app_plan_sha256"],
                "desktop_app_plan_sha256",
            ),
            browser_session_plan_sha256=_sha256(
                data["browser_session_plan_sha256"],
                "browser_session_plan_sha256",
            ),
            static_web_plan_sha256=_sha256(
                data["static_web_plan_sha256"],
                "static_web_plan_sha256",
            ),
            install_receipt_sha256=_sha256(
                data["install_receipt_sha256"],
                "install_receipt_sha256",
            ),
            approved_desktop_permissions=tuple(
                _string(item, "desktop permission", maximum=128) for item in permissions
            ),
            display_selector=_string(
                data["display_selector"],
                "display_selector",
                maximum=64,
            ),
            bundle_path=_string(data["bundle_path"], "bundle_path", maximum=4096),
            desktop_entry_path=_string(
                data["desktop_entry_path"],
                "desktop_entry_path",
                maximum=4096,
            ),
            desktop_entry_sha256=_sha256(
                data["desktop_entry_sha256"],
                "desktop_entry_sha256",
            ),
            persistent_launch_grant_authority=data["persistent_launch_grant_authority"],
            status=data["status"],
        )
        if data["desktop_launch_grant_sha256"] != grant.sha256():
            raise ValueError("desktop launch grant digest does not match canonical grant")
        return grant


def _desktop_entry_content(plan: DesktopAppPlan, bundle_path: Path) -> str:
    exec_line = f"phi-app launch-desktop-bundle {_desktop_exec_quote(str(bundle_path))}"
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={_desktop_value(plan.desktop_name)}\n"
        f"Comment={_desktop_value(plan.desktop_comment)}\n"
        f"Icon={plan.desktop_icon}\n"
        f"Exec={exec_line}\n"
        "Terminal=false\n"
        "StartupNotify=true\n"
        "Categories=Utility;\n"
        "NoDisplay=false\n"
    )


@dataclass(frozen=True)
class DesktopAppInstallResult:
    grant: DesktopLaunchGrant
    bundle_path: str
    desktop_entry_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "grant": self.grant.to_dict(),
            "bundle_path": self.bundle_path,
            "desktop_entry_path": self.desktop_entry_path,
        }


class DesktopAppInstaller:
    def install(
        self,
        request: DesktopAppRegistrationRequest,
        *,
        install_root: Path,
        desktop_root: Path,
        applications_root: Path,
    ) -> DesktopAppInstallResult:
        current_plan = plan_desktop_app(
            request.browser_plan.to_dict(),
            request.static_plan.to_dict(),
            request.install_receipt.to_dict(),
            install_root=install_root,
        )
        if current_plan.sha256() != request.plan.sha256():
            raise ValueError("desktop app binding changed after review")

        bundles = _path_root(desktop_root, "desktop app bundle root")
        applications = _path_root(applications_root, "desktop applications root")
        final_bundle = bundles / request.plan.app_id / request.plan.sha256()[:16]
        if final_bundle.exists() or final_bundle.is_symlink():
            raise ValueError("desktop app bundle destination already exists")
        app_dir = final_bundle.parent
        if app_dir.is_symlink():
            raise ValueError("desktop app ID directory must not be a symlink")
        app_dir.mkdir(parents=True, exist_ok=True)
        app_dir = app_dir.resolve(strict=True)
        if bundles != app_dir and bundles not in app_dir.parents:
            raise ValueError("desktop app bundle path escaped configured root")

        entry_path = applications / request.plan.desktop_entry_filename
        if entry_path.exists() or entry_path.is_symlink():
            raise ValueError("desktop entry destination already exists")

        entry_content = _desktop_entry_content(request.plan, final_bundle)
        entry_sha = hashlib.sha256(entry_content.encode("utf-8")).hexdigest()
        grant = DesktopLaunchGrant(
            grant_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(UTC).isoformat(),
            app_id=request.plan.app_id,
            app_version=request.plan.app_version,
            desktop_app_plan_sha256=request.plan.sha256(),
            browser_session_plan_sha256=request.browser_plan.sha256(),
            static_web_plan_sha256=request.static_plan.sha256(),
            install_receipt_sha256=request.install_receipt.sha256(),
            approved_desktop_permissions=request.approved_desktop_permissions,
            display_selector=request.plan.display_selector,
            bundle_path=str(final_bundle),
            desktop_entry_path=str(entry_path.resolve(strict=False)),
            desktop_entry_sha256=entry_sha,
            persistent_launch_grant_authority=True,
        )

        staging = Path(
            tempfile.mkdtemp(prefix=f".install-{request.plan.app_id}-", dir=app_dir)
        ).resolve()
        try:
            _write_json_atomic(staging / "desktop-plan.json", request.plan.to_dict())
            _write_json_atomic(staging / "browser-plan.json", request.browser_plan.to_dict())
            _write_json_atomic(staging / "static-plan.json", request.static_plan.to_dict())
            _write_json_atomic(
                staging / "install-receipt.json",
                request.install_receipt.to_dict(),
            )
            _write_json_atomic(staging / "grant.json", grant.to_dict())
            staging.replace(final_bundle)
            try:
                _write_text_atomic(entry_path, entry_content)
            except OSError:
                shutil.rmtree(final_bundle, ignore_errors=True)
                raise
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)

        return DesktopAppInstallResult(
            grant=grant,
            bundle_path=str(final_bundle),
            desktop_entry_path=str(entry_path),
        )


def resolve_current_wayland_socket(
    env: Mapping[str, str] | None = None,
) -> WaylandSocketIdentity:
    source = os.environ if env is None else env
    runtime_value = source.get("XDG_RUNTIME_DIR")
    display_value = source.get("WAYLAND_DISPLAY")
    if not runtime_value:
        raise ValueError("XDG_RUNTIME_DIR is required for desktop Wayland launch")
    if not display_value:
        raise ValueError("WAYLAND_DISPLAY is required for desktop Wayland launch")
    if (
        not _DISPLAY_NAME_RE.fullmatch(display_value)
        or Path(display_value).name != display_value
    ):
        raise ValueError("WAYLAND_DISPLAY must be a safe socket basename")

    runtime = Path(runtime_value).expanduser()
    if not runtime.is_absolute():
        raise ValueError("XDG_RUNTIME_DIR must be absolute")
    if runtime.is_symlink():
        raise ValueError("XDG_RUNTIME_DIR must not be a symlink")
    try:
        metadata = runtime.stat()
    except OSError as exc:
        raise ValueError("XDG_RUNTIME_DIR is unavailable") from exc
    if not runtime.is_dir():
        raise ValueError("XDG_RUNTIME_DIR must be a directory")
    if metadata.st_uid != os.getuid():
        raise ValueError("XDG_RUNTIME_DIR must be owned by the current user")
    runtime = runtime.resolve(strict=True)
    return inspect_wayland_socket(runtime / display_value)


@dataclass(frozen=True)
class DesktopLaunchReceipt:
    receipt_id: str
    timestamp_utc: str
    app_id: str
    app_version: str
    desktop_launch_grant_sha256: str
    desktop_app_plan_sha256: str
    browser_session_plan_sha256: str
    static_web_plan_sha256: str
    install_receipt_sha256: str
    visible_browser_plan_sha256: str
    visible_browser_receipt_sha256: str
    wayland_socket: WaylandSocketIdentity
    approved_desktop_permissions: tuple[str, ...]
    status: DesktopLaunchStatus
    persistent_launch_grant_authority: bool
    display_authority: bool
    schema_version: str = DESKTOP_LAUNCH_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DESKTOP_LAUNCH_RECEIPT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported desktop launch receipt schema: {self.schema_version}")
        try:
            uuid.UUID(self.receipt_id)
        except ValueError as exc:
            raise ValueError("desktop launch receipt_id must be a UUID") from exc
        parsed = datetime.fromisoformat(self.timestamp_utc)
        if parsed.tzinfo is None:
            raise ValueError("desktop launch receipt timestamp must include timezone")
        for value, label in (
            (self.desktop_launch_grant_sha256, "desktop_launch_grant_sha256"),
            (self.desktop_app_plan_sha256, "desktop_app_plan_sha256"),
            (self.browser_session_plan_sha256, "browser_session_plan_sha256"),
            (self.static_web_plan_sha256, "static_web_plan_sha256"),
            (self.install_receipt_sha256, "install_receipt_sha256"),
            (self.visible_browser_plan_sha256, "visible_browser_plan_sha256"),
            (self.visible_browser_receipt_sha256, "visible_browser_receipt_sha256"),
        ):
            _sha256(value, label)
        if self.approved_desktop_permissions != _DESKTOP_PERMISSIONS:
            raise ValueError("desktop launch receipt permissions do not match v0.38")
        if self.status not in {"completed", "timed_out", "browser_failed"}:
            raise ValueError("unsupported desktop launch status")
        if not self.persistent_launch_grant_authority:
            raise ValueError("desktop launch receipt must record persistent grant authority")
        if not self.display_authority:
            raise ValueError("desktop launch receipt must record display authority")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "timestamp_utc": self.timestamp_utc,
            "app_id": self.app_id,
            "app_version": self.app_version,
            "desktop_launch_grant_sha256": self.desktop_launch_grant_sha256,
            "desktop_app_plan_sha256": self.desktop_app_plan_sha256,
            "browser_session_plan_sha256": self.browser_session_plan_sha256,
            "static_web_plan_sha256": self.static_web_plan_sha256,
            "install_receipt_sha256": self.install_receipt_sha256,
            "visible_browser_plan_sha256": self.visible_browser_plan_sha256,
            "visible_browser_receipt_sha256": self.visible_browser_receipt_sha256,
            "wayland_socket": self.wayland_socket.to_dict(),
            "approved_desktop_permissions": list(self.approved_desktop_permissions),
            "status": self.status,
            "persistent_launch_grant_authority": self.persistent_launch_grant_authority,
            "display_authority": self.display_authority,
        }

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["desktop_launch_receipt_sha256"] = self.sha256()
        return result


@dataclass(frozen=True)
class DesktopLaunchResult:
    receipt: DesktopLaunchReceipt
    visible_result: VisibleBrowserSessionResult
    receipt_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt": self.receipt.to_dict(),
            "visible_result": self.visible_result.to_dict(),
            "receipt_path": self.receipt_path,
        }


class DesktopAppLaunchService:
    def __init__(
        self,
        *,
        visible_service: VisibleBrowserSessionService | None = None,
    ) -> None:
        self.visible_service = visible_service or VisibleBrowserSessionService()

    @staticmethod
    def _load_json(path: Path, label: str) -> Any:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"{label} is unavailable or unsafe")
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError(f"{label} exceeds bounded size")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label} is invalid JSON") from exc

    def launch(
        self,
        bundle_path: Path,
        *,
        install_root: Path,
        session_root: Path,
        receipt_root: Path,
        env: Mapping[str, str] | None = None,
    ) -> DesktopLaunchResult:
        bundle = bundle_path.expanduser()
        if bundle.is_symlink():
            raise ValueError("desktop bundle path must not be a symlink")
        bundle = bundle.resolve(strict=True)
        if not bundle.is_dir():
            raise ValueError("desktop bundle path must be a directory")

        plan = DesktopAppPlan.from_dict(
            self._load_json(bundle / "desktop-plan.json", "desktop plan")
        )
        browser = BrowserSessionPlan.from_dict(
            self._load_json(bundle / "browser-plan.json", "browser plan")
        )
        static = StaticWebAdapterPlan.from_dict(
            self._load_json(bundle / "static-plan.json", "static plan")
        )
        install_receipt = AppInstallReceipt.from_dict(
            self._load_json(bundle / "install-receipt.json", "install receipt")
        )
        grant = DesktopLaunchGrant.from_dict(
            self._load_json(bundle / "grant.json", "desktop launch grant")
        )

        if Path(grant.bundle_path) != bundle:
            raise ValueError("desktop grant bundle path does not match launched bundle")
        if grant.desktop_app_plan_sha256 != plan.sha256():
            raise ValueError("desktop grant does not bind desktop plan")
        if grant.browser_session_plan_sha256 != browser.sha256():
            raise ValueError("desktop grant does not bind browser plan")
        if grant.static_web_plan_sha256 != static.sha256():
            raise ValueError("desktop grant does not bind static plan")
        if grant.install_receipt_sha256 != install_receipt.sha256():
            raise ValueError("desktop grant does not bind install receipt")

        entry = Path(grant.desktop_entry_path)
        if entry.is_symlink() or not entry.is_file():
            raise ValueError("desktop launcher entry is unavailable or unsafe")
        if hashlib.sha256(entry.read_bytes()).hexdigest() != grant.desktop_entry_sha256:
            raise ValueError("desktop launcher entry changed after grant")

        current_plan = plan_desktop_app(
            browser.to_dict(),
            static.to_dict(),
            install_receipt.to_dict(),
            install_root=install_root,
        )
        if current_plan.sha256() != plan.sha256():
            raise ValueError("desktop app binding changed after persistent grant")

        wayland = resolve_current_wayland_socket(env)
        visible_plan = plan_visible_browser_session(
            browser.to_dict(),
            wayland_socket_path=Path(wayland.host_path),
        )
        request = VisibleBrowserSessionRequest.from_payloads(
            visible_plan.to_dict(),
            browser.to_dict(),
            static.to_dict(),
            install_receipt.to_dict(),
            approved_visible_browser_plan_sha256=visible_plan.sha256(),
            approved_parent_browser_plan_sha256=browser.sha256(),
            approved_static_web_plan_sha256=static.sha256(),
            approved_browser_permissions=_VISIBLE_PERMISSIONS,
        )
        visible_result = self.visible_service.run(
            request,
            install_root=install_root,
            session_root=session_root,
            receipt_root=receipt_root,
        )

        status = cast(DesktopLaunchStatus, visible_result.receipt.status)
        receipt = DesktopLaunchReceipt(
            receipt_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(UTC).isoformat(),
            app_id=plan.app_id,
            app_version=plan.app_version,
            desktop_launch_grant_sha256=grant.sha256(),
            desktop_app_plan_sha256=plan.sha256(),
            browser_session_plan_sha256=browser.sha256(),
            static_web_plan_sha256=static.sha256(),
            install_receipt_sha256=install_receipt.sha256(),
            visible_browser_plan_sha256=visible_plan.sha256(),
            visible_browser_receipt_sha256=visible_result.receipt.sha256(),
            wayland_socket=wayland,
            approved_desktop_permissions=grant.approved_desktop_permissions,
            status=status,
            persistent_launch_grant_authority=True,
            display_authority=True,
        )
        receipts = _path_root(receipt_root, "desktop launch receipt root")
        receipt_path = receipts / f"desktop-launch-{receipt.receipt_id}.json"
        _write_json_atomic(receipt_path, receipt.to_dict())
        return DesktopLaunchResult(
            receipt=receipt,
            visible_result=visible_result,
            receipt_path=str(receipt_path),
        )


@dataclass(frozen=True)
class DesktopRevokeReceipt:
    receipt_id: str
    timestamp_utc: str
    app_id: str
    desktop_launch_grant_sha256: str
    bundle_path: str
    desktop_entry_path: str
    status: DesktopRevokeStatus = "revoked"
    schema_version: str = DESKTOP_REVOKE_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DESKTOP_REVOKE_RECEIPT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported desktop revoke receipt schema: {self.schema_version}")
        try:
            uuid.UUID(self.receipt_id)
        except ValueError as exc:
            raise ValueError("desktop revoke receipt_id must be a UUID") from exc
        parsed = datetime.fromisoformat(self.timestamp_utc)
        if parsed.tzinfo is None:
            raise ValueError("desktop revoke timestamp must include timezone")
        _sha256(self.desktop_launch_grant_sha256, "desktop_launch_grant_sha256")
        if self.status != "revoked":
            raise ValueError("unsupported desktop revoke status")

    def body_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["desktop_revoke_receipt_sha256"] = self.sha256()
        return result


class DesktopAppRevocationService:
    def revoke(
        self,
        bundle_path: Path,
        *,
        approved_desktop_launch_grant_sha256: str,
        desktop_root: Path,
        applications_root: Path,
        receipt_root: Path,
    ) -> DesktopRevokeReceipt:
        bundles = _path_root(desktop_root, "desktop app bundle root")
        applications = _path_root(applications_root, "desktop applications root")
        bundle = _path_under(bundles, bundle_path, "desktop bundle path")
        grant_path = bundle / "grant.json"
        if grant_path.is_symlink() or not grant_path.is_file():
            raise ValueError("desktop launch grant is unavailable")
        grant = DesktopLaunchGrant.from_dict(
            json.loads(grant_path.read_text(encoding="utf-8"))
        )
        if grant.sha256() != _sha256(
            approved_desktop_launch_grant_sha256,
            "approved_desktop_launch_grant_sha256",
        ):
            raise ValueError("Approved desktop grant SHA-256 does not match canonical grant")
        if Path(grant.bundle_path) != bundle:
            raise ValueError("desktop grant bundle path mismatch")
        entry = _path_under(
            applications,
            Path(grant.desktop_entry_path),
            "desktop entry path",
        )
        if hashlib.sha256(entry.read_bytes()).hexdigest() != grant.desktop_entry_sha256:
            raise ValueError("desktop entry changed after grant")

        entry.unlink()
        shutil.rmtree(bundle)
        parent = bundle.parent
        if parent != bundles:
            try:
                parent.rmdir()
            except OSError:
                pass

        receipt = DesktopRevokeReceipt(
            receipt_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(UTC).isoformat(),
            app_id=grant.app_id,
            desktop_launch_grant_sha256=grant.sha256(),
            bundle_path=str(bundle),
            desktop_entry_path=str(entry),
        )
        receipts = _path_root(receipt_root, "desktop revoke receipt root")
        _write_json_atomic(
            receipts / f"desktop-revoke-{receipt.receipt_id}.json",
            receipt.to_dict(),
        )
        return receipt
