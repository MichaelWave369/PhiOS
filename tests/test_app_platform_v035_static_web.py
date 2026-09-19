from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

import pytest

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
from phios.apps.static_web import (
    StaticWebAdapterPlan,
    StaticWebAdapterService,
    StaticWebServeRequest,
    plan_static_web_adapter,
    review_static_web_adapter,
)


def _manifest(
    *,
    runtime: str = "node",
    target: str = "package.json",
    permissions: tuple[str, ...] = (),
) -> AppManifest:
    return AppManifest.from_dict(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "phi.static-example",
            "name": "Static Example",
            "version": "1.0.0",
            "description": "Static adapter fixture",
            "source": {
                "repository_url": "https://github.com/example/static-example",
                "license_expression": "MIT",
                "redistribution": "permitted",
            },
            "entrypoint": {"runtime": runtime, "target": target},
            "permissions": list(permissions),
        }
    )


def _install(
    tmp_path: Path,
    *,
    runtime: str = "node",
    target: str = "package.json",
    permissions: tuple[str, ...] = (),
    roots: tuple[str, ...] = ("dist",),
) -> tuple[AppInstallReceipt, AppManifest, Path, Path]:
    manifest = _manifest(runtime=runtime, target=target, permissions=permissions)
    install_root = tmp_path / "installed"
    install_path = install_root / manifest.app_id / manifest.version / "artifactprefix"
    payload = install_path / "payload"
    metadata = install_path / ".phios"
    payload.mkdir(parents=True)
    metadata.mkdir()

    artifacts: list[PackageArtifact] = []
    for root in roots:
        root_dir = payload / root
        assets = root_dir / "assets"
        assets.mkdir(parents=True)
        (root_dir / "index.html").write_text("<html>phi</html>", encoding="utf-8")
        (assets / "app.js").write_text("console.log('phi')", encoding="utf-8")
        for path in sorted(root_dir.rglob("*")):
            if path.is_file():
                artifacts.append(
                    PackageArtifact(
                        path=path.relative_to(payload).as_posix(),
                        byte_count=path.stat().st_size,
                        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    )
                )

    artifacts_tuple = tuple(sorted(artifacts, key=lambda item: item.path))
    artifact_digest = hashlib.sha256()
    for artifact in artifacts_tuple:
        artifact_digest.update(artifact.canonical_line())
    artifact_set_sha = artifact_digest.hexdigest()

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
        artifact_set_sha256=artifact_set_sha,
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
        timestamp_utc="2026-09-19T06:00:00+00:00",
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


class FakeStaticRunner:
    def __init__(self, policy: RuntimeSandboxPolicy, static_root: Path) -> None:
        self.policy = policy
        self.static_root = static_root
        self.preflight_calls = 0
        self.probed: list[str] = []
        self.argv_calls: list[tuple[str, tuple[str, ...], int]] = []

    def preflight(self) -> SandboxBackendIdentity:
        self.preflight_calls += 1
        return SandboxBackendIdentity(
            backend="bubblewrap",
            executable_path="/usr/bin/bwrap",
            version="bubblewrap test",
            version_output_sha256=hashlib.sha256(b"bubblewrap test").hexdigest(),
            platform_system="Linux",
            platform_machine="x86_64",
        )

    def probe_tool(self, executable_tool: str) -> ToolIdentity:
        self.probed.append(executable_tool)
        return ToolIdentity(
            logical_tool=executable_tool,
            executable_path=f"/usr/bin/{executable_tool}",
            version=f"{executable_tool} test",
            version_output_sha256=hashlib.sha256(
                f"{executable_tool} test".encode()
            ).hexdigest(),
        )

    def run_argv(
        self,
        executable_tool: str,
        argv_tail: tuple[str, ...],
        *,
        timeout_seconds: int,
    ) -> ProcessResult:
        self.argv_calls.append((executable_tool, argv_tail, timeout_seconds))
        return ProcessResult(
            exit_code=-1,
            timed_out=True,
            duration_ms=timeout_seconds * 1000,
            stdout=_capture(),
            stderr=_capture(),
        )

    def control_evidence(self) -> RuntimeControlEvidence:
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
            wall_clock_timeout_enforced=True,
            cpu_rlimit_enforced=True,
            address_space_rlimit_enforced=True,
            open_files_rlimit_enforced=True,
            file_size_rlimit_enforced=True,
            seccomp_enforced=False,
            network_allowlist_enforced=False,
            parent_death_enforced=True,
        )


