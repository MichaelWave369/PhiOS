from __future__ import annotations

import hashlib
import http.client
import json
import os
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

from .build_execution import ProcessResult, StreamCapture, ToolIdentity
from .package_install import AppInstallReceipt
from .runtime import (
    BubblewrapRuntimeRunner,
    RuntimeControlEvidence,
    RuntimeSandboxPolicy,
)
from .sandbox import SandboxBackendIdentity
from .static_web import (
    StaticWebAdapterPlan,
    StaticWebServeRequest,
    plan_static_web_adapter,
)

BROWSER_SESSION_PLAN_SCHEMA_VERSION = "phios.browser_session_plan.v0.1"
BROWSER_SESSION_REVIEW_SCHEMA_VERSION = "phios.browser_session_plan_review.v0.1"
BROWSER_SESSION_RECEIPT_SCHEMA_VERSION = "phios.browser_session_receipt.v0.1"

BrowserSessionStatus = Literal["completed", "timed_out", "browser_failed"]
BrowserProfileMode = Literal["ephemeral"]
BrowserDisplayMode = Literal["headless"]
BrowserFamily = Literal["chromium"]

_BROWSER_TOOLS = {"chromium", "chromium-browser"}
_BROWSER_PERMISSIONS = (
    "browser.network.inherit",
    "browser.page.execute",
)
_LOOPBACK_HOST = "127.0.0.1"
_MIN_SESSION_SECONDS = 1
_MAX_SESSION_SECONDS = 300
_MIN_READINESS_TIMEOUT_MS = 250
_MAX_READINESS_TIMEOUT_MS = 10_000
_VIRTUAL_TIME_BUDGET_MS = 5_000


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
    url = _string(value, "browser loopback_url", maximum=256)
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
        raise ValueError("browser loopback_url must be plain reviewed 127.0.0.1 HTTP")
    if parsed.port is None or not 1024 <= parsed.port <= 65535:
        raise ValueError("browser loopback_url port is out of bounds")
    return url


def _browser_argv(browser_tool: str, loopback_url: str) -> tuple[str, ...]:
    return (
        browser_tool,
        "--headless=new",
        "--dump-dom",
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
        f"--virtual-time-budget={_VIRTUAL_TIME_BUDGET_MS}",
        "--user-data-dir=/home/phios/browser-profile",
        loopback_url,
    )


