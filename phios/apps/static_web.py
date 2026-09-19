from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Literal, Protocol, cast

from .build_execution import ProcessResult, ToolIdentity
from .package_install import AppInstallReceipt, BuildPackagePlan, snapshot_installed_tree
from .runtime import (
    BubblewrapRuntimeRunner,
    RuntimeControlEvidence,
    RuntimeSandboxPolicy,
    _verify_install,
)
from .sandbox import SandboxBackendIdentity

STATIC_WEB_ADAPTER_PLAN_SCHEMA_VERSION = "phios.static_web_adapter_plan.v0.1"
STATIC_WEB_ADAPTER_REVIEW_SCHEMA_VERSION = "phios.static_web_adapter_plan_review.v0.1"
STATIC_WEB_SERVE_RECEIPT_SCHEMA_VERSION = "phios.static_web_serve_receipt.v0.1"

StaticWebStatus = Literal[
    "ready_for_review",
    "unsupported_manifest_runtime",
    "unsupported_output",
    "ambiguous_output",
]

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_LOOPBACK_HOST = "127.0.0.1"
_DEFAULT_PORT = 8787
_DEFAULT_SERVE_SECONDS = 300
_MAX_SERVE_SECONDS = 3600
_SUPPORTED_MANIFEST_RUNTIMES = {"node", "static_web"}
_CANDIDATE_INDEXES = (
    ("dist/index.html", "dist", "vite_dist_index"),
    ("build/index.html", "build", "react_build_index"),
)


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
class StaticWebAdapterPlan:
    app_id: str
    app_version: str
    install_receipt_sha256: str
    manifest_sha256: str
    installed_tree_sha256: str
    package_plan_sha256: str
    install_path: str
    manifest_runtime: str
    manifest_target: str
    deferred_manifest_permissions: tuple[str, ...]
    static_root_relative: str | None
    static_root_sha256: str | None
    static_file_count: int
    static_total_bytes: int
    index_relative: str | None
    mapping_rule: str | None
    loopback_host: str
    loopback_port: int
    serve_seconds: int
    server_tool: str | None
    server_argv: tuple[str, ...]
    policy: RuntimeSandboxPolicy
    status: StaticWebStatus
    notes: tuple[str, ...]
    browser_launch_authority: bool = False
    application_code_executed_by_server: bool = False
    launch_authority: bool = False
    schema_version: str = STATIC_WEB_ADAPTER_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != STATIC_WEB_ADAPTER_PLAN_SCHEMA_VERSION:
            raise ValueError(f"Unsupported static-web adapter plan schema: {self.schema_version}")
        _string(self.app_id, "static-web app_id", maximum=64)
        _string(self.app_version, "static-web app_version", maximum=128)
        _sha256(self.install_receipt_sha256, "install_receipt_sha256")
        _sha256(self.manifest_sha256, "manifest_sha256")
        _sha256(self.installed_tree_sha256, "installed_tree_sha256")
        _sha256(self.package_plan_sha256, "package_plan_sha256")
        if not Path(self.install_path).is_absolute():
            raise ValueError("static-web install_path must be absolute")
        if tuple(sorted(self.deferred_manifest_permissions)) != self.deferred_manifest_permissions:
            raise ValueError("deferred manifest permissions must be sorted")
        if len(set(self.deferred_manifest_permissions)) != len(
            self.deferred_manifest_permissions
        ):
            raise ValueError("deferred manifest permissions must not contain duplicates")
        if self.loopback_host != _LOOPBACK_HOST:
            raise ValueError("v0.35 static-web host must be 127.0.0.1")
        _int(self.loopback_port, "loopback_port", minimum=1024, maximum=65535)
        _int(
            self.serve_seconds,
            "serve_seconds",
            minimum=1,
            maximum=_MAX_SERVE_SECONDS,
        )
        if self.policy.network_mode != "inherit":
            raise ValueError("v0.35 static-web server requires host network inheritance")
        if self.status not in {
            "ready_for_review",
            "unsupported_manifest_runtime",
            "unsupported_output",
            "ambiguous_output",
        }:
            raise ValueError("unsupported static-web adapter status")
        if self.browser_launch_authority is not False:
            raise ValueError("v0.35 never grants browser launch authority")
        if self.application_code_executed_by_server is not False:
            raise ValueError("v0.35 server must not execute application code")
        if self.launch_authority is not False:
            raise ValueError("static-web adapter plans do not themselves grant serve authority")

        if self.status == "ready_for_review":
            if self.manifest_runtime not in _SUPPORTED_MANIFEST_RUNTIMES:
                raise ValueError("ready static-web plan has unsupported manifest runtime")
            if self.static_root_relative not in {"dist", "build"}:
                raise ValueError("ready static-web plan has unsupported static root")
            if self.index_relative != "index.html":
                raise ValueError("ready static-web plan requires index.html")
            if self.mapping_rule not in {"vite_dist_index", "react_build_index"}:
                raise ValueError("ready static-web plan has unsupported mapping rule")
            if self.static_root_sha256 is None:
                raise ValueError("ready static-web plan requires static-root digest")
            _sha256(self.static_root_sha256, "static_root_sha256")
            _int(self.static_file_count, "static_file_count", minimum=1, maximum=65536)
            _int(
                self.static_total_bytes,
                "static_total_bytes",
                minimum=1,
                maximum=512 * 1024 * 1024,
            )
            if self.server_tool != "python3":
                raise ValueError("v0.35 static-web server tool must be python3")
            expected_argv = (
                "python3",
                "-m",
                "http.server",
                str(self.loopback_port),
                "--bind",
                self.loopback_host,
                "--directory",
                "/app",
            )
            if self.server_argv != expected_argv:
                raise ValueError("static-web server argv does not match v0.35 contract")
        else:
            if self.static_root_relative is not None:
                raise ValueError("unsupported static-web plan must not name a static root")
            if self.static_root_sha256 is not None:
                raise ValueError("unsupported static-web plan must not contain root digest")
            if self.static_file_count != 0 or self.static_total_bytes != 0:
                raise ValueError("unsupported static-web plan must not contain static totals")
            if self.index_relative is not None or self.mapping_rule is not None:
                raise ValueError("unsupported static-web plan must not contain mapping evidence")
            if self.server_tool is not None or self.server_argv:
                raise ValueError("unsupported static-web plan must not contain server argv")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app_id": self.app_id,
            "app_version": self.app_version,
            "install_receipt_sha256": self.install_receipt_sha256,
            "manifest_sha256": self.manifest_sha256,
            "installed_tree_sha256": self.installed_tree_sha256,
            "package_plan_sha256": self.package_plan_sha256,
            "install_path": self.install_path,
            "manifest_runtime": self.manifest_runtime,
            "manifest_target": self.manifest_target,
            "deferred_manifest_permissions": list(self.deferred_manifest_permissions),
            "static_root_relative": self.static_root_relative,
            "static_root_sha256": self.static_root_sha256,
            "static_file_count": self.static_file_count,
            "static_total_bytes": self.static_total_bytes,
            "index_relative": self.index_relative,
            "mapping_rule": self.mapping_rule,
            "loopback_host": self.loopback_host,
            "loopback_port": self.loopback_port,
            "serve_seconds": self.serve_seconds,
            "server_tool": self.server_tool,
            "server_argv": list(self.server_argv),
            "policy": self.policy.to_dict(),
            "status": self.status,
            "notes": list(self.notes),
            "browser_launch_authority": self.browser_launch_authority,
            "application_code_executed_by_server": self.application_code_executed_by_server,
            "launch_authority": self.launch_authority,
        }

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["static_web_plan_sha256"] = self.sha256()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> StaticWebAdapterPlan:
        data = _mapping(value, "static-web adapter plan")
        expected = {
            "schema_version",
            "app_id",
            "app_version",
            "install_receipt_sha256",
            "manifest_sha256",
            "installed_tree_sha256",
            "package_plan_sha256",
            "install_path",
            "manifest_runtime",
            "manifest_target",
            "deferred_manifest_permissions",
            "static_root_relative",
            "static_root_sha256",
            "static_file_count",
            "static_total_bytes",
            "index_relative",
            "mapping_rule",
            "loopback_host",
            "loopback_port",
            "serve_seconds",
            "server_tool",
            "server_argv",
            "policy",
            "status",
            "notes",
            "browser_launch_authority",
            "application_code_executed_by_server",
            "launch_authority",
            "static_web_plan_sha256",
        }
        if set(data) != expected:
            raise ValueError("static-web adapter plan contains missing or unknown fields")
        permissions = data["deferred_manifest_permissions"]
        argv = data["server_argv"]
        notes = data["notes"]
        if not isinstance(permissions, list):
            raise ValueError("deferred_manifest_permissions must be an array")
        if not isinstance(argv, list):
            raise ValueError("server_argv must be an array")
        if not isinstance(notes, list):
            raise ValueError("static-web notes must be an array")
        root_sha = data["static_root_sha256"]
        if root_sha is not None:
            root_sha = _sha256(root_sha, "static_root_sha256")
        optional_fields: dict[str, str | None] = {}
        for key in ("static_root_relative", "index_relative", "mapping_rule", "server_tool"):
            item = data[key]
            optional_fields[key] = (
                None if item is None else _string(item, key, maximum=512)
            )
        plan = cls(
            schema_version=data["schema_version"],
            app_id=_string(data["app_id"], "static-web app_id", maximum=64),
            app_version=_string(data["app_version"], "static-web app_version", maximum=128),
            install_receipt_sha256=_sha256(
                data["install_receipt_sha256"],
                "install_receipt_sha256",
            ),
            manifest_sha256=_sha256(data["manifest_sha256"], "manifest_sha256"),
            installed_tree_sha256=_sha256(
                data["installed_tree_sha256"],
                "installed_tree_sha256",
            ),
            package_plan_sha256=_sha256(
                data["package_plan_sha256"],
                "package_plan_sha256",
            ),
            install_path=_string(data["install_path"], "static-web install_path", maximum=4096),
            manifest_runtime=_string(
                data["manifest_runtime"],
                "manifest_runtime",
                maximum=32,
            ),
            manifest_target=_string(data["manifest_target"], "manifest_target", maximum=512),
            deferred_manifest_permissions=tuple(
                _string(item, "deferred manifest permission", maximum=128)
                for item in permissions
            ),
            static_root_relative=optional_fields["static_root_relative"],
            static_root_sha256=root_sha,
            static_file_count=data["static_file_count"],
            static_total_bytes=data["static_total_bytes"],
            index_relative=optional_fields["index_relative"],
            mapping_rule=optional_fields["mapping_rule"],
            loopback_host=_string(data["loopback_host"], "loopback_host", maximum=64),
            loopback_port=data["loopback_port"],
            serve_seconds=data["serve_seconds"],
            server_tool=optional_fields["server_tool"],
            server_argv=tuple(_string(item, "server argv item", maximum=2048) for item in argv),
            policy=RuntimeSandboxPolicy.from_dict(data["policy"]),
            status=data["status"],
            notes=tuple(_string(item, "static-web note", maximum=512) for item in notes),
            browser_launch_authority=data["browser_launch_authority"],
            application_code_executed_by_server=data["application_code_executed_by_server"],
            launch_authority=data["launch_authority"],
        )
        if data["static_web_plan_sha256"] != plan.sha256():
            raise ValueError("static-web adapter plan digest does not match canonical plan")
        return plan


