from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

import pytest

from phios.apps.browser_session import (
    BrowserReadinessEvidence,
    BrowserSessionExecution,
    BrowserSessionPlan,
    BrowserSessionReceipt,
    BrowserSessionRequest,
    BrowserSessionService,
    plan_browser_session,
    review_browser_session,
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


def _manifest() -> AppManifest:
    return AppManifest.from_dict(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "phi.browser-example",
            "name": "Browser Example",
            "version": "1.0.0",
            "description": "Browser session fixture",
            "source": {
                "repository_url": "https://github.com/example/browser-example",
                "license_expression": "MIT",
                "redistribution": "permitted",
            },
            "entrypoint": {"runtime": "node", "target": "package.json"},
            "permissions": [],
        }
    )


def _install(
    tmp_path: Path,
) -> tuple[AppInstallReceipt, AppManifest, Path, Path]:
    manifest = _manifest()
    install_root = tmp_path / "installed"
    install_path = install_root / manifest.app_id / manifest.version / "artifactprefix"
    payload = install_path / "payload"
    metadata = install_path / ".phios"
    dist = payload / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    metadata.mkdir()
    (dist / "index.html").write_text(
        "<html><body><div id='app'></div></body></html>",
        encoding="utf-8",
    )
    (assets / "app.js").write_text(
        "document.querySelector('#app').textContent='PhiOS';",
        encoding="utf-8",
    )

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
    artifact_digest = hashlib.sha256()
    for artifact in artifacts_tuple:
        artifact_digest.update(artifact.canonical_line())

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
        artifact_set_sha256=artifact_digest.hexdigest(),
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
        timestamp_utc="2026-09-19T06:30:00+00:00",
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
    return receipt, manifest, install_root, install_path


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


class FakeBrowserRunner:
    def __init__(
        self,
        server_policy: RuntimeSandboxPolicy,
        browser_policy: RuntimeSandboxPolicy,
        static_root: Path,
        browser_root: Path,
        *,
        browser_exit_code: int = 0,
        browser_timed_out: bool = False,
    ) -> None:
        self.server_policy = server_policy
        self.browser_policy = browser_policy
        self.static_root = static_root
        self.browser_root = browser_root
        self.browser_exit_code = browser_exit_code
        self.browser_timed_out = browser_timed_out
        self.calls: list[tuple[str, str]] = []

    def execute(self, static_plan: object, browser_plan: object) -> BrowserSessionExecution:
        self.calls.append(("execute", "called"))
        dom = b"<html><body><div id='app'>PhiOS</div></body></html>"
        return BrowserSessionExecution(
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
                elapsed_ms=80,
                port_available_before_spawn=True,
            ),
            server_result=ProcessResult(
                exit_code=-15,
                timed_out=False,
                duration_ms=950,
                stdout=_capture(),
                stderr=_capture(b"served"),
            ),
            browser_result=ProcessResult(
                exit_code=self.browser_exit_code,
                timed_out=self.browser_timed_out,
                duration_ms=600,
                stdout=_capture(dom),
                stderr=_capture(),
            ),
            server_terminated_by_session=True,
        )


def _plans(
    tmp_path: Path,
    *,
    port: int = 9101,
    session_seconds: int = 30,
) -> tuple[AppInstallReceipt, Path, object, BrowserSessionPlan]:
    receipt, _, install_root, _ = _install(tmp_path)
    static_plan = plan_static_web_adapter(
        receipt.to_dict(),
        install_root=install_root,
        loopback_port=port,
        serve_seconds=120,
    )
    browser_plan = plan_browser_session(
        static_plan.to_dict(),
        browser_tool="chromium",
        session_seconds=session_seconds,
        readiness_timeout_ms=2500,
    )
    return receipt, install_root, static_plan, browser_plan


def test_browser_plan_binds_headless_ephemeral_authority(tmp_path: Path) -> None:
    _, _, static_plan, plan = _plans(tmp_path)
    review = review_browser_session(plan.to_dict())

    assert plan.static_web_plan_sha256 == static_plan.sha256()
    assert plan.loopback_url == "http://127.0.0.1:9101/"
    assert plan.browser_family == "chromium"
    assert plan.browser_mode == "headless_dump_dom"
    assert plan.profile_mode == "ephemeral"
    assert plan.display_mode == "headless"
    assert plan.requested_browser_permissions == (
        "browser.network.inherit",
        "browser.page.execute",
    )
    assert "--headless=new" in plan.browser_argv
    assert "--dump-dom" in plan.browser_argv
    assert "--user-data-dir=/home/phios/browser-profile" in plan.browser_argv
    assert plan.loopback_url == plan.browser_argv[-1]
    assert plan.policy.network_mode == "inherit"
    assert plan.launch_authority is False
    assert plan.page_execution_authority is False
    assert plan.display_authority is False
    assert plan.persistent_profile_authority is False
    assert plan.host_home_authority is False
    assert review.browser_session_plan_sha256 == plan.sha256()
    assert BrowserSessionPlan.from_dict(plan.to_dict()) == plan


