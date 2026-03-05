"""Phi session entry points."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field

from phios.shell.phi_prompt import build_prompt
from phios.shell.phi_router import route_command


@dataclass
class PhiSession:
    started_at: float = field(default_factory=time.monotonic)
    commands_run: int = 0
    resonance_moments_hit: int = 0
    coherence_history: list[float] = field(default_factory=list)
    trajectory: str = "stable"

    def elapsed_seconds(self) -> int:
        return int(time.monotonic() - self.started_at)


def run_repl(session: PhiSession | None = None) -> int:
    current = session or PhiSession()
    while True:
        try:
            line = input(build_prompt())
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            return 0

        raw = line.strip()
        if not raw:
            continue

        current.commands_run += 1
        output, code = route_command(raw.split(), session=current)
        if output == "exit":
            return 0
        if output:
            print(output)
        if code != 0:
            print(f"(exit {code})")


def main(argv: list[str] | None = None) -> int:
    session = PhiSession()
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return run_repl(session)
    try:
        session.commands_run += 1
        output, code = route_command(args, session=session)
    except KeyboardInterrupt:
        return 0
    if output == "exit":
        return 0
    if output:
        print(output)
    return code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
