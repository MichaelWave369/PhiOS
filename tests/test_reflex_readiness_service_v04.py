from __future__ import annotations

import json

from phios.reflex import PhiReflex, ReflexInput
from phios.reflex.dispatch_shadow import observe_dispatch
from phios.reflex.outcome_calibration import (
    ReflexOutcomeObservation,
    evaluate_dispatch_outcome,
)
from phios.reflex.providers.rules import RulesReflexProvider
from phios.services.agent_dispatch import (
    build_reflex_readiness_report,
    dispatch_agentception_run,
)


class JevLikeProvider:
    name = "jev"

    def evaluate(self, reflex_input: ReflexInput):
        base = RulesReflexProvider().evaluate(reflex_input)
        return type(base)(
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
            latency_ms=base.latency_ms,
        )


def _calibration(run_id: str, evidence_char: str = "a"):
    shadow = observe_dispatch(
        task="build adapter",
        operational_context={"task": "build adapter", "arch": "default"},
        operational_plan={"plan_steps": [{"step": "build"}]},
        reflex=PhiReflex(shadow=JevLikeProvider()),
        external_side_effect=False,
    ).to_dict()
    observation = ReflexOutcomeObservation(
        run_id=run_id,
        dispatch_outcome="succeeded",
        observer_label="operator",
        evidence_sha256=evidence_char * 64,
        actual_role="builder",
        actual_risk="elevated",
        system2_needed=True,
        verification_needed=True,
    )
    return evaluate_dispatch_outcome(
        dispatch_shadow=shadow,
        observation=observation,
    ).to_dict()


def test_readiness_report_scans_persisted_runs(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_AGENTCEPTION_ENABLED", "false")

    for idx in range(3):
        run = dispatch_agentception_run(
            task=f"task {idx}",
            context={"task": f"task {idx}"},
            plan={"source": "test"},
            stream=False,
        )
        run_id = str(run["run_id"])
        path = (
            tmp_path
            / ".phios"
            / "agents"
            / "runs"
            / f"{run_id}.json"
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["reflex_calibration_receipts"] = [_calibration(run_id)]
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    from phios.reflex.calibration_aggregation import PromotionReadinessPolicy

    report = build_reflex_readiness_report(
        policy=PromotionReadinessPolicy(
            policy_id="test",
            candidate_provider="jev",
            min_unique_runs=3,
            min_candidate_scored_runs=3,
            min_dimension_coverage=0.5,
            min_shadow_availability_rate=1.0,
            max_candidate_mean_brier=0.05,
            max_regression_vs_paired_baseline=0.0,
        )
    )

    assert report["ok"] is True
    assert report["runs_scanned"] == 3
    assert report["runs_with_calibration"] == 3
    assert report["calibration_receipts_found"] == 3
    assert report["report"]["status"] == "REVIEW_ELIGIBLE"
    assert report["report"]["promotion_authority"] is False


def test_readiness_report_with_no_calibrations_is_insufficient(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("HOME", str(tmp_path))

    report = build_reflex_readiness_report()

    assert report["ok"] is True
    assert report["runs_scanned"] == 0
    assert report["calibration_receipts_found"] == 0
    assert report["report"]["status"] == "INSUFFICIENT_EVIDENCE"


def test_conflicting_receipts_in_one_run_are_excluded_from_report(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_AGENTCEPTION_ENABLED", "false")

    run = dispatch_agentception_run(
        task="conflicted",
        context={"task": "conflicted"},
        plan={"source": "test"},
        stream=False,
    )
    run_id = str(run["run_id"])
    path = (
        tmp_path
        / ".phios"
        / "agents"
        / "runs"
        / f"{run_id}.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["reflex_calibration_receipts"] = [
        _calibration(run_id, "a"),
        _calibration(run_id, "b"),
    ]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    from phios.reflex.calibration_aggregation import PromotionReadinessPolicy

    report = build_reflex_readiness_report(
        policy=PromotionReadinessPolicy(
            policy_id="test",
            candidate_provider="jev",
            min_unique_runs=1,
            min_candidate_scored_runs=1,
        )
    )

    aggregate = report["report"]
    assert aggregate["ambiguous_runs"] == [run_id]
    assert aggregate["included_runs"] == 0
    assert aggregate["status"] == "INSUFFICIENT_EVIDENCE"
