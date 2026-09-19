from __future__ import annotations

from dataclasses import replace

import pytest

from phios.core.dynamic_field import (
    DynamicField,
    DynamicFieldLaw,
    FieldEvent,
    FieldVariableRule,
)
from phios.core.field_aware_routing import DynamicCostBinding, FieldAwareRouter
from phios.core.governed_plan_adoption import (
    GovernedPlanAdoptionGate,
    PlanAdoptionContractError,
    PlanAdoptionGrant,
)
from phios.core.governed_replanning import (
    GovernedReplanner,
    ReplanPolicy,
)


def _id(state: dict[str, object]) -> str:
    return str(state["id"])


def _field() -> DynamicField:
    return DynamicField(
        DynamicFieldLaw(
            law_id="adoption-field",
            version="0.6-test",
            variables=(
                FieldVariableRule(
                    name="historical_failure",
                    minimum=0.0,
                    maximum=5.0,
                    initial=0.0,
                    allowed_event_kinds=("failure",),
                    max_abs_delta=2.0,
                ),
            ),
        )
    )


def _states():
    return {
        "A": {"id": "A"},
        "B": {"id": "B"},
        "C": {"id": "C"},
        "D": {"id": "D"},
    }


def _graph():
    return {
        "A": ["B", "C"],
        "B": ["D"],
        "C": ["D"],
        "D": [],
    }


def _stack():
    field = _field()
    router = FieldAwareRouter(
        dynamic_field=field,
        state_id=_id,
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
    replanner = GovernedReplanner(
        router=router,
        policy=ReplanPolicy(
            policy_id="stable-routing",
            minimum_cost_improvement=1.0,
        ),
    )
    return field, router, replanner


def _route(router, field_state, states, graph):
    return router.route(
        field_state,
        [states["A"]],
        expand=lambda state: [states[item] for item in graph[_id(state)]],
        goal=lambda state: _id(state) == "D",
    )


def _replan(field, router, replanner, states, graph):
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
    )
    return previous, receipt


def _grant(plan, replan, disposition):
    return PlanAdoptionGrant(
        grant_id=f"grant-{disposition.lower()}",
        authority_source="operator",
        plan_id=plan.plan_id,
        current_plan_sha256=plan.state_sha256,
        replan_receipt_sha256=replan.receipt_sha256,
        disposition=disposition,
    )


def test_matching_adoption_grant_creates_new_incumbent_plan():
    field, router, replanner = _stack()
    states = _states()
    graph = _graph()
    previous, replan = _replan(
        field, router, replanner, states, graph
    )
    gate = GovernedPlanAdoptionGate()
    plan = gate.initialize_plan(
        plan_id="primary-plan",
        route_receipt=previous,
    )

    next_plan, receipt = gate.apply(
        current_plan=plan,
        replan_receipt=replan,
        requested_disposition="ADOPT",
        grant=_grant(plan, replan, "ADOPT"),
    )

    assert replan.decision == "REPLAN"
    assert receipt.status == "ADOPTED"
    assert receipt.reason == "authorized_replan_adopted"
    assert receipt.grant_scope_valid is True
    assert receipt.plan_changed is True
    assert next_plan.revision == 1
    assert next_plan.path_ids == ("A", "C", "D")
    assert next_plan.source_route_receipt_sha256 == (
        replan.candidate_route_receipt_sha256
    )
    assert next_plan.source_replan_receipt_sha256 == replan.receipt_sha256
    assert next_plan.action_authority is False
    assert next_plan.execution_authority is False
    assert receipt.execution_authority is False


def test_missing_authority_holds_plan_unchanged():
    field, router, replanner = _stack()
    states = _states()
    graph = _graph()
    previous, replan = _replan(
        field, router, replanner, states, graph
    )
    gate = GovernedPlanAdoptionGate()
    plan = gate.initialize_plan(
        plan_id="primary-plan",
        route_receipt=previous,
    )

    next_plan, receipt = gate.apply(
        current_plan=plan,
        replan_receipt=replan,
        requested_disposition="ADOPT",
        grant=None,
    )

    assert next_plan == plan
    assert receipt.status == "HELD"
    assert receipt.reason == "adoption_authority_missing"
    assert receipt.plan_changed is False


def test_mismatched_grant_scope_holds_plan():
    field, router, replanner = _stack()
    states = _states()
    graph = _graph()
    previous, replan = _replan(
        field, router, replanner, states, graph
    )
    gate = GovernedPlanAdoptionGate()
    plan = gate.initialize_plan(
        plan_id="primary-plan",
        route_receipt=previous,
    )
    grant = replace(
        _grant(plan, replan, "ADOPT"),
        current_plan_sha256="f" * 64,
    )

    next_plan, receipt = gate.apply(
        current_plan=plan,
        replan_receipt=replan,
        requested_disposition="ADOPT",
        grant=grant,
    )

    assert next_plan == plan
    assert receipt.status == "HELD"
    assert receipt.reason == "grant_plan_state_scope_mismatch"
    assert receipt.grant_scope_valid is False


