from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

from phios.action_lease import ActionLease
from phios.authority_epoch import AuthorityEpoch
from phios.core.field_aware_routing import FieldAwareRouteReceipt
from phios.core.governed_action_binding import (
    ActionBindingGrant,
    GovernedActionBinder,
)
from phios.core.governed_execution_handoff import GovernedExecutionHandoff
from phios.core.governed_plan_adoption import GovernedPlanAdoptionGate
from phios.effect_intent import EffectIntent
from phios.enforcement_profile import EnforcementProfile, EnforcementRule
from phios.mandala import AuthoritativeAuthorityEvent, AuthorityEventKind
from phios.spine.executor import ArtifactResult
from phios.spine.models import Capability
from phios.spine.runtime import PhiOSSpine


ISSUER = "authority-broker:test"
AUTHORIZATION_RECEIPT = "a" * 64
ENFORCEMENT_EVIDENCE = "b" * 64
POLICY = "c" * 64


def _route_receipt() -> FieldAwareRouteReceipt:
    payload = {
        "schema": "phios.field_aware_route_receipt.v0.4",
        "status": "found",
        "field_law_sha256": "d" * 64,
        "field_state_sha256": "e" * 64,
        "field_revision": 0,
        "bindings": [],
        "path_receipt_sha256": "f" * 64,
        "path_ids": ["A", "B", "D"],
        "total_cost": 2.0,
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
        field_law_sha256="d" * 64,
        field_state_sha256="e" * 64,
        field_revision=0,
        bindings=(),
        path_receipt_sha256="f" * 64,
        path_ids=("A", "B", "D"),
        total_cost=2.0,
        optimality_scope=(
            "least_declared_cost_over_observed_graph_at_exact_field_snapshot"
        ),
        action_authority=False,
        receipt_sha256=digest,
    )


