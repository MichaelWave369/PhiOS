from __future__ import annotations

import hashlib
import json
from pathlib import Path

from phios.action_lease import ActionLease
from phios.authority_epoch import AuthorityEpoch
from phios.core.field_aware_routing import FieldAwareRouteReceipt
from phios.core.governed_action_binding import (
    ActionBindingGrant,
    GovernedActionBinder,
)
from phios.core.governed_plan_adoption import GovernedPlanAdoptionGate
from phios.core.leased_execution_handoff import (
    GovernedLeasedExecutionHandoff,
    LeaseVerificationEvidence,
)
from phios.effect_intent import EffectIntent
from phios.enforcement_profile import EnforcementProfile, EnforcementRule
from phios.mandala import AuthoritativeAuthorityEvent, AuthorityEventKind
from phios.spine.executor import ArtifactResult
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
        plan_id="leased-plan",
        route_receipt=_route_receipt(),
    )


def _binding(plan, capability: Capability, payload: dict[str, object]):
    binder = GovernedActionBinder()
    payload_sha = binder.payload_sha256(payload)
    grant = ActionBindingGrant(
        grant_id="bind-leased-001",
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
                effective_at="2026-09-24T02:00:00+00:00",
                expires_at="2026-09-24T02:20:00+00:00",
            ),
        ),
        observed_at="2026-09-24T02:03:00+00:00",
    )


def _intent(binding) -> EffectIntent:
    return EffectIntent.build(
        capability_id=binding.capability_id,
        capability_version=binding.capability_version,
        payload_sha256=binding.payload_sha256,
        declared_at="2026-09-24T02:04:00+00:00",
        effects_declared=binding.effects_declared,
    )