@dataclass(frozen=True)
class BrowserSessionPlan:
    app_id: str
    app_version: str
    static_web_plan_sha256: str
    install_receipt_sha256: str
    installed_tree_sha256: str
    static_root_sha256: str
    loopback_url: str
    static_serve_seconds: int
    browser_family: BrowserFamily
    browser_tool: str
    browser_mode: str
    profile_mode: BrowserProfileMode
    display_mode: BrowserDisplayMode
    requested_browser_permissions: tuple[str, ...]
    browser_argv: tuple[str, ...]
    policy: RuntimeSandboxPolicy
    session_seconds: int
    readiness_timeout_ms: int
    virtual_time_budget_ms: int
    launch_authority: bool = False
    page_execution_authority: bool = False
    display_authority: bool = False
    persistent_profile_authority: bool = False
    host_home_authority: bool = False
    schema_version: str = BROWSER_SESSION_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != BROWSER_SESSION_PLAN_SCHEMA_VERSION:
            raise ValueError(f"Unsupported browser session plan schema: {self.schema_version}")
        _string(self.app_id, "browser app_id", maximum=64)
        _string(self.app_version, "browser app_version", maximum=128)
        _sha256(self.static_web_plan_sha256, "static_web_plan_sha256")
        _sha256(self.install_receipt_sha256, "install_receipt_sha256")
        _sha256(self.installed_tree_sha256, "installed_tree_sha256")
        _sha256(self.static_root_sha256, "static_root_sha256")
        _validate_loopback_url(self.loopback_url)
        _int(
            self.static_serve_seconds,
            "static_serve_seconds",
            minimum=1,
            maximum=3600,
        )
        if self.browser_family != "chromium":
            raise ValueError("v0.36 supports only the Chromium browser family")
        if self.browser_tool not in _BROWSER_TOOLS:
            raise ValueError("v0.36 browser_tool must be chromium or chromium-browser")
        if self.browser_mode != "headless_dump_dom":
            raise ValueError("v0.36 supports only headless_dump_dom browser mode")
        if self.profile_mode != "ephemeral":
            raise ValueError("v0.36 browser profile must be ephemeral")
        if self.display_mode != "headless":
            raise ValueError("v0.36 does not grant GUI display authority")
        if self.requested_browser_permissions != _BROWSER_PERMISSIONS:
            raise ValueError("v0.36 browser permissions must match the fixed authority set")
        if self.browser_argv != _browser_argv(self.browser_tool, self.loopback_url):
            raise ValueError("browser argv does not match the v0.36 fixed Chromium contract")
        if self.policy.network_mode != "inherit":
            raise ValueError("v0.36 browser requires explicit host-network inheritance")
        _int(
            self.session_seconds,
            "browser session_seconds",
            minimum=_MIN_SESSION_SECONDS,
            maximum=_MAX_SESSION_SECONDS,
        )
        _int(
            self.readiness_timeout_ms,
            "browser readiness_timeout_ms",
            minimum=_MIN_READINESS_TIMEOUT_MS,
            maximum=_MAX_READINESS_TIMEOUT_MS,
        )
        readiness_seconds = (self.readiness_timeout_ms + 999) // 1000
        if self.session_seconds + readiness_seconds > self.static_serve_seconds:
            raise ValueError(
                "browser readiness + session window exceeds reviewed static serve window"
            )
        if self.virtual_time_budget_ms != _VIRTUAL_TIME_BUDGET_MS:
            raise ValueError("v0.36 virtual_time_budget_ms is fixed")
        if self.launch_authority is not False:
            raise ValueError("browser plans do not themselves grant launch authority")
        if self.page_execution_authority is not False:
            raise ValueError("browser plans do not themselves grant page execution authority")
        if self.display_authority is not False:
            raise ValueError("v0.36 browser plans never grant display authority")
        if self.persistent_profile_authority is not False:
            raise ValueError("v0.36 browser plans never grant persistent profile authority")
        if self.host_home_authority is not False:
            raise ValueError("v0.36 browser plans never grant host-home authority")

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
            "display_mode": self.display_mode,
            "requested_browser_permissions": list(self.requested_browser_permissions),
            "browser_argv": list(self.browser_argv),
            "policy": self.policy.to_dict(),
            "session_seconds": self.session_seconds,
            "readiness_timeout_ms": self.readiness_timeout_ms,
            "virtual_time_budget_ms": self.virtual_time_budget_ms,
            "launch_authority": self.launch_authority,
            "page_execution_authority": self.page_execution_authority,
            "display_authority": self.display_authority,
            "persistent_profile_authority": self.persistent_profile_authority,
            "host_home_authority": self.host_home_authority,
        }

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["browser_session_plan_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> BrowserSessionPlan:
        data = _mapping(value, "browser session plan")
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
            "display_mode",
            "requested_browser_permissions",
            "browser_argv",
            "policy",
            "session_seconds",
            "readiness_timeout_ms",
            "virtual_time_budget_ms",
            "launch_authority",
            "page_execution_authority",
            "display_authority",
            "persistent_profile_authority",
            "host_home_authority",
            "browser_session_plan_sha256",
        }
        if set(data) != expected:
            raise ValueError("browser session plan contains missing or unknown fields")
        permissions = data["requested_browser_permissions"]
        argv = data["browser_argv"]
        if not isinstance(permissions, list):
            raise ValueError("requested_browser_permissions must be an array")
        if not isinstance(argv, list):
            raise ValueError("browser_argv must be an array")
        plan = cls(
            schema_version=data["schema_version"],
            app_id=_string(data["app_id"], "browser app_id", maximum=64),
            app_version=_string(data["app_version"], "browser app_version", maximum=128),
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
            static_serve_seconds=data["static_serve_seconds"],
            browser_family=data["browser_family"],
            browser_tool=_string(data["browser_tool"], "browser_tool", maximum=64),
            browser_mode=_string(data["browser_mode"], "browser_mode", maximum=64),
            profile_mode=data["profile_mode"],
            display_mode=data["display_mode"],
            requested_browser_permissions=tuple(
                _string(item, "browser permission", maximum=128)
                for item in permissions
            ),
            browser_argv=tuple(
                _string(item, "browser argv item", maximum=1024)
                for item in argv
            ),
            policy=RuntimeSandboxPolicy.from_dict(data["policy"]),
            session_seconds=data["session_seconds"],
            readiness_timeout_ms=data["readiness_timeout_ms"],
            virtual_time_budget_ms=data["virtual_time_budget_ms"],
            launch_authority=data["launch_authority"],
            page_execution_authority=data["page_execution_authority"],
            display_authority=data["display_authority"],
            persistent_profile_authority=data["persistent_profile_authority"],
            host_home_authority=data["host_home_authority"],
        )
        if data["browser_session_plan_sha256"] != plan.sha256():
            raise ValueError("browser session plan digest does not match canonical plan")
        return plan


