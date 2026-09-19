from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Literal, Protocol, cast
from urllib.parse import urlsplit

from .browser_session import (
    BrowserSessionExecution,
    BrowserSessionPlan,
    BubblewrapBrowserSessionRunner,
    plan_browser_session,
)
from .build_execution import ToolIdentity
from .package_install import AppInstallReceipt
from .runtime import BubblewrapRuntimeRunner, RuntimeControlEvidence, RuntimeSandboxPolicy
from .sandbox import SandboxBackendIdentity
from .static_web import StaticWebAdapterPlan, plan_static_web_adapter

VISIBLE_BROWSER_PLAN_SCHEMA_VERSION = "phios.visible_browser_session_plan.v0.1"
VISIBLE_BROWSER_REVIEW_SCHEMA_VERSION = "phios.visible_browser_session_plan_review.v0.1"
VISIBLE_BROWSER_RECEIPT_SCHEMA_VERSION = "phios.visible_browser_session_receipt.v0.1"

VisibleBrowserStatus = Literal["completed", "timed_out", "browser_failed"]
DisplayTransport = Literal["wayland"]

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DISPLAY_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_BROWSER_TOOLS = {"chromium", "chromium-browser"}
_VISIBLE_PERMISSIONS = (
    "browser.display.wayland",
    "browser.network.inherit",
    "browser.page.execute",
)
_SANDBOX_WAYLAND_DIR = "/run/phios-wayland"


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


