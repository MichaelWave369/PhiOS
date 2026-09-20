from __future__ import annotations

import argparse
import json
from pathlib import Path

from phios.mandala import AuthorityContext

from .snapshot import LedgerSnapshotExporter

DEFAULT_STATE_ROOT = Path.home() / ".phios" / "spine-v0.1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="phi-analytics",
        description="PhiOS derived Ledger analytics surfaces",
    )
    parser.add_argument("--state-root", default=str(DEFAULT_STATE_ROOT))
    parser.add_argument("--allow", action="append", default=[], metavar="PERMISSION")
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser(
        "snapshot-export",
        help="Export a stable, visibility-filtered snapshot of canonical Ledger streams",
    )
    export.add_argument(
        "--output-root",
        help="Override the derived snapshot directory",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    permissions = tuple(dict.fromkeys(args.allow))
    authority = AuthorityContext(ceiling=permissions, grants=permissions)

    if args.command == "snapshot-export":
        exporter = LedgerSnapshotExporter(
            state_root=Path(args.state_root),
            output_root=Path(args.output_root) if args.output_root else None,
        )
        try:
            snapshot = exporter.export(authority=authority)
        except (PermissionError, ValueError, RuntimeError, OSError) as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
            return 2
        print(json.dumps(snapshot.to_dict(), indent=2))
        return 0

    parser.error("unknown analytics command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
