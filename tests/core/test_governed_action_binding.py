from __future__ import annotations

from dataclasses import replace

import pytest

from phios.core.governed_action_binding import (
    ActionBindingContractError,
    ActionBindingGrant,
    GovernedActionBinder,
)
from phios.core.governed_plan_adoption import (
    GovernedPlanAdoptionGate,
    PlanAdoptionContractError,
)
from phios.core.field_aware_routing import FieldAwareRouteReceipt
from phios.spine.models import Capability


def _route_receipt() -> FieldAwareRouteReceipt:
    payload = {
        "schema": "phios.field_aware_route_receipt.v0.4",
        "status": "found",
        "field_law_sha256": "a" * 64,
        "field_state_sha256": "b" * 64,
        "field_revision": 0,
        "bindings": [],
        "path_receipt_sha256": "c" * 64,
        "path_ids": ["A", "B", "D"],
        "total_cost": 2.0,
        "optimality_scope": (
            "least_declared_cost_over_observed_graph_at_exact_field_snapshot"
        ),
        "action_authority": False,
    }
    import hashlib
    import json

    digest = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return FieldAwareRouteReceipt(
        schema="phios.field_aware_route_receipt.v0.4",
        status="found",
        field_law_sha256="a" * 64,
        field_state_sha256="b" * 64,
        field_revision=0,
        bindings=(),
        path_receipt_sha256="c" * 64,
        path_ids=("A", "B", "D"),
        total_cost=2.0,
        optimality_scope=(
            "least_declared_cost_over_observed_graph_at_exact_field_snapshot"
        ),
        action_authority=False,
        receipt_sha256=digest,
    )


def _plan():
    return GovernedPlanAdoptionGate().initialize_plan(
        plan_id="primary-plan",
        route_receipt=_route_receipt(),
    )


def _capability():
    return Capability(
        id="commons.text_artifact",
        name="Text Artifact",
        description="test",
        permissions=("artifact.write",),
        effects=("filesystem.change",),
        risk="low",
        version="0.1.0",
    )


def _payload():
    return {"name": "demo", "text": "hello"}


def _payload_sha():
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps(
            _payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _grant(plan):
    return ActionBindingGrant(
        grant_id="bind-001",
        authority_source="operator",
        plan_id=plan.plan_id,
        plan_state_sha256=plan.state_sha256,
        transition_index=0,
        source_state_id="A",
        target_state_id="B",
        capability_id="commons.text_artifact",
        payload_sha256=_payload_sha(),
    )


def test_exact_grant_binds_plan_edge_to_spine_capability():
    plan = _plan()
    binding, receipt = GovernedActionBinder().bind(
        plan=plan,
        transition_index=0,
        capability=_capability(),
        payload=_payload(),
        grant=_grant(plan),
    )

    assert binding is not None
    assert receipt.status == "BOUND"
    assert receipt.grant_scope_valid is True
    assert binding.plan_state_sha256 == plan.state_sha256
    assert binding.source_state_id == "A"
    assert binding.target_state_id == "B"
    assert binding.capability_id == "commons.text_artifact"
    assert binding.permissions_requested == ("artifact.write",)
    assert binding.effects_declared == ("filesystem.change",)
    assert receipt.effects_declared == ("filesystem.change",)
    assert binding.action_authority is False
    assert binding.execution_authority is False


def test_missing_binding_authority_holds():
    plan = _plan()
    binding, receipt = GovernedActionBinder().bind(
        plan=plan,
        transition_index=0,
        capability=_capability(),
        payload=_payload(),
        grant=None,
    )

    assert binding is None
    assert receipt.status == "HELD"
    assert receipt.reason == "action_binding_authority_missing"


def test_payload_scope_mismatch_holds():
    plan = _plan()
    grant = replace(_grant(plan), payload_sha256="f" * 64)

    binding, receipt = GovernedActionBinder().bind(
        plan=plan,
        transition_index=0,
        capability=_capability(),
        payload=_payload(),
        grant=grant,
    )

    assert binding is None
    assert receipt.reason == "grant_payload_scope_mismatch"


def test_capability_scope_mismatch_holds():
    plan = _plan()
    grant = replace(_grant(plan), capability_id="other.capability")

    binding, receipt = GovernedActionBinder().bind(
        plan=plan,
        transition_index=0,
        capability=_capability(),
        payload=_payload(),
        grant=grant,
    )

    assert binding is None
    assert receipt.reason == "grant_capability_scope_mismatch"


def test_plan_state_scope_mismatch_holds():
    plan = _plan()
    grant = replace(_grant(plan), plan_state_sha256="e" * 64)

    binding, receipt = GovernedActionBinder().bind(
        plan=plan,
        transition_index=0,
        capability=_capability(),
        payload=_payload(),
        grant=grant,
    )

    assert binding is None
    assert receipt.reason == "grant_plan_state_scope_mismatch"


def test_invalid_transition_index_is_rejected():
    plan = _plan()

    with pytest.raises(ActionBindingContractError):
        GovernedActionBinder().bind(
            plan=plan,
            transition_index=2,
            capability=_capability(),
            payload=_payload(),
            grant=None,
        )


def test_tampered_plan_is_rejected():
    plan = replace(_plan(), path_ids=("A", "C", "D"))

    with pytest.raises(PlanAdoptionContractError):
        GovernedActionBinder().bind(
            plan=plan,
            transition_index=0,
            capability=_capability(),
            payload=_payload(),
            grant=None,
        )


def test_non_json_payload_is_rejected():
    plan = _plan()

    with pytest.raises(ActionBindingContractError):
        GovernedActionBinder().bind(
            plan=plan,
            transition_index=0,
            capability=_capability(),
            payload={"bad": object()},
            grant=None,
        )


def test_binding_is_deterministic():
    plan = _plan()
    binder = GovernedActionBinder()
    grant = _grant(plan)

    first_binding, first_receipt = binder.bind(
        plan=plan,
        transition_index=0,
        capability=_capability(),
        payload=_payload(),
        grant=grant,
    )
    second_binding, second_receipt = binder.bind(
        plan=plan,
        transition_index=0,
        capability=_capability(),
        payload=_payload(),
        grant=grant,
    )

    assert first_binding is not None
    assert second_binding is not None
    assert first_binding.to_dict() == second_binding.to_dict()
    assert first_receipt.to_dict() == second_receipt.to_dict()