def test_browser_plan_digest_binds_session_window(tmp_path: Path) -> None:
    receipt, _, install_root, _ = _install(tmp_path)
    static_plan = plan_static_web_adapter(
        receipt.to_dict(),
        install_root=install_root,
        loopback_port=9102,
        serve_seconds=120,
    )
    first = plan_browser_session(static_plan.to_dict(), session_seconds=20)
    second = plan_browser_session(static_plan.to_dict(), session_seconds=21)

    assert first.sha256() != second.sha256()


def test_browser_planning_rejects_unknown_browser_tool(tmp_path: Path) -> None:
    receipt, _, install_root, _ = _install(tmp_path)
    static_plan = plan_static_web_adapter(
        receipt.to_dict(),
        install_root=install_root,
    )

    with pytest.raises(ValueError, match="browser_tool"):
        plan_browser_session(static_plan.to_dict(), browser_tool="random-browser")


def test_browser_request_requires_both_exact_plan_approvals(tmp_path: Path) -> None:
    receipt, _, static_plan, plan = _plans(tmp_path)

    request = BrowserSessionRequest.from_payloads(
        plan.to_dict(),
        static_plan.to_dict(),
        receipt.to_dict(),
        approved_browser_session_plan_sha256=plan.sha256(),
        approved_static_web_plan_sha256=static_plan.sha256(),
        approved_browser_permissions=plan.requested_browser_permissions,
    )
    assert request.plan == plan

    with pytest.raises(ValueError, match="browser-session"):
        BrowserSessionRequest.from_payloads(
            plan.to_dict(),
            static_plan.to_dict(),
            receipt.to_dict(),
            approved_browser_session_plan_sha256="0" * 64,
            approved_static_web_plan_sha256=static_plan.sha256(),
            approved_browser_permissions=plan.requested_browser_permissions,
        )

    with pytest.raises(ValueError, match="static-web"):
        BrowserSessionRequest.from_payloads(
            plan.to_dict(),
            static_plan.to_dict(),
            receipt.to_dict(),
            approved_browser_session_plan_sha256=plan.sha256(),
            approved_static_web_plan_sha256="0" * 64,
            approved_browser_permissions=plan.requested_browser_permissions,
        )


def test_browser_request_requires_exact_permission_set(tmp_path: Path) -> None:
    receipt, _, static_plan, plan = _plans(tmp_path)

    with pytest.raises(ValueError, match="exactly match"):
        BrowserSessionRequest.from_payloads(
            plan.to_dict(),
            static_plan.to_dict(),
            receipt.to_dict(),
            approved_browser_session_plan_sha256=plan.sha256(),
            approved_static_web_plan_sha256=static_plan.sha256(),
            approved_browser_permissions=("browser.page.execute",),
        )


def test_browser_session_records_coordinated_headless_execution(tmp_path: Path) -> None:
    receipt, install_root, static_plan, plan = _plans(tmp_path, port=9103)
    request = BrowserSessionRequest.from_payloads(
        plan.to_dict(),
        static_plan.to_dict(),
        receipt.to_dict(),
        approved_browser_session_plan_sha256=plan.sha256(),
        approved_static_web_plan_sha256=static_plan.sha256(),
        approved_browser_permissions=plan.requested_browser_permissions,
    )
    created: list[FakeBrowserRunner] = []

    def factory(
        server_policy: RuntimeSandboxPolicy,
        browser_policy: RuntimeSandboxPolicy,
        static_root: Path,
        browser_root: Path,
    ) -> FakeBrowserRunner:
        runner = FakeBrowserRunner(
            server_policy,
            browser_policy,
            static_root,
            browser_root,
        )
        created.append(runner)
        return runner

    result = BrowserSessionService(runner_factory=factory).run(
        request,
        install_root=install_root,
        session_root=tmp_path / "sessions",
        receipt_root=tmp_path / "receipts",
    )

    assert result.receipt.status == "completed"
    assert result.receipt.browser_session_plan_sha256 == plan.sha256()
    assert result.receipt.static_web_plan_sha256 == static_plan.sha256()
    assert result.receipt.readiness.ready is True
    assert result.receipt.readiness.status_code == 200
    assert result.receipt.server_terminated_by_session is True
    assert result.receipt.page_execution_authority is True
    assert result.receipt.browser_network_inherited is True
    assert result.receipt.display_authority is False
    assert result.receipt.persistent_profile_authority is False
    assert result.receipt.host_home_authority is False
    assert result.receipt.browser_controls.private_home is True
    assert result.receipt.browser_controls.private_tmp is True
    assert result.receipt.browser_controls.host_network_inherited is True
    assert result.receipt.browser_controls.network_allowlist_enforced is False
    assert result.receipt.browser_stdout_byte_count > 0
    assert BrowserSessionReceipt.from_dict(result.receipt.to_dict()) == result.receipt
    assert result.receipt_persisted is True
    assert Path(result.receipt_path).is_file()
    assert created[0].static_root.name == "dist"
    assert not created[0].browser_root.exists()


