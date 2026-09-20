from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from phios.reflex.influence_adoption import (
    GovernedReflexInfluenceAdoptionGate,
    ReflexInfluenceAdoptionContractError,
    ReflexInfluenceGrant,
)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _readiness(status: str = "REVIEW_ELIGIBLE"):
    payload = {
        "schema": "phios.reflex_promotion_readiness_receipt.v0.4",
        "status": status,
        "reason": "all_advisory_review_thresholds_met",
        "policy_id": "test-policy",
        "policy_sha256": "a" * 64,
        "candidate_provider": "jev",
        "unique_runs_seen": 30,
        "included_runs": 30,
        "ambiguous_runs": [],
        "exact_duplicates_ignored": 0,
        "shadow_ok_runs": 28,
        "shadow_unavailable_runs": 2,
        "shadow_error_runs": 0,
        "shadow_availability_rate": 0.933333333,
        "baseline": {
            "provider": "rules",
            "models": ["deterministic-rules"],
            "available_runs": 30,
            "scored_runs": 30,
            "scored_dimension_observations": 90,
            "dimension_counts": {
                "role": 30,
                "risk": 20,
                "system2": 30,
                "verification": 10,
            },
            "dimension_mean_brier": {
                "role": 0.12,
                "risk": 0.10,
                "system2": 0.11,
                "verification": 0.14,
            },
            "dimension_coverage": 0.75,
            "mean_brier": 0.1175,
        },
        "candidate": {
            "provider": "jev",
            "models": ["jev-test"],
            "available_runs": 28,
            "scored_runs": 28,
            "scored_dimension_observations": 84,
            "dimension_counts": {
                "role": 28,
                "risk": 19,
                "system2": 28,
                "verification": 9,
            },
            "dimension_mean_brier": {
                "role": 0.06,
                "risk": 0.07,
                "system2": 0.05,
                "verification": 0.08,
            },
            "dimension_coverage": 0.75,
            "mean_brier": 0.065,
        },
        "paired_baseline": {
            "provider": "rules",
            "models": ["deterministic-rules"],
            "available_runs": 28,
            "scored_runs": 28,
            "scored_dimension_observations": 84,
            "dimension_counts": {
                "role": 28,
                "risk": 19,
                "system2": 28,
                "verification": 9,
            },
            "dimension_mean_brier": {
                "role": 0.12,
                "risk": 0.10,
                "system2": 0.11,
                "verification": 0.14,
            },
            "dimension_coverage": 0.75,
            "mean_brier": 0.1175,
        },
        "candidate_vs_paired_baseline_delta": -0.0525,
        "source_receipt_sha256s": ["b" * 64, "c" * 64],
        "thresholds_passed": {
            "maximum_candidate_mean_brier": True,
            "maximum_regression_vs_paired_baseline": True,
            "minimum_candidate_scored_runs": True,
            "minimum_dimension_coverage": True,
            "minimum_shadow_availability_rate": True,
            "minimum_unique_runs": True,
            "no_ambiguous_run_loss": True,
        },
        "routing_influence_authority": False,
        "promotion_authority": False,
        "action_authority": False,
        "execution_authority": False,
    }
    payload["receipt_sha256"] = _digest(payload)
    return payload


def _grant(readiness, current_sha=None, disposition="ADOPT"):
    return ReflexInfluenceGrant(
        grant_id="grant-001",
        authority_source="operator",
        readiness_receipt_sha256=readiness["receipt_sha256"],
        current_policy_sha256=current_sha,
        candidate_provider="jev",
        allowed_dimensions=("role", "system2"),
        max_influence_weight=0.20,
        rollback_on_provider_unavailable=True,
        max_consecutive_provider_errors=3,
        disposition=disposition,
    )


def test_review_eligible_receipt_with_exact_grant_adopts_inactive_policy():
    readiness = _readiness()
    gate = GovernedReflexInfluenceAdoptionGate()

    state, receipt = gate.apply(
        readiness_receipt=readiness,
        requested_disposition="ADOPT",
        allowed_dimensions=("role", "system2"),
        max_influence_weight=0.20,
        rollback_on_provider_unavailable=True,
        max_consecutive_provider_errors=3,
        grant=_grant(readiness),
    )

    assert state is not None
    assert receipt.status == "ADOPTED"
    assert state.candidate_provider == "jev"
    assert state.candidate_models == ("jev-test",)
    assert state.allowed_dimensions == ("role", "system2")
    assert state.max_influence_weight == pytest.approx(0.20)
    assert state.routing_influence_active is False
    assert state.runtime_activation_authority is False
    assert receipt.promotion_authority is False
    assert receipt.action_authority is False
    assert receipt.execution_authority is False


def test_review_eligible_without_grant_is_held():
    readiness = _readiness()

    state, receipt = GovernedReflexInfluenceAdoptionGate().apply(
        readiness_receipt=readiness,
        requested_disposition="ADOPT",
        allowed_dimensions=("role",),
        max_influence_weight=0.10,
        rollback_on_provider_unavailable=True,
        max_consecutive_provider_errors=2,
        grant=None,
    )

    assert state is None
    assert receipt.status == "HELD"
    assert receipt.reason == "influence_adoption_authority_missing"


