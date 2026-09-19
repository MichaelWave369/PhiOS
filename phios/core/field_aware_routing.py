"""Field-aware advisory routing for PhiOS core reasoning v0.4.

This layer binds validated Dynamic Field State v0.3 snapshots into
Relational Field Geometry v0.2 costs. Dynamic field values may reshape soft
route costs, while hard transition constraints remain absolute.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence

from phios.core.dynamic_field import DynamicField, DynamicFieldState
from phios.core.relational_field import (
    FieldAxisSpec,
    FieldPathReceipt,
    RelationCostSpec,
    RelationalField,
    RelationalFieldContractError,
    TransitionConstraintSpec,
)


State = Any
StateId = Callable[[State], str]
RelationMeasure = Callable[[State, State], float]
StateExpansion = Callable[[State], Iterable[State]]
GoalPredicate = Callable[[State], bool]


class FieldAwareRoutingContractError(ValueError):
    """Raised when a field-aware routing contract cannot be evaluated safely."""


@dataclass(frozen=True, slots=True)
class DynamicCostBinding:
    """Bind one non-negative live field value to one transition susceptibility."""

    name: str
    field_variable: str
    evaluate: RelationMeasure
    scale: float = 1.0


@dataclass(frozen=True, slots=True)
class DynamicBindingSnapshot:
    """Exact dynamic value used to build one routing cost term."""

    name: str
    field_variable: str
    field_value: float
    scale: float

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "field_variable": self.field_variable,
            "field_value": self.field_value,
            "scale": self.scale,
        }


@dataclass(frozen=True, slots=True)
class FieldAwarePathAssessmentReceipt:
    """Cost/admissibility of one explicit path at one exact field snapshot."""

    schema: str
    status: str
    field_law_sha256: str
    field_state_sha256: str
    field_revision: int
    bindings: tuple[DynamicBindingSnapshot, ...]
    path_ids: tuple[str, ...]
    transition_receipt_sha256s: tuple[str, ...]
    blocked_transition_index: int | None
    total_cost: float | None
    action_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "status": self.status,
            "field_law_sha256": self.field_law_sha256,
            "field_state_sha256": self.field_state_sha256,
            "field_revision": self.field_revision,
            "bindings": [item.to_dict() for item in self.bindings],
            "path_ids": list(self.path_ids),
            "transition_receipt_sha256s": list(self.transition_receipt_sha256s),
            "blocked_transition_index": self.blocked_transition_index,
            "total_cost": self.total_cost,
            "action_authority": self.action_authority,
            "receipt_sha256": self.receipt_sha256,
        }


@dataclass(frozen=True, slots=True)
class FieldAwareRouteReceipt:
    """Receipt binding a route result to the exact dynamic-field snapshot."""

    schema: str
    status: str
    field_law_sha256: str
    field_state_sha256: str
    field_revision: int
    bindings: tuple[DynamicBindingSnapshot, ...]
    path_receipt_sha256: str
    path_ids: tuple[str, ...]
    total_cost: float | None
    optimality_scope: str
    action_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "status": self.status,
            "field_law_sha256": self.field_law_sha256,
            "field_state_sha256": self.field_state_sha256,
            "field_revision": self.field_revision,
            "bindings": [item.to_dict() for item in self.bindings],
            "path_receipt_sha256": self.path_receipt_sha256,
            "path_ids": list(self.path_ids),
            "total_cost": self.total_cost,
            "optimality_scope": self.optimality_scope,
            "action_authority": self.action_authority,
            "receipt_sha256": self.receipt_sha256,
        }


class FieldAwareRouter:
    """Route over a static transition graph using one validated live field snapshot.

    Hard constraints are passed unchanged into RelationalField. Dynamic values
    can only add non-negative soft relation cost through explicit bindings.
    """

    def __init__(
        self,
        *,
        dynamic_field: DynamicField,
        state_id: StateId,
        axes: Sequence[FieldAxisSpec] = (),
        relation_costs: Sequence[RelationCostSpec] = (),
        constraints: Sequence[TransitionConstraintSpec] = (),
        dynamic_bindings: Sequence[DynamicCostBinding] = (),
    ) -> None:
        self._dynamic_field = dynamic_field
        self._state_id = state_id
        self._axes = tuple(axes)
        self._relation_costs = tuple(relation_costs)
        self._constraints = tuple(constraints)
        self._dynamic_bindings = tuple(dynamic_bindings)

        names = [binding.name.strip() for binding in self._dynamic_bindings]
        if any(not name for name in names):
            raise FieldAwareRoutingContractError(
                "dynamic binding names must be non-empty"
            )
        if len(set(names)) != len(names):
            raise FieldAwareRoutingContractError(
                "dynamic binding names must be unique"
            )

        law_rules = {
            rule.name: rule
            for rule in self._dynamic_field.law.variables
        }
        for binding in self._dynamic_bindings:
            variable = binding.field_variable.strip()
            if variable not in law_rules:
                raise FieldAwareRoutingContractError(
                    f"binding {binding.name!r} references unknown field variable "
                    f"{variable!r}"
                )
            if law_rules[variable].minimum < 0:
                raise FieldAwareRoutingContractError(
                    f"binding {binding.name!r} requires a field variable with "
                    "non-negative governing bounds"
                )
            _require_nonnegative_finite(
                binding.scale,
                f"binding {binding.name!r} scale",
            )

    def route(
        self,
        field_state: DynamicFieldState,
        starts: Iterable[State],
        *,
        expand: StateExpansion,
        goal: GoalPredicate,
        base_cost: float = 1.0,
        max_states: int = 10_000,
    ) -> FieldAwareRouteReceipt:
        reasoner, snapshots = self._reasoner_for_state(field_state)
        try:
            path = reasoner.least_cost_path(
                starts,
                expand=expand,
                goal=goal,
                base_cost=base_cost,
                max_states=max_states,
            )
        except RelationalFieldContractError as exc:
            raise FieldAwareRoutingContractError(str(exc)) from exc

        return self._build_receipt(
            field_state=field_state,
            snapshots=snapshots,
            path=path,
        )

    def assess_path(
        self,
        field_state: DynamicFieldState,
        path_states: Sequence[State],
        *,
        base_cost: float = 1.0,
    ) -> FieldAwarePathAssessmentReceipt:
        """Re-score one explicit path under one exact validated field snapshot."""

        reasoner, snapshots = self._reasoner_for_state(field_state)
        states = tuple(path_states)
        if not states:
            raise FieldAwareRoutingContractError(
                "path assessment requires at least one state"
            )

        path_ids = tuple(_require_state_id(self._state_id(state)) for state in states)
        transition_hashes: list[str] = []
        total_cost = 0.0
        blocked_index: int | None = None
        status = "admissible"

        for index, (source, target) in enumerate(zip(states, states[1:])):
            try:
                transition = reasoner.assess_transition(
                    source,
                    target,
                    base_cost=base_cost,
                )
            except RelationalFieldContractError as exc:
                raise FieldAwareRoutingContractError(str(exc)) from exc
            transition_hashes.append(transition.receipt_sha256)
            if transition.status == "blocked":
                status = "blocked"
                blocked_index = index
                total: float | None = None
                break
            if transition.total_cost is None:
                raise FieldAwareRoutingContractError(
                    "admissible transition must have total cost"
                )
            total_cost += transition.total_cost
        else:
            total = total_cost

        payload: dict[str, object] = {
            "schema": "phios.field_aware_path_assessment.v0.5",
            "status": status,
            "field_law_sha256": field_state.law_sha256,
            "field_state_sha256": field_state.state_sha256,
            "field_revision": field_state.revision,
            "bindings": [item.to_dict() for item in snapshots],
            "path_ids": list(path_ids),
            "transition_receipt_sha256s": transition_hashes,
            "blocked_transition_index": blocked_index,
            "total_cost": total,
            "action_authority": False,
        }
        return FieldAwarePathAssessmentReceipt(
            schema="phios.field_aware_path_assessment.v0.5",
            status=status,
            field_law_sha256=field_state.law_sha256,
            field_state_sha256=field_state.state_sha256,
            field_revision=field_state.revision,
            bindings=snapshots,
            path_ids=path_ids,
            transition_receipt_sha256s=tuple(transition_hashes),
            blocked_transition_index=blocked_index,
            total_cost=total,
            action_authority=False,
            receipt_sha256=_payload_digest(payload),
        )

    def _reasoner_for_state(
        self,
        field_state: DynamicFieldState,
    ) -> tuple[RelationalField, tuple[DynamicBindingSnapshot, ...]]:
        self._dynamic_field.validate_state(field_state)
        values = field_state.as_mapping()

        snapshots: list[DynamicBindingSnapshot] = []
        dynamic_relation_costs: list[RelationCostSpec] = []
        for binding in sorted(
            self._dynamic_bindings,
            key=lambda item: item.name,
        ):
            variable = binding.field_variable.strip()
            field_value = _require_nonnegative_finite(
                values[variable],
                f"dynamic field {variable!r} value",
            )
            scale = _require_nonnegative_finite(
                binding.scale,
                f"binding {binding.name!r} scale",
            )
            snapshots.append(
                DynamicBindingSnapshot(
                    name=binding.name,
                    field_variable=variable,
                    field_value=field_value,
                    scale=scale,
                )
            )
            dynamic_relation_costs.append(
                RelationCostSpec(
                    name=f"dynamic:{binding.name}",
                    evaluate=_bound_relation_measure(
                        binding_name=binding.name,
                        evaluator=binding.evaluate,
                        field_value=field_value,
                    ),
                    weight=scale,
                )
            )

        reasoner = RelationalField(
            state_id=self._state_id,
            axes=self._axes,
            relation_costs=self._relation_costs + tuple(dynamic_relation_costs),
            constraints=self._constraints,
        )
        return reasoner, tuple(snapshots)

    def _build_receipt(
        self,
        *,
        field_state: DynamicFieldState,
        snapshots: tuple[DynamicBindingSnapshot, ...],
        path: FieldPathReceipt,
    ) -> FieldAwareRouteReceipt:
        payload: dict[str, object] = {
            "schema": "phios.field_aware_route_receipt.v0.4",
            "status": path.status,
            "field_law_sha256": field_state.law_sha256,
            "field_state_sha256": field_state.state_sha256,
            "field_revision": field_state.revision,
            "bindings": [item.to_dict() for item in snapshots],
            "path_receipt_sha256": path.receipt_sha256,
            "path_ids": list(path.path_ids),
            "total_cost": path.total_cost,
            "optimality_scope": (
                "least_declared_cost_over_observed_graph_at_exact_field_snapshot"
            ),
            "action_authority": False,
        }
        return FieldAwareRouteReceipt(
            schema="phios.field_aware_route_receipt.v0.4",
            status=path.status,
            field_law_sha256=field_state.law_sha256,
            field_state_sha256=field_state.state_sha256,
            field_revision=field_state.revision,
            bindings=snapshots,
            path_receipt_sha256=path.receipt_sha256,
            path_ids=path.path_ids,
            total_cost=path.total_cost,
            optimality_scope=(
                "least_declared_cost_over_observed_graph_at_exact_field_snapshot"
            ),
            action_authority=False,
            receipt_sha256=_payload_digest(payload),
        )


def _bound_relation_measure(
    *,
    binding_name: str,
    evaluator: RelationMeasure,
    field_value: float,
) -> RelationMeasure:
    def measure(source: State, target: State) -> float:
        try:
            susceptibility = _require_nonnegative_finite(
                evaluator(source, target),
                f"binding {binding_name!r} transition susceptibility",
            )
        except Exception as exc:
            if isinstance(exc, FieldAwareRoutingContractError):
                raise
            raise FieldAwareRoutingContractError(
                f"binding {binding_name!r} could not be evaluated: "
                f"{type(exc).__name__}"
            ) from exc
        return field_value * susceptibility

    return measure


def _require_state_id(value: object) -> str:
    state_id = str(value).strip()
    if not state_id:
        raise FieldAwareRoutingContractError("state_id must be non-empty")
    return state_id


def _require_finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FieldAwareRoutingContractError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise FieldAwareRoutingContractError(f"{label} must be finite")
    return number


def _require_nonnegative_finite(value: object, label: str) -> float:
    number = _require_finite(value, label)
    if number < 0:
        raise FieldAwareRoutingContractError(f"{label} must be non-negative")
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
        raise FieldAwareRoutingContractError(
            "field-aware routing payload must be canonical JSON"
        ) from exc


def _payload_digest(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(
        _canonical_json(dict(payload)).encode("utf-8")
    ).hexdigest()
