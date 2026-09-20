from __future__ import annotations

from dataclasses import replace

import pytest

from phios.reflex import PhiReflex, ReflexInput
from phios.reflex.dispatch_shadow import (
    DispatchShadowContractError,
    observe_dispatch,
)
from phios.reflex.providers.rules import RulesReflexProvider


class FixedShadowProvider:
    name = "fixed-shadow"

    def evaluate(self, reflex_input: ReflexInput):
        base = RulesReflexProvider().evaluate(reflex_input)
        return replace(
            base,
            provider=self.name,
            provider_version="test",
            model="fixed",
        )


def _context():
    return {
        "task": "build test",
        "orchestrator": "phios",
        "arch": "default",
        "review_panel": False,
    }


def _plan():
    return {
        "source": "local-fallback",
        "planner_available": False,
        "plan_steps": [
            {"step": "decompose task", "status": "pending"},
            {"step": "assign specialist agents", "status": "pending"},
        ],
    }


def test_dispatch_shadow_binds_exact_context_and_plan_without_influence():
    context = _context()
    plan = _plan()
    receipt = observe_dispatch(
        task="build test",
        operational_context=context,
        operational_plan=plan,
        reflex=PhiReflex(shadow=FixedShadowProvider()),
        external_side_effect=False,
    )

    assert receipt.reflex_receipt.shadow_status == "ok"
    assert receipt.planner_influenced_by_reflex is False
    assert receipt.operational_context_contains_reflex is False
    assert receipt.operational_plan_contains_reflex is False
    assert receipt.action_authority is False
    assert receipt.execution_authority is False
    assert len(receipt.operational_context_sha256) == 64
    assert len(receipt.operational_plan_sha256) == 64


def test_dispatch_shadow_changes_when_operational_plan_changes():
    first = observe_dispatch(
        task="build test",
        operational_context=_context(),
        operational_plan=_plan(),
        reflex=PhiReflex(),
        external_side_effect=False,
    )
    changed_plan = _plan()
    changed_plan["plan_steps"] = [
        {"step": "different step", "status": "pending"},
    ]
    second = observe_dispatch(
        task="build test",
        operational_context=_context(),
        operational_plan=changed_plan,
        reflex=PhiReflex(),
        external_side_effect=False,
    )

    assert first.operational_plan_sha256 != second.operational_plan_sha256
    assert first.receipt_sha256 != second.receipt_sha256


def test_reflex_material_in_operational_context_is_rejected():
    context = _context()
    context["reflex_shadow"] = {"role": "builder"}

    with pytest.raises(DispatchShadowContractError):
        observe_dispatch(
            task="build test",
            operational_context=context,
            operational_plan=_plan(),
            reflex=PhiReflex(),
            external_side_effect=False,
        )


def test_reflex_material_in_operational_plan_is_rejected():
    plan = _plan()
    plan["jev_score"] = 0.99

    with pytest.raises(DispatchShadowContractError):
        observe_dispatch(
            task="build test",
            operational_context=_context(),
            operational_plan=plan,
            reflex=PhiReflex(),
            external_side_effect=False,
        )


def test_external_side_effect_signal_reaches_reflex_risk():
    receipt = observe_dispatch(
        task="dispatch agents",
        operational_context=_context(),
        operational_plan=_plan(),
        reflex=PhiReflex(),
        external_side_effect=True,
    )

    assert receipt.reflex_receipt.baseline.risk == "high"