def test_vite_dist_maps_to_reviewable_static_root(tmp_path: Path) -> None:
    receipt, _, install_root, _ = _install(tmp_path)

    plan = plan_static_web_adapter(
        receipt.to_dict(),
        install_root=install_root,
        loopback_port=9001,
        serve_seconds=45,
    )
    review = review_static_web_adapter(plan.to_dict())

    assert plan.status == "ready_for_review"
    assert plan.static_root_relative == "dist"
    assert plan.mapping_rule == "vite_dist_index"
    assert plan.server_argv == (
        "python3",
        "-m",
        "http.server",
        "9001",
        "--bind",
        "127.0.0.1",
        "--directory",
        "/app",
    )
    assert plan.policy.network_mode == "inherit"
    assert plan.browser_launch_authority is False
    assert plan.application_code_executed_by_server is False
    assert plan.launch_authority is False
    assert review.loopback_url == "http://127.0.0.1:9001/"
    assert review.static_web_plan_sha256 == plan.sha256()
    assert StaticWebAdapterPlan.from_dict(plan.to_dict()) == plan


def test_react_build_maps_to_reviewable_static_root(tmp_path: Path) -> None:
    receipt, _, install_root, _ = _install(tmp_path, roots=("build",))

    plan = plan_static_web_adapter(receipt.to_dict(), install_root=install_root)

    assert plan.status == "ready_for_review"
    assert plan.static_root_relative == "build"
    assert plan.mapping_rule == "react_build_index"


def test_multiple_known_static_roots_fail_closed_as_ambiguous(tmp_path: Path) -> None:
    receipt, _, install_root, _ = _install(tmp_path, roots=("dist", "build"))

    plan = plan_static_web_adapter(receipt.to_dict(), install_root=install_root)

    assert plan.status == "ambiguous_output"
    assert plan.static_root_relative is None
    assert plan.server_argv == ()