def _int(value: Any, label: str, *, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return value


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


@dataclass(frozen=True)
class WaylandSocketIdentity:
    host_path: str
    display_name: str
    device: int
    inode: int
    ctime_ns: int
    owner_uid: int
    owner_gid: int

    def __post_init__(self) -> None:
        path = Path(self.host_path)
        if not path.is_absolute():
            raise ValueError("Wayland socket path must be absolute")
        if not _DISPLAY_NAME_RE.fullmatch(self.display_name):
            raise ValueError("Wayland display name contains unsupported characters")
        if path.name != self.display_name:
            raise ValueError("Wayland display name must match socket basename")
        _int(self.device, "Wayland socket device", minimum=0, maximum=2**63 - 1)
        _int(self.inode, "Wayland socket inode", minimum=1, maximum=2**63 - 1)
        _int(self.ctime_ns, "Wayland socket ctime_ns", minimum=1, maximum=2**63 - 1)
        _int(self.owner_uid, "Wayland socket owner_uid", minimum=0, maximum=2**31 - 1)
        _int(self.owner_gid, "Wayland socket owner_gid", minimum=0, maximum=2**31 - 1)

    @property
    def sandbox_path(self) -> str:
        return f"{_SANDBOX_WAYLAND_DIR}/{self.display_name}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Any) -> WaylandSocketIdentity:
        data = _mapping(value, "Wayland socket identity")
        if set(data) != {
            "host_path",
            "display_name",
            "device",
            "inode",
            "ctime_ns",
            "owner_uid",
            "owner_gid",
        }:
            raise ValueError("Wayland socket identity contains missing or unknown fields")
        return cls(
            host_path=_string(data["host_path"], "Wayland host_path", maximum=4096),
            display_name=_string(data["display_name"], "Wayland display_name", maximum=128),
            device=data["device"],
            inode=data["inode"],
            ctime_ns=data["ctime_ns"],
            owner_uid=data["owner_uid"],
            owner_gid=data["owner_gid"],
        )


def inspect_wayland_socket(path_value: Path | str) -> WaylandSocketIdentity:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        raise ValueError("Wayland socket path must be absolute")
    if path.is_symlink():
        raise ValueError("Wayland socket path must not be a symlink")
    try:
        metadata = path.stat()
    except OSError as exc:
        raise ValueError("Wayland socket path is unavailable") from exc
    if not stat.S_ISSOCK(metadata.st_mode):
        raise ValueError("Wayland display path must be a Unix socket")
    if metadata.st_uid != os.getuid():
        raise ValueError("Wayland socket must be owned by the current user")
    resolved = path.resolve(strict=True)
    name = resolved.name
    if not _DISPLAY_NAME_RE.fullmatch(name):
        raise ValueError("Wayland socket basename contains unsupported characters")
    return WaylandSocketIdentity(
        host_path=str(resolved),
        display_name=name,
        device=metadata.st_dev,
        inode=metadata.st_ino,
        ctime_ns=metadata.st_ctime_ns,
        owner_uid=metadata.st_uid,
        owner_gid=metadata.st_gid,
    )


def _verify_wayland_socket(identity: WaylandSocketIdentity) -> Path:
    observed = inspect_wayland_socket(identity.host_path)
    if observed != identity:
        raise ValueError("Wayland display socket identity changed after review")
    return Path(observed.host_path)


def _validate_loopback_url(value: Any) -> str:
    url = _string(value, "visible browser loopback_url", maximum=256)
    parsed = urlsplit(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.path != "/"
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
        or parsed.port is None
        or not 1024 <= parsed.port <= 65535
    ):
        raise ValueError("visible browser loopback URL must be plain reviewed 127.0.0.1 HTTP")
    return url


def _visible_browser_argv(browser_tool: str, loopback_url: str) -> tuple[str, ...]:
    if browser_tool not in _BROWSER_TOOLS:
        raise ValueError("visible browser tool must be chromium or chromium-browser")
    return (
        browser_tool,
        "--ozone-platform=wayland",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-domain-reliability",
        "--disable-breakpad",
        "--disable-crash-reporter",
        "--disable-extensions",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--no-proxy-server",
        "--disable-features=Translate,OptimizationHints,MediaRouter",
        "--user-data-dir=/home/phios/browser-profile",
        f"--app={loopback_url}",
    )


@dataclass(frozen=True)
class VisibleBrowserSessionPlan:
    app_id: str
    app_version: str
    parent_browser_session_plan_sha256: str
    static_web_plan_sha256: str
    install_receipt_sha256: str
    installed_tree_sha256: str
    static_root_sha256: str
    loopback_url: str
    static_serve_seconds: int
    browser_family: str
    browser_tool: str
    browser_mode: str
    profile_mode: str
    display_transport: DisplayTransport
    wayland_socket: WaylandSocketIdentity
    requested_browser_permissions: tuple[str, ...]
    browser_argv: tuple[str, ...]
    policy: RuntimeSandboxPolicy
    session_seconds: int
    readiness_timeout_ms: int
    launch_authority: bool = False
    page_execution_authority: bool = False
    display_authority: bool = False
    persistent_profile_authority: bool = False
    host_home_authority: bool = False
    gpu_device_authority: bool = False
    x11_authority: bool = False
    schema_version: str = VISIBLE_BROWSER_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != VISIBLE_BROWSER_PLAN_SCHEMA_VERSION:
            raise ValueError(f"Unsupported visible-browser plan schema: {self.schema_version}")
        _string(self.app_id, "visible browser app_id", maximum=64)
        _string(self.app_version, "visible browser app_version", maximum=128)
        _sha256(
            self.parent_browser_session_plan_sha256,
            "parent_browser_session_plan_sha256",
        )
        _sha256(self.static_web_plan_sha256, "static_web_plan_sha256")
        _sha256(self.install_receipt_sha256, "install_receipt_sha256")
        _sha256(self.installed_tree_sha256, "installed_tree_sha256")
        _sha256(self.static_root_sha256, "static_root_sha256")
        _validate_loopback_url(self.loopback_url)
        _int(self.static_serve_seconds, "static_serve_seconds", minimum=1, maximum=3600)
        if self.browser_family != "chromium":
            raise ValueError("v0.37 supports only Chromium-family visible sessions")
        if self.browser_tool not in _BROWSER_TOOLS:
            raise ValueError("v0.37 browser_tool must be chromium or chromium-browser")
        if self.browser_mode != "visible_app_window":
            raise ValueError("v0.37 browser_mode must be visible_app_window")
        if self.profile_mode != "ephemeral":
            raise ValueError("v0.37 browser profile must remain ephemeral")
        if self.display_transport != "wayland":
            raise ValueError("v0.37 supports only Wayland display transport")
        if self.requested_browser_permissions != _VISIBLE_PERMISSIONS:
            raise ValueError("v0.37 browser permissions must match the fixed visible authority set")
        if self.browser_argv != _visible_browser_argv(self.browser_tool, self.loopback_url):
            raise ValueError("visible browser argv does not match the v0.37 contract")
        if self.policy.network_mode != "inherit":
            raise ValueError("visible browser requires host-network inheritance")
        _int(self.session_seconds, "session_seconds", minimum=1, maximum=300)
        _int(self.readiness_timeout_ms, "readiness_timeout_ms", minimum=250, maximum=10_000)
        readiness_seconds = (self.readiness_timeout_ms + 999) // 1000
        if self.session_seconds + readiness_seconds > self.static_serve_seconds:
            raise ValueError(
                "visible browser readiness + session exceeds reviewed static serve window"
            )
        if self.launch_authority is not False:
            raise ValueError("visible browser plan does not grant launch authority")
        if self.page_execution_authority is not False:
            raise ValueError("visible browser plan does not grant page execution authority")
        if self.display_authority is not False:
            raise ValueError("visible browser plan does not grant display authority")
        if self.persistent_profile_authority is not False:
            raise ValueError("visible browser plan never grants persistent profile authority")
        if self.host_home_authority is not False:
            raise ValueError("visible browser plan never grants host-home authority")
        if self.gpu_device_authority is not False:
            raise ValueError("v0.37 does not grant GPU device authority")
        if self.x11_authority is not False:
            raise ValueError("v0.37 does not grant X11 authority")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app_id": self.app_id,
            "app_version": self.app_version,
            "parent_browser_session_plan_sha256": self.parent_browser_session_plan_sha256,
            "static_web_plan_sha256": self.static_web_plan_sha256,
            "install_receipt_sha256": self.install_receipt_sha256,
            "installed_tree_sha256": self.installed_tree_sha256,
            "static_root_sha256": self.static_root_sha256,
            "loopback_url": self.loopback_url,
            "static_serve_seconds": self.static_serve_seconds,
            "browser_family": self.browser_family,
            "browser_tool": self.browser_tool,
            "browser_mode": self.browser_mode,
            "profile_mode": self.profile_mode,
            "display_transport": self.display_transport,
            "wayland_socket": self.wayland_socket.to_dict(),
            "requested_browser_permissions": list(self.requested_browser_permissions),
            "browser_argv": list(self.browser_argv),
            "policy": self.policy.to_dict(),
            "session_seconds": self.session_seconds,
            "readiness_timeout_ms": self.readiness_timeout_ms,
            "launch_authority": self.launch_authority,
            "page_execution_authority": self.page_execution_authority,
            "display_authority": self.display_authority,
            "persistent_profile_authority": self.persistent_profile_authority,
            "host_home_authority": self.host_home_authority,
            "gpu_device_authority": self.gpu_device_authority,
            "x11_authority": self.x11_authority,
        }

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["visible_browser_plan_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> VisibleBrowserSessionPlan:
        data = _mapping(value, "visible browser session plan")
        expected = {
            "schema_version",
            "app_id",
            "app_version",
            "parent_browser_session_plan_sha256",
            "static_web_plan_sha256",
            "install_receipt_sha256",
            "installed_tree_sha256",
            "static_root_sha256",
            "loopback_url",
            "static_serve_seconds",
            "browser_family",
            "browser_tool",
            "browser_mode",
            "profile_mode",
            "display_transport",
            "wayland_socket",
            "requested_browser_permissions",
            "browser_argv",
            "policy",
            "session_seconds",
            "readiness_timeout_ms",
            "launch_authority",
            "page_execution_authority",
            "display_authority",
            "persistent_profile_authority",
            "host_home_authority",
            "gpu_device_authority",
            "x11_authority",
            "visible_browser_plan_sha256",
        }
        if set(data) != expected:
            raise ValueError("visible browser plan contains missing or unknown fields")
        permissions = data["requested_browser_permissions"]
        argv = data["browser_argv"]
        if not isinstance(permissions, list) or not isinstance(argv, list):
            raise ValueError("visible browser permissions and argv must be arrays")
        plan = cls(
            schema_version=data["schema_version"],
            app_id=_string(data["app_id"], "visible browser app_id", maximum=64),
            app_version=_string(data["app_version"], "visible browser app_version", maximum=128),
            parent_browser_session_plan_sha256=_sha256(
                data["parent_browser_session_plan_sha256"],
                "parent_browser_session_plan_sha256",
            ),
            static_web_plan_sha256=_sha256(data["static_web_plan_sha256"], "static_web_plan_sha256"),
            install_receipt_sha256=_sha256(
                data["install_receipt_sha256"],
                "install_receipt_sha256",
            ),
            installed_tree_sha256=_sha256(
                data["installed_tree_sha256"],
                "installed_tree_sha256",
            ),
            static_root_sha256=_sha256(
                data["static_root_sha256"],
                "static_root_sha256",
            ),
            loopback_url=_validate_loopback_url(data["loopback_url"]),
            static_serve_seconds=data["static_serve_seconds"],
            browser_family=_string(data["browser_family"], "browser_family", maximum=64),
            browser_tool=_string(data["browser_tool"], "browser_tool", maximum=64),
            browser_mode=_string(data["browser_mode"], "browser_mode", maximum=64),
            profile_mode=_string(data["profile_mode"], "profile_mode", maximum=64),
            display_transport=data["display_transport"],
            wayland_socket=WaylandSocketIdentity.from_dict(data["wayland_socket"]),
            requested_browser_permissions=tuple(
                _string(item, "visible browser permission", maximum=128)
                for item in permissions
            ),
            browser_argv=tuple(
                _string(item, "visible browser argv item", maximum=1024) for item in argv
            ),
            policy=RuntimeSandboxPolicy.from_dict(data["policy"]),
            session_seconds=data["session_seconds"],
            readiness_timeout_ms=data["readiness_timeout_ms"],
            launch_authority=data["launch_authority"],
            page_execution_authority=data["page_execution_authority"],
            display_authority=data["display_authority"],
            persistent_profile_authority=data["persistent_profile_authority"],
            host_home_authority=data["host_home_authority"],
            gpu_device_authority=data["gpu_device_authority"],
            x11_authority=data["x11_authority"],
        )
        if data["visible_browser_plan_sha256"] != plan.sha256():
            raise ValueError("visible browser plan digest does not match canonical plan")
        return plan


def plan_visible_browser_session(
    browser_session_plan_value: Any,
    *,
    wayland_socket_path: Path,
) -> VisibleBrowserSessionPlan:
    parent = BrowserSessionPlan.from_dict(browser_session_plan_value)
    socket_identity = inspect_wayland_socket(wayland_socket_path)
    policy = RuntimeSandboxPolicy(
        network_mode="inherit",
        wall_clock_seconds=parent.session_seconds,
        cpu_seconds=min(parent.session_seconds, 300),
        address_space_bytes=4 * 1024 * 1024 * 1024,
        max_open_files=1024,
        max_file_size_bytes=128 * 1024 * 1024,
    )
    return VisibleBrowserSessionPlan(
        app_id=parent.app_id,
        app_version=parent.app_version,
        parent_browser_session_plan_sha256=parent.sha256(),
        static_web_plan_sha256=parent.static_web_plan_sha256,
        install_receipt_sha256=parent.install_receipt_sha256,
        installed_tree_sha256=parent.installed_tree_sha256,
        static_root_sha256=parent.static_root_sha256,
        loopback_url=parent.loopback_url,
        static_serve_seconds=parent.static_serve_seconds,
        browser_family=parent.browser_family,
        browser_tool=parent.browser_tool,
        browser_mode="visible_app_window",
        profile_mode="ephemeral",
        display_transport="wayland",
        wayland_socket=socket_identity,
        requested_browser_permissions=_VISIBLE_PERMISSIONS,
        browser_argv=_visible_browser_argv(parent.browser_tool, parent.loopback_url),
        policy=policy,
        session_seconds=parent.session_seconds,
        readiness_timeout_ms=parent.readiness_timeout_ms,
        launch_authority=False,
        page_execution_authority=False,
        display_authority=False,
        persistent_profile_authority=False,
        host_home_authority=False,
        gpu_device_authority=False,
        x11_authority=False,
    )


@dataclass(frozen=True)
class VisibleBrowserSessionReview:
    visible_browser_plan_sha256: str
    parent_browser_session_plan_sha256: str
    static_web_plan_sha256: str
    app_id: str
    app_version: str
    loopback_url: str
    browser_tool: str
    display_transport: str
    wayland_socket: WaylandSocketIdentity
    requested_browser_permissions: tuple[str, ...]
    session_seconds: int
    launch_authority: bool
    page_execution_authority: bool
    display_authority: bool
    persistent_profile_authority: bool
    host_home_authority: bool
    gpu_device_authority: bool
    x11_authority: bool
    schema_version: str = VISIBLE_BROWSER_REVIEW_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["wayland_socket"] = self.wayland_socket.to_dict()
        result["requested_browser_permissions"] = list(self.requested_browser_permissions)
        return result


def review_visible_browser_session(value: Any) -> VisibleBrowserSessionReview:
    plan = VisibleBrowserSessionPlan.from_dict(value)
    return VisibleBrowserSessionReview(
        visible_browser_plan_sha256=plan.sha256(),
        parent_browser_session_plan_sha256=plan.parent_browser_session_plan_sha256,
        static_web_plan_sha256=plan.static_web_plan_sha256,
        app_id=plan.app_id,
        app_version=plan.app_version,
        loopback_url=plan.loopback_url,
        browser_tool=plan.browser_tool,
        display_transport=plan.display_transport,
        wayland_socket=plan.wayland_socket,
        requested_browser_permissions=plan.requested_browser_permissions,
        session_seconds=plan.session_seconds,
        launch_authority=plan.launch_authority,
        page_execution_authority=plan.page_execution_authority,
        display_authority=plan.display_authority,
        persistent_profile_authority=plan.persistent_profile_authority,
        host_home_authority=plan.host_home_authority,
        gpu_device_authority=plan.gpu_device_authority,
        x11_authority=plan.x11_authority,
    )


@dataclass(frozen=True)
class VisibleBrowserSessionRequest:
    plan: VisibleBrowserSessionPlan
    parent_browser_plan: BrowserSessionPlan
    static_web_plan: StaticWebAdapterPlan
    install_receipt: AppInstallReceipt
    approved_visible_browser_plan_sha256: str
    approved_parent_browser_plan_sha256: str
    approved_static_web_plan_sha256: str
    approved_browser_permissions: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.approved_visible_browser_plan_sha256 != self.plan.sha256():
            raise ValueError("Approved visible-browser plan SHA-256 does not match canonical plan")
        if self.approved_parent_browser_plan_sha256 != self.parent_browser_plan.sha256():
            raise ValueError("Approved parent browser-session SHA-256 does not match plan")
        if self.approved_static_web_plan_sha256 != self.static_web_plan.sha256():
            raise ValueError("Approved static-web plan SHA-256 does not match plan")
        if self.plan.parent_browser_session_plan_sha256 != self.parent_browser_plan.sha256():
            raise ValueError("visible browser plan does not bind supplied parent browser plan")
        if self.plan.static_web_plan_sha256 != self.static_web_plan.sha256():
            raise ValueError("visible browser plan does not bind supplied static-web plan")
        if self.parent_browser_plan.static_web_plan_sha256 != self.static_web_plan.sha256():
            raise ValueError("parent browser plan does not bind supplied static-web plan")
        if self.install_receipt.sha256() != self.plan.install_receipt_sha256:
            raise ValueError("install receipt does not match visible browser plan")
        if self.install_receipt.sha256() != self.parent_browser_plan.install_receipt_sha256:
            raise ValueError("install receipt does not match parent browser plan")
        if self.install_receipt.sha256() != self.static_web_plan.install_receipt_sha256:
            raise ValueError("install receipt does not match static-web plan")
        approved = tuple(sorted(self.approved_browser_permissions))
        if approved != self.approved_browser_permissions:
            raise ValueError("approved visible-browser permissions must be sorted")
        if approved != self.plan.requested_browser_permissions:
            raise ValueError(
                "Approved visible-browser permissions must exactly match reviewed plan"
            )

    @classmethod
    def from_payloads(
        cls,
        plan_value: Any,
        parent_browser_plan_value: Any,
        static_web_plan_value: Any,
        install_receipt_value: Any,
        *,
        approved_visible_browser_plan_sha256: str,
        approved_parent_browser_plan_sha256: str,
        approved_static_web_plan_sha256: str,
        approved_browser_permissions: tuple[str, ...],
    ) -> VisibleBrowserSessionRequest:
        return cls(
            plan=VisibleBrowserSessionPlan.from_dict(plan_value),
            parent_browser_plan=BrowserSessionPlan.from_dict(parent_browser_plan_value),
            static_web_plan=StaticWebAdapterPlan.from_dict(static_web_plan_value),
            install_receipt=AppInstallReceipt.from_dict(install_receipt_value),
            approved_visible_browser_plan_sha256=_sha256(
                approved_visible_browser_plan_sha256,
                "approved_visible_browser_plan_sha256",
            ),
            approved_parent_browser_plan_sha256=_sha256(
                approved_parent_browser_plan_sha256,
                "approved_parent_browser_plan_sha256",
            ),
            approved_static_web_plan_sha256=_sha256(
                approved_static_web_plan_sha256,
                "approved_static_web_plan_sha256",
            ),
            approved_browser_permissions=tuple(sorted(approved_browser_permissions)),
        )


@dataclass(frozen=True)
class WaylandDisplayEvidence:
    transport: str
    host_socket_path: str
    host_socket_device: int
    host_socket_inode: int
    host_socket_ctime_ns: int
    host_socket_owner_uid: int
    host_socket_owner_gid: int
    sandbox_socket_path: str
    exact_socket_bind: bool
    host_runtime_directory_mounted: bool
    wayland_environment_set: bool
    display_authority_granted: bool
    gpu_device_authority: bool
    x11_authority: bool

    def __post_init__(self) -> None:
        bool_fields = (
            self.exact_socket_bind,
            self.host_runtime_directory_mounted,
            self.wayland_environment_set,
            self.display_authority_granted,
            self.gpu_device_authority,
            self.x11_authority,
        )
        if any(not isinstance(value, bool) for value in bool_fields):
            raise ValueError("Wayland display evidence authority fields must be boolean")
        if self.transport != "wayland":
            raise ValueError("visible display evidence must use Wayland")
        if not self.exact_socket_bind:
            raise ValueError("visible display evidence requires exact Wayland socket bind")
        if self.host_runtime_directory_mounted:
            raise ValueError("v0.37 must not mount the host runtime directory")
        if not self.wayland_environment_set:
            raise ValueError("visible display evidence requires Wayland environment")
        if not self.display_authority_granted:
            raise ValueError("visible display evidence must record granted display authority")
        if self.gpu_device_authority or self.x11_authority:
            raise ValueError("v0.37 display evidence must not grant GPU or X11 authority")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Any) -> WaylandDisplayEvidence:
        data = _mapping(value, "Wayland display evidence")
        if set(data) != set(cls.__dataclass_fields__):
            raise ValueError("Wayland display evidence contains missing or unknown fields")
        return cls(**data)


