from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .acquisition import SourceAcquisitionRequest, SourceAcquisitionService
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

    return 2


if __name__ == "__main__":
    sys.exit(main())