def _lease(binding) -> ActionLease:
    intent = _intent(binding)
    rule = EnforcementRule.build(
        rule_id="artifact-write-boundary",
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
        issued_at="2026-09-24T02:04:00+00:00",
        valid_from="2026-09-24T02:04:00+00:00",
        valid_until="2026-09-24T02:10:00+00:00",
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


def test_valid_lease_executes_once_and_persists_lease_provenance(
    tmp_path: Path,
) -> None:
    plan = _plan()
    payload = {"name": "leased", "text": "one bounded execution"}
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    binding = _binding(
        plan,
        spine.registry.get("commons.text_artifact"),
        payload,
    )
    lease = _lease(binding)
    verification = _verification(lease)
    handoff = GovernedLeasedExecutionHandoff()

    first = handoff.execute(
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
        lease=lease,
        verification=verification,
        current_authority_epoch_sha256=lease.authority_epoch_sha256,
        checked_at="2026-09-24T02:05:00+00:00",
    )
    replay = handoff.execute(
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
        lease=lease,
        verification=verification,
        current_authority_epoch_sha256=lease.authority_epoch_sha256,
        checked_at="2026-09-24T02:05:30+00:00",
    )

    assert first.status == "SUCCEEDED"
    assert first.lease_claimed is True
    assert first.lease_consumed is True
    assert first.action_authority is False
    assert first.execution_authority is False
    assert first.effect_performed is False

    assert replay.status == "HELD"
    assert replay.reason == "lease_consumed"
    assert replay.replay_blocked is True

    entry = spine.ledger.recent(1)[0]
    provenance = entry["governed_provenance"]
    assert isinstance(provenance, dict)
    assert provenance["action_lease_sha256"] == lease.action_lease_sha256
    assert provenance["authority_epoch_sha256"] == (
        lease.authority_epoch_sha256
    )
    assert provenance["authorization_receipt_sha256"] == AUTHORIZATION
    assert provenance["lease_verification_sha256"] == (
        verification.verification_evidence_sha256
    )


def test_permission_denial_releases_lease_for_safe_retry(tmp_path: Path) -> None:
    plan = _plan()
    payload = {"name": "retry", "text": "permission later"}
    denied_spine = PhiOSSpine(state_root=tmp_path)
    capability = denied_spine.registry.get("commons.text_artifact")
    binding = _binding(plan, capability, payload)
    lease = _lease(binding)
    verification = _verification(lease)
    handoff = GovernedLeasedExecutionHandoff()

    denied = handoff.execute(
        plan=plan,
        binding=binding,
        payload=payload,
        spine=denied_spine,
        lease=lease,
        verification=verification,
        current_authority_epoch_sha256=lease.authority_epoch_sha256,
        checked_at="2026-09-24T02:05:00+00:00",
    )

    assert denied.status == "DENIED"
    assert denied.lease_consumed is False
    assert denied_spine.ledger.has_consumed_action_lease(
        lease.action_lease_sha256
    ) is False

    allowed_spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    succeeded = handoff.execute(
        plan=plan,
        binding=binding,
        payload=payload,
        spine=allowed_spine,
        lease=lease,
        verification=verification,
        current_authority_epoch_sha256=lease.authority_epoch_sha256,
        checked_at="2026-09-24T02:06:00+00:00",
    )

    assert succeeded.status == "SUCCEEDED"
    assert succeeded.lease_consumed is True


def test_failed_executor_consumes_lease_to_block_blind_retry(
    tmp_path: Path,
) -> None:
    plan = _plan()
    payload = {"value": "danger"}
    capability = Capability(
        id="custom.leased-failure",
        name="Leased failure",
        description="always fails",
        permissions=("artifact.write",),
        effects=("filesystem.change",),
        risk="medium",
        version="1.0.0",
    )
    binding = _binding(plan, capability, payload)
    lease = _lease(binding)
    verification = _verification(lease)
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    spine.registry.register(capability)

    def fail_handler(data: dict[str, object]) -> ArtifactResult:
        raise RuntimeError(f"simulated failure: {data}")

    spine.executors.register(
        capability.id,
        fail_handler,
        effects=("filesystem.change",),
    )
    handoff = GovernedLeasedExecutionHandoff()

    failed = handoff.execute(
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
        lease=lease,
        verification=verification,
        current_authority_epoch_sha256=lease.authority_epoch_sha256,
        checked_at="2026-09-24T02:05:00+00:00",
    )
    replay = handoff.execute(
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
        lease=lease,
        verification=verification,
        current_authority_epoch_sha256=lease.authority_epoch_sha256,
        checked_at="2026-09-24T02:06:00+00:00",
    )

    assert failed.status == "FAILED"
    assert failed.lease_consumed is True
    assert replay.status == "HELD"
    assert replay.reason == "lease_consumed"


def test_changed_authority_epoch_holds_before_claim(tmp_path: Path) -> None:
    plan = _plan()
    payload = {"name": "stale", "text": "do not execute"}
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    binding = _binding(
        plan,
        spine.registry.get("commons.text_artifact"),
        payload,
    )
    lease = _lease(binding)

    receipt = GovernedLeasedExecutionHandoff().execute(
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
        lease=lease,
        verification=_verification(lease),
        current_authority_epoch_sha256="f" * 64,
        checked_at="2026-09-24T02:05:00+00:00",
    )

    assert receipt.status == "HELD"
    assert receipt.reason == "authority_epoch_changed"
    assert receipt.lease_claimed is False
    assert spine.ledger.recent(10) == []


def test_unverified_issuer_decision_holds_before_claim(tmp_path: Path) -> None:
    plan = _plan()
    payload = {"name": "verify", "text": "not trusted yet"}
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    binding = _binding(
        plan,
        spine.registry.get("commons.text_artifact"),
        payload,
    )
    lease = _lease(binding)
    verification = LeaseVerificationEvidence(
        lease_sha256=lease.action_lease_sha256,
        issuer_id=lease.issuer_id,
        authorization_receipt_sha256=lease.authorization_receipt_sha256,
        verifier_id="test-authority-verifier",
        verification_receipt_sha256=VERIFICATION_RECEIPT,
        accepted=False,
    )

    receipt = GovernedLeasedExecutionHandoff().execute(
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
        lease=lease,
        verification=verification,
        current_authority_epoch_sha256=lease.authority_epoch_sha256,
        checked_at="2026-09-24T02:05:00+00:00",
    )

    assert receipt.status == "HELD"
    assert receipt.reason == "lease_authorization_not_verified"
    assert receipt.lease_claimed is False
    assert spine.ledger.recent(10) == []


def test_lease_scope_mismatch_holds_before_runtime_execution(
    tmp_path: Path,
) -> None:
    plan = _plan()
    payload = {"name": "scope", "text": "bound"}
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    capability = spine.registry.get("commons.text_artifact")
    binding = _binding(plan, capability, payload)
    lease = _lease(binding)

    other_payload = {"name": "scope", "text": "different"}
    other_binding = _binding(plan, capability, other_payload)

    receipt = GovernedLeasedExecutionHandoff().execute(
        plan=plan,
        binding=other_binding,
        payload=other_payload,
        spine=spine,
        lease=lease,
        verification=_verification(lease),
        current_authority_epoch_sha256=lease.authority_epoch_sha256,
        checked_at="2026-09-24T02:05:00+00:00",
    )

    assert receipt.status == "HELD"
    assert receipt.reason == "lease_payload_scope_mismatch"
    assert receipt.lease_claimed is False
    assert spine.ledger.recent(10) == []


def test_existing_atomic_lease_claim_blocks_parallel_attempt(
    tmp_path: Path,
) -> None:
    plan = _plan()
    payload = {"name": "parallel", "text": "one claimant"}
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["artifact.write"],
    )
    binding = _binding(
        plan,
        spine.registry.get("commons.text_artifact"),
        payload,
    )
    lease = _lease(binding)
    assert spine.ledger.claim_action_lease(
        lease.action_lease_sha256
    ) is True

    receipt = GovernedLeasedExecutionHandoff().execute(
        plan=plan,
        binding=binding,
        payload=payload,
        spine=spine,
        lease=lease,
        verification=_verification(lease),
        current_authority_epoch_sha256=lease.authority_epoch_sha256,
        checked_at="2026-09-24T02:05:00+00:00",
    )

    assert receipt.status == "HELD"
    assert receipt.reason == "lease_execution_claim_unavailable"
    assert receipt.replay_blocked is True
    assert spine.ledger.recent(10) == []
