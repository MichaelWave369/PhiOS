from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from phios.apps.build_execution import ProcessResult, StreamCapture, ToolIdentity
from phios.apps.build_plan import AcquisitionBinding, BuildPlan, plan_build_from_payloads
from phios.apps.manifest import AppManifest
from phios.apps.sandbox import BuildSandboxPolicy
from phios.apps.toolchain_acquisition import CapsuleAcquisitionReceipt
from phios.apps.toolchain_attestation import (
    ToolProbeObservation,
    attest_toolchain,
    plan_toolchain_sandbox,
)
from phios.apps.toolchain_capsule import (
    ToolchainCapsule,
    ToolchainTool,
    bind_toolchain_capsule,
    derive_toolchain_requirement,
)
from phios.apps.toolchain_runtime import (
    OciRuntimeAdapterIdentity,
    OciRuntimeControlEvidence,
    ToolchainRuntimeReceipt,
    ToolchainRuntimeRequest,
    ToolchainRuntimeService,
)


def _manifest() -> AppManifest:
    return AppManifest.from_dict(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "phi.v054-example",
            "name": "v0.54 Example",
            "version": "1.0.0",
            "description": "Toolchain runtime contract fixture",
            "source": {
                "repository_url": "https://github.com/example/v054-example",
                "license_expression": "MIT",
                "redistribution": "unknown",
            },
            "entrypoint": {"runtime": "node", "target": "package.json"},
            "permissions": [],
        }
    )


def _intake(manifest: AppManifest) -> dict[str, Any]:
    return {
        "evidence": {
            "repository_url": manifest.source.repository_url,
            "head_sha": "a" * 40,
        },
        "proposal": {
            "status": "inferred_candidate",
            "repository_url": manifest.source.repository_url,
            "app_id": manifest.app_id,
            "permissions_source": "not_declared",
        },
        "manifest_candidate": manifest.to_dict(),
    }


def _source_receipt(root: Path, manifest: AppManifest) -> dict[str, Any]:
    files = [path for path in root.rglob("*") if path.is_file()]
    return {
        "schema_version": "phios.source_acquisition_receipt.v0.1",
        "receipt_id": "11111111-1111-1111-1111-111111111111",
        "timestamp_utc": "2026-10-04T00:00:00+00:00",
        "app_id": manifest.app_id,
        "repository_url": manifest.source.repository_url,
        "commit_sha": "a" * 40,
        "manifest_sha256": manifest.sha256(),
        "archive_sha256": "b" * 64,
        "tree_sha256": "c" * 64,
        "file_count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
        "workspace_path": str(root.resolve()),
        "status": "acquired",
    }


def _plan_digest(data: dict[str, Any]) -> str:
    body = dict(data)
    body.pop("plan_sha256", None)
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _plan(root: Path, *, network_free: bool) -> tuple[BuildPlan, AcquisitionBinding]:
    root.mkdir(parents=True, exist_ok=True)
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
    receipt = _source_receipt(root, manifest)
    plan = plan_build_from_payloads(_intake(manifest), receipt)

    if network_free:
        data = plan.to_dict()
        for step in data["steps"]:
            step["requires_network"] = False
        data["requested_build_permissions"] = [
            permission
            for permission in data["requested_build_permissions"]
            if permission != "build.network.dependencies"
        ]
        data["plan_sha256"] = _plan_digest(data)
        plan = BuildPlan.from_dict(data)

    return plan, AcquisitionBinding.from_dict(receipt)


def _capsule(tmp_path: Path) -> tuple[ToolchainCapsule, bytes, Path]:
    payload = b"v0.54-fixture-oci-archive"
    digest = hashlib.sha256(payload).hexdigest()
    storage = tmp_path / "capsule.oci"
    storage.write_bytes(payload)
    capsule = ToolchainCapsule(
        capsule_id="phios.node-npm.v054",
        family="node_npm",
        platform="linux_x86_64",
        artifact_kind="oci_image",
        artifact_ref=f"registry.example/phios/node-npm@sha256:{digest}",
        artifact_sha256=digest,
        tools=(
            ToolchainTool("node", "22.0.0"),
            ToolchainTool("npm", "10.0.0"),
        ),
    )
    return capsule, payload, storage


def _observations() -> tuple[ToolProbeObservation, ...]:
    return (
        ToolProbeObservation(
            name="node",
            probe_argv=("node", "--version"),
            observed_version="22.0.0",
            subject_locator="/usr/bin/node",
            subject_sha256="1" * 64,
            probe_output_sha256="2" * 64,
        ),
        ToolProbeObservation(
            name="npm",
            probe_argv=("npm", "--version"),
            observed_version="10.0.0",
            subject_locator="/usr/bin/npm",
            subject_sha256="3" * 64,
            probe_output_sha256="4" * 64,
        ),
    )


