"""ΦPredict R0.2: explicit, read-only verification of public GitHub workflow runs.

This module does not trigger workflows or write to GitHub. It adds a hash-linked
verification event only after comparing a public GitHub Actions API response
with an already recorded R0.1 observation. Fetching is OFF by default.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
    _canonical,
    _now,
    _replay,
    _when,
    load_ledger,
)

VERIFY_FIELDS = {
    "prediction_id",
    "run_id",
    "api_sha256",
    "checked_at",
    "run_created_at",
    "run_attempt",
}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> None:
        raise PredictionContractError("GitHub API redirect refused")


def _fetch_public_run(url: str) -> bytes:
    """Fetch ONE canonical public GitHub API path without proxies or redirects."""
    if not url.startswith("https://api.github.com/repos/"):
        raise PredictionContractError("only the public GitHub API is permitted")
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "PhiOS-PhiPredict/0.2-read-only",
        },
        method="GET",
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _NoRedirect()
    )
    try:
        with opener.open(request, timeout=10) as response:
            if response.geturl() != url:
                raise PredictionContractError("unexpected GitHub API response URL")
            content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
            if content_type not in {"application/json", "application/vnd.github+json"}:
                raise PredictionContractError("GitHub response is not JSON")
            raw = response.read(MAX_EVIDENCE_BYTES + 1)
    except (urllib.error.URLError, OSError) as exc:
        raise PredictionContractError("public GitHub API fetch failed") from exc
    if len(raw) > MAX_EVIDENCE_BYTES:
        raise PredictionContractError("GitHub API response exceeds evidence limit")
    return raw


def verify_github_run(
    path: Path, *, prediction_id: str, allow_public_network: bool = False
) -> dict[str, Any]:
    """Verify an existing observation against the live PUBLIC GitHub Actions API.

    Only the exact public GitHub endpoint derived from a validated ledger target
    is fetched. The operator must explicitly approve this one read-only call.
    """
    if not allow_public_network:
        raise PredictionContractError("public network access requires explicit approval")
    events = load_ledger(path)
    predictions, outcomes = _replay(events)
    if prediction_id not in predictions or prediction_id not in outcomes:
        raise PredictionContractError("prediction needs a recorded outcome first")
    if any(
        event["kind"] == "github_verification"
        and event["data"]["prediction_id"] == prediction_id
        for event in events
    ):
        raise PredictionContractError("GitHub run already verified in this ledger")

    prediction = predictions[prediction_id]
    outcome = outcomes[prediction_id]
    repo = prediction["repo"]
    run_id = outcome["run_id"]
    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}"
    raw = _fetch_public_run(url)
    try:
        payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PredictionContractError("GitHub returned malformed JSON") from exc
    if not isinstance(payload, dict):
        raise PredictionContractError("GitHub response is not an object")

    source_repo = payload.get("repository")
    source_repo_name = (
        source_repo.get("full_name") if isinstance(source_repo, dict) else None
    )
    expected_url = f"https://github.com/{repo}/actions/runs/{run_id}"
    identity_matches = (
        type(payload.get("id")) is int
        and payload["id"] == run_id
        and source_repo_name == repo
        and payload.get("head_sha") == prediction["head_sha"]
        and payload.get("name") == prediction["workflow"]
        and payload.get("html_url") == expected_url
    )
    if not identity_matches:
        raise PredictionContractError("GitHub API run identity mismatch")
    if payload.get("status") != "completed":
        raise PredictionContractError("GitHub API run is not completed")
    if payload.get("conclusion") != outcome["conclusion"]:
        raise PredictionContractError("GitHub outcome differs from stored observation")

    attempt = payload.get("run_attempt")
    if type(attempt) is not int or attempt != 1:
        raise PredictionContractError("reruns or missing run_attempt are not supported in R0.2")

    created = _when(payload.get("created_at"), "github_created_at")
    started = _when(payload.get("run_started_at"), "github_run_started_at")
    observed_start = _when(outcome["run_started_at"], "observed_run_started_at")
    checked = datetime.now(timezone.utc)
    if created > started or started > checked:
        raise PredictionContractError("contradictory GitHub workflow timestamps")
    if started != observed_start:
        raise PredictionContractError("GitHub workflow start differs from observation")
    record = {
        "prediction_id": prediction_id,
        "run_id": run_id,
        "api_sha256": hashlib.sha256(raw).hexdigest(),
        "checked_at": _now(),
        "run_created_at": payload["created_at"],
        "run_attempt": attempt,
    }
    return _append(path, "github_verification", record)


def verified_report(path: Path) -> dict[str, Any]:
    """Score only independently checked GitHub run IDs with pre-creation timing.

    Source verification is an HTTPS/API observation, NOT an external signed
    commitment of the local prediction or proof of prediction independence.
    """
    events = load_ledger(path)
    predictions, outcomes = _replay(events)
    verified = {
        event["data"]["prediction_id"]: event["data"]
        for event in events
        if event["kind"] == "github_verification"
    }
    scores: list[tuple[float, int]] = []
    excluded: dict[str, int] = {}
    for prediction_id, prediction in predictions.items():
        if prediction["cohort"] != "holdout" or prediction_id not in outcomes:
            continue
        outcome = outcomes[prediction_id]
        receipt = verified.get(prediction_id)
        if receipt is None:
            reason = "not_independently_checked"
        elif _when(prediction["registered_at"], "registered_at") >= _when(
            receipt["run_created_at"], "run_created_at"
        ):
            reason = "late_after_github_run_creation"
        elif outcome["conclusion"] not in {"success", "failure"}:
            reason = "nonbinary_outcome"
        else:
            reason = ""
        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1
            continue
        scores.append(
            (float(prediction["probability"]), int(outcome["conclusion"] == "success"))
        )
    count = len(scores)
    brier = sum((p - y) ** 2 for p, y in scores) / count if count else None
    if count < 20:
        verdict = "HOLD_INSUFFICIENT_VERIFIED_HOLDOUT"
    elif brier is not None and brier < 0.25:
        verdict = "DESCRIPTIVE_LOWER_ERROR_NOT_VALIDATED"
    else:
        verdict = "DESCRIPTIVE_NO_IMPROVEMENT"
    return {
        "schema": "phios.predict.verified_report.r0.2",
        "verdict": verdict,
        "prediction_count": len(predictions),
        "observation_count": len(outcomes),
        "github_checked_count": len(verified),
        "verified_holdout_scored": count,
        "verified_holdout_excluded": excluded,
        "verified_candidate_mean_brier": brier,
        "fixed_half_baseline_mean_brier": 0.25 if count else None,
        "verified_candidate_minus_baseline": (
            brier - 0.25 if brier is not None else None
        ),
        "action_authority": False,
        "source_limit": (
            "Public GitHub HTTPS/API response is checked at one point in time; "
            "local prediction timestamps and ledger custody are not authenticated. "
            "A matching source is not proof of a truly preregistered forecast."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=Path("phipredict-ledger.jsonl"))
    subs = parser.add_subparsers(dest="command", required=True)
    verify = subs.add_parser("verify-github", help="explicitly check one public GitHub run")
    verify.add_argument("--id", required=True)
    verify.add_argument(
        "--allow-public-network", action="store_true",
        help="approve a single read-only GET to api.github.com",
    )
    subs.add_parser("verified-report", help="score only public-API-checked holdout runs")
    args = parser.parse_args(argv)
    try:
        if args.command == "verify-github":
            result = verify_github_run(
                args.ledger, prediction_id=args.id,
                allow_public_network=args.allow_public_network,
            )
        else:
            result = verified_report(args.ledger)
    except (PredictionContractError, OSError, ValueError) as exc:
        print(f"ΦPredict R0.2 HOLD: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
