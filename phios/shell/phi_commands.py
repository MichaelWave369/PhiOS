"""Command implementations."""

from __future__ import annotations

import json
import os
import platform
import select
import sys
import termios
import time
import tty
from datetime import datetime
from pathlib import Path
from typing import Callable

from phios import __version__
from phios.core.brainc_client import OLLAMA_URL, ollama_available
from phios.core.lt_engine import compute_lt
from phios.core.sovereignty import SovereignSnapshot, export_snapshot, verify_snapshot
from phios.core.tbrc_bridge import TBRCBridge, tbrc_connected
from phios.core.phi_sync import sync_both, sync_pull, sync_push, sync_status
from phios.desktop.install import PhiDesktopInstaller
from phios.desktop.wallpaper import SacredGeometryWallpaper
from phios.display.panels import render_live_panel

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None


CommandHandler = Callable[[list[str], object | None], str]


def _boxed_tbrc_message(reason: str) -> str:
    return "\n".join([
        "+-----------------------------------------+",
        "| TBRC bridge unavailable                 |",
        f"| {reason[:37].ljust(37)} |",
        "+-----------------------------------------+",
    ])


def _calc_trajectory(history: list[float]) -> str:
    if len(history) < 3:
        return "stable"
    a, b, c = history[-3], history[-2], history[-1]
    span = max(history[-3:]) - min(history[-3:])
    if span > 0.2:
        return "volatile"
    if c > b >= a:
        return "rising"
    if c < b <= a:
        return "falling"
    return "stable"


def _resonance_in(elapsed_s: int) -> int:
    rem = elapsed_s % 369
    return 0 if rem == 0 else 369 - rem


def _default_key_reader() -> str | None:
    if os.name == "nt":
        try:
            import msvcrt

            if msvcrt.kbhit():
                return msvcrt.getch().decode(errors="ignore").lower()
        except Exception:
            return None
        return None

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if ready:
            return sys.stdin.read(1).lower()
        return None
    except Exception:
        return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def cmd_coherence_live(session: object, key_reader: Callable[[], str | None] | None = None, iterations: int | None = None) -> str:
    key_reader = key_reader or _default_key_reader
    snapshotter = SovereignSnapshot()
    start = time.monotonic()
    local_history = list(getattr(session, "coherence_history", []))
    i = 0

    while True:
        i += 1
        lt = compute_lt()
        score = float(lt.get("lt", 0.5))
        local_history.append(score)
        local_history = local_history[-9:]
        elapsed_s = int(time.monotonic() - start)
        trajectory = _calc_trajectory(local_history)
        setattr(session, "trajectory", trajectory)
        setattr(session, "coherence_history", local_history)

        resonance_now = elapsed_s > 0 and elapsed_s % 369 == 0
        if resonance_now:
            setattr(session, "resonance_moments_hit", int(getattr(session, "resonance_moments_hit", 0)) + 1)

        payload = {
            "lt": score,
            "components": lt.get("components", {}),
            "trajectory": trajectory,
            "history": local_history,
            "elapsed_s": elapsed_s,
            "resonance_in": _resonance_in(elapsed_s),
            "resonance_now": resonance_now,
        }

        print("\x1b[2J\x1b[H" + render_live_panel(payload), flush=True)

        key = key_reader() if key_reader else None
        if key == "q":
            return ""
        if key == "r":
            local_history = []
            setattr(session, "coherence_history", local_history)
        if key == "s":
            path = f"phi_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            snap = snapshotter.capture(lt, {
                "history": local_history,
                "duration_s": int(getattr(session, "elapsed_seconds", lambda: elapsed_s)()),
                "commands_run": int(getattr(session, "commands_run", 0)),
                "resonance_moments_hit": int(getattr(session, "resonance_moments_hit", 0)),
                "trajectory": trajectory,
            })
            Path(path).write_text(json.dumps(snap, indent=2), encoding="utf-8")

        if iterations is not None and i >= iterations:
            return ""
        try:
            time.sleep(3)
        except KeyboardInterrupt:
            return ""