def _lineage(
    tmp_path: Path,
    *,
    network_free: bool = True,
):
    plan, source = _plan(tmp_path / "source", network_free=network_free)
    capsule, payload, storage = _capsule(tmp_path)
    requirement = derive_toolchain_requirement(plan)
    binding = bind_toolchain_capsule(requirement, capsule)
    acquisition = CapsuleAcquisitionReceipt(
        receipt_id="22222222-2222-2222-2222-222222222222",
        timestamp_utc="2026-10-04T00:00:00+00:00",
        app_id=plan.app_id,
        commit_sha=plan.commit_sha,
        plan_sha256=plan.sha256(),
        requirement_sha256=requirement.sha256(),
        capsule_sha256=capsule.sha256(),
        binding_sha256=binding.sha256(),
        capsule_id=capsule.capsule_id,
        family=capsule.family,
        artifact_kind=capsule.artifact_kind,
        artifact_ref=capsule.artifact_ref,
        artifact_sha256=capsule.artifact_sha256,
        artifact_bytes=len(payload),
        storage_path=str(storage.resolve()),
        storage_state="created",
    )
    attestation = attest_toolchain(
        plan,
        capsule,
        acquisition,
        _observations(),
        inspector_id="phios.fixture-inspector",
        inspector_version="0.1.0",
    )
    sandbox = plan_toolchain_sandbox(
        plan,
        capsule,
        acquisition,
        attestation,
        sandbox_policy=BuildSandboxPolicy(network_mode="deny"),
    )
    return plan, source, capsule, acquisition, attestation, sandbox


def _request(tmp_path: Path) -> ToolchainRuntimeRequest:
    plan, source, capsule, acquisition, attestation, sandbox = _lineage(tmp_path)
    return ToolchainRuntimeRequest(
        build_plan=plan,
        source_acquisition=source,
        capsule=capsule,
        capsule_acquisition=acquisition,
        attestation=attestation,
        sandbox_plan=sandbox,
        approved_sandbox_plan_sha256=sandbox.sha256(),
        approved_attestation_sha256=attestation.sha256(),
        approved_source_snapshot_sha256=plan.source_snapshot_sha256,
        approved_build_permissions=plan.requested_build_permissions,
        execution_approval_id="33333333-3333-3333-3333-333333333333",
    )


def _empty_capture() -> StreamCapture:
    return StreamCapture(
        byte_count=0,
        sha256=hashlib.sha256(b"").hexdigest(),
        preview="",
        preview_truncated=False,
    )


