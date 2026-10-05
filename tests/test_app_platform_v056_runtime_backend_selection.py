from __future__ import annotations

from dataclasses import replace

import pytest

from phios.apps.podman_runtime import (
    PODMAN_ROOTLESS_ADAPTER_ID,
    PODMAN_ROOTLESS_ADAPTER_VERSION,
)
from phios.apps.runtime_backend_selection import (
    RuntimeBackendQualification,
    RuntimeBackendSelectionProposal,
    RuntimeBackendSelectionReceipt,
    propose_runtime_backend_selection,
    qualify_runtime_backend,
    select_runtime_backend,
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
        capsule_id="phios.node-npm.v056",
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
        app_id="phi.v056-example",
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


def _identity(
    *,
    adapter_id: str = PODMAN_ROOTLESS_ADAPTER_ID,
    adapter_version: str = PODMAN_ROOTLESS_ADAPTER_VERSION,
    backend: str = "podman",
    backend_version: str = "podman version 6.1.3",
) -> OciRuntimeAdapterIdentity:
    return OciRuntimeAdapterIdentity(
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        backend=backend,
        backend_version=backend_version,
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


class FakeBackend:
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
        self._identity = identity or _identity()

    def preflight(self) -> OciRuntimeAdapterIdentity:
        return self._identity

    def control_evidence(self) -> OciRuntimeControlEvidence:
        return _controls()

    def runtime_observations(self):
        raise AssertionError("v0.56 qualification must not run tool observations")

    def probe(self, **kwargs):
        raise AssertionError("v0.56 qualification must not probe build tools")

    def run(self, *args, **kwargs):
        raise AssertionError("v0.56 qualification must not execute build steps")


def _qualified():
    capsule = _capsule()
    attestation = _attestation(capsule)
    sandbox = _sandbox(capsule, attestation)
    runner = FakeBackend(sandbox, capsule)
    qualification = qualify_runtime_backend(
        sandbox,
        capsule,
        attestation,
        runner,
    )
    return capsule, attestation, sandbox, qualification


def test_exact_podman_backend_qualifies_without_execution() -> None:
    capsule, attestation, sandbox, qualification = _qualified()

    assert qualification.status == "qualified_for_selection"
    assert qualification.sandbox_plan_sha256 == sandbox.sha256()
    assert qualification.capsule_sha256 == capsule.sha256()
    assert qualification.attestation_sha256 == attestation.sha256()
    assert qualification.runtime_identity.adapter_id == PODMAN_ROOTLESS_ADAPTER_ID
    assert qualification.selection_authority is False
    assert qualification.execution_authority is False
    assert RuntimeBackendQualification.from_dict(
        qualification.to_dict()
    ) == qualification


def test_unknown_adapter_is_rejected() -> None:
    capsule = _capsule()
    attestation = _attestation(capsule)
    sandbox = _sandbox(capsule, attestation)
    runner = FakeBackend(
        sandbox,
        capsule,
        identity=_identity(adapter_id="phios.unknown"),
    )

    with pytest.raises(ValueError, match="unrecognized runtime backend"):
        qualify_runtime_backend(sandbox, capsule, attestation, runner)


def test_runner_binding_mismatch_is_rejected() -> None:
    capsule = _capsule()
    attestation = _attestation(capsule)
    sandbox = _sandbox(capsule, attestation)
    runner = FakeBackend(sandbox, capsule)
    runner.sandbox_plan_sha256 = "0" * 64

    with pytest.raises(ValueError, match="sandbox plan"):
        qualify_runtime_backend(sandbox, capsule, attestation, runner)


def test_zero_one_and_multiple_candidate_proposals_are_distinct() -> None:
    capsule, attestation, sandbox, qualification = _qualified()

    empty = propose_runtime_backend_selection(
        sandbox,
        capsule,
        attestation,
        (),
    )
    assert empty.status == "no_qualified_backend"
    assert empty.advisory_only is True
    assert empty.execution_authority is False

    single = propose_runtime_backend_selection(
        sandbox,
        capsule,
        attestation,
        (qualification,),
    )
    assert single.status == "candidate_available"
    assert single.candidate_qualification_sha256s == (qualification.sha256(),)
    assert RuntimeBackendSelectionProposal.from_dict(single.to_dict()) == single

    second = replace(
        qualification,
        runtime_identity=_identity(backend_version="podman version 6.1.4"),
    )
    multiple = propose_runtime_backend_selection(
        sandbox,
        capsule,
        attestation,
        (qualification, second),
    )
    assert multiple.status == "operator_choice_required"
    assert len(multiple.candidate_qualification_sha256s) == 2


def test_operator_selection_binds_exact_qualification_without_execution_authority() -> None:
    capsule, attestation, sandbox, qualification = _qualified()
    proposal = propose_runtime_backend_selection(
        sandbox,
        capsule,
        attestation,
        (qualification,),
    )

    receipt = select_runtime_backend(
        proposal,
        qualification,
        selection_id="66666666-6666-6666-6666-666666666666",
        approved_qualification_sha256=qualification.sha256(),
    )

    assert receipt.status == "selected_for_request"
    assert receipt.operator_confirmed is True
    assert receipt.execution_authority is False
    assert receipt.network_authority is False
    assert receipt.install_authority is False
    assert receipt.host_write_authority is False
    assert RuntimeBackendSelectionReceipt.from_dict(receipt.to_dict()) == receipt


def test_stale_qualification_approval_is_rejected() -> None:
    capsule, attestation, sandbox, qualification = _qualified()
    proposal = propose_runtime_backend_selection(
        sandbox,
        capsule,
        attestation,
        (qualification,),
    )

    with pytest.raises(ValueError, match="approved qualification"):
        select_runtime_backend(
            proposal,
            qualification,
            selection_id="77777777-7777-7777-7777-777777777777",
            approved_qualification_sha256="0" * 64,
        )


def test_selection_receipt_rejects_authority_smuggling() -> None:
    capsule, attestation, sandbox, qualification = _qualified()
    proposal = propose_runtime_backend_selection(
        sandbox,
        capsule,
        attestation,
        (qualification,),
    )
    receipt = select_runtime_backend(
        proposal,
        qualification,
        selection_id="88888888-8888-8888-8888-888888888888",
        approved_qualification_sha256=qualification.sha256(),
    )
    data = receipt.to_dict()
    data["execution_authority"] = True

    with pytest.raises(ValueError, match="must remain false"):
        RuntimeBackendSelectionReceipt.from_dict(data)
