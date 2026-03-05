"""Routing for shell commands and safe command passthrough."""

from __future__ import annotations

import os
import shlex
import subprocess
from typing import Sequence

from phios.shell.phi_commands import COMMANDS


def route_command(argv: Sequence[str], session: object | None = None) -> tuple[str, int]:
    """Route a command to a built-in handler or passthrough command."""
    if not argv:
        return "", 0

    cmd = argv[0]
    args = list(argv[1:])
    if cmd in ("exit", "quit"):
        return "exit", 0

    handler = COMMANDS.get(cmd)
    if handler is not None:
        try:
            return handler(args, session=session), 0
        except KeyboardInterrupt:
            return "", 0
        except (RuntimeError, ValueError, OSError) as exc:
            return f"Command error ({cmd}): {exc}", 1
        except Exception as exc:
            return f"Command error ({cmd}): {exc}", 1

    return run_fallback(" ".join(argv))


def _split_command(command: str) -> list[str]:
    if os.name == "nt":
        return shlex.split(command, posix=False)
    return shlex.split(command, posix=True)


def run_fallback(command: str) -> tuple[str, int]:
    """Run unknown command safely without invoking a shell."""
    try:
        argv = _split_command(command)
        if not argv:
            return "", 0
        proc = subprocess.run(argv, capture_output=True, text=True, check=False, shell=False)
        out = (proc.stdout or "") + (proc.stderr or "")
        return out.rstrip("\n"), proc.returncode
    except ValueError as exc:
        return f"Fallback parse error: {exc}", 1
    except OSError as exc:
        return f"Fallback execution error: {exc}", 1
