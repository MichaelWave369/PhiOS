from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from .browser_session import BrowserSessionPlan
from .desktop_launch import (
    DesktopAppPlan,
    DesktopLaunchGrant,
    plan_desktop_app,
    render_desktop_entry,
)
from .package_install import AppInstallReceipt
from .static_web import StaticWebAdapterPlan

DESKTOP_UPDATE_PLAN_SCHEMA_VERSION = "phios.desktop_update_plan.v0.1"
DESKTOP_UPDATE_REVIEW_SCHEMA_VERSION = "phios.desktop_update_review.v0.1"
DESKTOP_UPDATE_RECEIPT_SCHEMA_VERSION = "phios.desktop_update_receipt.v0.1"
DESKTOP_ROLLBACK_PLAN_SCHEMA_VERSION = "phios.desktop_rollback_plan.v0.1"
DESKTOP_ROLLBACK_REVIEW_SCHEMA_VERSION = "phios.desktop_rollback_review.v0.1"
DESKTOP_ROLLBACK_RECEIPT_SCHEMA_VERSION = "phios.desktop_rollback_receipt.v0.1"
DESKTOP_RETENTION_MARKER_SCHEMA_VERSION = "phios.desktop_retention_marker.v0.1"

TransitionKind = Literal["update", "rollback"]
UpdateStatus = Literal["updated"]
RollbackStatus = Literal["rolled_back"]

_UPDATE_PERMISSIONS = ("desktop.update.switch",)
_ROLLBACK_PERMISSIONS = ("desktop.rollback.switch",)
_BUNDLE_FILES = {
    "desktop-plan.json",
    "browser-plan.json",
    "static-plan.json",
    "install-receipt.json",
    "grant.json",
}
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


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
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


def _root(path: Path, label: str, *, create: bool = False) -> Path:
    expanded = path.expanduser()
    if expanded.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    if create:
        expanded.mkdir(parents=True, exist_ok=True)
    resolved = expanded.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError(f"{label} must be a directory")
    return resolved


def _contained(root: Path, path: Path, label: str) -> Path:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    resolved = path.resolve(strict=True)
    if root != resolved and root not in resolved.parents:
        raise ValueError(f"{label} escaped configured root")
    return resolved


def _entry_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class _DesktopBundle:
    path: Path
    plan: DesktopAppPlan
    browser: BrowserSessionPlan
    static: StaticWebAdapterPlan
    install_receipt: AppInstallReceipt
    grant: DesktopLaunchGrant


def _load_bundle(bundle_path: Path, *, desktop_root: Path) -> _DesktopBundle:
    bundle = _contained(desktop_root, bundle_path, "desktop bundle")
    if not bundle.is_dir():
        raise ValueError("desktop bundle must be a directory")
    children = sorted(bundle.iterdir(), key=lambda path: path.name)
    if (
        {child.name for child in children} != _BUNDLE_FILES
        or any(child.is_symlink() or not child.is_file() for child in children)
    ):
        raise ValueError("desktop bundle layout does not match v0.38 contract")

    plan = DesktopAppPlan.from_dict(_read_json(bundle / "desktop-plan.json", "desktop plan"))
    browser = BrowserSessionPlan.from_dict(
        _read_json(bundle / "browser-plan.json", "browser plan")
    )
    static = StaticWebAdapterPlan.from_dict(
        _read_json(bundle / "static-plan.json", "static plan")
    )
    install_receipt = AppInstallReceipt.from_dict(
        _read_json(bundle / "install-receipt.json", "install receipt")
    )
    grant = DesktopLaunchGrant.from_dict(
        _read_json(bundle / "grant.json", "desktop launch grant")
    )

    if bundle.parent.name != plan.app_id:
        raise ValueError("desktop bundle app directory does not match plan app_id")
    if bundle.name != plan.sha256()[:16]:
        raise ValueError("desktop bundle directory does not match desktop-plan digest")
    if Path(grant.bundle_path) != bundle:
        raise ValueError("desktop grant bundle path mismatch")
    if grant.app_id != plan.app_id or grant.app_version != plan.app_version:
        raise ValueError("desktop grant app identity mismatch")
    if grant.desktop_app_plan_sha256 != plan.sha256():
        raise ValueError("desktop grant does not bind desktop plan")
    if grant.browser_session_plan_sha256 != browser.sha256():
        raise ValueError("desktop grant does not bind browser plan")
    if grant.static_web_plan_sha256 != static.sha256():
        raise ValueError("desktop grant does not bind static plan")
    if grant.install_receipt_sha256 != install_receipt.sha256():
        raise ValueError("desktop grant does not bind install receipt")
    if plan.browser_session_plan_sha256 != browser.sha256():
        raise ValueError("desktop plan does not bind browser plan")
    if plan.static_web_plan_sha256 != static.sha256():
        raise ValueError("desktop plan does not bind static plan")
    if plan.install_receipt_sha256 != install_receipt.sha256():
        raise ValueError("desktop plan does not bind install receipt")
    if browser.static_web_plan_sha256 != static.sha256():
        raise ValueError("browser plan does not bind static plan")
    return _DesktopBundle(
        path=bundle,
        plan=plan,
        browser=browser,
        static=static,
        install_receipt=install_receipt,
        grant=grant,
    )


def _verify_current_bundle(
    bundle: _DesktopBundle,
    *,
    install_root: Path,
    applications_root: Path,
    require_active_entry: bool,
) -> None:
    current = plan_desktop_app(
        bundle.browser.to_dict(),
        bundle.static.to_dict(),
        bundle.install_receipt.to_dict(),
        install_root=install_root,
    )
    if current.sha256() != bundle.plan.sha256():
        raise ValueError("desktop bundle installed ancestry changed")
    entry = Path(bundle.grant.desktop_entry_path)
    if not entry.is_absolute():
        raise ValueError("desktop entry path must be absolute")
    if not require_active_entry:
        return
    entry = _contained(applications_root, entry, "desktop entry")
    if not entry.is_file():
        raise ValueError("desktop entry must be a regular file")
    if entry.name != bundle.plan.desktop_entry_filename:
        raise ValueError("desktop entry filename does not match desktop plan")
    if _entry_digest(entry) != bundle.grant.desktop_entry_sha256:
        raise ValueError("desktop entry does not match active grant")


