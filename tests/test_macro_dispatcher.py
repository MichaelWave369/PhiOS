from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from phios.action_lease import ActionLease
from phios.authority_epoch import AuthorityEpoch
from phios.core.field_aware_routing import FieldAwareRouteReceipt
from phios.core.governed_action_binding import (
    ActionBindingGrant,
    GovernedActionBinder,
)
from phios.core.governed_plan_adoption import GovernedPlanAdoptionGate
from phios.core.leased_execution_handoff import LeaseVerificationEvidence
from phios.effect_intent import EffectIntent
from phios.enforcement_profile import EnforcementProfile, EnforcementRule
from phios.macro_dispatcher import (
    GovernedDoDispatcher,
    GovernedDoDispatcherContractError,
)
from phios.macro_graph import DoStep, MacroDefinition, MacroGraphPlanner
from phios.macro_runner import (
    MacroRunner,
    RunnerInputs,
    RunnerStatus,
)
from phios.macro_runtime import (
    ExecutionMode,
    IdempotencyClass,
    Operation,
    ReplayClass,
    RollbackClass,
    SideEffectClass,
)
from phios.mandala import AuthoritativeAuthorityEvent, AuthorityEventKind
from phios.spine.models import Capability
from phios.spine.runtime import PhiOSSpine

AUTHORIZATION = "a" * 64
VERIFICATION_RECEIPT = "b" * 64
ENFORCEMENT_EVIDENCE = "c" * 64
POLICY = "d" * 64


def _route_receipt() -> FieldAwareRouteReceipt:
    payload = {
        "schema": "phios.field_aware_route_receipt.v0.4",
        "status": "found",
        "field_law_sha256": "e" * 64,
        "field_state_sha256": "f" * 64,
        "field_revision": 0,
        "bindings": [],
        "path_receipt_sha256": "1" * 64,
        "path_ids": ["A", "B"],
        "total_cost": 1.0,
        "optimality_scope": (
            "least_declared_cost_over_observed_graph_at_exact_field_snapshot"
        ),
        "action_authority": False,
    }
    digest = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return FieldAwareRouteReceipt(
        schema="phios.field_aware_route_receipt.v0.4",
        status="found",
        field_law_sha256="e" * 64,
        field_state_sha256="f" * 64,
        field_revision=0,
        bindings=(),
        path_receipt_sha256="1" * 64,
        path_ids=("A", "B"),
        total_cost=1.0,
        optimality_scope=(
            "least_declared_cost_over_observed_graph_at_exact_field_snapshot"
        ),
        action_authority=False,
        receipt_sha256=digest,
    )


def _plan_state():
    return GovernedPlanAdoptionGate().initialize_plan(
        plan_id="macro-dispatch-plan",
        route_receipt=_route_receipt(),
    )


def _binding(
    plan,
    capability: Capability,
    payload: dict[str, object],
):
    binder = GovernedActionBinder()
    payload_sha = binder.payload_sha256(payload)
    grant = ActionBindingGrant(
        grant_id="bind-macro-dispatch-001",
        authority_source="operator",
        plan_id=plan.plan_id,
        plan_state_sha256=plan.state_sha256,
        transition_index=0,
        source_state_id="A",
        target_state_id="B",
        capability_id=capability.id,
        payload_sha256=payload_sha,
    )
    binding, receipt = binder.bind(
        plan=plan,
        transition_index=0,
        capability=capability,
        payload=payload,
        grant=grant,
    )
    assert receipt.status == "BOUND"
    assert binding is not None
    return binding


def _authority_epoch() -> AuthorityEpoch:
    return AuthorityEpoch.build(
        principal_id="operator:michael",
        policy_sha256=POLICY,
        ceiling=("artifact.write",),
        events=(
            AuthoritativeAuthorityEvent(
                event_id="grant-artifact",
                sequence=1,
                kind=AuthorityEventKind.GRANT,
                permission="artifact.write",
                authority_source="operator-ledger",
                effective_at="2026-09-26T21:00:00+00:00",
                expires_at="2026-09-26T23:30:00+00:00",
            ),
        ),
        observed_at="2026-09-26T21:03:00+00:00",
    )