@dataclass(frozen=True)
class StaticWebAdapterReview:
    static_web_plan_sha256: str
    app_id: str
    app_version: str
    install_receipt_sha256: str
    installed_tree_sha256: str
    static_root_relative: str | None
    static_root_sha256: str | None
    mapping_rule: str | None
    loopback_url: str
    serve_seconds: int
    deferred_manifest_permissions: tuple[str, ...]
    status: StaticWebStatus
    browser_launch_authority: bool
    application_code_executed_by_server: bool
    launch_authority: bool
    schema_version: str = STATIC_WEB_ADAPTER_REVIEW_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["deferred_manifest_permissions"] = list(self.deferred_manifest_permissions)
        return result


def _load_package_plan(install_path: Path, receipt: AppInstallReceipt) -> BuildPackagePlan:
    path = install_path / ".phios" / "package-plan.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError("installed package-plan metadata is unavailable or unsafe")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("installed package-plan metadata is invalid JSON") from exc
    plan = BuildPackagePlan.from_dict(value)
    if plan.sha256() != receipt.package_plan_sha256:
        raise ValueError("installed package plan does not match install receipt")
    if plan.app_id != receipt.app_id or plan.app_version != receipt.app_version:
        raise ValueError("installed package plan identity does not match install receipt")
    if plan.manifest_sha256 != receipt.manifest_sha256:
        raise ValueError("installed package plan manifest does not match install receipt")
    return plan


