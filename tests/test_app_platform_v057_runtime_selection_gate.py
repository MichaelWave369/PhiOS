from __future__ import annotations

from dataclasses import dataclass

import pytest

import phios.apps.runtime_selection_gate as gate
from phios.apps.runtime_backend_selection import (
    propose_runtime_backend_selection,
    qualify_runtime_backend,
    select_runtime_backend,
)
from phios.apps.runtime_selection_gate import (
    RuntimeSelectionExecutionReceipt,
    SelectedToolchainRuntimeRequest,
    SelectedToolchainRuntimeService,
)
from phios.apps.sandbox import BuildSandboxPolicy
from phios.apps.toolchain_attestation import (
    ToolProbeObservation,
    ToolchainAttestation,
    ToolchainSandboxPlan,
)
from phios.apps.toolchain_capsule import ToolchainCapsule, ToolchainTool
from phios.apps.toolchain_runtime import (
    OciRuntimeAdapterIdentity,
    OciRuntimeControlEvidence,
)


def _capsule() -> ToolchainCapsule:
    return ToolchainCapsule(
        capsule_id="phios.node-npm.v057",
        family="node_npm",
        platform="linux_x86_64",
        artifact_kind="oci_image",
        artifact_ref="registry.example/phios/node@sha256:" + "1" * 64,
        artifact_sha256="1" * 64,
        tools=(
            ToolchainTool("node", "22.0.0"),
            ToolchainTool("npm", "10.0.0"),
        ),
    )


def _attestation(capsule: ToolchainCapsule) -> ToolchainAttestation:
    return ToolchainAttestation(
        app_id="phi.v057-example",
        commit_sha="a" * 40,
        plan_sha256="2" * 64,
        requirement_sha256="3" * 64,
        capsule_sha256=capsule.sha256(),
        binding_sha256="4" * 64,
        acquisition_receipt_sha256="5" * 64,
        artifact_sha256=capsule.artifact_sha256,
        inspector_id="phios.fixture-inspector",
        inspector_version="0.1.0",
        observations=(
            ToolProbeObservation(
                name="node",
                probe_argv=("node", "--version"),
                observed_version="22.0.0",
                subject_locator="/usr/bin/node",
                subject_sha256="6" * 64,
                probe_output_sha256="7" * 64,
            ),
        ),
    )


def _sandbox(
    capsule: ToolchainCapsule,
    attestation: ToolchainAttestation,
) -> ToolchainSandboxPlan:
    return ToolchainSandboxPlan(
        app_id=attestation.app_id,
        commit_sha=attestation.commit_sha,
        build_plan_sha256=attestation.plan_sha256,
        acquisition_receipt_sha256="5" * 64,
        capsule_sha256=capsule.sha256(),
        attestation_sha256=attestation.sha256(),
        capsule_artifact_sha256=capsule.artifact_sha256,
        capsule_storage_path="/var/lib/phios/capsules/node.oci",
        sandbox_policy=BuildSandboxPolicy(network_mode="deny"),
        steps=(),
        status="ready_for_runtime_adapter_review",
    )


def _identity() -> OciRuntimeAdapterIdentity:
    return OciRuntimeAdapterIdentity(
        adapter_id="phios.podman-rootless",
        adapter_version="0.1.0",
        backend="podman",
        backend_version="podman version 6.1.3",
        backend_binary_sha256="8" * 64,
        platform_system="Linux",
        platform_machine="x86_64",
    )


