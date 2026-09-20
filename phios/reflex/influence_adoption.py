"""PhiReflex v0.5 governed influence-policy adoption.

A v0.4 REVIEW_ELIGIBLE receipt is advisory evidence only. v0.5 requires an
exact scoped external grant before that evidence can become an immutable
influence-policy state. Adoption still does not activate routing influence.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping


INFLUENCE_DIMENSIONS = ("role", "risk", "system2", "verification")


class ReflexInfluenceAdoptionContractError(ValueError):
    """Raised when influence-adoption inputs or evidence are malformed."""


@dataclass(frozen=True, slots=True)
class ReflexInfluenceGrant:
    """External authority scoped to one readiness/policy/disposition tuple."""

    grant_id: str
    authority_source: str
    readiness_receipt_sha256: str
    current_policy_sha256: str | None
    candidate_provider: str
    allowed_dimensions: tuple[str, ...]
    max_influence_weight: float
    rollback_on_provider_unavailable: bool
    max_consecutive_provider_errors: int
    disposition: str

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": "phios.reflex_influence_grant.v0.5",
            "grant_id": self.grant_id,
            "authority_source": self.authority_source,
            "readiness_receipt_sha256": self.readiness_receipt_sha256,
            "current_policy_sha256": self.current_policy_sha256,
            "candidate_provider": self.candidate_provider,
            "allowed_dimensions": list(self.allowed_dimensions),
            "max_influence_weight": self.max_influence_weight,
            "rollback_on_provider_unavailable": (
                self.rollback_on_provider_unavailable
            ),
            "max_consecutive_provider_errors": (
                self.max_consecutive_provider_errors
            ),
            "disposition": self.disposition,
        }

    @property
    def grant_sha256(self) -> str:
        return _digest(self.to_payload())


@dataclass(frozen=True, slots=True)
class ReflexInfluencePolicyState:
    """Immutable adopted influence policy that remains runtime-inactive."""

    schema: str
    policy_id: str
    revision: int
    readiness_receipt_sha256: str
    candidate_provider: str
    candidate_models: tuple[str, ...]
    allowed_dimensions: tuple[str, ...]
    max_influence_weight: float
    rollback_on_provider_unavailable: bool
    max_consecutive_provider_errors: int
    parent_policy_sha256: str | None
    routing_influence_active: bool
    runtime_activation_authority: bool
    promotion_authority: bool
    action_authority: bool
    execution_authority: bool
    state_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "policy_id": self.policy_id,
            "revision": self.revision,
            "readiness_receipt_sha256": self.readiness_receipt_sha256,
            "candidate_provider": self.candidate_provider,
            "candidate_models": list(self.candidate_models),
            "allowed_dimensions": list(self.allowed_dimensions),
            "max_influence_weight": self.max_influence_weight,
            "rollback_on_provider_unavailable": (
                self.rollback_on_provider_unavailable
            ),
            "max_consecutive_provider_errors": (
                self.max_consecutive_provider_errors
            ),
            "parent_policy_sha256": self.parent_policy_sha256,
            "routing_influence_active": self.routing_influence_active,
            "runtime_activation_authority": self.runtime_activation_authority,
            "promotion_authority": self.promotion_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "state_sha256": self.state_sha256,
        }


@dataclass(frozen=True, slots=True)
class ReflexInfluenceAdoptionReceipt:
    """Deterministic ADOPTED / REJECTED / HELD influence-policy receipt."""

    schema: str
    status: str
    reason: str
    requested_disposition: str
    readiness_status: str
    readiness_receipt_sha256: str
    candidate_provider: str
    candidate_models: tuple[str, ...]
    prior_policy_sha256: str | None
    next_policy_sha256: str | None
    prior_revision: int | None
    next_revision: int | None
    allowed_dimensions: tuple[str, ...]
    max_influence_weight: float
    grant_id: str | None
    grant_sha256: str | None
    authority_source: str | None
    grant_scope_valid: bool
    policy_changed: bool
    routing_influence_active: bool
    runtime_activation_authority: bool
    promotion_authority: bool
    action_authority: bool
    execution_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "status": self.status,
            "reason": self.reason,
            "requested_disposition": self.requested_disposition,
            "readiness_status": self.readiness_status,
            "readiness_receipt_sha256": self.readiness_receipt_sha256,
            "candidate_provider": self.candidate_provider,
            "candidate_models": list(self.candidate_models),
            "prior_policy_sha256": self.prior_policy_sha256,
            "next_policy_sha256": self.next_policy_sha256,
            "prior_revision": self.prior_revision,
            "next_revision": self.next_revision,
            "allowed_dimensions": list(self.allowed_dimensions),
            "max_influence_weight": self.max_influence_weight,
            "grant_id": self.grant_id,
            "grant_sha256": self.grant_sha256,
            "authority_source": self.authority_source,
            "grant_scope_valid": self.grant_scope_valid,
            "policy_changed": self.policy_changed,
            "routing_influence_active": self.routing_influence_active,
            "runtime_activation_authority": self.runtime_activation_authority,
            "promotion_authority": self.promotion_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
            "receipt_sha256": self.receipt_sha256,
        }


class GovernedReflexInfluenceAdoptionGate:
    """Adopt advisory influence policy without activating routing influence."""

    def validate_policy_state(self, state: ReflexInfluencePolicyState) -> None:
        _validate_policy_state(state)

    def apply(
        self,
        *,
        readiness_receipt: Mapping[str, Any],
        requested_disposition: str,
        allowed_dimensions: tuple[str, ...],
        max_influence_weight: float,
        rollback_on_provider_unavailable: bool,
        max_consecutive_provider_errors: int,
        grant: ReflexInfluenceGrant | None,
        current_policy: ReflexInfluencePolicyState | None = None,
    ) -> tuple[
        ReflexInfluencePolicyState | None,
        ReflexInfluenceAdoptionReceipt,
    ]:
        readiness = _validate_readiness_receipt(dict(readiness_receipt))
        if current_policy is not None:
            _validate_policy_state(current_policy)

        disposition = _normalize_disposition(requested_disposition)
        dimensions = _normalize_dimensions(allowed_dimensions)
        weight = _validate_weight(max_influence_weight)
        error_limit = _validate_error_limit(max_consecutive_provider_errors)

        readiness_status = str(readiness["status"])
        provider = str(readiness["candidate_provider"]).strip()
        candidate_obj = readiness.get("candidate")
        models = _candidate_models(candidate_obj)

        if readiness_status != "REVIEW_ELIGIBLE":
            return current_policy, self._receipt(
                status="HELD",
                reason="readiness_not_review_eligible",
                disposition=disposition,
                readiness=readiness,
                current_policy=current_policy,
                next_policy=current_policy,
                dimensions=dimensions,
                weight=weight,
                grant=grant,
                grant_scope_valid=False,
            )

        scope_valid, scope_reason = self._grant_scope(
            readiness=readiness,
            current_policy=current_policy,
            disposition=disposition,
            provider=provider,
            dimensions=dimensions,
            weight=weight,
            rollback_on_provider_unavailable=rollback_on_provider_unavailable,
            max_consecutive_provider_errors=error_limit,
            grant=grant,
        )
        if not scope_valid:
            return current_policy, self._receipt(
                status="HELD",
                reason=scope_reason,
                disposition=disposition,
                readiness=readiness,
                current_policy=current_policy,
                next_policy=current_policy,
                dimensions=dimensions,
                weight=weight,
                grant=grant,
                grant_scope_valid=False,
            )

        if disposition == "HOLD":
            return current_policy, self._receipt(
                status="HELD",
                reason="authorized_hold",
                disposition=disposition,
                readiness=readiness,
                current_policy=current_policy,
                next_policy=current_policy,
                dimensions=dimensions,
                weight=weight,
                grant=grant,
                grant_scope_valid=True,
            )

        if disposition == "REJECT":
            return current_policy, self._receipt(
                status="REJECTED",
                reason="authorized_rejection",
                disposition=disposition,
                readiness=readiness,
                current_policy=current_policy,
                next_policy=current_policy,
                dimensions=dimensions,
                weight=weight,
                grant=grant,
                grant_scope_valid=True,
            )

        next_policy = _build_policy_state(
            policy_id=(
                current_policy.policy_id
                if current_policy is not None
                else f"phios.reflex.influence.{provider}"
            ),
            revision=(
                current_policy.revision + 1
                if current_policy is not None
                else 0
            ),
            readiness_receipt_sha256=str(readiness["receipt_sha256"]),
            candidate_provider=provider,
            candidate_models=models,
            allowed_dimensions=dimensions,
            max_influence_weight=weight,
            rollback_on_provider_unavailable=rollback_on_provider_unavailable,
            max_consecutive_provider_errors=error_limit,
            parent_policy_sha256=(
                current_policy.state_sha256
                if current_policy is not None
                else None
            ),
        )
        return next_policy, self._receipt(
            status="ADOPTED",
            reason="authorized_influence_policy_adopted",
            disposition=disposition,
            readiness=readiness,
            current_policy=current_policy,
            next_policy=next_policy,
            dimensions=dimensions,
            weight=weight,
            grant=grant,
            grant_scope_valid=True,
        )

    def _grant_scope(
        self,
        *,
        readiness: Mapping[str, Any],
        current_policy: ReflexInfluencePolicyState | None,
        disposition: str,
        provider: str,
        dimensions: tuple[str, ...],
        weight: float,
        rollback_on_provider_unavailable: bool,
        max_consecutive_provider_errors: int,
        grant: ReflexInfluenceGrant | None,
    ) -> tuple[bool, str]:
        if grant is None:
            return False, "influence_adoption_authority_missing"
        if not grant.grant_id.strip():
            raise ReflexInfluenceAdoptionContractError(
                "grant_id must be non-empty"
            )
        if not grant.authority_source.strip():
            raise ReflexInfluenceAdoptionContractError(
                "grant authority_source must be non-empty"
            )
        _require_sha256(
            grant.readiness_receipt_sha256,
            "grant readiness_receipt_sha256",
        )
        if grant.current_policy_sha256 is not None:
            _require_sha256(
                grant.current_policy_sha256,
                "grant current_policy_sha256",
            )

        if grant.readiness_receipt_sha256 != readiness["receipt_sha256"]:
            return False, "grant_readiness_scope_mismatch"
        current_sha = (
            current_policy.state_sha256 if current_policy is not None else None
        )
        if grant.current_policy_sha256 != current_sha:
            return False, "grant_current_policy_scope_mismatch"
        if grant.candidate_provider.strip() != provider:
            return False, "grant_provider_scope_mismatch"
        if _normalize_dimensions(grant.allowed_dimensions) != dimensions:
            return False, "grant_dimension_scope_mismatch"
        if _validate_weight(grant.max_influence_weight) != weight:
            return False, "grant_weight_scope_mismatch"
        if (
            grant.rollback_on_provider_unavailable
            != rollback_on_provider_unavailable
        ):
            return False, "grant_rollback_scope_mismatch"
        if (
            _validate_error_limit(grant.max_consecutive_provider_errors)
            != max_consecutive_provider_errors
        ):
            return False, "grant_error_limit_scope_mismatch"
        if _normalize_disposition(grant.disposition) != disposition:
            return False, "grant_disposition_scope_mismatch"
        return True, "grant_scope_valid"

    def _receipt(
        self,
        *,
        status: str,
        reason: str,
        disposition: str,
        readiness: Mapping[str, Any],
        current_policy: ReflexInfluencePolicyState | None,
        next_policy: ReflexInfluencePolicyState | None,
        dimensions: tuple[str, ...],
        weight: float,
        grant: ReflexInfluenceGrant | None,
        grant_scope_valid: bool,
    ) -> ReflexInfluenceAdoptionReceipt:
        candidate_obj = readiness.get("candidate")
        models = _candidate_models(candidate_obj)
        grant_id = grant.grant_id.strip() if grant is not None else None
        authority_source = (
            grant.authority_source.strip() if grant is not None else None
        )
        grant_sha = grant.grant_sha256 if grant is not None else None
        payload: dict[str, object] = {
            "schema": "phios.reflex_influence_adoption_receipt.v0.5",
            "status": status,
            "reason": reason,
            "requested_disposition": disposition,
            "readiness_status": str(readiness["status"]),
            "readiness_receipt_sha256": str(readiness["receipt_sha256"]),
            "candidate_provider": str(readiness["candidate_provider"]),
            "candidate_models": list(models),
            "prior_policy_sha256": (
                current_policy.state_sha256
                if current_policy is not None
                else None
            ),
            "next_policy_sha256": (
                next_policy.state_sha256 if next_policy is not None else None
            ),
            "prior_revision": (
                current_policy.revision if current_policy is not None else None
            ),
            "next_revision": (
                next_policy.revision if next_policy is not None else None
            ),
            "allowed_dimensions": list(dimensions),
            "max_influence_weight": weight,
            "grant_id": grant_id,
            "grant_sha256": grant_sha,
            "authority_source": authority_source,
            "grant_scope_valid": grant_scope_valid,
            "policy_changed": (
                current_policy is not next_policy
                and (
                    current_policy is None
                    or next_policy is None
                    or current_policy.state_sha256 != next_policy.state_sha256
                )
            ),
            "routing_influence_active": False,
            "runtime_activation_authority": False,
            "promotion_authority": False,
            "action_authority": False,
            "execution_authority": False,
        }
        return ReflexInfluenceAdoptionReceipt(
            schema="phios.reflex_influence_adoption_receipt.v0.5",
            status=status,
            reason=reason,
            requested_disposition=disposition,
            readiness_status=str(readiness["status"]),
            readiness_receipt_sha256=str(readiness["receipt_sha256"]),
            candidate_provider=str(readiness["candidate_provider"]),
            candidate_models=models,
            prior_policy_sha256=(
                current_policy.state_sha256
                if current_policy is not None
                else None
            ),
            next_policy_sha256=(
                next_policy.state_sha256 if next_policy is not None else None
            ),
            prior_revision=(
                current_policy.revision if current_policy is not None else None
            ),
            next_revision=(
                next_policy.revision if next_policy is not None else None
            ),
            allowed_dimensions=dimensions,
            max_influence_weight=weight,
            grant_id=grant_id,
            grant_sha256=grant_sha,
            authority_source=authority_source,
            grant_scope_valid=grant_scope_valid,
            policy_changed=bool(payload["policy_changed"]),
            routing_influence_active=False,
            runtime_activation_authority=False,
            promotion_authority=False,
            action_authority=False,
            execution_authority=False,
            receipt_sha256=_digest(payload),
        )


def _build_policy_state(
    *,
    policy_id: str,
    revision: int,
    readiness_receipt_sha256: str,
    candidate_provider: str,
    candidate_models: tuple[str, ...],
    allowed_dimensions: tuple[str, ...],
    max_influence_weight: float,
    rollback_on_provider_unavailable: bool,
    max_consecutive_provider_errors: int,
    parent_policy_sha256: str | None,
) -> ReflexInfluencePolicyState:
    payload: dict[str, object] = {
        "schema": "phios.reflex_influence_policy_state.v0.5",
        "policy_id": policy_id,
        "revision": revision,
        "readiness_receipt_sha256": readiness_receipt_sha256,
        "candidate_provider": candidate_provider,
        "candidate_models": list(candidate_models),
        "allowed_dimensions": list(allowed_dimensions),
        "max_influence_weight": max_influence_weight,
        "rollback_on_provider_unavailable": rollback_on_provider_unavailable,
        "max_consecutive_provider_errors": max_consecutive_provider_errors,
        "parent_policy_sha256": parent_policy_sha256,
        "routing_influence_active": False,
        "runtime_activation_authority": False,
        "promotion_authority": False,
        "action_authority": False,
        "execution_authority": False,
    }
    return ReflexInfluencePolicyState(
        schema="phios.reflex_influence_policy_state.v0.5",
        policy_id=policy_id,
        revision=revision,
        readiness_receipt_sha256=readiness_receipt_sha256,
        candidate_provider=candidate_provider,
        candidate_models=candidate_models,
        allowed_dimensions=allowed_dimensions,
        max_influence_weight=max_influence_weight,
        rollback_on_provider_unavailable=rollback_on_provider_unavailable,
        max_consecutive_provider_errors=max_consecutive_provider_errors,
        parent_policy_sha256=parent_policy_sha256,
        routing_influence_active=False,
        runtime_activation_authority=False,
        promotion_authority=False,
        action_authority=False,
        execution_authority=False,
        state_sha256=_digest(payload),
    )


def _validate_policy_state(state: ReflexInfluencePolicyState) -> None:
    if state.schema != "phios.reflex_influence_policy_state.v0.5":
        raise ReflexInfluenceAdoptionContractError(
            "unsupported influence policy schema"
        )
    if not state.policy_id.strip():
        raise ReflexInfluenceAdoptionContractError("policy_id must be non-empty")
    if state.revision < 0:
        raise ReflexInfluenceAdoptionContractError(
            "policy revision must be non-negative"
        )
    _require_sha256(
        state.readiness_receipt_sha256,
        "readiness_receipt_sha256",
    )
    if state.parent_policy_sha256 is not None:
        _require_sha256(
            state.parent_policy_sha256,
            "parent_policy_sha256",
        )
    if not state.candidate_provider.strip():
        raise ReflexInfluenceAdoptionContractError(
            "candidate_provider must be non-empty"
        )
    if not state.candidate_models or any(
        not model.strip() for model in state.candidate_models
    ):
        raise ReflexInfluenceAdoptionContractError(
            "candidate_models must be non-empty"
        )
    _normalize_dimensions(state.allowed_dimensions)
    _validate_weight(state.max_influence_weight)
    _validate_error_limit(state.max_consecutive_provider_errors)
    if state.routing_influence_active is not False:
        raise ReflexInfluenceAdoptionContractError(
            "v0.5 policy cannot activate routing influence"
        )
    if state.runtime_activation_authority is not False:
        raise ReflexInfluenceAdoptionContractError(
            "v0.5 policy cannot carry runtime activation authority"
        )
    if state.promotion_authority is not False:
        raise ReflexInfluenceAdoptionContractError(
            "v0.5 policy cannot carry promotion authority"
        )
    if state.action_authority is not False or state.execution_authority is not False:
        raise ReflexInfluenceAdoptionContractError(
            "v0.5 policy cannot carry action/execution authority"
        )

    expected = {
        key: value
        for key, value in state.to_dict().items()
        if key != "state_sha256"
    }
    if _digest(expected) != state.state_sha256:
        raise ReflexInfluenceAdoptionContractError(
            "influence policy state hash does not match contents"
        )


def _validate_readiness_receipt(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema") != "phios.reflex_promotion_readiness_receipt.v0.4":
        raise ReflexInfluenceAdoptionContractError(
            "unsupported readiness receipt schema"
        )
    if payload.get("status") not in {
        "INSUFFICIENT_EVIDENCE",
        "NOT_REVIEW_ELIGIBLE",
        "REVIEW_ELIGIBLE",
    }:
        raise ReflexInfluenceAdoptionContractError(
            "unsupported readiness status"
        )
    for key in (
        "routing_influence_authority",
        "promotion_authority",
        "action_authority",
        "execution_authority",
    ):
        if payload.get(key) is not False:
            raise ReflexInfluenceAdoptionContractError(
                f"readiness receipt must keep {key}=false"
            )
    provider = str(payload.get("candidate_provider", "")).strip()
    if not provider:
        raise ReflexInfluenceAdoptionContractError(
            "readiness candidate_provider must be non-empty"
        )
    _require_sha256(str(payload.get("policy_sha256", "")), "policy_sha256")
    _require_sha256(str(payload.get("receipt_sha256", "")), "receipt_sha256")
    source_shas = payload.get("source_receipt_sha256s")
    if not isinstance(source_shas, list):
        raise ReflexInfluenceAdoptionContractError(
            "source_receipt_sha256s must be a list"
        )
    for digest in source_shas:
        _require_sha256(str(digest), "source_receipt_sha256")
    if payload.get("status") == "REVIEW_ELIGIBLE":
        _candidate_models(payload.get("candidate"))

    expected = dict(payload)
    receipt_sha = str(expected.pop("receipt_sha256"))
    if _digest(expected) != receipt_sha:
        raise ReflexInfluenceAdoptionContractError(
            "readiness receipt hash does not match contents"
        )
    return payload


def _candidate_models(candidate: object) -> tuple[str, ...]:
    if not isinstance(candidate, dict):
        return ()
    models_obj = candidate.get("models")
    if not isinstance(models_obj, list):
        raise ReflexInfluenceAdoptionContractError(
            "candidate models must be a list"
        )
    models = tuple(sorted({str(item).strip() for item in models_obj}))
    if not models or any(not item for item in models):
        raise ReflexInfluenceAdoptionContractError(
            "candidate models must be non-empty"
        )
    return models


def _normalize_dimensions(dimensions: tuple[str, ...]) -> tuple[str, ...]:
    if not dimensions:
        raise ReflexInfluenceAdoptionContractError(
            "allowed_dimensions must be non-empty"
        )
    normalized = tuple(sorted(set(dimensions)))
    if len(normalized) != len(dimensions):
        raise ReflexInfluenceAdoptionContractError(
            "allowed_dimensions must be unique"
        )
    if any(item not in INFLUENCE_DIMENSIONS for item in normalized):
        raise ReflexInfluenceAdoptionContractError(
            "unsupported influence dimension"
        )
    return normalized


def _validate_weight(value: float) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0 or number > 1:
        raise ReflexInfluenceAdoptionContractError(
            "max_influence_weight must be in (0, 1]"
        )
    return number


def _validate_error_limit(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ReflexInfluenceAdoptionContractError(
            "max_consecutive_provider_errors must be a positive integer"
        )
    return value


def _normalize_disposition(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in {"ADOPT", "REJECT", "HOLD"}:
        raise ReflexInfluenceAdoptionContractError(
            "disposition must be ADOPT, REJECT, or HOLD"
        )
    return normalized


def _require_sha256(value: str, label: str) -> None:
    normalized = value.strip().lower()
    if len(normalized) != 64:
        raise ReflexInfluenceAdoptionContractError(
            f"{label} must be a SHA-256 hex digest"
        )
    try:
        int(normalized, 16)
    except ValueError as exc:
        raise ReflexInfluenceAdoptionContractError(
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
        raise ReflexInfluenceAdoptionContractError(
            "influence-adoption payload must be canonical JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
