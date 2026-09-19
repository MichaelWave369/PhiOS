from __future__ import annotations

from dataclasses import replace

import pytest

from phios.core.dynamic_field import (
    DynamicField,
    DynamicFieldLaw,
    FieldEvent,
    FieldVariableRule,
)
from phios.core.field_aware_routing import (
    DynamicCostBinding,
    FieldAwareRouter,
    FieldAwareRoutingContractError,
)
from phios.core.relational_field import TransitionConstraintSpec


def _id(state: dict[str, object]) -> str:
    return str(state["id"])


def _field() -> DynamicField:
    return DynamicField(
        DynamicFieldLaw(
            law_id="routing-field",
            version="0.4-test",
            variables=(
                FieldVariableRule(
                    name="historical_failure",
                    minimum=0.0,
                    maximum=5.0,
                    initial=0.0,
                    allowed_event_kinds=("failure", "recovery"),
                    max_abs_delta=2.0,
                ),
                FieldVariableRule(
                    name="resource_pressure",
                    minimum=0.0,
                    maximum=1.0,
                    initial=0.2,
                    allowed_event_kinds=("resource",),
                    max_abs_delta=0.5,
                ),
            ),
        )
    )


def _states():
    return {
        "A": {"id": "A", "authorized": True},
        "B": {"id": "B", "authorized": True},
        "C": {"id": "C", "authorized": True},
        "D": {"id": "D", "authorized": True},
    }


def _graph():
    return {
        "A": ["B", "C"],
        "B": ["D"],
        "C": ["D"],
        "D": [],
    }


def test_live_failure_field_can_change_preferred_route():
    field = _field()
    router = FieldAwareRouter(
        dynamic_field=field,
        state_id=_id,
        dynamic_bindings=(
            DynamicCostBinding(
                name="failure_exposure",
                field_variable="historical_failure",
                evaluate=lambda source, target: 10.0 if _id(target) == "B" else 0.0,
            ),
        ),
    )
    states = _states()
    graph = _graph()

    initial = field.initialize()
    before = router.route(
        initial,
        [states["A"]],
        expand=lambda state: [states[item] for item in graph[_id(state)]],
        goal=lambda state: _id(state) == "D",
        base_cost=1.0,
    )

    changed, update = field.apply_event(
        initial,
        FieldEvent(
            event_id="failure-001",
            kind="failure",
            deltas={"historical_failure": 1.0},
            source_label="builder-run",
        ),
    )
    after = router.route(
        changed,
        [states["A"]],
        expand=lambda state: [states[item] for item in graph[_id(state)]],
        goal=lambda state: _id(state) == "D",
        base_cost=1.0,
    )

    assert update.status == "applied"
    assert before.path_ids == ("A", "B", "D")
    assert after.path_ids == ("A", "C", "D")
    assert before.field_state_sha256 != after.field_state_sha256
    assert after.action_authority is False


def test_hard_constraint_remains_absolute_under_dynamic_routing():
    field = _field()
    router = FieldAwareRouter(
        dynamic_field=field,
        state_id=_id,
        constraints=(
            TransitionConstraintSpec(
                "authority_granted",
                lambda source, target: bool(target["authorized"]),
            ),
        ),
        dynamic_bindings=(
            DynamicCostBinding(
                name="resource_exposure",
                field_variable="resource_pressure",
                evaluate=lambda source, target: 0.0,
            ),
        ),
    )
    states = _states()
    states["B"]["authorized"] = False
    graph = _graph()

    receipt = router.route(
        field.initialize(),
        [states["A"]],
        expand=lambda state: [states[item] for item in graph[_id(state)]],
        goal=lambda state: _id(state) == "D",
    )

    assert receipt.path_ids == ("A", "C", "D")
    assert "B" not in receipt.path_ids


def test_route_receipt_binds_exact_field_snapshot_and_is_deterministic():
    field = _field()
    router = FieldAwareRouter(
        dynamic_field=field,
        state_id=_id,
        dynamic_bindings=(
            DynamicCostBinding(
                name="failure_exposure",
                field_variable="historical_failure",
                evaluate=lambda source, target: 1.0,
                scale=2.0,
            ),
        ),
    )
    states = _states()
    graph = _graph()
    state = field.initialize()

    def run():
        return router.route(
            state,
            [states["A"]],
            expand=lambda item: [states[key] for key in graph[_id(item)]],
            goal=lambda item: _id(item) == "D",
        )

    first = run()
    second = run()

    assert first.to_dict() == second.to_dict()
    assert first.field_state_sha256 == state.state_sha256
    assert first.bindings[0].field_value == pytest.approx(0.0)
    assert (
        first.optimality_scope
        == "least_declared_cost_over_observed_graph_at_exact_field_snapshot"
    )


def test_tampered_dynamic_state_is_rejected_before_routing():
    field = _field()
    router = FieldAwareRouter(
        dynamic_field=field,
        state_id=_id,
    )
    state = replace(field.initialize(), state_sha256="f" * 64)

    with pytest.raises(Exception):
        router.route(
            state,
            [{"id": "A"}],
            expand=lambda item: [],
            goal=lambda item: False,
        )


def test_binding_unknown_variable_is_rejected():
    field = _field()

    with pytest.raises(FieldAwareRoutingContractError):
        FieldAwareRouter(
            dynamic_field=field,
            state_id=_id,
            dynamic_bindings=(
                DynamicCostBinding(
                    name="bad",
                    field_variable="not_declared",
                    evaluate=lambda source, target: 1.0,
                ),
            ),
        )


def test_binding_negative_domain_variable_is_rejected():
    field = DynamicField(
        DynamicFieldLaw(
            law_id="negative-field",
            version="test",
            variables=(
                FieldVariableRule(
                    name="signed_signal",
                    minimum=-1.0,
                    maximum=1.0,
                    initial=0.0,
                    allowed_event_kinds=("signal",),
                    max_abs_delta=0.5,
                ),
            ),
        )
    )

    with pytest.raises(FieldAwareRoutingContractError):
        FieldAwareRouter(
            dynamic_field=field,
            state_id=_id,
            dynamic_bindings=(
                DynamicCostBinding(
                    name="signed",
                    field_variable="signed_signal",
                    evaluate=lambda source, target: 1.0,
                ),
            ),
        )


def test_negative_transition_susceptibility_is_rejected():
    field = _field()
    router = FieldAwareRouter(
        dynamic_field=field,
        state_id=_id,
        dynamic_bindings=(
            DynamicCostBinding(
                name="bad_susceptibility",
                field_variable="resource_pressure",
                evaluate=lambda source, target: -1.0,
            ),
        ),
    )

    with pytest.raises(FieldAwareRoutingContractError):
        router.route(
            field.initialize(),
            [{"id": "A"},],
            expand=lambda item: [{"id": "B"}] if _id(item) == "A" else [],
            goal=lambda item: _id(item) == "B",
        )
