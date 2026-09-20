from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from phios.reflex.control_plane import (
    ReflexControlPlaneContractError,
    ReflexRuntimeControlPlane,
)
from phios.reflex.influence_adoption import ReflexInfluencePolicyState
from phios.reflex.models import ReflexDecision, ReflexInput
from phios.reflex.runtime_influence import (
    ROUTING_SURFACE,
    ReflexActivationGrant,
    ReflexActivationRequest,
)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _policy() -> ReflexInfluencePolicyState:
    payload = {
        "schema": "phios.reflex_influence_policy_state.v0.5",
        "policy_id": "phios.reflex.influence.jev",
        "revision": 0,
        "readiness_receipt_sha256": "a" * 64,
        "candidate_provider": "jev",
        "candidate_models": ["jev-test"],
        "allowed_dimensions": ["role", "system2"],
        "max_influence_weight": 0.25,
        "rollback_on_provider_unavailable": True,
        "max_consecutive_provider_errors": 2,
        "parent_policy_sha256": None,
        "routing_influence_active": False,
        "runtime_activation_authority": False,
        "promotion_authority": False,
        "action_authority": False,
        "execution_authority": False,
    }
    return ReflexInfluencePolicyState(
        schema="phios.reflex_influence_policy_state.v0.5",
        policy_id="phios.reflex.influence.jev",
        revision=0,
        readiness_receipt_sha256="a" * 64,
        candidate_provider="jev",
        candidate_models=("jev-test",),
        allowed_dimensions=("role", "system2"),
        max_influence_weight=0.25,
        rollback_on_provider_unavailable=True,
        max_consecutive_provider_errors=2,
        parent_policy_sha256=None,
        routing_influence_active=False,
        runtime_activation_authority=False,
        promotion_authority=False,
        action_authority=False,
        execution_authority=False,
        state_sha256=_digest(payload),
    )


def _request() -> ReflexActivationRequest:
    return ReflexActivationRequest(
        provider="jev",
        models=("jev-test",),
        routing_surface=ROUTING_SURFACE,
        allowed_dimensions=("role", "system2"),
        influence_weight=0.20,
    )


def _grant(policy: ReflexInfluencePolicyState, request: ReflexActivationRequest):
    return ReflexActivationGrant(
        grant_id="grant-001",
        authority_source="operator",
        policy_state_sha256=policy.state_sha256,
        current_activation_sha256=None,
        activation_request_sha256=request.request_sha256,
        disposition="ACTIVATE",
    )


def _setup(control: ReflexRuntimeControlPlane, epoch: int = 100):
    policy = _policy()
    request = _request()
    grant = _grant(policy, request)
    control.ingest_policy_payload(
        policy.to_dict(),
        evaluation_epoch=epoch,
    )
    control.ingest_grant_payload(
        grant.to_payload(),
        evaluation_epoch=epoch,
    )
    return policy, request, grant


class FixedProvider:
    def __init__(self, decision: ReflexDecision):
        self.decision = decision

    def evaluate(self, reflex_input: ReflexInput) -> ReflexDecision:
        return self.decision


def _baseline() -> ReflexDecision:
    return ReflexDecision(
        provider="rules",
        provider_version="test",
        model="rules",
        role="utility",
        role_probabilities=(
            ("utility", 0.8),
            ("builder", 0.05),
            ("synthesis", 0.05),
            ("translator", 0.05),
            ("ledger", 0.05),
        ),
        risk="low",
        risk_probabilities=(("low", 0.8), ("elevated", 0.1), ("high", 0.1)),
        needs_system2_probability=0.2,
        needs_verification_probability=0.2,
        confidence=0.8,
        latency_ms=0.0,
    )


def _candidate() -> ReflexDecision:
    return ReflexDecision(
        provider="jev",
        provider_version="test",
        model="jev-test",
        role="builder",
        role_probabilities=(
            ("utility", 0.05),
            ("builder", 0.85),
            ("synthesis", 0.04),
            ("translator", 0.03),
            ("ledger", 0.03),
        ),
        risk="high",
        risk_probabilities=(("low", 0.05), ("elevated", 0.15), ("high", 0.8)),
        needs_system2_probability=0.9,
        needs_verification_probability=0.9,
        confidence=0.85,
        latency_ms=1.0,
    )


def test_policy_grant_activation_survive_restart(tmp_path):
    control = ReflexRuntimeControlPlane(root=tmp_path)
    _, request, _ = _setup(control)

    result = control.activate(
        request=request,
        grant_id="grant-001",
        evaluation_epoch=101,
        lease_until_epoch=500,
    )
    assert result["ok"] is True
    assert result["activation"]["routing_influence_active"] is True

    restarted = ReflexRuntimeControlPlane(root=tmp_path)
    status = restarted.status(evaluation_epoch=200)
    assert status["routing_influence_active"] is True
    assert status["lease"]["valid_through_epoch"] == 500


def test_grant_ingest_is_idempotent_but_id_conflict_fails(tmp_path):
    control = ReflexRuntimeControlPlane(root=tmp_path)
    policy, request, grant = _setup(control)

    again = control.ingest_grant_payload(
        grant.to_payload(),
        evaluation_epoch=101,
    )
    assert again["idempotent"] is True

    conflicting = replace(
        grant,
        activation_request_sha256="f" * 64,
    )
    with pytest.raises(ReflexControlPlaneContractError):
        control.ingest_grant_payload(
            conflicting.to_payload(),
            evaluation_epoch=102,
        )


