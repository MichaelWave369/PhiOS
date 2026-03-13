"""Command implementations."""

from __future__ import annotations

import hashlib
import json
import os
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
from phios.core.brainc_client import BrainCClient, ollama_available
from phios.adapters.phik import PhiKernelCLIAdapter
from phios.core.phik_service import (
    build_ask_report,
    build_coherence_report,
    build_doctor_report,
    build_status_report,
    export_phase1_bundle,
    run_init,
    run_pulse_once,
)
from phios.core.hemavit_observatory import (
    build_observatory_report,
    export_observatory_bundle,
    zhemawit_mapping_table,
)
from phios.core.psi_mind_observatory import (
    build_psi_mind_report,
    export_psi_mind_bundle,
    psi_mind_mapping_table,
)
from phios.core.session_layer import (
    build_session_checkin_report,
    build_session_start_report,
    export_session_bundle,
)
from phios.core.bioeffector_layer import (
    add_bioeffector_entry,
    export_bioeffector_bundle,
    list_bioeffectors,
    summarize_bioeffectors,
)
from phios.services.visualizer import VisualizerError, launch_bloom, launch_live_bloom
from phios.core.lt_engine import compute_lt
from phios.core.sovereignty import SovereignSnapshot, export_snapshot, verify_snapshot
from phios.core.tbrc_bridge import TBRCBridge, tbrc_connected
from phios.core.phi_sync import sync_both, sync_pull, sync_push, sync_status
from phios.core.living_spec import PhiOSLivingSpec
from phios.core.founding_document import FOUNDING_DOCUMENT, ParallaxFoundingDocument
from phios.core.launch_artifacts import LaunchArtifactGenerator
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
LIVING_SPEC = PhiOSLivingSpec()
FOUNDING = ParallaxFoundingDocument()
LAUNCH_ARTIFACTS = LaunchArtifactGenerator()


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
            "  doctor [--json]             Check PhiKernel readiness",
            "  init --passphrase ...       Initialize PhiKernel through PhiOS",
            "  pulse once [--json]         Run single PhiKernel pulse",
            "  observatory [--json]        Show Hemavit/TIEKAT observatory frame",
            "  observatory export <path>   Export observatory snapshot",
            "  z map [--json]              Show Z_Hemawit symbolic mapping table",
            "  mind [--json]               Show Ψ_mind observatory frame",
            "  mind map [--json]           Show Ψ_mind symbolic mapping table",
            "  mind export <path>          Export Ψ_mind snapshot",
            "  session start [--json]      Show startup session readiness",
            "  session checkin [--json]    Show integrated daily check-in",
            "  session export <path>       Export session bundle",
            "  bio list [--json]            List tracked bioeffector entries",
            "  bio add ... [--json]         Add a bioeffector tracking entry",
            "  bio show [--json]            Show bioeffector summary",
            "  bio export <path>            Export bioeffector layer",
            "  view --mode sonic [--live] [--refresh-seconds <float>] [--duration <seconds>] [--output <path.html>]",
            "  status [--json]               Show PhiKernel-backed operator status",
            "  ask <prompt> [--json]         Ask PhiKernel coach",
            "  coherence [live|--json]       Show PhiKernel coherence field",
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
            "  spec [generate|view|verify]",
            "  founding [view|export|verify]",
            "  launch [artifacts|announce|distrowatch|investor]",
            "  build [iso|status|clean]",
            "  notify [test|status|history]",
            "  exit                        Exit REPL",
        ]
    )



def _extract_flag_value(args: list[str], flag: str) -> str | None:
    if flag not in args:
        return None
    idx = args.index(flag)
    if idx + 1 >= len(args):
        raise ValueError(f"Missing value for {flag}")
    return args[idx + 1]


def cmd_doctor(args: list[str], session: object | None = None) -> str:
    if "--help" in args or "-h" in args:
        return "Usage: doctor [--json]"

    report = build_doctor_report(PhiKernelCLIAdapter())
    if "--json" in args:
        return json.dumps(report, indent=2)

    checks = report.get("checks", {}) if isinstance(report.get("checks"), dict) else {}
    return "\n".join(
        [
            "PHI369 Labs / Parallax · PhiKernel Readiness",
            f"status: {report.get('status', 'unknown')}",
            f"phik callable: {'yes' if checks.get('phik_callable') else 'no'}",
            f"anchor exists: {'yes' if checks.get('anchor_exists') else 'no'}",
            f"heart status: {'yes' if checks.get('heart_status_exists') else 'no'}",
            f"coherence frame: {'yes' if checks.get('coherence_frame_exists') else 'no'}",
            f"capsule entries: {checks.get('capsule_entries', 0)}",
            f"message: {report.get('message', '')}",
        ]
    )