def plan_static_web_adapter(
    install_receipt_value: Any,
    *,
    install_root: Path,
    loopback_port: int = _DEFAULT_PORT,
    serve_seconds: int = _DEFAULT_SERVE_SECONDS,
) -> StaticWebAdapterPlan:
    _int(loopback_port, "loopback_port", minimum=1024, maximum=65535)
    _int(serve_seconds, "serve_seconds", minimum=1, maximum=_MAX_SERVE_SECONDS)
    verified = _verify_install(install_receipt_value, install_root=install_root)
    package_plan = _load_package_plan(verified.install_path, verified.receipt)
    manifest = verified.manifest
    permissions = tuple(sorted(manifest.permissions))
    notes: list[str] = [
        "v0.35 trusted server serves static files only; browser launch is not authorized",
        "manifest runtime permissions are recorded but not granted to the trusted server",
        "server inherits host network only to expose a reviewed 127.0.0.1 listener",
    ]
    policy = RuntimeSandboxPolicy(
        network_mode="inherit",
        wall_clock_seconds=serve_seconds,
        cpu_seconds=min(serve_seconds, 300),
        address_space_bytes=1024 * 1024 * 1024,
        max_open_files=256,
        max_file_size_bytes=64 * 1024 * 1024,
    )

    if manifest.entrypoint.runtime not in _SUPPORTED_MANIFEST_RUNTIMES:
        return StaticWebAdapterPlan(
            app_id=manifest.app_id,
            app_version=manifest.version,
            install_receipt_sha256=verified.receipt.sha256(),
            manifest_sha256=manifest.sha256(),
            installed_tree_sha256=verified.receipt.installed_tree_sha256,
            package_plan_sha256=package_plan.sha256(),
            install_path=str(verified.install_path),
            manifest_runtime=manifest.entrypoint.runtime,
            manifest_target=manifest.entrypoint.target,
            deferred_manifest_permissions=permissions,
            static_root_relative=None,
            static_root_sha256=None,
            static_file_count=0,
            static_total_bytes=0,
            index_relative=None,
            mapping_rule=None,
            loopback_host=_LOOPBACK_HOST,
            loopback_port=loopback_port,
            serve_seconds=serve_seconds,
            server_tool=None,
            server_argv=(),
            policy=policy,
            status="unsupported_manifest_runtime",
            notes=tuple(notes + ["manifest runtime is not eligible for static-web mapping"]),
        )

    artifact_paths = {artifact.path for artifact in package_plan.artifacts}
    candidates = [
        (index_path, root, rule)
        for index_path, root, rule in _CANDIDATE_INDEXES
        if index_path in artifact_paths
    ]
    if not candidates:
        return StaticWebAdapterPlan(
            app_id=manifest.app_id,
            app_version=manifest.version,
            install_receipt_sha256=verified.receipt.sha256(),
            manifest_sha256=manifest.sha256(),
            installed_tree_sha256=verified.receipt.installed_tree_sha256,
            package_plan_sha256=package_plan.sha256(),
            install_path=str(verified.install_path),
            manifest_runtime=manifest.entrypoint.runtime,
            manifest_target=manifest.entrypoint.target,
            deferred_manifest_permissions=permissions,
            static_root_relative=None,
            static_root_sha256=None,
            static_file_count=0,
            static_total_bytes=0,
            index_relative=None,
            mapping_rule=None,
            loopback_host=_LOOPBACK_HOST,
            loopback_port=loopback_port,
            serve_seconds=serve_seconds,
            server_tool=None,
            server_argv=(),
            policy=policy,
            status="unsupported_output",
            notes=tuple(notes + ["no receipted dist/index.html or build/index.html artifact was observed"]),
        )
    if len(candidates) != 1:
        return StaticWebAdapterPlan(
            app_id=manifest.app_id,
            app_version=manifest.version,
            install_receipt_sha256=verified.receipt.sha256(),
            manifest_sha256=manifest.sha256(),
            installed_tree_sha256=verified.receipt.installed_tree_sha256,
            package_plan_sha256=package_plan.sha256(),
            install_path=str(verified.install_path),
            manifest_runtime=manifest.entrypoint.runtime,
            manifest_target=manifest.entrypoint.target,
            deferred_manifest_permissions=permissions,
            static_root_relative=None,
            static_root_sha256=None,
            static_file_count=0,
            static_total_bytes=0,
            index_relative=None,
            mapping_rule=None,
            loopback_host=_LOOPBACK_HOST,
            loopback_port=loopback_port,
            serve_seconds=serve_seconds,
            server_tool=None,
            server_argv=(),
            policy=policy,
            status="ambiguous_output",
            notes=tuple(notes + ["multiple recognized static output roots were receipted"]),
        )

    _, root_relative, mapping_rule = candidates[0]
    static_root = verified.payload_path / root_relative
    if static_root.is_symlink():
        raise ValueError("static-web output root must not be a symlink")
    static_root = static_root.resolve(strict=True)
    payload_root = verified.payload_path.resolve(strict=True)
    if payload_root != static_root and payload_root not in static_root.parents:
        raise ValueError("static-web output root escaped installed payload")
    if not static_root.is_dir():
        raise ValueError("static-web output root is not a directory")
    index = static_root / "index.html"
    if index.is_symlink() or not index.is_file():
        raise ValueError("static-web index.html is unavailable or unsafe")
    root_sha, file_count, total_bytes = snapshot_installed_tree(static_root)

    argv = (
        "python3",
        "-m",
        "http.server",
        str(loopback_port),
        "--bind",
        _LOOPBACK_HOST,
        "--directory",
        "/app",
    )
    return StaticWebAdapterPlan(
        app_id=manifest.app_id,
        app_version=manifest.version,
        install_receipt_sha256=verified.receipt.sha256(),
        manifest_sha256=manifest.sha256(),
        installed_tree_sha256=verified.receipt.installed_tree_sha256,
        package_plan_sha256=package_plan.sha256(),
        install_path=str(verified.install_path),
        manifest_runtime=manifest.entrypoint.runtime,
        manifest_target=manifest.entrypoint.target,
        deferred_manifest_permissions=permissions,
        static_root_relative=root_relative,
        static_root_sha256=root_sha,
        static_file_count=file_count,
        static_total_bytes=total_bytes,
        index_relative="index.html",
        mapping_rule=mapping_rule,
        loopback_host=_LOOPBACK_HOST,
        loopback_port=loopback_port,
        serve_seconds=serve_seconds,
        server_tool="python3",
        server_argv=argv,
        policy=policy,
        status="ready_for_review",
        notes=tuple(notes + [f"static root selected by reviewed artifact rule: {mapping_rule}"]),
    )