class WaylandBubblewrapRuntimeRunner(BubblewrapRuntimeRunner):
    def __init__(
        self,
        policy: RuntimeSandboxPolicy,
        *,
        payload_root: Path,
        wayland_socket: WaylandSocketIdentity,
    ) -> None:
        self.wayland_socket = wayland_socket
        _verify_wayland_socket(wayland_socket)
        super().__init__(
            policy,
            payload_root=payload_root,
            data_path=None,
        )

    def command_for(
        self,
        *,
        executable_path: str,
        argv_tail: tuple[str, ...],
    ) -> tuple[str, ...]:
        socket_path = _verify_wayland_socket(self.wayland_socket)
        command = list(
            super().command_for(
                executable_path=executable_path,
                argv_tail=argv_tail,
            )
        )
        payload_index = command.index(str(self.payload_root))
        if command[payload_index - 1] != "--ro-bind" or command[payload_index + 1] != "/app":
            raise ValueError("runtime command no longer exposes expected /app mount seam")
        command[payload_index - 1:payload_index - 1] = [
            "--dir",
            "/run",
            "--dir",
            _SANDBOX_WAYLAND_DIR,
            "--ro-bind",
            str(socket_path),
            self.wayland_socket.sandbox_path,
        ]
        _, prlimit = self._resolve_backend_tools()
        prlimit_index = command.index(prlimit)
        command[prlimit_index:prlimit_index] = [
            "--setenv",
            "WAYLAND_DISPLAY",
            self.wayland_socket.sandbox_path,
            "--setenv",
            "XDG_SESSION_TYPE",
            "wayland",
        ]
        return tuple(command)

    def display_evidence(self) -> WaylandDisplayEvidence:
        _verify_wayland_socket(self.wayland_socket)
        return WaylandDisplayEvidence(
            transport="wayland",
            host_socket_path=self.wayland_socket.host_path,
            host_socket_device=self.wayland_socket.device,
            host_socket_inode=self.wayland_socket.inode,
            host_socket_ctime_ns=self.wayland_socket.ctime_ns,
            host_socket_owner_uid=self.wayland_socket.owner_uid,
            host_socket_owner_gid=self.wayland_socket.owner_gid,
            sandbox_socket_path=self.wayland_socket.sandbox_path,
            exact_socket_bind=True,
            host_runtime_directory_mounted=False,
            wayland_environment_set=True,
            display_authority_granted=True,
            gpu_device_authority=False,
            x11_authority=False,
        )