def cmd_init(args: list[str], session: object | None = None) -> str:
    if "--help" in args or "-h" in args:
        return (
            "Usage: init --passphrase <value> --sovereign-name <name> --user-label <label> "
            "[--resonant-label <label>] [--json]"
        )

    passphrase = _extract_flag_value(args, "--passphrase")
    sovereign_name = _extract_flag_value(args, "--sovereign-name")
    user_label = _extract_flag_value(args, "--user-label")
    resonant_label = _extract_flag_value(args, "--resonant-label")

    if not passphrase or not sovereign_name or not user_label:
        return (
            "Usage: init --passphrase <value> --sovereign-name <name> --user-label <label> "
            "[--resonant-label <label>] [--json]"
        )

    result = run_init(
        PhiKernelCLIAdapter(),
        passphrase=passphrase,
        sovereign_name=sovereign_name,
        user_label=user_label,
        resonant_label=resonant_label,
    )

    if "--json" in args:
        return json.dumps(result, indent=2)

    return "\n".join(
        [
            "PHI369 Labs / Parallax · Initialization Complete",
            f"sovereign_name: {sovereign_name}",
            f"user_label: {user_label}",
            "PhiKernel remains the runtime source of truth.",
        ]
    )


def cmd_pulse(args: list[str], session: object | None = None) -> str:
    if not args or args[0] in {"--help", "-h"}:
        return "Usage: pulse once [--checkpoint <path>] [--passphrase <value>] [--json]"

    action = args[0]
    tail = args[1:]
    if action != "once":
        return "Usage: pulse once [--checkpoint <path>] [--passphrase <value>] [--json]"
    if "--help" in tail or "-h" in tail:
        return "Usage: pulse once [--checkpoint <path>] [--passphrase <value>] [--json]"

    checkpoint = _extract_flag_value(tail, "--checkpoint")
    passphrase = _extract_flag_value(tail, "--passphrase")
    if checkpoint and not passphrase:
        raise ValueError("--passphrase is required when --checkpoint is used")

    result = run_pulse_once(PhiKernelCLIAdapter(), checkpoint=checkpoint, passphrase=passphrase)
    if "--json" in tail:
        return json.dumps(result, indent=2)

    return "\n".join(
        [
            "PHI369 Labs / Parallax · Pulse Once",
            f"field_action: {result.get('field_action', result.get('recommended_action', 'unknown'))}",
            f"field_band: {result.get('field_band', result.get('drift_band', 'unknown'))}",
            f"route_reason: {result.get('route_reason', 'n/a')}",
        ]
    )


def cmd_observatory(args: list[str], session: object | None = None) -> str:
    if args and args[0] in {"--help", "-h"}:
        return "Usage: observatory [--json] | observatory export <path.json>"

    if args and args[0] == "export":
        if len(args) > 1 and args[1] in {"--help", "-h"}:
            return "Usage: observatory export <path.json>"
        if len(args) < 2:
            return "Usage: observatory export <path.json>"
        out_path = export_observatory_bundle(PhiKernelCLIAdapter(), args[1])
        return f"✓ Hemavit observatory bundle written: {out_path}"

    report = build_observatory_report(PhiKernelCLIAdapter())
    if "--json" in args:
        return json.dumps(report, indent=2)

    frame = report.get("observatory_frame", {}) if isinstance(report.get("observatory_frame"), dict) else {}
    return "\n".join(
        [
            "PHI369 Labs / Parallax · Hemavit Observatory",
            "Boundary: PhiKernel is source-of-truth; PhiOS provides symbolic interpretation.",
            f"anchor_state: {frame.get('anchor_state', 'unknown')}",
            f"current_field_action: {frame.get('current_field_action', 'unknown')}",
            f"drift_band: {frame.get('drift_band', 'unknown')}",
            f"capsule_continuity_count: {frame.get('capsule_continuity_count', 0)}",
            f"C_landscape_state: {frame.get('C_landscape_state', 'unknown')}",
            f"observer_stability: {frame.get('observer_stability', 'unknown')}",
            f"entropy_gradient_state: {frame.get('entropy_gradient_state', 'unknown')}",
            f"information_gradient_state: {frame.get('information_gradient_state', 'unknown')}",
            f"collapse_risk: {frame.get('collapse_risk', 'unknown')}",
            f"recognition_readiness: {frame.get('recognition_readiness', 'unknown')}",
            f"zhemawit_mode: {frame.get('zhemawit_mode', 'unknown')}",
        ]
    )


