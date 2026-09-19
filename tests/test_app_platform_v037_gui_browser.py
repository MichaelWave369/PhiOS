from __future__ import annotations

import hashlib
import json
import socket
import uuid
from pathlib import Path
from typing import cast

import pytest

from phios.apps.browser_session import BrowserReadinessEvidence
from phios.apps.build_execution import ProcessResult, StreamCapture, ToolIdentity
from phios.apps.gui_session import (
    BubblewrapGuiBrowserRunner,
    GuiBrowserExecution,
    GuiBrowserPlan,
    GuiBrowserReceipt,
    GuiBrowserRequest,
    GuiBrowserService,
    GuiDisplayEvidence,
    WaylandSocketIdentity,
    plan_gui_browser,
    review_gui_browser,
)
from phios.apps.manifest import AppManifest
from phios.apps.package_install import (
    AppInstallReceipt,
    BuildPackagePlan,
    PackageArtifact,
    snapshot_installed_tree,
)
from phios.apps.runtime import (
    BubblewrapRuntimeRunner,
    RuntimeControlEvidence,
    RuntimeSandboxPolicy,
)
from phios.apps.sandbox import SandboxBackendIdentity
from phios.apps.static_web import plan_static_web_adapter


def _wayland_socket(tmp_path: Path, name: str = "wayland-0") -> tuple[socket.socket, Path]:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    path = runtime / name
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    return server, path


def _manifest() -> AppManifest:
    return AppManifest.from_dict(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "phi.gui-example",
            "name": "GUI Example",
            "version": "1.0.0",
            "description": "GUI contract fixture",
            "source": {
                "repository_url": "https://github.com/example/gui-example",
                "license_expression": "MIT",
                "redistribution": "permitted",
            },
            "entrypoint": {"runtime": "node", "target": "package.json"},
            "permissions": [],
        }
    )


def _install(tmp_path: Path) -> tuple[AppInstallReceipt, Path, Path]:
    manifest = _manifest()
    install_root = tmp_path / "installed"
    install_path = install_root / manifest.app_id / manifest.version / "artifactprefix"
    payload = install_path / "payload"
    dist = payload / "dist"
    assets = dist / "assets"
    metadata = install_path / ".phios"
    assets.mkdir(parents=True)
    metadata.mkdir()

    (dist / "index.html").write_text("<html>gui</html>", encoding="utf-8")
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
    artifacts_tuple = tuple(artifacts)
    digest = hashlib.sha256()
    for artifact in artifacts_tuple:
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
        artifacts=artifacts_tuple,
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

    payload_sha, artifact_count, total_bytes = snapshot_installed_tree(payload)
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
        artifact_count=artifact_count,
        total_bytes=total_bytes,
        install_path=str(install_path.resolve()),
        launch_authority=False,
        status="installed",
    )
    return receipt, install_root, install_path


def _capture(content: bytes = b"") -> StreamCapture:
    return StreamCapture(
        byte_count=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        preview="",
        preview_truncated=bool(content),
    )


def _controls(*, browser: bool) -> RuntimeControlEvidence:
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
        wall_clock_timeout_enforced=browser,
        cpu_rlimit_enforced=True,
        address_space_rlimit_enforced=True,
        open_files_rlimit_enforced=True,
        file_size_rlimit_enforced=True,
        seccomp_enforced=False,
        network_allowlist_enforced=False,
        parent_death_enforced=True,
    )


class FakeGuiRunner:
    def __init__(self, plan: GuiBrowserPlan) -> None:
        self.plan = plan
        self.calls = 0

    def execute(self, static_plan: object, gui_plan: GuiBrowserPlan) -> GuiBrowserExecution:
        self.calls += 1
        assert gui_plan == self.plan
        backend = SandboxBackendIdentity(
            backend="bubblewrap",
            executable_path="/usr/bin/bwrap",
            version="bubblewrap test",
            version_output_sha256=hashlib.sha256(b"bubblewrap").hexdigest(),
            platform_system="Linux",
            platform_machine="x86_64",
        )
        python = ToolIdentity(
            logical_tool="python3",
            executable_path="/usr/bin/python3",
            version="Python test",
            version_output_sha256=hashlib.sha256(b"python").hexdigest(),
        )
        chromium = ToolIdentity(
            logical_tool=gui_plan.browser_tool,
            executable_path=f"/usr/bin/{gui_plan.browser_tool}",
            version="Chromium test",
            version_output_sha256=hashlib.sha256(b"chromium").hexdigest(),
        )
        return GuiBrowserExecution(
            server_backend_identity=backend,
            server_tool_identity=python,
            browser_backend_identity=backend,
            browser_tool_identity=chromium,
            server_controls=_controls(browser=False),
            browser_controls=_controls(browser=True),
            display=GuiDisplayEvidence(
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
            ),
            readiness=BrowserReadinessEvidence(
                ready=True,
                status_code=200,
                attempts=1,
                elapsed_ms=1,
                port_available_before_spawn=True,
            ),
            server_result=ProcessResult(
                exit_code=-15,
                timed_out=False,
                duration_ms=100,
                stdout=_capture(),
                stderr=_capture(),
            ),
            browser_result=ProcessResult(
                exit_code=-1,
                timed_out=True,
                duration_ms=gui_plan.session_seconds * 1000,
                stdout=_capture(),
                stderr=_capture(),
            ),
            server_terminated_by_session=True,
        )


