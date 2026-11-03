"""v0.66 ThinkTank receipt-producer orchestration tests.

These tests mock producer output and NEVER execute a real npm build.
PhiOS's real v0.32 Bubblewrap receipt production has separate integration tests.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts import thinktank_governed_offline_producer as gate

PIN = gate.SOURCE_SHA
PLAN_DIGEST = "b" * 64


class FakeService:
    def __init__(self, *, status: str = "success", network: bool = True):
        self.calls = 0
        self.status = status
        self.network = network

    def execute(self, request, *, execution_root, receipt_root):
        self.calls += 1
        self.last_request = request
        self.last_execution_root = execution_root
        self.last_receipt_root = receipt_root
        execution = SimpleNamespace(
            status=self.status, network_sandbox_enforced=self.network,
            to_dict=lambda: {"marker": "actual-service-output-placeholder"},
            sha256=lambda: "1" * 64,
        )
        sandbox_receipt = SimpleNamespace(
            controls=SimpleNamespace(
                network_namespace_enforced=self.network,
                host_network_inherited=not self.network,
            ),
            sha256=lambda: "2" * 64,
        )
        offline_receipt = SimpleNamespace(
            build_status=self.status, network_mode="deny",
            network_namespace_enforced=self.network,
            to_dict=lambda: {"marker": "actual-offline-output-placeholder"},
            sha256=lambda: "3" * 64,
        )
        return SimpleNamespace(
            sandboxed_build=SimpleNamespace(
                execution=execution, sandbox=sandbox_receipt,
                sandbox_receipt_persisted=True,
                control_plane_receipt_persisted=True,
            ),
            offline_receipt=offline_receipt,
            offline_receipt_persisted=True,
        )


def _mock_inputs():
    handoff = {
        "candidate_manifest_sha256": "c" * 64,
        "package_artifact_count": 1,
        "package_artifact_set_sha256": "d" * 64,
    }
    plan = SimpleNamespace(
        derived_build_plan=SimpleNamespace(
            app_id=gate.APP_ID,
            repository_url="https://github.com/MichaelWave369/think-tank",
            commit_sha=PIN, manifest_sha256="c" * 64,
            status="ready_for_review", package_manager="npm",
            working_directory=".",
            requested_build_permissions=("build.process.execute", "build.workspace.write"),
            steps=(
                SimpleNamespace(phase="dependencies", tool="npm",
                                argv=("npm", "ci", "--offline", "--cache",
                                      "/phios/npm-cache"), requires_network=False),
                SimpleNamespace(phase="build", tool="npm",
                                argv=("npm", "run", "build"), requires_network=False),
            ),
            expected_outputs=("dist/",),
        ),
        cache_mount_target="/phios/npm-cache",
        sha256=lambda: PLAN_DIGEST,
    )
    request = SimpleNamespace(
        release_build_review_sha256=None,
        npm_cache=SimpleNamespace(sha256=lambda: "e" * 64),
    )
    candidate = {
        "source_sha": PIN,
        "manifest": {
            "source": {"repository_url": "https://github.com/MichaelWave369/think-tank"}
        },
    }
    return handoff, plan, request, candidate


def _patched_contracts(handoff, plan, request, candidate):
    from contextlib import ExitStack
    stack = ExitStack()
    stack.enter_context(patch.object(gate, "reviewed_candidate", return_value=candidate))
    stack.enter_context(patch.object(gate, "artifacts_from_handoff",
                                     return_value=(object(),)))
    stack.enter_context(patch.object(gate.NpmOfflineBuildPlan, "from_dict",
                                     return_value=plan))
    stack.enter_context(patch.object(gate.NpmOfflineBuildRequest, "from_payloads",
                                     return_value=request))
    return stack


def test_preflight_only_never_starts_service():
    h, p, request, candidate = _mock_inputs()
    with _patched_contracts(h, p, request, candidate):
        _, report = gate.preflight(h, {}, {}, {})
    assert report["status"] == "OFFLINE_BUILD_PLAN_REVIEW_ONLY"
    assert report["offline_plan_sha256"] == PLAN_DIGEST
    assert report["build_executed"] is False
    assert report["app_installed"] is False
    assert report["release_authorized"] is False


def test_wrong_plan_digest_denied_before_any_build(tmp_path: Path):
    h, p, request, candidate = _mock_inputs()
    service = FakeService()
    with _patched_contracts(h, p, request, candidate):
        with pytest.raises(ValueError, match="EXACT_OFFLINE_PLAN_APPROVAL_REQUIRED"):
            gate.execute(h, {}, {}, {}, approved_offline_plan_sha="0" * 64,
                         approved_source_sha=PIN,
                         private_execution_root=tmp_path / "build",
                         private_receipt_root=tmp_path / "receipts", service=service)
    assert service.calls == 0


def test_wrong_source_pin_denied_before_any_build(tmp_path: Path):
    h, p, request, candidate = _mock_inputs()
    service = FakeService()
    with _patched_contracts(h, p, request, candidate):
        with pytest.raises(ValueError, match="EXACT_SOURCE_APPROVAL_REQUIRED"):
            gate.execute(h, {}, {}, {}, approved_offline_plan_sha=PLAN_DIGEST,
                         approved_source_sha="0" * 40,
                         private_execution_root=tmp_path / "build",
                         private_receipt_root=tmp_path / "receipts", service=service)
    assert service.calls == 0


def test_network_permission_or_extra_step_refused():
    h, p, request, candidate = _mock_inputs()
    p.derived_build_plan.requested_build_permissions += ("build.network.dependencies",)
    with _patched_contracts(h, p, request, candidate):
        with pytest.raises(ValueError, match="PINNED_PLAN_OR_BUILD_STEPS_DRIFT"):
            gate.preflight(h, {}, {}, {})
    p.derived_build_plan.requested_build_permissions = (
        "build.process.execute", "build.workspace.write"
    )
    p.derived_build_plan.steps += (
        SimpleNamespace(phase="package", tool="npm",
                        argv=("npm", "publish"), requires_network=True),
    )
    with _patched_contracts(h, p, request, candidate):
        with pytest.raises(ValueError, match="PINNED_PLAN_OR_BUILD_STEPS_DRIFT"):
            gate.preflight(h, {}, {}, {})


def test_candidate_drift_refused():
    h, p, request, candidate = _mock_inputs()
    candidate["source_sha"] = "0" * 40
    with _patched_contracts(h, p, request, candidate):
        with pytest.raises(ValueError, match="PINNED_PLAN_OR_BUILD_STEPS_DRIFT"):
            gate.preflight(h, {}, {}, {})


def test_release_review_receipt_denied():
    h, p, request, candidate = _mock_inputs()
    request.release_build_review_sha256 = "8" * 64
    with _patched_contracts(h, p, request, candidate):
        with pytest.raises(ValueError, match="RELEASE_BUILD_LINEAGE_FORBIDDEN"):
            gate.preflight(h, {}, {}, {})


def test_exactly_approved_test_scope_invokes_existing_service_once(tmp_path: Path):
    h, p, request, candidate = _mock_inputs()
    service = FakeService()
    with _patched_contracts(h, p, request, candidate), patch.object(
        gate, "review_package_plan",
        return_value={"package_plan": {"package_plan_sha256": "4" * 64}},
    ) as downstream:
        report = gate.execute(
            h, {}, {}, {},
            approved_offline_plan_sha=PLAN_DIGEST, approved_source_sha=PIN,
            private_execution_root=tmp_path / "build",
            private_receipt_root=tmp_path / "receipts", service=service,
        )
    assert service.calls == 1
    assert service.last_request is request
    assert service.last_execution_root == tmp_path / "build"
    assert downstream.call_count == 1
    assert report["status"] == "REAL_PHIOS_OFFLINE_BUILD_RECEIPTS_MATCH_HANDOFF_REVIEW_ONLY"
    assert report["build_executed"] is True
    assert report["execution_receipt_sha256"] == "1" * 64
    assert report["offline_receipt_sha256"] == "3" * 64
    assert report["canonical_package_plan_sha256"] == "4" * 64
    assert report["app_installed"] is False
    assert report["release_authorized"] is False
    assert report["receipt_producer_independently_attested"] is False


def test_failed_or_unisolated_build_cannot_reach_package_plan(tmp_path: Path):
    h, p, request, candidate = _mock_inputs()
    for status, network in (("failed", True), ("success", False)):
        with _patched_contracts(h, p, request, candidate), patch.object(
            gate, "review_package_plan"
        ) as downstream:
            service = FakeService(status=status, network=network)
            with pytest.raises(ValueError, match="SANDBOX_OR_RECEIPT_PRODUCTION_NOT_QUALIFIED"):
                gate.execute(
                    h, {}, {}, {},
                    approved_offline_plan_sha=PLAN_DIGEST, approved_source_sha=PIN,
                    private_execution_root=tmp_path / "build",
                    private_receipt_root=tmp_path / "receipts", service=service,
                )
            downstream.assert_not_called()


def test_mismatched_actual_bytes_block_downstream_review(tmp_path: Path):
    h, p, request, candidate = _mock_inputs()
    with _patched_contracts(h, p, request, candidate), patch.object(
        gate, "review_package_plan", side_effect=ValueError("WORKSPACE_BYTES_DRIFT"),
    ):
        with pytest.raises(ValueError, match="WORKSPACE_BYTES_DRIFT"):
            gate.execute(h, {}, {}, {},
                         approved_offline_plan_sha=PLAN_DIGEST, approved_source_sha=PIN,
                         private_execution_root=tmp_path / "build",
                         private_receipt_root=tmp_path / "receipts", service=FakeService())


def test_untrusted_or_nonabsolute_root_blocked(tmp_path: Path):
    h, p, request, candidate = _mock_inputs()
    alias = tmp_path / "alias"
    actual = tmp_path / "build"
    actual.mkdir()
    alias.symlink_to(actual)
    for root in (Path("relative"), alias, tmp_path):
        service = FakeService()
        with _patched_contracts(h, p, request, candidate):
            with pytest.raises(ValueError, match="PRIVATE_ROOTS_MUST_BE_SEPARATE"):
                gate.execute(
                    h, {}, {}, {},
                    approved_offline_plan_sha=PLAN_DIGEST, approved_source_sha=PIN,
                    private_execution_root=root,
                    private_receipt_root=tmp_path / "receipts", service=service,
                )
        assert service.calls == 0


def test_malformed_real_offline_plan_is_refused_before_execution():
    with pytest.raises((ValueError, KeyError, TypeError)):
        gate.NpmOfflineBuildPlan.from_dict({
            "schema_version": "phios.thinktank_web_hosted_pilot.v0.2",
            "hosted_locked_npm_ci": True,
        })
