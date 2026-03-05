"""Phi session entry points."""

from __future__ import annotations

import sys

from phios.shell.phi_prompt import build_prompt
from phios.shell.phi_router import route_command


def run_repl() -> int:
    while True:
        try:
            line = input(build_prompt())
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            continue

        raw = line.strip()
        if not raw:
            continue

        output, code = route_command(raw.split())
        if output == "exit":
            return 0
        if output:
            print(output)
        if code != 0:
            print(f"(exit {code})")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return run_repl()
    output, code = route_command(args)
    if output == "exit":
        return 0
    if output:
        print(output)
    return code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
