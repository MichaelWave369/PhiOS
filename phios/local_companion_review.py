"""Offline review of PhiBuddy's native Council Lab report; never runs a model."""

import argparse
import hashlib
import json
from pathlib import Path

MAX_REPORT = 4 * 1024 * 1024
CASES = (
    ("literal", "Reply with only the exact string PHI369-ORBIT.", "PHI369-ORBIT"),
    ("arithmetic", "Reply with only the integer result of 17 multiplied by 23.", "391"),
    ("coding", "Propose a safe way to make a local SQLite backup. In two sentences, identify one limitation. Do not execute anything.", None),
)


def suite():
    return {"cases": [
        {"id": key, "prompt": prompt, "reference": ref}
        for key, prompt, ref in CASES
    ]}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def answer_metrics(row, requests, reference):
    if not isinstance(row, dict):
        raise ValueError("invalid answer")
    answer, elapsed, count = row.get("answer"), row.get("elapsed_ms"), row.get("model_requests")
    if (not isinstance(answer, str) or not answer.strip() or len(answer) > 200_000
            or type(elapsed) is not int or not 0 <= elapsed <= 2**63 - 1
            or type(count) is not int or count != requests):
        raise ValueError("invalid answer fields")
    return {
        "elapsed_ms": elapsed,
        "declared_requests": count,
        "exact_match": None if reference is None else answer.strip() == reference,
    }


def review(raw, depth):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_REPORT:
        raise ValueError("invalid report size")
    if depth not in ("quick", "debate"):
        raise ValueError("invalid depth")
    lines = raw.decode("utf-8").splitlines()
    if len(lines) != len(CASES):
        raise ValueError("missing or extra cases")
    rows = []
    for i, (line, (key, prompt, reference)) in enumerate(zip(lines, CASES)):
        row = json.loads(line, object_pairs_hook=unique_object)
        if (not isinstance(row, dict) or row.get("case_id") != key
                or row.get("prompt") != prompt or "reference" not in row
                or row["reference"] != reference or row.get("council_depth") != depth
                or row.get("order") != ("solo_first" if i % 2 == 0 else "council_first")):
            raise ValueError("case identity, order or depth mismatch")
        rows.append({
            "case_id": key,
            "solo": answer_metrics(row.get("solo"), 1, reference),
            "council": answer_metrics(row.get("council"), 4 if depth == "quick" else 7, reference),
        })
    return {
        "schema": "phios.local-intelligence.phibuddy-review.r03b",
        "status": "REPORT_STRUCTURE_MATCH_REVIEW_ONLY",
        "report_sha256": hashlib.sha256(raw).hexdigest(),
        "depth": depth,
        "cases": rows,
        "solo_declared_requests": sum(row["solo"]["declared_requests"] for row in rows),
        "council_declared_requests": sum(row["council"]["declared_requests"] for row in rows),
        "human_review_required": True,
        "native_execution_verified": False,
        "offline_execution_verified": False,
        "model_identity_verified": False,
        "superiority_verified": False,
        "authority_granted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("suite", help="print the fixed public case file")
    inspect = sub.add_parser("review", help="review explicitly selected native JSONL")
    inspect.add_argument("--report", required=True)
    inspect.add_argument("--depth", choices=("quick", "debate"), default="quick")
    args = parser.parse_args()
    if args.command == "suite":
        print(json.dumps(suite(), indent=2))
        return 0
    try:
        with Path(args.report).open("rb") as stream:
            report = review(stream.read(MAX_REPORT + 1), args.depth)
    except (OSError, ValueError, RecursionError):
        print(json.dumps({"status": "INVALID_OR_INCOMPLETE_REPORT"}))
        return 2
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
