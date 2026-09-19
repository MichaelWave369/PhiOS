from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .acquisition import (
    SourceAcquisitionRequest,
    SourceAcquisitionService,
    review_intake_for_acquisition,
)
from .build_execution import BuildExecutionRequest, BuildExecutionService
from .build_plan import plan_build_from_payloads, review_build_plan
from .intake import inspect_public_github_app

_MAX_INTAKE_RESULT_BYTES = 2 * 1024 * 1024


def _load_json_file(path: Path) -> Any:
    source = path.expanduser().resolve()
    size = source.stat().st_size
    if size > _MAX_INTAKE_RESULT_BYTES:
        raise ValueError("Intake result JSON exceeds the bounded input size")
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid intake result JSON: {exc.msg}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="phi-app",
        description="PhiOS App Platform utilities.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect-github",
        help="Read a bounded public GitHub repository snapshot and propose app metadata.",
    )
    inspect_parser.add_argument("repository_url")

    review_parser = subparsers.add_parser(
        "review-intake",
        help="Show the exact commit and manifest digest that must be approved for acquisition.",
    )
    review_parser.add_argument("intake_json", type=Path)

    acquire_parser = subparsers.add_parser(
        "acquire-github",
        help="Acquire one explicitly approved intake result at its exact commit SHA.",
    )
    acquire_parser.add_argument("intake_json", type=Path)
    acquire_parser.add_argument("--approve-commit-sha", required=True)
    acquire_parser.add_argument("--approve-manifest-sha", required=True)
    acquire_parser.add_argument(
        "--workspace-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "source",
    )
    acquire_parser.add_argument("--receipt-root", type=Path, default=None)

    plan_parser = subparsers.add_parser(
        "plan-build",
        help="Create a deterministic non-executing build plan from intake + acquisition receipt.",
    )
    plan_parser.add_argument("intake_json", type=Path)
    plan_parser.add_argument("acquisition_receipt_json", type=Path)

    review_plan_parser = subparsers.add_parser(
        "review-build-plan",
        help="Validate and expose the exact digest and requested authority of a build plan.",
    )
    review_plan_parser.add_argument("build_plan_json", type=Path)

    execute_parser = subparsers.add_parser(
        "execute-build",
        help="Execute one explicitly approved build plan in an isolated working copy.",
    )
    execute_parser.add_argument("build_plan_json", type=Path)
    execute_parser.add_argument("acquisition_receipt_json", type=Path)
    execute_parser.add_argument("--approve-plan-sha", required=True)
    execute_parser.add_argument("--approve-source-sha", required=True)
    execute_parser.add_argument(
        "--allow-build-permission",
        action="append",
        default=[],
        dest="build_permissions",
    )
    execute_parser.add_argument(
        "--execution-root",
        type=Path,
        default=Path.home() / ".phios" / "apps" / "builds",
    )
    execute_parser.add_argument("--receipt-root", type=Path, default=None)
    execute_parser.add_argument("--step-timeout-seconds", type=int, default=900)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "inspect-github":
        try:
            result = inspect_public_github_app(args.repository_url)
        except ValueError as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(result.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "review-intake":
        try:
            payload = _load_json_file(args.intake_json)
            review = review_intake_for_acquisition(payload)
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(review.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "acquire-github":
        try:
            payload = _load_json_file(args.intake_json)
            request = SourceAcquisitionRequest.from_intake_payload(
                payload,
                approved_commit_sha=args.approve_commit_sha,
                approved_manifest_sha256=args.approve_manifest_sha,
            )
            receipt = SourceAcquisitionService().acquire(
                request,
                workspace_root=args.workspace_root,
                receipt_root=args.receipt_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(receipt.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "plan-build":
        try:
            intake_payload = _load_json_file(args.intake_json)
            receipt_payload = _load_json_file(args.acquisition_receipt_json)
            plan = plan_build_from_payloads(intake_payload, receipt_payload)
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(plan.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "review-build-plan":
        try:
            payload = _load_json_file(args.build_plan_json)
            build_review = review_build_plan(payload)
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(build_review.to_dict(), sort_keys=True, indent=2))
        return 0

    if args.command == "execute-build":
        try:
            plan_payload = _load_json_file(args.build_plan_json)
            receipt_payload = _load_json_file(args.acquisition_receipt_json)
            execution_request = BuildExecutionRequest.from_payloads(
                plan_payload,
                receipt_payload,
                approved_plan_sha256=args.approve_plan_sha,
                approved_source_snapshot_sha256=args.approve_source_sha,
                approved_permissions=tuple(args.build_permissions),
            )
            execution = BuildExecutionService(
                step_timeout_seconds=args.step_timeout_seconds,
            ).execute(
                execution_request,
                execution_root=args.execution_root,
                receipt_root=args.receipt_root,
            )
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
            return 2
        print(json.dumps(execution.to_dict(), sort_keys=True, indent=2))
        return 0 if execution.status in {"success", "no_build_required"} else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
