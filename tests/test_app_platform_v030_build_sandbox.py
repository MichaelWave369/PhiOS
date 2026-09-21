from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from phios.apps.build_execution import (
    BuildExecutionRequest,
    ProcessResult,
    StreamCapture,
    ToolIdentity,
)
from phios.apps.build_plan import plan_build_from_payloads
from phios.apps.manifest import AppManifest
from phios.apps.control_plane_isolation import (
    ControlPlaneIsolationReceipt,
    ControlPlaneSurfaceMap,
    SandboxReachabilitySnapshot,
    default_phios_control_plane_surfaces,
    evaluate_control_plane_isolation,
)
from phios.apps.sandbox import (
    BuildSandboxPolicy,
    BubblewrapSandboxRunner,
    SandboxBackendIdentity,
    SandboxControlEvidence,
    SandboxedBuildExecutionService,
)


def _manifest(runtime: str = "node", target: str = "package.json") -> AppManifest:
    return AppManifest.from_dict(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "phi.example",
            "name": "Example",
            "version": "1.0.0",
            "description": "Example app",
            "source": {
                "repository_url": "https://github.com/example/example",
                "license_expression": "MIT",
                "redistribution": "unknown",
            },
            "entrypoint": {"runtime": runtime, "target": target},
            "permissions": [],
        }
    )


def _intake(manifest: AppManifest) -> dict[str, Any]:
    return {
        "evidence": {
            "repository_url": "https://github.com/example/example",
            "head_sha": "a" * 40,
        },
        "proposal": {
            "status": "inferred_candidate",
            "repository_url": "https://github.com/example/example",
            "app_id": manifest.app_id,
            "permissions_source": "not_declared",
        },
        "manifest_candidate": manifest.to_dict(),
    }


def _receipt(root: Path, manifest: AppManifest) -> dict[str, Any]:
    files = [path for path in root.rglob("*") if path.is_file()]
    return {
        "schema_version": "phios.source_acquisition_receipt.v0.1",
        "receipt_id": "11111111-1111-1111-1111-111111111111",
        "timestamp_utc": "2026-09-19T00:00:00+00:00",
        "app_id": manifest.app_id,
        "repository_url": "https://github.com/example/example",
        "commit_sha": "a" * 40,
        "manifest_sha256": manifest.sha256(),
        "archive_sha256": "b" * 64,
        "tree_sha256": "c" * 64,
        "file_count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
        "workspace_path": str(root.resolve()),
        "status": "acquired",
    }


def _locked_node_plan(root: Path) -> tuple[dict[str, Any], Any]:
    manifest = _manifest()
    (root / "package.json").write_text(
        json.dumps(
            {
                "name": "example",
                "scripts": {"build": "vite build"},
                "devDependencies": {"vite": "^7.0.0"},
            }
        ),
        encoding="utf-8",
    )
    (root / "package-lock.json").write_text("{}", encoding="utf-8")
    (root / "vite.config.js").write_text("export default {}", encoding="utf-8")
    receipt = _receipt(root, manifest)
    plan = plan_build_from_payloads(_intake(manifest), receipt)
    return receipt, plan


def _request(plan: Any, receipt: dict[str, Any]) -> BuildExecutionRequest:
    return BuildExecutionRequest.from_payloads(
        plan.to_dict(),
        receipt,
        approved_plan_sha256=plan.sha256(),
        approved_source_snapshot_sha256=plan.source_snapshot_sha256,
        approved_permissions=plan.requested_build_permissions,
    )


def _empty_capture() -> StreamCapture:
    return StreamCapture(
        byte_count=0,
        sha256=hashlib.sha256(b"").hexdigest(),
        preview="",
        preview_truncated=False,
    )


