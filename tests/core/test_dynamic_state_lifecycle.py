from dataclasses import replace

import pytest

from phios.core.dynamic_field import (
    DynamicField,
    DynamicFieldLaw,
    FieldEvent,
    FieldVariableRule,
)
from phios.core.dynamic_state import (
    DynamicStateContractError,
    DynamicStateController,
    DynamicStateDecayRule,
    DynamicStatePolicy,
)
from phios.core.field_aware_routing import (
    DynamicCostBinding,
    FieldAwareRouter,
    FieldAwareRoutingContractError,
)


def _field() -> DynamicField:
    return DynamicField(
        DynamicFieldLaw(
            law_id="temporal-field",
            version="0.8-test",
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
                    name="uncertainty",
                    minimum=0.0,
                    maximum=1.0,
                    initial=0.8,
                    allowed_event_kinds=("evidence", "contradiction"),
                    max_abs_delta=0.4,
                ),
            ),
        )
    )


def _policy() -> DynamicStatePolicy:
    return DynamicStatePolicy(
        policy_id="advisory-decay",
        version="0.1",
        max_state_age_seconds=20.0,
        rules=(
            DynamicStateDecayRule(
                field_variable="historical_failure",
                grace_seconds=0.0,
                attenuation_rate_per_second=0.1,
            ),
            DynamicStateDecayRule(
                field_variable="uncertainty",
                grace_seconds=5.0,
                attenuation_rate_per_second=0.05,
            ),
        ),
    )


def _failed_state(field: DynamicField):
    initial = field.initialize()
    failed, receipt = field.apply_event(
        initial,
        FieldEvent(
            event_id="failure-001",
            kind="failure",
            deltas={"historical_failure": 1.0},
            source_label="builder",
            evidence_sha256="a" * 64,
        ),
    )
    assert receipt.status == "applied"
    return failed


def test_dynamic_state_attenuates_toward_law_initial_values() -> None:
    field = _field()
    state = _failed_state(field)
    controller = DynamicStateController(
        dynamic_field=field,
        policy=_policy(),
    )

    result = controller.evaluate(
        state,
        activated_at_utc="2026-09-21T20:00:00+00:00",
        observed_at_utc="2026-09-21T20:00:05+00:00",
    )

    effective = result.require_consumable_state()
    assert result.receipt.status == "ATTENUATED"
    assert result.receipt.age_seconds == pytest.approx(5.0)
    assert effective.value("historical_failure") == pytest.approx(0.5)
    assert effective.value("uncertainty") == pytest.approx(0.8)
    assert effective.revision == state.revision + 1
    assert effective.applied_event_ids[-1].startswith("dynamic-state:")
    assert result.receipt.governing_law_mutated is False
    assert result.receipt.operational_authority is False
    assert result.receipt.action_authority is False
    assert result.receipt.execution_authority is False


def test_dynamic_state_can_move_both_sides_toward_initial_baseline() -> None:
    field = _field()
    initial = field.initialize()
    changed, _ = field.apply_event(
        initial,
        FieldEvent(
            event_id="evidence-001",
            kind="evidence",
            deltas={"uncertainty": -0.3},
            source_label="reality",
        ),
    )
    controller = DynamicStateController(
        dynamic_field=field,
        policy=_policy(),
    )

    result = controller.evaluate(
        changed,
        activated_at_utc="2026-09-21T20:00:00+00:00",
        observed_at_utc="2026-09-21T20:00:09+00:00",
    )

    assert result.require_consumable_state().value("uncertainty") == pytest.approx(
        0.7
    )


def test_within_grace_can_remain_active_without_new_field_revision() -> None:
    field = _field()
    initial = field.initialize()
    changed, _ = field.apply_event(
        initial,
        FieldEvent(
            event_id="evidence-001",
            kind="evidence",
            deltas={"uncertainty": -0.2},
            source_label="reality",
        ),
    )
    policy = DynamicStatePolicy(
        policy_id="grace-test",
        version="0.1",
        max_state_age_seconds=20.0,
        rules=(
            DynamicStateDecayRule(
                field_variable="historical_failure",
                grace_seconds=10.0,
                attenuation_rate_per_second=0.1,
            ),
            DynamicStateDecayRule(
                field_variable="uncertainty",
                grace_seconds=10.0,
                attenuation_rate_per_second=0.1,
            ),
        ),
    )
    controller = DynamicStateController(dynamic_field=field, policy=policy)

    result = controller.evaluate(
        changed,
        activated_at_utc="2026-09-21T20:00:00+00:00",
        observed_at_utc="2026-09-21T20:00:05+00:00",
    )

    assert result.receipt.status == "ACTIVE"
    assert result.effective_state == changed
    assert result.receipt.transition_id is None
    assert result.receipt.transition_sha256 is None


