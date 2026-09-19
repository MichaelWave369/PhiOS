from __future__ import annotations

import hashlib
import json
import os
import socket
import uuid
from pathlib import Path

import pytest

from phios.apps.browser_session import (
    BrowserReadinessEvidence,
    BrowserSessionExecution,
    BrowserSessionPlan,
    plan_browser_session,
)
from phios.apps.build_execution import ProcessResult, StreamCapture, ToolIdentity
from phios.apps.manifest import AppManifest
from phios.apps.package_install import (
    AppInstallReceipt,
    BuildPackagePlan,
    PackageArtifact,
    snapshot_installed_tree,
)
from phios.apps.runtime import RuntimeControlEvidence, RuntimeSandboxPolicy
from phios.apps.sandbox import SandboxBackendIdentity
from phios.apps.static_web import plan_static_web_adapter
from phios.apps.visible_browser import (
    VisibleBrowserExecution,
    VisibleBrowserSessionPlan,
    VisibleBrowserSessionReceipt,
    VisibleBrowserSessionRequest,
    VisibleBrowserSessionService,
    WaylandBubblewrapRuntimeRunner,
    WaylandDisplayEvidence,
    inspect_wayland_socket,
    plan_visible_browser_session,
    review_visible_browser_session,
)


def _manifest() -> AppManifest:
    return AppManifest.from_dict(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "phi.visible-example",
            "name": "Visible Example",
            "version": "1.0.0",
            "description": "Visible browser fixture",
            "source": {
                "repository_url": "https://github.com/example/visible-example",
                "license_expression": "MIT",
                "redistribution": "permitted",
            },
            "entrypoint": {"runtime": "node", "target": "package.json"},
            "permissions": [],
        }
    )