def cmd_z(args: list[str], session: object | None = None) -> str:
    if not args or args[0] in {"--help", "-h"}:
        return "Usage: z map [--json]"

    action = args[0]
    tail = args[1:]
    if action != "map":
        return "Usage: z map [--json]"
    if "--help" in tail or "-h" in tail:
        return "Usage: z map [--json]"

    mapping = zhemawit_mapping_table()
    if "--json" in tail:
        return json.dumps({"symbolic_mapping": mapping}, indent=2)

    lines = [
        "PHI369 Labs / Parallax · Z_Hemawit Symbolic Map",
        "Symbolic documentation and runtime introspection (not a physics simulator).",
    ]
    for k, v in mapping.items():
        lines.append(f"{k} -> {v}")
    return "\n".join(lines)


def cmd_mind(args: list[str], session: object | None = None) -> str:
    if args and args[0] in {"--help", "-h"}:
        return "Usage: mind [--json] | mind map [--json] | mind export <path.json>"

    if args and args[0] == "map":
        tail = args[1:]
        if "--help" in tail or "-h" in tail:
            return "Usage: mind map [--json]"
        mapping = psi_mind_mapping_table()
        if "--json" in tail:
            return json.dumps({"symbolic_mapping": mapping}, indent=2)
        lines = [
            "PHI369 Labs / Parallax · Ψ_mind Symbolic Map",
            "Symbolic documentation/runtime introspection (not a simulator).",
        ]
        for k, v in mapping.items():
            lines.append(f"{k} -> {v}")
        return "\n".join(lines)

    if args and args[0] == "export":
        if len(args) > 1 and args[1] in {"--help", "-h"}:
            return "Usage: mind export <path.json>"
        if len(args) < 2:
            return "Usage: mind export <path.json>"
        out_path = export_psi_mind_bundle(PhiKernelCLIAdapter(), args[1])
        return f"✓ Ψ_mind observatory bundle written: {out_path}"

    report = build_psi_mind_report(PhiKernelCLIAdapter())
    if "--json" in args:
        return json.dumps(report, indent=2)

    frame = report.get("mind_observatory_frame", {}) if isinstance(report.get("mind_observatory_frame"), dict) else {}
    return "\n".join(
        [
            "PHI369 Labs / Parallax · Ψ_mind Observatory",
            "Boundary: PhiKernel is source-of-truth; PhiOS provides symbolic interpretation.",
            f"anchor_state: {frame.get('anchor_state', 'unknown')}",
            f"current_field_action: {frame.get('current_field_action', 'unknown')}",
            f"drift_band: {frame.get('drift_band', 'unknown')}",
            f"capsule_continuity_count: {frame.get('capsule_continuity_count', 0)}",
            f"psi_mind_state: {frame.get('psi_mind_state', 'unknown')}",
            f"observer_coupling: {frame.get('observer_coupling', 'unknown')}",
            f"entropy_load: {frame.get('entropy_load', 'unknown')}",
            f"information_density: {frame.get('information_density', 'unknown')}",
            f"kernel_resonance: {frame.get('kernel_resonance', 'unknown')}",
            f"overlap_strength: {frame.get('overlap_strength', 'unknown')}",
            f"collapse_risk: {frame.get('collapse_risk', 'unknown')}",
            f"recognition_readiness: {frame.get('recognition_readiness', 'unknown')}",
            f"mind_mode: {frame.get('mind_mode', 'unknown')}",
        ]
    )


