from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Literal, Protocol, cast
from urllib.parse import urlsplit

from .browser_session import BrowserReadinessEvidence
from .build_execution import ProcessResult, StreamCapture, ToolIdentity
from .package_install import AppInstallReceipt
from .runtime import BubblewrapRuntimeRunner, RuntimeControlEvidence, RuntimeSandboxPolicy
from .sandbox import SandboxBackendIdentity
from .static_web import StaticWebAdapterPlan, StaticWebServeRequest, plan_static_web_adapter

GUI_BROWSER_PLAN_SCHEMA_VERSION = "phios.gui_browser_plan.v0.1"
GUI_BROWSER_REVIEW_SCHEMA_VERSION = "phios.gui_browser_plan_review.v0.1"
GUI_BROWSER_RECEIPT_SCHEMA_VERSION = "phios.gui_browser_receipt.v0.1"

GuiSessionStatus = Literal["window_closed", "visible_window_complete", "browser_failed"]
GuiDisplayTransport = Literal["wayland"]
GuiProfileMode = Literal["ephemeral"]

_BROWSER_TOOLS = {"chromium", "chromium-browser"}
_GUI_PERMISSIONS = (
    "browser.display.wayland",
    "browser.network.inherit",
    "browser.page.execute",
)
_LOOPBACK_HOST = "127.0.0.1"
_SANDBOX_RUNTIME_DIR = "/run/user/phios"
_MIN_SESSION_SECONDS = 1
_MAX_SESSION_SECONDS = 300
_MIN_READINESS_TIMEOUT_MS = 250
_MAX_READINESS_TIMEOUT_MS = 10_000
_WAYLAND_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


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


def _loopback_url(plan: StaticWebAdapterPlan) -> str:
    return f"http://{plan.loopback_host}:{plan.loopback_port}/"