def test_browser_session_rejects_install_drift_after_review(tmp_path: Path) -> None:
    receipt, install_root, static_plan, plan = _plans(tmp_path, port=9104)
    request = BrowserSessionRequest.from_payloads(
        plan.to_dict(),
        static_plan.to_dict(),
        receipt.to_dict(),
        approved_browser_session_plan_sha256=plan.sha256(),
        approved_static_web_plan_sha256=static_plan.sha256(),
        approved_browser_permissions=plan.requested_browser_permissions,
    )
    install_path = Path(receipt.install_path)
    (install_path / "payload" / "dist" / "index.html").write_text(
        "tampered",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="installed tree changed"):
        BrowserSessionService(
            runner_factory=lambda a, b, c, d: FakeBrowserRunner(a, b, c, d)
        ).run(
            request,
            install_root=install_root,
            session_root=tmp_path / "sessions",
            receipt_root=tmp_path / "receipts",
        )


def test_browser_session_timeout_is_receipted_without_display_authority(
    tmp_path: Path,
) -> None:
    receipt, install_root, static_plan, plan = _plans(tmp_path, port=9105)
    request = BrowserSessionRequest.from_payloads(
        plan.to_dict(),
        static_plan.to_dict(),
        receipt.to_dict(),
        approved_browser_session_plan_sha256=plan.sha256(),
        approved_static_web_plan_sha256=static_plan.sha256(),
        approved_browser_permissions=plan.requested_browser_permissions,
    )

    result = BrowserSessionService(
        runner_factory=lambda a, b, c, d: FakeBrowserRunner(
            a,
            b,
            c,
            d,
            browser_exit_code=-9,
            browser_timed_out=True,
        )
    ).run(
        request,
        install_root=install_root,
        session_root=tmp_path / "sessions",
        receipt_root=tmp_path / "receipts",
    )

    assert result.receipt.status == "timed_out"
    assert result.receipt.browser_timed_out is True
    assert result.receipt.display_authority is False


def test_browser_window_must_fit_inside_static_serve_authority(tmp_path: Path) -> None:
    receipt, _, install_root, _ = _install(tmp_path)
    static_plan = plan_static_web_adapter(
        receipt.to_dict(),
        install_root=install_root,
        loopback_port=9106,
        serve_seconds=5,
    )

    with pytest.raises(ValueError, match="exceeds reviewed static serve window"):
        plan_browser_session(
            static_plan.to_dict(),
            session_seconds=5,
            readiness_timeout_ms=1000,
        )


def test_browser_session_receipt_rejects_digest_tampering(tmp_path: Path) -> None:
    receipt, install_root, static_plan, plan = _plans(tmp_path, port=9107)
    request = BrowserSessionRequest.from_payloads(
        plan.to_dict(),
        static_plan.to_dict(),
        receipt.to_dict(),
        approved_browser_session_plan_sha256=plan.sha256(),
        approved_static_web_plan_sha256=static_plan.sha256(),
        approved_browser_permissions=plan.requested_browser_permissions,
    )
    result = BrowserSessionService(
        runner_factory=lambda a, b, c, d: FakeBrowserRunner(a, b, c, d)
    ).run(
        request,
        install_root=install_root,
        session_root=tmp_path / "sessions",
        receipt_root=tmp_path / "receipts",
    )
    payload = result.receipt.to_dict()
    payload["static_root_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="digest"):
        BrowserSessionReceipt.from_dict(payload)
