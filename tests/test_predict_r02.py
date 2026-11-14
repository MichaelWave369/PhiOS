"""ΦPredict R0.2: real-source transport boundary, replay and scoring tests.

All network responses are mocked. This suite cannot attest a real GitHub run.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from phios.predict import (
    PredictionContractError,
    load_ledger,
    observe,
    register,
    report,
)
from phios.predict_source import main, verified_report, verify_github_run

REPO = "MichaelWave369/PhiOS"
SHA = "b" * 40


def _time(minutes_before: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_before)).isoformat()


def _setup(tmp_path, *, pid="trial1", sha=SHA, run_id=1234, status="completed"):
    ledger = tmp_path / "ledger.jsonl"
    with patch("phios.predict._now", return_value=_time(10)):
        register(
            ledger, prediction_id=pid, repo=REPO, head_sha=sha,
            workflow="CI", probability=0.8, cohort="holdout",
        )
    payload = {
        "id": run_id,
        "name": "CI",
        "head_sha": sha,
        "repository": {"full_name": REPO},
        "html_url": f"https://github.com/{REPO}/actions/runs/{run_id}",
        "status": status,
        "conclusion": "success",
        "run_started_at": _time(5),
        "created_at": _time(7),
        "run_attempt": 1,
    }
    run_path = tmp_path / "run.json"
    run_path.write_text(json.dumps(payload), encoding="utf-8")
    observe(ledger, prediction_id=pid, run_json=run_path)
    return ledger, payload


def _verify(monkeypatch, ledger, payload, *, pid="trial1"):
    seen = []

    def mock_fetch(url):
        seen.append(url)
        return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr("phios.predict_source._fetch_public_run", mock_fetch)
    result = verify_github_run(
        ledger, prediction_id=pid, allow_public_network=True
    )
    assert seen == [
        f"https://api.github.com/repos/{REPO}/actions/runs/{payload['id']}"
    ]
    return result


def test_verified_ledger_and_source_only_report(monkeypatch, tmp_path):
    ledger, payload = _setup(tmp_path)
    before = report(ledger)
    assert before["holdout_scored"] == 1
    assert verified_report(ledger)["verified_holdout_scored"] == 0
    event = _verify(monkeypatch, ledger, payload)
    assert event["kind"] == "github_verification"
    assert event["sequence"] == 3
    assert len(load_ledger(ledger)) == 3
    result = verified_report(ledger)
    assert result["github_checked_count"] == 1
    assert result["verified_holdout_scored"] == 1
    assert result["verified_candidate_mean_brier"] == pytest.approx(0.04)
    assert result["verdict"] == "HOLD_INSUFFICIENT_VERIFIED_HOLDOUT"
    assert result["action_authority"] is False
    assert report(ledger)["holdout_scored"] == 1


def test_public_network_must_be_explicit(monkeypatch, tmp_path):
    ledger, _ = _setup(tmp_path)

    def forbidden(_url):
        raise AssertionError("must not call network")

    monkeypatch.setattr("phios.predict_source._fetch_public_run", forbidden)
    with pytest.raises(PredictionContractError, match="explicit approval"):
        verify_github_run(ledger, prediction_id="trial1")
    assert main(["--ledger", str(ledger), "verify-github", "--id", "trial1"]) == 2
    assert main(["--ledger", str(ledger), "verified-report"]) == 0
    assert len(load_ledger(ledger)) == 2


@pytest.mark.parametrize(
    "changes",
    [
        {"head_sha": "f" * 40},
        {"name": "Other CI"},
        {"repository": {"full_name": "another/repo"}},
        {"status": "in_progress"},
        {"conclusion": "failure"},
        {"run_attempt": 2},
        {"run_attempt": None},
        {"created_at": None},
        {"html_url": "https://example.net/malicious"},
        {"id": True},
    ],
)
def test_mismatch_and_reruns_hold_without_event(monkeypatch, tmp_path, changes):
    ledger, original = _setup(tmp_path)
    payload = {**original, **changes}
    monkeypatch.setattr(
        "phios.predict_source._fetch_public_run",
        lambda _: json.dumps(payload).encode("utf-8"),
    )
    with pytest.raises(PredictionContractError):
        verify_github_run(ledger, prediction_id="trial1", allow_public_network=True)
    assert len(load_ledger(ledger)) == 2


def test_post_creation_prediction_cannot_enter_verified_score(monkeypatch, tmp_path):
    ledger, payload = _setup(tmp_path)
    # This API creation time predates the declared local registration timestamp.
    payload["created_at"] = _time(20)
    _verify(monkeypatch, ledger, payload)
    result = verified_report(ledger)
    assert result["github_checked_count"] == 1
    assert result["verified_holdout_scored"] == 0
    assert result["verified_holdout_excluded"]["late_after_github_run_creation"] == 1


def test_start_time_disagreement_rejected(monkeypatch, tmp_path):
    ledger, payload = _setup(tmp_path)
    payload["run_started_at"] = _time(4)
    monkeypatch.setattr(
        "phios.predict_source._fetch_public_run",
        lambda _: json.dumps(payload).encode("utf-8"),
    )
    with pytest.raises(PredictionContractError, match="start differs"):
        verify_github_run(ledger, prediction_id="trial1", allow_public_network=True)
    assert len(load_ledger(ledger)) == 2


def test_duplicate_verification_rejected(monkeypatch, tmp_path):
    ledger, payload = _setup(tmp_path)
    _verify(monkeypatch, ledger, payload)
    with pytest.raises(PredictionContractError, match="already verified"):
        verify_github_run(ledger, prediction_id="trial1", allow_public_network=True)


def test_modified_verification_hash_detected(monkeypatch, tmp_path):
    ledger, payload = _setup(tmp_path)
    _verify(monkeypatch, ledger, payload)
    before = ledger.read_text(encoding="utf-8")
    ledger.write_text(before.replace('"run_attempt":1', '"run_attempt":2'), encoding="utf-8")
    with pytest.raises(PredictionContractError):
        verified_report(ledger)


def test_twenty_verified_holdout_results_descriptive_not_proof(monkeypatch, tmp_path):
    ledger = tmp_path / "batch.jsonl"
    for number in range(20):
        pid = f"p{number}"
        sha = f"{number + 1:040x}"
        with patch("phios.predict._now", return_value=_time(10)):
            register(
                ledger, prediction_id=pid, repo=REPO, head_sha=sha,
                workflow="CI", probability=0.8, cohort="holdout",
            )
        payload = {
            "id": number + 9000,
            "name": "CI",
            "head_sha": sha,
            "repository": {"full_name": REPO},
            "html_url": f"https://github.com/{REPO}/actions/runs/{number + 9000}",
            "status": "completed",
            "conclusion": "success",
            "run_started_at": _time(5),
            "created_at": _time(7),
            "run_attempt": 1,
        }
        source = tmp_path / "run.json"
        source.write_text(json.dumps(payload), encoding="utf-8")
        observe(ledger, prediction_id=pid, run_json=source)
        _verify(monkeypatch, ledger, payload, pid=pid)
    summary = verified_report(ledger)
    assert summary["verified_holdout_scored"] == 20
    assert summary["verified_candidate_mean_brier"] == pytest.approx(0.04)
    assert summary["verdict"] == "DESCRIPTIVE_LOWER_ERROR_NOT_VALIDATED"
    assert summary["action_authority"] is False


def test_invalid_json_and_oversize_live_response_hold(monkeypatch, tmp_path):
    ledger, _ = _setup(tmp_path)
    for raw in (b"<html>nope</html>", b"x" * 2_000_100):
        monkeypatch.setattr("phios.predict_source._fetch_public_run", lambda _: raw)
        with pytest.raises(PredictionContractError):
            verify_github_run(ledger, prediction_id="trial1", allow_public_network=True)
    assert len(load_ledger(ledger)) == 2


def test_redirect_denial_is_fail_closed():
    from phios.predict_source import _NoRedirect
    with pytest.raises(PredictionContractError, match="redirect"):
        _NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://evil")