def _static_plan(tmp_path: Path):
    receipt, install_root, install_path = _install(tmp_path)
    static = plan_static_web_adapter(
        receipt.to_dict(),
        install_root=install_root,
        loopback_port=9010,
        serve_seconds=90,
    )
    return receipt, install_root, install_path, static


def test_wayland_plan_binds_real_socket_instance(tmp_path: Path) -> None:
    receipt, _, _, static = _static_plan(tmp_path)
    server, path = _wayland_socket(tmp_path)
    try:
        plan = plan_gui_browser(
            static.to_dict(),
            wayland_socket_path=path,
            session_seconds=30,
            readiness_timeout_ms=2000,
        )
    finally:
        server.close()

    assert plan.app_id == receipt.app_id
    assert plan.display_transport == "wayland"
    assert plan.wayland.host_path == str(path.resolve())
    assert plan.wayland.inode > 0
    assert plan.wayland.sandbox_socket_path == "/run/user/phios/wayland-0"
    assert plan.requested_browser_permissions == (
        "browser.display.wayland",
        "browser.network.inherit",
        "browser.page.execute",
    )
    assert "--headless=new" not in plan.browser_argv
    assert "--ozone-platform=wayland" in plan.browser_argv
    assert f"--app={plan.loopback_url}" in plan.browser_argv
    assert plan.display_authority is False
    assert plan.gpu_device_authority is False
    assert plan.dbus_authority is False
    assert GuiBrowserPlan.from_dict(plan.to_dict()) == plan


def test_gui_review_exposes_display_authority_without_granting_it(tmp_path: Path) -> None:
    _, _, _, static = _static_plan(tmp_path)
    server, path = _wayland_socket(tmp_path)
    try:
        plan = plan_gui_browser(static.to_dict(), wayland_socket_path=path)
        review = review_gui_browser(plan.to_dict())
    finally:
        server.close()

    assert review.gui_browser_plan_sha256 == plan.sha256()
    assert review.display_transport == "wayland"
    assert review.display_authority is False
    assert review.gpu_device_authority is False
    assert review.dbus_authority is False


def test_non_socket_wayland_path_is_rejected(tmp_path: Path) -> None:
    _, _, _, static = _static_plan(tmp_path)
    fake = tmp_path / "wayland-0"
    fake.write_text("not a socket", encoding="utf-8")

    with pytest.raises(ValueError, match="Unix-domain socket"):
        plan_gui_browser(static.to_dict(), wayland_socket_path=fake)


def test_replacing_wayland_socket_invalidates_reviewed_identity(tmp_path: Path) -> None:
    _, _, _, static = _static_plan(tmp_path)
    server, path = _wayland_socket(tmp_path)
    plan = plan_gui_browser(static.to_dict(), wayland_socket_path=path)
    server.close()
    path.unlink()
    replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    replacement.bind(str(path))
    try:
        with pytest.raises(ValueError, match="instance changed"):
            plan.wayland.verify_current()
    finally:
        replacement.close()


def test_gui_request_requires_exact_permissions_and_plan_sha(tmp_path: Path) -> None:
    receipt, _, _, static = _static_plan(tmp_path)
    server, path = _wayland_socket(tmp_path)
    try:
        plan = plan_gui_browser(static.to_dict(), wayland_socket_path=path)
        request = GuiBrowserRequest.from_payloads(
            plan.to_dict(),
            static.to_dict(),
            receipt.to_dict(),
            approved_gui_browser_plan_sha256=plan.sha256(),
            approved_static_web_plan_sha256=static.sha256(),
            approved_browser_permissions=plan.requested_browser_permissions,
        )
        assert request.plan == plan

        with pytest.raises(ValueError, match="Approved GUI browser plan"):
            GuiBrowserRequest.from_payloads(
                plan.to_dict(),
                static.to_dict(),
                receipt.to_dict(),
                approved_gui_browser_plan_sha256="0" * 64,
                approved_static_web_plan_sha256=static.sha256(),
                approved_browser_permissions=plan.requested_browser_permissions,
            )

        with pytest.raises(ValueError, match="exactly match"):
            GuiBrowserRequest.from_payloads(
                plan.to_dict(),
                static.to_dict(),
                receipt.to_dict(),
                approved_gui_browser_plan_sha256=plan.sha256(),
                approved_static_web_plan_sha256=static.sha256(),
                approved_browser_permissions=(
                    "browser.network.inherit",
                    "browser.page.execute",
                ),
            )
    finally:
        server.close()