def test_non_review_eligible_receipt_cannot_be_adopted_even_with_grant():
    readiness = _readiness("NOT_REVIEW_ELIGIBLE")

    state, receipt = GovernedReflexInfluenceAdoptionGate().apply(
        readiness_receipt=readiness,
        requested_disposition="ADOPT",
        allowed_dimensions=("role", "system2"),
        max_influence_weight=0.20,
        rollback_on_provider_unavailable=True,
        max_consecutive_provider_errors=3,
        grant=_grant(readiness),
    )

    assert state is None
    assert receipt.status == "HELD"
    assert receipt.reason == "readiness_not_review_eligible"


def test_grant_dimension_mismatch_is_held():
    readiness = _readiness()
    grant = replace(_grant(readiness), allowed_dimensions=("risk",))

    state, receipt = GovernedReflexInfluenceAdoptionGate().apply(
        readiness_receipt=readiness,
        requested_disposition="ADOPT",
        allowed_dimensions=("role", "system2"),
        max_influence_weight=0.20,
        rollback_on_provider_unavailable=True,
        max_consecutive_provider_errors=3,
        grant=grant,
    )

    assert state is None
    assert receipt.reason == "grant_dimension_scope_mismatch"


def test_authorized_rejection_does_not_create_policy():
    readiness = _readiness()

    state, receipt = GovernedReflexInfluenceAdoptionGate().apply(
        readiness_receipt=readiness,
        requested_disposition="REJECT",
        allowed_dimensions=("role", "system2"),
        max_influence_weight=0.20,
        rollback_on_provider_unavailable=True,
        max_consecutive_provider_errors=3,
        grant=_grant(readiness, disposition="REJECT"),
    )

    assert state is None
    assert receipt.status == "REJECTED"
    assert receipt.policy_changed is False


def test_policy_update_requires_exact_current_state_scope():
    readiness = _readiness()
    gate = GovernedReflexInfluenceAdoptionGate()
    first, first_receipt = gate.apply(
        readiness_receipt=readiness,
        requested_disposition="ADOPT",
        allowed_dimensions=("role", "system2"),
        max_influence_weight=0.20,
        rollback_on_provider_unavailable=True,
        max_consecutive_provider_errors=3,
        grant=_grant(readiness),
    )
    assert first is not None
    assert first_receipt.status == "ADOPTED"

    stale_grant = _grant(readiness, current_sha=None)
    second, second_receipt = gate.apply(
        readiness_receipt=readiness,
        requested_disposition="ADOPT",
        allowed_dimensions=("role", "system2"),
        max_influence_weight=0.20,
        rollback_on_provider_unavailable=True,
        max_consecutive_provider_errors=3,
        grant=stale_grant,
        current_policy=first,
    )

    assert second == first
    assert second_receipt.status == "HELD"
    assert second_receipt.reason == "grant_current_policy_scope_mismatch"


def test_exact_current_state_scope_allows_new_policy_revision():
    readiness = _readiness()
    gate = GovernedReflexInfluenceAdoptionGate()
    first, _ = gate.apply(
        readiness_receipt=readiness,
        requested_disposition="ADOPT",
        allowed_dimensions=("role", "system2"),
        max_influence_weight=0.20,
        rollback_on_provider_unavailable=True,
        max_consecutive_provider_errors=3,
        grant=_grant(readiness),
    )
    assert first is not None

    grant = _grant(readiness, current_sha=first.state_sha256)
    second, receipt = gate.apply(
        readiness_receipt=readiness,
        requested_disposition="ADOPT",
        allowed_dimensions=("role", "system2"),
        max_influence_weight=0.20,
        rollback_on_provider_unavailable=True,
        max_consecutive_provider_errors=3,
        grant=grant,
        current_policy=first,
    )

    assert second is not None
    assert second.revision == first.revision + 1
    assert second.parent_policy_sha256 == first.state_sha256
    assert receipt.status == "ADOPTED"


def test_tampered_readiness_receipt_is_rejected():
    readiness = _readiness()
    readiness["candidate_provider"] = "other"

    with pytest.raises(ReflexInfluenceAdoptionContractError):
        GovernedReflexInfluenceAdoptionGate().apply(
            readiness_receipt=readiness,
            requested_disposition="ADOPT",
            allowed_dimensions=("role",),
            max_influence_weight=0.10,
            rollback_on_provider_unavailable=True,
            max_consecutive_provider_errors=2,
            grant=None,
        )


def test_tampered_policy_state_is_rejected():
    readiness = _readiness()
    gate = GovernedReflexInfluenceAdoptionGate()
    state, _ = gate.apply(
        readiness_receipt=readiness,
        requested_disposition="ADOPT",
        allowed_dimensions=("role", "system2"),
        max_influence_weight=0.20,
        rollback_on_provider_unavailable=True,
        max_consecutive_provider_errors=3,
        grant=_grant(readiness),
    )
    assert state is not None

    tampered = replace(state, max_influence_weight=0.50)
    with pytest.raises(ReflexInfluenceAdoptionContractError):
        gate.validate_policy_state(tampered)
