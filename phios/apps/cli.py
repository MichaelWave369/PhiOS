from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .intake import inspect_public_github_app


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

    return 2


if __name__ == "__main__":
    sys.exit(main())
