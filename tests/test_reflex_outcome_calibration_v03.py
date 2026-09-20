from __future__ import annotations

from dataclasses import replace

import pytest

from phios.reflex import PhiReflex, ReflexInput
from phios.reflex.dispatch_shadow import observe_dispatch
from phios.reflex.outcome_calibration import (
    ReflexOutcomeContractError,
    ReflexOutcomeObservation,
    evaluate_dispatch_outcome,
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
            role_probabilities=(
                ("utility", 0.02),
                ("builder", 0.90),
                ("synthesis", 0.04),
                ("translator", 0.01),
                ("ledger", 0.03),
            ),
            role="builder",
            risk_probabilities=(
                ("low", 0.05),
                ("elevated", 0.90),
                ("high", 0.05),
            ),
            risk="elevated",
            needs_system2_probability=0.92,
            needs_verification_probability=0.85,
            confidence=0.90,
        )


def _shadow():
    return observe_dispatch(
        task="build the adapter",
        operational_context={
            "task": "build the adapter",
            "orchestrator": "phios",
            "arch": "default",
        },
        operational_plan={
            "source": "local-fallback",
            "plan_steps": [{"step": "build", "status": "pending"}],
        },
        reflex=PhiReflex(shadow=FixedShadowProvider()),
        external_side_effect=False,
    ).to_dict()


def _observation(**changes):
    values = {
        "run_id": "run_abc",
        "dispatch_outcome": "succeeded",
        "observer_label": "operator-review",
        "evidence_sha256": "a" * 64,
        "actual_role": "builder",
        "actual_risk": "elevated",
        "system2_needed": True,
        "verification_needed": True,
    }
    values.update(changes)
    return ReflexOutcomeObservation(**values)


def test_calibration_scores_only_observed_dimensions():
    receipt = evaluate_dispatch_outcome(
        dispatch_shadow=_shadow(),
        observation=_observation(
            actual_risk=None,
            verification_needed=None,
        ),
    )

    assert receipt.status == "scored"
    assert receipt.baseline.scored_dimensions == 2
    assert receipt.baseline.role_scored is True
    assert receipt.baseline.risk_scored is False
    assert receipt.baseline.verification_scored is False
    assert receipt.shadow is not None
    assert receipt.shadow.scored_dimensions == 2
    assert receipt.action_authority is False
    assert receipt.execution_authority is False


def test_no_labels_produces_unscored_receipt_not_fake_accuracy():
    receipt = evaluate_dispatch_outcome(
        dispatch_shadow=_shadow(),
        observation=_observation(
            actual_role=None,
            actual_risk=None,
            system2_needed=None,
            verification_needed=None,
        ),
    )

    assert receipt.status == "unscored_no_observed_labels"
    assert receipt.baseline.scored_dimensions == 0
    assert receipt.baseline.mean_brier is None
    assert receipt.shadow is not None
    assert receipt.shadow.mean_brier is None


def test_shadow_provider_is_scored_against_same_ground_truth():
    receipt = evaluate_dispatch_outcome(
        dispatch_shadow=_shadow(),
        observation=_observation(),
    )

    assert receipt.compared_providers is True
    assert receipt.shadow is not None
    assert receipt.baseline.scored_dimensions == 4
    assert receipt.shadow.scored_dimensions == 4
    assert receipt.shadow.role_match is True
    assert receipt.shadow.risk_match is True
    assert receipt.shadow.system2_brier == pytest.approx((0.92 - 1.0) ** 2)
    assert receipt.shadow.verification_brier == pytest.approx((0.85 - 1.0) ** 2)


def test_dispatch_outcome_does_not_become_ground_truth_by_itself():
    receipt = evaluate_dispatch_outcome(
        dispatch_shadow=_shadow(),
        observation=_observation(
            dispatch_outcome="failed",
            actual_role=None,
            actual_risk=None,
            system2_needed=None,
            verification_needed=None,
        ),
    )

    assert receipt.observation.dispatch_outcome == "failed"
    assert receipt.status == "unscored_no_observed_labels"
    assert receipt.baseline.scored_dimensions == 0


def test_tampered_dispatch_shadow_receipt_is_rejected():
    shadow = _shadow()
    shadow["operational_plan_sha256"] = "b" * 64

    with pytest.raises(ReflexOutcomeContractError):
        evaluate_dispatch_outcome(
            dispatch_shadow=shadow,
            observation=_observation(),
        )


def test_contaminated_dispatch_shadow_is_rejected_even_with_rehashed_outer_receipt():
    shadow = _shadow()
    shadow["planner_influenced_by_reflex"] = True

    with pytest.raises(ReflexOutcomeContractError):
        evaluate_dispatch_outcome(
            dispatch_shadow=shadow,
            observation=_observation(),
        )


def test_invalid_observed_labels_fail_closed():
    with pytest.raises(ReflexOutcomeContractError):
        _observation(actual_role="wizard")


def test_calibration_receipt_is_deterministic():
    shadow = _shadow()
    observation = _observation()

    first = evaluate_dispatch_outcome(
        dispatch_shadow=shadow,
        observation=observation,
    )
    second = evaluate_dispatch_outcome(
        dispatch_shadow=shadow,
        observation=observation,
    )

    assert first.to_dict() == second.to_dict()
