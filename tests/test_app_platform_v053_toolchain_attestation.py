from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from phios.apps.build_plan import BuildPlan, plan_build_from_payloads
from phios.apps.manifest import AppManifest
from phios.apps.sandbox import BuildSandboxPolicy
from phios.apps.toolchain_acquisition import CapsuleAcquisitionReceipt
from phios.apps.toolchain_attestation import (
    ToolProbeObservation,
    ToolchainAttestation,
    ToolchainSandboxPlan,
    attest_toolchain,
    plan_toolchain_sandbox,
)
from phios.apps.toolchain_capsule import (
    ToolchainCapsule,
    ToolchainTool,
    bind_toolchain_capsule,
    derive_toolchain_requirement,
)


def _manifest(runtime: str = "node", target: str = "package.json") -> AppManifest:
    return AppManifest.from_dict(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "phi.v053-example",
            "name": "v0.53 Example",
            "version": "1.0.0",
            "description": "Toolchain attestation contract fixture",
            "source": {
                "repository_url": "https://github.com/example/v053-example",
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


def _node_plan(tmp_path: Path, *, offline: bool = False) -> BuildPlan:
    tmp_path.mkdir(parents=True, exist_ok=True)
    manifest = _manifest()
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "example", "scripts": {"build": "vite build"}}),
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    (tmp_path / "vite.config.js").write_text("export default {}", encoding="utf-8")
    plan = plan_build_from_payloads(_intake(manifest), _source_receipt(tmp_path, manifest))
    if not offline:
        return plan

    data = plan.to_dict()
    for step in data["steps"]:
        step["requires_network"] = False
    data["requested_build_permissions"] = [
        value for value in data["requested_build_permissions"]
        if value != "build.network.dependencies"
    ]
    data.pop("plan_sha256")
    return BuildPlan.from_dict({**data, "plan_sha256": _plan_digest(data)})


def _plan_digest(data: dict[str, Any]) -> str:
    body = dict(data)
    body.pop("plan_sha256", None)
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _capsule() -> ToolchainCapsule:
    return ToolchainCapsule(
        capsule_id="phios.node-npm.v053",
        family="node_npm",
        platform="linux_x86_64",
        artifact_kind="oci_image",
        artifact_ref="registry.example/phios/node-npm@sha256:" + "d" * 64,
        artifact_sha256="d" * 64,
        tools=(
            ToolchainTool("node", "22.0.0"),
            ToolchainTool("npm", "10.0.0"),
        ),
    )


def _acquisition(plan: BuildPlan, capsule: ToolchainCapsule, tmp_path: Path) -> CapsuleAcquisitionReceipt:
    requirement = derive_toolchain_requirement(plan)
    binding = bind_toolchain_capsule(requirement, capsule)
    return CapsuleAcquisitionReceipt(
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
        artifact_bytes=1234,
        storage_path=str((tmp_path / "capsule.oci").resolve()),
        storage_state="created",
    )


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


def test_attestation_binds_exact_plan_capsule_acquisition_and_tools(tmp_path: Path) -> None:
    plan = _node_plan(tmp_path / "source")
    capsule = _capsule()
    acquisition = _acquisition(plan, capsule, tmp_path)

    attestation = attest_toolchain(
        plan,
        capsule,
        acquisition,
        _observations(),
        inspector_id="phios.fixture-inspector",
        inspector_version="0.1.0",
    )

    assert attestation.status == "attested_for_review"
    assert attestation.plan_sha256 == plan.sha256()
    assert attestation.acquisition_receipt_sha256 == acquisition.sha256()
    assert attestation.execution_authority is False
    assert attestation.network_authority is False
    assert attestation.install_authority is False
    assert attestation.host_write_authority is False
    assert ToolchainAttestation.from_dict(attestation.to_dict()) == attestation