def cmd_session(args: list[str], session: object | None = None) -> str:
    if not args or args[0] in {"--help", "-h"}:
        return "Usage: session <start|checkin|export> ..."

    action = args[0]
    tail = args[1:]

    if action == "start":
        if "--help" in tail or "-h" in tail:
            return "Usage: session start [--json]"
        report = build_session_start_report(PhiKernelCLIAdapter())
        if "--json" in tail:
            return json.dumps(report, indent=2)
        return "\n".join(
            [
                "PHI369 Labs / Parallax · Session Start",
                f"session_state: {report.get('session_state', 'unknown')}",
                f"anchor_ready: {report.get('anchor_ready', report.get('anchor_readiness', 'unknown'))}",
                f"heart_ready: {report.get('heart_ready', report.get('heart_presence', 'unknown'))}",
                f"field_action: {report.get('field_action', 'unknown')}",
                f"drift_band: {report.get('drift_band', 'unknown')}",
                f"observatory_mode: {report.get('observatory_mode', 'unknown')}",
                f"mind_mode: {report.get('mind_mode', 'unknown')}",
                f"observer_state: {report.get('observer_state', 'unknown')}",
                f"self_alignment: {report.get('self_alignment', 'unknown')}",
                f"next_step: {report.get('next_step', report.get('next_recommended_step', ''))}",
            ]
        )

    if action == "checkin":
        if "--help" in tail or "-h" in tail:
            return "Usage: session checkin [--json]"
        report = build_session_checkin_report(PhiKernelCLIAdapter())
        if "--json" in tail:
            return json.dumps(report, indent=2)
        return "\n".join(
            [
                "PHI369 Labs / Parallax · Session Check-in",
                f"session_state: {report.get('session_state', 'unknown')}",
                f"observer_state: {report.get('observer_state', 'unknown')}",
                f"self_alignment: {report.get('self_alignment', 'unknown')}",
                f"information_density: {report.get('information_density', 'unknown')}",
                f"entropy_load: {report.get('entropy_load', 'unknown')}",
                f"emergence_pressure: {report.get('emergence_pressure', 'unknown')}",
                f"collapse_risk: {report.get('collapse_risk', 'unknown')}",
                f"recognition_readiness: {report.get('recognition_readiness', 'unknown')}",
                f"zhemawit_mode: {report.get('zhemawit_mode', 'unknown')}",
                f"recommended_action: {report.get('recommended_action', 'unknown')}",
                f"recommended_prompt: {report.get('recommended_prompt', '')}",
                f"next_step: {report.get('next_step', '')}",
            ]
        )

    if action == "export":
        if len(tail) > 0 and tail[0] in {"--help", "-h"}:
            return "Usage: session export <path.json>"
        if not tail:
            return "Usage: session export <path.json>"
        out_path = export_session_bundle(PhiKernelCLIAdapter(), tail[0])
        return f"✓ Session bundle written: {out_path}"

    return "Usage: session <start|checkin|export> ..."


def cmd_bio(args: list[str], session: object | None = None) -> str:
    if not args or args[0] in {"--help", "-h"}:
        return "Usage: bio <list|add|show|export> ..."

    action = args[0]
    tail = args[1:]

    if action == "list":
        if "--help" in tail or "-h" in tail:
            return "Usage: bio list [--json]"
        rows = list_bioeffectors()
        if "--json" in tail:
            return json.dumps({"entries": rows}, indent=2)
        if not rows:
            return "No bioeffector entries tracked yet."
        lines = ["PHI369 Labs / Parallax · Bioeffectors"]
        for row in rows[-9:]:
            lines.append(f"- {row.get('name', 'unknown')} · {row.get('compound', 'n/a')} · {row.get('source', 'n/a')}")
        return "\n".join(lines)

    if action == "add":
        if "--help" in tail or "-h" in tail:
            return (
                "Usage: bio add --name <name> --compound <compound> --source <source> "
                "[--dose <dose>] [--unit <unit>] [--timing <timing>] [--notes <notes>] [--json]"
            )

        name = _extract_flag_value(tail, "--name")
        compound = _extract_flag_value(tail, "--compound")
        source = _extract_flag_value(tail, "--source")
        dose = _extract_flag_value(tail, "--dose")
        unit = _extract_flag_value(tail, "--unit")
        timing = _extract_flag_value(tail, "--timing")
        notes = _extract_flag_value(tail, "--notes")

        if not name or not compound or not source:
            return (
                "Usage: bio add --name <name> --compound <compound> --source <source> "
                "[--dose <dose>] [--unit <unit>] [--timing <timing>] [--notes <notes>] [--json]"
            )

        entry = add_bioeffector_entry(
            name=name,
            compound=compound,
            source=source,
            dose=dose,
            unit=unit,
            timing=timing,
            notes=notes,
        )
        if "--json" in tail:
            return json.dumps({"entry": entry}, indent=2)
        return f"Bioeffector entry added: {entry.get('name')} ({entry.get('compound')})"

    if action == "show":
        if "--help" in tail or "-h" in tail:
            return "Usage: bio show [--json]"
        summary = summarize_bioeffectors()
        if "--json" in tail:
            return json.dumps(summary, indent=2)
        return "\n".join(
            [
                "PHI369 Labs / Parallax · Bioeffector Summary",
                f"bioeffector_count: {summary.get('bioeffector_count', 0)}",
                f"dominant_source_type: {summary.get('dominant_source_type', 'none')}",
                f"timing_state: {summary.get('timing_state', 'unspecified')}",
                f"bioeffector_mode: {summary.get('bioeffector_mode', 'tracking-observatory')}",
                f"support_vector: {summary.get('support_vector', 'baseline')}",
                f"tracking_confidence: {summary.get('tracking_confidence', 'low')}",
                f"session_correlation_readiness: {summary.get('session_correlation_readiness', 'forming')}",
            ]
        )

    if action == "export":
        if len(tail) > 0 and tail[0] in {"--help", "-h"}:
            return "Usage: bio export <path.json>"
        if not tail:
            return "Usage: bio export <path.json>"
        out = export_bioeffector_bundle(tail[0])
        return f"✓ Bioeffector bundle written: {out}"

    return "Usage: bio <list|add|show|export> ..."