def plan_browser_session(
    static_web_plan_value: Any,
    *,
    browser_tool: str = "chromium",
    session_seconds: int = 60,
    readiness_timeout_ms: int = 3_000,
) -> BrowserSessionPlan:
    static_plan = StaticWebAdapterPlan.from_dict(static_web_plan_value)
    if static_plan.status != "ready_for_review":
        raise ValueError("browser planning requires a ready_for_review static-web plan")
    if static_plan.static_root_sha256 is None:
        raise ValueError("static-web plan lacks static-root identity")
    if browser_tool not in _BROWSER_TOOLS:
        raise ValueError("browser_tool must be chromium or chromium-browser")
    _int(
        session_seconds,
        "browser session_seconds",
        minimum=_MIN_SESSION_SECONDS,
        maximum=_MAX_SESSION_SECONDS,
    )
    _int(
        readiness_timeout_ms,
        "browser readiness_timeout_ms",
        minimum=_MIN_READINESS_TIMEOUT_MS,
        maximum=_MAX_READINESS_TIMEOUT_MS,
    )
    loopback_url = _loopback_url(static_plan)
    policy = RuntimeSandboxPolicy(
        network_mode="inherit",
        wall_clock_seconds=session_seconds,
        cpu_seconds=min(session_seconds, 300),
        address_space_bytes=4 * 1024 * 1024 * 1024,
        max_open_files=1024,
        max_file_size_bytes=128 * 1024 * 1024,
    )
    return BrowserSessionPlan(
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
        browser_mode="headless_dump_dom",
        profile_mode="ephemeral",
        display_mode="headless",
        requested_browser_permissions=_BROWSER_PERMISSIONS,
        browser_argv=_browser_argv(browser_tool, loopback_url),
        policy=policy,
        session_seconds=session_seconds,
        readiness_timeout_ms=readiness_timeout_ms,
        virtual_time_budget_ms=_VIRTUAL_TIME_BUDGET_MS,
        launch_authority=False,
        page_execution_authority=False,
        display_authority=False,
        persistent_profile_authority=False,
        host_home_authority=False,
    )


@dataclass(frozen=True)
class BrowserSessionReview:
    browser_session_plan_sha256: str
    app_id: str
    app_version: str
    static_web_plan_sha256: str
    loopback_url: str
    browser_family: str
    browser_tool: str
    browser_mode: str
    profile_mode: str
    display_mode: str
    requested_browser_permissions: tuple[str, ...]
    session_seconds: int
    readiness_timeout_ms: int
    launch_authority: bool
    page_execution_authority: bool
    display_authority: bool
    persistent_profile_authority: bool
    host_home_authority: bool
    schema_version: str = BROWSER_SESSION_REVIEW_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["requested_browser_permissions"] = list(self.requested_browser_permissions)
        return result


def review_browser_session(value: Any) -> BrowserSessionReview:
    plan = BrowserSessionPlan.from_dict(value)
    return BrowserSessionReview(
        browser_session_plan_sha256=plan.sha256(),
        app_id=plan.app_id,
        app_version=plan.app_version,
        static_web_plan_sha256=plan.static_web_plan_sha256,
        loopback_url=plan.loopback_url,
        browser_family=plan.browser_family,
        browser_tool=plan.browser_tool,
        browser_mode=plan.browser_mode,
        profile_mode=plan.profile_mode,
        display_mode=plan.display_mode,
        requested_browser_permissions=plan.requested_browser_permissions,
        session_seconds=plan.session_seconds,
        readiness_timeout_ms=plan.readiness_timeout_ms,
        launch_authority=plan.launch_authority,
        page_execution_authority=plan.page_execution_authority,
        display_authority=plan.display_authority,
        persistent_profile_authority=plan.persistent_profile_authority,
        host_home_authority=plan.host_home_authority,
    )


