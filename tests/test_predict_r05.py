"""ΦPredict R0.5 fail-closed point-in-time comment/run re-auditing tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from phios.predict import (
    PredictionContractError,
    _append,
    load_ledger,
    observe,
    register,
)
from phios.predict_anchor import anchor_payload
from phios.predict_audit import audit_anchor, main

REPO = "MichaelWave369/PhiOS"
PID = "trial-one"
SHA = "a" * 40
RUN_ID = 24138
COMMENT_ID = 45192
ROOT = datetime(2026, 11, 10, tzinfo=timezone.utc)


def _when(seconds: int) -> str:
    return (ROOT + timedelta(seconds=seconds)).isoformat()


def _prepare(tmp_path):
    ledger = tmp_path / "predictions.jsonl"
    with patch("phios.predict._now", return_value=_when(0)):
        register(
            ledger, prediction_id=PID, repo=REPO, head_sha=SHA,
            workflow="PhiOS qualification", probability=0.7, cohort="holdout",
        )
    run = {
        "id": RUN_ID,
        "repository": {"full_name": REPO},
        "head_sha": SHA,
        "name": "PhiOS qualification",
        "html_url": f"https://github.com/{REPO}/actions/runs/{RUN_ID}",
        "status": "completed",
        "conclusion": "success",
        "run_attempt": 1,
        "created_at": _when(180),
        "run_started_at": _when(240),
    }
    fixture = tmp_path / "run.json"
    fixture.write_text(json.dumps(run), encoding="utf-8")
    with patch("phios.predict._now", return_value=_when(300)):
        observe(ledger, prediction_id=PID, run_json=fixture)
    _append(ledger, "github_verification", {
        "prediction_id": PID,
        "run_id": RUN_ID,
        "api_sha256": "e" * 64,
        "checked_at": _when(500),
        "run_created_at": _when(180),
        "run_attempt": 1,
    })
    commitment = anchor_payload(
        ledger, prediction_id=PID
    )["commitment_sha256"]
    comment = {
        "id": COMMENT_ID,
        "issue_url": f"https://api.github.com/repos/{REPO}/issues/14",
        "html_url": (
            f"https://github.com/{REPO}/issues/14#issuecomment-{COMMENT_ID}"
        ),
        "body": "PHIPREDICT_R04_SHA256 " + commitment,
        "created_at": _when(60),
        "updated_at": _when(60),
    }
    _append(ledger, "github_anchor", {
        "prediction_id": PID,
        "comment_id": COMMENT_ID,
        "commitment_sha256": commitment,
        "comment_api_sha256": "d" * 64,
        "comment_created_at": _when(60),
        "comment_updated_at": _when(60),
        "run_created_at": _when(180),
        "checked_at": _when(510),
    })
    assert len(load_ledger(ledger)) == 4
    return ledger, comment, run


def _stub(monkeypatch, comment, run):
    seen = []

    def comment_fetch(url):
        seen.append(url)
        return json.dumps(comment).encode()

    def run_fetch(url):
        seen.append(url)
        return json.dumps(run).encode()

    monkeypatch.setattr("phios.predict_audit._fetch_public_comment", comment_fetch)
    monkeypatch.setattr("phios.predict_audit._fetch_public_run", run_fetch)
    return seen


def test_two_explicit_public_reads_unchanged_and_no_ledger_writes(
    monkeypatch, tmp_path
):
    ledger, comment, run = _prepare(tmp_path)
    seen = _stub(monkeypatch, comment, run)
    original = ledger.read_bytes()
    report = audit_anchor(
        ledger, prediction_id=PID, allow_public_network=True
    )
    assert seen == [
        f"https://api.github.com/repos/{REPO}/issues/comments/{COMMENT_ID}",
        f"https://api.github.com/repos/{REPO}/actions/runs/{RUN_ID}",
    ]
    assert report["result"] == "UNCHANGED_AT_THIS_CHECK"
    assert report["ledger_chain_head"] == load_ledger(ledger)[-1]["sha256"]
    assert report["ledger_mutated"] is False
    assert report["action_authority"] is False
    assert ledger.read_bytes() == original


def test_unrelated_public_metadata_does_not_count_as_tampering(
    monkeypatch, tmp_path
):
    ledger, comment, run = _prepare(tmp_path)
    comment["user"] = {"login": "someone"}
    run["jobs_url"] = "public-api-metadata"
    _stub(monkeypatch, comment, run)
    result = audit_anchor(
        ledger, prediction_id=PID, allow_public_network=True
    )
    assert result["result"] == "UNCHANGED_AT_THIS_CHECK"
    assert result["comment_api_sha256"] != "d" * 64
    assert result["run_api_sha256"] != "e" * 64


@pytest.mark.parametrize("changes", [
    {"body": "PHIPREDICT_R04_SHA256 " + "0" * 64},
    {"id": COMMENT_ID + 1},
    {"id": True},
    {"issue_url": "https://api.github.com/repos/another/repo/issues/14"},
    {"issue_url": "https://api.github.com/repos/MichaelWave369/PhiOS/issues/0"},
    {"html_url": "https://example.invalid/comment"},
    {"created_at": _when(61)},
    {"updated_at": _when(61)},
    {"updated_at": _when(200)},
    {"created_at": None},
])
def test_edited_deleted_moved_or_forged_comment_fails_closed(
    monkeypatch, tmp_path, changes
):
    ledger, comment, run = _prepare(tmp_path)
    comment.update(changes)
    seen = _stub(monkeypatch, comment, run)
    original = ledger.read_bytes()
    with pytest.raises(PredictionContractError):
        audit_anchor(ledger, prediction_id=PID, allow_public_network=True)
    assert len(seen) == 1
    assert ledger.read_bytes() == original


@pytest.mark.parametrize("changes", [
    {"run_attempt": 2},
    {"run_attempt": True},
    {"status": "in_progress"},
    {"conclusion": "failure"},
    {"id": RUN_ID + 1},
    {"head_sha": "f" * 40},
    {"name": "Different CI"},
    {"repository": {"full_name": "different/repo"}},
    {"html_url": "https://example.invalid/runs/24138"},
    {"created_at": _when(181)},
    {"run_started_at": _when(241)},
    {"run_started_at": None},
])
def test_rerun_or_changed_run_is_not_requalified(
    monkeypatch, tmp_path, changes
):
    ledger, comment, run = _prepare(tmp_path)
    run.update(changes)
    seen = _stub(monkeypatch, comment, run)
    before = ledger.read_bytes()
    with pytest.raises(PredictionContractError):
        audit_anchor(ledger, prediction_id=PID, allow_public_network=True)
    assert len(seen) == 2
    assert ledger.read_bytes() == before


def test_missing_comment_and_malformed_run_do_not_write(
    monkeypatch, tmp_path
):
    ledger, comment, run = _prepare(tmp_path)
    _stub(monkeypatch, comment, run)
    monkeypatch.setattr(
        "phios.predict_audit._fetch_public_comment",
        lambda url: (_ for _ in ()).throw(
            PredictionContractError("GitHub public comment 404")
        ),
    )
    with pytest.raises(PredictionContractError, match="404"):
        audit_anchor(ledger, prediction_id=PID, allow_public_network=True)

    _stub(monkeypatch, comment, run)
    monkeypatch.setattr(
        "phios.predict_audit._fetch_public_run", lambda url: b"<html>fail"
    )
    with pytest.raises(PredictionContractError, match="malformed"):
        audit_anchor(ledger, prediction_id=PID, allow_public_network=True)
    assert len(load_ledger(ledger)) == 4


def test_missing_explicit_network_approval_never_fetches(
    monkeypatch, tmp_path, capsys
):
    ledger, comment, run = _prepare(tmp_path)
    def forbidden(url):
        pytest.fail("no public read authorized")
    monkeypatch.setattr("phios.predict_audit._fetch_public_run", forbidden)
    monkeypatch.setattr("phios.predict_audit._fetch_public_comment", forbidden)
    with pytest.raises(PredictionContractError, match="explicit approval"):
        audit_anchor(ledger, prediction_id=PID)
    assert main(["--ledger", str(ledger), "--id", PID]) == 2
    assert "HOLD" in capsys.readouterr().err


def test_no_anchored_evidence_blocks_audit_before_network(
    monkeypatch, tmp_path
):
    ledger, comment, run = _prepare(tmp_path)
    original = ledger.read_text()
    # Make a well-formed, source-verified ledger with no anchor event.
    lines = original.splitlines()
    ledger.write_text("\n".join(lines[:-1]) + "\n")
    _stub(monkeypatch, comment, run)
    with pytest.raises(PredictionContractError, match="anchored"):
        audit_anchor(ledger, prediction_id=PID, allow_public_network=True)


def test_oversize_response_is_rejected_even_when_transport_is_mocked(
    monkeypatch, tmp_path
):
    ledger, comment, run = _prepare(tmp_path)
    _stub(monkeypatch, comment, run)
    monkeypatch.setattr(
        "phios.predict_audit._fetch_public_comment",
        lambda url: b"x" * 2_000_100,
    )
    with pytest.raises(PredictionContractError, match="exceeds"):
        audit_anchor(ledger, prediction_id=PID, allow_public_network=True)