def review_static_web_adapter(value: Any) -> StaticWebAdapterReview:
    plan = StaticWebAdapterPlan.from_dict(value)
    return StaticWebAdapterReview(
        static_web_plan_sha256=plan.sha256(),
        app_id=plan.app_id,
        app_version=plan.app_version,
        install_receipt_sha256=plan.install_receipt_sha256,
        installed_tree_sha256=plan.installed_tree_sha256,
        static_root_relative=plan.static_root_relative,
        static_root_sha256=plan.static_root_sha256,
        mapping_rule=plan.mapping_rule,
        loopback_url=f"http://{plan.loopback_host}:{plan.loopback_port}/",
        serve_seconds=plan.serve_seconds,
        deferred_manifest_permissions=plan.deferred_manifest_permissions,
        status=plan.status,
        browser_launch_authority=plan.browser_launch_authority,
        application_code_executed_by_server=plan.application_code_executed_by_server,
        launch_authority=plan.launch_authority,
    )


@dataclass(frozen=True)
class StaticWebServeRequest:
    plan: StaticWebAdapterPlan
    install_receipt: AppInstallReceipt
    approved_static_web_plan_sha256: str

    def __post_init__(self) -> None:
        if self.plan.status != "ready_for_review":
            raise ValueError("only ready_for_review static-web plans are serveable")
        if self.approved_static_web_plan_sha256 != self.plan.sha256():
            raise ValueError("Approved static-web plan SHA-256 does not match canonical plan")
        if self.install_receipt.sha256() != self.plan.install_receipt_sha256:
            raise ValueError("install receipt does not match static-web plan")
        if self.install_receipt.installed_tree_sha256 != self.plan.installed_tree_sha256:
            raise ValueError("install receipt tree does not match static-web plan")

    @classmethod
    def from_payloads(
        cls,
        plan_value: Any,
        install_receipt_value: Any,
        *,
        approved_static_web_plan_sha256: str,
    ) -> StaticWebServeRequest:
        return cls(
            plan=StaticWebAdapterPlan.from_dict(plan_value),
            install_receipt=AppInstallReceipt.from_dict(install_receipt_value),
            approved_static_web_plan_sha256=_sha256(
                approved_static_web_plan_sha256,
                "approved_static_web_plan_sha256",
            ),
        )


