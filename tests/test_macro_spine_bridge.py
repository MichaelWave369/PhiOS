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
from phios.macro_runtime import (
    ExecutionMode,
    IdempotencyClass,
    Operation,
    ReplayClass,
    RollbackClass,
    SideEffectClass,
)
from phios.macro_spine_bridge import (
    MacroSpineBinding,
    MacroSpineBridge,
    MacroSpineBridgeContractError,
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


def _plan():
    return GovernedPlanAdoptionGate().initialize_plan(
        plan_id="macro-spine-plan",
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
        grant_id="bind-macro-spine-001",
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
                effective_at="2026-09-26T20:00:00+00:00",
                expires_at="2026-09-26T22:30:00+00:00",
            ),
        ),
        observed_at="2026-09-26T20:03:00+00:00",
    )


def _lease(binding) -> ActionLease:
    intent = EffectIntent.build(
        capability_id=binding.capability_id,
        capability_version=binding.capability_version,
        payload_sha256=binding.payload_sha256,
        declared_at="2026-09-26T20:04:00+00:00",
        effects_declared=binding.effects_declared,
    )
    rule = EnforcementRule.build(
        rule_id="macro-artifact-write-boundary",
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
        issued_at="2026-09-26T20:04:00+00:00",
        valid_from="2026-09-26T20:04:00+00:00",
        valid_until="2026-09-26T22:00:00+00:00",
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
        operation_id="macro.step.text_artifact",
        operation_version="0.2.0",
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


def test_live_macro_uses_existing_lease_and_persists_macro_receipt(
    tmp_path: Path,
) -> None:
    plan = _plan()
    payload = {"name": "macro-v02", "text": "governed macro execution"}
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    capability = spine.registry.get("commons.text_artifact")
    binding = _binding(plan, capability, payload)
    lease = _lease(binding)
    operation = _operation(capability, payload)
    macro_binding = MacroSpineBinding.build(
        macro_id="macro:test",
        macro_version="0.2.0",
        operation=operation,
        plan=plan,
        binding=binding,
        lease=lease,
    )
    bridge = MacroSpineBridge()

    first = bridge.execute(
        operation=operation,
        macro_binding=macro_binding,
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
        lease=lease,
        verification=_verification(lease),
        current_authority_epoch_sha256=lease.authority_epoch_sha256,
        checked_at="2026-09-26T20:05:00+00:00",
    )
    replay = bridge.execute(
        operation=operation,
        macro_binding=macro_binding,
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
        lease=lease,
        verification=_verification(lease),
        current_authority_epoch_sha256=lease.authority_epoch_sha256,
        checked_at="2026-09-26T20:06:00+00:00",
    )

    assert first.status == "SUCCEEDED"
    assert first.lease_consumed is True
    assert first.spine_execution_status == "succeeded"
    assert first.spine_receipt_id is not None
    assert first.action_authority is False
    assert first.execution_authority is False
    assert first.effect_performed is False
    assert len(first.receipt_sha256) == 64

    assert replay.status == "HELD"
    assert replay.reason == "lease_consumed"
    assert replay.replay_blocked is True
    assert replay.spine_receipt_id is None

    macro_rows = spine.ledger.recent_macro_receipts(2)
    assert [row["status"] for row in macro_rows] == ["SUCCEEDED", "HELD"]
    assert macro_rows[0]["operation_hash"] == operation.operation_hash
    assert macro_rows[0]["action_binding_sha256"] == binding.binding_sha256
    assert macro_rows[0]["action_lease_sha256"] == lease.action_lease_sha256
    assert macro_rows[0]["spine_receipt_id"] == first.spine_receipt_id

    execution_row = spine.ledger.recent(1)[0]
    provenance = execution_row["governed_provenance"]
    assert isinstance(provenance, dict)
    assert provenance["action_binding_sha256"] == binding.binding_sha256
    assert provenance["action_lease_sha256"] == lease.action_lease_sha256


def test_scope_mismatch_blocks_before_spine_execution(tmp_path: Path) -> None:
    plan = _plan()
    payload = {"name": "macro-v02", "text": "original"}
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    capability = spine.registry.get("commons.text_artifact")
    binding = _binding(plan, capability, payload)
    lease = _lease(binding)
    operation = _operation(capability, payload)
    macro_binding = MacroSpineBinding.build(
        macro_id="macro:test",
        macro_version="0.2.0",
        operation=operation,
        plan=plan,
        binding=binding,
        lease=lease,
    )
    altered = _operation(
        capability,
        {"name": "macro-v02", "text": "different"},
    )

    with pytest.raises(
        MacroSpineBridgeContractError,
        match="inputs differ",
    ):
        MacroSpineBridge().execute(
            operation=altered,
            macro_binding=macro_binding,
            plan=plan,
            binding=binding,
            payload=payload,
            spine=spine,
            lease=lease,
            verification=_verification(lease),
            current_authority_epoch_sha256=lease.authority_epoch_sha256,
            checked_at="2026-09-26T20:05:00+00:00",
        )

    assert spine.ledger.recent(1) == []
    assert spine.ledger.recent_macro_receipts(1) == []