@dataclass(frozen=True)
class VisibleBrowserExecution:
    browser: BrowserSessionExecution
    display: WaylandDisplayEvidence


class VisibleBrowserRunner(Protocol):
    def execute(
        self,
        static_plan: StaticWebAdapterPlan,
        visible_plan: VisibleBrowserSessionPlan,
    ) -> VisibleBrowserExecution: ...


class BubblewrapVisibleBrowserRunner:
    def __init__(
        self,
        *,
        server_policy: RuntimeSandboxPolicy,
        browser_policy: RuntimeSandboxPolicy,
        static_root: Path,
        browser_root: Path,
        wayland_socket: WaylandSocketIdentity,
    ) -> None:
        self.display_runner = WaylandBubblewrapRuntimeRunner(
            browser_policy,
            payload_root=browser_root,
            wayland_socket=wayland_socket,
        )
        self.coordinated = BubblewrapBrowserSessionRunner(
            server_policy=server_policy,
            browser_policy=browser_policy,
            static_root=static_root,
            browser_root=browser_root,
            browser_runtime_runner=self.display_runner,
        )

    def execute(
        self,
        static_plan: StaticWebAdapterPlan,
        visible_plan: VisibleBrowserSessionPlan,
    ) -> VisibleBrowserExecution:
        _verify_wayland_socket(visible_plan.wayland_socket)
        execution = self.coordinated.execute(static_plan, visible_plan)
        return VisibleBrowserExecution(
            browser=execution,
            display=self.display_runner.display_evidence(),
        )