class StaticWebServerRunner(Protocol):
    policy: RuntimeSandboxPolicy

    def preflight(self) -> SandboxBackendIdentity: ...

    def probe_tool(self, executable_tool: str) -> ToolIdentity: ...

    def run_argv(
        self,
        executable_tool: str,
        argv_tail: tuple[str, ...],
        *,
        timeout_seconds: int,
    ) -> ProcessResult: ...

    def control_evidence(self) -> RuntimeControlEvidence: ...


StaticWebRunnerFactory = Callable[
    [RuntimeSandboxPolicy, Path],
    StaticWebServerRunner,
]


def _default_runner(
    policy: RuntimeSandboxPolicy,
    static_root: Path,
) -> StaticWebServerRunner:
    return BubblewrapRuntimeRunner(
        policy,
        payload_root=static_root,
        data_path=None,
    )


@dataclass(frozen=True)
class StaticWebServeReceipt:
    receipt_id: str
    timestamp_utc: str
    app_id: str
    app_version: str
    static_web_plan_sha256: str
    install_receipt_sha256: str
    installed_tree_sha256: str
    package_plan_sha256: str
    static_root_sha256: str
    mapping_rule: str
    loopback_url: str
    serve_seconds: int
    policy: RuntimeSandboxPolicy
    backend_identity: SandboxBackendIdentity
    controls: RuntimeControlEvidence
    server_tool_identity: ToolIdentity
    exit_code: int
    timed_out: bool
    duration_ms: int
    stdout_byte_count: int
    stdout_sha256: str
    stderr_byte_count: int
    stderr_sha256: str
    status: str
    failure_reason: str | None
    browser_launch_authority: bool
    application_code_executed_by_server: bool
    schema_version: str = STATIC_WEB_SERVE_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != STATIC_WEB_SERVE_RECEIPT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported static-web serve receipt schema: {self.schema_version}")
        try:
            uuid.UUID(self.receipt_id)
        except ValueError as exc:
            raise ValueError("static-web receipt_id must be a UUID") from exc
        parsed = datetime.fromisoformat(self.timestamp_utc)
        if parsed.tzinfo is None:
            raise ValueError("static-web receipt timestamp must include a timezone")
        for value, label in (
            (self.static_web_plan_sha256, "static_web_plan_sha256"),
            (self.install_receipt_sha256, "install_receipt_sha256"),
            (self.installed_tree_sha256, "installed_tree_sha256"),
            (self.package_plan_sha256, "package_plan_sha256"),
            (self.static_root_sha256, "static_root_sha256"),
            (self.stdout_sha256, "stdout_sha256"),
            (self.stderr_sha256, "stderr_sha256"),
        ):
            _sha256(value, label)
        _int(self.serve_seconds, "serve_seconds", minimum=1, maximum=_MAX_SERVE_SECONDS)
        _int(self.duration_ms, "duration_ms", minimum=0, maximum=86_400_000)
        if self.policy.network_mode != "inherit":
            raise ValueError("static-web receipt requires host-network policy")
        if not self.controls.host_network_inherited:
            raise ValueError("static-web receipt requires host-network inheritance evidence")
        if self.controls.network_namespace_enforced:
            raise ValueError("static-web receipt must not claim a separate network namespace")
        if not self.controls.installed_payload_read_only:
            raise ValueError("static-web receipt requires read-only site root evidence")
        if self.controls.persistent_data_writable_mount:
            raise ValueError("static-web server must not receive persistent app-data mount")
        if self.browser_launch_authority is not False:
            raise ValueError("static-web receipt must not grant browser launch authority")
        if self.application_code_executed_by_server is not False:
            raise ValueError("static-web server must not execute application code")
        if self.status not in {"serve_window_complete", "server_exited", "server_failed"}:
            raise ValueError("unsupported static-web serve status")
        if self.status == "serve_window_complete" and not self.timed_out:
            raise ValueError("serve_window_complete requires timed_out=true")
        if self.status != "serve_window_complete" and self.timed_out:
            raise ValueError("timed_out=true requires serve_window_complete")

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "timestamp_utc": self.timestamp_utc,
            "app_id": self.app_id,
            "app_version": self.app_version,
            "static_web_plan_sha256": self.static_web_plan_sha256,
            "install_receipt_sha256": self.install_receipt_sha256,
            "installed_tree_sha256": self.installed_tree_sha256,
            "package_plan_sha256": self.package_plan_sha256,
            "static_root_sha256": self.static_root_sha256,
            "mapping_rule": self.mapping_rule,
            "loopback_url": self.loopback_url,
            "serve_seconds": self.serve_seconds,
            "policy": self.policy.to_dict(),
            "backend_identity": self.backend_identity.to_dict(),
            "controls": self.controls.to_dict(),
            "server_tool_identity": self.server_tool_identity.to_dict(),
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "duration_ms": self.duration_ms,
            "stdout_byte_count": self.stdout_byte_count,
            "stdout_sha256": self.stdout_sha256,
            "stderr_byte_count": self.stderr_byte_count,
            "stderr_sha256": self.stderr_sha256,
            "status": self.status,
            "failure_reason": self.failure_reason,
            "browser_launch_authority": self.browser_launch_authority,
            "application_code_executed_by_server": self.application_code_executed_by_server,
        }

    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.body_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = self.body_dict()
        result["static_web_receipt_sha256"] = self.sha256()
        return result


