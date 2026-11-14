"""Focused, fully offline ΦPredict R0.1 contract and calibration tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from phios.predict import (
    PredictionContractError,
    load_ledger,
    main,
    observe,
    register,
    report,
)

REPO = "MichaelWave369/PhiOS"
SHA = "a" * 40


def _register(path, prediction_id="p01", *, head_sha=SHA, p=0.9, cohort="holdout"):
    return register(
        path, prediction_id=prediction_id, repo=REPO, head_sha=head_sha,
        workflow="CI", probability=p, cohort=cohort,
    )


def _run_json(path, *, sha=SHA, run_id=701, conclusion="success", **changes):
    started = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    payload = {
        "id": run_id,
        "repository": {"full_name": REPO},
        "name": "CI",
        "head_sha": sha,
        "status": "completed",
        "conclusion": conclusion,
        "html_url": f"https://github.com/{REPO}/actions/runs/{run_id}",
        "run_started_at": started,
    }
    payload.update(changes)
    source = path / f"run-{run_id}.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    return source


def test_register_observe_hash_chain_and_report(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    first = _register(ledger)
    assert first["sequence"] == 1
    assert report(ledger)["pending"] == 1
    source = _run_json(tmp_path)
    second = observe(ledger, prediction_id="p01", run_json=source)
    assert second["sequence"] == 2
    assert second["previous_sha256"] == first["sha256"]
    assert second["data"]["source_sha256"]
    assert len(load_ledger(ledger)) == 2
    summary = report(ledger)
    assert summary["holdout_scored"] == 1
    assert summary["candidate_mean_brier"] == pytest.approx(0.01)
    assert summary["fixed_half_baseline_mean_brier"] == pytest.approx(0.25)
    assert summary["verdict"] == "HOLD_INSUFFICIENT_HOLDOUT"
    assert summary["action_authority"] is False


def test_twenty_prequential_holdout_outcomes_produce_descriptive_gate(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    for i in range(20):
        sha = f"{i + 1:040x}"
        _register(ledger, f"p{i + 1}", head_sha=sha)
        source = _run_json(tmp_path, sha=sha, run_id=i + 1000)
        observe(ledger, prediction_id=f"p{i + 1}", run_json=source)
    summary = report(ledger)
    assert summary["holdout_scored"] == 20
    assert summary["verdict"] == "DESCRIPTIVE_LOWER_ERROR_NOT_VALIDATED"
    assert summary["candidate_mean_brier"] == pytest.approx(0.01)
    assert sum(group["count"] for group in summary["calibration_bins"]) == 20


def test_wrong_target_run_and_nonfinal_run_are_rejected(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    _register(ledger)
    bad = _run_json(tmp_path, **{"repository": {"full_name": "other/Other"}})
    with pytest.raises(PredictionContractError, match="identity"):
        observe(ledger, prediction_id="p01", run_json=bad)
    not_final = _run_json(tmp_path, status="in_progress", conclusion=None)
    with pytest.raises(PredictionContractError, match="not completed"):
        observe(ledger, prediction_id="p01", run_json=not_final)
    assert len(load_ledger(ledger)) == 1


def test_late_prediction_does_not_get_scored(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    _register(ledger)
    earlier = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    source = _run_json(tmp_path, run_started_at=earlier)
    observe(ledger, prediction_id="p01", run_json=source)
    summary = report(ledger)
    assert summary["holdout_scored"] == 0
    assert summary["holdout_excluded"]["late_or_unverified_pre_run"] == 1


def test_neutral_outcome_not_counted_as_failure(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    _register(ledger)
    source = _run_json(tmp_path, conclusion="cancelled")
    observe(ledger, prediction_id="p01", run_json=source)
    summary = report(ledger)
    assert summary["holdout_scored"] == 0
    assert summary["holdout_excluded"]["nonbinary_outcome"] == 1


def test_duplicate_prediction_and_duplicate_observation_fail_closed(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    _register(ledger)
    with pytest.raises(PredictionContractError, match="duplicate"):
        _register(ledger, "another-id")
    source = _run_json(tmp_path)
    observe(ledger, prediction_id="p01", run_json=source)
    with pytest.raises(PredictionContractError, match="already observed"):
        observe(ledger, prediction_id="p01", run_json=source)


def test_mutated_history_fails_before_reporting_or_appending(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    _register(ledger)
    contents = ledger.read_text(encoding="utf-8")
    assert '"probability":0.9' in contents
    ledger.write_text(contents.replace('"probability":0.9', '"probability":0.1'), encoding="utf-8")
    with pytest.raises(PredictionContractError, match="tampered"):
        report(ledger)
    with pytest.raises(PredictionContractError, match="tampered"):
        _register(ledger, "p02", head_sha="b" * 40)
    assert not (tmp_path / "ledger.jsonl.lock").exists()


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -0.1, 1.1, True])
def test_reject_invalid_probabilities(tmp_path, invalid):
    with pytest.raises(PredictionContractError, match="probability"):
        _register(tmp_path / "ledger.jsonl", p=invalid)


def test_holds_invalid_source_url_and_oversize_file(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    _register(ledger)
    source = _run_json(tmp_path, html_url="https://github.com/evil/other/actions/runs/701")
    with pytest.raises(PredictionContractError, match="URL"):
        observe(ledger, prediction_id="p01", run_json=source)
    source.write_bytes(b"x" * 2_000_001)
    with pytest.raises(PredictionContractError, match="size limit"):
        observe(ledger, prediction_id="p01", run_json=source)


def test_cli_report_and_verify_are_read_only(tmp_path, capsys):
    ledger = tmp_path / "ledger.jsonl"
    assert main(["--ledger", str(ledger), "verify"]) == 0
    assert "verified_events" in capsys.readouterr().out
    assert not ledger.exists()
    assert main(["--ledger", str(ledger), "report"]) == 0
    assert "HOLD_INSUFFICIENT_HOLDOUT" in capsys.readouterr().out
    assert not ledger.exists()
