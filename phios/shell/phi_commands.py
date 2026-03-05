"""Command implementations."""

from __future__ import annotations

import os
import platform
from datetime import datetime
from typing import Callable

from phios import __version__
from phios.core.brainc_client import OLLAMA_URL, ollama_available
from phios.core.lt_engine import compute_lt
from phios.core.sovereignty import export_snapshot, verify_snapshot
from phios.core.tbrc_bridge import tbrc_connected

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None


CommandHandler = Callable[[list[str]], str]


def cmd_help(_: list[str]) -> str:
    return "\n".join(
        [
            "Commands:",
            "  help                  Show this help",
            "  version               Show PhiOS version info",
            "  status                Show local system status",
            "  coherence             Compute L(t) coherence",
            "  sovereign export P    Export sovereign snapshot",
            "  sovereign verify P    Verify sovereign snapshot",
            "  brainc status         Check local Ollama status",
            "  tbrc status           Check TBRC bridge status",
            "  memory status         Memory lattice placeholder",
            "  archive status        Archive placeholder",
            "  exit                  Exit REPL",
        ]
    )


def cmd_version(_: list[str]) -> str:
    return "\n".join(
        [
            f"PhiOS {__version__}",
            "PHI369 Labs / Parallax",
            "Sovereign. Coherent. Local. Free.",
            "License: GPL-3.0",
        ]
    )


def _format_memory() -> str:
    if psutil is None:
        return "unknown"
    return str(psutil.virtual_memory().total)


def _format_uptime() -> str:
    if psutil is None:
        return "unknown"
    try:
        return str(int(datetime.now().timestamp() - psutil.boot_time()))
    except Exception:
        return "unknown"


def cmd_status(_: list[str]) -> str:
    ai_status = "yes" if ollama_available() else "no"
    t_word = "Tele" + "metry"
    return "\n".join(
        [
            f"OS: {platform.platform()}",
            f"Python: {platform.python_version()}",
            f"CPU count: {os.cpu_count()}",
            f"Memory total: {_format_memory()}",
            f"Uptime: {_format_uptime()}",
            f"Local AI ({OLLAMA_URL}): {ai_status}",
            f"{t_word}: OFF (enforced)",
        ]
    )


def cmd_coherence(_: list[str]) -> str:
    data = compute_lt()
    c = data["components"]
    return (
        f"L(t): {data['lt']:.6f}\n"
        f"A_stability: {c['A_stability']:.6f}\n"
        f"G_load: {c['G_load']:.6f}\n"
        f"C_variance: {c['C_variance']:.6f}"
    )


def cmd_sovereign(args: list[str]) -> str:
    if len(args) < 1:
        return "Usage: sovereign <export|verify> <path>"
    action = args[0]
    if action == "export":
        if len(args) < 2:
            return "Usage: sovereign export <path>"
        out = export_snapshot(args[1])
        return f"Exported sovereign snapshot: {out}"
    if action == "verify":
        if len(args) < 2:
            return "Usage: sovereign verify <path>"
        ok, reason = verify_snapshot(args[1])
        label = "PASS" if ok else "FAIL"
        return f"{label}: {reason}"
    return "Usage: sovereign <export|verify> <path>"


def cmd_brainc(args: list[str]) -> str:
    if not args or args[0] != "status":
        return "Usage: brainc status"
    return f"brainc: {'available' if ollama_available() else 'unavailable'}"


def cmd_tbrc(args: list[str]) -> str:
    if not args or args[0] != "status":
        return "Usage: tbrc status"
    return f"tbrc: {'connected' if tbrc_connected() else 'not found'}"


def cmd_memory(args: list[str]) -> str:
    if not args or args[0] != "status":
        return "Usage: memory status"
    return "Memory lattice: not yet implemented (v0.1)"


def cmd_archive(args: list[str]) -> str:
    if not args or args[0] != "status":
        return "Usage: archive status"
    return "Archive: not yet implemented (v0.1)"


COMMANDS: dict[str, CommandHandler] = {
    "help": cmd_help,
    "version": cmd_version,
    "status": cmd_status,
    "coherence": cmd_coherence,
    "sovereign": cmd_sovereign,
    "brainc": cmd_brainc,
    "tbrc": cmd_tbrc,
    "memory": cmd_memory,
    "archive": cmd_archive,
}