VisibleBrowserRunnerFactory = Callable[
    [RuntimeSandboxPolicy, RuntimeSandboxPolicy, Path, Path, WaylandSocketIdentity],
    VisibleBrowserRunner,
]


def _default_runner_factory(
    server_policy: RuntimeSandboxPolicy,
    browser_policy: RuntimeSandboxPolicy,
    static_root: Path,
    browser_root: Path,
    wayland_socket: WaylandSocketIdentity,
) -> VisibleBrowserRunner:
    return BubblewrapVisibleBrowserRunner(
        server_policy=server_policy,
        browser_policy=browser_policy,
        static_root=static_root,
        browser_root=browser_root,
        wayland_socket=wayland_socket,
    )


@dataclass(frozen=True)
class VisibleBrowserSessionReceipt:
    receipt_id: str
    timestamp_utc: str
    app_id: str
    app_version: str
    visible_browser_plan_sha256: str
    parent_browser_session_plan_sha256: str
    static_web_plan_sha256: str
    install_receipt_sha256: str
    installed_tree_sha256: str
    static_root_sha256: str
    loopback_url: str
    approved_browser_permissions: tuple[str, ...]
    browser_tool: str
    browser_mode: str
    profile_mode: str
    display_transport: str
    display_evidence: WaylandDisplayEvidence
    browser_policy: RuntimeSandboxPolicy
    server_backend_identity: SandboxBackendIdentity
    server_tool_identity: ToolIdentity
    browser_backend_identity: SandboxBackendIdentity
    browser_tool_identity: ToolIdentity
    server_controls: RuntimeControlEvidence
    browser_controls: RuntimeControlEvidence
    readiness_ready: bool
    readiness_status_code: int
    readiness_attempts: int
    readiness_elapsed_ms: int
    server_terminated_by_session: bool
    server_exit_code: int
    server_duration_ms: int
    server_stdout_sha256: str
    server_stderr_sha256: str
    browser_exit_code: int
    browser_timed_out: bool
    browser_duration_ms: int
    browser_stdout_sha256: str
    browser_stderr_sha256: str
    status: VisibleBrowserStatus
    failure_reason: str | None
    page_execution_authority: bool
    browser_network_inherited: bool
    display_authority: bool
    persistent_profile_authority: bool
    host_home_authority: bool
    gpu_device_authority: bool
    x11_authority: bool
    schema_version: str = VISIBLE_BROWSER_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != VISIBLE_BROWSER_RECEIPT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported visible-browser receipt schema: {self.schema_version}")
        try:
            uuid.UUID(self.receipt_id)
        except ValueError as exc:
            raise ValueError("visible-browser receipt_id must be a UUID") from exc
        parsed = datetime.fromisoformat(self.timestamp_utc)
        if parsed.tzinfo is None:
            raise ValueError("visible-browser receipt timestamp must include timezone")
        for value, label in (
            (self.visible_browser_plan_sha256, "visible_browser_plan_sha256"),
            (self.parent_browser_session_plan_sha256, "parent_browser_session_plan_sha256"),
            (self.static_web_plan_sha256, "static_web_plan_sha256"),
            (self.install_receipt_sha256, "install_receipt_sha256"),
            (self.installed_tree_sha256, "installed_tree_sha256"),
            (self.static_root_sha256, "static_root_sha256"),
            (self.server_stdout_sha256, "server_stdout_sha256"),
            (self.server_stderr_sha256, "server_stderr_sha256"),
            (self.browser_stdout_sha256, "browser_stdout_sha256"),
            (self.browser_stderr_sha256, "browser_stderr_sha256"),
        ):
            _sha256(value, label)
        _validate_loopback_url(self.loopback_url)
        _string(self.app_id, "visible-browser app_id", maximum=64)
        _string(self.app_version, "visible-browser app_version", maximum=128)
        if self.approved_browser_permissions != _VISIBLE_PERMISSIONS:
            raise ValueError("visible-browser receipt permissions do not match v0.37 authority set")
        if self.browser_tool not in _BROWSER_TOOLS:
            raise ValueError("visible-browser receipt has unsupported browser tool")
        if self.browser_mode != "visible_app_window":
            raise ValueError("visible-browser receipt has unsupported browser mode")
        if self.profile_mode != "ephemeral":
            raise ValueError("visible-browser receipt must use ephemeral profile")
        if self.display_transport != "wayland":
            raise ValueError("visible-browser receipt must use Wayland")
        if self.display_evidence.transport != self.display_transport:
            raise ValueError("visible-browser display evidence transport mismatch")
        if self.browser_policy.network_mode != "inherit":
            raise ValueError("visible-browser receipt requires host-network browser policy")
        if not self.readiness_ready or self.readiness_status_code != 200:
            raise ValueError("visible-browser receipt requires successful static-server readiness")
        if not self.server_terminated_by_session:
            raise ValueError("visible-browser receipt requires owned server termination")
        if not self.browser_controls.host_network_inherited:
            raise ValueError("visible-browser receipt requires browser host-network inheritance")
        if self.browser_controls.network_namespace_enforced:
            raise ValueError("visible-browser receipt must not claim browser network namespace")
        if not self.browser_controls.private_home or not self.browser_controls.private_tmp:
            raise ValueError("visible-browser receipt requires private browser home/tmp")
        if self.browser_controls.persistent_data_writable_mount:
            raise ValueError("visible-browser receipt must not expose persistent app data")
        if not self.page_execution_authority:
            raise ValueError("visible-browser receipt must record page execution authority")
        if not self.browser_network_inherited:
            raise ValueError("visible-browser receipt must record browser network authority")
        if not self.display_authority:
            raise ValueError("visible-browser receipt must record display authority")
        if self.persistent_profile_authority or self.host_home_authority:
            raise ValueError("visible-browser receipt must not grant persistent profile/host home")
        if self.gpu_device_authority or self.x11_authority:
            raise ValueError("v0.37 receipt must not grant GPU or X11 authority")
        bool_fields = (
            self.readiness_ready,
            self.server_terminated_by_session,
            self.browser_timed_out,
            self.page_execution_authority,
            self.browser_network_inherited,
            self.display_authority,
            self.persistent_profile_authority,
            self.host_home_authority,
            self.gpu_device_authority,
            self.x11_authority,
        )
        if any(not isinstance(value, bool) for value in bool_fields):
            raise ValueError("visible-browser receipt authority/status flags must be boolean")
        _int(self.readiness_status_code, "readiness_status_code", minimum=100, maximum=599)
        _int(self.readiness_attempts, "readiness_attempts", minimum=1, maximum=10_000)
        _int(self.readiness_elapsed_ms, "readiness_elapsed_ms", minimum=0, maximum=60_000)
        _int(self.server_duration_ms, "server_duration_ms", minimum=0, maximum=86_400_000)
        _int(self.browser_duration_ms, "browser_duration_ms", minimum=0, maximum=86_400_000)
        if not isinstance(self.server_exit_code, int) or isinstance(self.server_exit_code, bool):
            raise ValueError("server_exit_code must be an integer")
        if not isinstance(self.browser_exit_code, int) or isinstance(self.browser_exit_code, bool):
            raise ValueError("browser_exit_code must be an integer")
        if self.status not in {"completed", "timed_out", "browser_failed"}:
            raise ValueError("unsupported visible-browser status")
        if self.status == "completed":
            if self.browser_timed_out or self.browser_exit_code != 0 or self.failure_reason is not None:
                raise ValueError("completed visible-browser receipt has inconsistent process state")
        elif self.status == "timed_out":
            if not self.browser_timed_out:
                raise ValueError("timed_out visible-browser receipt requires browser_timed_out=true")
        else:
            if self.browser_timed_out or self.browser_exit_code == 0 or self.failure_reason is None:
                raise ValueError("browser_failed receipt requires nonzero non-timeout failure")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "timestamp_utc": self.timestamp_utc,
            "app_id": self.app_id,
            "app_version": self.app_version,
            "visible_browser_plan_sha256": self.visible_browser_plan_sha256,
            "parent_browser_session_plan_sha256": self.parent_browser_session_plan_sha256,
            "static_web_plan_sha256": self.static_web_plan_sha256,
            "install_receipt_sha256": self.install_receipt_sha256,
            "installed_tree_sha256": self.installed_tree_sha256,
            "static_root_sha256": self.static_root_sha256,
            "loopback_url": self.loopback_url,
            "approved_browser_permissions": list(self.approved_browser_permissions),
            "browser_tool": self.browser_tool,
            "browser_mode": self.browser_mode,
            "profile_mode": self.profile_mode,
            "display_transport": self.display_transport,
            "display_evidence": self.display_evidence.to_dict(),
            "browser_policy": self.browser_policy.to_dict(),
            "server_backend_identity": self.server_backend_identity.to_dict(),
            "server_tool_identity": self.server_tool_identity.to_dict(),
            "browser_backend_identity": self.browser_backend_identity.to_dict(),
            "browser_tool_identity": self.browser_tool_identity.to_dict(),
            "server_controls": self.server_controls.to_dict(),
            "browser_controls": self.browser_controls.to_dict(),
            "readiness_ready": self.readiness_ready,
            "readiness_status_code": self.readiness_status_code,
            "readiness_attempts": self.readiness_attempts,
            "readiness_elapsed_ms": self.readiness_elapsed_ms,
            "server_terminated_by_session": self.server_terminated_by_session,
            "server_exit_code": self.server_exit_code,
            "server_duration_ms": self.server_duration_ms,
            "server_stdout_sha256": self.server_stdout_sha256,
            "server_stderr_sha256": self.server_stderr_sha256,
            "browser_exit_code": self.browser_exit_code,
            "browser_timed_out": self.browser_timed_out,
            "browser_duration_ms": self.browser_duration_ms,
            "browser_stdout_sha256": self.browser_stdout_sha256,
            "browser_stderr_sha256": self.browser_stderr_sha256,
            "status": self.status,
            "failure_reason": self.failure_reason,
            "page_execution_authority": self.page_execution_authority,
            "browser_network_inherited": self.browser_network_inherited,
            "display_authority": self.display_authority,
            "persistent_profile_authority": self.persistent_profile_authority,
            "host_home_authority": self.host_home_authority,
            "gpu_device_authority": self.gpu_device_authority,
            "x11_authority": self.x11_authority,
        }

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["visible_browser_receipt_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> VisibleBrowserSessionReceipt:
        data = _mapping(value, "visible browser session receipt")
        expected = {
            "schema_version",
            "receipt_id",
            "timestamp_utc",
            "app_id",
            "app_version",
            "visible_browser_plan_sha256",
            "parent_browser_session_plan_sha256",
            "static_web_plan_sha256",
            "install_receipt_sha256",
            "installed_tree_sha256",
            "static_root_sha256",
            "loopback_url",
            "approved_browser_permissions",
            "browser_tool",
            "browser_mode",
            "profile_mode",
            "display_transport",
            "display_evidence",
            "browser_policy",
            "server_backend_identity",
            "server_tool_identity",
            "browser_backend_identity",
            "browser_tool_identity",
            "server_controls",
            "browser_controls",
            "readiness_ready",
            "readiness_status_code",
            "readiness_attempts",
            "readiness_elapsed_ms",
            "server_terminated_by_session",
            "server_exit_code",
            "server_duration_ms",
            "server_stdout_sha256",
            "server_stderr_sha256",
            "browser_exit_code",
            "browser_timed_out",
            "browser_duration_ms",
            "browser_stdout_sha256",
            "browser_stderr_sha256",
            "status",
            "failure_reason",
            "page_execution_authority",
            "browser_network_inherited",
            "display_authority",
            "persistent_profile_authority",
            "host_home_authority",
            "gpu_device_authority",
            "x11_authority",
            "visible_browser_receipt_sha256",
        }
        if set(data) != expected:
            raise ValueError("visible browser receipt contains missing or unknown fields")
        permissions = data["approved_browser_permissions"]
        if not isinstance(permissions, list):
            raise ValueError("approved_browser_permissions must be an array")

        def backend(value: Any, label: str) -> SandboxBackendIdentity:
            item = _mapping(value, label)
            if set(item) != {
                "backend",
                "executable_path",
                "version",
                "version_output_sha256",
                "platform_system",
                "platform_machine",
            }:
                raise ValueError(f"{label} contains missing or unknown fields")
            return SandboxBackendIdentity(
                backend=_string(item["backend"], f"{label} backend", maximum=64),
                executable_path=_string(
                    item["executable_path"],
                    f"{label} executable_path",
                    maximum=4096,
                ),
                version=_string(item["version"], f"{label} version", maximum=512),
                version_output_sha256=_sha256(
                    item["version_output_sha256"],
                    f"{label} version_output_sha256",
                ),
                platform_system=_string(
                    item["platform_system"],
                    f"{label} platform_system",
                    maximum=128,
                ),
                platform_machine=_string(
                    item["platform_machine"],
                    f"{label} platform_machine",
                    maximum=128,
                ),
            )

        def tool(value: Any, label: str) -> ToolIdentity:
            item = _mapping(value, label)
            if set(item) != {
                "logical_tool",
                "executable_path",
                "version",
                "version_output_sha256",
            }:
                raise ValueError(f"{label} contains missing or unknown fields")
            return ToolIdentity(
                logical_tool=_string(
                    item["logical_tool"],
                    f"{label} logical_tool",
                    maximum=64,
                ),
                executable_path=_string(
                    item["executable_path"],
                    f"{label} executable_path",
                    maximum=4096,
                ),
                version=_string(item["version"], f"{label} version", maximum=512),
                version_output_sha256=_sha256(
                    item["version_output_sha256"],
                    f"{label} version_output_sha256",
                ),
            )

        failure_reason = data["failure_reason"]
        if failure_reason is not None:
            failure_reason = _string(failure_reason, "failure_reason", maximum=512)
        status_text = _string(data["status"], "visible-browser status", maximum=64)
        if status_text not in {"completed", "timed_out", "browser_failed"}:
            raise ValueError("unsupported visible-browser status")
        status = cast(VisibleBrowserStatus, status_text)
        receipt = cls(
            schema_version=data["schema_version"],
            receipt_id=_string(data["receipt_id"], "visible-browser receipt_id", maximum=64),
            timestamp_utc=_string(
                data["timestamp_utc"],
                "visible-browser timestamp_utc",
                maximum=128,
            ),
            app_id=_string(data["app_id"], "visible-browser app_id", maximum=64),
            app_version=_string(
                data["app_version"],
                "visible-browser app_version",
                maximum=128,
            ),
            visible_browser_plan_sha256=_sha256(
                data["visible_browser_plan_sha256"],
                "visible_browser_plan_sha256",
            ),
            parent_browser_session_plan_sha256=_sha256(
                data["parent_browser_session_plan_sha256"],
                "parent_browser_session_plan_sha256",
            ),
            static_web_plan_sha256=_sha256(
                data["static_web_plan_sha256"],
                "static_web_plan_sha256",
            ),
            install_receipt_sha256=_sha256(
                data["install_receipt_sha256"],
                "install_receipt_sha256",
            ),
            installed_tree_sha256=_sha256(
                data["installed_tree_sha256"],
                "installed_tree_sha256",
            ),
            static_root_sha256=_sha256(
                data["static_root_sha256"],
                "static_root_sha256",
            ),
            loopback_url=_validate_loopback_url(data["loopback_url"]),
            approved_browser_permissions=tuple(
                _string(item, "visible-browser permission", maximum=128)
                for item in permissions
            ),
            browser_tool=_string(data["browser_tool"], "browser_tool", maximum=64),
            browser_mode=_string(data["browser_mode"], "browser_mode", maximum=64),
            profile_mode=_string(data["profile_mode"], "profile_mode", maximum=64),
            display_transport=_string(
                data["display_transport"],
                "display_transport",
                maximum=64,
            ),
            display_evidence=WaylandDisplayEvidence.from_dict(data["display_evidence"]),
            browser_policy=RuntimeSandboxPolicy.from_dict(data["browser_policy"]),
            server_backend_identity=backend(
                data["server_backend_identity"],
                "server_backend_identity",
            ),
            server_tool_identity=tool(
                data["server_tool_identity"],
                "server_tool_identity",
            ),
            browser_backend_identity=backend(
                data["browser_backend_identity"],
                "browser_backend_identity",
            ),
            browser_tool_identity=tool(
                data["browser_tool_identity"],
                "browser_tool_identity",
            ),
            server_controls=RuntimeControlEvidence.from_dict(data["server_controls"]),
            browser_controls=RuntimeControlEvidence.from_dict(data["browser_controls"]),
            readiness_ready=data["readiness_ready"],
            readiness_status_code=data["readiness_status_code"],
            readiness_attempts=data["readiness_attempts"],
            readiness_elapsed_ms=data["readiness_elapsed_ms"],
            server_terminated_by_session=data["server_terminated_by_session"],
            server_exit_code=data["server_exit_code"],
            server_duration_ms=data["server_duration_ms"],
            server_stdout_sha256=_sha256(
                data["server_stdout_sha256"],
                "server_stdout_sha256",
            ),
            server_stderr_sha256=_sha256(
                data["server_stderr_sha256"],
                "server_stderr_sha256",
            ),
            browser_exit_code=data["browser_exit_code"],
            browser_timed_out=data["browser_timed_out"],
            browser_duration_ms=data["browser_duration_ms"],
            browser_stdout_sha256=_sha256(
                data["browser_stdout_sha256"],
                "browser_stdout_sha256",
            ),
            browser_stderr_sha256=_sha256(
                data["browser_stderr_sha256"],
                "browser_stderr_sha256",
            ),
            status=status,
            failure_reason=failure_reason,
            page_execution_authority=data["page_execution_authority"],
            browser_network_inherited=data["browser_network_inherited"],
            display_authority=data["display_authority"],
            persistent_profile_authority=data["persistent_profile_authority"],
            host_home_authority=data["host_home_authority"],
            gpu_device_authority=data["gpu_device_authority"],
            x11_authority=data["x11_authority"],
        )
        if data["visible_browser_receipt_sha256"] != receipt.sha256():
            raise ValueError("visible browser receipt digest does not match canonical receipt")
        return receipt


@dataclass(frozen=True)
class VisibleBrowserSessionResult:
    receipt: VisibleBrowserSessionReceipt
    receipt_path: str
    receipt_persisted: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt": self.receipt.to_dict(),
            "receipt_path": self.receipt_path,
            "receipt_persisted": self.receipt_persisted,
        }