@dataclass(frozen=True)
class DesktopRetentionMarker:
    app_id: str
    retained_bundle_path: str
    retained_version: str
    retained_desktop_plan_sha256: str
    retained_grant_sha256: str
    active_bundle_path: str
    active_version: str
    active_desktop_plan_sha256: str
    active_grant_sha256: str
    transition_kind: TransitionKind
    transition_plan_sha256: str
    schema_version: str = DESKTOP_RETENTION_MARKER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DESKTOP_RETENTION_MARKER_SCHEMA_VERSION:
            raise ValueError(f"Unsupported retention marker schema: {self.schema_version}")
        _string(self.app_id, "retention app_id", maximum=64)
        _string(self.retained_version, "retained_version", maximum=128)
        _string(self.active_version, "active_version", maximum=128)
        if not Path(self.retained_bundle_path).is_absolute():
            raise ValueError("retained_bundle_path must be absolute")
        if not Path(self.active_bundle_path).is_absolute():
            raise ValueError("active_bundle_path must be absolute")
        for value, label in (
            (self.retained_desktop_plan_sha256, "retained_desktop_plan_sha256"),
            (self.retained_grant_sha256, "retained_grant_sha256"),
            (self.active_desktop_plan_sha256, "active_desktop_plan_sha256"),
            (self.active_grant_sha256, "active_grant_sha256"),
            (self.transition_plan_sha256, "transition_plan_sha256"),
        ):
            _sha256(value, label)
        if self.transition_kind not in {"update", "rollback"}:
            raise ValueError("unsupported retention marker transition kind")
        if self.retained_bundle_path == self.active_bundle_path:
            raise ValueError("retained and active bundles must differ")

    def body_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["desktop_retention_marker_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> DesktopRetentionMarker:
        data = _mapping(value, "desktop retention marker")
        expected = {
            "schema_version",
            "app_id",
            "retained_bundle_path",
            "retained_version",
            "retained_desktop_plan_sha256",
            "retained_grant_sha256",
            "active_bundle_path",
            "active_version",
            "active_desktop_plan_sha256",
            "active_grant_sha256",
            "transition_kind",
            "transition_plan_sha256",
            "desktop_retention_marker_sha256",
        }
        if set(data) != expected:
            raise ValueError("desktop retention marker contains missing or unknown fields")
        kind = _string(data["transition_kind"], "transition_kind", maximum=16)
        if kind not in {"update", "rollback"}:
            raise ValueError("unsupported retention marker transition kind")
        marker = cls(
            schema_version=data["schema_version"],
            app_id=_string(data["app_id"], "app_id", maximum=64),
            retained_bundle_path=_string(
                data["retained_bundle_path"],
                "retained_bundle_path",
                maximum=4096,
            ),
            retained_version=_string(
                data["retained_version"],
                "retained_version",
                maximum=128,
            ),
            retained_desktop_plan_sha256=_sha256(
                data["retained_desktop_plan_sha256"],
                "retained_desktop_plan_sha256",
            ),
            retained_grant_sha256=_sha256(
                data["retained_grant_sha256"],
                "retained_grant_sha256",
            ),
            active_bundle_path=_string(
                data["active_bundle_path"],
                "active_bundle_path",
                maximum=4096,
            ),
            active_version=_string(
                data["active_version"],
                "active_version",
                maximum=128,
            ),
            active_desktop_plan_sha256=_sha256(
                data["active_desktop_plan_sha256"],
                "active_desktop_plan_sha256",
            ),
            active_grant_sha256=_sha256(
                data["active_grant_sha256"],
                "active_grant_sha256",
            ),
            transition_kind=cast(TransitionKind, kind),
            transition_plan_sha256=_sha256(
                data["transition_plan_sha256"],
                "transition_plan_sha256",
            ),
        )
        if data["desktop_retention_marker_sha256"] != marker.sha256():
            raise ValueError("desktop retention marker digest does not match canonical marker")
        return marker


def retention_marker_path(desktop_root: Path, marker: DesktopRetentionMarker) -> Path:
    root = desktop_root.resolve(strict=True)
    app_dir = root / marker.app_id
    if app_dir.is_symlink() or not app_dir.is_dir():
        raise ValueError("retention marker app directory is unavailable or unsafe")
    name = f".retained-{marker.retained_desktop_plan_sha256[:16]}.json"
    return app_dir / name


@dataclass(frozen=True)
class DesktopUpdatePlan:
    app_id: str
    from_version: str
    to_version: str
    active_bundle_path: str
    candidate_bundle_path: str
    desktop_entry_path: str
    active_desktop_plan_sha256: str
    active_grant_sha256: str
    active_entry_sha256: str
    candidate_desktop_plan_sha256: str
    candidate_browser_plan_sha256: str
    candidate_static_plan_sha256: str
    candidate_install_receipt_sha256: str
    candidate_installed_tree_sha256: str
    candidate_entry_sha256: str
    candidate_desktop_permissions: tuple[str, ...]
    requested_update_permissions: tuple[str, ...]
    retain_previous_version: bool
    update_authority: bool = False
    rollback_authority: bool = False
    schema_version: str = DESKTOP_UPDATE_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DESKTOP_UPDATE_PLAN_SCHEMA_VERSION:
            raise ValueError(f"Unsupported desktop update plan schema: {self.schema_version}")
        _string(self.app_id, "update app_id", maximum=64)
        _string(self.from_version, "from_version", maximum=128)
        _string(self.to_version, "to_version", maximum=128)
        if self.from_version == self.to_version:
            raise ValueError("desktop update requires a different candidate version")
        for path_value, label in (
            (self.active_bundle_path, "active_bundle_path"),
            (self.candidate_bundle_path, "candidate_bundle_path"),
            (self.desktop_entry_path, "desktop_entry_path"),
        ):
            if not Path(path_value).is_absolute():
                raise ValueError(f"{label} must be absolute")
        for value, label in (
            (self.active_desktop_plan_sha256, "active_desktop_plan_sha256"),
            (self.active_grant_sha256, "active_grant_sha256"),
            (self.active_entry_sha256, "active_entry_sha256"),
            (self.candidate_desktop_plan_sha256, "candidate_desktop_plan_sha256"),
            (self.candidate_browser_plan_sha256, "candidate_browser_plan_sha256"),
            (self.candidate_static_plan_sha256, "candidate_static_plan_sha256"),
            (self.candidate_install_receipt_sha256, "candidate_install_receipt_sha256"),
            (self.candidate_installed_tree_sha256, "candidate_installed_tree_sha256"),
            (self.candidate_entry_sha256, "candidate_entry_sha256"),
        ):
            _sha256(value, label)
        if tuple(sorted(self.candidate_desktop_permissions)) != self.candidate_desktop_permissions:
            raise ValueError("candidate desktop permissions must be sorted")
        if self.requested_update_permissions != _UPDATE_PERMISSIONS:
            raise ValueError("desktop update permission set does not match v0.40")
        if self.retain_previous_version is not True:
            raise ValueError("v0.40 update must retain previous version")
        if self.update_authority or self.rollback_authority:
            raise ValueError("desktop update plan does not itself grant transition authority")

    def body_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["candidate_desktop_permissions"] = list(self.candidate_desktop_permissions)
        result["requested_update_permissions"] = list(self.requested_update_permissions)
        return result

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["desktop_update_plan_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> DesktopUpdatePlan:
        data = _mapping(value, "desktop update plan")
        expected = {
            "schema_version",
            "app_id",
            "from_version",
            "to_version",
            "active_bundle_path",
            "candidate_bundle_path",
            "desktop_entry_path",
            "active_desktop_plan_sha256",
            "active_grant_sha256",
            "active_entry_sha256",
            "candidate_desktop_plan_sha256",
            "candidate_browser_plan_sha256",
            "candidate_static_plan_sha256",
            "candidate_install_receipt_sha256",
            "candidate_installed_tree_sha256",
            "candidate_entry_sha256",
            "candidate_desktop_permissions",
            "requested_update_permissions",
            "retain_previous_version",
            "update_authority",
            "rollback_authority",
            "desktop_update_plan_sha256",
        }
        if set(data) != expected:
            raise ValueError("desktop update plan contains missing or unknown fields")
        candidate_permissions = data["candidate_desktop_permissions"]
        update_permissions = data["requested_update_permissions"]
        if not isinstance(candidate_permissions, list) or not isinstance(update_permissions, list):
            raise ValueError("desktop update permissions must be arrays")
        plan = cls(
            schema_version=data["schema_version"],
            app_id=_string(data["app_id"], "app_id", maximum=64),
            from_version=_string(data["from_version"], "from_version", maximum=128),
            to_version=_string(data["to_version"], "to_version", maximum=128),
            active_bundle_path=_string(
                data["active_bundle_path"],
                "active_bundle_path",
                maximum=4096,
            ),
            candidate_bundle_path=_string(
                data["candidate_bundle_path"],
                "candidate_bundle_path",
                maximum=4096,
            ),
            desktop_entry_path=_string(
                data["desktop_entry_path"],
                "desktop_entry_path",
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
            candidate_desktop_plan_sha256=_sha256(
                data["candidate_desktop_plan_sha256"],
                "candidate_desktop_plan_sha256",
            ),
            candidate_browser_plan_sha256=_sha256(
                data["candidate_browser_plan_sha256"],
                "candidate_browser_plan_sha256",
            ),
            candidate_static_plan_sha256=_sha256(
                data["candidate_static_plan_sha256"],
                "candidate_static_plan_sha256",
            ),
            candidate_install_receipt_sha256=_sha256(
                data["candidate_install_receipt_sha256"],
                "candidate_install_receipt_sha256",
            ),
            candidate_installed_tree_sha256=_sha256(
                data["candidate_installed_tree_sha256"],
                "candidate_installed_tree_sha256",
            ),
            candidate_entry_sha256=_sha256(
                data["candidate_entry_sha256"],
                "candidate_entry_sha256",
            ),
            candidate_desktop_permissions=tuple(
                _string(item, "candidate desktop permission", maximum=128)
                for item in candidate_permissions
            ),
            requested_update_permissions=tuple(
                _string(item, "update permission", maximum=128)
                for item in update_permissions
            ),
            retain_previous_version=data["retain_previous_version"],
            update_authority=data["update_authority"],
            rollback_authority=data["rollback_authority"],
        )
        if data["desktop_update_plan_sha256"] != plan.sha256():
            raise ValueError("desktop update plan digest does not match canonical plan")
        return plan


def plan_desktop_update(
    active_bundle_path: Path,
    candidate_browser_plan_value: Any,
    candidate_static_plan_value: Any,
    candidate_install_receipt_value: Any,
    *,
    install_root: Path,
    desktop_root: Path,
    applications_root: Path,
) -> DesktopUpdatePlan:
    desktop = _root(desktop_root, "desktop app bundle root")
    applications = _root(applications_root, "desktop applications root")
    installed = _root(install_root, "installed app root")
    active = _load_bundle(active_bundle_path, desktop_root=desktop)
    _verify_current_bundle(
        active,
        install_root=installed,
        applications_root=applications,
        require_active_entry=True,
    )

    candidate_browser = BrowserSessionPlan.from_dict(candidate_browser_plan_value)
    candidate_static = StaticWebAdapterPlan.from_dict(candidate_static_plan_value)
    candidate_install = AppInstallReceipt.from_dict(candidate_install_receipt_value)
    candidate_plan = plan_desktop_app(
        candidate_browser.to_dict(),
        candidate_static.to_dict(),
        candidate_install.to_dict(),
        install_root=installed,
    )
    if candidate_plan.app_id != active.plan.app_id:
        raise ValueError("candidate update app_id does not match active app")
    if candidate_plan.app_version == active.plan.app_version:
        raise ValueError("candidate update version must differ from active version")
    if candidate_plan.requested_desktop_permissions != active.grant.approved_desktop_permissions:
        raise ValueError("candidate desktop permissions differ from active persistent grant")

    candidate_bundle = desktop / candidate_plan.app_id / candidate_plan.sha256()[:16]
    if candidate_bundle.exists() or candidate_bundle.is_symlink():
        raise ValueError("candidate desktop bundle destination already exists")
    entry = _contained(
        applications,
        Path(active.grant.desktop_entry_path),
        "active desktop entry",
    )
    candidate_entry = render_desktop_entry(candidate_plan, candidate_bundle)
    candidate_entry_sha = hashlib.sha256(candidate_entry.encode("utf-8")).hexdigest()
    return DesktopUpdatePlan(
        app_id=active.plan.app_id,
        from_version=active.plan.app_version,
        to_version=candidate_plan.app_version,
        active_bundle_path=str(active.path),
        candidate_bundle_path=str(candidate_bundle),
        desktop_entry_path=str(entry),
        active_desktop_plan_sha256=active.plan.sha256(),
        active_grant_sha256=active.grant.sha256(),
        active_entry_sha256=active.grant.desktop_entry_sha256,
        candidate_desktop_plan_sha256=candidate_plan.sha256(),
        candidate_browser_plan_sha256=candidate_browser.sha256(),
        candidate_static_plan_sha256=candidate_static.sha256(),
        candidate_install_receipt_sha256=candidate_install.sha256(),
        candidate_installed_tree_sha256=candidate_install.installed_tree_sha256,
        candidate_entry_sha256=candidate_entry_sha,
        candidate_desktop_permissions=candidate_plan.requested_desktop_permissions,
        requested_update_permissions=_UPDATE_PERMISSIONS,
        retain_previous_version=True,
    )


@dataclass(frozen=True)
class DesktopUpdateReview:
    desktop_update_plan_sha256: str
    app_id: str
    from_version: str
    to_version: str
    active_grant_sha256: str
    candidate_desktop_plan_sha256: str
    active_entry_sha256: str
    candidate_entry_sha256: str
    candidate_desktop_permissions: tuple[str, ...]
    requested_update_permissions: tuple[str, ...]
    retain_previous_version: bool
    update_authority: bool
    rollback_authority: bool
    schema_version: str = DESKTOP_UPDATE_REVIEW_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["candidate_desktop_permissions"] = list(self.candidate_desktop_permissions)
        result["requested_update_permissions"] = list(self.requested_update_permissions)
        return result


def review_desktop_update(value: Any) -> DesktopUpdateReview:
    plan = DesktopUpdatePlan.from_dict(value)
    return DesktopUpdateReview(
        desktop_update_plan_sha256=plan.sha256(),
        app_id=plan.app_id,
        from_version=plan.from_version,
        to_version=plan.to_version,
        active_grant_sha256=plan.active_grant_sha256,
        candidate_desktop_plan_sha256=plan.candidate_desktop_plan_sha256,
        active_entry_sha256=plan.active_entry_sha256,
        candidate_entry_sha256=plan.candidate_entry_sha256,
        candidate_desktop_permissions=plan.candidate_desktop_permissions,
        requested_update_permissions=plan.requested_update_permissions,
        retain_previous_version=plan.retain_previous_version,
        update_authority=False,
        rollback_authority=False,
    )


@dataclass(frozen=True)
class DesktopUpdateRequest:
    plan: DesktopUpdatePlan
    candidate_browser: BrowserSessionPlan
    candidate_static: StaticWebAdapterPlan
    candidate_install_receipt: AppInstallReceipt
    approved_update_plan_sha256: str
    approved_active_grant_sha256: str
    approved_candidate_desktop_plan_sha256: str
    approved_update_permissions: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.approved_update_plan_sha256 != self.plan.sha256():
            raise ValueError("Approved update plan SHA-256 does not match canonical plan")
        if self.approved_active_grant_sha256 != self.plan.active_grant_sha256:
            raise ValueError("Approved active grant SHA-256 does not match update plan")
        if (
            self.approved_candidate_desktop_plan_sha256
            != self.plan.candidate_desktop_plan_sha256
        ):
            raise ValueError("Approved candidate desktop-plan SHA-256 does not match update plan")
        if self.candidate_browser.sha256() != self.plan.candidate_browser_plan_sha256:
            raise ValueError("update plan does not bind candidate browser plan")
        if self.candidate_static.sha256() != self.plan.candidate_static_plan_sha256:
            raise ValueError("update plan does not bind candidate static plan")
        if (
            self.candidate_install_receipt.sha256()
            != self.plan.candidate_install_receipt_sha256
        ):
            raise ValueError("update plan does not bind candidate install receipt")
        if self.approved_update_permissions != self.plan.requested_update_permissions:
            raise ValueError("Approved update permissions must exactly match reviewed plan")

    @classmethod
    def from_payloads(
        cls,
        plan_value: Any,
        candidate_browser_plan_value: Any,
        candidate_static_plan_value: Any,
        candidate_install_receipt_value: Any,
        *,
        approved_update_plan_sha256: str,
        approved_active_grant_sha256: str,
        approved_candidate_desktop_plan_sha256: str,
        approved_update_permissions: tuple[str, ...],
    ) -> DesktopUpdateRequest:
        return cls(
            plan=DesktopUpdatePlan.from_dict(plan_value),
            candidate_browser=BrowserSessionPlan.from_dict(candidate_browser_plan_value),
            candidate_static=StaticWebAdapterPlan.from_dict(candidate_static_plan_value),
            candidate_install_receipt=AppInstallReceipt.from_dict(
                candidate_install_receipt_value
            ),
            approved_update_plan_sha256=_sha256(
                approved_update_plan_sha256,
                "approved_update_plan_sha256",
            ),
            approved_active_grant_sha256=_sha256(
                approved_active_grant_sha256,
                "approved_active_grant_sha256",
            ),
            approved_candidate_desktop_plan_sha256=_sha256(
                approved_candidate_desktop_plan_sha256,
                "approved_candidate_desktop_plan_sha256",
            ),
            approved_update_permissions=tuple(sorted(approved_update_permissions)),
        )


@dataclass(frozen=True)
class DesktopUpdateReceipt:
    receipt_id: str
    timestamp_utc: str
    desktop_update_plan_sha256: str
    app_id: str
    from_version: str
    to_version: str
    previous_bundle_path: str
    previous_desktop_plan_sha256: str
    previous_grant_sha256: str
    previous_entry_sha256: str
    active_bundle_path: str
    active_desktop_plan_sha256: str
    active_grant_sha256: str
    active_entry_sha256: str
    retention_marker_path: str
    retention_marker_sha256: str
    update_switch_authority: bool
    rollback_authority: bool
    status: UpdateStatus = "updated"
    schema_version: str = DESKTOP_UPDATE_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DESKTOP_UPDATE_RECEIPT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported desktop update receipt schema: {self.schema_version}")
        try:
            uuid.UUID(self.receipt_id)
        except ValueError as exc:
            raise ValueError("desktop update receipt_id must be a UUID") from exc
        parsed = datetime.fromisoformat(self.timestamp_utc)
        if parsed.tzinfo is None:
            raise ValueError("desktop update timestamp must include timezone")
        for value, label in (
            (self.desktop_update_plan_sha256, "desktop_update_plan_sha256"),
            (self.previous_desktop_plan_sha256, "previous_desktop_plan_sha256"),
            (self.previous_grant_sha256, "previous_grant_sha256"),
            (self.previous_entry_sha256, "previous_entry_sha256"),
            (self.active_desktop_plan_sha256, "active_desktop_plan_sha256"),
            (self.active_grant_sha256, "active_grant_sha256"),
            (self.active_entry_sha256, "active_entry_sha256"),
            (self.retention_marker_sha256, "retention_marker_sha256"),
        ):
            _sha256(value, label)
        if any(
            not Path(value).is_absolute()
            for value in (
                self.previous_bundle_path,
                self.active_bundle_path,
                self.retention_marker_path,
            )
        ):
            raise ValueError("desktop update receipt paths must be absolute")
        if not isinstance(self.update_switch_authority, bool) or not isinstance(
            self.rollback_authority, bool
        ):
            raise ValueError("desktop update receipt authority fields must be boolean")
        if not self.update_switch_authority or self.rollback_authority:
            raise ValueError("desktop update receipt authority state is invalid")
        if self.status != "updated":
            raise ValueError("unsupported desktop update status")

    def body_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["desktop_update_receipt_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> DesktopUpdateReceipt:
        data = _mapping(value, "desktop update receipt")
        expected = {
            "schema_version",
            "receipt_id",
            "timestamp_utc",
            "desktop_update_plan_sha256",
            "app_id",
            "from_version",
            "to_version",
            "previous_bundle_path",
            "previous_desktop_plan_sha256",
            "previous_grant_sha256",
            "previous_entry_sha256",
            "active_bundle_path",
            "active_desktop_plan_sha256",
            "active_grant_sha256",
            "active_entry_sha256",
            "retention_marker_path",
            "retention_marker_sha256",
            "update_switch_authority",
            "rollback_authority",
            "status",
            "desktop_update_receipt_sha256",
        }
        if set(data) != expected:
            raise ValueError("desktop update receipt contains missing or unknown fields")
        receipt = cls(
            schema_version=data["schema_version"],
            receipt_id=_string(data["receipt_id"], "receipt_id", maximum=64),
            timestamp_utc=_string(data["timestamp_utc"], "timestamp_utc", maximum=128),
            desktop_update_plan_sha256=_sha256(
                data["desktop_update_plan_sha256"],
                "desktop_update_plan_sha256",
            ),
            app_id=_string(data["app_id"], "app_id", maximum=64),
            from_version=_string(data["from_version"], "from_version", maximum=128),
            to_version=_string(data["to_version"], "to_version", maximum=128),
            previous_bundle_path=_string(
                data["previous_bundle_path"],
                "previous_bundle_path",
                maximum=4096,
            ),
            previous_desktop_plan_sha256=_sha256(
                data["previous_desktop_plan_sha256"],
                "previous_desktop_plan_sha256",
            ),
            previous_grant_sha256=_sha256(
                data["previous_grant_sha256"],
                "previous_grant_sha256",
            ),
            previous_entry_sha256=_sha256(
                data["previous_entry_sha256"],
                "previous_entry_sha256",
            ),
            active_bundle_path=_string(
                data["active_bundle_path"],
                "active_bundle_path",
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
            retention_marker_path=_string(
                data["retention_marker_path"],
                "retention_marker_path",
                maximum=4096,
            ),
            retention_marker_sha256=_sha256(
                data["retention_marker_sha256"],
                "retention_marker_sha256",
            ),
            update_switch_authority=data["update_switch_authority"],
            rollback_authority=data["rollback_authority"],
            status=data["status"],
        )
        if data["desktop_update_receipt_sha256"] != receipt.sha256():
            raise ValueError("desktop update receipt digest does not match canonical receipt")
        return receipt


@dataclass(frozen=True)
class DesktopUpdateResult:
    receipt: DesktopUpdateReceipt
    candidate_grant: DesktopLaunchGrant
    receipt_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt": self.receipt.to_dict(),
            "candidate_grant": self.candidate_grant.to_dict(),
            "receipt_path": self.receipt_path,
        }


class DesktopUpdateService:
    def execute(
        self,
        request: DesktopUpdateRequest,
        *,
        install_root: Path,
        desktop_root: Path,
        applications_root: Path,
        receipt_root: Path,
    ) -> DesktopUpdateResult:
        current_plan = plan_desktop_update(
            Path(request.plan.active_bundle_path),
            request.candidate_browser.to_dict(),
            request.candidate_static.to_dict(),
            request.candidate_install_receipt.to_dict(),
            install_root=install_root,
            desktop_root=desktop_root,
            applications_root=applications_root,
        )
        if current_plan.sha256() != request.plan.sha256():
            raise ValueError("desktop update binding changed after review")

        desktop = _root(desktop_root, "desktop app bundle root")
        applications = _root(applications_root, "desktop applications root")
        installed = _root(install_root, "installed app root")
        receipts = _root(receipt_root, "desktop update receipt root", create=True)
        active = _load_bundle(Path(request.plan.active_bundle_path), desktop_root=desktop)
        _verify_current_bundle(
            active,
            install_root=installed,
            applications_root=applications,
            require_active_entry=True,
        )

        candidate_plan = plan_desktop_app(
            request.candidate_browser.to_dict(),
            request.candidate_static.to_dict(),
            request.candidate_install_receipt.to_dict(),
            install_root=installed,
        )
        candidate_bundle = Path(request.plan.candidate_bundle_path)
        app_dir = candidate_bundle.parent
        if app_dir.is_symlink() or not app_dir.is_dir():
            raise ValueError("candidate app directory is unavailable or unsafe")
        app_dir = app_dir.resolve(strict=True)
        if desktop != app_dir and desktop not in app_dir.parents:
            raise ValueError("candidate app directory escaped desktop root")
        if candidate_bundle.exists() or candidate_bundle.is_symlink():
            raise ValueError("candidate desktop bundle destination already exists")

        entry_path = _contained(
            applications,
            Path(request.plan.desktop_entry_path),
            "active desktop entry",
        )
        previous_entry_bytes = entry_path.read_bytes()
        if hashlib.sha256(previous_entry_bytes).hexdigest() != request.plan.active_entry_sha256:
            raise ValueError("active desktop entry changed after review")
        candidate_entry_text = render_desktop_entry(candidate_plan, candidate_bundle)
        if (
            hashlib.sha256(candidate_entry_text.encode("utf-8")).hexdigest()
            != request.plan.candidate_entry_sha256
        ):
            raise ValueError("candidate desktop entry no longer matches reviewed update plan")

        candidate_grant = DesktopLaunchGrant(
            grant_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(UTC).isoformat(),
            app_id=candidate_plan.app_id,
            app_version=candidate_plan.app_version,
            desktop_app_plan_sha256=candidate_plan.sha256(),
            browser_session_plan_sha256=request.candidate_browser.sha256(),
            static_web_plan_sha256=request.candidate_static.sha256(),
            install_receipt_sha256=request.candidate_install_receipt.sha256(),
            approved_desktop_permissions=candidate_plan.requested_desktop_permissions,
            display_selector=candidate_plan.display_selector,
            bundle_path=str(candidate_bundle),
            desktop_entry_path=str(entry_path),
            desktop_entry_sha256=request.plan.candidate_entry_sha256,
            persistent_launch_grant_authority=True,
        )

        staging = Path(
            tempfile.mkdtemp(prefix=f".update-{candidate_plan.app_id}-", dir=app_dir)
        ).resolve()
        marker: DesktopRetentionMarker | None = None
        marker_path: Path | None = None
        switched = False
        try:
            _write_json_atomic(staging / "desktop-plan.json", candidate_plan.to_dict())
            _write_json_atomic(
                staging / "browser-plan.json",
                request.candidate_browser.to_dict(),
            )
            _write_json_atomic(
                staging / "static-plan.json",
                request.candidate_static.to_dict(),
            )
            _write_json_atomic(
                staging / "install-receipt.json",
                request.candidate_install_receipt.to_dict(),
            )
            _write_json_atomic(staging / "grant.json", candidate_grant.to_dict())
            staging.replace(candidate_bundle)

            _write_text_atomic(entry_path, candidate_entry_text)
            switched = True
            if _entry_digest(entry_path) != request.plan.candidate_entry_sha256:
                raise OSError("candidate desktop entry verification failed after atomic switch")

            marker = DesktopRetentionMarker(
                app_id=active.plan.app_id,
                retained_bundle_path=str(active.path),
                retained_version=active.plan.app_version,
                retained_desktop_plan_sha256=active.plan.sha256(),
                retained_grant_sha256=active.grant.sha256(),
                active_bundle_path=str(candidate_bundle),
                active_version=candidate_plan.app_version,
                active_desktop_plan_sha256=candidate_plan.sha256(),
                active_grant_sha256=candidate_grant.sha256(),
                transition_kind="update",
                transition_plan_sha256=request.plan.sha256(),
            )
            marker_path = retention_marker_path(desktop, marker)
            if marker_path.exists() or marker_path.is_symlink():
                raise ValueError("retention marker destination already exists")
            _write_json_atomic(marker_path, marker.to_dict())

            receipt = DesktopUpdateReceipt(
                receipt_id=str(uuid.uuid4()),
                timestamp_utc=datetime.now(UTC).isoformat(),
                desktop_update_plan_sha256=request.plan.sha256(),
                app_id=active.plan.app_id,
                from_version=active.plan.app_version,
                to_version=candidate_plan.app_version,
                previous_bundle_path=str(active.path),
                previous_desktop_plan_sha256=active.plan.sha256(),
                previous_grant_sha256=active.grant.sha256(),
                previous_entry_sha256=active.grant.desktop_entry_sha256,
                active_bundle_path=str(candidate_bundle),
                active_desktop_plan_sha256=candidate_plan.sha256(),
                active_grant_sha256=candidate_grant.sha256(),
                active_entry_sha256=candidate_grant.desktop_entry_sha256,
                retention_marker_path=str(marker_path),
                retention_marker_sha256=marker.sha256(),
                update_switch_authority=True,
                rollback_authority=False,
            )
            receipt_path = receipts / f"desktop-update-{receipt.receipt_id}.json"
            _write_json_atomic(receipt_path, receipt.to_dict())
        except (OSError, ValueError):
            if marker_path is not None and marker_path.exists():
                marker_path.unlink()
            if switched:
                try:
                    temporary_text = previous_entry_bytes.decode("utf-8")
                    _write_text_atomic(entry_path, temporary_text)
                except (OSError, UnicodeDecodeError):
                    pass
            if candidate_bundle.exists():
                shutil.rmtree(candidate_bundle, ignore_errors=True)
            raise
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)

        return DesktopUpdateResult(
            receipt=receipt,
            candidate_grant=candidate_grant,
            receipt_path=str(receipt_path),
        )


@dataclass(frozen=True)
class DesktopRollbackPlan:
    desktop_update_receipt_sha256: str
    app_id: str
    from_version: str
    to_version: str
    active_bundle_path: str
    target_bundle_path: str
    desktop_entry_path: str
    active_grant_sha256: str
    target_grant_sha256: str
    active_entry_sha256: str
    rollback_entry_sha256: str
    retention_marker_path: str
    retention_marker_sha256: str
    post_rollback_marker_path: str
    requested_rollback_permissions: tuple[str, ...]
    rollback_authority: bool = False
    schema_version: str = DESKTOP_ROLLBACK_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DESKTOP_ROLLBACK_PLAN_SCHEMA_VERSION:
            raise ValueError(f"Unsupported desktop rollback plan schema: {self.schema_version}")
        for value, label in (
            (self.desktop_update_receipt_sha256, "desktop_update_receipt_sha256"),
            (self.active_grant_sha256, "active_grant_sha256"),
            (self.target_grant_sha256, "target_grant_sha256"),
            (self.active_entry_sha256, "active_entry_sha256"),
            (self.rollback_entry_sha256, "rollback_entry_sha256"),
            (self.retention_marker_sha256, "retention_marker_sha256"),
        ):
            _sha256(value, label)
        for value, label in (
            (self.active_bundle_path, "active_bundle_path"),
            (self.target_bundle_path, "target_bundle_path"),
            (self.desktop_entry_path, "desktop_entry_path"),
            (self.retention_marker_path, "retention_marker_path"),
            (self.post_rollback_marker_path, "post_rollback_marker_path"),
        ):
            if not Path(value).is_absolute():
                raise ValueError(f"{label} must be absolute")
        if self.requested_rollback_permissions != _ROLLBACK_PERMISSIONS:
            raise ValueError("desktop rollback permission set does not match v0.40")
        if self.rollback_authority:
            raise ValueError("desktop rollback plan does not itself grant rollback authority")

    def body_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["requested_rollback_permissions"] = list(
            self.requested_rollback_permissions
        )
        return result

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["desktop_rollback_plan_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> DesktopRollbackPlan:
        data = _mapping(value, "desktop rollback plan")
        expected = {
            "schema_version",
            "desktop_update_receipt_sha256",
            "app_id",
            "from_version",
            "to_version",
            "active_bundle_path",
            "target_bundle_path",
            "desktop_entry_path",
            "active_grant_sha256",
            "target_grant_sha256",
            "active_entry_sha256",
            "rollback_entry_sha256",
            "retention_marker_path",
            "retention_marker_sha256",
            "post_rollback_marker_path",
            "requested_rollback_permissions",
            "rollback_authority",
            "desktop_rollback_plan_sha256",
        }
        if set(data) != expected:
            raise ValueError("desktop rollback plan contains missing or unknown fields")
        permissions = data["requested_rollback_permissions"]
        if not isinstance(permissions, list):
            raise ValueError("requested_rollback_permissions must be an array")
        plan = cls(
            schema_version=data["schema_version"],
            desktop_update_receipt_sha256=_sha256(
                data["desktop_update_receipt_sha256"],
                "desktop_update_receipt_sha256",
            ),
            app_id=_string(data["app_id"], "app_id", maximum=64),
            from_version=_string(data["from_version"], "from_version", maximum=128),
            to_version=_string(data["to_version"], "to_version", maximum=128),
            active_bundle_path=_string(
                data["active_bundle_path"],
                "active_bundle_path",
                maximum=4096,
            ),
            target_bundle_path=_string(
                data["target_bundle_path"],
                "target_bundle_path",
                maximum=4096,
            ),
            desktop_entry_path=_string(
                data["desktop_entry_path"],
                "desktop_entry_path",
                maximum=4096,
            ),
            active_grant_sha256=_sha256(
                data["active_grant_sha256"],
                "active_grant_sha256",
            ),
            target_grant_sha256=_sha256(
                data["target_grant_sha256"],
                "target_grant_sha256",
            ),
            active_entry_sha256=_sha256(
                data["active_entry_sha256"],
                "active_entry_sha256",
            ),
            rollback_entry_sha256=_sha256(
                data["rollback_entry_sha256"],
                "rollback_entry_sha256",
            ),
            retention_marker_path=_string(
                data["retention_marker_path"],
                "retention_marker_path",
                maximum=4096,
            ),
            retention_marker_sha256=_sha256(
                data["retention_marker_sha256"],
                "retention_marker_sha256",
            ),
            post_rollback_marker_path=_string(
                data["post_rollback_marker_path"],
                "post_rollback_marker_path",
                maximum=4096,
            ),
            requested_rollback_permissions=tuple(
                _string(item, "rollback permission", maximum=128) for item in permissions
            ),
            rollback_authority=data["rollback_authority"],
        )
        if data["desktop_rollback_plan_sha256"] != plan.sha256():
            raise ValueError("desktop rollback plan digest does not match canonical plan")
        return plan


def plan_desktop_rollback(
    update_receipt_value: Any,
    *,
    install_root: Path,
    desktop_root: Path,
    applications_root: Path,
) -> DesktopRollbackPlan:
    receipt = DesktopUpdateReceipt.from_dict(update_receipt_value)
    desktop = _root(desktop_root, "desktop app bundle root")
    applications = _root(applications_root, "desktop applications root")
    installed = _root(install_root, "installed app root")

    active = _load_bundle(Path(receipt.active_bundle_path), desktop_root=desktop)
    target = _load_bundle(Path(receipt.previous_bundle_path), desktop_root=desktop)
    if active.plan.app_id != receipt.app_id or target.plan.app_id != receipt.app_id:
        raise ValueError("rollback bundle app identity mismatch")
    if active.grant.sha256() != receipt.active_grant_sha256:
        raise ValueError("rollback active grant does not match update receipt")
    if target.grant.sha256() != receipt.previous_grant_sha256:
        raise ValueError("rollback target grant does not match update receipt")
    _verify_current_bundle(
        active,
        install_root=installed,
        applications_root=applications,
        require_active_entry=True,
    )
    _verify_current_bundle(
        target,
        install_root=installed,
        applications_root=applications,
        require_active_entry=False,
    )

    marker_path = Path(receipt.retention_marker_path)
    marker = DesktopRetentionMarker.from_dict(
        _read_json(marker_path, "desktop retention marker")
    )
    if marker.sha256() != receipt.retention_marker_sha256:
        raise ValueError("retention marker does not match update receipt")
    if (
        Path(marker.retained_bundle_path) != target.path
        or marker.retained_grant_sha256 != target.grant.sha256()
        or Path(marker.active_bundle_path) != active.path
        or marker.active_grant_sha256 != active.grant.sha256()
    ):
        raise ValueError("retention marker bundle/grant binding mismatch")

    entry = _contained(
        applications,
        Path(active.grant.desktop_entry_path),
        "active desktop entry",
    )
    rollback_text = render_desktop_entry(target.plan, target.path)
    rollback_entry_sha = hashlib.sha256(rollback_text.encode("utf-8")).hexdigest()
    if rollback_entry_sha != target.grant.desktop_entry_sha256:
        raise ValueError("retained target launcher no longer matches target grant")

    post_marker_name = f".retained-{active.plan.sha256()[:16]}.json"
    post_marker_path = target.path.parent / post_marker_name
    return DesktopRollbackPlan(
        desktop_update_receipt_sha256=receipt.sha256(),
        app_id=receipt.app_id,
        from_version=active.plan.app_version,
        to_version=target.plan.app_version,
        active_bundle_path=str(active.path),
        target_bundle_path=str(target.path),
        desktop_entry_path=str(entry),
        active_grant_sha256=active.grant.sha256(),
        target_grant_sha256=target.grant.sha256(),
        active_entry_sha256=active.grant.desktop_entry_sha256,
        rollback_entry_sha256=rollback_entry_sha,
        retention_marker_path=str(marker_path),
        retention_marker_sha256=marker.sha256(),
        post_rollback_marker_path=str(post_marker_path),
        requested_rollback_permissions=_ROLLBACK_PERMISSIONS,
        rollback_authority=False,
    )


@dataclass(frozen=True)
class DesktopRollbackReview:
    desktop_rollback_plan_sha256: str
    desktop_update_receipt_sha256: str
    app_id: str
    from_version: str
    to_version: str
    active_grant_sha256: str
    target_grant_sha256: str
    requested_rollback_permissions: tuple[str, ...]
    rollback_authority: bool
    schema_version: str = DESKTOP_ROLLBACK_REVIEW_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["requested_rollback_permissions"] = list(
            self.requested_rollback_permissions
        )
        return result


def review_desktop_rollback(value: Any) -> DesktopRollbackReview:
    plan = DesktopRollbackPlan.from_dict(value)
    return DesktopRollbackReview(
        desktop_rollback_plan_sha256=plan.sha256(),
        desktop_update_receipt_sha256=plan.desktop_update_receipt_sha256,
        app_id=plan.app_id,
        from_version=plan.from_version,
        to_version=plan.to_version,
        active_grant_sha256=plan.active_grant_sha256,
        target_grant_sha256=plan.target_grant_sha256,
        requested_rollback_permissions=plan.requested_rollback_permissions,
        rollback_authority=False,
    )


@dataclass(frozen=True)
class DesktopRollbackRequest:
    plan: DesktopRollbackPlan
    update_receipt: DesktopUpdateReceipt
    approved_rollback_plan_sha256: str
    approved_active_grant_sha256: str
    approved_target_grant_sha256: str
    approved_rollback_permissions: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.approved_rollback_plan_sha256 != self.plan.sha256():
            raise ValueError("Approved rollback plan SHA-256 does not match canonical plan")
        if self.update_receipt.sha256() != self.plan.desktop_update_receipt_sha256:
            raise ValueError("rollback plan does not bind supplied update receipt")
        if self.approved_active_grant_sha256 != self.plan.active_grant_sha256:
            raise ValueError("Approved active grant SHA-256 does not match rollback plan")
        if self.approved_target_grant_sha256 != self.plan.target_grant_sha256:
            raise ValueError("Approved target grant SHA-256 does not match rollback plan")
        if self.approved_rollback_permissions != self.plan.requested_rollback_permissions:
            raise ValueError("Approved rollback permissions must exactly match reviewed plan")

    @classmethod
    def from_payloads(
        cls,
        plan_value: Any,
        update_receipt_value: Any,
        *,
        approved_rollback_plan_sha256: str,
        approved_active_grant_sha256: str,
        approved_target_grant_sha256: str,
        approved_rollback_permissions: tuple[str, ...],
    ) -> DesktopRollbackRequest:
        return cls(
            plan=DesktopRollbackPlan.from_dict(plan_value),
            update_receipt=DesktopUpdateReceipt.from_dict(update_receipt_value),
            approved_rollback_plan_sha256=_sha256(
                approved_rollback_plan_sha256,
                "approved_rollback_plan_sha256",
            ),
            approved_active_grant_sha256=_sha256(
                approved_active_grant_sha256,
                "approved_active_grant_sha256",
            ),
            approved_target_grant_sha256=_sha256(
                approved_target_grant_sha256,
                "approved_target_grant_sha256",
            ),
            approved_rollback_permissions=tuple(sorted(approved_rollback_permissions)),
        )


@dataclass(frozen=True)
class DesktopRollbackReceipt:
    receipt_id: str
    timestamp_utc: str
    desktop_rollback_plan_sha256: str
    desktop_update_receipt_sha256: str
    app_id: str
    from_version: str
    to_version: str
    active_bundle_path: str
    active_grant_sha256: str
    active_entry_sha256: str
    retained_bundle_path: str
    retained_grant_sha256: str
    retention_marker_path: str
    retention_marker_sha256: str
    rollback_switch_authority: bool
    update_authority: bool
    status: RollbackStatus = "rolled_back"
    schema_version: str = DESKTOP_ROLLBACK_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DESKTOP_ROLLBACK_RECEIPT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported desktop rollback receipt schema: {self.schema_version}")
        try:
            uuid.UUID(self.receipt_id)
        except ValueError as exc:
            raise ValueError("desktop rollback receipt_id must be a UUID") from exc
        parsed = datetime.fromisoformat(self.timestamp_utc)
        if parsed.tzinfo is None:
            raise ValueError("desktop rollback timestamp must include timezone")
        for value, label in (
            (self.desktop_rollback_plan_sha256, "desktop_rollback_plan_sha256"),
            (self.desktop_update_receipt_sha256, "desktop_update_receipt_sha256"),
            (self.active_grant_sha256, "active_grant_sha256"),
            (self.active_entry_sha256, "active_entry_sha256"),
            (self.retained_grant_sha256, "retained_grant_sha256"),
            (self.retention_marker_sha256, "retention_marker_sha256"),
        ):
            _sha256(value, label)
        if any(
            not Path(value).is_absolute()
            for value in (
                self.active_bundle_path,
                self.retained_bundle_path,
                self.retention_marker_path,
            )
        ):
            raise ValueError("desktop rollback receipt paths must be absolute")
        if not isinstance(self.rollback_switch_authority, bool) or not isinstance(
            self.update_authority, bool
        ):
            raise ValueError("desktop rollback receipt authority fields must be boolean")
        if not self.rollback_switch_authority or self.update_authority:
            raise ValueError("desktop rollback receipt authority state is invalid")
        if self.status != "rolled_back":
            raise ValueError("unsupported desktop rollback status")

    def body_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["desktop_rollback_receipt_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> DesktopRollbackReceipt:
        data = _mapping(value, "desktop rollback receipt")
        expected = {
            "schema_version",
            "receipt_id",
            "timestamp_utc",
            "desktop_rollback_plan_sha256",
            "desktop_update_receipt_sha256",
            "app_id",
            "from_version",
            "to_version",
            "active_bundle_path",
            "active_grant_sha256",
            "active_entry_sha256",
            "retained_bundle_path",
            "retained_grant_sha256",
            "retention_marker_path",
            "retention_marker_sha256",
            "rollback_switch_authority",
            "update_authority",
            "status",
            "desktop_rollback_receipt_sha256",
        }
        if set(data) != expected:
            raise ValueError("desktop rollback receipt contains missing or unknown fields")
        receipt = cls(
            schema_version=data["schema_version"],
            receipt_id=_string(data["receipt_id"], "receipt_id", maximum=64),
            timestamp_utc=_string(data["timestamp_utc"], "timestamp_utc", maximum=128),
            desktop_rollback_plan_sha256=_sha256(
                data["desktop_rollback_plan_sha256"],
                "desktop_rollback_plan_sha256",
            ),
            desktop_update_receipt_sha256=_sha256(
                data["desktop_update_receipt_sha256"],
                "desktop_update_receipt_sha256",
            ),
            app_id=_string(data["app_id"], "app_id", maximum=64),
            from_version=_string(data["from_version"], "from_version", maximum=128),
            to_version=_string(data["to_version"], "to_version", maximum=128),
            active_bundle_path=_string(
                data["active_bundle_path"],
                "active_bundle_path",
                maximum=4096,
            ),
            active_grant_sha256=_sha256(
                data["active_grant_sha256"],
                "active_grant_sha256",
            ),
            active_entry_sha256=_sha256(
                data["active_entry_sha256"],
                "active_entry_sha256",
            ),
            retained_bundle_path=_string(
                data["retained_bundle_path"],
                "retained_bundle_path",
                maximum=4096,
            ),
            retained_grant_sha256=_sha256(
                data["retained_grant_sha256"],
                "retained_grant_sha256",
            ),
            retention_marker_path=_string(
                data["retention_marker_path"],
                "retention_marker_path",
                maximum=4096,
            ),
            retention_marker_sha256=_sha256(
                data["retention_marker_sha256"],
                "retention_marker_sha256",
            ),
            rollback_switch_authority=data["rollback_switch_authority"],
            update_authority=data["update_authority"],
            status=data["status"],
        )
        if data["desktop_rollback_receipt_sha256"] != receipt.sha256():
            raise ValueError("desktop rollback receipt digest does not match canonical receipt")
        return receipt


@dataclass(frozen=True)
class DesktopRollbackResult:
    receipt: DesktopRollbackReceipt
    receipt_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt": self.receipt.to_dict(),
            "receipt_path": self.receipt_path,
        }


class DesktopRollbackService:
    def execute(
        self,
        request: DesktopRollbackRequest,
        *,
        install_root: Path,
        desktop_root: Path,
        applications_root: Path,
        receipt_root: Path,
    ) -> DesktopRollbackResult:
        current_plan = plan_desktop_rollback(
            request.update_receipt.to_dict(),
            install_root=install_root,
            desktop_root=desktop_root,
            applications_root=applications_root,
        )
        if current_plan.sha256() != request.plan.sha256():
            raise ValueError("desktop rollback binding changed after review")

        desktop = _root(desktop_root, "desktop app bundle root")
        applications = _root(applications_root, "desktop applications root")
        installed = _root(install_root, "installed app root")
        receipts = _root(receipt_root, "desktop rollback receipt root", create=True)
        active = _load_bundle(Path(request.plan.active_bundle_path), desktop_root=desktop)
        target = _load_bundle(Path(request.plan.target_bundle_path), desktop_root=desktop)
        _verify_current_bundle(
            active,
            install_root=installed,
            applications_root=applications,
            require_active_entry=True,
        )
        _verify_current_bundle(
            target,
            install_root=installed,
            applications_root=applications,
            require_active_entry=False,
        )
        entry_path = _contained(
            applications,
            Path(request.plan.desktop_entry_path),
            "active desktop entry",
        )
        active_entry_bytes = entry_path.read_bytes()
        if hashlib.sha256(active_entry_bytes).hexdigest() != request.plan.active_entry_sha256:
            raise ValueError("active desktop entry changed after rollback review")
        target_entry_text = render_desktop_entry(target.plan, target.path)
        if (
            hashlib.sha256(target_entry_text.encode("utf-8")).hexdigest()
            != request.plan.rollback_entry_sha256
        ):
            raise ValueError("rollback target entry changed after review")

        old_marker_path = Path(request.plan.retention_marker_path)
        old_marker_bytes = old_marker_path.read_bytes()
        old_marker = DesktopRetentionMarker.from_dict(
            json.loads(old_marker_bytes.decode("utf-8"))
        )
        if old_marker.sha256() != request.plan.retention_marker_sha256:
            raise ValueError("retention marker changed after rollback review")

        post_marker = DesktopRetentionMarker(
            app_id=active.plan.app_id,
            retained_bundle_path=str(active.path),
            retained_version=active.plan.app_version,
            retained_desktop_plan_sha256=active.plan.sha256(),
            retained_grant_sha256=active.grant.sha256(),
            active_bundle_path=str(target.path),
            active_version=target.plan.app_version,
            active_desktop_plan_sha256=target.plan.sha256(),
            active_grant_sha256=target.grant.sha256(),
            transition_kind="rollback",
            transition_plan_sha256=request.plan.sha256(),
        )
        post_marker_path = Path(request.plan.post_rollback_marker_path)
        if post_marker_path.exists() or post_marker_path.is_symlink():
            raise ValueError("post-rollback retention marker already exists")

        switched = False
        old_marker_removed = False
        try:
            _write_text_atomic(entry_path, target_entry_text)
            switched = True
            if _entry_digest(entry_path) != request.plan.rollback_entry_sha256:
                raise OSError("rollback desktop entry verification failed")
            old_marker_path.unlink()
            old_marker_removed = True
            _write_json_atomic(post_marker_path, post_marker.to_dict())

            receipt = DesktopRollbackReceipt(
                receipt_id=str(uuid.uuid4()),
                timestamp_utc=datetime.now(UTC).isoformat(),
                desktop_rollback_plan_sha256=request.plan.sha256(),
                desktop_update_receipt_sha256=request.update_receipt.sha256(),
                app_id=active.plan.app_id,
                from_version=active.plan.app_version,
                to_version=target.plan.app_version,
                active_bundle_path=str(target.path),
                active_grant_sha256=target.grant.sha256(),
                active_entry_sha256=target.grant.desktop_entry_sha256,
                retained_bundle_path=str(active.path),
                retained_grant_sha256=active.grant.sha256(),
                retention_marker_path=str(post_marker_path),
                retention_marker_sha256=post_marker.sha256(),
                rollback_switch_authority=True,
                update_authority=False,
            )
            receipt_path = receipts / f"desktop-rollback-{receipt.receipt_id}.json"
            _write_json_atomic(receipt_path, receipt.to_dict())
        except (OSError, ValueError):
            if post_marker_path.exists():
                post_marker_path.unlink()
            if old_marker_removed:
                try:
                    _write_json_atomic(old_marker_path, old_marker.to_dict())
                except OSError:
                    pass
            if switched:
                try:
                    _write_text_atomic(entry_path, active_entry_bytes.decode("utf-8"))
                except (OSError, UnicodeDecodeError):
                    pass
            raise

        return DesktopRollbackResult(receipt=receipt, receipt_path=str(receipt_path))