def _controls() -> OciRuntimeControlEvidence:
    return OciRuntimeControlEvidence(
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


class FakeRunner:
    isolation_mode = "fixture"
    network_sandbox_enforced = True

    def __init__(
        self,
        sandbox: ToolchainSandboxPlan,
        capsule: ToolchainCapsule,
        *,
        identity: OciRuntimeAdapterIdentity | None = None,
    ) -> None:
        self.capsule_artifact_sha256 = capsule.artifact_sha256
        self.capsule_storage_path = sandbox.capsule_storage_path
        self.sandbox_plan_sha256 = sandbox.sha256()
        self.policy_sha256 = sandbox.sandbox_policy.sha256()
        self.identity = identity or _identity()

    def preflight(self) -> OciRuntimeAdapterIdentity:
        return self.identity

    def control_evidence(self) -> OciRuntimeControlEvidence:
        return _controls()

    def runtime_observations(self):
        raise AssertionError("selection qualification must not observe tools")

    def probe(self, **kwargs):
        raise AssertionError("selection qualification must not probe tools")

    def run(self, *args, **kwargs):
        raise AssertionError("selection qualification must not execute build steps")


@dataclass
class FakeBuildPlan:
    app_id: str = "phi.v057-example"
    commit_sha: str = "a" * 40


@dataclass
class FakeRuntimeRequest:
    sandbox_plan: ToolchainSandboxPlan
    capsule: ToolchainCapsule
    attestation: ToolchainAttestation
    execution_approval_id: str = "99999999-9999-9999-9999-999999999999"
    build_plan: FakeBuildPlan = FakeBuildPlan()


@dataclass
class FakeRuntimeReceipt:
    runtime_identity: OciRuntimeAdapterIdentity
    controls: OciRuntimeControlEvidence

    def sha256(self) -> str:
        return "9" * 64


@dataclass
class FakeUnderlyingResult:
    runtime: FakeRuntimeReceipt


class FakeToolchainRuntimeService:
    def __init__(self, *, runner) -> None:
        self.runner = runner

    def execute(self, request, *, execution_root, receipt_root=None):
        del request, execution_root, receipt_root
        return FakeUnderlyingResult(
            runtime=FakeRuntimeReceipt(
                runtime_identity=self.runner.preflight(),
                controls=self.runner.control_evidence(),
            )
        )


def _selection_lineage():
    capsule = _capsule()
    attestation = _attestation(capsule)
    sandbox = _sandbox(capsule, attestation)
    runner = FakeRunner(sandbox, capsule)
    qualification = qualify_runtime_backend(
        sandbox,
        capsule,
        attestation,
        runner,
    )
    proposal = propose_runtime_backend_selection(
        sandbox,
        capsule,
        attestation,
        (qualification,),
    )
    selection = select_runtime_backend(
        proposal,
        qualification,
        selection_id="88888888-8888-8888-8888-888888888888",
        approved_qualification_sha256=qualification.sha256(),
    )
    runtime_request = FakeRuntimeRequest(
        sandbox_plan=sandbox,
        capsule=capsule,
        attestation=attestation,
    )
    selected = SelectedToolchainRuntimeRequest(
        runtime_request=runtime_request,  # type: ignore[arg-type]
        qualification=qualification,
        selection=selection,
        approved_selection_receipt_sha256=selection.sha256(),
    )
    return selected, runner


def test_selected_request_binds_exact_operator_selection() -> None:
    selected, _ = _selection_lineage()

    assert selected.selection.operator_confirmed is True
    assert selected.selection.execution_authority is False
    assert (
        selected.approved_selection_receipt_sha256
        == selected.selection.sha256()
    )


def test_stale_selection_approval_is_rejected() -> None:
    selected, _ = _selection_lineage()

    with pytest.raises(ValueError, match="approved selection receipt"):
        SelectedToolchainRuntimeRequest(
            runtime_request=selected.runtime_request,
            qualification=selected.qualification,
            selection=selected.selection,
            approved_selection_receipt_sha256="0" * 64,
        )


def test_live_backend_drift_is_rejected_before_execution() -> None:
    selected, _ = _selection_lineage()
    changed = OciRuntimeAdapterIdentity(
        adapter_id="phios.podman-rootless",
        adapter_version="0.1.0",
        backend="podman",
        backend_version="podman version 6.1.4",
        backend_binary_sha256="8" * 64,
        platform_system="Linux",
        platform_machine="x86_64",
    )
    runner = FakeRunner(
        selected.runtime_request.sandbox_plan,
        selected.runtime_request.capsule,
        identity=changed,
    )

    with pytest.raises(ValueError, match="live runtime backend qualification"):
        SelectedToolchainRuntimeService(runner=runner).execute(
            selected,
            execution_root=Path("/tmp/not-used"),
        )


def test_selected_backend_delegates_and_binds_execution_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    selected, runner = _selection_lineage()
    monkeypatch.setattr(
        gate,
        "ToolchainRuntimeService",
        FakeToolchainRuntimeService,
    )

    result = SelectedToolchainRuntimeService(runner=runner).execute(
        selected,
        execution_root=tmp_path / "executions",
    )

    receipt = result.selection_receipt
    assert receipt.status == "executed_selected_backend"
    assert receipt.operator_selection_verified is True
    assert receipt.selection_receipt_sha256 == selected.selection.sha256()
    assert receipt.qualification_sha256 == selected.qualification.sha256()
    assert receipt.selected_adapter_id == "phios.podman-rootless"
    assert receipt.reusable_execution_authority is False
    assert receipt.network_authority is False
    assert receipt.install_authority is False
    assert receipt.host_write_authority is False
    assert RuntimeSelectionExecutionReceipt.from_dict(receipt.to_dict()) == receipt


def test_selection_execution_receipt_rejects_authority_smuggling(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    selected, runner = _selection_lineage()
    monkeypatch.setattr(
        gate,
        "ToolchainRuntimeService",
        FakeToolchainRuntimeService,
    )
    result = SelectedToolchainRuntimeService(runner=runner).execute(
        selected,
        execution_root=tmp_path / "executions",
    )
    data = result.selection_receipt.to_dict()
    data["install_authority"] = True

    with pytest.raises(ValueError, match="must remain false"):
        RuntimeSelectionExecutionReceipt.from_dict(data)