def _plan():
    return GovernedPlanAdoptionGate().initialize_plan(
        plan_id="lease-plan",
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
        grant_id="bind-lease-001",
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


def _epoch(
    *,
    permission: str,
    principal_id: str = "operator:michael",
) -> AuthorityEpoch:
    return AuthorityEpoch.build(
        principal_id=principal_id,
        policy_sha256=POLICY,
        ceiling=(permission,),
        events=(
            AuthoritativeAuthorityEvent(
                event_id=f"grant-{permission}",
                sequence=1,
                kind=AuthorityEventKind.GRANT,
                permission=permission,
                authority_source="operator-ledger",
                effective_at="2026-09-24T02:00:00+00:00",
                expires_at="2026-09-24T02:30:00+00:00",
            ),
        ),
        observed_at="2026-09-24T02:03:00+00:00",
    )


def _lease(
    *,
    binding,
    permission: str,
    epoch: AuthorityEpoch,
) -> ActionLease:
    intent = EffectIntent.build(
        capability_id=binding.capability_id,
        capability_version=binding.capability_version,
        payload_sha256=binding.payload_sha256,
        declared_at="2026-09-24T02:02:00+00:00",
        effects_declared=binding.effects_declared,
    )
    rule = EnforcementRule.build(
        rule_id="runtime-boundary",
        effect_scope=binding.effects_declared,
        constraint="runtime effect is bounded by the declared enforcement seam",
        layer="linux_namespaces",
        boundary="kernel_boundary",
        status="enforced",
        mechanism="test enforcement boundary",
        evidence_ref_sha256s=(ENFORCEMENT_EVIDENCE,),
    )
    profile = EnforcementProfile.build(
        intent=intent,
        rules=(rule,),
    )
    return ActionLease.issue(
        principal_id=epoch.principal_id,
        issuer_id=ISSUER,
        authorization_receipt_sha256=AUTHORIZATION_RECEIPT,
        intent=intent,
        enforcement=profile,
        authority_epoch=epoch,
        permissions_authorized=(permission,),
        accepted_unenforced_effects=(),
        issued_at="2026-09-24T02:03:00+00:00",
        valid_from="2026-09-24T02:03:00+00:00",
        valid_until="2026-09-24T02:10:00+00:00",
    )


def _execute_with_lease(
    *,
    handoff: GovernedExecutionHandoff,
    plan,
    binding,
    payload: dict[str, object],
    spine: PhiOSSpine,
    lease: ActionLease,
    current_epoch_sha256: str | None = None,
    trusted_issuers: tuple[str, ...] = (ISSUER,),
    accepted_receipts: tuple[str, ...] = (AUTHORIZATION_RECEIPT,),
):
    return handoff.execute_with_lease(
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
        lease=lease,
        checked_at="2026-09-24T02:05:00+00:00",
        current_authority_epoch_sha256=(
            current_epoch_sha256 or lease.authority_epoch_sha256
        ),
        trusted_issuer_ids=trusted_issuers,
        accepted_authorization_receipt_sha256s=accepted_receipts,
    )


def test_successful_lease_execution_consumes_binding_and_lease(
    tmp_path: Path,
) -> None:
    plan = _plan()
    payload = {"name": "lease-proof", "text": "bounded authority"}
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    capability = spine.registry.get("commons.text_artifact")
    binding = _binding(plan, capability, payload)
    epoch = _epoch(permission="artifact.write")
    lease = _lease(
        binding=binding,
        permission="artifact.write",
        epoch=epoch,
    )
    handoff = GovernedExecutionHandoff()

    first = _execute_with_lease(
        handoff=handoff,
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
        lease=lease,
    )
    replay = _execute_with_lease(
        handoff=handoff,
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
        lease=lease,
    )

    assert first.schema == "phios.execution_handoff_receipt.v0.9"
    assert first.status == "SUCCEEDED"
    assert first.binding_consumed is True
    assert first.lease_consumed is True
    assert first.action_lease_sha256 == lease.action_lease_sha256
    assert first.lease_evaluation_reason == "lease_current"
    assert spine.ledger.has_consumed_binding(binding.binding_sha256) is True
    assert (
        spine.ledger.has_consumed_action_lease(lease.action_lease_sha256)
        is True
    )

    assert replay.status == "HELD"
    assert replay.reason == "action_lease_consumed"
    assert replay.replay_blocked is True
    assert replay.lease_consumed is False


def test_authority_epoch_change_holds_before_execution(tmp_path: Path) -> None:
    plan = _plan()
    payload = {"name": "stale", "text": "do not execute"}
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    capability = spine.registry.get("commons.text_artifact")
    binding = _binding(plan, capability, payload)
    lease = _lease(
        binding=binding,
        permission="artifact.write",
        epoch=_epoch(permission="artifact.write"),
    )

    receipt = _execute_with_lease(
        handoff=GovernedExecutionHandoff(),
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
        lease=lease,
        current_epoch_sha256="9" * 64,
    )

    assert receipt.status == "HELD"
    assert receipt.reason == "action_lease_authority_epoch_changed"
    assert receipt.binding_consumed is False
    assert receipt.lease_consumed is False
    assert spine.ledger.recent(10) == []


def test_untrusted_issuer_and_unaccepted_decision_fail_closed(
    tmp_path: Path,
) -> None:
    plan = _plan()
    payload = {"name": "trust", "text": "check issuer"}
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    binding = _binding(
        plan,
        spine.registry.get("commons.text_artifact"),
        payload,
    )
    lease = _lease(
        binding=binding,
        permission="artifact.write",
        epoch=_epoch(permission="artifact.write"),
    )
    handoff = GovernedExecutionHandoff()

    untrusted = _execute_with_lease(
        handoff=handoff,
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
        lease=lease,
        trusted_issuers=("authority-broker:other",),
    )
    unaccepted = _execute_with_lease(
        handoff=handoff,
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
        lease=lease,
        accepted_receipts=("8" * 64,),
    )

    assert untrusted.status == "HELD"
    assert untrusted.reason == "action_lease_issuer_untrusted"
    assert unaccepted.status == "HELD"
    assert unaccepted.reason == (
        "action_lease_authorization_receipt_unaccepted"
    )
    assert spine.ledger.recent(10) == []


def test_lease_scope_mismatch_holds_before_runtime_claim(tmp_path: Path) -> None:
    plan = _plan()
    payload = {"name": "scope", "text": "bound"}
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    binding = _binding(
        plan,
        spine.registry.get("commons.text_artifact"),
        payload,
    )
    lease = _lease(
        binding=binding,
        permission="artifact.write",
        epoch=_epoch(permission="artifact.write"),
    )
    drifted = replace(lease, payload_sha256="7" * 64)

    receipt = _execute_with_lease(
        handoff=GovernedExecutionHandoff(),
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
        lease=drifted,
    )

    assert receipt.status == "HELD"
    assert receipt.reason == "action_lease_payload_scope_mismatch"
    assert receipt.binding_consumed is False
    assert spine.ledger.recent(10) == []


def test_permission_denial_releases_lease_for_safe_retry(
    tmp_path: Path,
) -> None:
    plan = _plan()
    payload = {"name": "retry", "text": "permission later"}
    denied_spine = PhiOSSpine(state_root=tmp_path)
    capability = denied_spine.registry.get("commons.text_artifact")
    binding = _binding(plan, capability, payload)
    lease = _lease(
        binding=binding,
        permission="artifact.write",
        epoch=_epoch(permission="artifact.write"),
    )
    handoff = GovernedExecutionHandoff()

    denied = _execute_with_lease(
        handoff=handoff,
        plan=plan,
        binding=binding,
        payload=payload,
        spine=denied_spine,
        lease=lease,
    )

    assert denied.status == "DENIED"
    assert denied.binding_consumed is False
    assert denied.lease_consumed is False
    assert (
        denied_spine.ledger.has_consumed_action_lease(
            lease.action_lease_sha256
        )
        is False
    )

    allowed_spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    succeeded = _execute_with_lease(
        handoff=handoff,
        plan=plan,
        binding=binding,
        payload=payload,
        spine=allowed_spine,
        lease=lease,
    )

    assert succeeded.status == "SUCCEEDED"
    assert succeeded.binding_consumed is True
    assert succeeded.lease_consumed is True


def test_executor_failure_consumes_single_use_lease(
    tmp_path: Path,
) -> None:
    plan = _plan()
    payload = {"value": "danger"}
    capability = Capability(
        id="custom.lease-failure",
        name="Lease Failure",
        description="always fails after executor entry",
        permissions=("custom.execute",),
        effects=("external_state.change",),
        risk="medium",
        version="1.0.0",
    )
    binding = _binding(plan, capability, payload)
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["custom.execute"],
    )
    spine.registry.register(capability)

    def fail_handler(data: dict[str, object]) -> ArtifactResult:
        raise RuntimeError(f"simulated failure: {data['value']}")

    spine.executors.register(
        capability.id,
        fail_handler,
        effects=("external_state.change",),
    )
    lease = _lease(
        binding=binding,
        permission="custom.execute",
        epoch=_epoch(permission="custom.execute"),
    )
    handoff = GovernedExecutionHandoff()

    failed = _execute_with_lease(
        handoff=handoff,
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
        lease=lease,
    )
    replay = _execute_with_lease(
        handoff=handoff,
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
        lease=lease,
    )

    assert failed.status == "FAILED"
    assert failed.binding_consumed is True
    assert failed.lease_consumed is True
    assert replay.status == "HELD"
    assert replay.reason == "action_lease_consumed"
