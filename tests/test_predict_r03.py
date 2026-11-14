"""ΦPredict R0.3: historical prequential calibration without lookahead."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from phios.predict import _append, observe, register
from phios.predict_calibration import (
    calibration_report,
    main,
    render_static_dashboard,
)

ROOT = datetime(2026, 11, 10, tzinfo=timezone.utc)
REPO = "MichaelWave369/PhiOS"


def _at(minutes: int) -> str:
    return (ROOT + timedelta(minutes=minutes)).isoformat()


def _add(
    tmp_path,
    ledger,
    pid,
    *,
    idx,
    reg,
    created,
    started,
    observed,
    checked,
    conclusion="success",
    cohort="holdout",
    workflow="CI",
    p=0.8,
    verification=True,
    observation=True,
):
    sha = f"{idx + 1:040x}"
    with patch("phios.predict._now", return_value=_at(reg)):
        register(
            ledger, prediction_id=pid, repo=REPO, head_sha=sha,
            workflow=workflow, probability=p, cohort=cohort,
        )
    if not observation:
        return
    run_id = 5000 + idx
    payload = {
        "id": run_id,
        "repository": {"full_name": REPO},
        "head_sha": sha,
        "name": workflow,
        "html_url": f"https://github.com/{REPO}/actions/runs/{run_id}",
        "status": "completed",
        "conclusion": conclusion,
        "run_started_at": _at(started),
    }
    evidence = tmp_path / f"{pid}.json"
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    with patch("phios.predict._now", return_value=_at(observed)):
        observe(ledger, prediction_id=pid, run_json=evidence)
    if verification:
        _append(ledger, "github_verification", {
            "prediction_id": pid,
            "run_id": run_id,
            "api_sha256": "a" * 64,
            "checked_at": _at(checked),
            "run_created_at": _at(created),
            "run_attempt": 1,
        })


def test_history_uses_only_verified_outcomes_known_before_forecast(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    _add(
        tmp_path, ledger, "pilot", idx=0, reg=0, created=10,
        started=20, observed=25, checked=30, cohort="pilot",
    )
    _add(
        tmp_path, ledger, "first", idx=1, reg=40, created=50,
        started=60, observed=70, checked=80, conclusion="failure", p=0.75,
    )
    _add(
        tmp_path, ledger, "second", idx=2, reg=90, created=100,
        started=110, observed=120, checked=130, conclusion="success", p=0.90,
    )
    result = calibration_report(ledger)
    rows = result["holdout_rows"]
    assert [r["prediction_id"] for r in rows] == ["first", "second"]
    assert rows[0]["historical_known_count"] == 1
    assert rows[0]["historical_probability"] == pytest.approx(2 / 3)
    assert rows[1]["historical_known_count"] == 2
    assert rows[1]["historical_probability"] == pytest.approx(0.5)
    assert result["candidate_mean_brier"] == pytest.approx((0.75**2 + 0.1**2) / 2)
    assert result["historical_mean_brier"] == pytest.approx(
        ((2 / 3)**2 + 0.5**2) / 2
    )
    assert result["scored_holdout"] == 2
    assert result["eligible_verified_history"] == 3
    assert result["verdict"] == "HOLD_INSUFFICIENT_VERIFIED_HOLDOUT"
    assert result["action_authority"] is False


def test_future_verified_outcome_does_not_leak_into_earlier_forecast(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    _add(
        tmp_path, ledger, "first", idx=0, reg=0, created=10,
        started=20, observed=60, checked=70,
    )
    _add(
        tmp_path, ledger, "second", idx=1, reg=30, created=40,
        started=50, observed=75, checked=80, conclusion="failure",
    )
    result = calibration_report(ledger)
    rows = result["holdout_rows"]
    assert [r["historical_known_count"] for r in rows] == [0, 0]
    assert [r["historical_probability"] for r in rows] == [0.5, 0.5]


def test_history_is_per_repository_and_workflow(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    _add(
        tmp_path, ledger, "first", idx=0, reg=0, created=10,
        started=20, observed=25, checked=30, workflow="CI",
    )
    _add(
        tmp_path, ledger, "second", idx=1, reg=40, created=50,
        started=60, observed=70, checked=80, workflow="Release",
    )
    assert calibration_report(ledger)["holdout_rows"][1]["historical_known_count"] == 0


def test_pending_unverified_nonbinary_and_late_are_excluded(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    _add(
        tmp_path, ledger, "pending", idx=0, reg=0, created=10, started=20,
        observed=30, checked=35, observation=False,
    )
    _add(
        tmp_path, ledger, "unchecked", idx=1, reg=0, created=10, started=20,
        observed=30, checked=35, verification=False,
    )
    _add(
        tmp_path, ledger, "neutral", idx=2, reg=0, created=10, started=20,
        observed=30, checked=35, conclusion="cancelled",
    )
    _add(
        tmp_path, ledger, "late", idx=3, reg=15, created=10, started=20,
        observed=30, checked=35,
    )
    result = calibration_report(ledger)
    assert result["scored_holdout"] == 0
    assert result["holdout_excluded"] == {
        "pending_outcome": 1,
        "not_github_checked": 1,
        "nonbinary_outcome": 1,
        "late_after_run_creation": 1,
    }
    assert result["historical_mean_brier"] is None
    assert result["fixed_half_mean_brier"] is None
    assert result["calibration_bins"][0]["mean_forecast"] is None


def test_twenty_holdout_results_remain_descriptive(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    for index in range(20):
        n = index * 40
        _add(
            tmp_path, ledger, f"trial{index}", idx=index, reg=n,
            created=n + 10, started=n + 20, observed=n + 25,
            checked=n + 30, p=0.90,
        )
    result = calibration_report(ledger)
    assert result["scored_holdout"] == 20
    assert result["verdict"] == "DESCRIPTIVE_LOWER_ERROR_THAN_HISTORICAL"
    assert result["candidate_mean_brier"] == pytest.approx(0.01)
    assert result["historical_mean_brier"] > 0.01
    assert sum(bin_["count"] for bin_ in result["calibration_bins"]) == 20
    assert result["holdout_rows"][-1]["historical_known_count"] == 19


def test_dashboard_is_offline_and_escapes_workflow_name(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    untrusted = '<img src=x onerror="alert(1)">'
    _add(
        tmp_path, ledger, "sample", idx=0, reg=0, created=10,
        started=20, observed=25, checked=30, workflow=untrusted,
    )
    rendered = render_static_dashboard(calibration_report(ledger))
    assert "<script" not in rendered
    assert untrusted not in rendered
    assert "&lt;img" in rendered
    assert "Content-Security-Policy" in rendered
    assert "<svg" in rendered
    assert "no remote data or scripts" in rendered


def test_report_is_read_only_unless_html_path_explicit(tmp_path, capsys):
    ledger = tmp_path / "ledger.jsonl"
    assert main(["--ledger", str(ledger)]) == 0
    assert "HOLD_INSUFFICIENT_VERIFIED_HOLDOUT" in capsys.readouterr().out
    assert not ledger.exists()
    assert not list(tmp_path.iterdir())
    output = tmp_path / "reports" / "calibration.html"
    assert main(["--ledger", str(ledger), "--html", str(output)]) == 0
    assert output.is_file()
    assert "No eligible holdout outcomes" in output.read_text()
    assert not ledger.exists()
