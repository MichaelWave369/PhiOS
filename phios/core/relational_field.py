"""Advisory relational field geometry for PhiOS.

The field separates hard admissibility boundaries from soft non-negative costs.
It can compare transitions and search for low-cost paths, but it never grants
execution authority.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import math
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence


State = Any
StateId = Callable[[State], str]
StateMeasure = Callable[[State], float]
RelationMeasure = Callable[[State, State], float]
TransitionPredicate = Callable[[State, State], bool]
StateExpansion = Callable[[State], Iterable[State]]
GoalPredicate = Callable[[State], bool]


class RelationalFieldContractError(ValueError):
    """Raised when a relational-field contract cannot be evaluated safely."""


@dataclass(frozen=True, slots=True)
class FieldAxisSpec:
    """Soft state field whose change contributes non-negative path cost."""

    name: str
    measure: StateMeasure
    weight: float = 1.0


@dataclass(frozen=True, slots=True)
class RelationCostSpec:
    """Soft directional relation cost evaluated for one transition."""

    name: str
    evaluate: RelationMeasure
    weight: float = 1.0


@dataclass(frozen=True, slots=True)
class TransitionConstraintSpec:
    """Hard transition boundary. Failure blocks the edge completely."""

    name: str
    predicate: TransitionPredicate


@dataclass(frozen=True, slots=True)
class AxisChange:
    """Measured contribution from one state field."""

    name: str
    source_value: float
    target_value: float
    absolute_delta: float
    weighted_cost: float

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "source_value": self.source_value,
            "target_value": self.target_value,
            "absolute_delta": self.absolute_delta,
            "weighted_cost": self.weighted_cost,
        }


@dataclass(frozen=True, slots=True)
class RelationCost:
    """Measured contribution from one pairwise relation."""

    name: str
    raw_cost: float
    weighted_cost: float

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "raw_cost": self.raw_cost,
            "weighted_cost": self.weighted_cost,
        }


@dataclass(frozen=True, slots=True)
class TransitionReceipt:
    """Deterministic advisory assessment for one state transition."""

    schema: str
    source_id: str
    target_id: str
    status: str
    blocked_by: tuple[str, ...]
    base_cost: float
    axis_changes: tuple[AxisChange, ...]
    relation_costs: tuple[RelationCost, ...]
    total_cost: float | None
    action_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "status": self.status,
            "blocked_by": list(self.blocked_by),
            "base_cost": self.base_cost,
            "axis_changes": [item.to_dict() for item in self.axis_changes],
            "relation_costs": [item.to_dict() for item in self.relation_costs],
            "total_cost": self.total_cost,
            "action_authority": self.action_authority,
            "receipt_sha256": self.receipt_sha256,
        }


@dataclass(frozen=True, slots=True)
class FieldPathReceipt:
    """Receipt for bounded least-declared-cost search over observed transitions."""

    schema: str
    status: str
    start_ids: tuple[str, ...]
    goal_id: str | None
    path_ids: tuple[str, ...]
    total_cost: float | None
    states_expanded: int
    transitions_evaluated: int
    blocked_transitions: int
    max_states: int
    optimality_scope: str
    action_authority: bool
    receipt_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "status": self.status,
            "start_ids": list(self.start_ids),
            "goal_id": self.goal_id,
            "path_ids": list(self.path_ids),
            "total_cost": self.total_cost,
            "states_expanded": self.states_expanded,
            "transitions_evaluated": self.transitions_evaluated,
            "blocked_transitions": self.blocked_transitions,
            "max_states": self.max_states,
            "optimality_scope": self.optimality_scope,
            "action_authority": self.action_authority,
            "receipt_sha256": self.receipt_sha256,
        }


class RelationalField:
    """Advisory geometry over state changes and pairwise relations.

    Hard constraints decide whether a transition exists in the admissible graph.
    Soft field axes and pairwise relation costs shape the cost of admissible
    transitions. Hard constraints are never traded against soft costs.
    """

    def __init__(
        self,
        *,
        state_id: StateId,
        axes: Sequence[FieldAxisSpec] = (),
        relation_costs: Sequence[RelationCostSpec] = (),
        constraints: Sequence[TransitionConstraintSpec] = (),
    ) -> None:
        self._state_id = state_id
        self._axes = tuple(axes)
        self._relation_costs = tuple(relation_costs)
        self._constraints = tuple(constraints)

        _require_unique_names("axis", [item.name for item in self._axes])
        _require_unique_names("relation cost", [item.name for item in self._relation_costs])
        _require_unique_names("constraint", [item.name for item in self._constraints])

        for item in self._axes:
            _require_nonnegative_finite(item.weight, f"axis {item.name!r} weight")
        for item in self._relation_costs:
            _require_nonnegative_finite(item.weight, f"relation {item.name!r} weight")

    def assess_transition(
        self,
        source: State,
        target: State,
        *,
        base_cost: float = 1.0,
    ) -> TransitionReceipt:
        base = _require_nonnegative_finite(base_cost, "base_cost")
        source_id = _require_state_id(self._state_id(source))
        target_id = _require_state_id(self._state_id(target))
        blocked_by = self._blocked_constraints(source, target)

        axis_changes: list[AxisChange] = []
        relation_costs: list[RelationCost] = []

        if not blocked_by:
            for spec in self._axes:
                try:
                    source_value = _require_finite(
                        spec.measure(source),
                        f"axis {spec.name!r} source value",
                    )
                    target_value = _require_finite(
                        spec.measure(target),
                        f"axis {spec.name!r} target value",
                    )
                except Exception as exc:
                    if isinstance(exc, RelationalFieldContractError):
                        raise
                    raise RelationalFieldContractError(
                        f"axis {spec.name!r} could not be evaluated: {type(exc).__name__}"
                    ) from exc
                delta = abs(target_value - source_value)
                axis_changes.append(
                    AxisChange(
                        name=spec.name,
                        source_value=source_value,
                        target_value=target_value,
                        absolute_delta=delta,
                        weighted_cost=delta * spec.weight,
                    )
                )

            for spec in self._relation_costs:
                try:
                    raw = _require_nonnegative_finite(
                        spec.evaluate(source, target),
                        f"relation {spec.name!r} cost",
                    )
                except Exception as exc:
                    if isinstance(exc, RelationalFieldContractError):
                        raise
                    raise RelationalFieldContractError(
                        f"relation {spec.name!r} could not be evaluated: {type(exc).__name__}"
                    ) from exc
                relation_costs.append(
                    RelationCost(
                        name=spec.name,
                        raw_cost=raw,
                        weighted_cost=raw * spec.weight,
                    )
                )

        total_cost: float | None
        status: str
        if blocked_by:
            total_cost = None
            status = "blocked"
        else:
            total_cost = base + sum(item.weighted_cost for item in axis_changes)
            total_cost += sum(item.weighted_cost for item in relation_costs)
            total_cost = _require_nonnegative_finite(total_cost, "total transition cost")
            status = "admissible"

        payload: dict[str, object] = {
            "schema": "phios.relational_transition_receipt.v0.2",
            "source_id": source_id,
            "target_id": target_id,
            "status": status,
            "blocked_by": list(blocked_by),
            "base_cost": base,
            "axis_changes": [item.to_dict() for item in axis_changes],
            "relation_costs": [item.to_dict() for item in relation_costs],
            "total_cost": total_cost,
            "action_authority": False,
        }
        return TransitionReceipt(
            schema="phios.relational_transition_receipt.v0.2",
            source_id=source_id,
            target_id=target_id,
            status=status,
            blocked_by=blocked_by,
            base_cost=base,
            axis_changes=tuple(axis_changes),
            relation_costs=tuple(relation_costs),
            total_cost=total_cost,
            action_authority=False,
            receipt_sha256=_payload_digest(payload),
        )

    def least_cost_path(
        self,
        starts: Iterable[State],
        *,
        expand: StateExpansion,
        goal: GoalPredicate,
        base_cost: float = 1.0,
        max_states: int = 10_000,
    ) -> FieldPathReceipt:
        base = _require_nonnegative_finite(base_cost, "base_cost")
        if max_states < 1:
            raise ValueError("max_states must be >= 1")

        start_states = sorted(
            list(starts),
            key=lambda state: _require_state_id(self._state_id(state)),
        )
        start_ids = tuple(_require_state_id(self._state_id(state)) for state in start_states)
        if len(set(start_ids)) != len(start_ids):
            raise RelationalFieldContractError("start state IDs must be unique")

        frontier: list[tuple[float, str, State]] = []
        best_cost: dict[str, float] = {}
        parent: dict[str, str | None] = {}
        state_by_id: dict[str, State] = {}

        for state in start_states:
            state_id = _require_state_id(self._state_id(state))
            best_cost[state_id] = 0.0
            parent[state_id] = None
            state_by_id[state_id] = state
            heapq.heappush(frontier, (0.0, state_id, state))

        expanded: set[str] = set()
        transitions_evaluated = 0
        blocked_transitions = 0
        goal_id: str | None = None
        status = "exhausted_over_observed_graph"

        while frontier:
            current_cost, current_id, current = heapq.heappop(frontier)
            if current_id in expanded:
                continue
            if current_cost != best_cost.get(current_id):
                continue

            expanded.add(current_id)

            try:
                is_goal = bool(goal(current))
            except Exception as exc:
                raise RelationalFieldContractError(
                    f"goal predicate could not be evaluated: {type(exc).__name__}"
                ) from exc
            if is_goal:
                goal_id = current_id
                status = "found"
                break

            if len(expanded) >= max_states:
                status = "limit_reached"
                break

            try:
                neighbors = list(expand(current))
            except Exception as exc:
                raise RelationalFieldContractError(
                    f"state expansion failed: {type(exc).__name__}"
                ) from exc
            neighbors.sort(key=lambda state: _require_state_id(self._state_id(state)))

            for neighbor in neighbors:
                neighbor_id = _require_state_id(self._state_id(neighbor))
                known = state_by_id.get(neighbor_id)
                if known is not None and known is not neighbor and known != neighbor:
                    raise RelationalFieldContractError(
                        f"state ID {neighbor_id!r} was reused for a different state"
                    )
                state_by_id.setdefault(neighbor_id, neighbor)

                receipt = self.assess_transition(current, neighbor, base_cost=base)
                transitions_evaluated += 1
                if receipt.status == "blocked":
                    blocked_transitions += 1
                    continue
                if receipt.total_cost is None:
                    raise RelationalFieldContractError(
                        "admissible transition must have a total cost"
                    )

                candidate_cost = current_cost + receipt.total_cost
                previous = best_cost.get(neighbor_id)
                if previous is None or candidate_cost < previous:
                    best_cost[neighbor_id] = candidate_cost
                    parent[neighbor_id] = current_id
                    heapq.heappush(frontier, (candidate_cost, neighbor_id, neighbor))

        path_ids: tuple[str, ...] = ()
        total_cost: float | None = None
        if goal_id is not None:
            path: list[str] = []
            cursor: str | None = goal_id
            while cursor is not None:
                path.append(cursor)
                cursor = parent[cursor]
            path_ids = tuple(reversed(path))
            total_cost = best_cost[goal_id]

        payload: dict[str, object] = {
            "schema": "phios.relational_field_path_receipt.v0.2",
            "status": status,
            "start_ids": list(start_ids),
            "goal_id": goal_id,
            "path_ids": list(path_ids),
            "total_cost": total_cost,
            "states_expanded": len(expanded),
            "transitions_evaluated": transitions_evaluated,
            "blocked_transitions": blocked_transitions,
            "max_states": max_states,
            "optimality_scope": "least_declared_cost_over_observed_graph",
            "action_authority": False,
        }
        return FieldPathReceipt(
            schema="phios.relational_field_path_receipt.v0.2",
            status=status,
            start_ids=start_ids,
            goal_id=goal_id,
            path_ids=path_ids,
            total_cost=total_cost,
            states_expanded=len(expanded),
            transitions_evaluated=transitions_evaluated,
            blocked_transitions=blocked_transitions,
            max_states=max_states,
            optimality_scope="least_declared_cost_over_observed_graph",
            action_authority=False,
            receipt_sha256=_payload_digest(payload),
        )

    def _blocked_constraints(self, source: State, target: State) -> tuple[str, ...]:
        blocked: list[str] = []
        for spec in self._constraints:
            try:
                allowed = bool(spec.predicate(source, target))
            except Exception:
                allowed = False
            if not allowed:
                blocked.append(spec.name)
        return tuple(blocked)


def _require_finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RelationalFieldContractError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise RelationalFieldContractError(f"{label} must be finite")
    return number


def _require_nonnegative_finite(value: object, label: str) -> float:
    number = _require_finite(value, label)
    if number < 0:
        raise RelationalFieldContractError(f"{label} must be non-negative")
    return number


def _require_state_id(value: object) -> str:
    state_id = str(value).strip()
    if not state_id:
        raise RelationalFieldContractError("state_id must be non-empty")
    return state_id


def _require_unique_names(kind: str, names: Sequence[str]) -> None:
    normalized = [name.strip() for name in names]
    if any(not name for name in normalized):
        raise RelationalFieldContractError(f"{kind} names must be non-empty")
    if len(set(normalized)) != len(normalized):
        raise RelationalFieldContractError(f"{kind} names must be unique")


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
        raise RelationalFieldContractError(
            "receipt payload must be canonical JSON"
        ) from exc


def _payload_digest(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_json(dict(payload)).encode("utf-8")).hexdigest()
