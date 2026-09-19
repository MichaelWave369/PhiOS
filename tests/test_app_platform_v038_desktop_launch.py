from __future__ import annotations

import hashlib
import json
import socket
import uuid
from pathlib import Path

import pytest

from phios.apps.browser_session import (
    BrowserReadinessEvidence,
    BrowserSessionExecution,
    plan_browser_session,
)
from phios.apps.build_execution import ProcessResult, StreamCapture, ToolIdentity
from phios.apps.desktop_launch import (
    DesktopAppInstaller,
    DesktopAppLaunchService,
    DesktopAppRegistrationRequest,
    DesktopAppRevocationService,
    DesktopLaunchGrant,
    DesktopLaunchReceipt,
    DesktopRevokeReceipt,
    plan_desktop_app,
    resolve_current_wayland_socket,
    review_desktop_app,
)
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
    VisibleBrowserSessionService,
    WaylandDisplayEvidence,
)


def _manifest() -> AppManifest:
    return AppManifest.from_dict(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "phi.desktop-example",
            "name": "Desktop Example",
            "version": "1.0.0",
            "description": "Governed desktop example",
            "source": {
                "repository_url": "https://github.com/example/desktop-example",
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
    metadata = install_path / ".phios"
    dist = payload / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    metadata.mkdir()
    (dist / "index.html").write_text("<html><body>desktop</body></html>", encoding="utf-8")
    (assets / "app.js").write_text("console.log('desktop')", encoding="utf-8")

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
    payload_sha, count, total = snapshot_installed_tree(payload)
    tree_sha, _, _ = snapshot_installed_tree(install_path)
    receipt = AppInstallReceipt(
        receipt_id=str(uuid.uuid4()),
        timestamp_utc="2026-09-19T07:20:00+00:00",
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
    return receipt, install_root, install_path


def _plans(tmp_path: Path):
    receipt, install_root, install_path = _install(tmp_path)
    static_plan = plan_static_web_adapter(
        receipt.to_dict(),
        install_root=install_root,
        loopback_port=9301,
        serve_seconds=120,
    )
    browser_plan = plan_browser_session(
        static_plan.to_dict(),
        browser_tool="chromium",
        session_seconds=30,
        readiness_timeout_ms=2500,
    )
    desktop_plan = plan_desktop_app(
        browser_plan.to_dict(),
        static_plan.to_dict(),
        receipt.to_dict(),
        install_root=install_root,
    )
    return receipt, install_root, install_path, static_plan, browser_plan, desktop_plan


def _register(tmp_path: Path):
    receipt, install_root, install_path, static_plan, browser_plan, desktop_plan = _plans(
        tmp_path
    )
    request = DesktopAppRegistrationRequest.from_payloads(
        desktop_plan.to_dict(),
        browser_plan.to_dict(),
        static_plan.to_dict(),
        receipt.to_dict(),
        approved_desktop_app_plan_sha256=desktop_plan.sha256(),
        approved_desktop_permissions=desktop_plan.requested_desktop_permissions,
    )
    desktop_root = tmp_path / "desktop-apps"
    applications_root = tmp_path / "applications"
    result = DesktopAppInstaller().install(
        request,
        install_root=install_root,
        desktop_root=desktop_root,
        applications_root=applications_root,
    )
    return (
        receipt,
        install_root,
        install_path,
        static_plan,
        browser_plan,
        desktop_plan,
        desktop_root,
        applications_root,
        result,
    )


def _wayland_socket(tmp_path: Path, name: str = "wayland-0") -> tuple[socket.socket, Path]:
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    path = runtime / name
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(path))
    return sock, path


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
    ) -> None:
        self.server_policy = server_policy
        self.browser_policy = browser_policy
        self.static_root = static_root
        self.browser_root = browser_root
        self.wayland_socket = wayland_socket

    def execute(
        self,
        static_plan: object,
        visible_plan: VisibleBrowserSessionPlan,
    ) -> VisibleBrowserExecution:
        identity = visible_plan.wayland_socket
        return VisibleBrowserExecution(
            browser=BrowserSessionExecution(
                server_backend_identity=_backend("server"),
                server_tool_identity=_tool("python3"),
                browser_backend_identity=_backend("browser"),
                browser_tool_identity=_tool("chromium"),
                server_controls=_controls(wall_clock=False),
                browser_controls=_controls(wall_clock=True),
                readiness=BrowserReadinessEvidence(
                    ready=True,
                    status_code=200,
                    attempts=1,
                    elapsed_ms=20,
                    port_available_before_spawn=True,
                ),
                server_result=ProcessResult(
                    exit_code=-15,
                    timed_out=False,
                    duration_ms=500,
                    stdout=_capture(),
                    stderr=_capture(),
                ),
                browser_result=ProcessResult(
                    exit_code=0,
                    timed_out=False,
                    duration_ms=400,
                    stdout=_capture(),
                    stderr=_capture(),
                ),
                server_terminated_by_session=True,
            ),
            display=WaylandDisplayEvidence(
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
            ),
        )


def _launch_service() -> DesktopAppLaunchService:
    visible = VisibleBrowserSessionService(
        runner_factory=lambda a, b, c, d, e: FakeVisibleRunner(a, b, c, d, e)
    )
    return DesktopAppLaunchService(visible_service=visible)


def test_desktop_plan_binds_manifest_and_runtime_ancestry(tmp_path: Path) -> None:
    receipt, _, _, static, browser, plan = _plans(tmp_path)
    review = review_desktop_app(plan.to_dict())

    assert plan.app_id == receipt.app_id
    assert plan.desktop_name == "Desktop Example"
    assert plan.desktop_comment == "Governed desktop example"
    assert plan.desktop_icon == "phios-app"
    assert plan.static_web_plan_sha256 == static.sha256()
    assert plan.browser_session_plan_sha256 == browser.sha256()
    assert plan.display_selector == "current_user_wayland_env"
    assert plan.requested_desktop_permissions == (
        "browser.display.wayland",
        "browser.network.inherit",
        "browser.page.execute",
        "desktop.launch.persist",
    )
    assert plan.persistent_launch_grant_authority is False
    assert plan.display_authority is False
    assert review.desktop_app_plan_sha256 == plan.sha256()


def test_desktop_registration_requires_exact_plan_and_permissions(tmp_path: Path) -> None:
    receipt, _, _, static, browser, plan = _plans(tmp_path)

    with pytest.raises(ValueError, match="Approved desktop-app"):
        DesktopAppRegistrationRequest.from_payloads(
            plan.to_dict(),
            browser.to_dict(),
            static.to_dict(),
            receipt.to_dict(),
            approved_desktop_app_plan_sha256="0" * 64,
            approved_desktop_permissions=plan.requested_desktop_permissions,
        )

    with pytest.raises(ValueError, match="exactly match"):
        DesktopAppRegistrationRequest.from_payloads(
            plan.to_dict(),
            browser.to_dict(),
            static.to_dict(),
            receipt.to_dict(),
            approved_desktop_app_plan_sha256=plan.sha256(),
            approved_desktop_permissions=(
                "browser.display.wayland",
                "browser.network.inherit",
                "browser.page.execute",
            ),
        )


def test_desktop_install_writes_bound_launcher_and_grant(tmp_path: Path) -> None:
    *_, plan, _, _, result = _register(tmp_path)
    bundle = Path(result.bundle_path)
    entry = Path(result.desktop_entry_path)

    assert bundle.is_dir()
    assert entry.is_file()
    assert (bundle / "desktop-plan.json").is_file()
    assert (bundle / "browser-plan.json").is_file()
    assert (bundle / "static-plan.json").is_file()
    assert (bundle / "install-receipt.json").is_file()
    assert (bundle / "grant.json").is_file()
    assert result.grant.persistent_launch_grant_authority is True
    assert result.grant.desktop_app_plan_sha256 == plan.sha256()
    text = entry.read_text(encoding="utf-8")
    assert "Name=Desktop Example" in text
    assert "Icon=phios-app" in text
    assert "Terminal=false" in text
    assert "launch-desktop-bundle" in text
    assert "sh -c" not in text
    assert DesktopLaunchGrant.from_dict(
        json.loads((bundle / "grant.json").read_text(encoding="utf-8"))
    ) == result.grant


def test_current_wayland_selector_uses_current_environment(tmp_path: Path) -> None:
    sock, path = _wayland_socket(tmp_path)
    try:
        identity = resolve_current_wayland_socket(
            {
                "XDG_RUNTIME_DIR": str(path.parent),
                "WAYLAND_DISPLAY": path.name,
            }
        )
        assert identity.host_path == str(path.resolve())
    finally:
        sock.close()


def test_current_wayland_selector_rejects_path_escape(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    with pytest.raises(ValueError, match="safe socket basename"):
        resolve_current_wayland_socket(
            {
                "XDG_RUNTIME_DIR": str(runtime),
                "WAYLAND_DISPLAY": "../wayland-0",
            }
        )


def test_one_click_launch_mints_fresh_visible_plan_for_current_socket(
    tmp_path: Path,
) -> None:
    (
        _,
        install_root,
        _,
        _,
        _,
        _,
        _,
        _,
        installed,
    ) = _register(tmp_path / "app")

    first, first_path = _wayland_socket(tmp_path / "display", "wayland-0")
    env = {
        "XDG_RUNTIME_DIR": str(first_path.parent),
        "WAYLAND_DISPLAY": first_path.name,
    }
    try:
        result = _launch_service().launch(
            Path(installed.bundle_path),
            install_root=install_root,
            session_root=tmp_path / "sessions",
            receipt_root=tmp_path / "receipts",
            env=env,
        )
        first_visible_sha = result.receipt.visible_browser_plan_sha256
        assert result.receipt.status == "completed"
        assert result.receipt.persistent_launch_grant_authority is True
        assert result.receipt.display_authority is True
        assert result.receipt.wayland_socket.host_path == str(first_path.resolve())
        assert DesktopLaunchReceipt.from_dict(result.receipt.to_dict()) == result.receipt
    finally:
        first.close()

    first_path.unlink()
    second = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    second.bind(str(first_path))
    try:
        result2 = _launch_service().launch(
            Path(installed.bundle_path),
            install_root=install_root,
            session_root=tmp_path / "sessions2",
            receipt_root=tmp_path / "receipts2",
            env=env,
        )
        assert result2.receipt.status == "completed"
        assert result2.receipt.visible_browser_plan_sha256 != first_visible_sha
    finally:
        second.close()


def test_launcher_entry_tampering_blocks_one_click_launch(tmp_path: Path) -> None:
    (
        _,
        install_root,
        _,
        _,
        _,
        _,
        _,
        _,
        installed,
    ) = _register(tmp_path / "app")
    entry = Path(installed.desktop_entry_path)
    entry.write_text(entry.read_text(encoding="utf-8") + "# tampered\n", encoding="utf-8")
    sock, path = _wayland_socket(tmp_path / "display")
    try:
        with pytest.raises(ValueError, match="launcher entry changed"):
            _launch_service().launch(
                Path(installed.bundle_path),
                install_root=install_root,
                session_root=tmp_path / "sessions",
                receipt_root=tmp_path / "receipts",
                env={
                    "XDG_RUNTIME_DIR": str(path.parent),
                    "WAYLAND_DISPLAY": path.name,
                },
            )
    finally:
        sock.close()


def test_install_drift_blocks_one_click_launch(tmp_path: Path) -> None:
    (
        _,
        install_root,
        install_path,
        _,
        _,
        _,
        _,
        _,
        installed,
    ) = _register(tmp_path / "app")
    (install_path / "payload" / "dist" / "index.html").write_text(
        "tampered",
        encoding="utf-8",
    )
    sock, path = _wayland_socket(tmp_path / "display")
    try:
        with pytest.raises(ValueError, match="installed tree changed"):
            _launch_service().launch(
                Path(installed.bundle_path),
                install_root=install_root,
                session_root=tmp_path / "sessions",
                receipt_root=tmp_path / "receipts",
                env={
                    "XDG_RUNTIME_DIR": str(path.parent),
                    "WAYLAND_DISPLAY": path.name,
                },
            )
    finally:
        sock.close()


def test_bundle_grant_tampering_is_rejected(tmp_path: Path) -> None:
    *_, installed = _register(tmp_path / "app")
    grant_path = Path(installed.bundle_path) / "grant.json"
    payload = json.loads(grant_path.read_text(encoding="utf-8"))
    payload["desktop_entry_sha256"] = "0" * 64
    grant_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    sock, path = _wayland_socket(tmp_path / "display")
    try:
        with pytest.raises(ValueError, match="digest"):
            _launch_service().launch(
                Path(installed.bundle_path),
                install_root=tmp_path / "app" / "installed",
                session_root=tmp_path / "sessions",
                receipt_root=tmp_path / "receipts",
                env={
                    "XDG_RUNTIME_DIR": str(path.parent),
                    "WAYLAND_DISPLAY": path.name,
                },
            )
    finally:
        sock.close()


def test_revocation_removes_launcher_and_bundle(tmp_path: Path) -> None:
    (
        _,
        _,
        _,
        _,
        _,
        _,
        desktop_root,
        applications_root,
        installed,
    ) = _register(tmp_path / "app")
    bundle = Path(installed.bundle_path)
    entry = Path(installed.desktop_entry_path)

    receipt = DesktopAppRevocationService().revoke(
        bundle,
        approved_desktop_launch_grant_sha256=installed.grant.sha256(),
        desktop_root=desktop_root,
        applications_root=applications_root,
        receipt_root=tmp_path / "revoke-receipts",
    )

    assert receipt.status == "revoked"
    assert DesktopRevokeReceipt.from_dict(receipt.to_dict()) == receipt
    assert not bundle.exists()
    assert not entry.exists()


def test_revocation_requires_exact_grant_sha(tmp_path: Path) -> None:
    (
        _,
        _,
        _,
        _,
        _,
        _,
        desktop_root,
        applications_root,
        installed,
    ) = _register(tmp_path / "app")

    with pytest.raises(ValueError, match="Approved desktop grant"):
        DesktopAppRevocationService().revoke(
            Path(installed.bundle_path),
            approved_desktop_launch_grant_sha256="0" * 64,
            desktop_root=desktop_root,
            applications_root=applications_root,
            receipt_root=tmp_path / "revoke-receipts",
        )


def test_desktop_launch_receipt_rejects_digest_tampering(tmp_path: Path) -> None:
    (
        _,
        install_root,
        _,
        _,
        _,
        _,
        _,
        _,
        installed,
    ) = _register(tmp_path / "app")
    sock, path = _wayland_socket(tmp_path / "display")
    try:
        result = _launch_service().launch(
            Path(installed.bundle_path),
            install_root=install_root,
            session_root=tmp_path / "sessions",
            receipt_root=tmp_path / "receipts",
            env={
                "XDG_RUNTIME_DIR": str(path.parent),
                "WAYLAND_DISPLAY": path.name,
            },
        )
        payload = result.receipt.to_dict()
        payload["visible_browser_plan_sha256"] = "0" * 64

        with pytest.raises(ValueError, match="digest"):
            DesktopLaunchReceipt.from_dict(payload)
    finally:
        sock.close()


def test_desktop_revoke_receipt_rejects_digest_tampering(tmp_path: Path) -> None:
    (
        _,
        _,
        _,
        _,
        _,
        _,
        desktop_root,
        applications_root,
        installed,
    ) = _register(tmp_path / "app")
    receipt = DesktopAppRevocationService().revoke(
        Path(installed.bundle_path),
        approved_desktop_launch_grant_sha256=installed.grant.sha256(),
        desktop_root=desktop_root,
        applications_root=applications_root,
        receipt_root=tmp_path / "revoke-receipts",
    )
    payload = receipt.to_dict()
    payload["desktop_entry_path"] = payload["desktop_entry_path"] + ".changed"

    with pytest.raises(ValueError, match="digest"):
        DesktopRevokeReceipt.from_dict(payload)
