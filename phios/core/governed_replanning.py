"""Governed advisory replanning for PhiOS core reasoning v0.5.

Replanning compares an incumbent path and a fresh candidate under the same exact
current field snapshot. A fixed hysteresis policy decides KEEP, REPLAN, or
UNRESOLVED. The decision never grants execution authority.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence

from phios.core.dynamic_field import DynamicFieldState
from phios.core.dynamic_state import DynamicStateEvaluation
from phios.core.field_aware_routing import (
    FieldAwarePathAssessmentReceipt,
    FieldAwareRouteReceipt,
    FieldAwareRouter,
)


State = Any
StateExpansion = Callable[[State], Iterable[State]]
GoalPredicate = Callable[[State], bool]


class GovernedReplanningContractError(ValueError):
    """Raised when a replanning contract cannot be evaluated safely."""


@dataclass(frozen=True, slots=True)
class ReplanPolicy:
    """Immutable hysteresis policy for advisory route replacement."""

    policy_id: str
    minimum_cost_improvement: float

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": "phios.replan_policy.v0.5",
            "policy_id": self.policy_id,
            "minimum_cost_improvement": self.minimum_cost_improvement,
        }

    @property
    def policy_sha256(self) -> str:
        return _payload_digest(self.to_payload())


@dataclass(frozen=True, slots=True)
class GovernedReplanReceipt:
    """Deterministic KEEP / REPLAN / UNRESOLVED advisory receipt."""

    schema: str
    decision: str
    reason: str
    policy_id: str
    policy_sha256: str
    minimum_cost_improvement: float
    previous_route_receipt_sha256: str
    previous_field_state_sha256: str
    current_field_state_sha256: str
    current_field_revision: int
    incumbent_assessment_sha256: str
    incumbent_path_ids: tuple[str, ...]
    incumbent_status: str
    incumbent_current_cost: float | None
    candidate_route_receipt_sha256: str
    candidate_path_ids: tuple[str, ...]
    candidate_status: str
    candidate_current_cost: float | None
    route_changed: bool
    cost_improvement: float | None
    comparison_scope: str
    action_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "decision": self.decision,
            "reason": self.reason,
            "policy_id": self.policy_id,
            "policy_sha256": self.policy_sha256,
            "minimum_cost_improvement": self.minimum_cost_improvement,
            "previous_route_receipt_sha256": self.previous_route_receipt_sha256,
            "previous_field_state_sha256": self.previous_field_state_sha256,
            "current_field_state_sha256": self.current_field_state_sha256,
            "current_field_revision": self.current_field_revision,
            "incumbent_assessment_sha256": self.incumbent_assessment_sha256,
            "incumbent_path_ids": list(self.incumbent_path_ids),
            "incumbent_status": self.incumbent_status,
            "incumbent_current_cost": self.incumbent_current_cost,
            "candidate_route_receipt_sha256": self.candidate_route_receipt_sha256,
            "candidate_path_ids": list(self.candidate_path_ids),
            "candidate_status": self.candidate_status,
            "candidate_current_cost": self.candidate_current_cost,
            "route_changed": self.route_changed,
            "cost_improvement": self.cost_improvement,
            "comparison_scope": self.comparison_scope,
            "action_authority": self.action_authority,
            "receipt_sha256": self.receipt_sha256,
        }


class GovernedReplanner:
    """Compare incumbent and candidate routes under one current field snapshot."""

    def __init__(
        self,
        *,
        router: FieldAwareRouter,
        policy: ReplanPolicy,
    ) -> None:
        self._router = router
        self._policy = self._validate_policy(policy)

    @property
    def policy(self) -> ReplanPolicy:
        return self._policy

    def assess(
        self,
        *,
        previous_route: FieldAwareRouteReceipt,
        current_field_state: DynamicFieldState | DynamicStateEvaluation,
        incumbent_path: Sequence[State],
        starts: Iterable[State],
        expand: StateExpansion,
        goal: GoalPredicate,
        base_cost: float = 1.0,
        max_states: int = 10_000,
    ) -> GovernedReplanReceipt:
        self._validate_previous_route(previous_route)

        resolved_current_state = (
            current_field_state.require_consumable_state()
            if isinstance(current_field_state, DynamicStateEvaluation)
            else current_field_state
        )

        incumbent = self._router.assess_path(
            current_field_state,
            incumbent_path,
            base_cost=base_cost,
        )
        if incumbent.path_ids != previous_route.path_ids:
            raise GovernedReplanningContractError(
                "incumbent path does not match previous route receipt"
            )
        if resolved_current_state.law_sha256 != previous_route.field_law_sha256:
            raise GovernedReplanningContractError(
                "current field law differs from previous route law"
            )
        if resolved_current_state.revision < previous_route.field_revision:
            raise GovernedReplanningContractError(
                "current field revision cannot precede previous route revision"
            )

        candidate = self._router.route(
            current_field_state,
            starts,
            expand=expand,
            goal=goal,
            base_cost=base_cost,
            max_states=max_states,
        )

        decision, reason, improvement = self._decide(
            incumbent=incumbent,
            candidate=candidate,
        )
        return self._build_receipt(
            decision=decision,
            reason=reason,
            improvement=improvement,
            previous_route=previous_route,
            current_field_state=resolved_current_state,
            incumbent=incumbent,
            candidate=candidate,
        )

    def _decide(
        self,
        *,
        incumbent: FieldAwarePathAssessmentReceipt,
        candidate: FieldAwareRouteReceipt,
    ) -> tuple[str, str, float | None]:
        route_changed = candidate.path_ids != incumbent.path_ids

        if candidate.status != "found" or candidate.total_cost is None:
            return "UNRESOLVED", "candidate_route_unresolved", None

        if incumbent.status == "blocked" or incumbent.total_cost is None:
            return "REPLAN", "incumbent_path_blocked", None

        improvement = incumbent.total_cost - candidate.total_cost
        if not route_changed:
            return "KEEP", "same_route_remains_preferred", improvement

        if improvement > self._policy.minimum_cost_improvement:
            return "REPLAN", "cost_improvement_exceeds_hysteresis", improvement

        return "KEEP", "hysteresis_threshold_not_exceeded", improvement

    def _validate_policy(self, policy: ReplanPolicy) -> ReplanPolicy:
        policy_id = policy.policy_id.strip()
        if not policy_id:
            raise GovernedReplanningContractError(
                "replan policy_id must be non-empty"
            )
        threshold = _require_nonnegative_finite(
            policy.minimum_cost_improvement,
            "minimum_cost_improvement",
        )
        return ReplanPolicy(
            policy_id=policy_id,
            minimum_cost_improvement=threshold,
        )

    def _validate_previous_route(
        self,
        receipt: FieldAwareRouteReceipt,
    ) -> None:
        if receipt.schema != "phios.field_aware_route_receipt.v0.4":
            raise GovernedReplanningContractError(
                "unsupported previous route receipt schema"
            )
        if receipt.action_authority is not False:
            raise GovernedReplanningContractError(
                "previous route receipt cannot carry action authority"
            )
        if receipt.status != "found":
            raise GovernedReplanningContractError(
                "previous route receipt must contain a found incumbent route"
            )
        if not receipt.path_ids:
            raise GovernedReplanningContractError(
                "previous route receipt must contain path IDs"
            )

        expected = _route_receipt_digest(receipt)
        if expected != receipt.receipt_sha256:
            raise GovernedReplanningContractError(
                "previous route receipt hash does not match receipt contents"
            )

    def _build_receipt(
        self,
        *,
        decision: str,
        reason: str,
        improvement: float | None,
        previous_route: FieldAwareRouteReceipt,
        current_field_state: DynamicFieldState,
        incumbent: FieldAwarePathAssessmentReceipt,
        candidate: FieldAwareRouteReceipt,
    ) -> GovernedReplanReceipt:
        route_changed = candidate.path_ids != incumbent.path_ids
        payload: dict[str, object] = {
            "schema": "phios.governed_replan_receipt.v0.5",
            "decision": decision,
            "reason": reason,
            "policy_id": self._policy.policy_id,
            "policy_sha256": self._policy.policy_sha256,
            "minimum_cost_improvement": self._policy.minimum_cost_improvement,
            "previous_route_receipt_sha256": previous_route.receipt_sha256,
            "previous_field_state_sha256": previous_route.field_state_sha256,
            "current_field_state_sha256": current_field_state.state_sha256,
            "current_field_revision": current_field_state.revision,
            "incumbent_assessment_sha256": incumbent.receipt_sha256,
            "incumbent_path_ids": list(incumbent.path_ids),
            "incumbent_status": incumbent.status,
            "incumbent_current_cost": incumbent.total_cost,
            "candidate_route_receipt_sha256": candidate.receipt_sha256,
            "candidate_path_ids": list(candidate.path_ids),
            "candidate_status": candidate.status,
            "candidate_current_cost": candidate.total_cost,
            "route_changed": route_changed,
            "cost_improvement": improvement,
            "comparison_scope": (
                "incumbent_and_candidate_evaluated_at_exact_current_field_snapshot"
            ),
            "action_authority": False,
        }
        return GovernedReplanReceipt(
            schema="phios.governed_replan_receipt.v0.5",
            decision=decision,
            reason=reason,
            policy_id=self._policy.policy_id,
            policy_sha256=self._policy.policy_sha256,
            minimum_cost_improvement=self._policy.minimum_cost_improvement,
            previous_route_receipt_sha256=previous_route.receipt_sha256,
            previous_field_state_sha256=previous_route.field_state_sha256,
            current_field_state_sha256=current_field_state.state_sha256,
            current_field_revision=current_field_state.revision,
            incumbent_assessment_sha256=incumbent.receipt_sha256,
            incumbent_path_ids=incumbent.path_ids,
            incumbent_status=incumbent.status,
            incumbent_current_cost=incumbent.total_cost,
            candidate_route_receipt_sha256=candidate.receipt_sha256,
            candidate_path_ids=candidate.path_ids,
            candidate_status=candidate.status,
            candidate_current_cost=candidate.total_cost,
            route_changed=route_changed,
            cost_improvement=improvement,
            comparison_scope=(
                "incumbent_and_candidate_evaluated_at_exact_current_field_snapshot"
            ),
            action_authority=False,
            receipt_sha256=_payload_digest(payload),
        )


def _route_receipt_digest(receipt: FieldAwareRouteReceipt) -> str:
    payload: dict[str, object] = {
        "schema": receipt.schema,
        "status": receipt.status,
        "field_law_sha256": receipt.field_law_sha256,
        "field_state_sha256": receipt.field_state_sha256,
        "field_revision": receipt.field_revision,
        "bindings": [item.to_dict() for item in receipt.bindings],
        "path_receipt_sha256": receipt.path_receipt_sha256,
        "path_ids": list(receipt.path_ids),
        "total_cost": receipt.total_cost,
        "optimality_scope": receipt.optimality_scope,
        "action_authority": receipt.action_authority,
    }
    return _payload_digest(payload)


def _require_finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GovernedReplanningContractError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise GovernedReplanningContractError(f"{label} must be finite")
    return number


def _require_nonnegative_finite(value: object, label: str) -> float:
    number = _require_finite(value, label)
    if number < 0:
        raise GovernedReplanningContractError(f"{label} must be non-negative")
    return number


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
        raise GovernedReplanningContractError(
            "governed replanning payload must be canonical JSON"
        ) from exc


def _payload_digest(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(
        _canonical_json(dict(payload)).encode("utf-8")
    ).hexdigest()