def _lease(binding) -> ActionLease:
    intent = EffectIntent.build(
        capability_id=binding.capability_id,
        capability_version=binding.capability_version,
        payload_sha256=binding.payload_sha256,
        declared_at="2026-09-26T21:04:00+00:00",
        effects_declared=binding.effects_declared,
    )
    rule = EnforcementRule.build(
        rule_id="macro-dispatch-artifact-boundary",
        effect_scope=("filesystem.change",),
        constraint="artifact writes remain inside the governed workspace",
        layer="linux_permissions",
        boundary="kernel_boundary",
        status="enforced",
        mechanism="runtime workspace permission boundary",
        evidence_ref_sha256s=(ENFORCEMENT_EVIDENCE,),
    )
    enforcement = EnforcementProfile.build(
        intent=intent,
        rules=(rule,),
    )
    return ActionLease.issue(
        principal_id="operator:michael",
        issuer_id="authority-broker:test",
        authorization_receipt_sha256=AUTHORIZATION,
        intent=intent,
        enforcement=enforcement,
        authority_epoch=_authority_epoch(),
        permissions_authorized=binding.permissions_requested,
        accepted_unenforced_effects=(),
        issued_at="2026-09-26T21:04:00+00:00",
        valid_from="2026-09-26T21:04:00+00:00",
        valid_until="2026-09-26T23:00:00+00:00",
    )


def _verification(lease: ActionLease) -> LeaseVerificationEvidence:
    return LeaseVerificationEvidence(
        lease_sha256=lease.action_lease_sha256,
        issuer_id=lease.issuer_id,
        authorization_receipt_sha256=lease.authorization_receipt_sha256,
        verifier_id="test-authority-verifier",
        verification_receipt_sha256=VERIFICATION_RECEIPT,
        accepted=True,
    )


def _operation(
    capability: Capability,
    payload: dict[str, object],
) -> Operation:
    return Operation(
        operation_id="macro.step.dispatch-artifact",
        operation_version="0.5.0",
        adapter_id="phios.spine",
        action=capability.id,
        inputs=dict(payload),
        required_capabilities=capability.permissions,
        execution_modes_supported=(ExecutionMode.LIVE,),
        idempotency_class=IdempotencyClass.NON_IDEMPOTENT,
        replay_class=ReplayClass.NON_REPLAYABLE,
        rollback_class=RollbackClass.NONE,
        side_effect_class=SideEffectClass.LOCAL_IRREVERSIBLE,
    )


def _macro_plan(operation: Operation):
    return MacroGraphPlanner().plan(
        MacroDefinition(
            macro_id="macro:dispatch-test",
            macro_version="0.5.0",
            steps=(DoStep(operation),),
        )
    )


def _waiting_state(macro_plan):
    runner = MacroRunner()
    return runner.advance(macro_plan, runner.start(macro_plan))


def test_dispatch_001_work_package_is_exact_and_zero_authority(
    tmp_path: Path,
) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    capability = spine.registry.get("commons.text_artifact")
    payload = {"name": "dispatch-package", "text": "exact scope"}
    operation = _operation(capability, payload)
    macro_plan = _macro_plan(operation)
    waiting = _waiting_state(macro_plan)

    package = GovernedDoDispatcher().package(
        macro_plan=macro_plan,
        run_state=waiting,
        operation=operation,
    )

    assert waiting.status is RunnerStatus.WAITING_OPERATION
    assert package.macro_plan_sha256 == macro_plan.plan_sha256
    assert package.macro_run_state_sha256 == waiting.state_sha256
    assert package.instruction_path == "root.0"
    assert package.operation_hash == operation.operation_hash
    assert package.input_hash == operation.input_hash
    assert package.operational_authority is False
    assert package.action_authority is False
    assert package.execution_authority is False
    assert len(package.work_package_sha256) == 64


def test_dispatch_002_success_closes_runner_to_spine_to_runner_loop(
    tmp_path: Path,
) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    capability = spine.registry.get("commons.text_artifact")
    payload = {
        "name": "dispatch-success",
        "text": "runner to governed spine to runner",
    }
    operation = _operation(capability, payload)
    macro_plan = _macro_plan(operation)
    runner = MacroRunner()
    waiting = runner.advance(macro_plan, runner.start(macro_plan))
    plan = _plan_state()
    binding = _binding(plan, capability, payload)
    lease = _lease(binding)
    dispatcher = GovernedDoDispatcher()
    package = dispatcher.package(
        macro_plan=macro_plan,
        run_state=waiting,
        operation=operation,
    )

    dispatched = dispatcher.dispatch(
        work_package=package,
        macro_plan=macro_plan,
        run_state=waiting,
        operation=operation,
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
        lease=lease,
        verification=_verification(lease),
        current_authority_epoch_sha256=lease.authority_epoch_sha256,
        checked_at="2026-09-26T21:05:00+00:00",
    )

    assert dispatched.macro_spine_receipt.status == "SUCCEEDED"
    assert dispatched.operation_resolution.status.value == "SUCCEEDED"
    assert (
        dispatched.operation_resolution.receipt_sha256
        == dispatched.dispatch_receipt.receipt_sha256
    )
    assert dispatched.dispatch_receipt.work_package_sha256 == (
        package.work_package_sha256
    )
    assert dispatched.dispatch_receipt.macro_spine_receipt_sha256 == (
        dispatched.macro_spine_receipt.receipt_sha256
    )
    assert dispatched.dispatch_receipt.operational_authority is False
    assert dispatched.dispatch_receipt.action_authority is False
    assert dispatched.dispatch_receipt.execution_authority is False
    assert dispatched.dispatch_receipt.effect_performed is False

    completed = runner.advance(
        macro_plan,
        waiting,
        RunnerInputs(
            operations=(dispatched.operation_resolution,),
        ),
    )
    assert completed.status is RunnerStatus.COMPLETED

    dispatch_rows = spine.ledger.recent_macro_dispatch_receipts(1)
    assert dispatch_rows[0]["receipt_sha256"] == (
        dispatched.dispatch_receipt.receipt_sha256
    )
    assert dispatch_rows[0]["macro_spine_receipt_sha256"] == (
        dispatched.macro_spine_receipt.receipt_sha256
    )
    assert dispatch_rows[0]["resolution_status"] == "SUCCEEDED"

    macro_rows = spine.ledger.recent_macro_receipts(1)
    assert macro_rows[0]["status"] == "SUCCEEDED"
    execution_rows = spine.ledger.recent(1)
    assert execution_rows[0]["execution_status"] == "succeeded"


