"""ΦPredict R0.5: opt-in, fail-closed *current* audit of a public commitment.

Re-fetch ONE previously anchored public issue comment and its ONE independently
verified public Actions run. No writes to GitHub, to the ledger or to disk.
An old R0.4 receipt is evidence of a historical observation, NOT a claim
that the comment/run are still unchanged today.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phios.predict import (
    MAX_EVIDENCE_BYTES,
    PredictionContractError,
    _replay,
    _when,
    load_ledger,
)
from phios.predict_anchor import ANCHOR_PREFIX, _fetch_public_comment
from phios.predict_source import _fetch_public_run


def audit_anchor(
    path: Path, *, prediction_id: str, allow_public_network: bool = False
) -> dict[str, Any]:
    """Cross-check one unchanged public comment *and* one unrerun GitHub run.

    The operator approves exactly two read-only public GETs. On ANY mismatch
    or missing public evidence the audit raises and does not claim success.
    This intentionally does not append an audit event to the old ledger;
    a one-time success never upgrades the permanent R0.4 report to "current".
    """
    if not allow_public_network:
        raise PredictionContractError("two public GitHub reads require explicit approval")
    events = load_ledger(path)
    predictions, outcomes = _replay(events)
    prediction = predictions.get(prediction_id)
    outcome = outcomes.get(prediction_id)
    checks = {
        e["data"]["prediction_id"]: e["data"]
        for e in events if e["kind"] == "github_verification"
    }
    anchors = {
        e["data"]["prediction_id"]: e["data"]
        for e in events if e["kind"] == "github_anchor"
    }
    check = checks.get(prediction_id)
    anchor = anchors.get(prediction_id)
    if not prediction or not outcome or not check or not anchor:
        raise PredictionContractError(
            "current audit requires a registered, observed, run-verified, anchored prediction"
        )
    repo = prediction["repo"]
    run_id = outcome["run_id"]
    comment_id = anchor["comment_id"]
    comment_url = f"https://api.github.com/repos/{repo}/issues/comments/{comment_id}"
    run_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}"

    raw_comment = _fetch_public_comment(comment_url)
    if len(raw_comment) > MAX_EVIDENCE_BYTES:
        raise PredictionContractError("re-audited issue comment exceeds evidence limit")
    try:
        comment = json.loads(raw_comment)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PredictionContractError("malformed public issue comment JSON") from exc
    if not isinstance(comment, dict):
        raise PredictionContractError("public issue comment is not an object")
    issue_url = comment.get("issue_url")
    match = re.fullmatch(
        rf"https://api\.github\.com/repos/{re.escape(repo)}/issues/([1-9][0-9]*)",
        issue_url if isinstance(issue_url, str) else "",
    )
    issue_number = match.group(1) if match else None
    expected_html = (
        f"https://github.com/{repo}/issues/{issue_number}#issuecomment-{comment_id}"
    )
    if (
        type(comment.get("id")) is not int
        or comment["id"] != comment_id
        or issue_number is None
        or comment.get("html_url") != expected_html
        or comment.get("body") != ANCHOR_PREFIX + anchor["commitment_sha256"]
    ):
        raise PredictionContractError("comment is deleted, changed or has wrong identity")
    created = _when(comment.get("created_at"), "current_comment_created_at")
    updated = _when(comment.get("updated_at"), "current_comment_updated_at")
    original_created = _when(anchor["comment_created_at"], "comment_created_at")
    original_updated = _when(anchor["comment_updated_at"], "comment_updated_at")
    if created != original_created or updated != original_updated:
        raise PredictionContractError("public comment chronology changed after anchor")
    if not (
        _when(prediction["registered_at"], "registered_at")
        < created <= updated
        < _when(check["run_created_at"], "run_created_at")
    ):
        raise PredictionContractError("public comment chronology is no longer admissible")

    raw_run = _fetch_public_run(run_url)
    if len(raw_run) > MAX_EVIDENCE_BYTES:
        raise PredictionContractError("re-audited GitHub run exceeds evidence limit")
    try:
        run = json.loads(raw_run)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PredictionContractError("malformed public GitHub run JSON") from exc
    if not isinstance(run, dict):
        raise PredictionContractError("public GitHub run is not an object")

    repository = run.get("repository")
    source_repo = (
        repository.get("full_name") if isinstance(repository, dict) else None
    )
    expected_run_html = f"https://github.com/{repo}/actions/runs/{run_id}"
    if (
        type(run.get("id")) is not int or run["id"] != run_id
        or source_repo != repo
        or run.get("head_sha") != prediction["head_sha"]
        or run.get("name") != prediction["workflow"]
        or run.get("html_url") != expected_run_html
        or run.get("status") != "completed"
        or run.get("conclusion") != outcome["conclusion"]
        or type(run.get("run_attempt")) is not int
        or run["run_attempt"] != 1
    ):
        raise PredictionContractError(
            "public GitHub run changed, reran or differs from recorded outcome"
        )
    run_created = _when(run.get("created_at"), "current_run_created_at")
    run_started = _when(run.get("run_started_at"), "current_run_started_at")
    if (
        run_created != _when(check["run_created_at"], "run_created_at")
        or run_started != _when(outcome["run_started_at"], "run_started_at")
        or updated >= run_created or run_created > run_started
        or run_started > datetime.now(timezone.utc)
    ):
        raise PredictionContractError("public run chronology changed since verification")
    return {
        "schema": "phios.predict.anchor_current_audit.r0.5",
        "result": "UNCHANGED_AT_THIS_CHECK",
        "prediction_id": prediction_id,
        "repo": repo,
        "run_id": run_id,
        "comment_id": comment_id,
        "comment_api_sha256": hashlib.sha256(raw_comment).hexdigest(),
        "run_api_sha256": hashlib.sha256(raw_run).hexdigest(),
        "comment_created_at": anchor["comment_created_at"],
        "comment_updated_at": anchor["comment_updated_at"],
        "run_created_at": check["run_created_at"],
        "run_attempt": 1,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "ledger_chain_head": events[-1]["sha256"],
        "ledger_mutated": False,
        "action_authority": False,
        "limits": (
            "This is a point-in-time, API-reported comparison, not a signed "
            "attestation or continuous monitor. Raw API hashes can change due "
            "to unrelated metadata; matched identity, body and timestamps are "
            "the audited conditions. A later edit, delete or rerun requires "
            "another explicit check. Forecast skill is not validated."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=Path("phipredict-ledger.jsonl"))
    parser.add_argument("--id", required=True, help="existing R0.4 anchored prediction ID")
    parser.add_argument(
        "--allow-public-network", action="store_true",
        help="approve exactly two read-only public GitHub API GETs",
    )
    args = parser.parse_args(argv)
    try:
        result = audit_anchor(
            args.ledger, prediction_id=args.id,
            allow_public_network=args.allow_public_network,
        )
    except (PredictionContractError, OSError, ValueError) as exc:
        print(f"ΦPredict R0.5 HOLD: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