def test_version_mismatch_is_rejected(tmp_path: Path) -> None:
    plan = _node_plan(tmp_path / "source")
    capsule = _capsule()
    acquisition = _acquisition(plan, capsule, tmp_path)
    observations = list(_observations())
    observations[0] = ToolProbeObservation(
        name="node",
        probe_argv=("node", "--version"),
        observed_version="21.0.0",
        subject_locator="/usr/bin/node",
        subject_sha256="1" * 64,
        probe_output_sha256="2" * 64,
    )

    with pytest.raises(ValueError, match="observed version"):
        attest_toolchain(
            plan,
            capsule,
            acquisition,
            tuple(observations),
            inspector_id="phios.fixture-inspector",
            inspector_version="0.1.0",
        )


def test_probe_argv_is_fixed_by_contract() -> None:
    with pytest.raises(ValueError, match="Probe argv"):
        ToolProbeObservation(
            name="node",
            probe_argv=("node", "--help"),
            observed_version="22.0.0",
            subject_locator="/usr/bin/node",
            subject_sha256="1" * 64,
            probe_output_sha256="2" * 64,
        )


def test_missing_tool_observation_is_rejected(tmp_path: Path) -> None:
    plan = _node_plan(tmp_path / "source")
    capsule = _capsule()
    acquisition = _acquisition(plan, capsule, tmp_path)

    with pytest.raises(ValueError, match="tool set"):
        attest_toolchain(
            plan,
            capsule,
            acquisition,
            (_observations()[0],),
            inspector_id="phios.fixture-inspector",
            inspector_version="0.1.0",
        )


def test_network_requiring_plan_is_held_for_dependency_staging(tmp_path: Path) -> None:
    plan = _node_plan(tmp_path / "source")
    capsule = _capsule()
    acquisition = _acquisition(plan, capsule, tmp_path)
    attestation = attest_toolchain(
        plan,
        capsule,
        acquisition,
        _observations(),
        inspector_id="phios.fixture-inspector",
        inspector_version="0.1.0",
    )

    sandbox = plan_toolchain_sandbox(plan, capsule, acquisition, attestation)

    assert sandbox.status == "dependency_staging_required"
    assert sandbox.sandbox_policy.network_mode == "deny"
    assert sandbox.runtime_adapter_required is True
    assert sandbox.execution_authority is False
    assert ToolchainSandboxPlan.from_dict(sandbox.to_dict()) == sandbox


def test_network_free_plan_reaches_runtime_adapter_review(tmp_path: Path) -> None:
    plan = _node_plan(tmp_path / "source", offline=True)
    capsule = _capsule()
    acquisition = _acquisition(plan, capsule, tmp_path)
    attestation = attest_toolchain(
        plan,
        capsule,
        acquisition,
        _observations(),
        inspector_id="phios.fixture-inspector",
        inspector_version="0.1.0",
    )

    sandbox = plan_toolchain_sandbox(plan, capsule, acquisition, attestation)

    assert sandbox.status == "ready_for_runtime_adapter_review"
    assert sandbox.sandbox_policy.network_mode == "deny"


def test_inheriting_network_policy_is_rejected(tmp_path: Path) -> None:
    plan = _node_plan(tmp_path / "source", offline=True)
    capsule = _capsule()
    acquisition = _acquisition(plan, capsule, tmp_path)
    attestation = attest_toolchain(
        plan,
        capsule,
        acquisition,
        _observations(),
        inspector_id="phios.fixture-inspector",
        inspector_version="0.1.0",
    )

    with pytest.raises(ValueError, match="network denial"):
        plan_toolchain_sandbox(
            plan,
            capsule,
            acquisition,
            attestation,
            sandbox_policy=BuildSandboxPolicy(network_mode="inherit"),
        )


def test_attestation_tamper_and_authority_smuggling_are_rejected(tmp_path: Path) -> None:
    plan = _node_plan(tmp_path / "source")
    capsule = _capsule()
    acquisition = _acquisition(plan, capsule, tmp_path)
    attestation = attest_toolchain(
        plan,
        capsule,
        acquisition,
        _observations(),
        inspector_id="phios.fixture-inspector",
        inspector_version="0.1.0",
    )

    data = attestation.to_dict()
    data["inspector_version"] = "tampered"
    with pytest.raises(ValueError, match="digest"):
        ToolchainAttestation.from_dict(data)

    data = attestation.to_dict()
    data["execution_authority"] = True
    with pytest.raises(ValueError, match="must remain false"):
        ToolchainAttestation.from_dict(data)