class VisibleBrowserSessionService:
    def __init__(
        self,
        *,
        runner_factory: VisibleBrowserRunnerFactory | None = None,
    ) -> None:
        self.runner_factory = runner_factory or _default_runner_factory

    def run(
        self,
        request: VisibleBrowserSessionRequest,
        *,
        install_root: Path,
        session_root: Path,
        receipt_root: Path,
    ) -> VisibleBrowserSessionResult:
        plan = request.plan
        static_plan = request.static_web_plan
        parent = request.parent_browser_plan

        current_static = plan_static_web_adapter(
            request.install_receipt.to_dict(),
            install_root=install_root,
            loopback_port=static_plan.loopback_port,
            serve_seconds=static_plan.serve_seconds,
        )
        if current_static.sha256() != static_plan.sha256():
            raise ValueError("static-web install binding changed after visible-browser review")
        current_parent = plan_browser_session(
            static_plan.to_dict(),
            browser_tool=parent.browser_tool,
            session_seconds=parent.session_seconds,
            readiness_timeout_ms=parent.readiness_timeout_ms,
        )
        if current_parent.sha256() != parent.sha256():
            raise ValueError("parent browser-session binding changed after visible-browser review")
        _verify_wayland_socket(plan.wayland_socket)

        if current_static.static_root_relative is None:
            raise ValueError("visible browser static-web plan lacks a serveable root")
        static_root = (
            Path(current_static.install_path)
            / "payload"
            / current_static.static_root_relative
        )
        if static_root.is_symlink():
            raise ValueError("visible browser static root must not be a symlink")
        static_root = static_root.resolve(strict=True)

        sessions = session_root.expanduser()
        if sessions.is_symlink():
            raise ValueError("visible browser session root must not be a symlink")
        sessions.mkdir(parents=True, exist_ok=True)
        sessions = sessions.resolve(strict=True)
        scratch = Path(tempfile.mkdtemp(prefix=f"{plan.app_id}-", dir=sessions)).resolve()
        browser_root = scratch / "browser-root"
        browser_root.mkdir()
        try:
            runner = self.runner_factory(
                static_plan.policy,
                plan.policy,
                static_root,
                browser_root,
                plan.wayland_socket,
            )
            execution = runner.execute(static_plan, plan)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

        base = execution.browser
        if base.browser_result.timed_out:
            status: VisibleBrowserStatus = "timed_out"
            failure_reason = "visible browser exceeded reviewed wall-clock bound"
        elif base.browser_result.exit_code == 0:
            status = "completed"
            failure_reason = None
        else:
            status = "browser_failed"
            failure_reason = f"visible browser exited with code {base.browser_result.exit_code}"

        receipt = VisibleBrowserSessionReceipt(
            receipt_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(UTC).isoformat(),
            app_id=plan.app_id,
            app_version=plan.app_version,
            visible_browser_plan_sha256=plan.sha256(),
            parent_browser_session_plan_sha256=parent.sha256(),
            static_web_plan_sha256=static_plan.sha256(),
            install_receipt_sha256=plan.install_receipt_sha256,
            installed_tree_sha256=plan.installed_tree_sha256,
            static_root_sha256=plan.static_root_sha256,
            loopback_url=plan.loopback_url,
            approved_browser_permissions=request.approved_browser_permissions,
            browser_tool=plan.browser_tool,
            browser_mode=plan.browser_mode,
            profile_mode=plan.profile_mode,
            display_transport=plan.display_transport,
            display_evidence=execution.display,
            browser_policy=plan.policy,
            server_backend_identity=base.server_backend_identity,
            server_tool_identity=base.server_tool_identity,
            browser_backend_identity=base.browser_backend_identity,
            browser_tool_identity=base.browser_tool_identity,
            server_controls=base.server_controls,
            browser_controls=base.browser_controls,
            readiness_ready=base.readiness.ready,
            readiness_status_code=base.readiness.status_code,
            readiness_attempts=base.readiness.attempts,
            readiness_elapsed_ms=base.readiness.elapsed_ms,
            server_terminated_by_session=base.server_terminated_by_session,
            server_exit_code=base.server_result.exit_code,
            server_duration_ms=base.server_result.duration_ms,
            server_stdout_sha256=base.server_result.stdout.sha256,
            server_stderr_sha256=base.server_result.stderr.sha256,
            browser_exit_code=base.browser_result.exit_code,
            browser_timed_out=base.browser_result.timed_out,
            browser_duration_ms=base.browser_result.duration_ms,
            browser_stdout_sha256=base.browser_result.stdout.sha256,
            browser_stderr_sha256=base.browser_result.stderr.sha256,
            status=status,
            failure_reason=failure_reason,
            page_execution_authority=True,
            browser_network_inherited=True,
            display_authority=True,
            persistent_profile_authority=False,
            host_home_authority=False,
            gpu_device_authority=False,
            x11_authority=False,
        )

        receipts = receipt_root.expanduser()
        if receipts.is_symlink():
            raise ValueError("visible browser receipt root must not be a symlink")
        receipts.mkdir(parents=True, exist_ok=True)
        receipts = receipts.resolve(strict=True)
        receipt_path = receipts / f"visible-browser-{receipt.receipt_id}.json"
        _write_json_atomic(receipt_path, receipt.to_dict())
        return VisibleBrowserSessionResult(
            receipt=receipt,
            receipt_path=str(receipt_path),
            receipt_persisted=True,
        )