@dataclass(frozen=True)
class StaticWebServeResult:
    receipt: StaticWebServeReceipt
    receipt_path: str
    receipt_persisted: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt": self.receipt.to_dict(),
            "receipt_path": self.receipt_path,
            "receipt_persisted": self.receipt_persisted,
        }


class StaticWebAdapterService:
    def __init__(
        self,
        *,
        runner_factory: StaticWebRunnerFactory | None = None,
    ) -> None:
        self.runner_factory = runner_factory or _default_runner

    def serve(
        self,
        request: StaticWebServeRequest,
        *,
        install_root: Path,
        receipt_root: Path,
    ) -> StaticWebServeResult:
        plan = request.plan
        verified = _verify_install(
            request.install_receipt.to_dict(),
            install_root=install_root,
        )
        if verified.receipt.sha256() != plan.install_receipt_sha256:
            raise ValueError("current install receipt does not match static-web plan")
        if verified.receipt.installed_tree_sha256 != plan.installed_tree_sha256:
            raise ValueError("current installed tree does not match static-web plan")
        package_plan = _load_package_plan(verified.install_path, verified.receipt)
        if package_plan.sha256() != plan.package_plan_sha256:
            raise ValueError("current package plan does not match static-web plan")
        if plan.static_root_relative is None or plan.static_root_sha256 is None:
            raise ValueError("static-web plan lacks a serveable root")
        static_root = verified.payload_path / plan.static_root_relative
        if static_root.is_symlink():
            raise ValueError("static-web root must not be a symlink")
        static_root = static_root.resolve(strict=True)
        payload = verified.payload_path.resolve(strict=True)
        if payload != static_root and payload not in static_root.parents:
            raise ValueError("static-web root escaped installed payload")
        root_sha, file_count, total_bytes = snapshot_installed_tree(static_root)
        if root_sha != plan.static_root_sha256:
            raise ValueError("static-web root changed after plan review")
        if file_count != plan.static_file_count or total_bytes != plan.static_total_bytes:
            raise ValueError("static-web root totals changed after plan review")
        index = static_root / "index.html"
        if index.is_symlink() or not index.is_file():
            raise ValueError("static-web index.html is unavailable before serve")

        runner = self.runner_factory(plan.policy, static_root)
        backend = runner.preflight()
        assert plan.server_tool is not None
        tool = runner.probe_tool(plan.server_tool)
        process = runner.run_argv(
            plan.server_tool,
            plan.server_argv[1:],
            timeout_seconds=plan.serve_seconds,
        )
        controls = runner.control_evidence()
        if not controls.host_network_inherited or controls.network_namespace_enforced:
            raise ValueError("static-web runner network evidence does not match reviewed plan")
        if not controls.installed_payload_read_only:
            raise ValueError("static-web runner did not keep site root read-only")
        if controls.persistent_data_writable_mount:
            raise ValueError("static-web runner unexpectedly exposed persistent app data")

        if process.timed_out:
            status = "serve_window_complete"
            failure_reason = None
        elif process.exit_code == 0:
            status = "server_exited"
            failure_reason = None
        else:
            status = "server_failed"
            failure_reason = f"static-web server exited with code {process.exit_code}"

        receipt = StaticWebServeReceipt(
            receipt_id=str(uuid.uuid4()),
            timestamp_utc=datetime.now(UTC).isoformat(),
            app_id=plan.app_id,
            app_version=plan.app_version,
            static_web_plan_sha256=plan.sha256(),
            install_receipt_sha256=plan.install_receipt_sha256,
            installed_tree_sha256=plan.installed_tree_sha256,
            package_plan_sha256=plan.package_plan_sha256,
            static_root_sha256=plan.static_root_sha256,
            mapping_rule=cast(str, plan.mapping_rule),
            loopback_url=f"http://{plan.loopback_host}:{plan.loopback_port}/",
            serve_seconds=plan.serve_seconds,
            policy=plan.policy,
            backend_identity=backend,
            controls=controls,
            server_tool_identity=tool,
            exit_code=process.exit_code,
            timed_out=process.timed_out,
            duration_ms=process.duration_ms,
            stdout_byte_count=process.stdout.byte_count,
            stdout_sha256=process.stdout.sha256,
            stderr_byte_count=process.stderr.byte_count,
            stderr_sha256=process.stderr.sha256,
            status=status,
            failure_reason=failure_reason,
            browser_launch_authority=False,
            application_code_executed_by_server=False,
        )

        receipts = receipt_root.expanduser()
        if receipts.is_symlink():
            raise ValueError("static-web receipt root must not be a symlink")
        receipts.mkdir(parents=True, exist_ok=True)
        receipts = receipts.resolve(strict=True)
        receipt_path = receipts / f"static-web-{receipt.receipt_id}.json"
        _write_json_atomic(receipt_path, receipt.to_dict())
        return StaticWebServeResult(
            receipt=receipt,
            receipt_path=str(receipt_path),
            receipt_persisted=True,
        )