def test_runtime_runner_mounts_only_reviewed_wayland_socket(tmp_path: Path) -> None:
    payload = tmp_path / "payload"
    payload.mkdir()
    server, path = _wayland_socket(tmp_path)
    try:
        runner = BubblewrapRuntimeRunner(
            RuntimeSandboxPolicy(network_mode="inherit"),
            payload_root=payload,
            data_path=None,
            bwrap_path="/usr/bin/bwrap",
            prlimit_path="/usr/bin/prlimit",
            extra_read_only_binds=((path, "/run/user/phios/wayland-0"),),
            extra_environment={
                "XDG_RUNTIME_DIR": "/run/user/phios",
                "WAYLAND_DISPLAY": "wayland-0",
            },
        )
        command = runner.command_for(
            executable_path="/usr/bin/true",
            argv_tail=(),
        )
    finally:
        server.close()

    socket_index = command.index(str(path.resolve()))
    assert command[socket_index - 1] == "--ro-bind"
    assert command[socket_index + 1] == "/run/user/phios/wayland-0"
    assert "/run/user/phios" in command
    assert "XDG_RUNTIME_DIR" in command
    assert "WAYLAND_DISPLAY" in command
    assert "/run/user/1000" not in command
    assert "/dev/dri" not in command


def test_runtime_runner_rejects_unbounded_extra_bind_target(tmp_path: Path) -> None:
    payload = tmp_path / "payload"
    payload.mkdir()
    server, path = _wayland_socket(tmp_path)
    try:
        with pytest.raises(ValueError, match="must be under"):
            BubblewrapRuntimeRunner(
                RuntimeSandboxPolicy(),
                payload_root=payload,
                data_path=None,
                extra_read_only_binds=((path, "/home/phios/wayland-0"),),
            )
    finally:
        server.close()


def test_runtime_runner_cannot_override_reserved_environment(tmp_path: Path) -> None:
    payload = tmp_path / "payload"
    payload.mkdir()

    with pytest.raises(ValueError, match="reserved"):
        BubblewrapRuntimeRunner(
            RuntimeSandboxPolicy(),
            payload_root=payload,
            data_path=None,
            extra_environment={"HOME": "/host/home"},
        )


def test_gui_service_records_display_authority_and_bounded_timeout(tmp_path: Path) -> None:
    receipt, install_root, _, static = _static_plan(tmp_path)
    server, path = _wayland_socket(tmp_path)
    created: list[FakeGuiRunner] = []
    try:
        plan = plan_gui_browser(
            static.to_dict(),
            wayland_socket_path=path,
            session_seconds=12,
            readiness_timeout_ms=1000,
        )
        request = GuiBrowserRequest.from_payloads(
            plan.to_dict(),
            static.to_dict(),
            receipt.to_dict(),
            approved_gui_browser_plan_sha256=plan.sha256(),
            approved_static_web_plan_sha256=static.sha256(),
            approved_browser_permissions=plan.requested_browser_permissions,
        )

        def factory(
            server_policy: RuntimeSandboxPolicy,
            browser_policy: RuntimeSandboxPolicy,
            static_root: Path,
            browser_root: Path,
            gui_plan: GuiBrowserPlan,
        ) -> FakeGuiRunner:
            assert server_policy.network_mode == "inherit"
            assert browser_policy.network_mode == "inherit"
            assert static_root.name == "dist"
            assert browser_root.is_dir()
            runner = FakeGuiRunner(gui_plan)
            created.append(runner)
            return runner

        result = GuiBrowserService(runner_factory=factory).run(
            request,
            install_root=install_root,
            session_root=tmp_path / "sessions",
            receipt_root=tmp_path / "receipts",
        )
    finally:
        server.close()

    assert result.receipt.status == "visible_window_complete"
    assert result.receipt.display_authority is True
    assert result.receipt.page_execution_authority is True
    assert result.receipt.browser_network_inherited is True
    assert result.receipt.persistent_profile_authority is False
    assert result.receipt.host_home_authority is False
    assert result.receipt.gpu_device_authority is False
    assert result.receipt.dbus_authority is False
    assert result.receipt.display.socket_bound_read_only is True
    assert result.receipt.display.host_runtime_directory_mounted is False
    assert result.receipt.display.dbus_socket_mounted is False
    assert result.receipt.display.gpu_device_mounted is False
    assert GuiBrowserReceipt.from_dict(result.receipt.to_dict()) == result.receipt
    assert result.receipt_persisted is True
    assert Path(result.receipt_path).is_file()
    assert created[0].calls == 1


