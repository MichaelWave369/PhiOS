from __future__ import annotations

import argparse
import json
from pathlib import Path

from phios.mandala import MANDALA_CONTRACT_VERSION, Gate, MandalaStatus

from . import __version__ as SPINE_VERSION
from .runtime import PhiOSSpine


def _runtime(args: argparse.Namespace) -> PhiOSSpine:
    root = Path(args.state_root).expanduser() if args.state_root else None
    return PhiOSSpine(state_root=root, allowed_permissions=args.allow or ())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="phi-spine", description="PhiOS Spine v0.4")
    parser.add_argument("--state-root", help="Override the PhiOS Spine local state root")
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        metavar="PERMISSION",
        help="Explicitly grant one permission for this invocation (repeatable)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show the v0.4 spine and Mandala contract state")
    sub.add_parser("list", help="List registered capabilities")

    perceive = sub.add_parser(
        "perceive",
        help="Admit text through the SOMA North Gate with native provenance",
    )
    perceive.add_argument("--source-id", required=True)
    perceive.add_argument("--text", required=True)
    perceive.add_argument(
        "--transform",
        action="append",
        default=[],
        choices=["strip_utf8_bom", "normalize_newlines"],
        help="Apply one deterministic recovery transform (repeatable)",
    )

    perceive_file = sub.add_parser(
        "perceive-file",
        help="Acquire one bounded text-like file through the SOMA North Gate",
    )
    perceive_file.add_argument("--root", required=True, help="Explicit source root")
    perceive_file.add_argument("--path", required=True, help="Path relative to --root")
    perceive_file.add_argument("--max-bytes", type=int, default=1_048_576)
    perceive_file.add_argument(
        "--transform",
        action="append",
        default=[],
        choices=["strip_utf8_bom", "normalize_newlines"],
        help="Apply one deterministic recovery transform (repeatable)",
    )

    run = sub.add_parser("run", help="Plan, authorize, execute, and receipt a capability")
    run.add_argument("capability_id")
    run.add_argument("--input", default="{}", help="JSON object payload")

    ledger = sub.add_parser("ledger", help="Show recent legacy execution receipts")
    ledger.add_argument("--limit", type=int, default=10)

    mandala = sub.add_parser("mandala-ledger", help="Show recent typed Mandala receipts")
    mandala.add_argument("--limit", type=int, default=10)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    runtime = _runtime(args)

    if args.command == "status":
        print(
            json.dumps(
                {
                    "version": SPINE_VERSION,
                    "state_root": str(runtime.state_root),
                    "capability_count": len(runtime.registry.list()),
                    "legacy_ledger": str(runtime.ledger.path),
                    "mandala_ledger": str(runtime.mandala_ledger.path),
                    "native_evidence_root": str(runtime.soma.evidence.root),
                    "mandala_contract": MANDALA_CONTRACT_VERSION,
                    "task_id": runtime.core.task_id,
                    "core_lifecycle": runtime.core.lifecycle.value,
                    "gates": [gate.value for gate in Gate],
                    "statuses": [status.value for status in MandalaStatus],
                    "north_gate": "soma.text.v0.1+soma.file.v0.1",
                },
                indent=2,
            )
        )
        return 0

    if args.command == "list":
        print(json.dumps([item.to_dict() for item in runtime.registry.list()], indent=2))
        return 0

    if args.command == "perceive":
        result = runtime.perceive_text(
            source_id=args.source_id,
            text=args.text,
            transforms=tuple(args.transform),
        )
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.receipt.status in {MandalaStatus.ACCEPTED, MandalaStatus.DEGRADED} else 2

    if args.command == "perceive-file":
        file_result = runtime.perceive_file(
            source_root=Path(args.root).expanduser(),
            relative_path=args.path,
            transforms=tuple(args.transform),
            max_bytes=args.max_bytes,
        )
        print(json.dumps(file_result.to_dict(), indent=2))
        return (
            0
            if file_result.receipt.status in {MandalaStatus.ACCEPTED, MandalaStatus.DEGRADED}
            else 2
        )

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

    if args.command == "mandala-ledger":
        print(json.dumps(runtime.mandala_ledger.recent(args.limit), indent=2))
        return 0

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