@dataclass(frozen=True)
class BrowserSessionRequest:
    plan: BrowserSessionPlan
    static_web_plan: StaticWebAdapterPlan
    install_receipt: AppInstallReceipt
    approved_browser_session_plan_sha256: str
    approved_static_web_plan_sha256: str
    approved_browser_permissions: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.approved_browser_session_plan_sha256 != self.plan.sha256():
            raise ValueError("Approved browser-session plan SHA-256 does not match canonical plan")
        if self.static_web_plan.sha256() != self.plan.static_web_plan_sha256:
            raise ValueError("static-web plan does not match browser-session plan")
        if self.approved_static_web_plan_sha256 != self.static_web_plan.sha256():
            raise ValueError("Approved static-web plan SHA-256 does not match canonical plan")
        if self.install_receipt.sha256() != self.plan.install_receipt_sha256:
            raise ValueError("install receipt does not match browser-session plan")
        if self.install_receipt.installed_tree_sha256 != self.plan.installed_tree_sha256:
            raise ValueError("install receipt tree does not match browser-session plan")
        if self.approved_browser_permissions != self.plan.requested_browser_permissions:
            raise ValueError(
                "Approved browser permissions must exactly match the reviewed browser plan"
            )

    @classmethod
    def from_payloads(
        cls,
        plan_value: Any,
        static_web_plan_value: Any,
        install_receipt_value: Any,
        *,
        approved_browser_session_plan_sha256: str,
        approved_static_web_plan_sha256: str,
        approved_browser_permissions: tuple[str, ...],
    ) -> BrowserSessionRequest:
        plan = BrowserSessionPlan.from_dict(plan_value)
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
            approved_browser_session_plan_sha256=_sha256(
                approved_browser_session_plan_sha256,
                "approved_browser_session_plan_sha256",
            ),
            approved_static_web_plan_sha256=_sha256(
                approved_static_web_plan_sha256,
                "approved_static_web_plan_sha256",
            ),
            approved_browser_permissions=approved,
        )


@dataclass(frozen=True)
class BrowserReadinessEvidence:
    ready: bool
    status_code: int
    attempts: int
    elapsed_ms: int
    port_available_before_spawn: bool

    def __post_init__(self) -> None:
        if self.ready is not True:
            raise ValueError("successful browser sessions require ready loopback evidence")
        _int(self.status_code, "readiness status_code", minimum=100, maximum=599)
        if self.status_code != 200:
            raise ValueError("v0.36 loopback readiness requires HTTP 200")
        _int(self.attempts, "readiness attempts", minimum=1, maximum=512)
        _int(self.elapsed_ms, "readiness elapsed_ms", minimum=0, maximum=60_000)
        if self.port_available_before_spawn is not True:
            raise ValueError("v0.36 requires the reviewed port to be free before server spawn")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BrowserSessionExecution:
    server_backend_identity: SandboxBackendIdentity
    server_tool_identity: ToolIdentity
    browser_backend_identity: SandboxBackendIdentity
    browser_tool_identity: ToolIdentity
    server_controls: RuntimeControlEvidence
    browser_controls: RuntimeControlEvidence
    readiness: BrowserReadinessEvidence
    server_result: ProcessResult
    browser_result: ProcessResult
    server_terminated_by_session: bool


class BrowserSessionRunner(Protocol):
    def execute(
        self,
        static_plan: StaticWebAdapterPlan,
        browser_plan: BrowserSessionPlan,
    ) -> BrowserSessionExecution: ...


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


