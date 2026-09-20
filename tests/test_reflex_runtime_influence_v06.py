from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from phios.reflex.influence_adoption import ReflexInfluencePolicyState
from phios.reflex.models import ReflexDecision, ReflexInput
from phios.reflex.providers.base import ReflexProviderUnavailable
from phios.reflex.runtime_influence import (
    ROUTING_SURFACE,
    GovernedReflexRuntimeInfluence,
    ReflexActivationGrant,
    ReflexActivationRequest,
    ReflexRuntimeInfluenceContractError,
    apply_influence_signal_to_context,
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


def _policy(
    *,
    weight: float = 0.30,
    rollback_on_unavailable: bool = True,
    error_limit: int = 3,
):
    payload = {
        "schema": "phios.reflex_influence_policy_state.v0.5",
        "policy_id": "phios.reflex.influence.jev",
        "revision": 0,
        "readiness_receipt_sha256": "a" * 64,
        "candidate_provider": "jev",
        "candidate_models": ["jev-test"],
        "allowed_dimensions": ["role", "system2"],
        "max_influence_weight": weight,
        "rollback_on_provider_unavailable": rollback_on_unavailable,
        "max_consecutive_provider_errors": error_limit,
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
        max_influence_weight=weight,
        rollback_on_provider_unavailable=rollback_on_unavailable,
        max_consecutive_provider_errors=error_limit,
        parent_policy_sha256=None,
        routing_influence_active=False,
        runtime_activation_authority=False,
        promotion_authority=False,
        action_authority=False,
        execution_authority=False,
        state_sha256=_digest(payload),
    )


def _request(weight: float = 0.20):
    return ReflexActivationRequest(
        provider="jev",
        models=("jev-test",),
        routing_surface=ROUTING_SURFACE,
        allowed_dimensions=("role", "system2"),
        influence_weight=weight,
    )


def _grant(policy, request, current_sha=None, disposition="ACTIVATE"):
    return ReflexActivationGrant(
        grant_id="activate-001",
        authority_source="operator",
        policy_state_sha256=policy.state_sha256,
        current_activation_sha256=current_sha,
        activation_request_sha256=request.request_sha256,
        disposition=disposition,
    )


class FixedProvider:
    name = "fixed"

    def __init__(self, decision: ReflexDecision):
        self._decision = decision

    def evaluate(self, reflex_input: ReflexInput) -> ReflexDecision:
        return self._decision


class UnavailableProvider:
    name = "jev"

    def evaluate(self, reflex_input: ReflexInput) -> ReflexDecision:
        raise ReflexProviderUnavailable("offline")


class ErrorProvider:
    name = "jev"

    def evaluate(self, reflex_input: ReflexInput) -> ReflexDecision:
        raise RuntimeError("boom")


def _baseline():
    return ReflexDecision(
        provider="rules",
        provider_version="test",
        model="rules",
        role="utility",
        role_probabilities=(
            ("utility", 0.80),
            ("builder", 0.05),
            ("synthesis", 0.05),
            ("translator", 0.05),
            ("ledger", 0.05),
        ),
        risk="elevated",
        risk_probabilities=(
            ("low", 0.10),
            ("elevated", 0.80),
            ("high", 0.10),
        ),
        needs_system2_probability=0.20,
        needs_verification_probability=0.60,
        confidence=0.80,
        latency_ms=0.0,
    )


def _candidate(model: str = "jev-test"):
    return ReflexDecision(
        provider="jev",
        provider_version="test",
        model=model,
        role="builder",
        role_probabilities=(
            ("utility", 0.05),
            ("builder", 0.85),
            ("synthesis", 0.04),
            ("translator", 0.03),
            ("ledger", 0.03),
        ),
        risk="high",
        risk_probabilities=(
            ("low", 0.05),
            ("elevated", 0.15),
            ("high", 0.80),
        ),
        needs_system2_probability=0.90,
        needs_verification_probability=0.95,
        confidence=0.85,
        latency_ms=12.0,
    )


def _activated(policy=None, request=None):
    policy = policy or _policy()
    request = request or _request()
    runtime = GovernedReflexRuntimeInfluence()
    state, receipt = runtime.activate(
        policy=policy,
        request=request,
        grant=_grant(policy, request),
    )
    assert state is not None
    assert receipt.status == "ACTIVATED"
    return runtime, policy, request, state


def test_exact_grant_activates_scoped_routing_authority_only():
    runtime, policy, request, state = _activated()

    assert state.routing_influence_active is True
    assert state.routing_influence_authority is True
    assert state.promotion_authority is False
    assert state.action_authority is False
    assert state.execution_authority is False
    assert state.influence_weight == pytest.approx(0.20)
    runtime.validate_activation_state(state)


def test_missing_grant_holds_activation():
    policy = _policy()
    request = _request()

    state, receipt = GovernedReflexRuntimeInfluence().activate(
        policy=policy,
        request=request,
        grant=None,
    )

    assert state is None
    assert receipt.status == "HELD"
    assert receipt.reason == "runtime_activation_authority_missing"


def test_activation_weight_cannot_exceed_adopted_policy():
    policy = _policy(weight=0.20)

    with pytest.raises(ReflexRuntimeInfluenceContractError):
        GovernedReflexRuntimeInfluence().activate(
            policy=policy,
            request=_request(weight=0.30),
            grant=None,
        )


def test_successful_evaluation_emits_deterministic_bounded_signal():
    runtime, policy, _, state = _activated()
    next_state, signal, receipt = runtime.evaluate(
        policy=policy,
        state=state,
        reflex_input=ReflexInput(task_text="build adapter", tool_intent=True),
        baseline_provider=FixedProvider(_baseline()),
        influence_provider=FixedProvider(_candidate()),
    )

    assert next_state == state
    assert signal is not None
    assert receipt.status == "INFLUENCED"
    role = dict(signal.role_probabilities or ())
    assert role["builder"] == pytest.approx(
        0.8 * 0.05 + 0.2 * 0.85
    )
    assert signal.needs_system2_probability == pytest.approx(
        0.8 * 0.20 + 0.2 * 0.90
    )
    assert signal.risk_probabilities is None
    assert signal.needs_verification_probability is None
    assert signal.routing_influence_authority is True
    assert signal.action_authority is False
    assert signal.execution_authority is False


def test_signal_can_modify_only_declared_planner_context_surface():
    runtime, policy, _, state = _activated()
    _, signal, _ = runtime.evaluate(
        policy=policy,
        state=state,
        reflex_input=ReflexInput(task_text="build adapter"),
        baseline_provider=FixedProvider(_baseline()),
        influence_provider=FixedProvider(_candidate()),
    )
    assert signal is not None

    original = {"task": "build adapter", "arch": "default"}
    influenced = apply_influence_signal_to_context(original, signal)

    assert "reflex_influence" not in original
    assert influenced["task"] == "build adapter"
    assert influenced["reflex_influence"]["signal_sha256"] == signal.signal_sha256
    assert influenced["reflex_influence"]["action_authority"] is False


def test_provider_unavailable_immediately_rolls_back_when_policy_requires_it():
    runtime, policy, _, state = _activated(
        policy=_policy(rollback_on_unavailable=True)
    )

    next_state, signal, receipt = runtime.evaluate(
        policy=policy,
        state=state,
        reflex_input=ReflexInput(task_text="build adapter"),
        baseline_provider=FixedProvider(_baseline()),
        influence_provider=UnavailableProvider(),
    )

    assert signal is None
    assert receipt.status == "ROLLED_BACK"
    assert receipt.fallback_used is True
    assert next_state.routing_influence_active is False
    assert next_state.routing_influence_authority is False


def test_provider_errors_fallback_then_roll_back_at_threshold():
    runtime, policy, _, state = _activated(
        policy=_policy(
            rollback_on_unavailable=False,
            error_limit=2,
        )
    )

    state1, signal1, receipt1 = runtime.evaluate(
        policy=policy,
        state=state,
        reflex_input=ReflexInput(task_text="build adapter"),
        baseline_provider=FixedProvider(_baseline()),
        influence_provider=ErrorProvider(),
    )
    assert signal1 is None
    assert receipt1.status == "FALLBACK"
    assert state1.routing_influence_active is True
    assert state1.consecutive_provider_errors == 1

    state2, signal2, receipt2 = runtime.evaluate(
        policy=policy,
        state=state1,
        reflex_input=ReflexInput(task_text="build adapter"),
        baseline_provider=FixedProvider(_baseline()),
        influence_provider=ErrorProvider(),
    )
    assert signal2 is None
    assert receipt2.status == "ROLLED_BACK"
    assert state2.routing_influence_active is False
    assert state2.consecutive_provider_errors == 2


def test_model_drift_forces_immediate_rollback():
    runtime, policy, _, state = _activated()

    next_state, signal, receipt = runtime.evaluate(
        policy=policy,
        state=state,
        reflex_input=ReflexInput(task_text="build adapter"),
        baseline_provider=FixedProvider(_baseline()),
        influence_provider=FixedProvider(_candidate("jev-other")),
    )

    assert signal is None
    assert receipt.status == "ROLLED_BACK"
    assert receipt.reason == "provider_model_drift"
    assert next_state.routing_influence_active is False


def test_operator_deactivation_needs_no_privilege_expansion_grant():
    runtime, policy, _, state = _activated()

    next_state, receipt = runtime.deactivate(
        policy=policy,
        state=state,
        reason="operator kill switch",
    )

    assert receipt.status == "DEACTIVATED"
    assert next_state.routing_influence_active is False
    assert next_state.routing_influence_authority is False
    assert next_state.action_authority is False
    assert next_state.execution_authority is False


def test_tampered_activation_state_is_rejected():
    runtime, _, _, state = _activated()
    tampered = replace(state, influence_weight=0.90)

    with pytest.raises(ReflexRuntimeInfluenceContractError):
        runtime.validate_activation_state(tampered)
