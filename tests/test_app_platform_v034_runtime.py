from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

import pytest

from phios.apps.build_execution import ProcessResult, StreamCapture, ToolIdentity
from phios.apps.manifest import AppManifest
from phios.apps.package_install import AppInstallReceipt, snapshot_installed_tree
from phios.apps.runtime import (
    BubblewrapRuntimeRunner,
    InstalledRuntimePlan,
    InstalledRuntimeService,
    RuntimeControlEvidence,
    RuntimeLaunchReceipt,
    RuntimeLaunchRequest,
    RuntimeSandboxPolicy,
    plan_installed_runtime,
    review_installed_runtime,
)
from phios.apps.sandbox import SandboxBackendIdentity


def _manifest(
    *,
    runtime: str = "node",
    target: str = "main.js",
    permissions: tuple[str, ...] = (),
) -> AppManifest:
    return AppManifest.from_dict(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "phi.runtime-example",
            "name": "Runtime Example",
            "version": "1.0.0",
            "description": "Runtime contract fixture",
            "source": {
                "repository_url": "https://github.com/example/runtime-example",
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
    target: str = "main.js",
    permissions: tuple[str, ...] = (),
) -> tuple[AppInstallReceipt, AppManifest, Path, Path]:
    manifest = _manifest(runtime=runtime, target=target, permissions=permissions)
    install_root = tmp_path / "installed"
    install_path = install_root / manifest.app_id / manifest.version / "artifactprefix"
    payload = install_path / "payload"
    metadata = install_path / ".phios"
    payload.mkdir(parents=True)
    metadata.mkdir()

    if target == "main.js":
        (payload / "main.js").write_text("console.log('phi runtime')\n", encoding="utf-8")
    elif target == "main.py":
        (payload / "main.py").write_text("print('phi runtime')\n", encoding="utf-8")
    elif target == "bin/app":
        target_path = payload / "bin" / "app"
        target_path.parent.mkdir()
        target_path.write_bytes(b"native")
    elif target == "package.json":
        (payload / "package.json").write_text('{"name":"x"}', encoding="utf-8")
    elif runtime == "static_web":
        (payload / target).write_text("<html>phi</html>", encoding="utf-8")
    elif runtime == "local_http":
        (payload / "service-placeholder.txt").write_text("loopback", encoding="utf-8")

    (metadata / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    (metadata / "package-plan.json").write_text(
        '{"schema_version":"fixture"}',
        encoding="utf-8",
    )

    payload_sha, artifact_count, total_bytes = snapshot_installed_tree(payload)
    tree_sha, _, _ = snapshot_installed_tree(install_path)
    receipt = AppInstallReceipt(
        receipt_id=str(uuid.uuid4()),
        timestamp_utc="2026-09-19T05:00:00+00:00",
        app_id=manifest.app_id,
        app_version=manifest.version,
        package_plan_sha256="1" * 64,
        manifest_sha256=manifest.sha256(),
        registry_snapshot_sha256="2" * 64,
        build_plan_sha256="3" * 64,
        execution_receipt_sha256="4" * 64,
        offline_build_receipt_sha256="5" * 64,
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


class FakeRuntimeRunner:
    def __init__(
        self,
        policy: RuntimeSandboxPolicy,
        payload_root: Path,
        data_path: Path | None,
    ) -> None:
        self.policy = policy
        self.payload_root = payload_root
        self.data_path = data_path
        self.preflight_calls = 0
        self.probed: list[str] = []
        self.plans: list[InstalledRuntimePlan] = []

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

    def run(self, plan: InstalledRuntimePlan) -> ProcessResult:
        self.plans.append(plan)
        return ProcessResult(
            exit_code=0,
            timed_out=False,
            duration_ms=7,
            stdout=_capture(b"hello"),
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
            persistent_data_writable_mount=self.data_path is not None,
            host_system_roots_read_only=True,
            network_namespace_enforced=self.policy.network_mode == "deny",
            host_network_inherited=self.policy.network_mode == "inherit",
            wall_clock_timeout_enforced=True,
            cpu_rlimit_enforced=True,
            address_space_rlimit_enforced=True,
            open_files_rlimit_enforced=True,
            file_size_rlimit_enforced=True,
            seccomp_enforced=False,
            network_allowlist_enforced=False,
            parent_death_enforced=True,
        )


def test_node_runtime_plan_is_reviewable_and_non_authoritative(tmp_path: Path) -> None:
    receipt, _, install_root, _ = _install(tmp_path)

    plan = plan_installed_runtime(receipt.to_dict(), install_root=install_root)
    review = review_installed_runtime(plan.to_dict())

    assert plan.status == "ready_for_review"
    assert plan.adapter == "node_direct_v034"
    assert plan.runtime_argv == ("node", "/app/main.js")
    assert plan.network_mode == "deny"
    assert plan.data_mode == "ephemeral"
    assert plan.requested_runtime_permissions == ()
    assert plan.launch_authority is False
    assert review.runtime_plan_sha256 == plan.sha256()
    assert review.launch_authority is False
    assert InstalledRuntimePlan.from_dict(plan.to_dict()) == plan


def test_python_runtime_plan_is_direct_when_target_is_installed(tmp_path: Path) -> None:
    receipt, _, install_root, _ = _install(
        tmp_path,
        runtime="python",
        target="main.py",
    )

    plan = plan_installed_runtime(receipt.to_dict(), install_root=install_root)

    assert plan.status == "ready_for_review"
    assert plan.adapter == "python_direct_v034"
    assert plan.executable_tool == "python3"
    assert plan.runtime_argv == ("python3", "/app/main.py")


@pytest.mark.parametrize(
    ("runtime", "target", "adapter"),
    [
        ("node", "package.json", "unsupported_node_entrypoint_v034"),
        ("native", "bin/app", "unsupported_native_mode_v034"),
        ("static_web", "index.html", "unsupported_static_web_v034"),
        (
            "local_http",
            "http://127.0.0.1:8787/status",
            "unsupported_local_http_v034",
        ),
    ],
)
def test_unsupported_runtime_shapes_fail_closed(
    tmp_path: Path,
    runtime: str,
    target: str,
    adapter: str,
) -> None:
    receipt, _, install_root, _ = _install(
        tmp_path,
        runtime=runtime,
        target=target,
    )

    plan = plan_installed_runtime(receipt.to_dict(), install_root=install_root)

    assert plan.status in {"unsupported_runtime", "unsupported_entrypoint"}
    assert plan.adapter == adapter
    assert plan.runtime_argv == ()
    assert plan.executable_tool is None


def test_unknown_manifest_permission_blocks_runtime_adapter(tmp_path: Path) -> None:
    receipt, _, install_root, _ = _install(
        tmp_path,
        permissions=("runtime.camera",),
    )

    plan = plan_installed_runtime(receipt.to_dict(), install_root=install_root)

    assert plan.status == "unsupported_permissions"
    assert plan.adapter == "unsupported_permissions_v034"
    assert plan.runtime_argv == ()


def test_network_and_persistent_data_are_explicit_permissions(tmp_path: Path) -> None:
    receipt, _, install_root, _ = _install(
        tmp_path,
        permissions=("runtime.data.persist", "runtime.network.inherit"),
    )

    plan = plan_installed_runtime(receipt.to_dict(), install_root=install_root)

    assert plan.status == "ready_for_review"
    assert plan.network_mode == "inherit"
    assert plan.data_mode == "persistent"
    assert plan.requested_runtime_permissions == (
        "runtime.data.persist",
        "runtime.network.inherit",
    )
    assert plan.policy.network_mode == "inherit"


def test_runtime_request_requires_exact_plan_and_permissions(tmp_path: Path) -> None:
    receipt, _, install_root, _ = _install(
        tmp_path,
        permissions=("runtime.data.persist",),
    )
    plan = plan_installed_runtime(receipt.to_dict(), install_root=install_root)

    request = RuntimeLaunchRequest.from_payloads(
        plan.to_dict(),
        receipt.to_dict(),
        approved_runtime_plan_sha256=plan.sha256(),
        approved_runtime_permissions=("runtime.data.persist",),
    )
    assert request.plan == plan

    with pytest.raises(ValueError, match="Approved runtime-plan"):
        RuntimeLaunchRequest.from_payloads(
            plan.to_dict(),
            receipt.to_dict(),
            approved_runtime_plan_sha256="0" * 64,
            approved_runtime_permissions=("runtime.data.persist",),
        )

    with pytest.raises(ValueError, match="exactly match"):
        RuntimeLaunchRequest.from_payloads(
            plan.to_dict(),
            receipt.to_dict(),
            approved_runtime_plan_sha256=plan.sha256(),
            approved_runtime_permissions=(),
        )


def test_runtime_planning_rejects_install_tree_tampering(tmp_path: Path) -> None:
    receipt, _, install_root, install_path = _install(tmp_path)
    (install_path / ".phios" / "manifest.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="installed tree changed"):
        plan_installed_runtime(receipt.to_dict(), install_root=install_root)


def test_runtime_launch_reverifies_tree_after_review(tmp_path: Path) -> None:
    receipt, _, install_root, install_path = _install(tmp_path)
    plan = plan_installed_runtime(receipt.to_dict(), install_root=install_root)
    request = RuntimeLaunchRequest.from_payloads(
        plan.to_dict(),
        receipt.to_dict(),
        approved_runtime_plan_sha256=plan.sha256(),
        approved_runtime_permissions=(),
    )
    (install_path / "payload" / "main.js").write_text("tampered", encoding="utf-8")

    with pytest.raises(ValueError, match="installed tree changed"):
        InstalledRuntimeService(
            runner_factory=lambda policy, payload, data: FakeRuntimeRunner(
                policy,
                payload,
                data,
            )
        ).launch(
            request,
            install_root=install_root,
            data_root=tmp_path / "data",
            receipt_root=tmp_path / "receipts",
        )


def test_runtime_launch_executes_reviewed_plan_and_persists_receipt(
    tmp_path: Path,
) -> None:
    receipt, _, install_root, _ = _install(tmp_path)
    plan = plan_installed_runtime(receipt.to_dict(), install_root=install_root)
    request = RuntimeLaunchRequest.from_payloads(
        plan.to_dict(),
        receipt.to_dict(),
        approved_runtime_plan_sha256=plan.sha256(),
        approved_runtime_permissions=(),
    )
    created: list[FakeRuntimeRunner] = []

    def factory(
        policy: RuntimeSandboxPolicy,
        payload: Path,
        data: Path | None,
    ) -> FakeRuntimeRunner:
        runner = FakeRuntimeRunner(policy, payload, data)
        created.append(runner)
        return runner

    result = InstalledRuntimeService(runner_factory=factory).launch(
        request,
        install_root=install_root,
        data_root=tmp_path / "data",
        receipt_root=tmp_path / "receipts",
    )

    assert result.receipt.status == "exited_success"
    assert result.receipt.runtime_plan_sha256 == plan.sha256()
    assert result.receipt.install_receipt_sha256 == receipt.sha256()
    assert result.receipt.network_mode == "deny"
    assert result.receipt.controls.network_namespace_enforced is True
    assert result.receipt.controls.host_network_inherited is False
    assert result.receipt.controls.installed_payload_read_only is True
    assert result.receipt.controls.persistent_data_writable_mount is False
    assert result.receipt.stdout_byte_count == 5
    assert RuntimeLaunchReceipt.from_dict(result.receipt.to_dict()) == result.receipt
    assert result.receipt_persisted is True
    assert Path(result.receipt_path).is_file()
    assert created[0].preflight_calls == 1
    assert created[0].probed == ["node"]
    assert created[0].plans == [plan]


def test_persistent_data_mount_is_created_only_with_permission(tmp_path: Path) -> None:
    receipt, _, install_root, _ = _install(
        tmp_path,
        permissions=("runtime.data.persist",),
    )
    plan = plan_installed_runtime(receipt.to_dict(), install_root=install_root)
    request = RuntimeLaunchRequest.from_payloads(
        plan.to_dict(),
        receipt.to_dict(),
        approved_runtime_plan_sha256=plan.sha256(),
        approved_runtime_permissions=("runtime.data.persist",),
    )
    created: list[FakeRuntimeRunner] = []

    def factory(
        policy: RuntimeSandboxPolicy,
        payload: Path,
        data: Path | None,
    ) -> FakeRuntimeRunner:
        runner = FakeRuntimeRunner(policy, payload, data)
        created.append(runner)
        return runner

    result = InstalledRuntimeService(runner_factory=factory).launch(
        request,
        install_root=install_root,
        data_root=tmp_path / "data",
        receipt_root=tmp_path / "receipts",
    )

    assert created[0].data_path == (tmp_path / "data" / "phi.runtime-example").resolve()
    assert result.receipt.controls.persistent_data_writable_mount is True


def test_bubblewrap_runtime_command_mounts_payload_read_only_and_denies_network(
    tmp_path: Path,
) -> None:
    payload = tmp_path / "payload"
    payload.mkdir()
    policy = RuntimeSandboxPolicy(network_mode="deny")
    runner = BubblewrapRuntimeRunner(
        policy,
        payload_root=payload,
        data_path=None,
        bwrap_path="/usr/bin/bwrap",
        prlimit_path="/usr/bin/prlimit",
    )

    command = runner.command_for(
        executable_path="/usr/bin/node",
        argv_tail=("/app/main.js",),
    )

    payload_index = command.index(str(payload.resolve()))
    assert command[payload_index - 1] == "--ro-bind"
    assert command[payload_index + 1] == "/app"
    assert "--unshare-net" in command
    assert "/phios/app-data" not in command


def test_bubblewrap_runtime_command_binds_persistent_data_only_when_reviewed(
    tmp_path: Path,
) -> None:
    payload = tmp_path / "payload"
    data = tmp_path / "data"
    payload.mkdir()
    data.mkdir()
    policy = RuntimeSandboxPolicy(network_mode="inherit")
    runner = BubblewrapRuntimeRunner(
        policy,
        payload_root=payload,
        data_path=data,
        bwrap_path="/usr/bin/bwrap",
        prlimit_path="/usr/bin/prlimit",
    )

    command = runner.command_for(
        executable_path="/usr/bin/node",
        argv_tail=("/app/main.js",),
    )

    data_index = command.index(str(data.resolve()))
    assert command[data_index - 1] == "--bind"
    assert command[data_index + 1] == "/phios/app-data"
    assert "--unshare-net" not in command
    assert "PHIOS_APP_DATA" in command


def test_runtime_plan_rejects_install_outside_configured_root(tmp_path: Path) -> None:
    receipt, _, _, _ = _install(tmp_path)
    wrong_root = tmp_path / "different-root"
    wrong_root.mkdir()

    with pytest.raises(ValueError, match="escaped configured root"):
        plan_installed_runtime(receipt.to_dict(), install_root=wrong_root)


def test_runtime_receipt_rejects_digest_tampering(tmp_path: Path) -> None:
    receipt, _, install_root, _ = _install(tmp_path)
    plan = plan_installed_runtime(receipt.to_dict(), install_root=install_root)
    request = RuntimeLaunchRequest.from_payloads(
        plan.to_dict(),
        receipt.to_dict(),
        approved_runtime_plan_sha256=plan.sha256(),
        approved_runtime_permissions=(),
    )
    result = InstalledRuntimeService(
        runner_factory=lambda policy, payload, data: FakeRuntimeRunner(
            policy,
            payload,
            data,
        )
    ).launch(
        request,
        install_root=install_root,
        data_root=tmp_path / "data",
        receipt_root=tmp_path / "receipts",
    )
    payload = result.receipt.to_dict()
    payload["installed_tree_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="digest"):
        RuntimeLaunchReceipt.from_dict(payload)