class BubblewrapBrowserSessionRunner:
    def __init__(
        self,
        *,
        server_policy: RuntimeSandboxPolicy,
        browser_policy: RuntimeSandboxPolicy,
        static_root: Path,
        browser_root: Path,
    ) -> None:
        self.static_root = static_root.resolve(strict=True)
        self.browser_root = browser_root.resolve(strict=True)
        self.server_runner = BubblewrapRuntimeRunner(
            server_policy,
            payload_root=self.static_root,
            data_path=None,
        )
        self.browser_runner = BubblewrapRuntimeRunner(
            browser_policy,
            payload_root=self.browser_root,
            data_path=None,
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
                    elapsed_ms = int((time.monotonic() - started) * 1000)
                    return BrowserReadinessEvidence(
                        ready=True,
                        status_code=200,
                        attempts=attempts,
                        elapsed_ms=elapsed_ms,
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
        duration_ms = int((time.monotonic() - started) * 1000)
        assert process.returncode is not None
        return ProcessResult(
            exit_code=process.returncode,
            timed_out=False,
            duration_ms=duration_ms,
            stdout=stdout_capture.result(),
            stderr=stderr_capture.result(),
        )

    def execute(
        self,
        static_plan: StaticWebAdapterPlan,
        browser_plan: BrowserSessionPlan,
    ) -> BrowserSessionExecution:
        if static_plan.server_tool != "python3":
            raise ValueError("v0.36 requires the v0.35 trusted Python static server")
        if static_plan.loopback_host != _LOOPBACK_HOST:
            raise ValueError("v0.36 requires the v0.35 127.0.0.1 listener")
        if not self._port_available(static_plan.loopback_host, static_plan.loopback_port):
            raise ValueError("reviewed loopback port is already occupied before server spawn")

        server_backend = self.server_runner.preflight()
        server_tool = self.server_runner.probe_tool("python3")
        browser_backend = self.browser_runner.preflight()
        browser_tool = self.browser_runner.probe_tool(browser_plan.browser_tool)

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
                timeout_ms=browser_plan.readiness_timeout_ms,
            )
            browser_result = self.browser_runner.run_argv(
                browser_plan.browser_tool,
                browser_plan.browser_argv[1:],
                timeout_seconds=browser_plan.session_seconds,
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
        return BrowserSessionExecution(
            server_backend_identity=server_backend,
            server_tool_identity=server_tool,
            browser_backend_identity=browser_backend,
            browser_tool_identity=browser_tool,
            server_controls=server_controls,
            browser_controls=browser_controls,
            readiness=readiness,
            server_result=server_result,
            browser_result=browser_result,
            server_terminated_by_session=True,
        )


BrowserSessionRunnerFactory = Callable[
    [RuntimeSandboxPolicy, RuntimeSandboxPolicy, Path, Path],
    BrowserSessionRunner,
]


def _default_runner_factory(
    server_policy: RuntimeSandboxPolicy,
    browser_policy: RuntimeSandboxPolicy,
    static_root: Path,
    browser_root: Path,
) -> BrowserSessionRunner:
    return BubblewrapBrowserSessionRunner(
        server_policy=server_policy,
        browser_policy=browser_policy,
        static_root=static_root,
        browser_root=browser_root,
    )


@dataclass(frozen=True)
class BrowserSessionReceipt:
    receipt_id: str
    timestamp_utc: str
    app_id: str
    app_version: str
    browser_session_plan_sha256: str
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
    display_mode: str
    browser_policy: RuntimeSandboxPolicy
    server_backend_identity: SandboxBackendIdentity
    server_tool_identity: ToolIdentity
    browser_backend_identity: SandboxBackendIdentity
    browser_tool_identity: ToolIdentity
    server_controls: RuntimeControlEvidence
    browser_controls: RuntimeControlEvidence
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
    status: BrowserSessionStatus
    failure_reason: str | None
    page_execution_authority: bool
    browser_network_inherited: bool
    display_authority: bool
    persistent_profile_authority: bool
    host_home_authority: bool
    schema_version: str = BROWSER_SESSION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != BROWSER_SESSION_RECEIPT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported browser session receipt schema: {self.schema_version}")
        try:
            uuid.UUID(self.receipt_id)
        except ValueError as exc:
            raise ValueError("browser session receipt_id must be a UUID") from exc
        timestamp = datetime.fromisoformat(self.timestamp_utc)
        if timestamp.tzinfo is None:
            raise ValueError("browser session timestamp must include a timezone")
        for value, label in (
            (self.browser_session_plan_sha256, "browser_session_plan_sha256"),
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
        if self.approved_browser_permissions != _BROWSER_PERMISSIONS:
            raise ValueError("browser receipt permissions must match the v0.36 authority set")
        if self.browser_family != "chromium":
            raise ValueError("browser receipt family must be chromium")
        if self.browser_tool not in _BROWSER_TOOLS:
            raise ValueError("browser receipt tool is unsupported")
        if self.browser_mode != "headless_dump_dom":
            raise ValueError("browser receipt mode is unsupported")
        if self.profile_mode != "ephemeral" or self.display_mode != "headless":
            raise ValueError("browser receipt isolation mode does not match v0.36")
        if self.browser_policy.network_mode != "inherit":
            raise ValueError("browser receipt must record host-network inheritance")
        if not self.server_controls.host_network_inherited:
            raise ValueError("server controls must record host-network inheritance")
        if self.server_controls.network_namespace_enforced:
            raise ValueError("server controls must not claim a separate network namespace")
        if not self.server_controls.installed_payload_read_only:
            raise ValueError("server controls must record read-only static root")
        if self.server_controls.persistent_data_writable_mount:
            raise ValueError("server controls must not expose persistent app data")
        if not self.browser_controls.host_network_inherited:
            raise ValueError("browser controls must record host-network inheritance")
        if self.browser_controls.network_namespace_enforced:
            raise ValueError("browser controls must not claim a separate network namespace")
        if not self.browser_controls.private_home or not self.browser_controls.private_tmp:
            raise ValueError("browser controls require private home and tmp")
        if self.browser_controls.persistent_data_writable_mount:
            raise ValueError("browser controls must not expose persistent app data")
        if not self.server_terminated_by_session:
            raise ValueError("v0.36 coordinated session must terminate its static server")
        if self.page_execution_authority is not True:
            raise ValueError("completed browser session must record page execution authority")
        if self.browser_network_inherited is not True:
            raise ValueError("browser session must record broad host-network inheritance")
        if self.display_authority is not False:
            raise ValueError("v0.36 never grants display authority")
        if self.persistent_profile_authority is not False:
            raise ValueError("v0.36 never grants persistent profile authority")
        if self.host_home_authority is not False:
            raise ValueError("v0.36 never grants host-home authority")
        _int(self.server_duration_ms, "server_duration_ms", minimum=0, maximum=86_400_000)
        _int(self.browser_duration_ms, "browser_duration_ms", minimum=0, maximum=86_400_000)
        for byte_count, byte_count_label in (
            (self.server_stdout_byte_count, "server_stdout_byte_count"),
            (self.server_stderr_byte_count, "server_stderr_byte_count"),
            (self.browser_stdout_byte_count, "browser_stdout_byte_count"),
            (self.browser_stderr_byte_count, "browser_stderr_byte_count"),
        ):
            _int(
                byte_count,
                byte_count_label,
                minimum=0,
                maximum=2**63 - 1,
            )
        if not isinstance(self.browser_exit_code, int) or isinstance(self.browser_exit_code, bool):
            raise ValueError("browser_exit_code must be an integer")
        if not isinstance(self.server_exit_code, int) or isinstance(self.server_exit_code, bool):
            raise ValueError("server_exit_code must be an integer")
        if not isinstance(self.browser_timed_out, bool):
            raise ValueError("browser_timed_out must be boolean")
        if self.status == "completed":
            if self.browser_timed_out or self.browser_exit_code != 0:
                raise ValueError("completed browser session requires exit_code 0 without timeout")
            if self.failure_reason is not None:
                raise ValueError("completed browser session must not contain failure_reason")
        elif self.status == "timed_out":
            if not self.browser_timed_out:
                raise ValueError("timed_out browser session requires browser_timed_out=true")
        elif self.status == "browser_failed":
            if self.browser_timed_out or self.browser_exit_code == 0:
                raise ValueError("browser_failed requires nonzero exit code without timeout")
            if self.failure_reason is None:
                raise ValueError("browser_failed requires a failure_reason")
        else:
            raise ValueError("unsupported browser session status")

    def body_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["approved_browser_permissions"] = list(self.approved_browser_permissions)
        result["browser_policy"] = self.browser_policy.to_dict()
        result["server_backend_identity"] = self.server_backend_identity.to_dict()
        result["server_tool_identity"] = self.server_tool_identity.to_dict()
        result["browser_backend_identity"] = self.browser_backend_identity.to_dict()
        result["browser_tool_identity"] = self.browser_tool_identity.to_dict()
        result["server_controls"] = self.server_controls.to_dict()
        result["browser_controls"] = self.browser_controls.to_dict()
        result["readiness"] = self.readiness.to_dict()
        return result

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["browser_session_receipt_sha256"] = self.sha256()
        return result


@dataclass(frozen=True)
class BrowserSessionResult:
    receipt: BrowserSessionReceipt
    receipt_path: str
    receipt_persisted: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt": self.receipt.to_dict(),
            "receipt_path": self.receipt_path,
            "receipt_persisted": self.receipt_persisted,
        }


class BrowserSessionService:
    def __init__(
        self,
        *,
        runner_factory: BrowserSessionRunnerFactory | None = None,
    ) -> None:
        self.runner_factory = runner_factory or _default_runner_factory

    def run(
        self,
        request: BrowserSessionRequest,
        *,
        install_root: Path,
        session_root: Path,
        receipt_root: Path,
    ) -> BrowserSessionResult:
        plan = request.plan
        static_plan = request.static_web_plan
        current_static = plan_static_web_adapter(
            request.install_receipt.to_dict(),
            install_root=install_root,
            loopback_port=static_plan.loopback_port,
            serve_seconds=static_plan.serve_seconds,
        )
        if current_static.sha256() != static_plan.sha256():
            raise ValueError("static-web install binding changed after browser-plan review")
        if current_static.static_root_relative is None:
            raise ValueError("current static-web plan lacks a serveable root")
        static_root = (
            Path(current_static.install_path)
            / "payload"
            / current_static.static_root_relative
        )
        if static_root.is_symlink():
            raise ValueError("browser session static root must not be a symlink")
        static_root = static_root.resolve(strict=True)
        if not static_root.is_dir():
            raise ValueError("browser session static root is not a directory")

        sessions = session_root.expanduser()
        if sessions.is_symlink():
            raise ValueError("browser session root must not be a symlink")
        sessions.mkdir(parents=True, exist_ok=True)
        sessions = sessions.resolve(strict=True)
        scratch = Path(
            tempfile.mkdtemp(prefix=f"{plan.app_id}-", dir=sessions)
        ).resolve()
        browser_root = scratch / "browser-root"
        browser_root.mkdir()
        try:
            runner = self.runner_factory(
                static_plan.policy,
                plan.policy,
                static_root,
                browser_root,
            )
            execution = runner.execute(static_plan, plan)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

        if execution.browser_result.timed_out:
            status: BrowserSessionStatus = "timed_out"
            failure_reason = "browser session exceeded the reviewed wall-clock bound"
        elif execution.browser_result.exit_code == 0:
            status = "completed"
            failure_reason = None
        else:
            status = "browser_failed"
            failure_reason = (
                f"browser process exited with code {execution.browser_result.exit_code}"
            )

        receipt = BrowserSessionReceipt(
            receipt_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(UTC).isoformat(),
            app_id=plan.app_id,
            app_version=plan.app_version,
            browser_session_plan_sha256=plan.sha256(),
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
            display_mode=plan.display_mode,
            browser_policy=plan.policy,
            server_backend_identity=execution.server_backend_identity,
            server_tool_identity=execution.server_tool_identity,
            browser_backend_identity=execution.browser_backend_identity,
            browser_tool_identity=execution.browser_tool_identity,
            server_controls=execution.server_controls,
            browser_controls=execution.browser_controls,
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
            display_authority=False,
            persistent_profile_authority=False,
            host_filesystem_authority=False,
        )

        receipts = receipt_root.expanduser()
        if receipts.is_symlink():
            raise ValueError("browser receipt root must not be a symlink")
        receipts.mkdir(parents=True, exist_ok=True)
        receipts = receipts.resolve(strict=True)
        receipt_path = receipts / f"browser-session-{receipt.receipt_id}.json"
        _write_json_atomic(receipt_path, receipt.to_dict())
        return BrowserSessionResult(
            receipt=receipt,
            receipt_path=str(receipt_path),
            receipt_persisted=True,
        )