class FakeSandboxRunner:
    isolation_mode = "fake_linux_namespace_sandbox"

    def __init__(
        self,
        policy: BuildSandboxPolicy,
        *,
        control_plane_surfaces: ControlPlaneSurfaceMap | None = None,
    ) -> None:
        self.policy = policy
        self.control_plane_surfaces = (
            control_plane_surfaces or default_phios_control_plane_surfaces()
        )
        self.network_sandbox_enforced = policy.network_mode == "deny"
        self.preflight_calls = 0
        self.runs: list[str] = []

    def preflight(self) -> SandboxBackendIdentity:
        self.preflight_calls += 1
        return SandboxBackendIdentity(
            backend="bubblewrap",
            executable_path="/usr/bin/bwrap",
            version="bubblewrap 0.test",
            version_output_sha256=hashlib.sha256(b"bwrap-test").hexdigest(),
            platform_system="Linux",
            platform_machine="x86_64",
        )

    def control_evidence(self) -> SandboxControlEvidence:
        return SandboxControlEvidence(
            mount_namespace_enforced=True,
            user_namespace_enforced=True,
            pid_namespace_enforced=True,
            ipc_namespace_enforced=True,
            uts_namespace_enforced=True,
            cgroup_namespace_requested=False,
            private_proc=True,
            private_dev=True,
            private_tmp=True,
            private_home=True,
            workspace_only_writable_mount=True,
            host_system_roots_read_only=True,
            network_namespace_enforced=self.policy.network_mode == "deny",
            host_network_inherited=self.policy.network_mode == "inherit",
            wall_clock_timeout_enforced=True,
            cpu_rlimit_enforced=True,
            address_space_rlimit_enforced=True,
            open_files_rlimit_enforced=True,
            file_size_rlimit_enforced=True,
            process_count_limit_enforced=False,
            seccomp_enforced=False,
            network_allowlist_enforced=False,
            parent_death_enforced=True,
        )

    def control_plane_isolation_receipt(
        self,
        *,
        source_root: Path,
        evaluated_at: str,
    ) -> ControlPlaneIsolationReceipt:
        controls = self.control_evidence()
        snapshot = SandboxReachabilitySnapshot.build(
            source_root=source_root,
            network_mode=self.policy.network_mode,
            mount_namespace_enforced=controls.mount_namespace_enforced,
            user_namespace_enforced=controls.user_namespace_enforced,
            pid_namespace_enforced=controls.pid_namespace_enforced,
            ipc_namespace_enforced=controls.ipc_namespace_enforced,
            network_namespace_enforced=controls.network_namespace_enforced,
        )
        return evaluate_control_plane_isolation(
            surface_map=self.control_plane_surfaces,
            snapshot=snapshot,
            evaluated_at=evaluated_at,
        )

    def probe(
        self,
        *,
        logical_tool: str,
        executable_tool: str,
        argv: tuple[str, ...],
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> ToolIdentity:
        assert env["PHIOS_EXECUTION_SOURCE"]
        assert timeout_seconds > 0
        return ToolIdentity(
            logical_tool=logical_tool,
            executable_path=f"/usr/bin/{executable_tool}",
            version=f"{logical_tool} test",
            version_output_sha256=hashlib.sha256(logical_tool.encode()).hexdigest(),
        )

    def run(
        self,
        step: Any,
        *,
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> ProcessResult:
        self.runs.append(step.step_id)
        if step.step_id == "build":
            dist = cwd / "dist"
            dist.mkdir(parents=True, exist_ok=True)
            (dist / "index.js").write_text("sandbox-built", encoding="utf-8")
        return ProcessResult(
            exit_code=0,
            timed_out=False,
            duration_ms=7,
            stdout=_empty_capture(),
            stderr=_empty_capture(),
        )


def test_sandbox_policy_digest_is_deterministic_and_tamper_evident() -> None:
    policy = BuildSandboxPolicy()
    payload = policy.to_dict()

    assert payload["policy_sha256"] == policy.sha256()
    assert BuildSandboxPolicy.from_dict(payload) == policy

    payload["cpu_seconds"] = 601
    with pytest.raises(ValueError, match="digest"):
        BuildSandboxPolicy.from_dict(payload)


def test_bubblewrap_command_denies_network_by_default(tmp_path: Path) -> None:
    policy = BuildSandboxPolicy(network_mode="deny")
    runner = BubblewrapSandboxRunner(
        policy,
        bwrap_path="/usr/bin/bwrap",
        prlimit_path="/usr/bin/prlimit",
    )

    command = runner.command_for(
        executable_path="/usr/bin/python3",
        argv_tail=("-c", "print('phi')"),
        source_root=tmp_path,
        cwd=tmp_path,
    )

    assert command[0] == "/usr/bin/bwrap"
    assert "--unshare-user" in command
    assert "--unshare-ipc" in command
    assert "--unshare-pid" in command
    assert "--unshare-uts" in command
    assert "--unshare-net" in command
    assert "--share-net" not in command
    assert "--clearenv" in command
    assert "--tmpfs" in command
    assert "--bind" in command
    assert str(tmp_path.resolve()) in command
    assert "/workspace" in command
    assert "PHIOS_BUILD_SANDBOX" in command
    assert "/usr/bin/prlimit" in command
    assert f"--cpu={policy.cpu_seconds}" in command
    assert f"--as={policy.address_space_bytes}" in command
    assert f"--nofile={policy.max_open_files}" in command
    assert f"--fsize={policy.max_file_size_bytes}" in command


def test_bubblewrap_inherit_mode_explicitly_shares_network(tmp_path: Path) -> None:
    runner = BubblewrapSandboxRunner(
        BuildSandboxPolicy(network_mode="inherit"),
        bwrap_path="/usr/bin/bwrap",
        prlimit_path="/usr/bin/prlimit",
    )
    command = runner.command_for(
        executable_path="/usr/bin/python3",
        argv_tail=("--version",),
        source_root=tmp_path,
        cwd=tmp_path,
    )

    assert "--unshare-user" in command
    assert "--unshare-net" not in command
    assert "--share-net" not in command


def test_command_builder_rejects_tool_outside_read_only_system_roots(
    tmp_path: Path,
) -> None:
    runner = BubblewrapSandboxRunner(
        BuildSandboxPolicy(),
        bwrap_path="/usr/bin/bwrap",
        prlimit_path="/usr/bin/prlimit",
    )

    with pytest.raises(ValueError, match="outside sandbox"):
        runner.command_for(
            executable_path=str(tmp_path / "evil-tool"),
            argv_tail=(),
            source_root=tmp_path,
            cwd=tmp_path,
        )


def test_sandbox_service_emits_dual_bound_receipts(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    receipt, plan = _locked_node_plan(source)
    policy = BuildSandboxPolicy(network_mode="deny")
    runner = FakeSandboxRunner(policy)

    result = SandboxedBuildExecutionService(
        policy,
        runner=runner,
    ).execute(
        _request(plan, receipt),
        execution_root=tmp_path / "executions",
    )

    assert result.execution.status == "success"
    assert result.execution.isolation_mode == "fake_linux_namespace_sandbox"
    assert result.execution.network_sandbox_enforced is True
    assert result.sandbox.build_execution_receipt_sha256 == result.execution.sha256()
    assert result.sandbox.plan_sha256 == plan.sha256()
    assert result.sandbox.source_snapshot_sha256 == plan.source_snapshot_sha256
    assert result.sandbox.controls.network_namespace_enforced is True
    assert result.sandbox.controls.network_allowlist_enforced is False
    assert result.sandbox.controls.seccomp_enforced is False
    assert result.sandbox.containment_level == "linux_namespaces_network_denied_rlimits"
    assert result.control_plane_isolation.status == "ISOLATED"
    assert result.control_plane_isolation.control_plane_reachable is False
    assert result.control_plane_isolation.mutation_reachable is False
    assert result.control_plane_isolation.action_authority is False
    assert result.control_plane_isolation.execution_authority is False
    assert result.sandbox.control_plane_isolation_receipt_sha256 == (
        result.control_plane_isolation.receipt_sha256
    )
    assert result.sandbox_receipt_persisted is True
    assert result.sandbox_receipt_path is not None
    assert Path(result.sandbox_receipt_path).is_file()
    assert result.control_plane_receipt_persisted is True
    assert result.control_plane_receipt_path is not None
    assert Path(result.control_plane_receipt_path).is_file()
    assert runner.preflight_calls == 1
    assert runner.runs == ["dependencies", "build"]

    persisted = json.loads(Path(result.sandbox_receipt_path).read_text(encoding="utf-8"))
    assert persisted["sandbox_receipt_sha256"] == result.sandbox.sha256()


def test_control_plane_overlap_blocks_before_backend_preflight(tmp_path: Path) -> None:
    source = tmp_path / "control" / "source"
    source.mkdir(parents=True)
    receipt, plan = _locked_node_plan(source)
    policy = BuildSandboxPolicy(network_mode="deny")
    surfaces = ControlPlaneSurfaceMap.build(
        protected_paths=(tmp_path / "control",),
        source="test-control-plane",
    )
    runner = FakeSandboxRunner(policy, control_plane_surfaces=surfaces)

    with pytest.raises(ValueError, match="control-plane isolation failed closed"):
        SandboxedBuildExecutionService(policy, runner=runner).execute(
            _request(plan, receipt),
            execution_root=tmp_path / "executions",
        )

    assert runner.preflight_calls == 1
    assert runner.runs == []


def test_host_network_inheritance_requires_network_permission(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    manifest = _manifest(runtime="static_web", target="index.html")
    (source / "index.html").write_text("<html>phi</html>", encoding="utf-8")
    receipt = _receipt(source, manifest)
    plan = plan_build_from_payloads(_intake(manifest), receipt)
    policy = BuildSandboxPolicy(network_mode="inherit")
    runner = FakeSandboxRunner(policy)

    with pytest.raises(ValueError, match="network.dependencies"):
        SandboxedBuildExecutionService(policy, runner=runner).execute(
            _request(plan, receipt),
            execution_root=tmp_path / "executions",
        )

    assert runner.preflight_calls == 0


def test_host_network_receipt_does_not_claim_network_isolation(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    receipt, plan = _locked_node_plan(source)
    policy = BuildSandboxPolicy(network_mode="inherit")
    runner = FakeSandboxRunner(policy)

    result = SandboxedBuildExecutionService(policy, runner=runner).execute(
        _request(plan, receipt),
        execution_root=tmp_path / "executions",
    )

    assert result.execution.network_sandbox_enforced is False
    assert result.sandbox.controls.network_namespace_enforced is False
    assert result.sandbox.controls.host_network_inherited is True
    assert result.sandbox.containment_level == "linux_namespaces_host_network_rlimits"


def test_runner_policy_must_match_service_policy() -> None:
    deny = BuildSandboxPolicy(network_mode="deny")
    inherit = BuildSandboxPolicy(network_mode="inherit")

    with pytest.raises(ValueError, match="policy does not match"):
        SandboxedBuildExecutionService(
            deny,
            runner=FakeSandboxRunner(inherit),
        )


def test_resource_policy_rejects_unbounded_values() -> None:
    with pytest.raises(ValueError, match="wall_clock_seconds"):
        BuildSandboxPolicy(wall_clock_seconds=0)
    with pytest.raises(ValueError, match="address_space_bytes"):
        BuildSandboxPolicy(address_space_bytes=64 * 1024 * 1024)
    with pytest.raises(ValueError, match="max_open_files"):
        BuildSandboxPolicy(max_open_files=10)
