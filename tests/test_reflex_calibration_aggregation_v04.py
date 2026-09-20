from __future__ import annotations

from dataclasses import replace

import pytest

from phios.reflex import PhiReflex, ReflexInput
from phios.reflex.calibration_aggregation import (
    PromotionReadinessPolicy,
    ReflexAggregationContractError,
    aggregate_calibration_receipts,
)
from phios.reflex.dispatch_shadow import observe_dispatch
from phios.reflex.outcome_calibration import (
    ReflexOutcomeObservation,
    evaluate_dispatch_outcome,
)
from phios.reflex.providers.rules import RulesReflexProvider


class JevLikeProvider:
    name = "jev"

    def __init__(self, *, degraded: bool = False):
        self._degraded = degraded

    def evaluate(self, reflex_input: ReflexInput):
        base = RulesReflexProvider().evaluate(reflex_input)
        if self._degraded:
            return replace(
                base,
                provider="jev",
                provider_version="test",
                model="jev-test",
                role="utility",
                role_probabilities=(
                    ("utility", 0.80),
                    ("builder", 0.05),
                    ("synthesis", 0.05),
                    ("translator", 0.05),
                    ("ledger", 0.05),
                ),
                risk="low",
                risk_probabilities=(
                    ("low", 0.80),
                    ("elevated", 0.10),
                    ("high", 0.10),
                ),
                needs_system2_probability=0.10,
                needs_verification_probability=0.10,
                confidence=0.80,
            )
        return replace(
            base,
            provider="jev",
            provider_version="test",
            model="jev-test",
            role="builder",
            role_probabilities=(
                ("utility", 0.01),
                ("builder", 0.96),
                ("synthesis", 0.01),
                ("translator", 0.01),
                ("ledger", 0.01),
            ),
            risk="elevated",
            risk_probabilities=(
                ("low", 0.02),
                ("elevated", 0.96),
                ("high", 0.02),
            ),
            needs_system2_probability=0.97,
            needs_verification_probability=0.96,
            confidence=0.96,
        )


def _receipt(run_id: str, *, degraded: bool = False, partial: bool = False):
    shadow = observe_dispatch(
        task="build the adapter",
        operational_context={"task": "build the adapter", "arch": "default"},
        operational_plan={"plan_steps": [{"step": "build"}]},
        reflex=PhiReflex(shadow=JevLikeProvider(degraded=degraded)),
        external_side_effect=False,
    ).to_dict()
    observation = ReflexOutcomeObservation(
        run_id=run_id,
        dispatch_outcome="succeeded",
        observer_label="operator",
        evidence_sha256=(run_id.encode("utf-8").hex() + "0" * 64)[:64],
        actual_role="builder",
        actual_risk=None if partial else "elevated",
        system2_needed=True,
        verification_needed=None if partial else True,
    )
    return evaluate_dispatch_outcome(
        dispatch_shadow=shadow,
        observation=observation,
    ).to_dict()


def _policy(**changes):
    values = {
        "policy_id": "test-policy",
        "candidate_provider": "jev",
        "min_unique_runs": 3,
        "min_candidate_scored_runs": 3,
        "min_dimension_coverage": 0.50,
        "min_shadow_availability_rate": 1.0,
        "max_candidate_mean_brier": 0.05,
        "max_regression_vs_paired_baseline": 0.0,
    }
    values.update(changes)
    return PromotionReadinessPolicy(**values)


def test_good_candidate_can_become_review_eligible_but_never_promoted():
    receipts = [_receipt(f"run_{idx}") for idx in range(3)]

    report = aggregate_calibration_receipts(
        receipts,
        policy=_policy(),
    )

    assert report.status == "REVIEW_ELIGIBLE"
    assert report.candidate is not None
    assert report.candidate.provider == "jev"
    assert report.candidate.scored_runs == 3
    assert report.paired_baseline is not None
    assert report.candidate_vs_paired_baseline_delta is not None
    assert report.candidate_vs_paired_baseline_delta <= 0
    assert report.routing_influence_authority is False
    assert report.promotion_authority is False
    assert report.action_authority is False
    assert report.execution_authority is False


def test_insufficient_sample_size_stays_insufficient():
    report = aggregate_calibration_receipts(
        [_receipt("run_1")],
        policy=_policy(),
    )

    assert report.status == "INSUFFICIENT_EVIDENCE"
    assert dict(report.thresholds_passed)["minimum_unique_runs"] is False


def test_quality_failure_is_not_review_eligible_after_sufficient_evidence():
    receipts = [
        _receipt(f"run_{idx}", degraded=True)
        for idx in range(3)
    ]

    report = aggregate_calibration_receipts(
        receipts,
        policy=_policy(max_candidate_mean_brier=0.01),
    )

    assert report.status == "NOT_REVIEW_ELIGIBLE"
    assert dict(report.thresholds_passed)[
        "maximum_candidate_mean_brier"
    ] is False


def test_partial_labels_reduce_coverage_without_becoming_fake_samples():
    receipts = [
        _receipt(f"run_{idx}", partial=True)
        for idx in range(3)
    ]

    report = aggregate_calibration_receipts(
        receipts,
        policy=_policy(min_dimension_coverage=0.75),
    )

    assert report.candidate is not None
    assert report.candidate.scored_dimension_observations == 6
    assert report.candidate.dimension_coverage == pytest.approx(0.5)
    assert report.status == "INSUFFICIENT_EVIDENCE"


def test_exact_duplicate_receipt_is_counted_once():
    receipt = _receipt("run_1")
    report = aggregate_calibration_receipts(
        [receipt, receipt],
        policy=_policy(min_unique_runs=1, min_candidate_scored_runs=1),
    )

    assert report.unique_runs_seen == 1
    assert report.included_runs == 1
    assert report.exact_duplicates_ignored == 1


def test_conflicting_receipts_for_same_run_are_excluded():
    first = _receipt("run_same")
    second = _receipt("run_same", degraded=True)

    report = aggregate_calibration_receipts(
        [first, second],
        policy=_policy(min_unique_runs=1, min_candidate_scored_runs=1),
    )

    assert report.unique_runs_seen == 1
    assert report.included_runs == 0
    assert report.ambiguous_runs == ("run_same",)
    assert report.status == "INSUFFICIENT_EVIDENCE"
    assert dict(report.thresholds_passed)["no_ambiguous_run_loss"] is False


def test_tampered_v03_receipt_is_rejected():
    receipt = _receipt("run_1")
    receipt["status"] = "unscored_no_observed_labels"

    with pytest.raises(ReflexAggregationContractError):
        aggregate_calibration_receipts([receipt], policy=_policy())


def test_report_is_deterministic_independent_of_receipt_order():
    receipts = [_receipt(f"run_{idx}") for idx in range(3)]
    first = aggregate_calibration_receipts(receipts, policy=_policy())
    second = aggregate_calibration_receipts(
        list(reversed(receipts)),
        policy=_policy(),
    )

    assert first.to_dict() == second.to_dict()