def _validate_loopback_url(value: Any) -> str:
    url = _string(value, "GUI loopback_url", maximum=256)
    parsed = urlsplit(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname != _LOOPBACK_HOST
        or parsed.path != "/"
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ValueError("GUI loopback_url must be plain reviewed 127.0.0.1 HTTP")
    if parsed.port is None or not 1024 <= parsed.port <= 65535:
        raise ValueError("GUI loopback_url port is out of bounds")
    return url


@dataclass(frozen=True)
class WaylandSocketIdentity:
    host_path: str
    device: int
    inode: int
    ctime_ns: int
    display_name: str
    sandbox_runtime_dir: str
    sandbox_socket_path: str

    def __post_init__(self) -> None:
        path = Path(self.host_path)
        if not path.is_absolute():
            raise ValueError("Wayland host socket path must be absolute")
        if not isinstance(self.device, int) or isinstance(self.device, bool) or self.device < 0:
            raise ValueError("Wayland socket device must be a nonnegative integer")
        if not isinstance(self.inode, int) or isinstance(self.inode, bool) or self.inode <= 0:
            raise ValueError("Wayland socket inode must be a positive integer")
        if (
            not isinstance(self.ctime_ns, int)
            or isinstance(self.ctime_ns, bool)
            or self.ctime_ns <= 0
        ):
            raise ValueError("Wayland socket ctime_ns must be a positive integer")
        if not _WAYLAND_NAME_RE.fullmatch(self.display_name):
            raise ValueError("Wayland display name is invalid")
        if self.sandbox_runtime_dir != _SANDBOX_RUNTIME_DIR:
            raise ValueError("v0.37 Wayland runtime dir is fixed")
        expected = f"{_SANDBOX_RUNTIME_DIR}/{self.display_name}"
        if self.sandbox_socket_path != expected:
            raise ValueError("Wayland sandbox socket path does not match display name")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def capture(cls, path_value: Path) -> WaylandSocketIdentity:
        path = Path(path_value)
        if path.is_symlink():
            raise ValueError("Wayland socket path must not be a symlink")
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise ValueError("Wayland socket path is unavailable") from exc
        if not resolved.is_socket():
            raise ValueError("Wayland display authority requires a Unix-domain socket")
        name = resolved.name
        if not _WAYLAND_NAME_RE.fullmatch(name):
            raise ValueError("Wayland display socket name is invalid")
        stat_result = resolved.stat()
        return cls(
            host_path=str(resolved),
            device=stat_result.st_dev,
            inode=stat_result.st_ino,
            ctime_ns=stat_result.st_ctime_ns,
            display_name=name,
            sandbox_runtime_dir=_SANDBOX_RUNTIME_DIR,
            sandbox_socket_path=f"{_SANDBOX_RUNTIME_DIR}/{name}",
        )

    @classmethod
    def from_dict(cls, value: Any) -> WaylandSocketIdentity:
        data = _mapping(value, "Wayland socket identity")
        expected = {
            "host_path",
            "device",
            "inode",
            "ctime_ns",
            "display_name",
            "sandbox_runtime_dir",
            "sandbox_socket_path",
        }
        if set(data) != expected:
            raise ValueError("Wayland socket identity contains missing or unknown fields")
        return cls(
            host_path=_string(data["host_path"], "Wayland host_path", maximum=4096),
            device=data["device"],
            inode=data["inode"],
            ctime_ns=data["ctime_ns"],
            display_name=_string(data["display_name"], "Wayland display_name", maximum=64),
            sandbox_runtime_dir=_string(
                data["sandbox_runtime_dir"],
                "Wayland sandbox_runtime_dir",
                maximum=128,
            ),
            sandbox_socket_path=_string(
                data["sandbox_socket_path"],
                "Wayland sandbox_socket_path",
                maximum=256,
            ),
        )

    def verify_current(self) -> Path:
        path = Path(self.host_path)
        if path.is_symlink():
            raise ValueError("reviewed Wayland socket became a symlink")
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise ValueError("reviewed Wayland socket is unavailable") from exc
        if str(resolved) != self.host_path or not resolved.is_socket():
            raise ValueError("reviewed Wayland socket identity changed")
        stat_result = resolved.stat()
        if (
            stat_result.st_dev != self.device
            or stat_result.st_ino != self.inode
            or stat_result.st_ctime_ns != self.ctime_ns
        ):
            raise ValueError("reviewed Wayland socket instance changed")
        return resolved


def _browser_argv(browser_tool: str, loopback_url: str) -> tuple[str, ...]:
    return (
        browser_tool,
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
        "--password-store=basic",
        "--disable-features=Translate,OptimizationHints,MediaRouter",
        "--ozone-platform=wayland",
        "--user-data-dir=/home/phios/browser-profile",
        f"--app={loopback_url}",
    )


@dataclass(frozen=True)
class GuiBrowserPlan:
    app_id: str
    app_version: str
    static_web_plan_sha256: str
    install_receipt_sha256: str
    installed_tree_sha256: str
    static_root_sha256: str
    loopback_url: str
    static_serve_seconds: int
    browser_family: str
    browser_tool: str
    browser_mode: str
    profile_mode: GuiProfileMode
    display_transport: GuiDisplayTransport
    wayland: WaylandSocketIdentity
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
    dbus_authority: bool = False
    schema_version: str = GUI_BROWSER_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GUI_BROWSER_PLAN_SCHEMA_VERSION:
            raise ValueError(f"Unsupported GUI browser plan schema: {self.schema_version}")
        _string(self.app_id, "GUI app_id", maximum=64)
        _string(self.app_version, "GUI app_version", maximum=128)
        _sha256(self.static_web_plan_sha256, "static_web_plan_sha256")
        _sha256(self.install_receipt_sha256, "install_receipt_sha256")
        _sha256(self.installed_tree_sha256, "installed_tree_sha256")
        _sha256(self.static_root_sha256, "static_root_sha256")
        _validate_loopback_url(self.loopback_url)
        _int(self.static_serve_seconds, "static_serve_seconds", minimum=1, maximum=3600)
        if self.browser_family != "chromium":
            raise ValueError("v0.37 supports only Chromium-family GUI sessions")
        if self.browser_tool not in _BROWSER_TOOLS:
            raise ValueError("v0.37 browser_tool must be chromium or chromium-browser")
        if self.browser_mode != "visible_app_window":
            raise ValueError("v0.37 supports only visible_app_window browser mode")
        if self.profile_mode != "ephemeral":
            raise ValueError("v0.37 browser profile must be ephemeral")
        if self.display_transport != "wayland":
            raise ValueError("v0.37 supports only Wayland display transport")
        if self.requested_browser_permissions != _GUI_PERMISSIONS:
            raise ValueError("v0.37 browser permissions must match the fixed authority set")
        if self.browser_argv != _browser_argv(self.browser_tool, self.loopback_url):
            raise ValueError("GUI browser argv does not match the v0.37 fixed Chromium contract")
        if self.policy.network_mode != "inherit":
            raise ValueError("v0.37 browser requires host-network inheritance")
        _int(
            self.session_seconds,
            "GUI session_seconds",
            minimum=_MIN_SESSION_SECONDS,
            maximum=_MAX_SESSION_SECONDS,
        )
        _int(
            self.readiness_timeout_ms,
            "GUI readiness_timeout_ms",
            minimum=_MIN_READINESS_TIMEOUT_MS,
            maximum=_MAX_READINESS_TIMEOUT_MS,
        )
        readiness_seconds = (self.readiness_timeout_ms + 999) // 1000
        if self.session_seconds + readiness_seconds > self.static_serve_seconds:
            raise ValueError("GUI readiness + session window exceeds reviewed static serve window")
        for value, label in (
            (self.launch_authority, "launch_authority"),
            (self.page_execution_authority, "page_execution_authority"),
            (self.display_authority, "display_authority"),
            (self.persistent_profile_authority, "persistent_profile_authority"),
            (self.host_home_authority, "host_home_authority"),
            (self.gpu_device_authority, "gpu_device_authority"),
            (self.dbus_authority, "dbus_authority"),
        ):
            if value is not False:
                raise ValueError(f"GUI plan must not pre-grant {label}")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app_id": self.app_id,
            "app_version": self.app_version,
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
            "wayland": self.wayland.to_dict(),
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
            "dbus_authority": self.dbus_authority,
        }

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["gui_browser_plan_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> GuiBrowserPlan:
        data = _mapping(value, "GUI browser plan")
        expected = {
            "schema_version",
            "app_id",
            "app_version",
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
            "wayland",
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
            "dbus_authority",
            "gui_browser_plan_sha256",
        }
        if set(data) != expected:
            raise ValueError("GUI browser plan contains missing or unknown fields")
        permissions = data["requested_browser_permissions"]
        argv = data["browser_argv"]
        if not isinstance(permissions, list) or not isinstance(argv, list):
            raise ValueError("GUI permissions and argv must be arrays")
        plan = cls(
            schema_version=data["schema_version"],
            app_id=_string(data["app_id"], "GUI app_id", maximum=64),
            app_version=_string(data["app_version"], "GUI app_version", maximum=128),
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
            static_root_sha256=_sha256(data["static_root_sha256"], "static_root_sha256"),
            loopback_url=_validate_loopback_url(data["loopback_url"]),
            static_serve_seconds=data["static_serve_seconds"],
            browser_family=_string(data["browser_family"], "browser_family", maximum=64),
            browser_tool=_string(data["browser_tool"], "browser_tool", maximum=64),
            browser_mode=_string(data["browser_mode"], "browser_mode", maximum=64),
            profile_mode=data["profile_mode"],
            display_transport=data["display_transport"],
            wayland=WaylandSocketIdentity.from_dict(data["wayland"]),
            requested_browser_permissions=tuple(
                _string(item, "GUI browser permission", maximum=128)
                for item in permissions
            ),
            browser_argv=tuple(
                _string(item, "GUI browser argv item", maximum=1024) for item in argv
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
            dbus_authority=data["dbus_authority"],
        )
        if data["gui_browser_plan_sha256"] != plan.sha256():
            raise ValueError("GUI browser plan digest does not match canonical plan")
        return plan


def plan_gui_browser(
    static_web_plan_value: Any,
    *,
    wayland_socket_path: Path,
    browser_tool: str = "chromium",
    session_seconds: int = 60,
    readiness_timeout_ms: int = 3_000,
) -> GuiBrowserPlan:
    static_plan = StaticWebAdapterPlan.from_dict(static_web_plan_value)
    if static_plan.status != "ready_for_review":
        raise ValueError("GUI planning requires a ready_for_review static-web plan")
    if static_plan.static_root_sha256 is None:
        raise ValueError("static-web plan lacks static-root identity")
    if browser_tool not in _BROWSER_TOOLS:
        raise ValueError("browser_tool must be chromium or chromium-browser")
    wayland = WaylandSocketIdentity.capture(wayland_socket_path)
    loopback_url = _loopback_url(static_plan)
    policy = RuntimeSandboxPolicy(
        network_mode="inherit",
        wall_clock_seconds=session_seconds,
        cpu_seconds=min(session_seconds, 300),
        address_space_bytes=4 * 1024 * 1024 * 1024,
        max_open_files=1024,
        max_file_size_bytes=128 * 1024 * 1024,
    )
    return GuiBrowserPlan(
        app_id=static_plan.app_id,
        app_version=static_plan.app_version,
        static_web_plan_sha256=static_plan.sha256(),
        install_receipt_sha256=static_plan.install_receipt_sha256,
        installed_tree_sha256=static_plan.installed_tree_sha256,
        static_root_sha256=static_plan.static_root_sha256,
        loopback_url=loopback_url,
        static_serve_seconds=static_plan.serve_seconds,
        browser_family="chromium",
        browser_tool=browser_tool,
        browser_mode="visible_app_window",
        profile_mode="ephemeral",
        display_transport="wayland",
        wayland=wayland,
        requested_browser_permissions=_GUI_PERMISSIONS,
        browser_argv=_browser_argv(browser_tool, loopback_url),
        policy=policy,
        session_seconds=session_seconds,
        readiness_timeout_ms=readiness_timeout_ms,
        launch_authority=False,
        page_execution_authority=False,
        display_authority=False,
        persistent_profile_authority=False,
        host_home_authority=False,
        gpu_device_authority=False,
        dbus_authority=False,
    )


@dataclass(frozen=True)
class GuiBrowserReview:
    gui_browser_plan_sha256: str
    app_id: str
    app_version: str
    static_web_plan_sha256: str
    loopback_url: str
    browser_tool: str
    display_transport: str
    wayland: WaylandSocketIdentity
    requested_browser_permissions: tuple[str, ...]
    session_seconds: int
    readiness_timeout_ms: int
    launch_authority: bool
    page_execution_authority: bool
    display_authority: bool
    gpu_device_authority: bool
    dbus_authority: bool
    schema_version: str = GUI_BROWSER_REVIEW_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["wayland"] = self.wayland.to_dict()
        result["requested_browser_permissions"] = list(self.requested_browser_permissions)
        return result


def review_gui_browser(value: Any) -> GuiBrowserReview:
    plan = GuiBrowserPlan.from_dict(value)
    return GuiBrowserReview(
        gui_browser_plan_sha256=plan.sha256(),
        app_id=plan.app_id,
        app_version=plan.app_version,
        static_web_plan_sha256=plan.static_web_plan_sha256,
        loopback_url=plan.loopback_url,
        browser_tool=plan.browser_tool,
        display_transport=plan.display_transport,
        wayland=plan.wayland,
        requested_browser_permissions=plan.requested_browser_permissions,
        session_seconds=plan.session_seconds,
        readiness_timeout_ms=plan.readiness_timeout_ms,
        launch_authority=plan.launch_authority,
        page_execution_authority=plan.page_execution_authority,
        display_authority=plan.display_authority,
        gpu_device_authority=plan.gpu_device_authority,
        dbus_authority=plan.dbus_authority,
    )


@dataclass(frozen=True)
class GuiBrowserRequest:
    plan: GuiBrowserPlan
    static_web_plan: StaticWebAdapterPlan
    install_receipt: AppInstallReceipt
    approved_gui_browser_plan_sha256: str
    approved_static_web_plan_sha256: str
    approved_browser_permissions: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.approved_gui_browser_plan_sha256 != self.plan.sha256():
            raise ValueError("Approved GUI browser plan SHA-256 does not match canonical plan")
        if self.static_web_plan.sha256() != self.plan.static_web_plan_sha256:
            raise ValueError("static-web plan does not match GUI browser plan")
        if self.approved_static_web_plan_sha256 != self.static_web_plan.sha256():
            raise ValueError("Approved static-web plan SHA-256 does not match canonical plan")
        if self.install_receipt.sha256() != self.plan.install_receipt_sha256:
            raise ValueError("install receipt does not match GUI browser plan")
        if self.install_receipt.installed_tree_sha256 != self.plan.installed_tree_sha256:
            raise ValueError("install receipt tree does not match GUI browser plan")
        if self.approved_browser_permissions != self.plan.requested_browser_permissions:
            raise ValueError("Approved browser permissions must exactly match GUI browser plan")

    @classmethod
    def from_payloads(
        cls,
        plan_value: Any,
        static_web_plan_value: Any,
        install_receipt_value: Any,
        *,
        approved_gui_browser_plan_sha256: str,
        approved_static_web_plan_sha256: str,
        approved_browser_permissions: tuple[str, ...],
    ) -> GuiBrowserRequest:
        plan = GuiBrowserPlan.from_dict(plan_value)
        static_plan = StaticWebAdapterPlan.from_dict(static_web_plan_value)
        receipt = AppInstallReceipt.from_dict(install_receipt_value)
        StaticWebServeRequest.from_payloads(
            static_plan.to_dict(),
            receipt.to_dict(),
            approved_static_web_plan_sha256=approved_static_web_plan_sha256,
        )
        approved = tuple(sorted(approved_browser_permissions))
        if len(set(approved)) != len(approved):
            raise ValueError("approved browser permissions must not contain duplicates")
        return cls(
            plan=plan,
            static_web_plan=static_plan,
            install_receipt=receipt,
            approved_gui_browser_plan_sha256=_sha256(
                approved_gui_browser_plan_sha256,
                "approved_gui_browser_plan_sha256",
            ),
            approved_static_web_plan_sha256=_sha256(
                approved_static_web_plan_sha256,
                "approved_static_web_plan_sha256",
            ),
            approved_browser_permissions=approved,
        )


@dataclass(frozen=True)
class GuiDisplayEvidence:
    transport: str
    host_socket_path: str
    host_socket_device: int
    host_socket_inode: int
    sandbox_socket_path: str
    socket_bound_read_only: bool
    display_environment_set: bool
    host_runtime_directory_mounted: bool
    dbus_socket_mounted: bool
    gpu_device_mounted: bool

    def __post_init__(self) -> None:
        if self.transport != "wayland":
            raise ValueError("v0.37 display evidence must use Wayland")
        if not Path(self.host_socket_path).is_absolute():
            raise ValueError("display evidence host socket path must be absolute")
        if self.socket_bound_read_only is not True:
            raise ValueError("v0.37 requires read-only Wayland socket bind evidence")
        if self.display_environment_set is not True:
            raise ValueError("v0.37 requires Wayland display environment evidence")
        if self.host_runtime_directory_mounted is not False:
            raise ValueError("v0.37 must not mount the whole host runtime directory")
        if self.dbus_socket_mounted is not False:
            raise ValueError("v0.37 must not mount host DBus")
        if self.gpu_device_mounted is not False:
            raise ValueError("v0.37 must not mount host GPU devices")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Any) -> GuiDisplayEvidence:
        data = _mapping(value, "GUI display evidence")
        expected = set(cls.__dataclass_fields__)
        if set(data) != expected:
            raise ValueError("GUI display evidence contains missing or unknown fields")
        return cls(**data)


@dataclass(frozen=True)
class GuiBrowserExecution:
    server_backend_identity: SandboxBackendIdentity
    server_tool_identity: ToolIdentity
    browser_backend_identity: SandboxBackendIdentity
    browser_tool_identity: ToolIdentity
    server_controls: RuntimeControlEvidence
    browser_controls: RuntimeControlEvidence
    display: GuiDisplayEvidence
    readiness: BrowserReadinessEvidence
    server_result: ProcessResult
    browser_result: ProcessResult
    server_terminated_by_session: bool


class GuiBrowserRunner(Protocol):
    def execute(
        self,
        static_plan: StaticWebAdapterPlan,
        gui_plan: GuiBrowserPlan,
    ) -> GuiBrowserExecution: ...


class _PipeDigest:
    def __init__(self) -> None:
        self.byte_count = 0
        self.digest = hashlib.sha256()

    def feed(self, chunk: bytes) -> None:
        self.byte_count += len(chunk)
        self.digest.update(chunk)

    def result(self) -> StreamCapture:
        return StreamCapture(
            byte_count=self.byte_count,
            sha256=self.digest.hexdigest(),
            preview="",
            preview_truncated=self.byte_count > 0,
        )


class BubblewrapGuiBrowserRunner:
    def __init__(
        self,
        *,
        server_policy: RuntimeSandboxPolicy,
        browser_policy: RuntimeSandboxPolicy,
        static_root: Path,
        browser_root: Path,
        gui_plan: GuiBrowserPlan,
    ) -> None:
        self.static_root = static_root.resolve(strict=True)
        self.browser_root = browser_root.resolve(strict=True)
        wayland_path = gui_plan.wayland.verify_current()
        self.gui_plan = gui_plan
        self.server_runner = BubblewrapRuntimeRunner(
            server_policy,
            payload_root=self.static_root,
            data_path=None,
        )
        self.browser_runner = BubblewrapRuntimeRunner(
            browser_policy,
            payload_root=self.browser_root,
            data_path=None,
            extra_read_only_binds=(
                (wayland_path, gui_plan.wayland.sandbox_socket_path),
            ),
            extra_environment={
                "XDG_RUNTIME_DIR": gui_plan.wayland.sandbox_runtime_dir,
                "WAYLAND_DISPLAY": gui_plan.wayland.display_name,
            },
        )

    @staticmethod
    def _port_available(host: str, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            try:
                sock.bind((host, port))
            except OSError:
                return False
        return True

    @staticmethod
    def _readiness_probe(
        process: subprocess.Popen[bytes],
        *,
        host: str,
        port: int,
        timeout_ms: int,
    ) -> BrowserReadinessEvidence:
        started = time.monotonic()
        deadline = started + (timeout_ms / 1000)
        attempts = 0
        last_status = 0
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            attempts += 1
            connection = http.client.HTTPConnection(host, port, timeout=0.2)
            try:
                connection.request("HEAD", "/")
                response = connection.getresponse()
                last_status = response.status
                response.read()
                if last_status == 200:
                    return BrowserReadinessEvidence(
                        ready=True,
                        status_code=200,
                        attempts=attempts,
                        elapsed_ms=int((time.monotonic() - started) * 1000),
                        port_available_before_spawn=True,
                    )
            except (OSError, http.client.HTTPException):
                pass
            finally:
                connection.close()
            time.sleep(0.05)
        raise ValueError(
            "reviewed static-web server did not become ready on the reviewed loopback port "
            f"(last_status={last_status})"
        )

    @staticmethod
    def _terminate_server(
        process: subprocess.Popen[bytes],
        *,
        started: float,
        stdout_thread: threading.Thread,
        stderr_thread: threading.Thread,
        stdout_capture: _PipeDigest,
        stderr_capture: _PipeDigest,
    ) -> ProcessResult:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        stdout_thread.join()
        stderr_thread.join()
        assert process.returncode is not None
        return ProcessResult(
            exit_code=process.returncode,
            timed_out=False,
            duration_ms=int((time.monotonic() - started) * 1000),
            stdout=stdout_capture.result(),
            stderr=stderr_capture.result(),
        )

    def execute(
        self,
        static_plan: StaticWebAdapterPlan,
        gui_plan: GuiBrowserPlan,
    ) -> GuiBrowserExecution:
        if static_plan.server_tool != "python3":
            raise ValueError("v0.37 requires the v0.35 trusted Python static server")
        if static_plan.loopback_host != _LOOPBACK_HOST:
            raise ValueError("v0.37 requires the v0.35 127.0.0.1 listener")
        if not self._port_available(static_plan.loopback_host, static_plan.loopback_port):
            raise ValueError("reviewed loopback port is occupied before GUI server spawn")

        server_backend = self.server_runner.preflight()
        server_tool = self.server_runner.probe_tool("python3")
        browser_backend = self.browser_runner.preflight()
        browser_tool = self.browser_runner.probe_tool(gui_plan.browser_tool)

        server_command = self.server_runner.command_for(
            executable_path=server_tool.executable_path,
            argv_tail=static_plan.server_argv[1:],
        )
        started = time.monotonic()
        server_process = subprocess.Popen(
            server_command,
            cwd=self.static_root,
            env={"PATH": os.environ.get("PATH", "")},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
        assert server_process.stdout is not None
        assert server_process.stderr is not None
        stdout_capture = _PipeDigest()
        stderr_capture = _PipeDigest()

        def drain(stream: Any, capture: _PipeDigest) -> None:
            while True:
                chunk = stream.read(65_536)
                if not chunk:
                    break
                capture.feed(chunk)

        stdout_thread = threading.Thread(
            target=drain,
            args=(server_process.stdout, stdout_capture),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=drain,
            args=(server_process.stderr, stderr_capture),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        try:
            readiness = self._readiness_probe(
                server_process,
                host=static_plan.loopback_host,
                port=static_plan.loopback_port,
                timeout_ms=gui_plan.readiness_timeout_ms,
            )
            gui_plan.wayland.verify_current()
            browser_result = self.browser_runner.run_argv(
                gui_plan.browser_tool,
                gui_plan.browser_argv[1:],
                timeout_seconds=gui_plan.session_seconds,
            )
        finally:
            server_result = self._terminate_server(
                server_process,
                started=started,
                stdout_thread=stdout_thread,
                stderr_thread=stderr_thread,
                stdout_capture=stdout_capture,
                stderr_capture=stderr_capture,
            )

        server_controls = replace(
            self.server_runner.control_evidence(),
            wall_clock_timeout_enforced=False,
        )
        browser_controls = self.browser_runner.control_evidence()
        display = GuiDisplayEvidence(
            transport="wayland",
            host_socket_path=gui_plan.wayland.host_path,
            host_socket_device=gui_plan.wayland.device,
            host_socket_inode=gui_plan.wayland.inode,
            sandbox_socket_path=gui_plan.wayland.sandbox_socket_path,
            socket_bound_read_only=True,
            display_environment_set=True,
            host_runtime_directory_mounted=False,
            dbus_socket_mounted=False,
            gpu_device_mounted=False,
        )
        return GuiBrowserExecution(
            server_backend_identity=server_backend,
            server_tool_identity=server_tool,
            browser_backend_identity=browser_backend,
            browser_tool_identity=browser_tool,
            server_controls=server_controls,
            browser_controls=browser_controls,
            display=display,
            readiness=readiness,
            server_result=server_result,
            browser_result=browser_result,
            server_terminated_by_session=True,
        )


GuiBrowserRunnerFactory = Callable[
    [RuntimeSandboxPolicy, RuntimeSandboxPolicy, Path, Path, GuiBrowserPlan],
    GuiBrowserRunner,
]


def _default_runner_factory(
    server_policy: RuntimeSandboxPolicy,
    browser_policy: RuntimeSandboxPolicy,
    static_root: Path,
    browser_root: Path,
    gui_plan: GuiBrowserPlan,
) -> GuiBrowserRunner:
    return BubblewrapGuiBrowserRunner(
        server_policy=server_policy,
        browser_policy=browser_policy,
        static_root=static_root,
        browser_root=browser_root,
        gui_plan=gui_plan,
    )


@dataclass(frozen=True)
class GuiBrowserReceipt:
    receipt_id: str
    timestamp_utc: str
    app_id: str
    app_version: str
    gui_browser_plan_sha256: str
    static_web_plan_sha256: str
    install_receipt_sha256: str
    installed_tree_sha256: str
    static_root_sha256: str
    loopback_url: str
    approved_browser_permissions: tuple[str, ...]
    browser_family: str
    browser_tool: str
    browser_mode: str
    profile_mode: str
    display_transport: str
    wayland: WaylandSocketIdentity
    browser_policy: RuntimeSandboxPolicy
    server_backend_identity: SandboxBackendIdentity
    server_tool_identity: ToolIdentity
    browser_backend_identity: SandboxBackendIdentity
    browser_tool_identity: ToolIdentity
    server_controls: RuntimeControlEvidence
    browser_controls: RuntimeControlEvidence
    display: GuiDisplayEvidence
    readiness: BrowserReadinessEvidence
    server_terminated_by_session: bool
    server_exit_code: int
    server_duration_ms: int
    server_stdout_byte_count: int
    server_stdout_sha256: str
    server_stderr_byte_count: int
    server_stderr_sha256: str
    browser_exit_code: int
    browser_timed_out: bool
    browser_duration_ms: int
    browser_stdout_byte_count: int
    browser_stdout_sha256: str
    browser_stderr_byte_count: int
    browser_stderr_sha256: str
    status: GuiSessionStatus
    failure_reason: str | None
    page_execution_authority: bool
    browser_network_inherited: bool
    display_authority: bool
    persistent_profile_authority: bool
    host_home_authority: bool
    gpu_device_authority: bool
    dbus_authority: bool
    schema_version: str = GUI_BROWSER_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GUI_BROWSER_RECEIPT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported GUI browser receipt schema: {self.schema_version}")
        try:
            uuid.UUID(self.receipt_id)
        except ValueError as exc:
            raise ValueError("GUI browser receipt_id must be a UUID") from exc
        timestamp = datetime.fromisoformat(self.timestamp_utc)
        if timestamp.tzinfo is None:
            raise ValueError("GUI browser timestamp must include a timezone")
        for value, label in (
            (self.gui_browser_plan_sha256, "gui_browser_plan_sha256"),
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
        if self.approved_browser_permissions != _GUI_PERMISSIONS:
            raise ValueError("GUI receipt permissions must match v0.37 authority set")
        if self.browser_family != "chromium" or self.browser_tool not in _BROWSER_TOOLS:
            raise ValueError("GUI receipt browser identity is unsupported")
        if (
            self.browser_mode != "visible_app_window"
            or self.profile_mode != "ephemeral"
            or self.display_transport != "wayland"
        ):
            raise ValueError("GUI receipt mode does not match v0.37")
        if self.browser_policy.network_mode != "inherit":
            raise ValueError("GUI receipt must record host-network inheritance")
        if not self.server_controls.host_network_inherited:
            raise ValueError("GUI server controls must record host-network inheritance")
        if self.server_controls.network_namespace_enforced:
            raise ValueError("GUI server must not claim a separate network namespace")
        if not self.browser_controls.host_network_inherited:
            raise ValueError("GUI browser controls must record host-network inheritance")
        if self.browser_controls.network_namespace_enforced:
            raise ValueError("GUI browser must not claim a separate network namespace")
        if not self.browser_controls.private_home or not self.browser_controls.private_tmp:
            raise ValueError("GUI browser controls require private home and tmp")
        if self.browser_controls.persistent_data_writable_mount:
            raise ValueError("GUI browser must not expose persistent app data")
        if not self.server_terminated_by_session:
            raise ValueError("GUI session must terminate its coordinated static server")
        if self.page_execution_authority is not True:
            raise ValueError("GUI receipt must record page execution authority")
        if self.browser_network_inherited is not True:
            raise ValueError("GUI receipt must record broad browser network authority")
        if self.display_authority is not True:
            raise ValueError("GUI receipt must record display authority")
        if self.persistent_profile_authority is not False:
            raise ValueError("v0.37 does not grant persistent profile authority")
        if self.host_home_authority is not False:
            raise ValueError("v0.37 does not grant host-home authority")
        if self.gpu_device_authority is not False:
            raise ValueError("v0.37 does not grant GPU device authority")
        if self.dbus_authority is not False:
            raise ValueError("v0.37 does not grant DBus authority")
        _int(self.server_duration_ms, "server_duration_ms", minimum=0, maximum=86_400_000)
        _int(self.browser_duration_ms, "browser_duration_ms", minimum=0, maximum=86_400_000)
        for byte_count, label in (
            (self.server_stdout_byte_count, "server_stdout_byte_count"),
            (self.server_stderr_byte_count, "server_stderr_byte_count"),
            (self.browser_stdout_byte_count, "browser_stdout_byte_count"),
            (self.browser_stderr_byte_count, "browser_stderr_byte_count"),
        ):
            _int(byte_count, label, minimum=0, maximum=2**63 - 1)
        if not isinstance(self.server_exit_code, int) or isinstance(self.server_exit_code, bool):
            raise ValueError("server_exit_code must be an integer")
        if not isinstance(self.browser_exit_code, int) or isinstance(self.browser_exit_code, bool):
            raise ValueError("browser_exit_code must be an integer")
        if not isinstance(self.browser_timed_out, bool):
            raise ValueError("browser_timed_out must be boolean")
        if self.status == "window_closed":
            if self.browser_timed_out or self.browser_exit_code != 0 or self.failure_reason is not None:
                raise ValueError("window_closed requires clean browser exit")
        elif self.status == "visible_window_complete":
            if not self.browser_timed_out or self.failure_reason is not None:
                raise ValueError("visible_window_complete requires reviewed timeout")
        elif self.status == "browser_failed":
            if self.browser_timed_out or self.browser_exit_code == 0 or self.failure_reason is None:
                raise ValueError("browser_failed requires nonzero exit without timeout")
        else:
            raise ValueError("unsupported GUI browser session status")

    def body_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["approved_browser_permissions"] = list(self.approved_browser_permissions)
        result["wayland"] = self.wayland.to_dict()
        result["browser_policy"] = self.browser_policy.to_dict()
        result["server_backend_identity"] = self.server_backend_identity.to_dict()
        result["server_tool_identity"] = self.server_tool_identity.to_dict()
        result["browser_backend_identity"] = self.browser_backend_identity.to_dict()
        result["browser_tool_identity"] = self.browser_tool_identity.to_dict()
        result["server_controls"] = self.server_controls.to_dict()
        result["browser_controls"] = self.browser_controls.to_dict()
        result["display"] = self.display.to_dict()
        result["readiness"] = self.readiness.to_dict()
        return result

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["gui_browser_receipt_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> GuiBrowserReceipt:
        data = _mapping(value, "GUI browser receipt")
        expected = {
            "schema_version",
            "receipt_id",
            "timestamp_utc",
            "app_id",
            "app_version",
            "gui_browser_plan_sha256",
            "static_web_plan_sha256",
            "install_receipt_sha256",
            "installed_tree_sha256",
            "static_root_sha256",
            "loopback_url",
            "approved_browser_permissions",
            "browser_family",
            "browser_tool",
            "browser_mode",
            "profile_mode",
            "display_transport",
            "wayland",
            "browser_policy",
            "server_backend_identity",
            "server_tool_identity",
            "browser_backend_identity",
            "browser_tool_identity",
            "server_controls",
            "browser_controls",
            "display",
            "readiness",
            "server_terminated_by_session",
            "server_exit_code",
            "server_duration_ms",
            "server_stdout_byte_count",
            "server_stdout_sha256",
            "server_stderr_byte_count",
            "server_stderr_sha256",
            "browser_exit_code",
            "browser_timed_out",
            "browser_duration_ms",
            "browser_stdout_byte_count",
            "browser_stdout_sha256",
            "browser_stderr_byte_count",
            "browser_stderr_sha256",
            "status",
            "failure_reason",
            "page_execution_authority",
            "browser_network_inherited",
            "display_authority",
            "persistent_profile_authority",
            "host_home_authority",
            "gpu_device_authority",
            "dbus_authority",
            "gui_browser_receipt_sha256",
        }
        if set(data) != expected:
            raise ValueError("GUI browser receipt contains missing or unknown fields")
        permissions = data["approved_browser_permissions"]
        if not isinstance(permissions, list):
            raise ValueError("approved_browser_permissions must be an array")

        def backend_identity(raw: Any, label: str) -> SandboxBackendIdentity:
            item = _mapping(raw, label)
            expected_fields = {
                "backend",
                "executable_path",
                "version",
                "version_output_sha256",
                "platform_system",
                "platform_machine",
            }
            if set(item) != expected_fields:
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

        def tool_identity(raw: Any, label: str) -> ToolIdentity:
            item = _mapping(raw, label)
            expected_fields = {
                "logical_tool",
                "executable_path",
                "version",
                "version_output_sha256",
            }
            if set(item) != expected_fields:
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
            failure_reason = _string(failure_reason, "GUI failure_reason", maximum=512)

        receipt = cls(
            schema_version=data["schema_version"],
            receipt_id=_string(data["receipt_id"], "GUI receipt_id", maximum=64),
            timestamp_utc=_string(data["timestamp_utc"], "GUI timestamp", maximum=128),
            app_id=_string(data["app_id"], "GUI app_id", maximum=64),
            app_version=_string(data["app_version"], "GUI app_version", maximum=128),
            gui_browser_plan_sha256=_sha256(
                data["gui_browser_plan_sha256"],
                "gui_browser_plan_sha256",
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
                _string(item, "GUI approved browser permission", maximum=128)
                for item in permissions
            ),
            browser_family=_string(data["browser_family"], "browser_family", maximum=64),
            browser_tool=_string(data["browser_tool"], "browser_tool", maximum=64),
            browser_mode=_string(data["browser_mode"], "browser_mode", maximum=64),
            profile_mode=_string(data["profile_mode"], "profile_mode", maximum=64),
            display_transport=_string(
                data["display_transport"],
                "display_transport",
                maximum=64,
            ),
            wayland=WaylandSocketIdentity.from_dict(data["wayland"]),
            browser_policy=RuntimeSandboxPolicy.from_dict(data["browser_policy"]),
            server_backend_identity=backend_identity(
                data["server_backend_identity"],
                "server backend identity",
            ),
            server_tool_identity=tool_identity(
                data["server_tool_identity"],
                "server tool identity",
            ),
            browser_backend_identity=backend_identity(
                data["browser_backend_identity"],
                "browser backend identity",
            ),
            browser_tool_identity=tool_identity(
                data["browser_tool_identity"],
                "browser tool identity",
            ),
            server_controls=RuntimeControlEvidence.from_dict(data["server_controls"]),
            browser_controls=RuntimeControlEvidence.from_dict(data["browser_controls"]),
            display=GuiDisplayEvidence.from_dict(data["display"]),
            readiness=BrowserReadinessEvidence.from_dict(data["readiness"]),
            server_terminated_by_session=data["server_terminated_by_session"],
            server_exit_code=data["server_exit_code"],
            server_duration_ms=data["server_duration_ms"],
            server_stdout_byte_count=data["server_stdout_byte_count"],
            server_stdout_sha256=_sha256(
                data["server_stdout_sha256"],
                "server_stdout_sha256",
            ),
            server_stderr_byte_count=data["server_stderr_byte_count"],
            server_stderr_sha256=_sha256(
                data["server_stderr_sha256"],
                "server_stderr_sha256",
            ),
            browser_exit_code=data["browser_exit_code"],
            browser_timed_out=data["browser_timed_out"],
            browser_duration_ms=data["browser_duration_ms"],
            browser_stdout_byte_count=data["browser_stdout_byte_count"],
            browser_stdout_sha256=_sha256(
                data["browser_stdout_sha256"],
                "browser_stdout_sha256",
            ),
            browser_stderr_byte_count=data["browser_stderr_byte_count"],
            browser_stderr_sha256=_sha256(
                data["browser_stderr_sha256"],
                "browser_stderr_sha256",
            ),
            status=cast(GuiSessionStatus, data["status"]),
            failure_reason=failure_reason,
            page_execution_authority=data["page_execution_authority"],
            browser_network_inherited=data["browser_network_inherited"],
            display_authority=data["display_authority"],
            persistent_profile_authority=data["persistent_profile_authority"],
            host_home_authority=data["host_home_authority"],
            gpu_device_authority=data["gpu_device_authority"],
            dbus_authority=data["dbus_authority"],
        )
        if data["gui_browser_receipt_sha256"] != receipt.sha256():
            raise ValueError("GUI browser receipt digest does not match canonical receipt")
        return receipt


@dataclass(frozen=True)
class GuiBrowserResult:
    receipt: GuiBrowserReceipt
    receipt_path: str
    receipt_persisted: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt": self.receipt.to_dict(),
            "receipt_path": self.receipt_path,
            "receipt_persisted": self.receipt_persisted,
        }


class GuiBrowserService:
    def __init__(self, *, runner_factory: GuiBrowserRunnerFactory | None = None) -> None:
        self.runner_factory = runner_factory or _default_runner_factory

    def run(
        self,
        request: GuiBrowserRequest,
        *,
        install_root: Path,
        session_root: Path,
        receipt_root: Path,
    ) -> GuiBrowserResult:
        plan = request.plan
        static_plan = request.static_web_plan
        plan.wayland.verify_current()
        current_static = plan_static_web_adapter(
            request.install_receipt.to_dict(),
            install_root=install_root,
            loopback_port=static_plan.loopback_port,
            serve_seconds=static_plan.serve_seconds,
        )
        if current_static.sha256() != static_plan.sha256():
            raise ValueError("static-web install binding changed after GUI-plan review")
        if current_static.static_root_relative is None:
            raise ValueError("current static-web plan lacks a serveable root")
        static_root = (
            Path(current_static.install_path)
            / "payload"
            / current_static.static_root_relative
        )
        if static_root.is_symlink():
            raise ValueError("GUI session static root must not be a symlink")
        static_root = static_root.resolve(strict=True)
        if not static_root.is_dir():
            raise ValueError("GUI session static root is not a directory")

        sessions = session_root.expanduser()
        if sessions.is_symlink():
            raise ValueError("GUI session root must not be a symlink")
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
                plan,
            )
            execution = runner.execute(static_plan, plan)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

        if execution.browser_result.timed_out:
            status: GuiSessionStatus = "visible_window_complete"
            failure_reason = None
        elif execution.browser_result.exit_code == 0:
            status = "window_closed"
            failure_reason = None
        else:
            status = "browser_failed"
            failure_reason = (
                f"GUI browser process exited with code {execution.browser_result.exit_code}"
            )

        receipt = GuiBrowserReceipt(
            receipt_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(UTC).isoformat(),
            app_id=plan.app_id,
            app_version=plan.app_version,
            gui_browser_plan_sha256=plan.sha256(),
            static_web_plan_sha256=static_plan.sha256(),
            install_receipt_sha256=plan.install_receipt_sha256,
            installed_tree_sha256=plan.installed_tree_sha256,
            static_root_sha256=plan.static_root_sha256,
            loopback_url=plan.loopback_url,
            approved_browser_permissions=request.approved_browser_permissions,
            browser_family=plan.browser_family,
            browser_tool=plan.browser_tool,
            browser_mode=plan.browser_mode,
            profile_mode=plan.profile_mode,
            display_transport=plan.display_transport,
            wayland=plan.wayland,
            browser_policy=plan.policy,
            server_backend_identity=execution.server_backend_identity,
            server_tool_identity=execution.server_tool_identity,
            browser_backend_identity=execution.browser_backend_identity,
            browser_tool_identity=execution.browser_tool_identity,
            server_controls=execution.server_controls,
            browser_controls=execution.browser_controls,
            display=execution.display,
            readiness=execution.readiness,
            server_terminated_by_session=execution.server_terminated_by_session,
            server_exit_code=execution.server_result.exit_code,
            server_duration_ms=execution.server_result.duration_ms,
            server_stdout_byte_count=execution.server_result.stdout.byte_count,
            server_stdout_sha256=execution.server_result.stdout.sha256,
            server_stderr_byte_count=execution.server_result.stderr.byte_count,
            server_stderr_sha256=execution.server_result.stderr.sha256,
            browser_exit_code=execution.browser_result.exit_code,
            browser_timed_out=execution.browser_result.timed_out,
            browser_duration_ms=execution.browser_result.duration_ms,
            browser_stdout_byte_count=execution.browser_result.stdout.byte_count,
            browser_stdout_sha256=execution.browser_result.stdout.sha256,
            browser_stderr_byte_count=execution.browser_result.stderr.byte_count,
            browser_stderr_sha256=execution.browser_result.stderr.sha256,
            status=status,
            failure_reason=failure_reason,
            page_execution_authority=True,
            browser_network_inherited=True,
            display_authority=True,
            persistent_profile_authority=False,
            host_home_authority=False,
            gpu_device_authority=False,
            dbus_authority=False,
        )

        receipts = receipt_root.expanduser()
        if receipts.is_symlink():
            raise ValueError("GUI receipt root must not be a symlink")
        receipts.mkdir(parents=True, exist_ok=True)
        receipts = receipts.resolve(strict=True)
        receipt_path = receipts / f"gui-browser-{receipt.receipt_id}.json"
        _write_json_atomic(receipt_path, receipt.to_dict())
        return GuiBrowserResult(
            receipt=receipt,
            receipt_path=str(receipt_path),
            receipt_persisted=True,
        )