def cmd_view(args: list[str], session: object | None = None) -> str:
    usage = "Usage: view --mode sonic [--live] [--refresh-seconds <float>] [--duration <seconds>] [--output <path.html>]"
    if "--help" in args or "-h" in args:
        return usage

    mode = _extract_flag_value(args, "--mode")
    if mode != "sonic":
        return usage

    live = "--live" in args
    out = _extract_flag_value(args, "--output")
    output_path = Path(out).expanduser() if out else None

    refresh_seconds = 2.0
    raw_refresh = _extract_flag_value(args, "--refresh-seconds")
    if raw_refresh is not None:
        try:
            refresh_seconds = max(float(raw_refresh), 0.2)
        except ValueError:
            return usage

    duration: float | None = None
    raw_duration = _extract_flag_value(args, "--duration")
    if raw_duration is not None:
        try:
            duration = max(float(raw_duration), 0.0)
        except ValueError:
            return usage

    try:
        if live:
            generated = launch_live_bloom(
                output_path=output_path,
                refresh_seconds=refresh_seconds,
                duration=duration,
                open_browser=True,
            )
            return f"Live visual bloom running: {generated}"
        generated = launch_bloom(output_path=output_path, open_browser=True)
    except VisualizerError as exc:
        raise RuntimeError(f"Visualizer unavailable: {exc}") from exc
    return f"Visual bloom generated: {generated}"

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


def cmd_status(args: list[str], session: object | None = None) -> str:
    if "--help" in args or "-h" in args:
        return "Usage: status [--json]"

    report = build_status_report(PhiKernelCLIAdapter())
    if "--json" in args:
        return json.dumps(report, indent=2)

    return "\n".join(
        [
            "PHI369 Labs / Parallax · PhiOS Operator Status",
            f"Anchor verification: {report.get('anchor_verification_state', 'unknown')}",
            f"Heart state: {report.get('heart_state', 'unknown')}",
            f"Field action / drift band: {report.get('field_action', 'unknown')} / {report.get('field_drift_band', 'unknown')}",
            f"Capsules tracked: {report.get('capsule_count', 0)}",
            "Source of truth: PhiKernel",
        ]
    )