def test_dispatch_003_mismatched_operation_rejected_before_execution(
    tmp_path: Path,
) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    capability = spine.registry.get("commons.text_artifact")
    payload = {"name": "dispatch-scope", "text": "original"}
    operation = _operation(capability, payload)
    macro_plan = _macro_plan(operation)
    waiting = _waiting_state(macro_plan)
    dispatcher = GovernedDoDispatcher()

    altered = _operation(
        capability,
        {"name": "dispatch-scope", "text": "altered"},
    )

    with pytest.raises(
        GovernedDoDispatcherContractError,
        match="does not match planned DO",
    ):
        dispatcher.package(
            macro_plan=macro_plan,
            run_state=waiting,
            operation=altered,
        )

    assert spine.ledger.recent(1) == []
    assert spine.ledger.recent_macro_receipts(1) == []
    assert spine.ledger.recent_macro_dispatch_receipts(1) == []


def test_dispatch_004_consumed_lease_maps_to_held_resolution(
    tmp_path: Path,
) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    capability = spine.registry.get("commons.text_artifact")
    payload = {"name": "dispatch-replay", "text": "single use"}
    operation = _operation(capability, payload)
    macro_plan = _macro_plan(operation)
    waiting = _waiting_state(macro_plan)
    plan = _plan_state()
    binding = _binding(plan, capability, payload)
    lease = _lease(binding)
    dispatcher = GovernedDoDispatcher()
    package = dispatcher.package(
        macro_plan=macro_plan,
        run_state=waiting,
        operation=operation,
    )

    first = dispatcher.dispatch(
        work_package=package,
        macro_plan=macro_plan,
        run_state=waiting,
        operation=operation,
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
        lease=lease,
        verification=_verification(lease),
        current_authority_epoch_sha256=lease.authority_epoch_sha256,
        checked_at="2026-09-26T21:05:00+00:00",
    )
    second = dispatcher.dispatch(
        work_package=package,
        macro_plan=macro_plan,
        run_state=waiting,
        operation=operation,
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
        lease=lease,
        verification=_verification(lease),
        current_authority_epoch_sha256=lease.authority_epoch_sha256,
        checked_at="2026-09-26T21:06:00+00:00",
    )

    assert first.operation_resolution.status.value == "SUCCEEDED"
    assert second.macro_spine_receipt.status == "HELD"
    assert second.macro_spine_receipt.reason == "lease_consumed"
    assert second.operation_resolution.status.value == "HELD"

    held = MacroRunner().advance(
        macro_plan,
        waiting,
        RunnerInputs(
            operations=(second.operation_resolution,),
        ),
    )
    assert held.status is RunnerStatus.HELD
    assert held.reason == "operation_held"


def test_dispatch_005_non_waiting_state_cannot_be_packaged(
    tmp_path: Path,
) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    capability = spine.registry.get("commons.text_artifact")
    operation = _operation(
        capability,
        {"name": "dispatch-ready", "text": "not waiting"},
    )
    macro_plan = _macro_plan(operation)
    ready = MacroRunner().start(macro_plan)

    with pytest.raises(
        GovernedDoDispatcherContractError,
        match="WAITING_OPERATION",
    ):
        GovernedDoDispatcher().package(
            macro_plan=macro_plan,
            run_state=ready,
            operation=operation,
        )
