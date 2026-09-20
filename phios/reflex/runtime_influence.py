"""PhiReflex v0.6 governed runtime routing influence.

v0.6 is the first PhiReflex rung that may produce a live planner-context
signal. Activation requires an exact v0.5 policy, an explicit activation
request, and an exact external grant. Runtime influence is bounded to one
declared planner-context surface and never carries action/execution authority.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from typing import Any, Mapping

from phios.reflex.influence_adoption import (
    GovernedReflexInfluenceAdoptionGate,
    ReflexInfluencePolicyState,
)
from phios.reflex.models import (
    ROLE_LABELS,
    RISK_LABELS,
    ReflexDecision,
    ReflexInput,
)
from phios.reflex.providers.base import ReflexProvider, ReflexProviderUnavailable


ROUTING_SURFACE = "agentception.planner_context.v0.6"
SUPPORTED_DIMENSIONS = ("role", "risk", "system2", "verification")


class ReflexRuntimeInfluenceContractError(ValueError):
    """Raised when runtime influence state, grants, or signals are malformed."""


@dataclass(frozen=True, slots=True)
class ReflexActivationRequest:
    provider: str
    models: tuple[str, ...]
    routing_surface: str
    allowed_dimensions: tuple[str, ...]
    influence_weight: float

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ReflexRuntimeInfluenceContractError(
                "activation provider must be non-empty"
            )
        if not self.models or any(not model.strip() for model in self.models):
            raise ReflexRuntimeInfluenceContractError(
                "activation models must be non-empty"
            )
        if self.routing_surface != ROUTING_SURFACE:
            raise ReflexRuntimeInfluenceContractError(
                "unsupported routing surface"
            )
        _normalize_dimensions(self.allowed_dimensions)
        _validate_weight(self.influence_weight)

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": "phios.reflex_activation_request.v0.6",
            "provider": self.provider.strip(),
            "models": list(tuple(sorted(set(self.models)))),
            "routing_surface": self.routing_surface,
            "allowed_dimensions": list(
                _normalize_dimensions(self.allowed_dimensions)
            ),
            "influence_weight": _validate_weight(self.influence_weight),
        }

    @property
    def request_sha256(self) -> str:
        return _digest(self.to_payload())


@dataclass(frozen=True, slots=True)
class ReflexActivationGrant:
    grant_id: str
    authority_source: str
    policy_state_sha256: str
    current_activation_sha256: str | None
    activation_request_sha256: str
    disposition: str

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": "phios.reflex_activation_grant.v0.6",
            "grant_id": self.grant_id,
            "authority_source": self.authority_source,
            "policy_state_sha256": self.policy_state_sha256,
            "current_activation_sha256": self.current_activation_sha256,
            "activation_request_sha256": self.activation_request_sha256,
            "disposition": self.disposition,
        }

    @property
    def grant_sha256(self) -> str:
        return _digest(self.to_payload())


@dataclass(frozen=True, slots=True)
class ReflexActivationState:
    schema: str
    activation_id: str
    revision: int
    policy_state_sha256: str
    provider: str
    models: tuple[str, ...]
    routing_surface: str
    allowed_dimensions: tuple[str, ...]
    influence_weight: float
    consecutive_provider_errors: int
    parent_activation_sha256: str | None
    activated_by_grant_sha256: str
    routing_influence_active: bool
    routing_influence_authority: bool
    promotion_authority: bool
    action_authority: bool
    execution_authority: bool
    state_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "activation_id": self.activation_id,
            "revision": self.revision,
            "policy_state_sha256": self.policy_state_sha256,
            "provider": self.provider,
            "models": list(self.models),
            "routing_surface": self.routing_surface,
            "allowed_dimensions": list(self.allowed_dimensions),
            "influence_weight": self.influence_weight,
            "consecutive_provider_errors": self.consecutive_provider_errors,
            "parent_activation_sha256": self.parent_activation_sha256,
            "activated_by_grant_sha256": self.activated_by_grant_sha256,
            "routing_influence_active": self.routing_influence_active,
            "routing_influence_authority": self.routing_influence_authority,
            "promotion_authority": self.promotion_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "state_sha256": self.state_sha256,
        }


@dataclass(frozen=True, slots=True)
class ReflexActivationReceipt:
    schema: str
    status: str
    reason: str
    policy_state_sha256: str
    activation_request_sha256: str
    prior_activation_sha256: str | None
    next_activation_sha256: str | None
    grant_id: str | None
    grant_sha256: str | None
    authority_source: str | None
    grant_scope_valid: bool
    routing_influence_active: bool
    routing_influence_authority: bool
    promotion_authority: bool
    action_authority: bool
    execution_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "status": self.status,
            "reason": self.reason,
            "policy_state_sha256": self.policy_state_sha256,
            "activation_request_sha256": self.activation_request_sha256,
            "prior_activation_sha256": self.prior_activation_sha256,
            "next_activation_sha256": self.next_activation_sha256,
            "grant_id": self.grant_id,
            "grant_sha256": self.grant_sha256,
            "authority_source": self.authority_source,
            "grant_scope_valid": self.grant_scope_valid,
            "routing_influence_active": self.routing_influence_active,
            "routing_influence_authority": self.routing_influence_authority,
            "promotion_authority": self.promotion_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "receipt_sha256": self.receipt_sha256,
        }


@dataclass(frozen=True, slots=True)
class ReflexRoutingInfluenceSignal:
    schema: str
    activation_state_sha256: str
    policy_state_sha256: str
    routing_surface: str
    provider: str
    model: str
    influence_weight: float
    allowed_dimensions: tuple[str, ...]
    role_probabilities: tuple[tuple[str, float], ...] | None
    risk_probabilities: tuple[tuple[str, float], ...] | None
    needs_system2_probability: float | None
    needs_verification_probability: float | None
    routing_influence_authority: bool
    action_authority: bool
    execution_authority: bool
    signal_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "activation_state_sha256": self.activation_state_sha256,
            "policy_state_sha256": self.policy_state_sha256,
            "routing_surface": self.routing_surface,
            "provider": self.provider,
            "model": self.model,
            "influence_weight": self.influence_weight,
            "allowed_dimensions": list(self.allowed_dimensions),
            "role_probabilities": (
                dict(self.role_probabilities)
                if self.role_probabilities is not None
                else None
            ),
            "risk_probabilities": (
                dict(self.risk_probabilities)
                if self.risk_probabilities is not None
                else None
            ),
            "needs_system2_probability": self.needs_system2_probability,
            "needs_verification_probability": (
                self.needs_verification_probability
            ),
            "routing_influence_authority": self.routing_influence_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "signal_sha256": self.signal_sha256,
        }


@dataclass(frozen=True, slots=True)
class ReflexRuntimeInfluenceReceipt:
    schema: str
    status: str
    reason: str
    prior_activation_sha256: str
    next_activation_sha256: str
    provider_attempted: bool
    provider_status: str
    provider_model: str | None
    consecutive_provider_errors: int
    fallback_used: bool
    rollback_performed: bool
    signal_sha256: str | None
    routing_influence_active: bool
    routing_influence_authority: bool
    action_authority: bool
    execution_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "status": self.status,
            "reason": self.reason,
            "prior_activation_sha256": self.prior_activation_sha256,
            "next_activation_sha256": self.next_activation_sha256,
            "provider_attempted": self.provider_attempted,
            "provider_status": self.provider_status,
            "provider_model": self.provider_model,
            "consecutive_provider_errors": self.consecutive_provider_errors,
            "fallback_used": self.fallback_used,
            "rollback_performed": self.rollback_performed,
            "signal_sha256": self.signal_sha256,
            "routing_influence_active": self.routing_influence_active,
            "routing_influence_authority": self.routing_influence_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "receipt_sha256": self.receipt_sha256,
        }


class GovernedReflexRuntimeInfluence:
    """Activate, evaluate, and collapse bounded PhiReflex routing influence."""

    def __init__(self) -> None:
        self._policy_gate = GovernedReflexInfluenceAdoptionGate()

    def validate_activation_grant(
        self,
        grant: ReflexActivationGrant,
    ) -> None:
        """Validate an external activation grant without consuming it."""

        self._validate_grant(grant)

    def activate(
        self,
        *,
        policy: ReflexInfluencePolicyState,
        request: ReflexActivationRequest,
        grant: ReflexActivationGrant | None,
        current_activation: ReflexActivationState | None = None,
    ) -> tuple[ReflexActivationState | None, ReflexActivationReceipt]:
        self._policy_gate.validate_policy_state(policy)
        if current_activation is not None:
            self.validate_activation_state(current_activation)
            if current_activation.policy_state_sha256 != policy.state_sha256:
                raise ReflexRuntimeInfluenceContractError(
                    "current activation belongs to another influence policy"
                )
        self._validate_request_against_policy(request, policy)

        prior_sha = (
            current_activation.state_sha256
            if current_activation is not None
            else None
        )
        if grant is None:
            return current_activation, self._activation_receipt(
                status="HELD",
                reason="runtime_activation_authority_missing",
                policy=policy,
                request=request,
                prior=current_activation,
                next_state=current_activation,
                grant=None,
                grant_scope_valid=False,
            )
        self._validate_grant(grant)
        if grant.policy_state_sha256 != policy.state_sha256:
            reason = "grant_policy_scope_mismatch"
        elif grant.current_activation_sha256 != prior_sha:
            reason = "grant_current_activation_scope_mismatch"
        elif grant.activation_request_sha256 != request.request_sha256:
            reason = "grant_activation_request_scope_mismatch"
        elif _normalize_disposition(grant.disposition) == "HOLD":
            return current_activation, self._activation_receipt(
                status="HELD",
                reason="authorized_hold",
                policy=policy,
                request=request,
                prior=current_activation,
                next_state=current_activation,
                grant=grant,
                grant_scope_valid=True,
            )
        else:
            reason = ""

        if reason:
            return current_activation, self._activation_receipt(
                status="HELD",
                reason=reason,
                policy=policy,
                request=request,
                prior=current_activation,
                next_state=current_activation,
                grant=grant,
                grant_scope_valid=False,
            )

        next_state = self._build_activation_state(
            activation_id=(
                current_activation.activation_id
                if current_activation is not None
                else f"phios.reflex.runtime.{policy.policy_id}"
            ),
            revision=(
                current_activation.revision + 1
                if current_activation is not None
                else 0
            ),
            policy=policy,
            request=request,
            consecutive_provider_errors=0,
            parent_activation_sha256=prior_sha,
            activated_by_grant_sha256=grant.grant_sha256,
            active=True,
        )
        return next_state, self._activation_receipt(
            status="ACTIVATED",
            reason="authorized_runtime_influence_activated",
            policy=policy,
            request=request,
            prior=current_activation,
            next_state=next_state,
            grant=grant,
            grant_scope_valid=True,
        )

    def deactivate(
        self,
        *,
        policy: ReflexInfluencePolicyState,
        state: ReflexActivationState,
        reason: str,
    ) -> tuple[ReflexActivationState, ReflexActivationReceipt]:
        """Collapse routing privilege without requiring an expansion grant."""

        self._policy_gate.validate_policy_state(policy)
        self.validate_activation_state(state)
        if state.policy_state_sha256 != policy.state_sha256:
            raise ReflexRuntimeInfluenceContractError(
                "activation state belongs to another influence policy"
            )
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise ReflexRuntimeInfluenceContractError(
                "deactivation reason must be non-empty"
            )
        request = ReflexActivationRequest(
            provider=state.provider,
            models=state.models,
            routing_surface=state.routing_surface,
            allowed_dimensions=state.allowed_dimensions,
            influence_weight=state.influence_weight,
        )
        if not state.routing_influence_active:
            return state, self._activation_receipt(
                status="INACTIVE",
                reason="already_inactive",
                policy=policy,
                request=request,
                prior=state,
                next_state=state,
                grant=None,
                grant_scope_valid=False,
            )
        next_state = self._build_activation_state(
            activation_id=state.activation_id,
            revision=state.revision + 1,
            policy=policy,
            request=request,
            consecutive_provider_errors=state.consecutive_provider_errors,
            parent_activation_sha256=state.state_sha256,
            activated_by_grant_sha256=state.activated_by_grant_sha256,
            active=False,
        )
        return next_state, self._activation_receipt(
            status="DEACTIVATED",
            reason=f"privilege_collapsed:{normalized_reason}",
            policy=policy,
            request=request,
            prior=state,
            next_state=next_state,
            grant=None,
            grant_scope_valid=False,
        )

    def evaluate(
        self,
        *,
        policy: ReflexInfluencePolicyState,
        state: ReflexActivationState,
        reflex_input: ReflexInput,
        baseline_provider: ReflexProvider,
        influence_provider: ReflexProvider,
    ) -> tuple[
        ReflexActivationState,
        ReflexRoutingInfluenceSignal | None,
        ReflexRuntimeInfluenceReceipt,
    ]:
        self._policy_gate.validate_policy_state(policy)
        self.validate_activation_state(state)
        if state.policy_state_sha256 != policy.state_sha256:
            raise ReflexRuntimeInfluenceContractError(
                "activation state belongs to another influence policy"
            )
        if not state.routing_influence_active:
            return state, None, self._runtime_receipt(
                status="INACTIVE",
                reason="routing_influence_inactive",
                prior=state,
                next_state=state,
                provider_attempted=False,
                provider_status="not_attempted",
                provider_model=None,
                fallback_used=True,
                rollback_performed=False,
                signal=None,
            )

        baseline = baseline_provider.evaluate(reflex_input)
        try:
            candidate = influence_provider.evaluate(reflex_input)
        except ReflexProviderUnavailable:
            return self._provider_failure(
                policy=policy,
                state=state,
                reason="provider_unavailable",
                immediate_rollback=policy.rollback_on_provider_unavailable,
            )
        except Exception:
            return self._provider_failure(
                policy=policy,
                state=state,
                reason="provider_error",
                immediate_rollback=False,
            )

        if candidate.provider != state.provider:
            return self._provider_contract_rollback(
                policy=policy,
                state=state,
                reason="provider_identity_drift",
                provider_model=candidate.model,
            )
        if candidate.model not in state.models:
            return self._provider_contract_rollback(
                policy=policy,
                state=state,
                reason="provider_model_drift",
                provider_model=candidate.model,
            )

        signal = self._build_signal(
            policy=policy,
            state=state,
            baseline=baseline,
            candidate=candidate,
        )
        next_state = state
        if state.consecutive_provider_errors:
            next_state = replace(
                state,
                revision=state.revision + 1,
                consecutive_provider_errors=0,
                parent_activation_sha256=state.state_sha256,
                state_sha256="",
            )
            next_state = replace(
                next_state,
                state_sha256=_activation_state_digest(next_state),
            )

        return next_state, signal, self._runtime_receipt(
            status="INFLUENCED",
            reason="bounded_routing_signal_emitted",
            prior=state,
            next_state=next_state,
            provider_attempted=True,
            provider_status="ok",
            provider_model=candidate.model,
            fallback_used=False,
            rollback_performed=False,
            signal=signal,
        )

    def validate_activation_state(self, state: ReflexActivationState) -> None:
        if state.schema != "phios.reflex_activation_state.v0.6":
            raise ReflexRuntimeInfluenceContractError(
                "unsupported activation state schema"
            )
        if not state.activation_id.strip():
            raise ReflexRuntimeInfluenceContractError(
                "activation_id must be non-empty"
            )
        if state.revision < 0:
            raise ReflexRuntimeInfluenceContractError(
                "activation revision must be non-negative"
            )
        _require_sha256(state.policy_state_sha256, "policy_state_sha256")
        if state.parent_activation_sha256 is not None:
            _require_sha256(
                state.parent_activation_sha256,
                "parent_activation_sha256",
            )
        _require_sha256(
            state.activated_by_grant_sha256,
            "activated_by_grant_sha256",
        )
        if state.routing_surface != ROUTING_SURFACE:
            raise ReflexRuntimeInfluenceContractError(
                "activation state uses unsupported routing surface"
            )
        _normalize_dimensions(state.allowed_dimensions)
        _validate_weight(state.influence_weight)
        if state.consecutive_provider_errors < 0:
            raise ReflexRuntimeInfluenceContractError(
                "consecutive_provider_errors must be non-negative"
            )
        if state.routing_influence_active is not state.routing_influence_authority:
            raise ReflexRuntimeInfluenceContractError(
                "active state and routing influence authority must match"
            )
        if state.promotion_authority is not False:
            raise ReflexRuntimeInfluenceContractError(
                "runtime influence cannot carry promotion authority"
            )
        if state.action_authority is not False or state.execution_authority is not False:
            raise ReflexRuntimeInfluenceContractError(
                "runtime influence cannot carry action/execution authority"
            )
        if _activation_state_digest(state) != state.state_sha256:
            raise ReflexRuntimeInfluenceContractError(
                "activation state hash does not match contents"
            )

    def _validate_request_against_policy(
        self,
        request: ReflexActivationRequest,
        policy: ReflexInfluencePolicyState,
    ) -> None:
        if request.provider.strip() != policy.candidate_provider:
            raise ReflexRuntimeInfluenceContractError(
                "activation provider is outside adopted policy"
            )
        request_models = tuple(sorted(set(request.models)))
        if request_models != policy.candidate_models:
            raise ReflexRuntimeInfluenceContractError(
                "activation models do not match adopted policy"
            )
        dimensions = set(_normalize_dimensions(request.allowed_dimensions))
        if not dimensions.issubset(set(policy.allowed_dimensions)):
            raise ReflexRuntimeInfluenceContractError(
                "activation dimensions exceed adopted policy"
            )
        if request.influence_weight > policy.max_influence_weight:
            raise ReflexRuntimeInfluenceContractError(
                "activation weight exceeds adopted policy"
            )

    def _validate_grant(self, grant: ReflexActivationGrant) -> None:
        if not grant.grant_id.strip():
            raise ReflexRuntimeInfluenceContractError(
                "activation grant_id must be non-empty"
            )
        if not grant.authority_source.strip():
            raise ReflexRuntimeInfluenceContractError(
                "activation authority_source must be non-empty"
            )
        _require_sha256(grant.policy_state_sha256, "grant policy_state_sha256")
        if grant.current_activation_sha256 is not None:
            _require_sha256(
                grant.current_activation_sha256,
                "grant current_activation_sha256",
            )
        _require_sha256(
            grant.activation_request_sha256,
            "grant activation_request_sha256",
        )
        _normalize_disposition(grant.disposition)

    def _provider_failure(
        self,
        *,
        policy: ReflexInfluencePolicyState,
        state: ReflexActivationState,
        reason: str,
        immediate_rollback: bool,
    ) -> tuple[
        ReflexActivationState,
        None,
        ReflexRuntimeInfluenceReceipt,
    ]:
        errors = state.consecutive_provider_errors + 1
        rollback = (
            immediate_rollback
            or errors >= policy.max_consecutive_provider_errors
        )
        next_state = replace(
            state,
            revision=state.revision + 1,
            consecutive_provider_errors=errors,
            parent_activation_sha256=state.state_sha256,
            routing_influence_active=not rollback,
            routing_influence_authority=not rollback,
            state_sha256="",
        )
        next_state = replace(
            next_state,
            state_sha256=_activation_state_digest(next_state),
        )
        return next_state, None, self._runtime_receipt(
            status="ROLLED_BACK" if rollback else "FALLBACK",
            reason=reason,
            prior=state,
            next_state=next_state,
            provider_attempted=True,
            provider_status=reason,
            provider_model=None,
            fallback_used=True,
            rollback_performed=rollback,
            signal=None,
        )

    def _provider_contract_rollback(
        self,
        *,
        policy: ReflexInfluencePolicyState,
        state: ReflexActivationState,
        reason: str,
        provider_model: str | None,
    ) -> tuple[
        ReflexActivationState,
        None,
        ReflexRuntimeInfluenceReceipt,
    ]:
        next_state = replace(
            state,
            revision=state.revision + 1,
            consecutive_provider_errors=state.consecutive_provider_errors + 1,
            parent_activation_sha256=state.state_sha256,
            routing_influence_active=False,
            routing_influence_authority=False,
            state_sha256="",
        )
        next_state = replace(
            next_state,
            state_sha256=_activation_state_digest(next_state),
        )
        return next_state, None, self._runtime_receipt(
            status="ROLLED_BACK",
            reason=reason,
            prior=state,
            next_state=next_state,
            provider_attempted=True,
            provider_status="contract_drift",
            provider_model=provider_model,
            fallback_used=True,
            rollback_performed=True,
            signal=None,
        )

    def _build_signal(
        self,
        *,
        policy: ReflexInfluencePolicyState,
        state: ReflexActivationState,
        baseline: ReflexDecision,
        candidate: ReflexDecision,
    ) -> ReflexRoutingInfluenceSignal:
        weight = state.influence_weight
        dimensions = state.allowed_dimensions
        role_probs = (
            _blend_distribution(
                baseline.role_probabilities,
                candidate.role_probabilities,
                ROLE_LABELS,
                weight,
            )
            if "role" in dimensions
            else None
        )
        risk_probs = (
            _blend_distribution(
                baseline.risk_probabilities,
                candidate.risk_probabilities,
                RISK_LABELS,
                weight,
            )
            if "risk" in dimensions
            else None
        )
        system2 = (
            _blend_scalar(
                baseline.needs_system2_probability,
                candidate.needs_system2_probability,
                weight,
            )
            if "system2" in dimensions
            else None
        )
        verification = (
            _blend_scalar(
                baseline.needs_verification_probability,
                candidate.needs_verification_probability,
                weight,
            )
            if "verification" in dimensions
            else None
        )
        payload: dict[str, object] = {
            "schema": "phios.reflex_routing_influence_signal.v0.6",
            "activation_state_sha256": state.state_sha256,
            "policy_state_sha256": policy.state_sha256,
            "routing_surface": state.routing_surface,
            "provider": candidate.provider,
            "model": candidate.model,
            "influence_weight": weight,
            "allowed_dimensions": list(dimensions),
            "role_probabilities": dict(role_probs) if role_probs else None,
            "risk_probabilities": dict(risk_probs) if risk_probs else None,
            "needs_system2_probability": system2,
            "needs_verification_probability": verification,
            "routing_influence_authority": True,
            "action_authority": False,
            "execution_authority": False,
        }
        return ReflexRoutingInfluenceSignal(
            schema="phios.reflex_routing_influence_signal.v0.6",
            activation_state_sha256=state.state_sha256,
            policy_state_sha256=policy.state_sha256,
            routing_surface=state.routing_surface,
            provider=candidate.provider,
            model=candidate.model,
            influence_weight=weight,
            allowed_dimensions=dimensions,
            role_probabilities=role_probs,
            risk_probabilities=risk_probs,
            needs_system2_probability=system2,
            needs_verification_probability=verification,
            routing_influence_authority=True,
            action_authority=False,
            execution_authority=False,
            signal_sha256=_digest(payload),
        )

    def _build_activation_state(
        self,
        *,
        activation_id: str,
        revision: int,
        policy: ReflexInfluencePolicyState,
        request: ReflexActivationRequest,
        consecutive_provider_errors: int,
        parent_activation_sha256: str | None,
        activated_by_grant_sha256: str,
        active: bool,
    ) -> ReflexActivationState:
        state = ReflexActivationState(
            schema="phios.reflex_activation_state.v0.6",
            activation_id=activation_id,
            revision=revision,
            policy_state_sha256=policy.state_sha256,
            provider=request.provider.strip(),
            models=tuple(sorted(set(request.models))),
            routing_surface=request.routing_surface,
            allowed_dimensions=_normalize_dimensions(
                request.allowed_dimensions
            ),
            influence_weight=_validate_weight(request.influence_weight),
            consecutive_provider_errors=consecutive_provider_errors,
            parent_activation_sha256=parent_activation_sha256,
            activated_by_grant_sha256=activated_by_grant_sha256,
            routing_influence_active=active,
            routing_influence_authority=active,
            promotion_authority=False,
            action_authority=False,
            execution_authority=False,
            state_sha256="",
        )
        return replace(state, state_sha256=_activation_state_digest(state))

    def _activation_receipt(
        self,
        *,
        status: str,
        reason: str,
        policy: ReflexInfluencePolicyState,
        request: ReflexActivationRequest,
        prior: ReflexActivationState | None,
        next_state: ReflexActivationState | None,
        grant: ReflexActivationGrant | None,
        grant_scope_valid: bool,
    ) -> ReflexActivationReceipt:
        payload: dict[str, object] = {
            "schema": "phios.reflex_activation_receipt.v0.6",
            "status": status,
            "reason": reason,
            "policy_state_sha256": policy.state_sha256,
            "activation_request_sha256": request.request_sha256,
            "prior_activation_sha256": (
                prior.state_sha256 if prior is not None else None
            ),
            "next_activation_sha256": (
                next_state.state_sha256 if next_state is not None else None
            ),
            "grant_id": grant.grant_id if grant is not None else None,
            "grant_sha256": grant.grant_sha256 if grant is not None else None,
            "authority_source": (
                grant.authority_source if grant is not None else None
            ),
            "grant_scope_valid": grant_scope_valid,
            "routing_influence_active": (
                next_state.routing_influence_active
                if next_state is not None
                else False
            ),
            "routing_influence_authority": (
                next_state.routing_influence_authority
                if next_state is not None
                else False
            ),
            "promotion_authority": False,
            "action_authority": False,
            "execution_authority": False,
        }
        return ReflexActivationReceipt(
            schema="phios.reflex_activation_receipt.v0.6",
            status=status,
            reason=reason,
            policy_state_sha256=policy.state_sha256,
            activation_request_sha256=request.request_sha256,
            prior_activation_sha256=(
                prior.state_sha256 if prior is not None else None
            ),
            next_activation_sha256=(
                next_state.state_sha256 if next_state is not None else None
            ),
            grant_id=grant.grant_id if grant is not None else None,
            grant_sha256=grant.grant_sha256 if grant is not None else None,
            authority_source=(
                grant.authority_source if grant is not None else None
            ),
            grant_scope_valid=grant_scope_valid,
            routing_influence_active=(
                next_state.routing_influence_active
                if next_state is not None
                else False
            ),
            routing_influence_authority=(
                next_state.routing_influence_authority
                if next_state is not None
                else False
            ),
            promotion_authority=False,
            action_authority=False,
            execution_authority=False,
            receipt_sha256=_digest(payload),
        )

    def _runtime_receipt(
        self,
        *,
        status: str,
        reason: str,
        prior: ReflexActivationState,
        next_state: ReflexActivationState,
        provider_attempted: bool,
        provider_status: str,
        provider_model: str | None,
        fallback_used: bool,
        rollback_performed: bool,
        signal: ReflexRoutingInfluenceSignal | None,
    ) -> ReflexRuntimeInfluenceReceipt:
        payload: dict[str, object] = {
            "schema": "phios.reflex_runtime_influence_receipt.v0.6",
            "status": status,
            "reason": reason,
            "prior_activation_sha256": prior.state_sha256,
            "next_activation_sha256": next_state.state_sha256,
            "provider_attempted": provider_attempted,
            "provider_status": provider_status,
            "provider_model": provider_model,
            "consecutive_provider_errors": (
                next_state.consecutive_provider_errors
            ),
            "fallback_used": fallback_used,
            "rollback_performed": rollback_performed,
            "signal_sha256": (
                signal.signal_sha256 if signal is not None else None
            ),
            "routing_influence_active": (
                next_state.routing_influence_active
            ),
            "routing_influence_authority": (
                next_state.routing_influence_authority
            ),
            "action_authority": False,
            "execution_authority": False,
        }
        return ReflexRuntimeInfluenceReceipt(
            schema="phios.reflex_runtime_influence_receipt.v0.6",
            status=status,
            reason=reason,
            prior_activation_sha256=prior.state_sha256,
            next_activation_sha256=next_state.state_sha256,
            provider_attempted=provider_attempted,
            provider_status=provider_status,
            provider_model=provider_model,
            consecutive_provider_errors=(
                next_state.consecutive_provider_errors
            ),
            fallback_used=fallback_used,
            rollback_performed=rollback_performed,
            signal_sha256=(
                signal.signal_sha256 if signal is not None else None
            ),
            routing_influence_active=(
                next_state.routing_influence_active
            ),
            routing_influence_authority=(
                next_state.routing_influence_authority
            ),
            action_authority=False,
            execution_authority=False,
            receipt_sha256=_digest(payload),
        )


def apply_influence_signal_to_context(
    context: Mapping[str, Any],
    signal: ReflexRoutingInfluenceSignal,
) -> dict[str, Any]:
    """Attach one validated v0.6 signal to the declared planner surface."""

    _validate_signal(signal)
    if signal.routing_surface != ROUTING_SURFACE:
        raise ReflexRuntimeInfluenceContractError(
            "routing signal targets another surface"
        )
    result = dict(context)
    if "reflex_influence" in result:
        raise ReflexRuntimeInfluenceContractError(
            "planner context already contains reflex_influence"
        )
    result["reflex_influence"] = signal.to_dict()
    return result


def _validate_signal(signal: ReflexRoutingInfluenceSignal) -> None:
    if signal.schema != "phios.reflex_routing_influence_signal.v0.6":
        raise ReflexRuntimeInfluenceContractError(
            "unsupported routing influence signal schema"
        )
    _require_sha256(
        signal.activation_state_sha256,
        "activation_state_sha256",
    )
    _require_sha256(signal.policy_state_sha256, "policy_state_sha256")
    _normalize_dimensions(signal.allowed_dimensions)
    _validate_weight(signal.influence_weight)
    if signal.routing_influence_authority is not True:
        raise ReflexRuntimeInfluenceContractError(
            "live influence signal requires scoped routing authority"
        )
    if signal.action_authority is not False or signal.execution_authority is not False:
        raise ReflexRuntimeInfluenceContractError(
            "routing signal cannot carry action/execution authority"
        )
    expected = signal.to_dict()
    digest = str(expected.pop("signal_sha256"))
    if _digest(expected) != digest:
        raise ReflexRuntimeInfluenceContractError(
            "routing influence signal hash does not match contents"
        )


def _activation_state_digest(state: ReflexActivationState) -> str:
    payload = state.to_dict()
    payload.pop("state_sha256", None)
    return _digest(payload)


def _blend_distribution(
    baseline: tuple[tuple[str, float], ...],
    candidate: tuple[tuple[str, float], ...],
    labels: tuple[str, ...],
    weight: float,
) -> tuple[tuple[str, float], ...]:
    base_map = dict(baseline)
    candidate_map = dict(candidate)
    if set(base_map) != set(labels) or set(candidate_map) != set(labels):
        raise ReflexRuntimeInfluenceContractError(
            "provider probability labels do not match routing contract"
        )
    blended = tuple(
        (
            label,
            round(
                (1.0 - weight) * float(base_map[label])
                + weight * float(candidate_map[label]),
                12,
            ),
        )
        for label in labels
    )
    total = sum(value for _, value in blended)
    if not math.isfinite(total) or abs(total - 1.0) > 1e-6:
        raise ReflexRuntimeInfluenceContractError(
            "blended categorical probabilities are invalid"
        )
    return blended


def _blend_scalar(baseline: float, candidate: float, weight: float) -> float:
    value = (1.0 - weight) * float(baseline) + weight * float(candidate)
    if not math.isfinite(value) or value < 0 or value > 1:
        raise ReflexRuntimeInfluenceContractError(
            "blended scalar probability is invalid"
        )
    return round(value, 12)


def _normalize_dimensions(dimensions: tuple[str, ...]) -> tuple[str, ...]:
    if not dimensions:
        raise ReflexRuntimeInfluenceContractError(
            "allowed_dimensions must be non-empty"
        )
    normalized = tuple(sorted(set(dimensions)))
    if len(normalized) != len(dimensions):
        raise ReflexRuntimeInfluenceContractError(
            "allowed_dimensions must be unique"
        )
    if any(item not in SUPPORTED_DIMENSIONS for item in normalized):
        raise ReflexRuntimeInfluenceContractError(
            "unsupported routing influence dimension"
        )
    return normalized


def _validate_weight(value: float) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0 or number > 1:
        raise ReflexRuntimeInfluenceContractError(
            "influence_weight must be in (0, 1]"
        )
    return number


def _normalize_disposition(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in {"ACTIVATE", "HOLD"}:
        raise ReflexRuntimeInfluenceContractError(
            "activation disposition must be ACTIVATE or HOLD"
        )
    return normalized


def _require_sha256(value: str, label: str) -> None:
    normalized = value.strip().lower()
    if len(normalized) != 64:
        raise ReflexRuntimeInfluenceContractError(
            f"{label} must be a SHA-256 hex digest"
        )
    try:
        int(normalized, 16)
    except ValueError as exc:
        raise ReflexRuntimeInfluenceContractError(
            f"{label} must be a SHA-256 hex digest"
        ) from exc


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ReflexRuntimeInfluenceContractError(
            "runtime influence payload must be canonical JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