def _install(tmp_path: Path) -> tuple[AppInstallReceipt, Path]:
    manifest = _manifest()
    install_root = tmp_path / "installed"
    install_path = install_root / manifest.app_id / manifest.version / "artifactprefix"
    payload = install_path / "payload"
    metadata = install_path / ".phios"
    dist = payload / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    metadata.mkdir()
    (dist / "index.html").write_text("<html><body>PhiOS GUI</body></html>", encoding="utf-8")
    (assets / "app.js").write_text("console.log('gui')", encoding="utf-8")

    artifacts: list[PackageArtifact] = []
    for path in sorted(dist.rglob("*")):
        if path.is_file():
            artifacts.append(
                PackageArtifact(
                    path=path.relative_to(payload).as_posix(),
                    byte_count=path.stat().st_size,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            )
    artifact_tuple = tuple(artifacts)
    digest = hashlib.sha256()
    for artifact in artifact_tuple:
        digest.update(artifact.canonical_line())
    package_plan = BuildPackagePlan(
        app_id=manifest.app_id,
        app_version=manifest.version,
        manifest_sha256=manifest.sha256(),
        registry_snapshot_sha256="1" * 64,
        repository_url=manifest.source.repository_url,
        commit_sha="a" * 40,
        build_plan_sha256="2" * 64,
        execution_receipt_sha256="3" * 64,
        offline_build_receipt_sha256="4" * 64,
        artifact_set_sha256=digest.hexdigest(),
        artifacts=artifact_tuple,
        install_relative_path=f"{manifest.app_id}/{manifest.version}/artifactprefix",
        launch_authority=False,
    )
    (metadata / "package-plan.json").write_text(
        json.dumps(package_plan.to_dict(), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    (metadata / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    payload_sha, count, total = snapshot_installed_tree(payload)
    tree_sha, _, _ = snapshot_installed_tree(install_path)
    receipt = AppInstallReceipt(
        receipt_id=str(uuid.uuid4()),
        timestamp_utc="2026-09-19T07:00:00+00:00",
        app_id=manifest.app_id,
        app_version=manifest.version,
        package_plan_sha256=package_plan.sha256(),
        manifest_sha256=manifest.sha256(),
        registry_snapshot_sha256="1" * 64,
        build_plan_sha256="2" * 64,
        execution_receipt_sha256="3" * 64,
        offline_build_receipt_sha256="4" * 64,
        artifact_set_sha256=payload_sha,
        installed_payload_sha256=payload_sha,
        installed_tree_sha256=tree_sha,
        artifact_count=count,
        total_bytes=total,
        install_path=str(install_path.resolve()),
        launch_authority=False,
        status="installed",
    )
    return receipt, install_root


def _wayland_socket(tmp_path: Path, name: str = "wayland-0") -> tuple[socket.socket, Path]:
    path = tmp_path / name
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(path))
    return sock, path.resolve()


def _capture(content: bytes = b"") -> StreamCapture:
    return StreamCapture(
        byte_count=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        preview="",
        preview_truncated=bool(content),
    )


def _backend(label: str) -> SandboxBackendIdentity:
    raw = f"bubblewrap {label}".encode()
    return SandboxBackendIdentity(
        backend="bubblewrap",
        executable_path="/usr/bin/bwrap",
        version=f"bubblewrap {label}",
        version_output_sha256=hashlib.sha256(raw).hexdigest(),
        platform_system="Linux",
        platform_machine="x86_64",
    )


def _tool(name: str) -> ToolIdentity:
    raw = f"{name} test".encode()
    return ToolIdentity(
        logical_tool=name,
        executable_path=f"/usr/bin/{name}",
        version=f"{name} test",
        version_output_sha256=hashlib.sha256(raw).hexdigest(),
    )


def _controls(*, wall_clock: bool) -> RuntimeControlEvidence:
    return RuntimeControlEvidence(
        mount_namespace_enforced=True,
        user_namespace_enforced=True,
        pid_namespace_enforced=True,
        ipc_namespace_enforced=True,
        uts_namespace_enforced=True,
        private_proc=True,
        private_dev=True,
        private_tmp=True,
        private_home=True,
        installed_payload_read_only=True,
        persistent_data_writable_mount=False,
        host_system_roots_read_only=True,
        network_namespace_enforced=False,
        host_network_inherited=True,
        wall_clock_timeout_enforced=wall_clock,
        cpu_rlimit_enforced=True,
        address_space_rlimit_enforced=True,
        open_files_rlimit_enforced=True,
        file_size_rlimit_enforced=True,
        seccomp_enforced=False,
        network_allowlist_enforced=False,
        parent_death_enforced=True,
    )


class FakeVisibleRunner:
    def __init__(
        self,
        server_policy: RuntimeSandboxPolicy,
        browser_policy: RuntimeSandboxPolicy,
        static_root: Path,
        browser_root: Path,
        wayland_socket: object,
        *,
        timed_out: bool = False,
    ) -> None:
        self.server_policy = server_policy
        self.browser_policy = browser_policy
        self.static_root = static_root
        self.browser_root = browser_root
        self.wayland_socket = wayland_socket
        self.timed_out = timed_out

    def execute(
        self,
        static_plan: object,
        visible_plan: VisibleBrowserSessionPlan,
    ) -> VisibleBrowserExecution:
        browser = BrowserSessionExecution(
            server_backend_identity=_backend("server"),
            server_tool_identity=_tool("python3"),
            browser_backend_identity=_backend("browser"),
            browser_tool_identity=_tool("chromium"),
            server_controls=_controls(wall_clock=False),
            browser_controls=_controls(wall_clock=True),
            readiness=BrowserReadinessEvidence(
                ready=True,
                status_code=200,
                attempts=2,
                elapsed_ms=50,
                port_available_before_spawn=True,
            ),
            server_result=ProcessResult(
                exit_code=-15,
                timed_out=False,
                duration_ms=1000,
                stdout=_capture(),
                stderr=_capture(),
            ),
            browser_result=ProcessResult(
                exit_code=-9 if self.timed_out else 0,
                timed_out=self.timed_out,
                duration_ms=500,
                stdout=_capture(),
                stderr=_capture(),
            ),
            server_terminated_by_session=True,
        )
        identity = visible_plan.wayland_socket
        display = WaylandDisplayEvidence(
            transport="wayland",
            host_socket_path=identity.host_path,
            host_socket_device=identity.device,
            host_socket_inode=identity.inode,
            host_socket_ctime_ns=identity.ctime_ns,
            host_socket_owner_uid=identity.owner_uid,
            host_socket_owner_gid=identity.owner_gid,
            sandbox_socket_path=identity.sandbox_path,
            exact_socket_bind=True,
            host_runtime_directory_mounted=False,
            wayland_environment_set=True,
            display_authority_granted=True,
            gpu_device_authority=False,
            x11_authority=False,
        )
        return VisibleBrowserExecution(browser=browser, display=display)


def _plans(
    tmp_path: Path,
    wayland_path: Path,
) -> tuple[AppInstallReceipt, Path, object, BrowserSessionPlan, VisibleBrowserSessionPlan]:
    receipt, install_root = _install(tmp_path)
    static_plan = plan_static_web_adapter(
        receipt.to_dict(),
        install_root=install_root,
        loopback_port=9201,
        serve_seconds=120,
    )
    browser_plan = plan_browser_session(
        static_plan.to_dict(),
        browser_tool="chromium",
        session_seconds=30,
        readiness_timeout_ms=2500,
    )
    visible = plan_visible_browser_session(
        browser_plan.to_dict(),
        wayland_socket_path=wayland_path,
    )
    return receipt, install_root, static_plan, browser_plan, visible


def test_wayland_socket_identity_binds_device_inode_and_owner(tmp_path: Path) -> None:
    sock, path = _wayland_socket(tmp_path)
    try:
        identity = inspect_wayland_socket(path)
        metadata = path.stat()
        assert identity.host_path == str(path)
        assert identity.display_name == "wayland-0"
        assert identity.device == metadata.st_dev
        assert identity.inode == metadata.st_ino
        assert identity.ctime_ns == metadata.st_ctime_ns
        assert identity.owner_uid == os.getuid()
        assert identity.owner_gid == metadata.st_gid
        assert identity.sandbox_path == "/run/phios-wayland/wayland-0"
    finally:
        sock.close()


def test_visible_plan_adds_only_wayland_display_authority(tmp_path: Path) -> None:
    sock, path = _wayland_socket(tmp_path)
    try:
        _, _, _, parent, plan = _plans(tmp_path / "case", path)
        review = review_visible_browser_session(plan.to_dict())

        assert plan.parent_browser_session_plan_sha256 == parent.sha256()
        assert plan.browser_mode == "visible_app_window"
        assert plan.display_transport == "wayland"
        assert plan.requested_browser_permissions == (
            "browser.display.wayland",
            "browser.network.inherit",
            "browser.page.execute",
        )
        assert "--ozone-platform=wayland" in plan.browser_argv
        assert "--headless=new" not in plan.browser_argv
        assert "--dump-dom" not in plan.browser_argv
        assert f"--app={plan.loopback_url}" in plan.browser_argv
        assert plan.launch_authority is False
        assert plan.page_execution_authority is False
        assert plan.display_authority is False
        assert plan.persistent_profile_authority is False
        assert plan.host_home_authority is False
        assert plan.gpu_device_authority is False
        assert plan.x11_authority is False
        assert review.visible_browser_plan_sha256 == plan.sha256()
        assert VisibleBrowserSessionPlan.from_dict(plan.to_dict()) == plan
    finally:
        sock.close()


def test_visible_request_requires_exact_three_plan_approvals(tmp_path: Path) -> None:
    sock, path = _wayland_socket(tmp_path)
    try:
        receipt, _, static_plan, parent, plan = _plans(tmp_path / "case", path)
        request = VisibleBrowserSessionRequest.from_payloads(
            plan.to_dict(),
            parent.to_dict(),
            static_plan.to_dict(),
            receipt.to_dict(),
            approved_visible_browser_plan_sha256=plan.sha256(),
            approved_parent_browser_plan_sha256=parent.sha256(),
            approved_static_web_plan_sha256=static_plan.sha256(),
            approved_browser_permissions=plan.requested_browser_permissions,
        )
        assert request.plan == plan

        with pytest.raises(ValueError, match="visible-browser"):
            VisibleBrowserSessionRequest.from_payloads(
                plan.to_dict(),
                parent.to_dict(),
                static_plan.to_dict(),
                receipt.to_dict(),
                approved_visible_browser_plan_sha256="0" * 64,
                approved_parent_browser_plan_sha256=parent.sha256(),
                approved_static_web_plan_sha256=static_plan.sha256(),
                approved_browser_permissions=plan.requested_browser_permissions,
            )
    finally:
        sock.close()


def test_visible_request_requires_exact_permission_set(tmp_path: Path) -> None:
    sock, path = _wayland_socket(tmp_path)
    try:
        receipt, _, static_plan, parent, plan = _plans(tmp_path / "case", path)
        with pytest.raises(ValueError, match="exactly match"):
            VisibleBrowserSessionRequest.from_payloads(
                plan.to_dict(),
                parent.to_dict(),
                static_plan.to_dict(),
                receipt.to_dict(),
                approved_visible_browser_plan_sha256=plan.sha256(),
                approved_parent_browser_plan_sha256=parent.sha256(),
                approved_static_web_plan_sha256=static_plan.sha256(),
                approved_browser_permissions=(
                    "browser.network.inherit",
                    "browser.page.execute",
                ),
            )
    finally:
        sock.close()


def test_wayland_socket_replacement_invalidates_review(tmp_path: Path) -> None:
    sock, path = _wayland_socket(tmp_path)
    receipt, install_root, static_plan, parent, plan = _plans(tmp_path / "case", path)
    request = VisibleBrowserSessionRequest.from_payloads(
        plan.to_dict(),
        parent.to_dict(),
        static_plan.to_dict(),
        receipt.to_dict(),
        approved_visible_browser_plan_sha256=plan.sha256(),
        approved_parent_browser_plan_sha256=parent.sha256(),
        approved_static_web_plan_sha256=static_plan.sha256(),
        approved_browser_permissions=plan.requested_browser_permissions,
    )
    sock.close()
    path.unlink()
    replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    replacement.bind(str(path))
    try:
        replaced_identity = inspect_wayland_socket(path)
        assert replaced_identity != plan.wayland_socket
        with pytest.raises(ValueError, match="identity changed"):
            VisibleBrowserSessionService(
                runner_factory=lambda a, b, c, d, e: FakeVisibleRunner(a, b, c, d, e)
            ).run(
                request,
                install_root=install_root,
                session_root=tmp_path / "sessions",
                receipt_root=tmp_path / "receipts",
            )
    finally:
        replacement.close()


def test_wayland_runner_mounts_only_exact_socket(tmp_path: Path) -> None:
    sock, path = _wayland_socket(tmp_path)
    browser_root = tmp_path / "browser-root"
    browser_root.mkdir()
    try:
        identity = inspect_wayland_socket(path)
        runner = WaylandBubblewrapRuntimeRunner(
            RuntimeSandboxPolicy(network_mode="inherit"),
            payload_root=browser_root,
            wayland_socket=identity,
        )
        runner.bwrap_path = "/usr/bin/bwrap"
        runner.prlimit_path = "/usr/bin/prlimit"
        command = runner.command_for(
            executable_path="/usr/bin/chromium",
            argv_tail=("--version",),
        )
        host_index = command.index(str(path))
        assert command[host_index - 1] == "--ro-bind"
        assert command[host_index + 1] == identity.sandbox_path
        assert str(path.parent) not in command
        assert "WAYLAND_DISPLAY" in command
        assert identity.sandbox_path in command
        assert "XDG_SESSION_TYPE" in command
        assert "wayland" in command
        assert "--unshare-net" not in command
    finally:
        sock.close()


def test_visible_session_records_display_authority_and_no_gpu_x11(
    tmp_path: Path,
) -> None:
    sock, path = _wayland_socket(tmp_path)
    try:
        receipt, install_root, static_plan, parent, plan = _plans(tmp_path / "case", path)
        request = VisibleBrowserSessionRequest.from_payloads(
            plan.to_dict(),
            parent.to_dict(),
            static_plan.to_dict(),
            receipt.to_dict(),
            approved_visible_browser_plan_sha256=plan.sha256(),
            approved_parent_browser_plan_sha256=parent.sha256(),
            approved_static_web_plan_sha256=static_plan.sha256(),
            approved_browser_permissions=plan.requested_browser_permissions,
        )
        result = VisibleBrowserSessionService(
            runner_factory=lambda a, b, c, d, e: FakeVisibleRunner(a, b, c, d, e)
        ).run(
            request,
            install_root=install_root,
            session_root=tmp_path / "sessions",
            receipt_root=tmp_path / "receipts",
        )

        assert result.receipt.status == "completed"
        assert result.receipt.page_execution_authority is True
        assert result.receipt.browser_network_inherited is True
        assert result.receipt.display_authority is True
        assert result.receipt.display_evidence.exact_socket_bind is True
        assert result.receipt.display_evidence.host_runtime_directory_mounted is False
        assert result.receipt.persistent_profile_authority is False
        assert result.receipt.host_home_authority is False
        assert result.receipt.gpu_device_authority is False
        assert result.receipt.x11_authority is False
        assert result.receipt.browser_controls.private_home is True
        assert result.receipt.browser_controls.private_tmp is True
        assert result.receipt.browser_controls.host_network_inherited is True
        assert VisibleBrowserSessionReceipt.from_dict(
            result.receipt.to_dict()
        ) == result.receipt
        assert result.receipt_persisted is True
        assert Path(result.receipt_path).is_file()
    finally:
        sock.close()


def test_visible_session_timeout_preserves_display_boundary(tmp_path: Path) -> None:
    sock, path = _wayland_socket(tmp_path)
    try:
        receipt, install_root, static_plan, parent, plan = _plans(tmp_path / "case", path)
        request = VisibleBrowserSessionRequest.from_payloads(
            plan.to_dict(),
            parent.to_dict(),
            static_plan.to_dict(),
            receipt.to_dict(),
            approved_visible_browser_plan_sha256=plan.sha256(),
            approved_parent_browser_plan_sha256=parent.sha256(),
            approved_static_web_plan_sha256=static_plan.sha256(),
            approved_browser_permissions=plan.requested_browser_permissions,
        )
        result = VisibleBrowserSessionService(
            runner_factory=lambda a, b, c, d, e: FakeVisibleRunner(
                a,
                b,
                c,
                d,
                e,
                timed_out=True,
            )
        ).run(
            request,
            install_root=install_root,
            session_root=tmp_path / "sessions",
            receipt_root=tmp_path / "receipts",
        )
        assert result.receipt.status == "timed_out"
        assert result.receipt.display_authority is True
        assert result.receipt.gpu_device_authority is False
    finally:
        sock.close()


def test_non_socket_wayland_path_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "wayland-0"
    path.write_text("not a socket", encoding="utf-8")

    with pytest.raises(ValueError, match="Unix socket"):
        inspect_wayland_socket(path)


def test_visible_browser_receipt_rejects_digest_tampering(tmp_path: Path) -> None:
    sock, path = _wayland_socket(tmp_path)
    try:
        receipt, install_root, static_plan, parent, plan = _plans(tmp_path / "case", path)
        request = VisibleBrowserSessionRequest.from_payloads(
            plan.to_dict(),
            parent.to_dict(),
            static_plan.to_dict(),
            receipt.to_dict(),
            approved_visible_browser_plan_sha256=plan.sha256(),
            approved_parent_browser_plan_sha256=parent.sha256(),
            approved_static_web_plan_sha256=static_plan.sha256(),
            approved_browser_permissions=plan.requested_browser_permissions,
        )
        result = VisibleBrowserSessionService(
            runner_factory=lambda a, b, c, d, e: FakeVisibleRunner(a, b, c, d, e)
        ).run(
            request,
            install_root=install_root,
            session_root=tmp_path / "sessions",
            receipt_root=tmp_path / "receipts",
        )
        payload = result.receipt.to_dict()
        payload["static_root_sha256"] = "0" * 64

        with pytest.raises(ValueError, match="digest"):
            VisibleBrowserSessionReceipt.from_dict(payload)
    finally:
        sock.close()
