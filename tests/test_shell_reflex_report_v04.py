from __future__ import annotations

import json

from phios.shell.phi_router import route_command


def test_agents_reflex_report_command_builds_explicit_policy(monkeypatch):
    captured = {}

    def fake_report(*, policy):
        captured["policy"] = policy
        return {
            "ok": True,
            "runs_scanned": 10,
            "runs_with_calibration": 8,
            "calibration_receipts_found": 8,
            "report": {
                "schema": "phios.reflex_promotion_readiness_receipt.v0.4",
                "status": "INSUFFICIENT_EVIDENCE",
            },
        }

    monkeypatch.setattr(
        "phios.shell.phi_commands.build_reflex_readiness_report",
        fake_report,
    )

    out, code = route_command(
        [
            "agents",
            "reflex-report",
            "--candidate",
            "jev",
            "--policy-id",
            "custom-policy",
            "--min-runs",
            "30",
            "--min-scored",
            "20",
            "--min-coverage",
            "0.75",
            "--min-availability",
            "0.9",
            "--max-brier",
            "0.15",
            "--max-regression",
            "0.01",
        ]
    )

    assert code == 0
    payload = json.loads(out)
    assert payload["ok"] is True
    policy = captured["policy"]
    assert policy.policy_id == "custom-policy"
    assert policy.candidate_provider == "jev"
    assert policy.min_unique_runs == 30
    assert policy.min_candidate_scored_runs == 20
    assert policy.min_dimension_coverage == 0.75
    assert policy.min_shadow_availability_rate == 0.9
    assert policy.max_candidate_mean_brier == 0.15
    assert policy.max_regression_vs_paired_baseline == 0.01


def test_agents_reflex_report_rejects_bad_numeric_policy():
    out, code = route_command(
        [
            "agents",
            "reflex-report",
            "--min-runs",
            "many",
        ]
    )

    assert code == 0
    assert "Reflex report error:" in out