class FakeOciRunner:
    isolation_mode = "fixture_oci_network_denied"
    network_sandbox_enforced = True

    def __init__(
        self,
        request: ToolchainRuntimeRequest,
        *,
        observations: tuple[ToolProbeObservation, ...] | None = None,
        controls: OciRuntimeControlEvidence | None = None,
    ) -> None:
        self.capsule_artifact_sha256 = request.capsule.artifact_sha256
        self.capsule_storage_path = request.capsule_acquisition.storage_path
        self.sandbox_plan_sha256 = request.sandbox_plan.sha256()
        self.policy_sha256 = request.sandbox_plan.sandbox_policy.sha256()
        self._observations = observations or request.attestation.observations
        self._controls = controls or OciRuntimeControlEvidence(
            rootfs_read_only=True,
            workspace_bind_read_write=True,
            network_namespace_enforced=True,
            host_network_inherited=False,
            host_control_plane_mounted=False,
            privileged_mode=False,
            capabilities_dropped=True,
            no_new_privileges=True,
            shell_invocation=False,
        )

    def preflight(self) -> OciRuntimeAdapterIdentity:
        return OciRuntimeAdapterIdentity(
            adapter_id="phios.fixture-oci",
            adapter_version="0.1.0",
            backend="fixture",
            backend_version="fixture 1",
            backend_binary_sha256="9" * 64,
            platform_system="Linux",
            platform_machine="x86_64",
        )

    def control_evidence(self) -> OciRuntimeControlEvidence:
        return self._controls

    def runtime_observations(self) -> tuple[ToolProbeObservation, ...]:
        return self._observations

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
        del executable_tool, argv, cwd, env, timeout_seconds
        observation = next(item for item in self._observations if item.name == logical_tool)
        return ToolIdentity(
            logical_tool=logical_tool,
            executable_path=observation.subject_locator,
            version=observation.observed_version,
            version_output_sha256=observation.probe_output_sha256,
        )

    def run(
        self,
        step: Any,
        *,
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> ProcessResult:
        del env, timeout_seconds
        if step.step_id == "build":
            dist = cwd / "dist"
            dist.mkdir(parents=True, exist_ok=True)
            (dist / "index.js").write_text("capsule-built", encoding="utf-8")
        return ProcessResult(
            exit_code=0,
            timed_out=False,
            duration_ms=7,
            stdout=_empty_capture(),
            stderr=_empty_capture(),
        )


def test_exact_approval_executes_once_and_emits_bound_receipt(tmp_path: Path) -> None:
    request = _request(tmp_path)
    runner = FakeOciRunner(request)

    result = ToolchainRuntimeService(runner=runner).execute(
        request,
        execution_root=tmp_path / "executions",
    )

    assert result.execution.status == "success"
    assert result.execution.network_sandbox_enforced is True
    assert result.runtime.build_execution_receipt_sha256 == result.execution.sha256()
    assert result.runtime.sandbox_plan_sha256 == request.sandbox_plan.sha256()
    assert result.runtime.execution_approval_consumed is True
    assert result.runtime.reusable_execution_authority is False
    assert result.runtime.network_authority is False
    assert result.runtime.install_authority is False
    assert result.runtime.host_write_authority is False
    assert ToolchainRuntimeReceipt.from_dict(result.runtime.to_dict()) == result.runtime


def test_stale_sandbox_plan_approval_is_rejected(tmp_path: Path) -> None:
    request = _request(tmp_path)

    with pytest.raises(ValueError, match="approved sandbox plan"):
        replace(request, approved_sandbox_plan_sha256="0" * 64)


def test_dependency_staging_plan_cannot_cross_runtime_boundary(tmp_path: Path) -> None:
    plan, source, capsule, acquisition, attestation, sandbox = _lineage(
        tmp_path,
        network_free=False,
    )
    assert sandbox.status == "dependency_staging_required"

    with pytest.raises(ValueError, match="ready_for_runtime_adapter_review"):
        ToolchainRuntimeRequest(
            build_plan=plan,
            source_acquisition=source,
            capsule=capsule,
            capsule_acquisition=acquisition,
            attestation=attestation,
            sandbox_plan=sandbox,
            approved_sandbox_plan_sha256=sandbox.sha256(),
            approved_attestation_sha256=attestation.sha256(),
            approved_source_snapshot_sha256=plan.source_snapshot_sha256,
            approved_build_permissions=plan.requested_build_permissions,
            execution_approval_id="44444444-4444-4444-4444-444444444444",
        )


def test_capsule_is_rehashed_immediately_before_execution(tmp_path: Path) -> None:
    request = _request(tmp_path)
    runner = FakeOciRunner(request)
    Path(request.capsule_acquisition.storage_path).write_bytes(b"tampered")

    with pytest.raises(ValueError, match="byte count changed|digest changed"):
        ToolchainRuntimeService(runner=runner).execute(
            request,
            execution_root=tmp_path / "executions",
        )


def test_runner_must_bind_exact_capsule_and_plan(tmp_path: Path) -> None:
    request = _request(tmp_path)
    runner = FakeOciRunner(request)
    runner.capsule_artifact_sha256 = "0" * 64

    with pytest.raises(ValueError, match="capsule digest"):
        ToolchainRuntimeService(runner=runner).execute(
            request,
            execution_root=tmp_path / "executions",
        )


def test_runtime_observations_must_match_reviewed_attestation(tmp_path: Path) -> None:
    request = _request(tmp_path)
    wrong = list(request.attestation.observations)
    wrong[0] = ToolProbeObservation(
        name="node",
        probe_argv=("node", "--version"),
        observed_version="21.0.0",
        subject_locator="/usr/bin/node",
        subject_sha256="1" * 64,
        probe_output_sha256="2" * 64,
    )
    runner = FakeOciRunner(request, observations=tuple(wrong))

    with pytest.raises(ValueError, match="runtime tool observations"):
        ToolchainRuntimeService(runner=runner).execute(
            request,
            execution_root=tmp_path / "executions",
        )


def test_control_evidence_fails_closed_on_authority_smuggling(tmp_path: Path) -> None:
    request = _request(tmp_path)

    with pytest.raises(ValueError, match="must remain false"):
        OciRuntimeControlEvidence(
            rootfs_read_only=True,
            workspace_bind_read_write=True,
            network_namespace_enforced=True,
            host_network_inherited=True,
            host_control_plane_mounted=False,
            privileged_mode=False,
            capabilities_dropped=True,
            no_new_privileges=True,
            shell_invocation=False,
        )


def test_execution_approval_cannot_be_replayed(tmp_path: Path) -> None:
    request = _request(tmp_path)
    service = ToolchainRuntimeService(runner=FakeOciRunner(request))

    first = service.execute(
        request,
        execution_root=tmp_path / "executions",
    )
    assert first.runtime.execution_approval_consumed is True

    with pytest.raises(ValueError, match="already been consumed"):
        service.execute(
            request,
            execution_root=tmp_path / "executions",
        )