def cmd_coherence(args: list[str], session: object | None = None) -> str:
    if args and args[0] == "live":
        if session is None:
            return "Live mode requires session context"
        return cmd_coherence_live(session)
    if "--help" in args or "-h" in args:
        return "Usage: coherence [live|--json]"

    report = build_coherence_report(PhiKernelCLIAdapter())
    if "--json" in args:
        return json.dumps(report, indent=2)

    return "\n".join(
        [
            "PHI369 Labs / Parallax · Coherence Report",
            f"C_current: {report.get('C_current')}",
            f"C_star: {report.get('C_star')}",
            f"distance_to_C_star: {report.get('distance_to_C_star')}",
            f"phi_flow: {report.get('phi_flow')}",
            f"lambda_node: {report.get('lambda_node')}",
            f"sigma_feedback: {report.get('sigma_feedback')}",
            f"fragmentation_score: {report.get('fragmentation_score')}",
            f"recommended_action: {report.get('recommended_action')}",
        ]
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
        if len(args) > 1 and args[1] in {"--help", "-h"}:
            return "Usage: sovereign export <path.json>"
        if len(args) < 2:
            return "Usage: sovereign export <path.json>"
        out_path = export_phase1_bundle(PhiKernelCLIAdapter(), args[1])
        return f"✓ Phase 1 export bundle written: {out_path}"

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
        return "Usage: ask <prompt> [--json]"
    if "--help" in args or "-h" in args:
        return "Usage: ask <prompt> [--json]"

    if args[0] == "--lt":
        return client.ask_about_lt(compute_lt())
    if args[0] == "--session":
        return client.ask_about_session(ctx)
    if args[0] == "--next":
        suggestion = client.suggest_next_command(list(ctx.get("recent_commands", [])), float(ctx.get("lt_score", 0.5)))
        return suggestion

    json_mode = "--json" in args
    prompt_parts = [a for a in args if a != "--json"]
    question = " ".join(prompt_parts).strip()
    report = build_ask_report(PhiKernelCLIAdapter(), question)

    if json_mode:
        return json.dumps(report, indent=2)

    next_actions = report.get("next_actions") or []
    if not isinstance(next_actions, list):
        next_actions = [str(next_actions)]
    actions_lines = "\n".join([f"  - {item}" for item in next_actions]) if next_actions else "  - (none)"

    return "\n".join(
        [
            "PHI369 Labs / Parallax · Ask",
            f"coach: {report.get('coach')}",
            f"field_action / band: {report.get('field_action')} / {report.get('field_band')}",
            f"safety_posture: {report.get('safety_posture')}",
            f"route_reason: {report.get('route_reason')}",
            "",
            str(report.get("body", "")),
            "",
            "next_actions:",
            actions_lines,
        ]
    )


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



def cmd_spec(args: list[str], session: object | None = None) -> str:
    action = args[0] if args else "view"
    if action == "generate":
        force = "--force" in args
        confirmed = "--yes" in args
        try:
            spec_path = LIVING_SPEC.generate(force=force, operator_confirmed=confirmed)
            content = Path(spec_path).read_text(encoding="utf-8")
            seal = LIVING_SPEC.generate_seal(content)
            LIVING_SPEC.store_in_archive(spec_path, seal, operator_confirmed=confirmed)
            return f"✓ Spec generated · Seal: {seal}"
        except Exception as exc:
            return f"FAIL: {exc}"
    if action == "view":
        path = Path("docs/PHIOS_LIVING_SPEC.md")
        if not path.exists():
            return "Spec not generated yet."
        return path.read_text(encoding="utf-8")
    if action == "verify":
        ok, message = LIVING_SPEC.verify()
        return message if ok else message
    return "Usage: spec [generate|view|verify]"


def cmd_founding(args: list[str], session: object | None = None) -> str:
    action = args[0] if args else "view"
    if action == "view":
        return FOUNDING_DOCUMENT
    if action == "export":
        if "--yes" not in args:
            return "Refusing export without confirmation. Use: phi founding export --yes"
        md = FOUNDING.export_markdown()
        _ = FOUNDING.export_html()
        digest = FOUNDING.hash_document(Path(md).read_text(encoding="utf-8"))
        FOUNDING.store_in_archive(md, digest, operator_confirmed=True)
        return f"Founding document exported · Hash: {digest}"
    if action == "verify":
        ok, message = FOUNDING.verify()
        return message
    return "Usage: founding [view|export|verify]"


def cmd_launch(args: list[str], session: object | None = None) -> str:
    action = args[0] if args else "artifacts"
    if action == "artifacts":
        files = LAUNCH_ARTIFACTS.generate_all()
        return json.dumps({"written": files}, indent=2)
    if action == "announce":
        return json.dumps(LAUNCH_ARTIFACTS.generate_announcement_kit(), indent=2)
    if action == "distrowatch":
        return LAUNCH_ARTIFACTS.generate_distrowatch_submission()
    if action == "investor":
        path = Path("docs/launch/investor_summary.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(LAUNCH_ARTIFACTS.generate_investor_summary(), encoding="utf-8")
        return str(path)
    return "Usage: launch [artifacts|announce|distrowatch|investor]"

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
    "doctor": cmd_doctor,
    "init": cmd_init,
    "pulse": cmd_pulse,
    "observatory": cmd_observatory,
    "z": cmd_z,
    "mind": cmd_mind,
    "session": cmd_session,
    "bio": cmd_bio,
    "view": cmd_view,
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
    "spec": cmd_spec,
    "founding": cmd_founding,
    "launch": cmd_launch,
    "notify": cmd_notify,
    "build": cmd_build,
}