def test_gui_service_rechecks_socket_before_execution(tmp_path: Path) -> None:
    receipt, install_root, _, static = _static_plan(tmp_path)
    server, path = _wayland_socket(tmp_path)
    plan = plan_gui_browser(static.to_dict(), wayland_socket_path=path)
    request = GuiBrowserRequest.from_payloads(
        plan.to_dict(),
        static.to_dict(),
        receipt.to_dict(),
        approved_gui_browser_plan_sha256=plan.sha256(),
        approved_static_web_plan_sha256=static.sha256(),
        approved_browser_permissions=plan.requested_browser_permissions,
    )
    server.close()
    path.unlink()
    replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    replacement.bind(str(path))
    try:
        with pytest.raises(ValueError, match="instance changed"):
            GuiBrowserService(
                runner_factory=lambda *args: FakeGuiRunner(plan)
            ).run(
                request,
                install_root=install_root,
                session_root=tmp_path / "sessions",
                receipt_root=tmp_path / "receipts",
            )
    finally:
        replacement.close()


def test_gui_lifecycle_cannot_exceed_static_serve_authority(tmp_path: Path) -> None:
    _, _, _, static = _static_plan(tmp_path)
    server, path = _wayland_socket(tmp_path)
    try:
        with pytest.raises(ValueError, match="exceeds reviewed static serve"):
            plan_gui_browser(
                static.to_dict(),
                wayland_socket_path=path,
                session_seconds=89,
                readiness_timeout_ms=2000,
            )
    finally:
        server.close()


def test_bubblewrap_gui_runner_records_no_gpu_or_dbus_authority(tmp_path: Path) -> None:
    receipt, install_root, _, static = _static_plan(tmp_path)
    server, path = _wayland_socket(tmp_path)
    try:
        plan = plan_gui_browser(static.to_dict(), wayland_socket_path=path)
        static_root = (
            Path(receipt.install_path)
            / "payload"
            / cast(str, static.static_root_relative)
        )
        browser_root = tmp_path / "browser-root"
        browser_root.mkdir()
        runner = BubblewrapGuiBrowserRunner(
            server_policy=static.policy,
            browser_policy=plan.policy,
            static_root=static_root,
            browser_root=browser_root,
            gui_plan=plan,
        )
        runner.browser_runner.bwrap_path = "/usr/bin/bwrap"
        runner.browser_runner.prlimit_path = "/usr/bin/prlimit"
        command = runner.browser_runner.command_for(
            executable_path="/usr/bin/true",
            argv_tail=(),
        )
    finally:
        server.close()

    assert plan.wayland.sandbox_socket_path in command
    assert "WAYLAND_DISPLAY" in command
    assert "XDG_RUNTIME_DIR" in command
    assert "/dev/dri" not in command
    assert "DBUS_SESSION_BUS_ADDRESS" not in command


def test_gui_receipt_rejects_digest_tampering(tmp_path: Path) -> None:
    receipt, install_root, _, static = _static_plan(tmp_path)
    server, path = _wayland_socket(tmp_path)
    try:
        plan = plan_gui_browser(
            static.to_dict(),
            wayland_socket_path=path,
            session_seconds=5,
            readiness_timeout_ms=1000,
        )
        request = GuiBrowserRequest.from_payloads(
            plan.to_dict(),
            static.to_dict(),
            receipt.to_dict(),
            approved_gui_browser_plan_sha256=plan.sha256(),
            approved_static_web_plan_sha256=static.sha256(),
            approved_browser_permissions=plan.requested_browser_permissions,
        )
        result = GuiBrowserService(
            runner_factory=lambda *args: FakeGuiRunner(plan)
        ).run(
            request,
            install_root=install_root,
            session_root=tmp_path / "sessions",
            receipt_root=tmp_path / "receipts",
        )
    finally:
        server.close()

    payload = result.receipt.to_dict()
    payload["static_root_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="digest"):
        GuiBrowserReceipt.from_dict(payload)