def test_max_age_terminates_state_instead_of_clamping_it() -> None:
    field = _field()
    state = _failed_state(field)
    controller = DynamicStateController(
        dynamic_field=field,
        policy=_policy(),
    )

    result = controller.evaluate(
        state,
        activated_at_utc="2026-09-21T20:00:00+00:00",
        observed_at_utc="2026-09-21T20:00:20+00:00",
    )

    assert result.receipt.status == "TERMINATED"
    assert result.receipt.reason == "max_state_age_reached"
    assert result.receipt.state_consumable is False
    assert result.receipt.terminated is True
    assert result.effective_state is None
    with pytest.raises(DynamicStateContractError, match="terminated"):
        result.require_consumable_state()


def test_lifecycle_derived_state_cannot_reset_its_own_clock() -> None:
    field = _field()
    state = _failed_state(field)
    controller = DynamicStateController(
        dynamic_field=field,
        policy=_policy(),
    )
    first = controller.evaluate(
        state,
        activated_at_utc="2026-09-21T20:00:00+00:00",
        observed_at_utc="2026-09-21T20:00:05+00:00",
    )
    derived = first.require_consumable_state()

    with pytest.raises(DynamicStateContractError, match="fresh external field event"):
        controller.evaluate(
            derived,
            activated_at_utc="2026-09-21T20:00:05+00:00",
            observed_at_utc="2026-09-21T20:00:06+00:00",
        )


def test_fresh_external_event_can_create_a_new_temporal_anchor() -> None:
    field = _field()
    state = _failed_state(field)
    controller = DynamicStateController(
        dynamic_field=field,
        policy=_policy(),
    )
    decayed = controller.evaluate(
        state,
        activated_at_utc="2026-09-21T20:00:00+00:00",
        observed_at_utc="2026-09-21T20:00:05+00:00",
    ).require_consumable_state()
    refreshed, update = field.apply_event(
        decayed,
        FieldEvent(
            event_id="failure-002",
            kind="failure",
            deltas={"historical_failure": 0.25},
            source_label="new-builder-observation",
        ),
    )
    assert update.status == "applied"

    result = controller.evaluate(
        refreshed,
        activated_at_utc="2026-09-21T20:00:06+00:00",
        observed_at_utc="2026-09-21T20:00:07+00:00",
    )

    assert result.receipt.anchor_event_id == "failure-002"
    assert result.receipt.status == "ATTENUATED"


def test_policy_must_cover_every_field_variable() -> None:
    field = _field()
    incomplete = DynamicStatePolicy(
        policy_id="bad",
        version="0.1",
        max_state_age_seconds=10.0,
        rules=(
            DynamicStateDecayRule(
                field_variable="historical_failure",
                grace_seconds=0.0,
                attenuation_rate_per_second=0.1,
            ),
        ),
    )

    with pytest.raises(DynamicStateContractError, match="cover every"):
        DynamicStateController(dynamic_field=field, policy=incomplete)


def test_same_temporal_evaluation_is_deterministic() -> None:
    field = _field()
    state = _failed_state(field)
    controller = DynamicStateController(
        dynamic_field=field,
        policy=_policy(),
    )

    def run():
        result = controller.evaluate(
            state,
            activated_at_utc="2026-09-21T20:00:00Z",
            observed_at_utc="2026-09-21T20:00:05Z",
        )
        return (
            result.receipt.to_dict(),
            result.require_consumable_state().to_dict(),
        )

    assert run() == run()