def test_lease_can_shorten_but_not_extend(tmp_path):
    control = ReflexRuntimeControlPlane(root=tmp_path)
    _, request, _ = _setup(control)
    control.activate(
        request=request,
        grant_id="grant-001",
        evaluation_epoch=101,
        lease_until_epoch=500,
    )

    short = control.attach_or_shorten_lease(
        valid_through_epoch=400,
        evaluation_epoch=200,
    )
    assert short["lease"]["valid_through_epoch"] == 400

    with pytest.raises(ReflexControlPlaneContractError):
        control.attach_or_shorten_lease(
            valid_through_epoch=450,
            evaluation_epoch=201,
        )


def test_expired_lease_collapses_privilege_on_restore(tmp_path):
    control = ReflexRuntimeControlPlane(root=tmp_path)
    _, request, _ = _setup(control)
    control.activate(
        request=request,
        grant_id="grant-001",
        evaluation_epoch=101,
        lease_until_epoch=150,
    )

    restarted = ReflexRuntimeControlPlane(root=tmp_path)
    status = restarted.status(evaluation_epoch=150)

    assert status["routing_influence_active"] is False
    assert status["recovery"]["status"] == "LEASE_EXPIRED"
    assert status["lease"] is None


def test_corrupt_activation_is_quarantined_and_fails_closed(tmp_path):
    control = ReflexRuntimeControlPlane(root=tmp_path)
    _, request, _ = _setup(control)
    control.activate(
        request=request,
        grant_id="grant-001",
        evaluation_epoch=101,
    )
    control.activation_path.write_text("{broken", encoding="utf-8")

    status = control.status(evaluation_epoch=102)

    assert status["routing_influence_active"] is False
    assert status["recovery"]["status"] == "RECOVERY_ROLLBACK"
    assert list(control.quarantine_dir.glob("activation.json.*.invalid"))


def test_runtime_evaluation_persists_signal_receipt_and_ledger(tmp_path):
    control = ReflexRuntimeControlPlane(root=tmp_path)
    _, request, _ = _setup(control)
    control.activate(
        request=request,
        grant_id="grant-001",
        evaluation_epoch=101,
    )

    signal, result = control.evaluate_active(
        reflex_input=ReflexInput(task_text="build adapter"),
        baseline_provider=FixedProvider(_baseline()),
        influence_provider=FixedProvider(_candidate()),
        evaluation_epoch=102,
    )

    assert signal is not None
    assert result["status"] == "INFLUENCED"
    ledger = control.ledger()
    assert any(entry["kind"] == "runtime" for entry in ledger)
    for index, entry in enumerate(ledger, start=1):
        assert entry["sequence"] == index
        if index > 1:
            assert entry["previous_entry_sha256"] == ledger[index - 2]["entry_sha256"]


def test_operator_deactivation_persists_across_restart(tmp_path):
    control = ReflexRuntimeControlPlane(root=tmp_path)
    _, request, _ = _setup(control)
    control.activate(
        request=request,
        grant_id="grant-001",
        evaluation_epoch=101,
    )

    result = control.deactivate(
        reason="operator kill switch",
        evaluation_epoch=102,
    )
    assert result["activation"]["routing_influence_active"] is False

    restarted = ReflexRuntimeControlPlane(root=tmp_path)
    status = restarted.status(evaluation_epoch=103)
    assert status["routing_influence_active"] is False


def test_corrupt_ledger_collapses_active_privilege(tmp_path):
    control = ReflexRuntimeControlPlane(root=tmp_path)
    _, request, _ = _setup(control)
    control.activate(
        request=request,
        grant_id="grant-001",
        evaluation_epoch=101,
    )
    control.ledger_path.write_text("not-json", encoding="utf-8")

    status = control.status(evaluation_epoch=102)

    assert status["routing_influence_active"] is False
    assert status["recovery"]["reason"] == (
        "ledger_integrity_loss_collapsed_privilege"
    )
    assert list(control.quarantine_dir.glob("ledger.json.*.invalid"))


def test_policy_replacement_requires_live_influence_to_be_deactivated(tmp_path):
    control = ReflexRuntimeControlPlane(root=tmp_path)
    policy, request, _ = _setup(control)
    control.activate(
        request=request,
        grant_id="grant-001",
        evaluation_epoch=101,
    )
    changed = replace(
        policy,
        revision=1,
        state_sha256="f" * 64,
    )

    with pytest.raises(Exception):
        control.ingest_policy_payload(
            changed.to_dict(),
            evaluation_epoch=102,
        )

def test_rejected_lease_extension_is_mutation_free(tmp_path):
    control = ReflexRuntimeControlPlane(root=tmp_path)
    _, request, _ = _setup(control)
    control.activate(
        request=request,
        grant_id="grant-001",
        evaluation_epoch=101,
        lease_until_epoch=500,
    )
    before = control.status(evaluation_epoch=200)
    before_sha = before["activation"]["state_sha256"]
    before_ledger = before["ledger_entries"]

    with pytest.raises(ReflexControlPlaneContractError):
        control.activate(
            request=request,
            grant_id="grant-001",
            evaluation_epoch=201,
            lease_until_epoch=600,
        )

    after = control.status(evaluation_epoch=202)
    assert after["activation"]["state_sha256"] == before_sha
    assert after["lease"]["valid_through_epoch"] == 500
    assert after["ledger_entries"] == before_ledger
