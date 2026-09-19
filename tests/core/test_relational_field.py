from __future__ import annotations

import pytest

from phios.core.relational_field import (
    FieldAxisSpec,
    RelationCostSpec,
    RelationalField,
    RelationalFieldContractError,
    TransitionConstraintSpec,
)


def _id(state: dict[str, object]) -> str:
    return str(state["id"])


def test_transition_cost_combines_field_change_and_pairwise_relation_cost():
    field = RelationalField(
        state_id=_id,
        axes=(
            FieldAxisSpec(
                "uncertainty",
                lambda state: float(state["uncertainty"]),
                weight=2.0,
            ),
        ),
        relation_costs=(
            RelationCostSpec(
                "resource_pressure",
                lambda source, target: float(target["resource"]),
                weight=0.5,
            ),
        ),
    )

    source = {"id": "A", "uncertainty": 0.8, "resource": 0.0}
    target = {"id": "B", "uncertainty": 0.2, "resource": 4.0}

    receipt = field.assess_transition(source, target, base_cost=1.0)

    assert receipt.status == "admissible"
    assert receipt.axis_changes[0].absolute_delta == pytest.approx(0.6)
    assert receipt.axis_changes[0].weighted_cost == pytest.approx(1.2)
    assert receipt.relation_costs[0].weighted_cost == pytest.approx(2.0)
    assert receipt.total_cost == pytest.approx(4.2)
    assert receipt.action_authority is False


def test_hard_constraint_cannot_be_outvoted_by_lower_soft_cost():
    field = RelationalField(
        state_id=_id,
        axes=(
            FieldAxisSpec("resource", lambda state: float(state["resource"])),
        ),
        constraints=(
            TransitionConstraintSpec(
                "authority_granted",
                lambda source, target: bool(target["authorized"]),
            ),
        ),
    )

    source = {"id": "A", "resource": 100.0, "authorized": True}
    cheap_but_forbidden = {"id": "B", "resource": 100.0, "authorized": False}

    receipt = field.assess_transition(source, cheap_but_forbidden, base_cost=0.0)

    assert receipt.status == "blocked"
    assert receipt.blocked_by == ("authority_granted",)
    assert receipt.total_cost is None
    assert receipt.action_authority is False


def test_constraint_exception_fails_closed():
    field = RelationalField(
        state_id=_id,
        constraints=(
            TransitionConstraintSpec(
                "fragile_gate",
                lambda source, target: (_ for _ in ()).throw(RuntimeError("boom")),
            ),
        ),
    )

    receipt = field.assess_transition({"id": "A"}, {"id": "B"})

    assert receipt.status == "blocked"
    assert receipt.blocked_by == ("fragile_gate",)


def test_least_cost_path_uses_relational_geometry_not_fewest_hops():
    states = {
        "A": {"id": "A", "x": 0.0},
        "B": {"id": "B", "x": 10.0},
        "C": {"id": "C", "x": 1.0},
        "D": {"id": "D", "x": 2.0},
    }
    graph = {
        "A": ["B", "C"],
        "B": ["D"],
        "C": ["D"],
        "D": [],
    }
    field = RelationalField(
        state_id=_id,
        axes=(FieldAxisSpec("distance", lambda state: float(state["x"])),),
    )

    receipt = field.least_cost_path(
        [states["A"]],
        expand=lambda state: [states[item] for item in graph[_id(state)]],
        goal=lambda state: _id(state) == "D",
        base_cost=0.0,
    )

    assert receipt.status == "found"
    assert receipt.path_ids == ("A", "C", "D")
    assert receipt.total_cost == pytest.approx(2.0)
    assert receipt.optimality_scope == "least_declared_cost_over_observed_graph"
    assert receipt.action_authority is False


def test_blocked_transition_is_removed_from_path_graph():
    states = {
        "A": {"id": "A", "authorized": True},
        "B": {"id": "B", "authorized": False},
        "C": {"id": "C", "authorized": True},
    }
    graph = {
        "A": ["B", "C"],
        "B": [],
        "C": [],
    }
    field = RelationalField(
        state_id=_id,
        constraints=(
            TransitionConstraintSpec(
                "authority_granted",
                lambda source, target: bool(target["authorized"]),
            ),
        ),
    )

    receipt = field.least_cost_path(
        [states["A"]],
        expand=lambda state: [states[item] for item in graph[_id(state)]],
        goal=lambda state: _id(state) == "C",
        base_cost=1.0,
    )

    assert receipt.status == "found"
    assert receipt.path_ids == ("A", "C")
    assert receipt.blocked_transitions == 1


def test_path_receipt_is_deterministic_across_neighbor_order():
    states = {
        "A": {"id": "A", "x": 0.0},
        "B": {"id": "B", "x": 1.0},
        "C": {"id": "C", "x": 1.0},
        "D": {"id": "D", "x": 2.0},
    }
    field = RelationalField(
        state_id=_id,
        axes=(FieldAxisSpec("distance", lambda state: float(state["x"])),),
    )

    def run(order: list[str]):
        graph = {
            "A": order,
            "B": ["D"],
            "C": ["D"],
            "D": [],
        }
        return field.least_cost_path(
            [states["A"]],
            expand=lambda state: [states[item] for item in graph[_id(state)]],
            goal=lambda state: _id(state) == "D",
            base_cost=0.0,
        )

    first = run(["C", "B"])
    second = run(["B", "C"])

    assert first.to_dict() == second.to_dict()
    assert first.path_ids == ("A", "B", "D")


def test_negative_weights_are_rejected():
    with pytest.raises(RelationalFieldContractError):
        RelationalField(
            state_id=_id,
            axes=(FieldAxisSpec("bad", lambda state: 0.0, weight=-1.0),),
        )