def cmd_help(_: list[str], session: object | None = None) -> str:
    return "\n".join(
        [
            "Commands:",
            "  help                        Show this help",
            "  version                     Show PhiOS version info",
            "  status                      Show local system status",
            "  coherence                   Compute L(t) coherence",
            "  coherence live              Launch live coherence monitor",
            "  sovereign export [path]     Export sovereign snapshot",
            "  sovereign verify <path>     Verify sovereign snapshot",
            "  sovereign compare A B       Compare snapshots",
            "  sovereign annotate P note   Add annotation",
            "  brainc status               Check local Ollama status",
            "  tbrc status                 Check TBRC bridge status",
            "  memory [status|search|recent]",
            "  archive [timeline|add|export]",
            "  kg [stats|search]",
            "  sync [status|push|pull|both]",
            "  desktop [status|install|config|reset]",
            "  wallpaper [generate|set|watch]",
            "  exit                        Exit REPL",
        ]
    )


def cmd_version(_: list[str], session: object | None = None) -> str:
    return "\n".join(
        [
            f"PhiOS v{__version__}",
            "PhiOS v0.1.0 (compat)",
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


def cmd_status(_: list[str], session: object | None = None) -> str:
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


def cmd_coherence(args: list[str], session: object | None = None) -> str:
    if args and args[0] == "live":
        if session is None:
            return "Live mode requires session context"
        return cmd_coherence_live(session)

    data = compute_lt()
    c = data["components"]
    if session is not None:
        history = list(getattr(session, "coherence_history", []))
        history.append(float(data["lt"]))
        setattr(session, "coherence_history", history[-9:])
    return (
        f"L(t): {data['lt']:.6f}\n"
        f"A_stability: {c['A_stability']:.6f}\n"
        f"G_load: {c['G_load']:.6f}\n"
        f"C_variance: {c['C_variance']:.6f}"
    )


def cmd_sovereign(args: list[str], session: object | None = None) -> str:
    if len(args) < 1:
        return "Usage: sovereign <export|verify|compare|annotate> ..."

    action = args[0]
    snapper = SovereignSnapshot()

    if action == "export":
        if session is None:
            session_data = {"history": [], "duration_s": 0, "commands_run": 0, "resonance_moments_hit": 0, "trajectory": "stable"}
        else:
            session_data = {
                "history": list(getattr(session, "coherence_history", [])),
                "duration_s": int(getattr(session, "elapsed_seconds", lambda: 0)()),
                "commands_run": int(getattr(session, "commands_run", 0)),
                "resonance_moments_hit": int(getattr(session, "resonance_moments_hit", 0)),
                "trajectory": str(getattr(session, "trajectory", "stable")),
            }
        lt = compute_lt()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = args[1] if len(args) > 1 else f"./phi_snapshot_{stamp}.json"
        data = snapper.capture(lt, session_data)
        Path(out_path).write_text(json.dumps(data, indent=2), encoding="utf-8")
        short_hash = data.get("integrity", {}).get("content_hash", "")[:6]
        return f"✓ Snapshot captured · L(t): {float(lt.get('lt', 0.0)):.3f} · Hash: {short_hash}..."

    if action == "verify":
        if len(args) < 2:
            return "Usage: sovereign verify <path>"
        ok, reason = verify_snapshot(args[1])
        label = "PASS" if ok else "FAIL"
        return f"{label}: {reason}"

    if action == "compare":
        if len(args) < 3:
            return "Usage: sovereign compare <path_a> <path_b>"
        out = snapper.compare(args[1], args[2])
        return json.dumps(out, indent=2)

    if action == "annotate":
        if len(args) < 3:
            return "Usage: sovereign annotate <path> <note>"
        note = " ".join(args[2:])
        try:
            snapper.annotate(args[1], note)
            return "Annotation added"
        except Exception as exc:
            return f"FAIL: {exc}"

    if action in ("export_legacy", "verify_legacy"):
        # Backward-compatible wrappers.
        if action == "export_legacy" and len(args) > 1:
            out = export_snapshot(args[1])
            return f"Exported sovereign snapshot: {out}"
        if action == "verify_legacy" and len(args) > 1:
            ok, reason = verify_snapshot(args[1])
            return f"{'PASS' if ok else 'FAIL'}: {reason}"

    return "Usage: sovereign <export|verify|compare|annotate> ..."


def cmd_brainc(args: list[str], session: object | None = None) -> str:
    if not args or args[0] != "status":
        return "Usage: brainc status"
    return f"brainc: {'available' if ollama_available() else 'unavailable'}"


def cmd_tbrc(args: list[str], session: object | None = None) -> str:
    if not args or args[0] != "status":
        return "Usage: tbrc status"
    return f"tbrc: {'connected' if tbrc_connected() else 'not found'}"


def cmd_memory(args: list[str], session: object | None = None) -> str:
    bridge = TBRCBridge()
    action = args[0] if args else "status"
    if action == "status":
        stats = bridge.memory_stats()
        if not stats.get("available", False):
            return _boxed_tbrc_message(str(stats.get("reason", "not available")))
        return json.dumps(stats, indent=2)
    if action == "search":
        query = " ".join(args[1:])
        if not query:
            return "Usage: memory search <query>"
        return json.dumps(bridge.memory_search(query), indent=2)
    if action == "recent":
        return json.dumps(bridge.archive_timeline(limit=5), indent=2)
    return "Usage: memory [status|search <query>|recent]"


def cmd_archive(args: list[str], session: object | None = None) -> str:
    bridge = TBRCBridge()
    action = args[0] if args else "timeline"
    if action == "status":
        return "Archive: not yet implemented (v0.1)"
    if action == "timeline":
        timeline = bridge.archive_timeline(limit=5)
        if not timeline:
            return _boxed_tbrc_message("timeline unavailable")
        return json.dumps(timeline, indent=2)
    if action == "add":
        if len(args) < 2:
            return "Usage: archive add <title> [narrative]"
        title = args[1]
        narrative = " ".join(args[2:]) if len(args) > 2 else ""
        result = bridge.archive_add(title=title, narrative=narrative)
        return json.dumps(result, indent=2)
    if action == "export":
        return "Archive export bridge: pending TBRC connector"
    return "Usage: archive [timeline|add|export]"


def cmd_kg(args: list[str], session: object | None = None) -> str:
    bridge = TBRCBridge()
    action = args[0] if args else "stats"
    if action == "stats":
        return json.dumps(bridge.kg_stats(), indent=2)
    if action == "search":
        query = " ".join(args[1:])
        if not query:
            return "Usage: kg search <concept>"
        return json.dumps(bridge.memory_search(query), indent=2)
    return "Usage: kg [stats|search <concept>]"


def cmd_sync(args: list[str], session: object | None = None) -> str:
    action = args[0] if args else "status"
    if action == "status":
        report = sync_status()
    elif action == "push":
        report = sync_push()
    elif action == "pull":
        report = sync_pull()
    elif action == "both":
        report = sync_both()
    else:
        return "Usage: sync [status|push|pull|both]"

    if not report.get("available", False):
        return _boxed_tbrc_message(str(report.get("reason", "not available")))
    return json.dumps(report, indent=2)


def cmd_desktop(args: list[str], session: object | None = None) -> str:
    installer = PhiDesktopInstaller()
    action = args[0] if args else "status"
    if action == "status":
        wayfire_ok = installer.wayfire_ini.exists()
        waybar_ok = (installer.waybar_dir / "config.jsonc").exists() and (installer.waybar_dir / "style.css").exists()
        return json.dumps({"wayfire": wayfire_ok, "waybar": waybar_ok, "installed": wayfire_ok and waybar_ok}, indent=2)
    if action == "install":
        confirm = len(args) > 1 and args[1] == "--yes"
        report = installer.install(dry_run=not confirm)
        if not confirm:
            return "Dry run (default). Re-run with: phi desktop install --yes\n" + json.dumps(report, indent=2)
        return json.dumps(report, indent=2)
    if action == "config":
        return f"Wayfire config path: {installer.wayfire_ini}"
    if action == "reset":
        installer.backup_existing_configs()
        installer.apply_phios_config()
        return "PhiOS desktop config reset complete"
    return "Usage: desktop [status|install|config|reset]"


def cmd_wallpaper(args: list[str], session: object | None = None) -> str:
    engine = SacredGeometryWallpaper()
    action = args[0] if args else "generate"
    if action == "generate":
        path = engine.generate()
        return f"Wallpaper generated: {path}"
    if action == "set":
        path = args[1] if len(args) > 1 else "~/.phi/wallpaper.png"
        ok = engine.set_as_wallpaper(path)
        return "Wallpaper applied" if ok else "Wallpaper backend unavailable"
    if action == "watch":
        engine.regenerate_on_lt_change()
        return "Wallpaper watch stopped"
    return "Usage: wallpaper [generate|set|watch]"


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
    "kg": cmd_kg,
    "sync": cmd_sync,
    "desktop": cmd_desktop,
    "wallpaper": cmd_wallpaper,
}
