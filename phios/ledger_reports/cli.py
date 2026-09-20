from __future__ import annotations

import argparse
import json
from pathlib import Path

from phios.mandala import AuthorityContext

from .observations import (
    ObservationReportService,
    ObservationSnapshotExporter,
    list_observation_reports,
)
from .queries import list_named_queries
from .service import LedgerReportService
from .snapshot import LedgerSnapshotExporter

DEFAULT_STATE_ROOT = Path.home() / ".phios" / "spine-v0.1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="phi-ledger",
        description="PhiOS derived Ledger snapshot surfaces",
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

    projection = sub.add_parser(
        "projection-build",
        help="Build one isolated DuckDB projection from a validated snapshot",
    )
    projection.add_argument("--snapshot-id", required=True)

    report = sub.add_parser(
        "report",
        help="Run one named read-only Ledger report against an existing projection",
    )
    report.add_argument("--snapshot-id", required=True)
    report.add_argument(
        "--name",
        required=True,
        choices=[item.name for item in list_named_queries()],
    )
    report.add_argument("--limit", type=int, default=100)

    sub.add_parser("report-list", help="List the closed named report catalog")

    sub.add_parser(
        "observation-export",
        help="Export allowlisted kernel/dispatch/reflex observations from fixed PhiOS stores",
    )
    sub.add_parser(
        "observation-report-list",
        help="List the closed observation report catalog",
    )
    observation_report = sub.add_parser(
        "observation-report",
        help="Run one closed report over an immutable observation snapshot",
    )
    observation_report.add_argument("--snapshot-id", required=True)
    observation_report.add_argument(
        "--name",
        required=True,
        choices=[name for name, _description in list_observation_reports()],
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

    if args.command == "report-list":
        print(
            json.dumps(
                [
                    {"name": item.name, "description": item.description}
                    for item in list_named_queries()
                ],
                indent=2,
            )
        )
        return 0

    if args.command == "observation-report-list":
        print(
            json.dumps(
                [
                    {"name": name, "description": description}
                    for name, description in list_observation_reports()
                ],
                indent=2,
            )
        )
        return 0

    if args.command == "observation-export":
        try:
            result = ObservationSnapshotExporter(
                state_root=Path(args.state_root)
            ).export(authority=authority)
        except (PermissionError, ValueError, RuntimeError, OSError) as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
            return 2
        print(json.dumps(result.to_dict(), indent=2))
        return 0

    if args.command == "observation-report":
        try:
            result = ObservationReportService(
                state_root=Path(args.state_root)
            ).run(
                snapshot_id=args.snapshot_id,
                report_name=args.name,
                authority=authority,
            )
        except (PermissionError, ValueError, RuntimeError, OSError) as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
            return 2
        print(json.dumps(result.to_dict(), indent=2))
        return 0

    service = LedgerReportService(state_root=Path(args.state_root))

    if args.command == "projection-build":
        try:
            projection_result = service.build_projection(
                snapshot_id=args.snapshot_id,
                authority=authority,
            )
        except (PermissionError, ValueError, RuntimeError, OSError) as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
            return 2
        print(json.dumps(projection_result.to_dict(), indent=2))
        return 0

    if args.command == "report":
        try:
            report_result = service.run_report(
                snapshot_id=args.snapshot_id,
                report_name=args.name,
                authority=authority,
                limit=args.limit,
            )
        except (PermissionError, ValueError, RuntimeError, OSError) as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
            return 2
        print(json.dumps(report_result.to_dict(), indent=2))
        return 0

    parser.error("unknown ledger command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
