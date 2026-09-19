from __future__ import annotations

from dataclasses import replace

import pytest

from phios.core.dynamic_field import (
    DynamicField,
    DynamicFieldContractError,
    DynamicFieldLaw,
    FieldEvent,
    FieldVariableRule,
)


def _law() -> DynamicFieldLaw:
    return DynamicFieldLaw(
        law_id="phi-core-field",
        version="0.3",
        variables=(
            FieldVariableRule(
                name="uncertainty",
                minimum=0.0,
                maximum=1.0,
                initial=0.8,
                allowed_event_kinds=("evidence", "contradiction"),
                max_abs_delta=0.4,
            ),
            FieldVariableRule(
                name="historical_failure",
                minimum=0.0,
                maximum=10.0,
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


def test_initialize_binds_state_to_immutable_law():
    field = DynamicField(_law())

    state = field.initialize()

    assert state.revision == 0
    assert state.value("uncertainty") == pytest.approx(0.8)
    assert state.action_authority is False
    assert state.law_sha256 == field.law.law_sha256


def test_evidence_can_reshape_field_without_mutating_law():
    field = DynamicField(_law())
    state = field.initialize()
    law_before = field.law.law_sha256

    next_state, receipt = field.apply_event(
        state,
        FieldEvent(
            event_id="evidence-001",
            kind="evidence",
            deltas={"uncertainty": -0.3},
            source_label="reality-gate",
            evidence_sha256="a" * 64,
        ),
    )

    assert receipt.status == "applied"
    assert next_state.value("uncertainty") == pytest.approx(0.5)
    assert next_state.revision == 1
    assert receipt.governing_law_mutated is False
    assert receipt.action_authority is False
    assert field.law.law_sha256 == law_before


def test_failure_can_change_future_field_state_under_declared_rule():
    field = DynamicField(_law())
    state = field.initialize()

    next_state, receipt = field.apply_event(
        state,
        FieldEvent(
            event_id="failure-001",
            kind="failure",
            deltas={"historical_failure": 1.5},
            source_label="builder-run",
        ),
    )

    assert receipt.status == "applied"
    assert next_state.value("historical_failure") == pytest.approx(1.5)
    assert receipt.changes[0].name == "historical_failure"


def test_disallowed_event_kind_is_blocked_without_state_change():
    field = DynamicField(_law())
    state = field.initialize()

    next_state, receipt = field.apply_event(
        state,
        FieldEvent(
            event_id="bad-kind-001",
            kind="failure",
            deltas={"uncertainty": -0.1},
            source_label="test",
        ),
    )

    assert receipt.status == "blocked"
    assert "uncertainty:event_kind_not_allowed" in receipt.blocked_by
    assert next_state == state


def test_delta_beyond_law_is_blocked_without_clamping():
    field = DynamicField(_law())
    state = field.initialize()

    next_state, receipt = field.apply_event(
        state,
        FieldEvent(
            event_id="oversize-001",
            kind="resource",
            deltas={"resource_pressure": 0.8},
            source_label="scheduler",
        ),
    )

    assert receipt.status == "blocked"
    assert "resource_pressure:delta_exceeds_rule" in receipt.blocked_by
    assert next_state == state


def test_value_outside_bounds_is_blocked():
    field = DynamicField(_law())
    state = field.initialize()

    next_state, receipt = field.apply_event(
        state,
        FieldEvent(
            event_id="bounds-001",
            kind="contradiction",
            deltas={"uncertainty": 0.4},
            source_label="verifier",
        ),
    )

    assert receipt.status == "blocked"
    assert "uncertainty:value_out_of_bounds" in receipt.blocked_by
    assert next_state == state


def test_event_replay_is_blocked():
    field = DynamicField(_law())
    state = field.initialize()
    event = FieldEvent(
        event_id="evidence-001",
        kind="evidence",
        deltas={"uncertainty": -0.2},
        source_label="reality-gate",
    )

    once, first_receipt = field.apply_event(state, event)
    twice, second_receipt = field.apply_event(once, event)

    assert first_receipt.status == "applied"
    assert second_receipt.status == "blocked"
    assert second_receipt.blocked_by == ("event_replay",)
    assert twice == once


def test_unknown_variable_cannot_smuggle_governance_change():
    field = DynamicField(_law())
    state = field.initialize()

    with pytest.raises(DynamicFieldContractError):
        field.apply_event(
            state,
            FieldEvent(
                event_id="law-hack-001",
                kind="evidence",
                deltas={"authority": 1.0},
                source_label="untrusted",
            ),
        )


def test_state_bound_to_different_law_is_rejected():
    field = DynamicField(_law())
    state = field.initialize()
    tampered = replace(state, law_sha256="0" * 64)

    with pytest.raises(DynamicFieldContractError):
        field.apply_event(
            tampered,
            FieldEvent(
                event_id="evidence-002",
                kind="evidence",
                deltas={"uncertainty": -0.1},
                source_label="test",
            ),
        )


def test_state_hash_tampering_is_rejected():
    field = DynamicField(_law())
    state = field.initialize()
    tampered = replace(state, state_sha256="f" * 64)

    with pytest.raises(DynamicFieldContractError):
        field.apply_event(
            tampered,
            FieldEvent(
                event_id="evidence-003",
                kind="evidence",
                deltas={"uncertainty": -0.1},
                source_label="test",
            ),
        )


def test_same_event_sequence_produces_same_state_and_receipts():
    field = DynamicField(_law())
    events = (
        FieldEvent(
            event_id="evidence-001",
            kind="evidence",
            deltas={"uncertainty": -0.2},
            source_label="gate",
            evidence_sha256="b" * 64,
        ),
        FieldEvent(
            event_id="failure-001",
            kind="failure",
            deltas={"historical_failure": 1.0},
            source_label="builder",
        ),
    )

    def run():
        state = field.initialize()
        receipts = []
        for event in events:
            state, receipt = field.apply_event(state, event)
            receipts.append(receipt.to_dict())
        return state.to_dict(), receipts

    assert run() == run()
