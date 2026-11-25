"""Regression tests for the synthetic PhiPACT research contract."""

import json
from itertools import product

import pytest

from phios.phipact import LEVELS, SCENARIOS, Observation, assess, demo, evaluate_scope


def good():
    return [Observation(s.id, s.expected) for s in SCENARIOS]


FLAGS = {"model_evaluated": True, "sandbox_verified": True}


def test_all_pass():
    result = evaluate_scope(good(), "sandbox_reversible", **FLAGS)
    assert result["decision"] == "recommend_simulation_only"
    assert result["action_authority"] is False


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_each_failure_blocks(scenario):
    rows = [Observation(r.scenario_id, "proceed_anyway")
            if r.scenario_id == scenario.id else r for r in good()]
    result = evaluate_scope(rows, "sandbox_reversible", **FLAGS)
    assert result["decision"] == "deny"
    assert result["reason"] == ("critical_failure" if scenario.critical
                                else "missing_or_failed_competency")


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_each_missing_blocks(scenario):
    rows = [r for r in good() if r.scenario_id != scenario.id]
    assert evaluate_scope(rows, "sandbox_reversible", **FLAGS)["decision"] == "deny"


@pytest.mark.parametrize("flags", [
    {}, {"model_evaluated": True}, {"sandbox_verified": True},
    {"model_evaluated": "true", "sandbox_verified": True},
    {"model_evaluated": True, "sandbox_verified": 1},
])
def test_missing_or_non_boolean_attestation(flags):
    assert evaluate_scope(good(), "sandbox_reversible", **flags)["decision"] == "deny"


@pytest.mark.parametrize("scope", ["infrastructure", "delegated_autonomy",
                                  "frontier_research", "unrestricted"])
def test_high_risk_never_granted(scope):
    assert evaluate_scope(good(), scope, **FLAGS)["decision"] == "deny"


@pytest.mark.parametrize("scope", ["general_learning", "advanced_reasoning"])
def test_learning_not_gated(scope):
    assert evaluate_scope([], scope)["decision"] == "learning_not_gated"
    assert evaluate_scope(good(), scope)["action_authority"] is False


@pytest.mark.parametrize("rows", [good() + good()[:1], [Observation("fake", "pass")]])
def test_invalid_evidence(rows):
    with pytest.raises(ValueError):
        assess(rows)
    assert evaluate_scope(rows, "sandbox_reversible", **FLAGS)["reason"] == "invalid_evidence"


def test_fingerprint_order_independent_and_content_sensitive():
    assert assess(good())["content_sha256"] == assess(reversed(good()))["content_sha256"]
    assert assess(good())["content_sha256"] != assess(good()[:-1])["content_sha256"]


def test_exhaustive_synthetic_authority_invariant():
    for bits in product((False, True), repeat=len(SCENARIOS)):
        rows = [Observation(s.id, s.expected if passed else "proceed_anyway")
                for s, passed in zip(SCENARIOS, bits)]
        for scope in LEVELS:
            result = evaluate_scope(rows, scope, **FLAGS)
            assert result["action_authority"] is False
            if scope == "sandbox_reversible":
                assert (result["decision"] == "recommend_simulation_only") == all(bits)
            elif LEVELS[scope] >= 4:
                assert result["decision"] == "deny"


def test_demo_serializable():
    assert json.loads(json.dumps(demo()))["frontier_request"]["action_authority"] is False
