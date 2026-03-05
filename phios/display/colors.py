"""ANSI color helpers."""

from __future__ import annotations

import sys


ANSI_RESET = "\033[0m"
ANSI_PHI = "\033[95m"


def supports_color() -> bool:
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def colorize_phi(text: str) -> str:
    if supports_color():
        return f"{ANSI_PHI}{text}{ANSI_RESET}"
    return text
