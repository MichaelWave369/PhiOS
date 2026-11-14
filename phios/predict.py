"""ΦPredict R0.1: offline, operator-controlled CI prediction ledger.

A prediction is committed before a workflow starts, then compared against an
operator-supplied, saved GitHub Actions workflow-run JSON document. Receipts
are locally hash-chained but neither signed nor independently time-attested.
No network, model execution, action authority, or automatic retraining.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "phios.predict.event.r0.1"
MAX_LEDGER_BYTES = 8_000_000
MAX_EVIDENCE_BYTES = 2_000_000
SHA_RE = re.compile(r"^[a-fA-F0-9]{40}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
CONCLUSIONS = {
    "success", "failure", "cancelled", "timed_out", "action_required",
    "neutral", "skipped", "stale", "startup_failure",
}
FIELDS = {"schema", "sequence", "previous_sha256", "kind", "data", "sha256"}
PREDICTION_FIELDS = {
    "id", "repo", "head_sha", "workflow", "probability", "cohort", "registered_at",
}
OUTCOME_FIELDS = {
    "prediction_id", "run_id", "conclusion", "run_started_at", "source_url",
    "source_sha256", "observed_at",
}
GITHUB_VERIFICATION_FIELDS = {
    "prediction_id", "run_id", "api_sha256", "checked_at", "run_created_at", "run_attempt",
}


class PredictionContractError(ValueError):
    """Malformed, untrusted, contradictory, or non-admissible ledger evidence."""


def _canonical(obj: Any) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _digest(obj: Any) -> str:
    return hashlib.sha256(_canonical(obj)).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _when(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise PredictionContractError(f"{field} must be an offset-aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PredictionContractError(f"{field} is not ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PredictionContractError(f"{field} requires an explicit UTC offset")
    return parsed.astimezone(timezone.utc)


def _exact_keys(obj: Any, required: set[str], field: str) -> Mapping[str, Any]:
    if not isinstance(obj, dict) or set(obj) != required:
        raise PredictionContractError(f"{field} requires exactly {sorted(required)}")
    return obj


def _check_prediction(data: Any) -> Mapping[str, Any]:
    row = _exact_keys(data, PREDICTION_FIELDS, "prediction")
    if not isinstance(row["id"], str) or not ID_RE.fullmatch(row["id"]):
        raise PredictionContractError("invalid prediction id")
    if not isinstance(row["repo"], str) or not REPO_RE.fullmatch(row["repo"]):
        raise PredictionContractError("invalid owner/repo")
    if not isinstance(row["head_sha"], str) or not SHA_RE.fullmatch(row["head_sha"]):
        raise PredictionContractError("head_sha must be 40 hexadecimal characters")
    if (
        not isinstance(row["workflow"], str)
        or not row["workflow"].strip()
        or len(row["workflow"]) > 128
    ):
        raise PredictionContractError("workflow must be a short nonempty name")
    p = row["probability"]
    if isinstance(p, bool) or not isinstance(p, (float, int)):
        raise PredictionContractError("probability must be a number, not a boolean")
    if not math.isfinite(p) or not (0 <= p <= 1):
        raise PredictionContractError("probability must be finite and within [0, 1]")
    if not isinstance(row["cohort"], str) or row["cohort"] not in {"pilot", "holdout"}:
        raise PredictionContractError("cohort must be pilot or holdout")
    _when(row["registered_at"], "registered_at")
    return row


def _check_outcome(data: Any) -> Mapping[str, Any]:
    row = _exact_keys(data, OUTCOME_FIELDS, "outcome")
    if not isinstance(row["prediction_id"], str) or not ID_RE.fullmatch(
        row["prediction_id"]
    ):
        raise PredictionContractError("invalid outcome prediction id")
    if isinstance(row["run_id"], bool) or not isinstance(row["run_id"], int):
        raise PredictionContractError("run_id must be a positive integer")
    if (
        row["run_id"] <= 0
        or not isinstance(row["conclusion"], str)
        or row["conclusion"] not in CONCLUSIONS
    ):
        raise PredictionContractError("invalid run id or workflow conclusion")
    if (
        not isinstance(row["source_sha256"], str)
        or not re.fullmatch(r"[a-f0-9]{64}", row["source_sha256"])
    ):
        raise PredictionContractError("source digest must be lowercase SHA-256")
    if not isinstance(row["source_url"], str):
        raise PredictionContractError("source_url must be a string")
    if _when(row["run_started_at"], "run_started_at") > _when(
        row["observed_at"], "observed_at"
    ):
        raise PredictionContractError("workflow start is later than local observation")
    return row


def _check_github_verification(data: Any) -> Mapping[str, Any]:
    row = _exact_keys(data, GITHUB_VERIFICATION_FIELDS, "github_verification")
    if not isinstance(row["prediction_id"], str) or not ID_RE.fullmatch(
        row["prediction_id"]
    ):
        raise PredictionContractError("invalid verified prediction id")
    if type(row["run_id"]) is not int or row["run_id"] <= 0:
        raise PredictionContractError("invalid verified workflow run id")
    if (
        not isinstance(row["api_sha256"], str)
        or not re.fullmatch(r"[a-f0-9]{64}", row["api_sha256"])
    ):
        raise PredictionContractError("invalid GitHub API response hash")
    if type(row["run_attempt"]) is not int or row["run_attempt"] != 1:
        raise PredictionContractError("reruns not supported for R0.2 verification")
    _when(row["checked_at"], "checked_at")
    _when(row["run_created_at"], "run_created_at")
    return row


def _replay(events: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    predictions: dict[str, Any] = {}
    outcomes: dict[str, Any] = {}
    targets: set[tuple[str, str, str]] = set()
    run_ids: set[int] = set()
    verified_ids: set[str] = set()
    for event in events:
        kind = event["kind"]
        if kind == "prediction":
            row = _check_prediction(event["data"])
            target = (row["repo"], row["head_sha"].lower(), row["workflow"])
            if row["id"] in predictions or target in targets:
                raise PredictionContractError("duplicate prediction id or workflow target")
            predictions[row["id"]] = row
            targets.add(target)
        elif kind == "outcome":
            row = _check_outcome(event["data"])
            pid = row["prediction_id"]
            if pid not in predictions:
                raise PredictionContractError("outcome without earlier prediction")
            if pid in outcomes or row["run_id"] in run_ids:
                raise PredictionContractError("duplicate outcome or workflow run")
            repo = predictions[pid]["repo"]
            expected_url = (
                f"https://github.com/{repo}/actions/runs/{row['run_id']}"
            )
            if row["source_url"] != expected_url:
                raise PredictionContractError("outcome source URL does not match target")
            outcomes[pid] = row
            run_ids.add(row["run_id"])
        elif kind == "github_verification":
            row = _check_github_verification(event["data"])
            pid = row["prediction_id"]
            if pid not in outcomes:
                raise PredictionContractError("verification without earlier observation")
            if pid in verified_ids:
                raise PredictionContractError("duplicate GitHub verification")
            if row["run_id"] != outcomes[pid]["run_id"]:
                raise PredictionContractError("GitHub verification run ID mismatch")
            started = _when(outcomes[pid]["run_started_at"], "run_started_at")
            created = _when(row["run_created_at"], "run_created_at")
            checked = _when(row["checked_at"], "checked_at")
            if created > started or checked < started:
                raise PredictionContractError("invalid GitHub verification chronology")
            verified_ids.add(pid)
        else:
            raise PredictionContractError("unsupported event kind")
    return predictions, outcomes


def load_ledger(path: Path) -> list[dict[str, Any]]:
    """Verify each hash and the full semantic sequence before using the ledger."""
    if not path.exists():
        return []
    if path.stat().st_size > MAX_LEDGER_BYTES:
        raise PredictionContractError("ledger exceeds R0.1 size limit")
    events: list[dict[str, Any]] = []
    previous = "0" * 64
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    raise PredictionContractError("blank ledger event")
                obj = json.loads(line)
                event = _exact_keys(obj, FIELDS, "event")
                if event["schema"] != SCHEMA:
                    raise PredictionContractError("event schema mismatch")
                if type(event["sequence"]) is not int or event["sequence"] != len(events) + 1:
                    raise PredictionContractError("nonsequential ledger event")
                if event["previous_sha256"] != previous:
                    raise PredictionContractError("broken event hash chain")
                if not isinstance(event["sha256"], str):
                    raise PredictionContractError("event digest missing")
                expected = _digest({key: event[key] for key in FIELDS - {"sha256"}})
                if not hmac.compare_digest(event["sha256"], expected):
                    raise PredictionContractError("tampered or invalid ledger event")
                previous = expected
                events.append(dict(event))
    except (UnicodeError, json.JSONDecodeError, OSError) as exc:
        raise PredictionContractError("cannot parse or read ledger") from exc
    _replay(events)
    return events


def _append(path: Path, kind: str, data: Mapping[str, Any]) -> dict[str, Any]:
    """Atomic replacement under a fail-closed local exclusive lock.

    The ledger is logically append-only; rewriting is an implementation detail.
    A stale lock after a crash requires manual inspection and removal.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".lock")
    try:
        lock_fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise PredictionContractError("ledger locked; inspect before removing stale lock") from exc
    tmp_path: str | None = None
    try:
        os.close(lock_fd)
        events = load_ledger(path)
        previous = events[-1]["sha256"] if events else "0" * 64
        event: dict[str, Any] = {
            "schema": SCHEMA,
            "sequence": len(events) + 1,
            "previous_sha256": previous,
            "kind": kind,
            "data": dict(data),
        }
        event["sha256"] = _digest(event)
        new_events = events + [event]
        _replay(new_events)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False,
            prefix=".phipredict-", suffix=".tmp"
        ) as stream:
            tmp_path = stream.name
            for item in new_events:
                stream.write(_canonical(item).decode("utf-8") + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        if os.path.getsize(tmp_path) > MAX_LEDGER_BYTES:
            raise PredictionContractError("ledger would exceed R0.1 size limit")
        os.replace(tmp_path, path)
        tmp_path = None
        return event
    finally:
        if tmp_path is not None:
            Path(tmp_path).unlink(missing_ok=True)
        lock.unlink(missing_ok=True)


def register(
    path: Path,
    *,
    prediction_id: str,
    repo: str,
    head_sha: str,
    workflow: str,
    probability: float,
    cohort: str = "pilot",
) -> dict[str, Any]:
    data = {
        "id": prediction_id,
        "repo": repo,
        "head_sha": head_sha.lower(),
        "workflow": workflow,
        "probability": probability,
        "cohort": cohort,
        "registered_at": _now(),
    }
    _check_prediction(data)
    return _append(path, "prediction", data)


def observe(path: Path, *, prediction_id: str, run_json: Path) -> dict[str, Any]:
    """Ingest saved GitHub Actions API JSON; never fetch or trigger a workflow."""
    predictions, outcomes = _replay(load_ledger(path))
    if prediction_id not in predictions or prediction_id in outcomes:
        raise PredictionContractError("unknown or already observed prediction")
    if run_json.stat().st_size > MAX_EVIDENCE_BYTES:
        raise PredictionContractError("evidence file exceeds R0.1 size limit")
    raw = run_json.read_bytes()
    try:
        payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PredictionContractError("invalid GitHub run JSON") from exc
    if not isinstance(payload, dict):
        raise PredictionContractError("GitHub run document must be an object")
    prediction = predictions[prediction_id]
    repo_obj = payload.get("repository")
    repo = repo_obj.get("full_name") if isinstance(repo_obj, dict) else None
    if (
        repo != prediction["repo"]
        or payload.get("head_sha") != prediction["head_sha"]
        or payload.get("name") != prediction["workflow"]
    ):
        raise PredictionContractError("workflow run identity does not match prediction")
    run_id = payload.get("id")
    if type(run_id) is not int or run_id <= 0:
        raise PredictionContractError("missing numeric workflow run id")
    if payload.get("status") != "completed":
        raise PredictionContractError("workflow run is not completed")
    conclusion = payload.get("conclusion")
    if conclusion not in CONCLUSIONS:
        raise PredictionContractError("unknown workflow run conclusion")
    source_url = payload.get("html_url")
    expected = f"https://github.com/{prediction['repo']}/actions/runs/{run_id}"
    if source_url != expected:
        raise PredictionContractError("GitHub run URL and id mismatch")
    started = payload.get("run_started_at")
    _when(started, "run_started_at")
    data = {
        "prediction_id": prediction_id,
        "run_id": run_id,
        "conclusion": conclusion,
        "run_started_at": started,
        "source_url": source_url,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "observed_at": _now(),
    }
    return _append(path, "outcome", data)


def report(path: Path) -> dict[str, Any]:
    events = load_ledger(path)
    predictions, outcomes = _replay(events)
    cohort_scores: list[tuple[float, int]] = []
    excluded: dict[str, int] = {}
    for pid, outcome in outcomes.items():
        prediction = predictions[pid]
        if prediction["cohort"] != "holdout":
            continue
        if _when(prediction["registered_at"], "registered_at") >= _when(
            outcome["run_started_at"], "run_started_at"
        ):
            reason = "late_or_unverified_pre_run"
        elif outcome["conclusion"] not in {"success", "failure"}:
            reason = "nonbinary_outcome"
        else:
            reason = ""
        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1
            continue
        cohort_scores.append(
            (float(prediction["probability"]), int(outcome["conclusion"] == "success"))
        )
    n = len(cohort_scores)
    brier = sum((p - y) ** 2 for p, y in cohort_scores) / n if n else None
    bins: list[dict[str, Any]] = []
    for index in range(5):
        group = [(p, y) for p, y in cohort_scores if min(4, int(p * 5)) == index]
        bins.append({
            "probability_from": index / 5,
            "probability_to": (index + 1) / 5,
            "count": len(group),
            "mean_prediction": sum(p for p, _ in group) / len(group) if group else None,
            "observed_success_rate": sum(y for _, y in group) / len(group) if group else None,
        })
    if n < 20:
        verdict = "HOLD_INSUFFICIENT_HOLDOUT"
    elif brier is not None and brier < 0.25:
        verdict = "DESCRIPTIVE_LOWER_ERROR_NOT_VALIDATED"
    else:
        verdict = "DESCRIPTIVE_NO_IMPROVEMENT"
    return {
        "schema": "phios.predict.report.r0.1",
        "verdict": verdict,
        "predictions": len(predictions),
        "observations": len(outcomes),
        "pending": len(predictions) - len(outcomes),
        "holdout_scored": n,
        "holdout_excluded": excluded,
        "candidate_mean_brier": brier,
        "fixed_half_baseline_mean_brier": 0.25 if n else None,
        "candidate_minus_baseline": brier - 0.25 if brier is not None else None,
        "calibration_bins": bins,
        "event_chain_head": events[-1]["sha256"] if events else None,
        "action_authority": False,
        "evidence_limit": (
            "Operator-supplied GitHub JSON and local timestamps are not "
            "independently authenticated; a local SHA chain is not a trusted timestamp."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=Path("phipredict-ledger.jsonl"))
    subs = parser.add_subparsers(dest="command", required=True)
    reg = subs.add_parser("register", help="commit a pre-run prediction")
    reg.add_argument("--id", required=True)
    reg.add_argument("--repo", required=True)
    reg.add_argument("--sha", required=True)
    reg.add_argument("--workflow", required=True)
    reg.add_argument("--probability", required=True, type=float)
    reg.add_argument("--cohort", choices=["pilot", "holdout"], default="pilot")
    obs = subs.add_parser("observe", help="ingest saved GitHub run JSON")
    obs.add_argument("--id", required=True)
    obs.add_argument("--run-json", required=True, type=Path)
    subs.add_parser("verify", help="validate the local hash chain and event sequence")
    subs.add_parser("report", help="print descriptive prediction calibration")
    args = parser.parse_args(argv)
    try:
        if args.command == "register":
            result = register(
                args.ledger, prediction_id=args.id, repo=args.repo, head_sha=args.sha,
                workflow=args.workflow, probability=args.probability, cohort=args.cohort,
            )
        elif args.command == "observe":
            result = observe(args.ledger, prediction_id=args.id, run_json=args.run_json)
        elif args.command == "verify":
            events = load_ledger(args.ledger)
            result = {
                "verified_events": len(events),
                "head": events[-1]["sha256"] if events else None,
                "authority": False,
            }
        else:
            result = report(args.ledger)
    except (PredictionContractError, OSError, ValueError) as exc:
        print(f"ΦPredict HOLD: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
