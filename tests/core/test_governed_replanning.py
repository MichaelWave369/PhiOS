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
)
from phios.core.governed_replanning import (
    GovernedReplanner,
    GovernedReplanningContractError,
    ReplanPolicy,
)
from phios.core.relational_field import TransitionConstraintSpec


def _id(state: dict[str, object]) -> str:
    return str(state["id"])


def _field() -> DynamicField:
    return DynamicField(
        DynamicFieldLaw(
            law_id="replan-field",
            version="0.5-test",
            variables=(
                FieldVariableRule(
                    name="historical_failure",
                    minimum=0.0,
                    maximum=5.0,
                    initial=0.0,
                    allowed_event_kinds=("failure", "recovery"),
                    max_abs_delta=2.0,
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


def _router(field: DynamicField, *, with_authority_gate: bool = False):
    constraints = ()
    if with_authority_gate:
        constraints = (
            TransitionConstraintSpec(
                "authority_granted",
                lambda source, target: bool(target["authorized"]),
            ),
        )
    return FieldAwareRouter(
        dynamic_field=field,
        state_id=_id,
        constraints=constraints,
        dynamic_bindings=(
            DynamicCostBinding(
                name="failure_exposure",
                field_variable="historical_failure",
                evaluate=lambda source, target: (
                    10.0 if _id(target) == "B" else 0.0
                ),
            ),
        ),
    )


def _route(router: FieldAwareRouter, field_state, states, graph):
    return router.route(
        field_state,
        [states["A"]],
        expand=lambda state: [states[item] for item in graph[_id(state)]],
        goal=lambda state: _id(state) == "D",
        base_cost=1.0,
    )


def test_replan_when_current_snapshot_materially_favors_new_route():
    field = _field()
    router = _router(field)
    replanner = GovernedReplanner(
        router=router,
        policy=ReplanPolicy(
            policy_id="stable-routing",
            minimum_cost_improvement=1.0,
        ),
    )
    states = _states()
    graph = _graph()

    initial = field.initialize()
    previous = _route(router, initial, states, graph)
    current, _ = field.apply_event(
        initial,
        FieldEvent(
            event_id="failure-001",
            kind="failure",
            deltas={"historical_failure": 1.0},
            source_label="builder",
        ),
    )

    receipt = replanner.assess(
        previous_route=previous,
        current_field_state=current,
        incumbent_path=[states["A"], states["B"], states["D"]],
        starts=[states["A"]],
        expand=lambda state: [states[item] for item in graph[_id(state)]],
        goal=lambda state: _id(state) == "D",
        base_cost=1.0,
    )

    assert previous.path_ids == ("A", "B", "D")
    assert receipt.candidate_path_ids == ("A", "C", "D")
    assert receipt.incumbent_current_cost == pytest.approx(12.0)
    assert receipt.candidate_current_cost == pytest.approx(2.0)
    assert receipt.cost_improvement == pytest.approx(10.0)
    assert receipt.decision == "REPLAN"
    assert receipt.reason == "cost_improvement_exceeds_hysteresis"
    assert receipt.action_authority is False


def test_hysteresis_keeps_incumbent_for_small_improvement():
    field = _field()
    router = _router(field)
    replanner = GovernedReplanner(
        router=router,
        policy=ReplanPolicy(
            policy_id="stable-routing",
            minimum_cost_improvement=1.0,
        ),
    )
    states = _states()
    graph = _graph()

    initial = field.initialize()
    previous = _route(router, initial, states, graph)
    current, _ = field.apply_event(
        initial,
        FieldEvent(
            event_id="failure-small",
            kind="failure",
            deltas={"historical_failure": 0.05},
            source_label="builder",
        ),
    )

    receipt = replanner.assess(
        previous_route=previous,
        current_field_state=current,
        incumbent_path=[states["A"], states["B"], states["D"]],
        starts=[states["A"]],
        expand=lambda state: [states[item] for item in graph[_id(state)]],
        goal=lambda state: _id(state) == "D",
    )

    assert receipt.candidate_path_ids == ("A", "C", "D")
    assert receipt.cost_improvement == pytest.approx(0.5)
    assert receipt.decision == "KEEP"
    assert receipt.reason == "hysteresis_threshold_not_exceeded"


def test_same_route_is_kept():
    field = _field()
    router = _router(field)
    replanner = GovernedReplanner(
        router=router,
        policy=ReplanPolicy(
            policy_id="stable-routing",
            minimum_cost_improvement=0.0,
        ),
    )
    states = _states()
    graph = _graph()
    initial = field.initialize()
    previous = _route(router, initial, states, graph)

    receipt = replanner.assess(
        previous_route=previous,
        current_field_state=initial,
        incumbent_path=[states["A"], states["B"], states["D"]],
        starts=[states["A"]],
        expand=lambda state: [states[item] for item in graph[_id(state)]],
        goal=lambda state: _id(state) == "D",
    )

    assert receipt.decision == "KEEP"
    assert receipt.reason == "same_route_remains_preferred"
    assert receipt.route_changed is False


def test_blocked_incumbent_forces_replan_when_candidate_exists():
    field = _field()
    router = _router(field, with_authority_gate=True)
    replanner = GovernedReplanner(
        router=router,
        policy=ReplanPolicy(
            policy_id="stable-routing",
            minimum_cost_improvement=999.0,
        ),
    )
    states = _states()
    graph = _graph()
    initial = field.initialize()
    previous = _route(router, initial, states, graph)

    states["B"]["authorized"] = False

    receipt = replanner.assess(
        previous_route=previous,
        current_field_state=initial,
        incumbent_path=[states["A"], states["B"], states["D"]],
        starts=[states["A"]],
        expand=lambda state: [states[item] for item in graph[_id(state)]],
        goal=lambda state: _id(state) == "D",
    )

    assert receipt.incumbent_status == "blocked"
    assert receipt.candidate_path_ids == ("A", "C", "D")
    assert receipt.decision == "REPLAN"
    assert receipt.reason == "incumbent_path_blocked"


def test_unresolved_candidate_does_not_claim_keep_or_replan():
    field = _field()
    router = _router(field)
    replanner = GovernedReplanner(
        router=router,
        policy=ReplanPolicy(
            policy_id="stable-routing",
            minimum_cost_improvement=1.0,
        ),
    )
    states = _states()
    graph = _graph()
    initial = field.initialize()
    previous = _route(router, initial, states, graph)

    receipt = replanner.assess(
        previous_route=previous,
        current_field_state=initial,
        incumbent_path=[states["A"], states["B"], states["D"]],
        starts=[states["A"]],
        expand=lambda state: [],
        goal=lambda state: _id(state) == "D",
    )

    assert receipt.candidate_status == "exhausted_over_observed_graph"
    assert receipt.decision == "UNRESOLVED"
    assert receipt.reason == "candidate_route_unresolved"


def test_previous_route_tampering_is_rejected():
    field = _field()
    router = _router(field)
    replanner = GovernedReplanner(
        router=router,
        policy=ReplanPolicy(
            policy_id="stable-routing",
            minimum_cost_improvement=1.0,
        ),
    )
    states = _states()
    graph = _graph()
    initial = field.initialize()
    previous = _route(router, initial, states, graph)
    tampered = replace(previous, path_ids=("A", "C", "D"))

    with pytest.raises(GovernedReplanningContractError):
        replanner.assess(
            previous_route=tampered,
            current_field_state=initial,
            incumbent_path=[states["A"], states["B"], states["D"]],
            starts=[states["A"]],
            expand=lambda state: [states[item] for item in graph[_id(state)]],
            goal=lambda state: _id(state) == "D",
        )


def test_field_revision_regression_is_rejected():
    field = _field()
    router = _router(field)
    replanner = GovernedReplanner(
        router=router,
        policy=ReplanPolicy(
            policy_id="stable-routing",
            minimum_cost_improvement=1.0,
        ),
    )
    states = _states()
    graph = _graph()
    initial = field.initialize()
    newer, _ = field.apply_event(
        initial,
        FieldEvent(
            event_id="failure-001",
            kind="failure",
            deltas={"historical_failure": 1.0},
            source_label="builder",
        ),
    )
    previous = _route(router, newer, states, graph)

    with pytest.raises(GovernedReplanningContractError):
        replanner.assess(
            previous_route=previous,
            current_field_state=initial,
            incumbent_path=[states[item] for item in previous.path_ids],
            starts=[states["A"]],
            expand=lambda state: [states[item] for item in graph[_id(state)]],
            goal=lambda state: _id(state) == "D",
        )


def test_policy_threshold_must_be_nonnegative():
    field = _field()
    router = _router(field)

    with pytest.raises(GovernedReplanningContractError):
        GovernedReplanner(
            router=router,
            policy=ReplanPolicy(
                policy_id="bad",
                minimum_cost_improvement=-1.0,
            ),
        )


def test_replan_receipt_is_deterministic():
    field = _field()
    router = _router(field)
    replanner = GovernedReplanner(
        router=router,
        policy=ReplanPolicy(
            policy_id="stable-routing",
            minimum_cost_improvement=1.0,
        ),
    )
    states = _states()
    graph = _graph()
    initial = field.initialize()
    previous = _route(router, initial, states, graph)

    def run():
        return replanner.assess(
            previous_route=previous,
            current_field_state=initial,
            incumbent_path=[states["A"], states["B"], states["D"]],
            starts=[states["A"]],
            expand=lambda state: [states[item] for item in graph[_id(state)]],
            goal=lambda state: _id(state) == "D",
        )

    assert run().to_dict() == run().to_dict()