def test_tampered_dynamic_state_receipt_is_rejected_at_consumption() -> None:
    field = _field()
    state = _failed_state(field)
    controller = DynamicStateController(
        dynamic_field=field,
        policy=_policy(),
    )
    result = controller.evaluate(
        state,
        activated_at_utc="2026-09-21T20:00:00+00:00",
        observed_at_utc="2026-09-21T20:00:05+00:00",
    )
    forged = replace(
        result,
        receipt=replace(result.receipt, age_seconds=1.0),
    )

    with pytest.raises(DynamicStateContractError, match="hash"):
        forged.require_consumable_state()


def _id(state: dict[str, object]) -> str:
    return str(state["id"])


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


def _hardened_router(
    field: DynamicField,
    controller: DynamicStateController,
) -> FieldAwareRouter:
    return FieldAwareRouter(
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
        require_dynamic_state_receipt=True,
        expected_dynamic_state_policy_sha256=controller.policy.policy_sha256,
    )


def test_hardened_router_rejects_raw_unreceipted_dynamic_state() -> None:
    field = _field()
    controller = DynamicStateController(
        dynamic_field=field,
        policy=_policy(),
    )
    router = _hardened_router(field, controller)
    states = _states()
    graph = _graph()

    with pytest.raises(FieldAwareRoutingContractError, match="requires"):
        router.route(
            _failed_state(field),
            [states["A"]],
            expand=lambda item: [states[key] for key in graph[_id(item)]],
            goal=lambda item: _id(item) == "D",
        )


def test_receipted_decay_changes_routing_pressure_and_is_bound_to_route() -> None:
    field = _field()
    source = _failed_state(field)
    controller = DynamicStateController(
        dynamic_field=field,
        policy=_policy(),
    )
    router = _hardened_router(field, controller)
    states = _states()
    graph = _graph()

    early = controller.evaluate(
        source,
        activated_at_utc="2026-09-21T20:00:00+00:00",
        observed_at_utc="2026-09-21T20:00:01+00:00",
    )
    late = controller.evaluate(
        source,
        activated_at_utc="2026-09-21T20:00:00+00:00",
        observed_at_utc="2026-09-21T20:00:10+00:00",
    )

    early_route = router.route(
        early,
        [states["A"]],
        expand=lambda item: [states[key] for key in graph[_id(item)]],
        goal=lambda item: _id(item) == "D",
    )
    late_route = router.route(
        late,
        [states["A"]],
        expand=lambda item: [states[key] for key in graph[_id(item)]],
        goal=lambda item: _id(item) == "D",
    )

    assert early_route.path_ids == ("A", "C", "D")
    assert late_route.path_ids == ("A", "B", "D")
    assert early_route.dynamic_state_receipt_sha256 == early.receipt.receipt_sha256
    assert early_route.dynamic_state_status == "ATTENUATED"
    assert late_route.dynamic_state_receipt_sha256 == late.receipt.receipt_sha256


def test_terminated_dynamic_state_blocks_before_routing() -> None:
    field = _field()
    source = _failed_state(field)
    controller = DynamicStateController(
        dynamic_field=field,
        policy=_policy(),
    )
    router = _hardened_router(field, controller)
    states = _states()
    graph = _graph()
    terminated = controller.evaluate(
        source,
        activated_at_utc="2026-09-21T20:00:00+00:00",
        observed_at_utc="2026-09-21T20:00:20+00:00",
    )

    with pytest.raises(DynamicStateContractError, match="terminated"):
        router.route(
            terminated,
            [states["A"]],
            expand=lambda item: [states[key] for key in graph[_id(item)]],
            goal=lambda item: _id(item) == "D",
        )


def test_hardened_router_rejects_wrong_temporal_policy() -> None:
    field = _field()
    source = _failed_state(field)
    controller = DynamicStateController(
        dynamic_field=field,
        policy=_policy(),
    )
    other_policy = DynamicStatePolicy(
        policy_id="other",
        version="0.1",
        max_state_age_seconds=30.0,
        rules=_policy().rules,
    )
    other = DynamicStateController(
        dynamic_field=field,
        policy=other_policy,
    )
    router = _hardened_router(field, controller)
    result = other.evaluate(
        source,
        activated_at_utc="2026-09-21T20:00:00+00:00",
        observed_at_utc="2026-09-21T20:00:01+00:00",
    )

    with pytest.raises(FieldAwareRoutingContractError, match="another temporal policy"):
        router.route(
            result,
            [{"id": "A"}],
            expand=lambda item: [],
            goal=lambda item: False,
        )
