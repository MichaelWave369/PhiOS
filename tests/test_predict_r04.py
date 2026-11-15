"""ΦPredict R0.4 external comment commitments, fail-closed offline tests.

Every public GitHub comment response is mocked. No network or public writes.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from phios.predict import (
    PredictionContractError,
    _append,
    load_ledger,
    observe,
    register,
)
from phios.predict_anchor import (
    anchor_payload,
    anchored_report,
    main,
    verify_anchor,
)

ROOT = datetime(2026, 11, 10, tzinfo=timezone.utc)
REPO = "MichaelWave369/PhiOS"
SHA = "a" * 40
COMMENT_ID = 8675309
RUN_ID = 123456


def _time(seconds: int) -> str:
    return (ROOT + timedelta(seconds=seconds)).isoformat()


def _prepared(tmp_path, *, with_source=True, conclusion="success"):
    ledger = tmp_path / "ledger.jsonl"
    with patch("phios.predict._now", return_value=_time(0)):
        register(
            ledger, prediction_id="trial001", repo=REPO, head_sha=SHA,
            workflow="CI", probability=0.80, cohort="holdout",
        )
    run = {
        "id": RUN_ID, "name": "CI", "head_sha": SHA,
        "repository": {"full_name": REPO},
        "html_url": f"https://github.com/{REPO}/actions/runs/{RUN_ID}",
        "status": "completed", "conclusion": conclusion,
        "run_started_at": _time(240),
    }
    path = tmp_path / "run.json"
    path.write_text(json.dumps(run), encoding="utf-8")
    observe(ledger, prediction_id="trial001", run_json=path)
    if with_source:
        _append(ledger, "github_verification", {
            "prediction_id": "trial001", "run_id": RUN_ID,
            "api_sha256": "e" * 64, "checked_at": _time(500),
            "run_created_at": _time(180), "run_attempt": 1,
        })
    return ledger


def _comment(ledger, *, created=60, updated=60):
    return {
        "id": COMMENT_ID,
        "body": anchor_payload(
            ledger, prediction_id="trial001"
        )["comment_body"],
        "issue_url": f"https://api.github.com/repos/{REPO}/issues/42",
        "html_url": f"https://github.com/{REPO}/issues/42#issuecomment-{COMMENT_ID}",
        "created_at": _time(created),
        "updated_at": _time(updated),
    }


def _verify(monkeypatch, ledger, comment):
    urls = []

    def fake_get(url):
        urls.append(url)
        return json.dumps(comment).encode("utf-8")

    monkeypatch.setattr("phios.predict_anchor._fetch_public_comment", fake_get)
    result = verify_anchor(
        ledger, prediction_id="trial001",
        comment_id=COMMENT_ID, allow_public_network=True,
    )
    assert urls == [
        f"https://api.github.com/repos/{REPO}/issues/comments/{COMMENT_ID}"
    ]
    return result


def test_payload_is_deterministic_and_ledger_stays_read_only(tmp_path):
    ledger = _prepared(tmp_path)
    before = ledger.read_bytes()
    payload = anchor_payload(ledger, prediction_id="trial001")
    assert payload == anchor_payload(ledger, prediction_id="trial001")
    assert payload["comment_body"] == (
        "PHIPREDICT_R04_SHA256 " + payload["commitment_sha256"]
    )
    assert len(payload["commitment_sha256"]) == 64
    assert payload["action_authority"] is False
    assert ledger.read_bytes() == before


def test_successfully_verified_anchor_is_scored_and_old_reports_still_load(
    tmp_path, monkeypatch
):
    ledger = _prepared(tmp_path)
    event = _verify(monkeypatch, ledger, _comment(ledger))
    assert event["kind"] == "github_anchor"
    assert event["sequence"] == 4
    assert len(load_ledger(ledger)) == 4
    report = anchored_report(ledger)
    assert report["holdout_scored"] == 1
    assert report["public_comment_anchored_count"] == 1
    assert report["candidate_mean_brier"] == pytest.approx(0.04)
    assert report["verdict"] == "HOLD_INSUFFICIENT_EXTERNALLY_ANCHORED_HOLDOUT"
    assert report["action_authority"] is False
    from phios.predict_source import verified_report
    from phios.predict_calibration import calibration_report
    assert verified_report(ledger)["verified_holdout_scored"] == 1
    assert calibration_report(ledger)["scored_holdout"] == 1


@pytest.mark.parametrize("change", [
    {"id": COMMENT_ID + 1},
    {"body": "PHIPREDICT_R04_SHA256 " + "0" * 64},
    {"issue_url": "https://api.github.com/repos/another/repo/issues/42"},
    {"issue_url": "https://api.github.com/repos/MichaelWave369/PhiOS/issues/0"},
    {"html_url": "https://example.org/issues/42"},
    {"created_at": _time(-100)},
    {"created_at": _time(190), "updated_at": _time(190)},
    {"updated_at": _time(190)},
    {"updated_at": _time(40)},
    {"created_at": "not-a-time"},
    {"updated_at": None},
])
def test_forged_borrowed_late_or_edited_comments_are_rejected(
    tmp_path, monkeypatch, change
):
    ledger = _prepared(tmp_path)
    body = {**_comment(ledger), **change}
    monkeypatch.setattr(
        "phios.predict_anchor._fetch_public_comment",
        lambda url: json.dumps(body).encode("utf-8"),
    )
    with pytest.raises(PredictionContractError):
        verify_anchor(
            ledger, prediction_id="trial001",
            comment_id=COMMENT_ID, allow_public_network=True,
        )
    assert len(load_ledger(ledger)) == 3
    assert anchored_report(ledger)["holdout_scored"] == 0


def test_network_default_off_and_unverified_run_holds(tmp_path, monkeypatch):
    ledger = _prepared(tmp_path)
    monkeypatch.setattr(
        "phios.predict_anchor._fetch_public_comment",
        lambda url: pytest.fail("network must not be touched"),
    )
    with pytest.raises(PredictionContractError, match="explicit approval"):
        verify_anchor(ledger, prediction_id="trial001", comment_id=COMMENT_ID)
    assert main([
        "--ledger", str(ledger), "verify-anchor", "--id", "trial001",
        "--comment-id", str(COMMENT_ID),
    ]) == 2
    assert len(load_ledger(ledger)) == 3

    unverified = _prepared(tmp_path / "other", with_source=False)
    with pytest.raises(PredictionContractError, match="independent"):
        verify_anchor(
            unverified, prediction_id="trial001",
            comment_id=COMMENT_ID, allow_public_network=True,
        )


def test_reused_anchor_and_hash_rewrite_rejected(tmp_path, monkeypatch):
    ledger = _prepared(tmp_path)
    _verify(monkeypatch, ledger, _comment(ledger))
    with pytest.raises(PredictionContractError, match="already"):
        verify_anchor(
            ledger, prediction_id="trial001",
            comment_id=COMMENT_ID, allow_public_network=True,
        )
    saved = ledger.read_text()
    ledger.write_text(saved.replace('"comment_id":8675309', '"comment_id":8675308'))
    with pytest.raises(PredictionContractError):
        anchored_report(ledger)


def test_nonbinary_conclusion_excluded_even_with_valid_anchor(tmp_path, monkeypatch):
    ledger = _prepared(tmp_path, conclusion="cancelled")
    _verify(monkeypatch, ledger, _comment(ledger))
    result = anchored_report(ledger)
    assert result["holdout_scored"] == 0
    assert result["holdout_excluded"]["nonbinary_outcome"] == 1
    assert result["candidate_mean_brier"] is None


def test_oversized_bad_json_and_wrong_type_rejected(tmp_path, monkeypatch):
    ledger = _prepared(tmp_path)
    for raw in (b"{", b"x" * 2_000_100, b"[]"):
        monkeypatch.setattr(
            "phios.predict_anchor._fetch_public_comment", lambda url: raw
        )
        with pytest.raises(PredictionContractError):
            verify_anchor(
                ledger, prediction_id="trial001",
                comment_id=COMMENT_ID, allow_public_network=True,
            )
    assert len(load_ledger(ledger)) == 3


def test_anchor_cli_missing_ledger_holds(tmp_path, capsys):
    missing = tmp_path / "no-ledger.jsonl"
    assert main([
        "--ledger", str(missing),
        "anchor-payload", "--id", "unknown",
    ]) == 2
    assert "HOLD" in capsys.readouterr().err
    assert not missing.exists()