def test_missing_known_output_is_reviewable_but_not_serveable(tmp_path: Path) -> None:
    receipt, manifest, install_root, install_path = _install(tmp_path)
    payload = install_path / "payload"
    for path in sorted((payload / "dist").rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
        else:
            path.rmdir()
    (payload / "dist").rmdir()

    package_plan_path = install_path / ".phios" / "package-plan.json"
    package_plan = BuildPackagePlan.from_dict(
        json.loads(package_plan_path.read_text(encoding="utf-8"))
    )
    # Keep one valid unrelated artifact so the install remains structurally valid.
    other = payload / "other.txt"
    other.write_text("x", encoding="utf-8")
    artifact = PackageArtifact(
        path="other.txt",
        byte_count=1,
        sha256=hashlib.sha256(b"x").hexdigest(),
    )
    digest = hashlib.sha256()
    digest.update(artifact.canonical_line())
    replacement = BuildPackagePlan(
        app_id=package_plan.app_id,
        app_version=package_plan.app_version,
        manifest_sha256=package_plan.manifest_sha256,
        registry_snapshot_sha256=package_plan.registry_snapshot_sha256,
        repository_url=package_plan.repository_url,
        commit_sha=package_plan.commit_sha,
        build_plan_sha256=package_plan.build_plan_sha256,
        execution_receipt_sha256=package_plan.execution_receipt_sha256,
        offline_build_receipt_sha256=package_plan.offline_build_receipt_sha256,
        artifact_set_sha256=digest.hexdigest(),
        artifacts=(artifact,),
        install_relative_path=package_plan.install_relative_path,
        launch_authority=False,
    )
    package_plan_path.write_text(
        json.dumps(replacement.to_dict(), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    payload_sha, artifact_count, total_bytes = snapshot_installed_tree(payload)
    tree_sha, _, _ = snapshot_installed_tree(install_path)
    updated_receipt = AppInstallReceipt(
        receipt_id=receipt.receipt_id,
        timestamp_utc=receipt.timestamp_utc,
        app_id=receipt.app_id,
        app_version=receipt.app_version,
        package_plan_sha256=replacement.sha256(),
        manifest_sha256=manifest.sha256(),
        registry_snapshot_sha256=receipt.registry_snapshot_sha256,
        build_plan_sha256=receipt.build_plan_sha256,
        execution_receipt_sha256=receipt.execution_receipt_sha256,
        offline_build_receipt_sha256=receipt.offline_build_receipt_sha256,
        artifact_set_sha256=payload_sha,
        installed_payload_sha256=payload_sha,
        installed_tree_sha256=tree_sha,
        artifact_count=artifact_count,
        total_bytes=total_bytes,
        install_path=receipt.install_path,
        launch_authority=False,
        status="installed",
    )

    plan = plan_static_web_adapter(
        updated_receipt.to_dict(),
        install_root=install_root,
    )

    assert plan.status == "unsupported_output"
    assert plan.server_tool is None


def test_non_web_manifest_runtime_is_not_mapped(tmp_path: Path) -> None:
    receipt, _, install_root, _ = _install(
        tmp_path,
        runtime="python",
        target="main.py",
    )

    plan = plan_static_web_adapter(receipt.to_dict(), install_root=install_root)

    assert plan.status == "unsupported_manifest_runtime"


def test_manifest_permissions_are_deferred_not_granted(tmp_path: Path) -> None:
    receipt, _, install_root, _ = _install(
        tmp_path,
        permissions=("runtime.network.inherit", "runtime.data.persist"),
    )

    plan = plan_static_web_adapter(receipt.to_dict(), install_root=install_root)

    assert plan.deferred_manifest_permissions == (
        "runtime.data.persist",
        "runtime.network.inherit",
    )
    assert plan.status == "ready_for_review"


def test_static_web_serve_requires_exact_plan_approval(tmp_path: Path) -> None:
    receipt, _, install_root, _ = _install(tmp_path)
    plan = plan_static_web_adapter(receipt.to_dict(), install_root=install_root)

    with pytest.raises(ValueError, match="Approved static-web plan"):
        StaticWebServeRequest.from_payloads(
            plan.to_dict(),
            receipt.to_dict(),
            approved_static_web_plan_sha256="0" * 64,
        )


def test_static_root_tampering_after_review_blocks_serve(tmp_path: Path) -> None:
    receipt, _, install_root, install_path = _install(tmp_path)
    plan = plan_static_web_adapter(receipt.to_dict(), install_root=install_root)
    request = StaticWebServeRequest.from_payloads(
        plan.to_dict(),
        receipt.to_dict(),
        approved_static_web_plan_sha256=plan.sha256(),
    )
    (install_path / "payload" / "dist" / "index.html").write_text(
        "tampered",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="installed tree changed"):
        StaticWebAdapterService(
            runner_factory=lambda policy, root: FakeStaticRunner(policy, root)
        ).serve(
            request,
            install_root=install_root,
            receipt_root=tmp_path / "receipts",
        )


def test_static_web_service_records_bounded_loopback_session(tmp_path: Path) -> None:
    receipt, _, install_root, _ = _install(tmp_path)
    plan = plan_static_web_adapter(
        receipt.to_dict(),
        install_root=install_root,
        loopback_port=9002,
        serve_seconds=12,
    )
    request = StaticWebServeRequest.from_payloads(
        plan.to_dict(),
        receipt.to_dict(),
        approved_static_web_plan_sha256=plan.sha256(),
    )
    created: list[FakeStaticRunner] = []

    def factory(policy: RuntimeSandboxPolicy, root: Path) -> FakeStaticRunner:
        runner = FakeStaticRunner(policy, root)
        created.append(runner)
        return runner

    result = StaticWebAdapterService(runner_factory=factory).serve(
        request,
        install_root=install_root,
        receipt_root=tmp_path / "receipts",
    )

    assert result.receipt.status == "serve_window_complete"
    assert result.receipt.loopback_url == "http://127.0.0.1:9002/"
    assert result.receipt.browser_launch_authority is False
    assert result.receipt.application_code_executed_by_server is False
    assert result.receipt.controls.host_network_inherited is True
    assert result.receipt.controls.network_namespace_enforced is False
    assert result.receipt.controls.installed_payload_read_only is True
    assert result.receipt.controls.persistent_data_writable_mount is False
    assert result.receipt_persisted is True
    assert Path(result.receipt_path).is_file()
    assert created[0].probed == ["python3"]
    assert created[0].argv_calls == [
        (
            "python3",
            (
                "-m",
                "http.server",
                "9002",
                "--bind",
                "127.0.0.1",
                "--directory",
                "/app",
            ),
            12,
        )
    ]


def test_loopback_port_is_bound_into_plan_digest(tmp_path: Path) -> None:
    receipt, _, install_root, _ = _install(tmp_path)
    first = plan_static_web_adapter(
        receipt.to_dict(),
        install_root=install_root,
        loopback_port=9003,
    )
    second = plan_static_web_adapter(
        receipt.to_dict(),
        install_root=install_root,
        loopback_port=9004,
    )

    assert first.sha256() != second.sha256()


def test_install_package_plan_tampering_blocks_mapping(tmp_path: Path) -> None:
    receipt, _, install_root, install_path = _install(tmp_path)
    package_plan_path = install_path / ".phios" / "package-plan.json"
    payload = json.loads(package_plan_path.read_text(encoding="utf-8"))
    payload["commit_sha"] = "b" * 40
    package_plan_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        plan_static_web_adapter(receipt.to_dict(), install_root=install_root)