def test_authorized_rejection_preserves_plan():
    field, router, replanner = _stack()
    states = _states()
    graph = _graph()
    previous, replan = _replan(
        field, router, replanner, states, graph
    )
    gate = GovernedPlanAdoptionGate()
    plan = gate.initialize_plan(
        plan_id="primary-plan",
        route_receipt=previous,
    )

    next_plan, receipt = gate.apply(
        current_plan=plan,
        replan_receipt=replan,
        requested_disposition="REJECT",
        grant=_grant(plan, replan, "REJECT"),
    )

    assert next_plan == plan
    assert receipt.status == "REJECTED"
    assert receipt.reason == "authorized_rejection"
    assert receipt.grant_scope_valid is True
    assert receipt.plan_changed is False


def test_authorized_hold_preserves_plan():
    field, router, replanner = _stack()
    states = _states()
    graph = _graph()
    previous, replan = _replan(
        field, router, replanner, states, graph
    )
    gate = GovernedPlanAdoptionGate()
    plan = gate.initialize_plan(
        plan_id="primary-plan",
        route_receipt=previous,
    )

    next_plan, receipt = gate.apply(
        current_plan=plan,
        replan_receipt=replan,
        requested_disposition="HOLD",
        grant=_grant(plan, replan, "HOLD"),
    )

    assert next_plan == plan
    assert receipt.status == "HELD"
    assert receipt.reason == "authorized_hold"
    assert receipt.grant_scope_valid is True


def test_keep_replan_decision_cannot_be_adopted():
    field, router, replanner = _stack()
    states = _states()
    graph = _graph()
    initial = field.initialize()
    previous = _route(router, initial, states, graph)
    keep = replanner.assess(
        previous_route=previous,
        current_field_state=initial,
        incumbent_path=[states["A"], states["B"], states["D"]],
        starts=[states["A"]],
        expand=lambda state: [states[item] for item in graph[_id(state)]],
        goal=lambda state: _id(state) == "D",
    )
    gate = GovernedPlanAdoptionGate()
    plan = gate.initialize_plan(
        plan_id="primary-plan",
        route_receipt=previous,
    )

    next_plan, receipt = gate.apply(
        current_plan=plan,
        replan_receipt=keep,
        requested_disposition="ADOPT",
        grant=_grant(plan, keep, "ADOPT"),
    )

    assert keep.decision == "KEEP"
    assert next_plan == plan
    assert receipt.status == "HELD"
    assert receipt.reason == "replan_decision_not_adoptable"


def test_stale_replan_cannot_replace_newer_plan_state():
    field, router, replanner = _stack()
    states = _states()
    graph = _graph()
    previous, replan = _replan(
        field, router, replanner, states, graph
    )
    gate = GovernedPlanAdoptionGate()
    plan = gate.initialize_plan(
        plan_id="primary-plan",
        route_receipt=previous,
    )
    adopted, _ = gate.apply(
        current_plan=plan,
        replan_receipt=replan,
        requested_disposition="ADOPT",
        grant=_grant(plan, replan, "ADOPT"),
    )

    next_plan, receipt = gate.apply(
        current_plan=adopted,
        replan_receipt=replan,
        requested_disposition="ADOPT",
        grant=_grant(adopted, replan, "ADOPT"),
    )

    assert next_plan == adopted
    assert receipt.status == "HELD"
    assert receipt.reason == "stale_replan_receipt"


def test_tampered_replan_receipt_is_rejected():
    field, router, replanner = _stack()
    states = _states()
    graph = _graph()
    previous, replan = _replan(
        field, router, replanner, states, graph
    )
    gate = GovernedPlanAdoptionGate()
    plan = gate.initialize_plan(
        plan_id="primary-plan",
        route_receipt=previous,
    )
    tampered = replace(replan, candidate_path_ids=("A", "B", "D"))

    with pytest.raises(PlanAdoptionContractError):
        gate.apply(
            current_plan=plan,
            replan_receipt=tampered,
            requested_disposition="ADOPT",
            grant=_grant(plan, replan, "ADOPT"),
        )


def test_tampered_plan_state_is_rejected():
    field, router, replanner = _stack()
    states = _states()
    graph = _graph()
    previous, replan = _replan(
        field, router, replanner, states, graph
    )
    gate = GovernedPlanAdoptionGate()
    plan = gate.initialize_plan(
        plan_id="primary-plan",
        route_receipt=previous,
    )
    tampered = replace(plan, path_ids=("A", "C", "D"))

    with pytest.raises(PlanAdoptionContractError):
        gate.apply(
            current_plan=tampered,
            replan_receipt=replan,
            requested_disposition="ADOPT",
            grant=None,
        )


def test_adoption_receipt_is_deterministic():
    field, router, replanner = _stack()
    states = _states()
    graph = _graph()
    previous, replan = _replan(
        field, router, replanner, states, graph
    )
    gate = GovernedPlanAdoptionGate()
    plan = gate.initialize_plan(
        plan_id="primary-plan",
        route_receipt=previous,
    )
    grant = _grant(plan, replan, "ADOPT")

    def run():
        return gate.apply(
            current_plan=plan,
            replan_receipt=replan,
            requested_disposition="ADOPT",
            grant=grant,
        )

    first_plan, first_receipt = run()
    second_plan, second_receipt = run()

    assert first_plan.to_dict() == second_plan.to_dict()
    assert first_receipt.to_dict() == second_receipt.to_dict()
