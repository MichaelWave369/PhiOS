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
from phios.curiosity_persistence import (
    CURIOSITY_PERSIST_PERMISSION,
    CuriosityPersistenceError,
    GovernedCuriosityPersistence,
)
from phios.effect_intent import EffectIntent
from phios.enforcement_profile import EnforcementProfile, EnforcementRule
from phios.mandala import AuthoritativeAuthorityEvent, AuthorityEventKind


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
        plan_id="curiosity-persist-plan",
        route_receipt=_route_receipt(),
    )


def _payload() -> dict[str, object]:
    return {
        "schema_version": "phios.curiosity_persist_payload.v0.4",
        "artifact_kind": "creative_seed",
        "title": "Nested bubble gear",
        "content": (
            "Explore the symbol freely without treating it as verified physics."
        ),
        "created_at": "2026-09-25T20:40:00+00:00",
        "created_by": "operator:mikey",
        "tags": ["bubble", "gear", "recursion"],
        "evidence_ref_sha256s": [],
        "parent_artifact_sha256s": [],
    }


def _binding(service: GovernedCuriosityPersistence, payload: dict[str, object]):
    plan = _plan()
    binder = GovernedActionBinder()
    grant = ActionBindingGrant(
        grant_id="bind-curiosity-001",
        authority_source="operator",
        plan_id=plan.plan_id,
        plan_state_sha256=plan.state_sha256,
        transition_index=0,
        source_state_id="A",
        target_state_id="B",
        capability_id=service.capability.id,
        payload_sha256=binder.payload_sha256(payload),
    )
    binding, receipt = binder.bind(
        plan=plan,
        transition_index=0,
        capability=service.capability,
        payload=payload,
        grant=grant,
    )
    assert receipt.status == "BOUND"
    assert binding is not None
    return plan, binding


def _authority_epoch() -> AuthorityEpoch:
    return AuthorityEpoch.build(
        principal_id="operator:mikey",
        policy_sha256=POLICY,
        ceiling=(CURIOSITY_PERSIST_PERMISSION,),
        events=(
            AuthoritativeAuthorityEvent(
                event_id="grant-curiosity-write",
                sequence=1,
                kind=AuthorityEventKind.GRANT,
                permission=CURIOSITY_PERSIST_PERMISSION,
                authority_source="operator-ledger",
                effective_at="2026-09-25T20:35:00+00:00",
                expires_at="2026-09-25T21:00:00+00:00",
            ),
        ),
        observed_at="2026-09-25T20:36:00+00:00",
    )


def _lease(binding) -> ActionLease:
    intent = EffectIntent.build(
        capability_id=binding.capability_id,
        capability_version=binding.capability_version,
        payload_sha256=binding.payload_sha256,
        declared_at="2026-09-25T20:37:00+00:00",
        effects_declared=binding.effects_declared,
    )
    rule = EnforcementRule.build(
        rule_id="curiosity-store-boundary",
        effect_scope=("filesystem.change",),
        constraint="writes remain inside the configured Curiosity Store",
        layer="linux_permissions",
        boundary="kernel_boundary",
        status="enforced",
        mechanism="bounded CuriosityStore append-only root",
        evidence_ref_sha256s=(ENFORCEMENT_EVIDENCE,),
    )
    enforcement = EnforcementProfile.build(
        intent=intent,
        rules=(rule,),
    )
    return ActionLease.issue(
        principal_id="operator:mikey",
        issuer_id="authority-broker:test",
        authorization_receipt_sha256=AUTHORIZATION,
        intent=intent,
        enforcement=enforcement,
        authority_epoch=_authority_epoch(),
        permissions_authorized=binding.permissions_requested,
        accepted_unenforced_effects=(),
        issued_at="2026-09-25T20:37:00+00:00",
        valid_from="2026-09-25T20:37:00+00:00",
        valid_until="2026-09-25T20:50:00+00:00",
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


def test_valid_lease_persists_zero_authority_curiosity_once(
    tmp_path: Path,
) -> None:
    service = GovernedCuriosityPersistence(
        state_root=tmp_path,
        allowed_permissions=(CURIOSITY_PERSIST_PERMISSION,),
    )
    payload = _payload()
    plan, binding = _binding(service, payload)
    lease = _lease(binding)
    verification = _verification(lease)

    first = service.execute(
        plan=plan,
        binding=binding,
        payload=payload,
        lease=lease,
        verification=verification,
        current_authority_epoch_sha256=lease.authority_epoch_sha256,
        checked_at="2026-09-25T20:40:30+00:00",
    )
    replay = service.execute(
        plan=plan,
        binding=binding,
        payload=payload,
        lease=lease,
        verification=verification,
        current_authority_epoch_sha256=lease.authority_epoch_sha256,
        checked_at="2026-09-25T20:41:00+00:00",
    )

    assert first.status == "SUCCEEDED"
    assert first.lease_consumed is True
    assert first.action_authority is False
    assert first.execution_authority is False
    assert first.effect_performed is False

    stored = service.store.artifacts()
    assert len(stored) == 1
    assert stored[0].title == "Nested bubble gear"
    assert stored[0].operational_authority is False
    assert stored[0].action_authority is False
    assert stored[0].execution_authority is False

    assert replay.status == "HELD"
    assert replay.reason == "lease_consumed"
    assert replay.replay_blocked is True


def test_permission_denial_does_not_persist_or_consume_lease(
    tmp_path: Path,
) -> None:
    service = GovernedCuriosityPersistence(
        state_root=tmp_path,
        allowed_permissions=(),
    )
    payload = _payload()
    plan, binding = _binding(service, payload)
    lease = _lease(binding)

    receipt = service.execute(
        plan=plan,
        binding=binding,
        payload=payload,
        lease=lease,
        verification=_verification(lease),
        current_authority_epoch_sha256=lease.authority_epoch_sha256,
        checked_at="2026-09-25T20:40:30+00:00",
    )

    assert receipt.status == "DENIED"
    assert receipt.lease_consumed is False
    assert service.store.artifacts() == []


def test_created_by_cannot_launder_lease_principal(
    tmp_path: Path,
) -> None:
    service = GovernedCuriosityPersistence(
        state_root=tmp_path,
        allowed_permissions=(CURIOSITY_PERSIST_PERMISSION,),
    )
    payload = _payload()
    plan, binding = _binding(service, payload)
    lease = _lease(binding)
    forged = dict(payload)
    forged["created_by"] = "operator:someone-else"

    with pytest.raises(
        CuriosityPersistenceError,
        match="must match ActionLease principal_id",
    ):
        service.execute(
            plan=plan,
            binding=binding,
            payload=forged,
            lease=lease,
            verification=_verification(lease),
            current_authority_epoch_sha256=lease.authority_epoch_sha256,
            checked_at="2026-09-25T20:40:30+00:00",
        )

    assert service.store.artifacts() == []


def test_noncanonical_payload_is_rejected_before_execution(
    tmp_path: Path,
) -> None:
    service = GovernedCuriosityPersistence(
        state_root=tmp_path,
        allowed_permissions=(CURIOSITY_PERSIST_PERMISSION,),
    )
    payload = _payload()
    payload["tags"] = ["gear", "bubble"]

    plan, binding = _binding(service, payload)
    lease = _lease(binding)

    with pytest.raises(
        CuriosityPersistenceError,
        match="tags must already be sorted",
    ):
        service.execute(
            plan=plan,
            binding=binding,
            payload=payload,
            lease=lease,
            verification=_verification(lease),
            current_authority_epoch_sha256=lease.authority_epoch_sha256,
            checked_at="2026-09-25T20:40:30+00:00",
        )
