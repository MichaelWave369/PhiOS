"""Routing for shell commands."""

from __future__ import annotations

import os
import subprocess
from typing import Sequence

from phios.shell.phi_commands import COMMANDS


def route_command(argv: Sequence[str]) -> tuple[str, int]:
    if not argv:
        return "", 0

    cmd = argv[0]
    args = list(argv[1:])
    if cmd in ("exit", "quit"):
        return "exit", 0

    handler = COMMANDS.get(cmd)
    if handler is not None:
        try:
            return handler(args), 0
        except Exception as exc:
            return f"Command error ({cmd}): {exc}", 1

    return run_fallback(" ".join(argv))


def run_fallback(command: str) -> tuple[str, int]:
    shell_exec = os.environ.get("SHELL")
    try:
        if shell_exec:
            proc = subprocess.run(
                [shell_exec, "-lc", command], capture_output=True, text=True, check=False
            )
        else:
            proc = subprocess.run(command, shell=True, capture_output=True, text=True, check=False)
        out = (proc.stdout or "") + (proc.stderr or "")
        return out.rstrip("\n"), proc.returncode
    except Exception as exc:
        return f"Fallback shell error: {exc}", 1
