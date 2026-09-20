"""CLI for PhiReflex v0.1 shadow evaluation."""

from __future__ import annotations

import argparse
import json

from phios.reflex import PhiReflex, ReflexInput
from phios.reflex.providers import JevReflexProvider


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="phi-reflex",
        description="Run PhiReflex advisory classification in shadow mode.",
    )
    parser.add_argument("task", help="Task text to classify.")
    parser.add_argument(
        "--tool-intent",
        action="store_true",
        help="Declare that the task implies tool use.",
    )
    parser.add_argument(
        "--external-side-effect",
        action="store_true",
        help="Declare that the task requests an external side effect.",
    )
    parser.add_argument(
        "--rules-only",
        action="store_true",
        help="Disable the optional Jev shadow provider.",
    )
    args = parser.parse_args()

    shadow = None if args.rules_only else JevReflexProvider()
    receipt = PhiReflex(shadow=shadow).evaluate(
        ReflexInput(
            task_text=args.task,
            tool_intent=args.tool_intent,
            external_side_effect=args.external_side_effect,
        )
    )
    print(json.dumps(receipt.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
