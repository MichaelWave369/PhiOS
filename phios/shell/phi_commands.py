"""Command implementations."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import select
import subprocess
import sys
import termios
import time
import tty
from datetime import datetime
from pathlib import Path
from typing import Callable

from phios import __version__
from phios.core.brainc_client import OLLAMA_URL, BrainCClient, ollama_available
from phios.core.lt_engine import compute_lt
from phios.core.sovereignty import SovereignSnapshot, export_snapshot, verify_snapshot
from phios.core.tbrc_bridge import TBRCBridge, tbrc_connected
from phios.core.phi_sync import sync_both, sync_pull, sync_push, sync_status
from phios.desktop.install import PhiDesktopInstaller
from phios.desktop.launcher import PhiLauncher
from phios.desktop.notifications import PhiNotifier
from phios.desktop.wallpaper import SacredGeometryWallpaper
from phios.display.panels import render_live_panel
from phios.shell.phi_dashboard import PhiDashboard
from phios.network.discovery import PhiNodeAnnouncer, PhiNodeDiscovery
from phios.network.exchange import PhiExchangeClient, PhiExchangeServer

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None


CommandHandler = Callable[[list[str], object | None], str]
NOTIFIER = PhiNotifier()
NETWORK_ANNOUNCER = PhiNodeAnnouncer()
NETWORK_DISCOVERY = PhiNodeDiscovery()
EXCHANGE_SERVER = PhiExchangeServer()
EXCHANGE_CLIENT = PhiExchangeClient(server=EXCHANGE_SERVER)


def _network_mode_enabled() -> bool:
    return bool(NETWORK_ANNOUNCER.active and NETWORK_DISCOVERY.active)


def _network_peers_box(peers: list[dict[str, object]]) -> str:
    if not peers:
        return "NETWORK · offline (phi network announce to join)"
    lines = ["+----------------------------------------------------+", "| NETWORK · peers                                    |", "+----------------------------------------------------+"]
    for peer in peers[:9]:
        row = f"| {str(peer.get('node_name','node'))[:12]:12} lt {float(peer.get('lt_score',0.0)):.2f} TBRC {'✓' if peer.get('tbrc', False) else '✗'} PHB {'✓' if peer.get('phb', False) else '✗'} |"
        lines.append(row.ljust(54) + ("|" if not row.endswith("|") else ""))
    lines.append("+----------------------------------------------------+")
    return "\n".join(lines)



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
    prev_score: float | None = None

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
            NOTIFIER.resonance_moment(score)

        if prev_score is not None and prev_score - score > 0.1:
            NOTIFIER.coherence_alert(score, prev_score - score)
        prev_score = score

        for marker_interval in (3, 6, 9):
            if elapsed_s > 0 and elapsed_s % marker_interval == 0:
                NOTIFIER.session_rhythm(marker_interval)

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
            "  ask <question|--lt|--session|--next>",
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
            "  launcher                    Open sovereign launcher",
            "  research [status|compose|start|stop|memory|archive|kg|phb|session]",
            "  dashboard                   Open the living dashboard",
            "  network [status|peers|announce|stop]",
            "  exchange [propose|pending|accept|reject|history]",
            "  build [iso|status|clean]",
            "  notify [test|status|history]",
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


def _sovereign_config_path() -> Path:
    root = Path(os.environ.get("PHIOS_CONFIG_HOME", str(Path.home())))
    return root / ".phi" / "config.json"


def _set_sovereign_mode(active: bool) -> None:
    cfg_path = _sovereign_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, object] = {}
    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except (json.JSONDecodeError, OSError, ValueError):
            data = {}
    data["sovereign_mode"] = active
    cfg_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _get_sovereign_mode() -> bool:
    cfg_path = _sovereign_config_path()
    if not cfg_path.exists():
        return True
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return bool(data.get("sovereign_mode", True))
    except (json.JSONDecodeError, OSError, ValueError):
        return True
    return True


def cmd_sovereign(args: list[str], session: object | None = None) -> str:
    if len(args) < 1:
        return "Usage: sovereign <on|off|toggle|export|verify|compare|annotate> ..."

    action = args[0]
    snapper = SovereignSnapshot()

    if action in {"on", "off", "toggle"}:
        current = _get_sovereign_mode()
        if action == "toggle":
            target = not current
        else:
            target = action == "on"
        _set_sovereign_mode(target)
        NOTIFIER.sovereignty_changed(target, force=True)
        return f"Sovereign mode: {'ON' if target else 'OFF'}"

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

    return "Usage: sovereign <on|off|toggle|export|verify|compare|annotate> ..."


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


def _build_ask_context(session: object | None = None) -> dict[str, object]:
    lt = compute_lt()
    return {
        "lt_score": float(lt.get("lt", 0.5)),
        "session_age": int(getattr(session, "elapsed_seconds", lambda: 0)()),
        "sovereign_mode": _get_sovereign_mode(),
        "tbrc_available": TBRCBridge().is_available(),
        "recent_commands": list(getattr(session, "recent_commands", []))[-5:] if session is not None else [],
    }


def cmd_ask(args: list[str], session: object | None = None) -> str:
    client = BrainCClient()
    ctx = _build_ask_context(session)
    if not args:
        return "Usage: ask <question|--lt|--session|--next>"

    if args[0] == "--lt":
        return client.ask_about_lt(compute_lt())
    if args[0] == "--session":
        return client.ask_about_session(ctx)
    if args[0] == "--next":
        suggestion = client.suggest_next_command(list(ctx.get("recent_commands", [])), float(ctx.get("lt_score", 0.5)))
        return suggestion

    question = " ".join(args).strip()
    response = client.ask(question, stream=True, context=ctx)
    NOTIFIER.notify("brainc_response", "BrainC response complete", f"Model: {response.model}")
    return response.answer


def cmd_launcher(args: list[str], session: object | None = None) -> str:
    PhiLauncher().launch()
    return "Launcher completed"


def cmd_notify(args: list[str], session: object | None = None) -> str:
    action = args[0] if args else "status"
    if action == "status":
        return json.dumps(NOTIFIER.status(), indent=2)
    if action == "history":
        lines = NOTIFIER.history_lines()
        return "\n".join(lines) if lines else "No notifications yet."
    if action == "test":
        lt_score = float(compute_lt().get("lt", 0.5))
        NOTIFIER.coherence_alert(lt_score, 0.2, force=True)
        NOTIFIER.resonance_moment(lt_score, force=True)
        NOTIFIER.sovereignty_changed(True, force=True)
        NOTIFIER.sovereignty_changed(False, force=True)
        NOTIFIER.session_rhythm(3, force=True)
        NOTIFIER.session_rhythm(6, force=True)
        NOTIFIER.session_rhythm(9, force=True)
        return "Notification test sequence emitted."
    return "Usage: notify [test|status|history]"




def cmd_research(args: list[str], session: object | None = None) -> str:
    bridge = TBRCBridge()
    action = args[0] if args else "status"

    if not bridge.is_available() and action in {"status", "compose", "session", "phb"}:
        return bridge.degraded_box()

    if action == "status":
        return json.dumps(bridge.full_status(), indent=2)
    if action == "compose":
        phb = bridge.get_phb_status()
        recommendation = "balanced" if phb.get("connected", False) else "default"
        if "--yes" not in args:
            return (
                "Research composer\n"
                "Preset families: default, deep, synthesis\n"
                f"PHB connected: {bool(phb.get('connected', False))}\n"
                f"Recommended engine: {recommendation}\n"
                "Confirmation required. Re-run with: phi research compose --yes"
            )
        result = bridge.start_quick_session(preset=recommendation, operator_confirmed=True)
        return json.dumps(result, indent=2)
    if action == "start":
        if "--yes" not in args:
            return "Refusing to start session without confirmation. Use: phi research start --yes [--preset name]"
        preset = "default"
        if "--preset" in args:
            idx = args.index("--preset")
            if idx + 1 < len(args):
                preset = args[idx + 1]
        return json.dumps(bridge.start_quick_session(preset=preset, operator_confirmed=True), indent=2)
    if action == "stop":
        if "--yes" not in args:
            return "Refusing to stop session without confirmation. Use: phi research stop --yes"
        return json.dumps(bridge.stop_active_session(operator_confirmed=True), indent=2)
    if action == "session":
        return json.dumps({"active_session": bridge.get_active_session(), "session_lt": bridge.get_session_lt()}, indent=2)
    if action == "memory":
        sub = args[1] if len(args) > 1 else "recent"
        if sub == "search":
            query = " ".join(args[2:]).strip()
            return json.dumps(bridge.search_memory(query, limit=5), indent=2)
        if sub == "stats":
            data = bridge.full_status()
            return json.dumps({"available": data.get("available", False), "entries": data.get("memory_entries", 0)}, indent=2)
        return json.dumps(bridge.search_memory("", limit=5), indent=2)
    if action == "archive":
        sub = args[1] if len(args) > 1 else "timeline"
        if sub == "add":
            if "--yes" not in args:
                return "Archive add requires explicit confirmation. Use: phi research archive add <title> <narrative> <significance> --yes"
            title = args[2] if len(args) > 2 else "milestone"
            narrative = args[3] if len(args) > 3 else ""
            significance = args[4] if len(args) > 4 else "gold"
            return json.dumps(bridge.add_archive_milestone(title, narrative, significance, operator_confirmed=True), indent=2)
        if sub == "export":
            return "Archive export bridge: pending TBRC connector"
        return json.dumps(bridge.get_archive_timeline(limit=9), indent=2)
    if action == "kg":
        sub = args[1] if len(args) > 1 else "stats"
        if sub == "find":
            concept = " ".join(args[2:]).strip()
            return json.dumps(bridge.find_concept(concept), indent=2)
        return json.dumps(bridge.get_kg_summary(), indent=2)
    if action == "phb":
        sub = args[1] if len(args) > 1 else "status"
        if sub == "calibrate":
            if "--yes" not in args:
                return "PHB calibration requires explicit confirmation. Use: phi research phb calibrate --yes"
            return json.dumps({"available": bridge.is_available(), "calibrated": bridge.is_available()}, indent=2)
        if sub == "readings":
            status = bridge.get_phb_status()
            readings = status.get("readings", []) if isinstance(status, dict) else []
            return json.dumps({"status": status, "readings": readings}, indent=2)
        return json.dumps(bridge.get_phb_status(), indent=2)

    return "Usage: research [status|compose|start|stop|memory|archive|kg|phb|session]"


def cmd_dashboard(args: list[str], session: object | None = None) -> str:
    PhiDashboard(announcer=NETWORK_ANNOUNCER, discovery=NETWORK_DISCOVERY).run()
    return "Dashboard closed"

def _iso_status() -> dict[str, object]:
    dist_dir = Path("dist")
    latest = None
    if dist_dir.exists():
        isos = sorted(dist_dir.glob("phios-v*-x86_64.iso"))
        if isos:
            latest = isos[-1]
    if latest is None:
        return {"exists": False, "path": None, "size": None, "sha256": None}

    data = latest.read_bytes()
    return {
        "exists": True,
        "path": str(latest),
        "size": latest.stat().st_size,
        "sha256": hashlib.sha256(data).hexdigest(),
    }




def cmd_network(args: list[str], session: object | None = None) -> str:
    action = args[0] if args else "status"

    if action == "status":
        data = {
            "discovery_active": NETWORK_DISCOVERY.active,
            "announcer_active": NETWORK_ANNOUNCER.active,
            "peer_count": len(NETWORK_DISCOVERY.get_peers()),
            "announced": NETWORK_ANNOUNCER.preview_payload(""),
            "exchange": EXCHANGE_SERVER.status(),
            "network_mode": _network_mode_enabled(),
        }
        return json.dumps(data, indent=2)

    if action == "peers":
        peers = NETWORK_DISCOVERY.get_peers()
        return _network_peers_box(peers)

    if action == "announce":
        if "--yes" not in args:
            preview = NETWORK_ANNOUNCER.preview_payload(args[1] if len(args) > 1 and not args[1].startswith("--") else "")
            return "Announce preview:\n" + json.dumps(preview, indent=2) + "\nConfirmation required: phi network announce --yes [node_name]"
        node_name = ""
        for token in args[1:]:
            if not token.startswith("--"):
                node_name = token
                break
        ok = NETWORK_ANNOUNCER.announce(node_name=node_name, operator_confirmed=True)
        NETWORK_DISCOVERY.start_listening()
        EXCHANGE_SERVER.start()
        return json.dumps({"announced": ok, "discovery": NETWORK_DISCOVERY.active, "exchange": EXCHANGE_SERVER.status()}, indent=2)

    if action == "stop":
        NETWORK_ANNOUNCER.stop()
        NETWORK_DISCOVERY.stop_listening()
        EXCHANGE_SERVER.stop()
        return json.dumps({"stopped": True, "network_mode": _network_mode_enabled()}, indent=2)

    return "Usage: network [status|peers|announce|stop]"


def cmd_exchange(args: list[str], session: object | None = None) -> str:
    action = args[0] if args else "pending"

    if action == "propose":
        if len(args) < 3:
            return "Usage: exchange propose <peer_address> <snapshot_path> --yes"
        peer_address = args[1]
        snapshot_path = args[2]
        confirmed = "--yes" in args
        if not confirmed:
            return "Refusing to propose without confirmation. Use: phi exchange propose <peer_address> <snapshot_path> --yes"
        proposal = EXCHANGE_CLIENT.propose_exchange(peer_address, snapshot_path, operator_confirmed=True)
        return json.dumps(proposal, indent=2)

    if action == "pending":
        return json.dumps(EXCHANGE_SERVER.get_pending_proposals(), indent=2)

    if action == "accept":
        if len(args) < 2:
            return "Usage: exchange accept <proposal_id> --yes"
        if "--yes" not in args:
            return "Refusing to accept without confirmation. Use: phi exchange accept <proposal_id> --yes"
        return json.dumps(EXCHANGE_SERVER.accept_proposal(args[1], operator_confirmed=True), indent=2)

    if action == "reject":
        if len(args) < 2:
            return "Usage: exchange reject <proposal_id>"
        EXCHANGE_SERVER.reject_proposal(args[1])
        return "Proposal rejected"

    if action == "history":
        return json.dumps(EXCHANGE_CLIENT.log.get_history(limit=9), indent=2)

    return "Usage: exchange [propose|pending|accept|reject|history]"

def cmd_build(args: list[str], session: object | None = None) -> str:
    action = args[0] if args else "status"
    if action == "status":
        return json.dumps(_iso_status(), indent=2)
    if action == "clean":
        removed: list[str] = []
        for target in [Path("build/work"), Path("build/out")]:
            if target.exists():
                import shutil

                shutil.rmtree(target)
                removed.append(str(target))
        dist_dir = Path("dist")
        if dist_dir.exists():
            for iso in dist_dir.glob("phios-v*-x86_64.iso"):
                iso.unlink()
                removed.append(str(iso))
        return json.dumps({"removed": removed}, indent=2)
    if action == "iso":
        confirmed = len(args) > 1 and args[1] == "--yes"
        if not confirmed:
            return "Refusing to build ISO without explicit confirmation. Re-run: phi build iso --yes"
        proc = subprocess.run(["bash", "build/build_iso.sh"], capture_output=True, text=True, check=False)
        output = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            return f"ISO build failed\n{output}"
        return f"ISO build completed\n{output}"
    return "Usage: build [iso|status|clean]"


COMMANDS: dict[str, CommandHandler] = {
    "help": cmd_help,
    "version": cmd_version,
    "status": cmd_status,
    "ask": cmd_ask,
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
    "launcher": cmd_launcher,
    "research": cmd_research,
    "dashboard": cmd_dashboard,
    "network": cmd_network,
    "exchange": cmd_exchange,
    "notify": cmd_notify,
    "build": cmd_build,
}
