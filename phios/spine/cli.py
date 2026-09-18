from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runtime import PhiOSSpine


def _runtime(args: argparse.Namespace) -> PhiOSSpine:
    root = Path(args.state_root).expanduser() if args.state_root else None
    return PhiOSSpine(state_root=root, allowed_permissions=args.allow or ())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="phi-spine", description="PhiOS Spine v0.1")
    parser.add_argument("--state-root", help="Override ~/.phios/spine-v0.1")
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        metavar="PERMISSION",
        help="Explicitly grant one permission for this invocation (repeatable)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show the v0.1 spine state")
    sub.add_parser("list", help="List registered capabilities")

    run = sub.add_parser("run", help="Plan, authorize, execute, and receipt a capability")
    run.add_argument("capability_id")
    run.add_argument("--input", default="{}", help="JSON object payload")

    ledger = sub.add_parser("ledger", help="Show recent Reality Ledger receipts")
    ledger.add_argument("--limit", type=int, default=10)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    runtime = _runtime(args)

    if args.command == "status":
        print(json.dumps({
            "version": "0.1.0",
            "state_root": str(runtime.state_root),
            "capability_count": len(runtime.registry.list()),
            "ledger": str(runtime.ledger.path),
        }, indent=2))
        return 0

    if args.command == "list":
        print(json.dumps([item.to_dict() for item in runtime.registry.list()], indent=2))
        return 0

    if args.command == "run":
        payload = json.loads(args.input)
        if not isinstance(payload, dict):
            parser.error("--input must decode to a JSON object")
        receipt = runtime.run(args.capability_id, payload)
        print(json.dumps(receipt.to_dict(), indent=2))
        return 0 if receipt.execution_status == "succeeded" else 2

    if args.command == "ledger":
        print(json.dumps(runtime.ledger.recent(args.limit), indent=2))
        return 0

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
