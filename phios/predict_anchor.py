"""ΦPredict R0.4: opt-in external timestamp for a registered forecast.

A public GitHub issue comment can commit a digest of an earlier local ledger
prediction, before a GitHub Actions run is created. The operator posts it
manually. This module only fetches ONE explicit public comment when approved.
It never writes to GitHub, posts a comment, triggers CI, or acts on a forecast.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phios.predict import (
    MAX_EVIDENCE_BYTES,
    PredictionContractError,
    _append,
    _now,
    _replay,
    _when,
    load_ledger,
)
from phios.predict_source import _NoRedirect

ANCHOR_PREFIX = "PHIPREDICT_R04_SHA256 "
DOMAIN = b"phios.predict.anchor.r0.4:"
SHA64 = re.compile(r"^[0-9a-f]{64}$")


def _prediction_event(events: list[dict[str, Any]], pid: str) -> dict[str, Any]:
    for event in events:
        if event["kind"] == "prediction" and event["data"]["id"] == pid:
            return event
    raise PredictionContractError("unknown prediction id")


def commitment_digest(event: dict[str, Any]) -> str:
    """Bind both the full forecast and ledger prefix via its event SHA-256."""
    if event["kind"] != "prediction" or not SHA64.fullmatch(event["sha256"]):
        raise PredictionContractError("a verified prediction event is required")
    return hashlib.sha256(DOMAIN + event["sha256"].encode("ascii")).hexdigest()


def anchor_payload(path: Path, *, prediction_id: str) -> dict[str, Any]:
    """Return a pasteable public commitment, without modifying anything."""
    events = load_ledger(path)
    predictions, _ = _replay(events)
    if prediction_id not in predictions:
        raise PredictionContractError("unknown prediction id")
    event = _prediction_event(events, prediction_id)
    digest = commitment_digest(event)
    return {
        "schema": "phios.predict.anchor_payload.r0.4",
        "prediction_id": prediction_id,
        "repo": predictions[prediction_id]["repo"],
        "commitment_sha256": digest,
        "comment_body": ANCHOR_PREFIX + digest,
        "prediction_event_sha256": event["sha256"],
        "action_authority": False,
        "instructions": (
            "Manually publish comment_body unchanged in a PUBLIC issue in the "
            "same repository BEFORE the forecasted GitHub Actions run is created. "
            "Keep the issue comment ID. Do not edit it after run creation. "
            "This command does not post or contact GitHub."
        ),
    }


def _fetch_public_comment(url: str) -> bytes:
    """One canonical public API GET. No credentials, proxy or redirects."""
    if not re.fullmatch(
        r"https://api\.github\.com/repos/[A-Za-z0-9_.-]+/"
        r"[A-Za-z0-9_.-]+/issues/comments/[1-9][0-9]*", url
    ):
        raise PredictionContractError("not a canonical public issue comment URL")
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "PhiOS-PhiPredict/0.4-read-only",
        },
        method="GET",
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _NoRedirect()
    )
    try:
        with opener.open(request, timeout=10) as response:
            if response.geturl() != url:
                raise PredictionContractError("unexpected GitHub response URL")
            content_type = response.headers.get(
                "Content-Type", ""
            ).split(";")[0].strip()
            if content_type not in {
                "application/json", "application/vnd.github+json"
            }:
                raise PredictionContractError("GitHub comment response is not JSON")
            raw = response.read(MAX_EVIDENCE_BYTES + 1)
    except (urllib.error.URLError, OSError) as exc:
        raise PredictionContractError("public GitHub comment fetch failed") from exc
    if len(raw) > MAX_EVIDENCE_BYTES:
        raise PredictionContractError("GitHub comment response exceeds evidence limit")
    return raw


def verify_anchor(
    path: Path, *, prediction_id: str, comment_id: int,
    allow_public_network: bool = False,
) -> dict[str, Any]:
    """Append an independently checked comment receipt, or fail closed."""
    if not allow_public_network:
        raise PredictionContractError("public network access requires explicit approval")
    if type(comment_id) is not int or comment_id <= 0:
        raise PredictionContractError("comment id must be a positive integer")
    events = load_ledger(path)
    predictions, outcomes = _replay(events)
    if prediction_id not in predictions or prediction_id not in outcomes:
        raise PredictionContractError("prediction and outcome must both exist")
    checks = {
        e["data"]["prediction_id"]: e["data"]
        for e in events if e["kind"] == "github_verification"
    }
    anchors = {
        e["data"]["prediction_id"] for e in events
        if e["kind"] == "github_anchor"
    }
    if prediction_id in anchors:
        raise PredictionContractError("prediction already has an anchored receipt")
    verified = checks.get(prediction_id)
    if verified is None:
        raise PredictionContractError("run needs independent R0.2 source verification")

    prediction = predictions[prediction_id]
    repo = prediction["repo"]
    url = f"https://api.github.com/repos/{repo}/issues/comments/{comment_id}"
    raw = _fetch_public_comment(url)
    if len(raw) > MAX_EVIDENCE_BYTES:
        raise PredictionContractError("public comment is too large")
    try:
        obj = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PredictionContractError("malformed public GitHub comment JSON") from exc
    if not isinstance(obj, dict):
        raise PredictionContractError("GitHub issue comment is not an object")
    issue_url = obj.get("issue_url")
    match = re.fullmatch(
        rf"https://api\.github\.com/repos/{re.escape(repo)}/issues/([1-9][0-9]*)",
        issue_url if isinstance(issue_url, str) else "",
    )
    issue_id = match.group(1) if match else None
    expected_html = (
        f"https://github.com/{repo}/issues/{issue_id}#issuecomment-{comment_id}"
    )
    if (
        type(obj.get("id")) is not int or obj["id"] != comment_id
        or issue_id is None or obj.get("html_url") != expected_html
        or obj.get("body") != anchor_payload(
            path, prediction_id=prediction_id
        )["comment_body"]
    ):
        raise PredictionContractError("public issue comment identity or digest mismatch")

    created = _when(obj.get("created_at"), "comment_created_at")
    updated = _when(obj.get("updated_at"), "comment_updated_at")
    registered = _when(prediction["registered_at"], "registered_at")
    run_created = _when(verified["run_created_at"], "run_created_at")
    now = datetime.now(timezone.utc)
    if not (registered < created <= updated < run_created <= now):
        raise PredictionContractError(
            "public comment must be created/last edited before run creation"
        )

    event = _prediction_event(events, prediction_id)
    payload = {
        "prediction_id": prediction_id,
        "comment_id": comment_id,
        "comment_api_sha256": hashlib.sha256(raw).hexdigest(),
        "commitment_sha256": commitment_digest(event),
        "comment_created_at": obj["created_at"],
        "comment_updated_at": obj["updated_at"],
        "run_created_at": verified["run_created_at"],
        "checked_at": _now(),
    }
    return _append(path, "github_anchor", payload)


def anchored_report(path: Path) -> dict[str, Any]:
    """Score only independently run-checked AND externally anchored holdout."""
    events = load_ledger(path)
    predictions, outcomes = _replay(events)
    verified = {
        event["data"]["prediction_id"]: event["data"] for event in events
        if event["kind"] == "github_verification"
    }
    anchored = {
        event["data"]["prediction_id"]: event["data"] for event in events
        if event["kind"] == "github_anchor"
    }
    eligible: list[tuple[float, int]] = []
    excluded: dict[str, int] = {}
    for pid, row in predictions.items():
        if row["cohort"] != "holdout":
            continue
        outcome = outcomes.get(pid)
        check = verified.get(pid)
        proof = anchored.get(pid)
        if outcome is None:
            reason = "pending_outcome"
        elif check is None:
            reason = "not_run_verified"
        elif proof is None:
            reason = "no_external_anchor"
        elif outcome["conclusion"] not in {"success", "failure"}:
            reason = "nonbinary_outcome"
        elif _when(row["registered_at"], "registered_at") >= _when(
            check["run_created_at"], "run_created_at"
        ):
            reason = "late_prediction"
        else:
            reason = ""
        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1
            continue
        assert outcome is not None
        eligible.append((
            float(row["probability"]), int(outcome["conclusion"] == "success")
        ))
    n = len(eligible)
    brier = sum((p - y) ** 2 for p, y in eligible) / n if n else None
    if n < 20:
        verdict = "HOLD_INSUFFICIENT_EXTERNALLY_ANCHORED_HOLDOUT"
    elif brier is not None and brier < 0.25:
        verdict = "DESCRIPTIVE_LOWER_ERROR_NOT_VALIDATED"
    else:
        verdict = "DESCRIPTIVE_NO_IMPROVEMENT"
    return {
        "schema": "phios.predict.anchored_report.r0.4",
        "verdict": verdict,
        "holdout_scored": n,
        "holdout_excluded": excluded,
        "github_verified_count": len(verified),
        "public_comment_anchored_count": len(anchored),
        "candidate_mean_brier": brier,
        "fixed_half_baseline_mean_brier": 0.25 if n else None,
        "action_authority": False,
        "limits": (
            "GitHub public issue comment created_at and updated_at are independently "
            "fetched, not signed attestations. Existing comments can be edited or "
            "deleted after verification; a later audit should recheck. Historical "
            "selection and dependent CI outcomes can bias Brier scores. Even an "
            "externally earlier digest does not validate forecasts or grant authority."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=Path("phipredict-ledger.jsonl"))
    subs = parser.add_subparsers(dest="command", required=True)
    payload = subs.add_parser("anchor-payload", help="print body to post manually")
    payload.add_argument("--id", required=True)
    verify = subs.add_parser(
        "verify-anchor", help="read-only check of one GitHub public issue comment"
    )
    verify.add_argument("--id", required=True)
    verify.add_argument("--comment-id", required=True, type=int)
    verify.add_argument("--allow-public-network", action="store_true")
    subs.add_parser("anchored-report", help="offline scores for anchored holdout only")
    args = parser.parse_args(argv)
    try:
        if args.command == "anchor-payload":
            result = anchor_payload(args.ledger, prediction_id=args.id)
        elif args.command == "verify-anchor":
            result = verify_anchor(
                args.ledger, prediction_id=args.id, comment_id=args.comment_id,
                allow_public_network=args.allow_public_network,
            )
        else:
            result = anchored_report(args.ledger)
    except (PredictionContractError, OSError, ValueError) as exc:
        print(f"ΦPredict R0.4 HOLD: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
