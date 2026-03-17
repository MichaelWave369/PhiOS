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
from phios.core.sectors import list_visual_bloom_sectors
from phios.mcp.policy import CAP_AGENT_DISPATCH, CAP_AGENT_KILL, CAP_AGENT_MEMORY_WRITE, is_capability_allowed

from phios.services.agent_dispatch import (
    build_dispatch_context,
    cancel_agent_run,
    dispatch_agentception_run,
    get_agent_run_status,
    list_agent_runs,
    persist_dispatch_storyboard,
    run_agentception_plan,
    stream_agent_run_events,
)
from phios.services.cognitive_arch import (
    build_cognitive_arch_context,
    recommend_cognitive_architecture,
)
from phios.services.cognitive_atoms import (
    build_sector_atom_context,
    recommend_cognitive_atom_overrides,
)
from phios.services.agent_memory import (
    get_agent_memory,
    get_agent_memory_coherence,
    list_recent_agent_deliberations,
    store_agent_deliberation,
)
from phios.services.debate_arena import (
    build_debate_context,
    evaluate_debate_coherence_gate,
    persist_debate_outcome,
)
from phios.services.review_gate import (
    build_review_context,
    evaluate_review_coherence_gate,
    persist_review_outcome,
)
from phios.services.dispatch_graph import (
    optimize_dispatch_graph,
    summarize_dispatch_graph_plan,
)
from phios.services.figure_fitness import (
    build_figure_fitness_report,
    recommend_figure_for_task,
    summarize_figure_fitness_landscape,
)
from phios.services.visualizer import (
    VALID_LENSES,
    VALID_PRESETS,
    VisualizerError,
    export_visual_bloom_atlas,
    export_visual_bloom_bundle,
    launch_bloom,
    launch_compare_bloom,
    launch_live_bloom,
    launch_replay_bloom,
    launch_visual_bloom_gallery,
    list_visual_bloom_collections,
    list_visual_bloom_compare_sets,
    list_visual_bloom_sessions,
    load_visual_bloom_compare_set,
    save_visual_bloom_compare_set,
    add_visual_bloom_constellation_entry,
    add_visual_bloom_narrative_entry,
    add_visual_bloom_narrative_link,
    create_visual_bloom_constellation,
    create_visual_bloom_narrative,
    create_visual_bloom_pathway,
    export_visual_bloom_constellation,
    export_visual_bloom_pathway,
    list_visual_bloom_constellations,
    list_visual_bloom_narratives,
    list_visual_bloom_pathways,
    load_visual_bloom_constellation,
    load_visual_bloom_narrative,
    load_visual_bloom_pathway,
    search_visual_bloom_metadata,
    add_visual_bloom_pathway_entry,
    build_visual_bloom_recommendations,
    launch_visual_bloom_dashboard,
    link_visual_bloom_pathway_steps,
    benchmark_visual_bloom_recommendations,
    launch_visual_bloom_atlas,
    export_visual_bloom_insight_pack,
    launch_visual_bloom_branch_replay,
    export_visual_bloom_route_compare_bundle,
    build_visual_bloom_strategy_diagnostics,
    create_visual_bloom_storyboard,
    list_visual_bloom_storyboards,
    load_visual_bloom_storyboard,
    add_visual_bloom_storyboard_section,
    export_visual_bloom_storyboard,
    build_visual_bloom_atlas_gallery_model,
    render_visual_bloom_atlas_gallery_html,
    export_visual_bloom_longitudinal_summary,
    create_visual_bloom_dossier,
    list_visual_bloom_dossiers,
    load_visual_bloom_dossier,
    add_visual_bloom_dossier_section,
    export_visual_bloom_dossier,
    create_visual_bloom_field_library,
    list_visual_bloom_field_libraries,
    load_visual_bloom_field_library,
    add_visual_bloom_field_library_entry,
    export_visual_bloom_field_library,
    create_visual_bloom_shelf,
    list_visual_bloom_shelves,
    load_visual_bloom_shelf,
    add_visual_bloom_shelf_item,
    export_visual_bloom_shelf,
    build_visual_bloom_catalog_model,
    filter_visual_bloom_catalog_entries,
    group_visual_bloom_catalog_entries,
    render_visual_bloom_catalog_html,
    create_visual_bloom_reading_room,
    list_visual_bloom_reading_rooms,
    load_visual_bloom_reading_room,
    add_visual_bloom_reading_room_section,
    export_visual_bloom_reading_room,
    create_visual_bloom_collection_map,
    list_visual_bloom_collection_maps,
    build_visual_bloom_collection_map_model,
    export_visual_bloom_collection_map,
    create_visual_bloom_study_hall,
    list_visual_bloom_study_halls,
    load_visual_bloom_study_hall,
    add_visual_bloom_study_hall_module,
    export_visual_bloom_study_hall,
    create_visual_bloom_thematic_pathway,
    list_visual_bloom_thematic_pathways,
    build_visual_bloom_thematic_pathway_model,
    export_visual_bloom_thematic_pathway,
    create_visual_bloom_curriculum,
    list_visual_bloom_curricula,
    load_visual_bloom_curriculum,
    add_visual_bloom_curriculum_unit,
    export_visual_bloom_curriculum,
    create_visual_bloom_journey_ensemble,
    list_visual_bloom_journey_ensembles,
    build_visual_bloom_journey_ensemble_model,
    export_visual_bloom_journey_ensemble,
    create_visual_bloom_syllabus,
    list_visual_bloom_syllabi,
    load_visual_bloom_syllabus,
    add_visual_bloom_syllabus_module,
    export_visual_bloom_syllabus,
    create_visual_bloom_atlas_cohort,
    list_visual_bloom_atlas_cohorts,
    build_visual_bloom_atlas_cohort_model,
    export_visual_bloom_atlas_cohort,
    write_bloom_file,
)
from phios.core.kernel_rollout import (
    KernelRolloutStore,
    export_compare_report,
    load_eval_cases,
    recent_rollout_status,
    run_kernel_evaluation,
)
from phios.core.kernel_runtime import KernelRuntimeConfig
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
            "  view --mode sonic [--live] [--refresh-seconds <float>] [--duration <seconds>] [--output <path.html>] [--journal] [--journal-dir <path>] [--label <name>] [--replay <session_id|session.json[:idx]>] [--state-idx <n>] [--next-state|--prev-state] [--preset <name>] [--lens <name>] [--audio-reactive] [--collection <name>] [--browse] [--browse-collections] [--browse-collection <name>] [--compare <left> <right>] [--export-report <path.json>]",
            "  status [--json]               Show PhiKernel-backed operator status",
            "  eval-kernel [--input <cases.json>] [--compare <primary> <shadow>] [--report <path.json>] [--json]",
            "  ask <prompt> [--json]         Ask PhiKernel coach",
            "  coherence [live|--json]       Show PhiKernel coherence field",
            "  coherence live              Launch live coherence monitor",
            "  sovereign export [path]     Export sovereign snapshot",
            "  sovereign verify <path>     Verify sovereign snapshot",
            "  sovereign compare A B       Compare snapshots",
            "  sovereign annotate P note   Add annotation",
            "  brainc status               Check local Ollama status",
            "  tbrc status                 Check TBRC bridge status",
            "  memory [status|search <query>|recent|topic <topic>|coherence <topic>|store <topic> --positions <json> --outcome <text> --winner <figure> --trace <comma floats> [--tags a,b] --yes]",
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
            "  dispatch <task> [--field-guided] [--arch <name>] [--review-panel] [--coherence-gate <float>] [--dry-run] [--stream]",
            "  dispatch optimize --graph <json> [--json]",
            "  agents [list|status <id>|kill <id> --yes|log <id>|figures [--top <n>] [--sector <name>]|evolve [--top <n>] [--sector <name>] [--task-key <key>] [--skill <skill>] [--min-coherence <v>]]",
            "  recommend-arch [--json]      Show field-guided cognitive architecture recommendation",
            "  recommend-atoms [--json]     Show sector-to-atom cognitive override recommendation",
            "  debate gate --session-id <id> --round <n> --positions <json> [--threshold <float>] [--persist] [--json]",
            "  review gate --round <n> --reviewer-grades <json> --reviewer-critiques <json> [--panel-id <id>] [--pr-number <n>] [--mediator-summary <text>] [--persist] [--json]",
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
    usage = "Usage: view --mode sonic [--live] [--refresh-seconds <float>] [--duration <seconds>] [--output <path.html>] [--journal] [--journal-dir <path>] [--label <name>] [--collection <name>] [--replay <session_id|session.json[:idx]>] [--state-idx <n>] [--next-state|--prev-state] [--compare <left_ref> <right_ref>] [--export-report <path.json>] [--export-bundle <dir>] [--with-integrity] [--bundle-label <name>] [--save-compare <name>] [--load-compare <name>] [--browse-compares] [--gallery] [--search <text>] [--filter-mode <mode>] [--filter-preset <name>] [--filter-lens <name>] [--filter-audio <on|off>] [--filter-label <text>] [--filter-session <id>] [--create-narrative <name>] [--narrative-title <text>] [--narrative-summary <text>] [--browse-narratives] [--load-narrative <name>] [--add-to-narrative <name> --session <ref>|--compare <left> <right>|--compare-set <name>] [--link-narrative <name> --link-type <type> --target-ref <ref>] [--entry-title <text>] [--entry-note <text>] [--export-atlas <name> <output-dir>] [--create-constellation <name>] [--constellation-title <text>] [--constellation-summary <text>] [--browse-constellations] [--load-constellation <name>] [--add-to-constellation <name> --narrative <ref>|--session <ref>|--compare-set <name>|--compare <left> <right>] [--export-constellation <name> <output-dir>] [--create-pathway <name>] [--browse-pathways] [--load-pathway <name>] [--add-to-pathway <name> --session <ref>|--compare <left> <right>|--narrative <name>|--atlas <path>|--constellation <name>] [--pathway-title <title>] [--pathway-summary <summary>] [--step-title <title>] [--step-note <note>] [--export-pathway <name> <output-dir>] [--link-pathway-step <pathway> --from-step <id> --to-step <id>] [--branch-label <label>] [--recommend-for <ref>] [--recommend-strategy <name>] [--benchmark-recommendations] [--atlas] [--atlas-target theoretical|bio_band|node] [--atlas-start-ref <ref>] [--atlas-node <idx>] [--atlas-max-l1-radius <int>] [--atlas-heat-mode <mode>] [--atlas-gallery] [--list-sectors] [--sector-family HG|HB] [--export-insight-pack <pathway> <output-dir>] [--insight-pack-title <title>] [--insight-pack-include-atlas] [--insight-pack-heat-mode <mode>] [--branch-replay <pathway>] [--export-route-compare <start-ref> <output-dir>] [--route-compare-title <title>] [--route-compare-heat-mode <mode>] [--route-compare-include-sector-overlays] [--show-strategy-diagnostics <ref>] [--create-storyboard <name>] [--browse-storyboards] [--load-storyboard <name>] [--add-to-storyboard <name>] [--section-type <type>] [--artifact-ref <ref>] [--storyboard-title <title>] [--storyboard-summary <summary>] [--storyboard-tags <comma,separated>] [--storyboard-filter-tags <comma,separated>] [--storyboard-filter-sector <sector>] [--storyboard-filter-type <type>] [--export-storyboard <name> <output-dir>] [--export-longitudinal-summary <output-dir>] [--longitudinal-title <title>] [--longitudinal-filter-tags <comma,separated>] [--longitudinal-filter-sector <sector>] [--longitudinal-filter-target <theoretical|bio_band|node>] [--create-dossier <name>] [--browse-dossiers] [--load-dossier <name>] [--add-to-dossier <name>] [--dossier-title <title>] [--dossier-summary <summary>] [--dossier-tags <comma,separated>] [--dossier-filter-tags <comma,separated>] [--dossier-filter-sector <sector>] [--dossier-filter-type <type>] [--dossier-filter-target <target>] [--export-dossier <name> <output-dir>] [--create-field-library <name>] [--browse-field-libraries] [--load-field-library <name>] [--add-to-field-library <name>] [--field-library-title <title>] [--field-library-summary <summary>] [--field-library-tags <comma,separated>] [--field-library-filter-tags <comma,separated>] [--field-library-filter-sector <sector>] [--field-library-filter-type <type>] [--field-library-filter-target <target>] [--export-field-library <name> <output-dir>] [--create-shelf <name>] [--browse-shelves] [--load-shelf <name>] [--add-to-shelf <name>] [--shelf-title <title>] [--shelf-summary <summary>] [--shelf-tags <comma,separated>] [--shelf-filter-tags <comma,separated>] [--shelf-filter-sector <sector>] [--shelf-filter-type <type>] [--export-shelf <name> <output-dir>] [--browse-catalog] [--catalog-filter-tags <comma,separated>] [--catalog-filter-sector <sector>] [--catalog-filter-type <type>] [--catalog-group-by <field>] [--create-reading-room <name>] [--browse-reading-rooms] [--load-reading-room <name>] [--add-to-reading-room <name>] [--reading-room-title <title>] [--reading-room-summary <summary>] [--reading-room-tags <comma,separated>] [--export-reading-room <name> <output-dir>] [--create-collection-map <name>] [--browse-collection-maps] [--load-collection-map <name>] [--collection-map-tags <comma,separated>] [--collection-map-filter-tags <comma,separated>] [--collection-map-filter-sector <sector>] [--collection-map-filter-type <type>] [--collection-map-group-by <field>] [--export-collection-map <name> <output-dir>] [--create-study-hall <name>] [--browse-study-halls] [--load-study-hall <name>] [--add-to-study-hall <name>] [--study-hall-title <title>] [--study-hall-summary <summary>] [--study-hall-tags <comma,separated>] [--export-study-hall <name> <output-dir>] [--create-thematic-pathway <name>] [--browse-thematic-pathways] [--load-thematic-pathway <name>] [--thematic-pathway-tags <comma,separated>] [--thematic-pathway-filter-tags <comma,separated>] [--thematic-pathway-filter-sector <sector>] [--thematic-pathway-filter-type <type>] [--thematic-pathway-group-by <field>] [--export-thematic-pathway <name> <output-dir>] [--create-curriculum <name>] [--browse-curricula] [--load-curriculum <name>] [--add-to-curriculum <name>] [--curriculum-title <title>] [--curriculum-summary <summary>] [--curriculum-tags <comma,separated>] [--export-curriculum <name> <output-dir>] [--create-journey-ensemble <name>] [--browse-journey-ensembles] [--load-journey-ensemble <name>] [--journey-ensemble-tags <comma,separated>] [--journey-ensemble-filter-tags <comma,separated>] [--journey-ensemble-filter-sector <sector>] [--journey-ensemble-filter-type <type>] [--journey-ensemble-group-by <field>] [--export-journey-ensemble <name> <output-dir>] [--create-syllabus <name>] [--browse-syllabi] [--load-syllabus <name>] [--add-to-syllabus <name>] [--syllabus-title <title>] [--syllabus-summary <summary>] [--syllabus-tags <comma,separated>] [--export-syllabus <name> <output-dir>] [--create-atlas-cohort <name>] [--browse-atlas-cohorts] [--load-atlas-cohort <name>] [--atlas-cohort-tags <comma,separated>] [--atlas-cohort-filter-tags <comma,separated>] [--atlas-cohort-filter-sector <sector>] [--atlas-cohort-filter-type <type>] [--atlas-cohort-group-by <field>] [--export-atlas-cohort <name> <output-dir>] [--dashboard] [--search <query>] [--search-tags <comma,separated>] [--search-type <session|compare|narrative|atlas|constellation|pathway>] [--search-bio <experimental|available|near-target>] [--tags <comma,separated,tags>] [--browse] [--browse-collections] [--browse-collection <name>] [--preset <name>] [--lens <name>] [--audio-reactive]"
    if "--help" in args or "-h" in args:
        return usage

    journal_dir_value = _extract_flag_value(args, "--journal-dir")
    journal_dir = Path(journal_dir_value).expanduser() if journal_dir_value else None

    if "--browse-collections" in args:
        cols = list_visual_bloom_collections(journal_dir=journal_dir)
        return json.dumps({"collections": cols}, indent=2)

    if "--browse-compares" in args:
        compares = list_visual_bloom_compare_sets(journal_dir=journal_dir)
        return json.dumps({"compare_sets": compares, "count": len(compares)}, indent=2)

    if "--browse-narratives" in args:
        narratives = list_visual_bloom_narratives(journal_dir=journal_dir)
        return json.dumps({"narratives": narratives, "count": len(narratives)}, indent=2)

    if "--browse-constellations" in args:
        consts = list_visual_bloom_constellations(journal_dir=journal_dir)
        return json.dumps({"constellations": consts, "count": len(consts)}, indent=2)

    if "--browse-pathways" in args:
        pathways = list_visual_bloom_pathways(journal_dir=journal_dir)
        return json.dumps({"pathways": pathways, "count": len(pathways)}, indent=2)

    if "--list-sectors" in args:
        fam = _extract_flag_value(args, "--sector-family")
        rows = list_visual_bloom_sectors(fam)
        return json.dumps({"family": fam or "all", "sectors": rows, "count": len(rows)}, indent=2)

    if "--browse-storyboards" in args:
        rows = list_visual_bloom_storyboards(journal_dir=journal_dir)
        return json.dumps({"storyboards": rows, "count": len(rows)}, indent=2)

    create_storyboard = _extract_flag_value(args, "--create-storyboard")
    if create_storyboard:
        try:
            path = create_visual_bloom_storyboard(
                name=create_storyboard,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--storyboard-title"),
                summary=_extract_flag_value(args, "--storyboard-summary"),
                tags=_extract_flag_value(args, "--storyboard-tags") or _extract_flag_value(args, "--tags"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom storyboard created: {path}"

    load_storyboard = _extract_flag_value(args, "--load-storyboard")
    if load_storyboard:
        try:
            doc = load_visual_bloom_storyboard(load_storyboard, journal_dir=journal_dir)
        except VisualizerError as exc:
            return str(exc)
        return json.dumps(doc, indent=2)

    add_storyboard = _extract_flag_value(args, "--add-to-storyboard")
    if add_storyboard:
        try:
            out = add_visual_bloom_storyboard_section(
                name=add_storyboard,
                section_type=_extract_flag_value(args, "--section-type") or "insight_pack",
                artifact_ref=_extract_flag_value(args, "--artifact-ref") or "",
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--entry-title") or _extract_flag_value(args, "--storyboard-title"),
                summary=_extract_flag_value(args, "--storyboard-summary"),
                notes=_extract_flag_value(args, "--entry-note"),
                tags=_extract_flag_value(args, "--storyboard-tags") or _extract_flag_value(args, "--tags"),
                sector_family=_extract_flag_value(args, "--sector-family"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom storyboard updated: {out}"

    if "--browse-dossiers" in args:
        rows = list_visual_bloom_dossiers(journal_dir=journal_dir)
        return json.dumps({"dossiers": rows, "count": len(rows)}, indent=2)

    create_dossier = _extract_flag_value(args, "--create-dossier")
    if create_dossier:
        try:
            path = create_visual_bloom_dossier(
                name=create_dossier,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--dossier-title"),
                summary=_extract_flag_value(args, "--dossier-summary"),
                tags=_extract_flag_value(args, "--dossier-tags") or _extract_flag_value(args, "--tags"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom dossier created: {path}"

    load_dossier = _extract_flag_value(args, "--load-dossier")
    if load_dossier:
        try:
            doc = load_visual_bloom_dossier(load_dossier, journal_dir=journal_dir)
        except VisualizerError as exc:
            return str(exc)
        return json.dumps(doc, indent=2)

    add_dossier = _extract_flag_value(args, "--add-to-dossier")
    if add_dossier:
        try:
            out = add_visual_bloom_dossier_section(
                name=add_dossier,
                section_type=_extract_flag_value(args, "--section-type") or "storyboard",
                artifact_ref=_extract_flag_value(args, "--artifact-ref") or "",
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--entry-title") or _extract_flag_value(args, "--dossier-title"),
                summary=_extract_flag_value(args, "--dossier-summary"),
                notes=_extract_flag_value(args, "--entry-note"),
                tags=_extract_flag_value(args, "--dossier-tags") or _extract_flag_value(args, "--tags"),
                sector_family=_extract_flag_value(args, "--sector-family"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom dossier updated: {out}"

    if "--browse-field-libraries" in args:
        rows = list_visual_bloom_field_libraries(journal_dir=journal_dir)
        return json.dumps({"field_libraries": rows, "count": len(rows)}, indent=2)

    create_library = _extract_flag_value(args, "--create-field-library")
    if create_library:
        try:
            path = create_visual_bloom_field_library(
                name=create_library,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--field-library-title"),
                summary=_extract_flag_value(args, "--field-library-summary"),
                tags=_extract_flag_value(args, "--field-library-tags") or _extract_flag_value(args, "--tags"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom field library created: {path}"

    load_library = _extract_flag_value(args, "--load-field-library")
    if load_library:
        try:
            doc = load_visual_bloom_field_library(load_library, journal_dir=journal_dir)
        except VisualizerError as exc:
            return str(exc)
        return json.dumps(doc, indent=2)

    add_library = _extract_flag_value(args, "--add-to-field-library")
    if add_library:
        try:
            out = add_visual_bloom_field_library_entry(
                name=add_library,
                collection_type=_extract_flag_value(args, "--section-type") or "dossier",
                artifact_ref=_extract_flag_value(args, "--artifact-ref") or "",
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--entry-title") or _extract_flag_value(args, "--field-library-title"),
                summary=_extract_flag_value(args, "--field-library-summary"),
                notes=_extract_flag_value(args, "--entry-note"),
                tags=_extract_flag_value(args, "--field-library-tags") or _extract_flag_value(args, "--tags"),
                sector_family=_extract_flag_value(args, "--sector-family"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom field library updated: {out}"

    if "--browse-shelves" in args:
        rows = list_visual_bloom_shelves(journal_dir=journal_dir)
        return json.dumps({"shelves": rows, "count": len(rows)}, indent=2)

    create_shelf = _extract_flag_value(args, "--create-shelf")
    if create_shelf:
        try:
            path = create_visual_bloom_shelf(
                name=create_shelf,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--shelf-title"),
                summary=_extract_flag_value(args, "--shelf-summary"),
                tags=_extract_flag_value(args, "--shelf-tags") or _extract_flag_value(args, "--tags"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom shelf created: {path}"

    load_shelf = _extract_flag_value(args, "--load-shelf")
    if load_shelf:
        try:
            doc = load_visual_bloom_shelf(load_shelf, journal_dir=journal_dir)
        except VisualizerError as exc:
            return str(exc)
        return json.dumps(doc, indent=2)

    add_shelf = _extract_flag_value(args, "--add-to-shelf")
    if add_shelf:
        try:
            out = add_visual_bloom_shelf_item(
                name=add_shelf,
                item_type=_extract_flag_value(args, "--section-type") or "dossier",
                artifact_ref=_extract_flag_value(args, "--artifact-ref") or "",
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--entry-title") or _extract_flag_value(args, "--shelf-title"),
                summary=_extract_flag_value(args, "--shelf-summary"),
                notes=_extract_flag_value(args, "--entry-note"),
                tags=_extract_flag_value(args, "--shelf-tags") or _extract_flag_value(args, "--tags"),
                sector_family=_extract_flag_value(args, "--sector-family"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom shelf updated: {out}"

    if "--browse-catalog" in args:
        try:
            model = build_visual_bloom_catalog_model(journal_dir=journal_dir)
            entries_obj = model.get("entries")
            entries = [e for e in entries_obj if isinstance(e, dict)] if isinstance(entries_obj, list) else []
            filtered = filter_visual_bloom_catalog_entries(
                entries=entries,
                filter_tags=_extract_flag_value(args, "--catalog-filter-tags"),
                filter_sector=_extract_flag_value(args, "--catalog-filter-sector"),
                filter_type=_extract_flag_value(args, "--catalog-filter-type"),
            )
            group_by = _extract_flag_value(args, "--catalog-group-by") or "artifact_type"
            groups = group_visual_bloom_catalog_entries(entries=filtered, group_by=group_by)
            browse_model = {
                **model,
                "filters": {
                    "tags": _extract_flag_value(args, "--catalog-filter-tags") or "",
                    "sector": _extract_flag_value(args, "--catalog-filter-sector") or "",
                    "type": _extract_flag_value(args, "--catalog-filter-type") or "",
                    "group_by": group_by,
                },
                "filtered_entries": filtered,
                "grouped_entries": groups,
            }
            out = _extract_flag_value(args, "--output")
            if out:
                html = render_visual_bloom_catalog_html(browse_model)
                target = write_bloom_file(html, Path(out).expanduser())
                return f"Visual bloom catalog generated: {target}"
        except (VisualizerError, ValueError) as exc:
            return str(exc)
        return json.dumps({
            "catalog": {
                "generated_at": model.get("generated_at", ""),
                "entry_count": model.get("entry_count", 0),
            },
            "filters": browse_model.get("filters", {}),
            "filtered_count": len(filtered),
            "grouped_entries": groups,
        }, indent=2)

    if "--browse-reading-rooms" in args:
        rows = list_visual_bloom_reading_rooms(journal_dir=journal_dir)
        return json.dumps({"reading_rooms": rows, "count": len(rows)}, indent=2)

    create_room = _extract_flag_value(args, "--create-reading-room")
    if create_room:
        try:
            path = create_visual_bloom_reading_room(
                name=create_room,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--reading-room-title"),
                summary=_extract_flag_value(args, "--reading-room-summary"),
                tags=_extract_flag_value(args, "--reading-room-tags") or _extract_flag_value(args, "--tags"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom reading room created: {path}"

    load_room = _extract_flag_value(args, "--load-reading-room")
    if load_room:
        try:
            room = load_visual_bloom_reading_room(load_room, journal_dir=journal_dir)
        except VisualizerError as exc:
            return str(exc)
        return json.dumps(room, indent=2)

    add_room = _extract_flag_value(args, "--add-to-reading-room")
    if add_room:
        try:
            out = add_visual_bloom_reading_room_section(
                name=add_room,
                section_type=_extract_flag_value(args, "--section-type") or "shelf",
                artifact_ref=_extract_flag_value(args, "--artifact-ref") or "",
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--entry-title") or _extract_flag_value(args, "--reading-room-title"),
                summary=_extract_flag_value(args, "--reading-room-summary"),
                notes=_extract_flag_value(args, "--entry-note"),
                tags=_extract_flag_value(args, "--reading-room-tags") or _extract_flag_value(args, "--tags"),
                sector_family=_extract_flag_value(args, "--sector-family"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom reading room updated: {out}"

    if "--browse-collection-maps" in args:
        rows = list_visual_bloom_collection_maps(journal_dir=journal_dir)
        return json.dumps({"collection_maps": rows, "count": len(rows)}, indent=2)

    create_map = _extract_flag_value(args, "--create-collection-map")
    if create_map:
        try:
            path = create_visual_bloom_collection_map(
                name=create_map,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--entry-title"),
                summary=_extract_flag_value(args, "--entry-note"),
                tags=_extract_flag_value(args, "--collection-map-tags") or _extract_flag_value(args, "--tags"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom collection map created: {path}"

    load_map = _extract_flag_value(args, "--load-collection-map")
    if load_map:
        try:
            model = build_visual_bloom_collection_map_model(
                name=load_map,
                journal_dir=journal_dir,
                filter_tags=_extract_flag_value(args, "--collection-map-filter-tags"),
                filter_sector=_extract_flag_value(args, "--collection-map-filter-sector"),
                filter_type=_extract_flag_value(args, "--collection-map-filter-type"),
                group_by=_extract_flag_value(args, "--collection-map-group-by") or "artifact_type",
            )
        except VisualizerError as exc:
            return str(exc)
        return json.dumps(model, indent=2)

    if "--browse-study-halls" in args:
        rows = list_visual_bloom_study_halls(journal_dir=journal_dir)
        return json.dumps({"study_halls": rows, "count": len(rows)}, indent=2)

    create_study_hall = _extract_flag_value(args, "--create-study-hall")
    if create_study_hall:
        try:
            path = create_visual_bloom_study_hall(
                name=create_study_hall,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--study-hall-title"),
                summary=_extract_flag_value(args, "--study-hall-summary"),
                tags=_extract_flag_value(args, "--study-hall-tags") or _extract_flag_value(args, "--tags"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom study hall created: {path}"

    load_study_hall = _extract_flag_value(args, "--load-study-hall")
    if load_study_hall:
        try:
            hall = load_visual_bloom_study_hall(load_study_hall, journal_dir=journal_dir)
        except VisualizerError as exc:
            return str(exc)
        return json.dumps(hall, indent=2)

    add_study_hall = _extract_flag_value(args, "--add-to-study-hall")
    if add_study_hall:
        try:
            out = add_visual_bloom_study_hall_module(
                name=add_study_hall,
                module_type=_extract_flag_value(args, "--section-type") or "reading_room",
                artifact_ref=_extract_flag_value(args, "--artifact-ref") or "",
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--entry-title") or _extract_flag_value(args, "--study-hall-title"),
                summary=_extract_flag_value(args, "--study-hall-summary"),
                notes=_extract_flag_value(args, "--entry-note"),
                tags=_extract_flag_value(args, "--study-hall-tags") or _extract_flag_value(args, "--tags"),
                sector_family=_extract_flag_value(args, "--sector-family"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom study hall updated: {out}"

    if "--browse-thematic-pathways" in args:
        rows = list_visual_bloom_thematic_pathways(journal_dir=journal_dir)
        return json.dumps({"thematic_pathways": rows, "count": len(rows)}, indent=2)

    create_thematic = _extract_flag_value(args, "--create-thematic-pathway")
    if create_thematic:
        try:
            path = create_visual_bloom_thematic_pathway(
                name=create_thematic,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--entry-title"),
                summary=_extract_flag_value(args, "--entry-note"),
                tags=_extract_flag_value(args, "--thematic-pathway-tags") or _extract_flag_value(args, "--tags"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom thematic pathway created: {path}"

    load_thematic = _extract_flag_value(args, "--load-thematic-pathway")
    if load_thematic:
        try:
            model = build_visual_bloom_thematic_pathway_model(
                name=load_thematic,
                journal_dir=journal_dir,
                filter_tags=_extract_flag_value(args, "--thematic-pathway-filter-tags"),
                filter_sector=_extract_flag_value(args, "--thematic-pathway-filter-sector"),
                filter_type=_extract_flag_value(args, "--thematic-pathway-filter-type"),
                group_by=_extract_flag_value(args, "--thematic-pathway-group-by") or "artifact_type",
            )
        except VisualizerError as exc:
            return str(exc)
        return json.dumps(model, indent=2)

    if "--browse-curricula" in args:
        rows = list_visual_bloom_curricula(journal_dir=journal_dir)
        return json.dumps({"curricula": rows, "count": len(rows)}, indent=2)

    create_curriculum = _extract_flag_value(args, "--create-curriculum")
    if create_curriculum:
        try:
            path = create_visual_bloom_curriculum(
                name=create_curriculum,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--curriculum-title"),
                summary=_extract_flag_value(args, "--curriculum-summary"),
                tags=_extract_flag_value(args, "--curriculum-tags") or _extract_flag_value(args, "--tags"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom curriculum created: {path}"

    load_curriculum = _extract_flag_value(args, "--load-curriculum")
    if load_curriculum:
        try:
            model = load_visual_bloom_curriculum(load_curriculum, journal_dir=journal_dir)
        except VisualizerError as exc:
            return str(exc)
        return json.dumps(model, indent=2)

    add_curriculum = _extract_flag_value(args, "--add-to-curriculum")
    if add_curriculum:
        try:
            out = add_visual_bloom_curriculum_unit(
                name=add_curriculum,
                unit_type=_extract_flag_value(args, "--section-type") or "study_hall",
                artifact_ref=_extract_flag_value(args, "--artifact-ref") or "",
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--entry-title") or _extract_flag_value(args, "--curriculum-title"),
                summary=_extract_flag_value(args, "--curriculum-summary"),
                notes=_extract_flag_value(args, "--entry-note"),
                tags=_extract_flag_value(args, "--curriculum-tags") or _extract_flag_value(args, "--tags"),
                sector_family=_extract_flag_value(args, "--sector-family"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom curriculum updated: {out}"

    if "--browse-journey-ensembles" in args:
        rows = list_visual_bloom_journey_ensembles(journal_dir=journal_dir)
        return json.dumps({"journey_ensembles": rows, "count": len(rows)}, indent=2)

    create_ensemble = _extract_flag_value(args, "--create-journey-ensemble")
    if create_ensemble:
        try:
            path = create_visual_bloom_journey_ensemble(
                name=create_ensemble,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--entry-title"),
                summary=_extract_flag_value(args, "--entry-note"),
                tags=_extract_flag_value(args, "--journey-ensemble-tags") or _extract_flag_value(args, "--tags"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom journey ensemble created: {path}"

    load_ensemble = _extract_flag_value(args, "--load-journey-ensemble")
    if load_ensemble:
        try:
            model = build_visual_bloom_journey_ensemble_model(
                name=load_ensemble,
                journal_dir=journal_dir,
                filter_tags=_extract_flag_value(args, "--journey-ensemble-filter-tags"),
                filter_sector=_extract_flag_value(args, "--journey-ensemble-filter-sector"),
                filter_type=_extract_flag_value(args, "--journey-ensemble-filter-type"),
                group_by=_extract_flag_value(args, "--journey-ensemble-group-by") or "artifact_type",
            )
        except VisualizerError as exc:
            return str(exc)
        return json.dumps(model, indent=2)

    if "--browse-syllabi" in args:
        rows = list_visual_bloom_syllabi(journal_dir=journal_dir)
        return json.dumps({"syllabi": rows, "count": len(rows)}, indent=2)

    create_syllabus = _extract_flag_value(args, "--create-syllabus")
    if create_syllabus:
        try:
            path = create_visual_bloom_syllabus(
                name=create_syllabus,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--syllabus-title"),
                summary=_extract_flag_value(args, "--syllabus-summary"),
                tags=_extract_flag_value(args, "--syllabus-tags") or _extract_flag_value(args, "--tags"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom syllabus created: {path}"

    load_syllabus = _extract_flag_value(args, "--load-syllabus")
    if load_syllabus:
        try:
            model = load_visual_bloom_syllabus(load_syllabus, journal_dir=journal_dir)
        except VisualizerError as exc:
            return str(exc)
        return json.dumps(model, indent=2)

    add_syllabus = _extract_flag_value(args, "--add-to-syllabus")
    if add_syllabus:
        try:
            out = add_visual_bloom_syllabus_module(
                name=add_syllabus,
                module_type=_extract_flag_value(args, "--section-type") or "curriculum",
                artifact_ref=_extract_flag_value(args, "--artifact-ref") or "",
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--entry-title") or _extract_flag_value(args, "--syllabus-title"),
                summary=_extract_flag_value(args, "--syllabus-summary"),
                notes=_extract_flag_value(args, "--entry-note"),
                tags=_extract_flag_value(args, "--syllabus-tags") or _extract_flag_value(args, "--tags"),
                sector_family=_extract_flag_value(args, "--sector-family"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom syllabus updated: {out}"

    if "--browse-atlas-cohorts" in args:
        rows = list_visual_bloom_atlas_cohorts(journal_dir=journal_dir)
        return json.dumps({"atlas_cohorts": rows, "count": len(rows)}, indent=2)

    create_cohort = _extract_flag_value(args, "--create-atlas-cohort")
    if create_cohort:
        try:
            path = create_visual_bloom_atlas_cohort(
                name=create_cohort,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--entry-title"),
                summary=_extract_flag_value(args, "--entry-note"),
                tags=_extract_flag_value(args, "--atlas-cohort-tags") or _extract_flag_value(args, "--tags"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom atlas cohort created: {path}"

    load_cohort = _extract_flag_value(args, "--load-atlas-cohort")
    if load_cohort:
        try:
            model = build_visual_bloom_atlas_cohort_model(
                name=load_cohort,
                journal_dir=journal_dir,
                filter_tags=_extract_flag_value(args, "--atlas-cohort-filter-tags"),
                filter_sector=_extract_flag_value(args, "--atlas-cohort-filter-sector"),
                filter_type=_extract_flag_value(args, "--atlas-cohort-filter-type"),
                group_by=_extract_flag_value(args, "--atlas-cohort-group-by") or "artifact_type",
            )
        except VisualizerError as exc:
            return str(exc)
        return json.dumps(model, indent=2)

    search_query = _extract_flag_value(args, "--search")
    if search_query and "--gallery" not in args:
        found = search_visual_bloom_metadata(
            query=search_query,
            journal_dir=journal_dir,
            search_tags=_extract_flag_value(args, "--search-tags"),
            search_type=_extract_flag_value(args, "--search-type"),
            search_bio=_extract_flag_value(args, "--search-bio"),
        )
        return json.dumps({"results": found, "count": len(found)}, indent=2)

    create_pathway = _extract_flag_value(args, "--create-pathway")
    if create_pathway:
        try:
            path = create_visual_bloom_pathway(
                name=create_pathway,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--pathway-title"),
                summary=_extract_flag_value(args, "--pathway-summary"),
                tags=_extract_flag_value(args, "--tags"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom pathway created: {path}"

    load_pathway = _extract_flag_value(args, "--load-pathway")
    if load_pathway:
        try:
            doc = load_visual_bloom_pathway(load_pathway, journal_dir=journal_dir)
        except VisualizerError as exc:
            return str(exc)
        return json.dumps(doc, indent=2)

    create_constellation = _extract_flag_value(args, "--create-constellation")
    if create_constellation:
        try:
            path = create_visual_bloom_constellation(
                name=create_constellation,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--constellation-title"),
                summary=_extract_flag_value(args, "--constellation-summary"),
                tags=_extract_flag_value(args, "--tags"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom constellation created: {path}"

    load_constellation = _extract_flag_value(args, "--load-constellation")
    if load_constellation:
        try:
            doc = load_visual_bloom_constellation(load_constellation, journal_dir=journal_dir)
        except VisualizerError as exc:
            return str(exc)
        return json.dumps(doc, indent=2)

    create_narrative = _extract_flag_value(args, "--create-narrative")
    if create_narrative:
        try:
            path = create_visual_bloom_narrative(
                name=create_narrative,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--narrative-title"),
                summary=_extract_flag_value(args, "--narrative-summary"),
                collection=_extract_flag_value(args, "--collection"),
                tags=_extract_flag_value(args, "--tags"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom narrative created: {path}"

    load_narrative = _extract_flag_value(args, "--load-narrative")
    if load_narrative:
        try:
            doc = load_visual_bloom_narrative(load_narrative, journal_dir=journal_dir)
        except VisualizerError as exc:
            return str(exc)
        return json.dumps(doc, indent=2)

    add_narrative = _extract_flag_value(args, "--add-to-narrative")
    if add_narrative:
        session_entry = _extract_flag_value(args, "--session")
        compare_set_entry = _extract_flag_value(args, "--compare-set")
        left: str | None = None
        right: str | None = None
        if "--compare" in args:
            idx = args.index("--compare")
            if idx + 2 < len(args):
                left, right = args[idx + 1], args[idx + 2]
        try:
            updated = add_visual_bloom_narrative_entry(
                name=add_narrative,
                journal_dir=journal_dir,
                session_ref=session_entry,
                compare_left=left,
                compare_right=right,
                compare_set=compare_set_entry,
                entry_title=_extract_flag_value(args, "--entry-title"),
                entry_note=_extract_flag_value(args, "--entry-note"),
                tags=_extract_flag_value(args, "--tags"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom narrative updated: {updated}"

    link_narrative = _extract_flag_value(args, "--link-narrative")
    if link_narrative:
        try:
            updated = add_visual_bloom_narrative_link(
                name=link_narrative,
                link_type=_extract_flag_value(args, "--link-type") or "narrative",
                target_ref=_extract_flag_value(args, "--target-ref") or "",
                journal_dir=journal_dir,
                label=_extract_flag_value(args, "--entry-title"),
                note=_extract_flag_value(args, "--entry-note"),
                tags=_extract_flag_value(args, "--tags"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom narrative link added: {updated}"

    add_constellation = _extract_flag_value(args, "--add-to-constellation")
    if add_constellation:
        nref = _extract_flag_value(args, "--narrative")
        sref = _extract_flag_value(args, "--session")
        cset = _extract_flag_value(args, "--compare-set")
        left: str | None = None
        right: str | None = None
        if "--compare" in args:
            idx = args.index("--compare")
            if idx + 2 < len(args):
                left, right = args[idx + 1], args[idx + 2]
        try:
            updated = add_visual_bloom_constellation_entry(
                name=add_constellation,
                journal_dir=journal_dir,
                narrative_ref=nref,
                session_ref=sref,
                compare_set=cset,
                compare_left=left,
                compare_right=right,
                entry_title=_extract_flag_value(args, "--entry-title"),
                entry_note=_extract_flag_value(args, "--entry-note"),
                tags=_extract_flag_value(args, "--tags"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom constellation updated: {updated}"

    add_pathway = _extract_flag_value(args, "--add-to-pathway")
    if add_pathway:
        sref = _extract_flag_value(args, "--session")
        nref = _extract_flag_value(args, "--narrative")
        aref = _extract_flag_value(args, "--atlas")
        cref = _extract_flag_value(args, "--constellation")
        left: str | None = None
        right: str | None = None
        if "--compare" in args:
            idx = args.index("--compare")
            if idx + 2 < len(args):
                left, right = args[idx + 1], args[idx + 2]
        try:
            updated = add_visual_bloom_pathway_entry(
                name=add_pathway,
                journal_dir=journal_dir,
                session_ref=sref,
                compare_left=left,
                compare_right=right,
                narrative_ref=nref,
                atlas_ref=aref,
                constellation_ref=cref,
                step_title=_extract_flag_value(args, "--step-title") or _extract_flag_value(args, "--entry-title"),
                step_note=_extract_flag_value(args, "--step-note") or _extract_flag_value(args, "--entry-note"),
                tags=_extract_flag_value(args, "--tags"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom pathway updated: {updated}"

    if "--link-pathway-step" in args:
        idx = args.index("--link-pathway-step")
        if idx + 1 >= len(args):
            return usage
        pname = args[idx + 1]
        from_step = _extract_flag_value(args, "--from-step")
        to_step = _extract_flag_value(args, "--to-step")
        if not from_step or not to_step:
            return "Pathway branch requires --from-step and --to-step"
        try:
            updated = link_visual_bloom_pathway_steps(
                name=pname,
                from_step=from_step,
                to_step=to_step,
                journal_dir=journal_dir,
                branch_label=_extract_flag_value(args, "--branch-label"),
                note=_extract_flag_value(args, "--step-note") or _extract_flag_value(args, "--entry-note"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom pathway linked: {updated}"

    recommend_for = _extract_flag_value(args, "--recommend-for")
    if recommend_for:
        strategy = _extract_flag_value(args, "--recommend-strategy") or "golden_angular"
        try:
            recs = build_visual_bloom_recommendations(target_ref=recommend_for, journal_dir=journal_dir, strategy=strategy)
        except VisualizerError as exc:
            return str(exc)
        return json.dumps({"target_ref": recommend_for, "strategy": strategy, "recommendations": recs, "count": len(recs)}, indent=2)

    if "--benchmark-recommendations" in args:
        raw = _extract_flag_value(args, "--recommend-strategy")
        strategies = [i.strip() for i in raw.split(",") if i.strip()] if raw else None
        summary = benchmark_visual_bloom_recommendations(journal_dir=journal_dir, strategies=strategies)
        return json.dumps(summary, indent=2)

    if "--atlas" in args:
        atlas_target = _extract_flag_value(args, "--atlas-target") or "theoretical"
        atlas_start_ref = _extract_flag_value(args, "--atlas-start-ref")
        atlas_node_val = _extract_flag_value(args, "--atlas-node")
        atlas_node = int(atlas_node_val) if atlas_node_val is not None and atlas_node_val.isdigit() else None
        radius_val = _extract_flag_value(args, "--atlas-max-l1-radius")
        radius = int(radius_val) if radius_val is not None and radius_val.isdigit() else 1
        heat_mode = _extract_flag_value(args, "--atlas-heat-mode") or "target_proximity"
        try:
            generated = launch_visual_bloom_atlas(
                output_path=Path(_extract_flag_value(args, "--output")).expanduser() if _extract_flag_value(args, "--output") else None,
                open_browser=True,
                atlas_target=atlas_target,
                atlas_start_ref=atlas_start_ref,
                atlas_node=atlas_node,
                atlas_max_l1_radius=radius,
                atlas_heat_mode=heat_mode,
                journal_dir=journal_dir,
            )
        except (VisualizerError, ValueError) as exc:
            return str(exc)
        return f"Visual bloom atlas generated: {generated}"

    if "--atlas-gallery" in args:
        try:
            model = build_visual_bloom_atlas_gallery_model(
                journal_dir=journal_dir,
                filter_tags=_extract_flag_value(args, "--storyboard-filter-tags") or _extract_flag_value(args, "--longitudinal-filter-tags"),
                filter_sector=_extract_flag_value(args, "--storyboard-filter-sector") or _extract_flag_value(args, "--longitudinal-filter-sector"),
                filter_target=_extract_flag_value(args, "--longitudinal-filter-target"),
                filter_heat_mode=_extract_flag_value(args, "--atlas-heat-mode"),
            )
            html = render_visual_bloom_atlas_gallery_html(model)
            target = Path(_extract_flag_value(args, "--output")).expanduser() if _extract_flag_value(args, "--output") else Path("/tmp/phios_bloom_atlas_gallery.html")
            written = write_bloom_file(html, target)
        except (VisualizerError, ValueError) as exc:
            return str(exc)
        return f"Visual bloom atlas gallery generated: {written}"

    branch_replay = _extract_flag_value(args, "--branch-replay")
    if branch_replay:
        try:
            generated = launch_visual_bloom_branch_replay(
                pathway_name=branch_replay,
                output_path=Path(_extract_flag_value(args, "--output")).expanduser() if _extract_flag_value(args, "--output") else None,
                open_browser=True,
                journal_dir=journal_dir,
            )
        except (VisualizerError, ValueError) as exc:
            return str(exc)
        return f"Visual bloom branch replay generated: {generated}"

    if "--export-route-compare" in args:
        idx = args.index("--export-route-compare")
        if idx + 2 >= len(args):
            return usage
        start_ref = args[idx + 1]
        outdir = Path(args[idx + 2]).expanduser()
        try:
            out = export_visual_bloom_route_compare_bundle(
                start_ref=start_ref,
                output_dir=outdir,
                route_compare_title=_extract_flag_value(args, "--route-compare-title"),
                route_compare_heat_mode=_extract_flag_value(args, "--route-compare-heat-mode") or "target_proximity",
                include_sector_overlays="--route-compare-include-sector-overlays" in args,
                journal_dir=journal_dir,
                with_integrity="--with-integrity" in args,
            )
        except (VisualizerError, ValueError) as exc:
            return str(exc)
        return f"Visual bloom route compare exported: {out}"

    diag_ref = _extract_flag_value(args, "--show-strategy-diagnostics")
    if diag_ref:
        diag = build_visual_bloom_strategy_diagnostics(target_ref=diag_ref, journal_dir=journal_dir)
        return json.dumps(diag, indent=2)

    if "--export-storyboard" in args:
        idx = args.index("--export-storyboard")
        if idx + 2 >= len(args):
            return usage
        sname = args[idx + 1]
        outdir = Path(args[idx + 2]).expanduser()
        try:
            out = export_visual_bloom_storyboard(
                name=sname,
                output_dir=outdir,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--storyboard-title"),
                filter_tags=_extract_flag_value(args, "--storyboard-filter-tags"),
                filter_sector=_extract_flag_value(args, "--storyboard-filter-sector"),
                filter_type=_extract_flag_value(args, "--storyboard-filter-type"),
                with_integrity="--with-integrity" in args,
            )
        except (VisualizerError, ValueError) as exc:
            return str(exc)
        return f"Visual bloom storyboard exported: {out}"

    if "--export-longitudinal-summary" in args:
        idx = args.index("--export-longitudinal-summary")
        if idx + 1 >= len(args):
            return usage
        outdir = Path(args[idx + 1]).expanduser()
        try:
            out = export_visual_bloom_longitudinal_summary(
                output_dir=outdir,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--longitudinal-title"),
                filter_tags=_extract_flag_value(args, "--longitudinal-filter-tags"),
                filter_sector=_extract_flag_value(args, "--longitudinal-filter-sector"),
                filter_target=_extract_flag_value(args, "--longitudinal-filter-target"),
                with_integrity="--with-integrity" in args,
            )
        except (VisualizerError, ValueError) as exc:
            return str(exc)
        return f"Visual bloom longitudinal summary exported: {out}"

    if "--export-dossier" in args:
        idx = args.index("--export-dossier")
        if idx + 2 >= len(args):
            return usage
        dname = args[idx + 1]
        outdir = Path(args[idx + 2]).expanduser()
        try:
            out = export_visual_bloom_dossier(
                name=dname,
                output_dir=outdir,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--dossier-title"),
                filter_tags=_extract_flag_value(args, "--dossier-filter-tags"),
                filter_sector=_extract_flag_value(args, "--dossier-filter-sector"),
                filter_type=_extract_flag_value(args, "--dossier-filter-type"),
                filter_target=_extract_flag_value(args, "--dossier-filter-target"),
                with_integrity="--with-integrity" in args,
            )
        except (VisualizerError, ValueError) as exc:
            return str(exc)
        return f"Visual bloom dossier exported: {out}"

    if "--export-field-library" in args:
        idx = args.index("--export-field-library")
        if idx + 2 >= len(args):
            return usage
        lname = args[idx + 1]
        outdir = Path(args[idx + 2]).expanduser()
        try:
            out = export_visual_bloom_field_library(
                name=lname,
                output_dir=outdir,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--field-library-title"),
                filter_tags=_extract_flag_value(args, "--field-library-filter-tags"),
                filter_sector=_extract_flag_value(args, "--field-library-filter-sector"),
                filter_type=_extract_flag_value(args, "--field-library-filter-type"),
                filter_target=_extract_flag_value(args, "--field-library-filter-target"),
                with_integrity="--with-integrity" in args,
            )
        except (VisualizerError, ValueError) as exc:
            return str(exc)
        return f"Visual bloom field library exported: {out}"

    if "--export-shelf" in args:
        idx = args.index("--export-shelf")
        if idx + 2 >= len(args):
            return usage
        sname = args[idx + 1]
        outdir = Path(args[idx + 2]).expanduser()
        try:
            out = export_visual_bloom_shelf(
                name=sname,
                output_dir=outdir,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--shelf-title"),
                filter_tags=_extract_flag_value(args, "--shelf-filter-tags"),
                filter_sector=_extract_flag_value(args, "--shelf-filter-sector"),
                filter_type=_extract_flag_value(args, "--shelf-filter-type"),
                with_integrity="--with-integrity" in args,
            )
        except (VisualizerError, ValueError) as exc:
            return str(exc)
        return f"Visual bloom shelf exported: {out}"

    if "--export-reading-room" in args:
        idx = args.index("--export-reading-room")
        if idx + 2 >= len(args):
            return usage
        rname = args[idx + 1]
        outdir = Path(args[idx + 2]).expanduser()
        try:
            out = export_visual_bloom_reading_room(
                name=rname,
                output_dir=outdir,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--reading-room-title"),
                filter_tags=_extract_flag_value(args, "--shelf-filter-tags"),
                filter_sector=_extract_flag_value(args, "--shelf-filter-sector"),
                filter_type=_extract_flag_value(args, "--shelf-filter-type"),
                with_integrity="--with-integrity" in args,
            )
        except (VisualizerError, ValueError) as exc:
            return str(exc)
        return f"Visual bloom reading room exported: {out}"

    if "--export-collection-map" in args:
        idx = args.index("--export-collection-map")
        if idx + 2 >= len(args):
            return usage
        mname = args[idx + 1]
        outdir = Path(args[idx + 2]).expanduser()
        try:
            out = export_visual_bloom_collection_map(
                name=mname,
                output_dir=outdir,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--entry-title"),
                filter_tags=_extract_flag_value(args, "--collection-map-filter-tags"),
                filter_sector=_extract_flag_value(args, "--collection-map-filter-sector"),
                filter_type=_extract_flag_value(args, "--collection-map-filter-type"),
                group_by=_extract_flag_value(args, "--collection-map-group-by") or "artifact_type",
                with_integrity="--with-integrity" in args,
            )
        except (VisualizerError, ValueError) as exc:
            return str(exc)
        return f"Visual bloom collection map exported: {out}"

    if "--export-study-hall" in args:
        idx = args.index("--export-study-hall")
        if idx + 2 >= len(args):
            return usage
        hname = args[idx + 1]
        outdir = Path(args[idx + 2]).expanduser()
        try:
            out = export_visual_bloom_study_hall(
                name=hname,
                output_dir=outdir,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--study-hall-title"),
                filter_tags=_extract_flag_value(args, "--shelf-filter-tags"),
                filter_sector=_extract_flag_value(args, "--shelf-filter-sector"),
                filter_type=_extract_flag_value(args, "--shelf-filter-type"),
                with_integrity="--with-integrity" in args,
            )
        except (VisualizerError, ValueError) as exc:
            return str(exc)
        return f"Visual bloom study hall exported: {out}"

    if "--export-thematic-pathway" in args:
        idx = args.index("--export-thematic-pathway")
        if idx + 2 >= len(args):
            return usage
        tname = args[idx + 1]
        outdir = Path(args[idx + 2]).expanduser()
        try:
            out = export_visual_bloom_thematic_pathway(
                name=tname,
                output_dir=outdir,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--entry-title"),
                filter_tags=_extract_flag_value(args, "--thematic-pathway-filter-tags"),
                filter_sector=_extract_flag_value(args, "--thematic-pathway-filter-sector"),
                filter_type=_extract_flag_value(args, "--thematic-pathway-filter-type"),
                group_by=_extract_flag_value(args, "--thematic-pathway-group-by") or "artifact_type",
                with_integrity="--with-integrity" in args,
            )
        except (VisualizerError, ValueError) as exc:
            return str(exc)
        return f"Visual bloom thematic pathway exported: {out}"

    if "--export-curriculum" in args:
        idx = args.index("--export-curriculum")
        if idx + 2 >= len(args):
            return usage
        cname = args[idx + 1]
        outdir = Path(args[idx + 2]).expanduser()
        try:
            out = export_visual_bloom_curriculum(
                name=cname,
                output_dir=outdir,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--curriculum-title"),
                filter_tags=_extract_flag_value(args, "--shelf-filter-tags"),
                filter_sector=_extract_flag_value(args, "--shelf-filter-sector"),
                filter_type=_extract_flag_value(args, "--shelf-filter-type"),
                with_integrity="--with-integrity" in args,
            )
        except (VisualizerError, ValueError) as exc:
            return str(exc)
        return f"Visual bloom curriculum exported: {out}"

    if "--export-journey-ensemble" in args:
        idx = args.index("--export-journey-ensemble")
        if idx + 2 >= len(args):
            return usage
        jname = args[idx + 1]
        outdir = Path(args[idx + 2]).expanduser()
        try:
            out = export_visual_bloom_journey_ensemble(
                name=jname,
                output_dir=outdir,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--entry-title"),
                filter_tags=_extract_flag_value(args, "--journey-ensemble-filter-tags"),
                filter_sector=_extract_flag_value(args, "--journey-ensemble-filter-sector"),
                filter_type=_extract_flag_value(args, "--journey-ensemble-filter-type"),
                group_by=_extract_flag_value(args, "--journey-ensemble-group-by") or "artifact_type",
                with_integrity="--with-integrity" in args,
            )
        except (VisualizerError, ValueError) as exc:
            return str(exc)
        return f"Visual bloom journey ensemble exported: {out}"

    if "--export-syllabus" in args:
        idx = args.index("--export-syllabus")
        if idx + 2 >= len(args):
            return usage
        sname = args[idx + 1]
        outdir = Path(args[idx + 2]).expanduser()
        try:
            out = export_visual_bloom_syllabus(
                name=sname,
                output_dir=outdir,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--syllabus-title"),
                filter_tags=_extract_flag_value(args, "--shelf-filter-tags"),
                filter_sector=_extract_flag_value(args, "--shelf-filter-sector"),
                filter_type=_extract_flag_value(args, "--shelf-filter-type"),
                with_integrity="--with-integrity" in args,
            )
        except (VisualizerError, ValueError) as exc:
            return str(exc)
        return f"Visual bloom syllabus exported: {out}"

    if "--export-atlas-cohort" in args:
        idx = args.index("--export-atlas-cohort")
        if idx + 2 >= len(args):
            return usage
        cname = args[idx + 1]
        outdir = Path(args[idx + 2]).expanduser()
        try:
            out = export_visual_bloom_atlas_cohort(
                name=cname,
                output_dir=outdir,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--entry-title"),
                filter_tags=_extract_flag_value(args, "--atlas-cohort-filter-tags"),
                filter_sector=_extract_flag_value(args, "--atlas-cohort-filter-sector"),
                filter_type=_extract_flag_value(args, "--atlas-cohort-filter-type"),
                group_by=_extract_flag_value(args, "--atlas-cohort-group-by") or "artifact_type",
                with_integrity="--with-integrity" in args,
            )
        except (VisualizerError, ValueError) as exc:
            return str(exc)
        return f"Visual bloom atlas cohort exported: {out}"

    if "--dashboard" in args:
        generated = launch_visual_bloom_dashboard(
            output_path=Path(_extract_flag_value(args, "--output")).expanduser() if _extract_flag_value(args, "--output") else None,
            open_browser=True,
            journal_dir=journal_dir,
            search=_extract_flag_value(args, "--search"),
        )
        return f"Visual bloom dashboard generated: {generated}"

    if "--export-insight-pack" in args:
        idx = args.index("--export-insight-pack")
        if idx + 2 >= len(args):
            return usage
        pname = args[idx + 1]
        outdir = Path(args[idx + 2]).expanduser()
        try:
            out = export_visual_bloom_insight_pack(
                pathway_name=pname,
                output_dir=outdir,
                journal_dir=journal_dir,
                title=_extract_flag_value(args, "--insight-pack-title"),
                include_atlas="--insight-pack-include-atlas" in args,
                heat_mode=_extract_flag_value(args, "--insight-pack-heat-mode") or "target_proximity",
                with_integrity="--with-integrity" in args,
            )
        except (VisualizerError, ValueError) as exc:
            return str(exc)
        return f"Visual bloom insight pack exported: {out}"

    if "--export-pathway" in args:
        idx = args.index("--export-pathway")
        if idx + 2 >= len(args):
            return usage
        pname = args[idx + 1]
        pdir = Path(args[idx + 2]).expanduser()
        try:
            out_dir = export_visual_bloom_pathway(
                name=pname,
                output_dir=pdir,
                journal_dir=journal_dir,
                with_integrity="--with-integrity" in args,
                tags=_extract_flag_value(args, "--tags"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom pathway exported: {out_dir}"

    if "--export-atlas" in args:
        idx = args.index("--export-atlas")
        if idx + 2 >= len(args):
            return usage
        narrative_name = args[idx + 1]
        atlas_dir = Path(args[idx + 2]).expanduser()
        try:
            out_dir = export_visual_bloom_atlas(
                name=narrative_name,
                output_dir=atlas_dir,
                journal_dir=journal_dir,
                with_integrity="--with-integrity" in args,
                tags=_extract_flag_value(args, "--tags"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom atlas exported: {out_dir}"

    if "--export-constellation" in args:
        idx = args.index("--export-constellation")
        if idx + 2 >= len(args):
            return usage
        cname = args[idx + 1]
        cdir = Path(args[idx + 2]).expanduser()
        try:
            out_dir = export_visual_bloom_constellation(
                name=cname,
                output_dir=cdir,
                journal_dir=journal_dir,
                with_integrity="--with-integrity" in args,
                tags=_extract_flag_value(args, "--tags"),
            )
        except VisualizerError as exc:
            return str(exc)
        return f"Visual bloom constellation exported: {out_dir}"

    if "--gallery" in args:
        gallery_collection = _extract_flag_value(args, "--collection")
        generated = launch_visual_bloom_gallery(
            output_path=Path(_extract_flag_value(args, "--output")).expanduser() if _extract_flag_value(args, "--output") else None,
            open_browser=True,
            journal_dir=journal_dir,
            collection=gallery_collection,
            search=_extract_flag_value(args, "--search"),
            mode=_extract_flag_value(args, "--filter-mode"),
            preset=_extract_flag_value(args, "--filter-preset"),
            lens=_extract_flag_value(args, "--filter-lens"),
            audio=_extract_flag_value(args, "--filter-audio"),
            label=_extract_flag_value(args, "--filter-label"),
            session_id=_extract_flag_value(args, "--filter-session"),
        )
        return f"Visual bloom gallery generated: {generated}"

    browse_collection = _extract_flag_value(args, "--browse-collection")
    if "--browse" in args or browse_collection is not None:
        sessions = list_visual_bloom_sessions(journal_dir=journal_dir, collection=browse_collection)
        return json.dumps({"sessions": sessions, "count": len(sessions)}, indent=2)

    compare_refs: tuple[str, str] | None = None
    if "--compare" in args:
        idx = args.index("--compare")
        if idx + 2 >= len(args):
            return usage
        compare_refs = (args[idx + 1], args[idx + 2])

    load_compare = _extract_flag_value(args, "--load-compare")
    if load_compare:
        try:
            comp = load_visual_bloom_compare_set(load_compare, journal_dir=journal_dir)
        except VisualizerError as exc:
            return str(exc)
        compare_refs = (str(comp.get("left_ref", "")), str(comp.get("right_ref", "")))
        if not compare_refs[0] or not compare_refs[1]:
            return f"Compare set '{load_compare}' is missing refs"

    export_report = _extract_flag_value(args, "--export-report")
    export_report_path = Path(export_report).expanduser() if export_report else None
    export_bundle = _extract_flag_value(args, "--export-bundle")
    export_bundle_path = Path(export_bundle).expanduser() if export_bundle else None
    with_integrity = "--with-integrity" in args
    bundle_label = _extract_flag_value(args, "--bundle-label")
    save_compare = _extract_flag_value(args, "--save-compare")

    raw_state_idx = _extract_flag_value(args, "--state-idx")
    state_idx: int | None = None
    if raw_state_idx is not None:
        try:
            state_idx = int(raw_state_idx)
        except ValueError:
            return usage
    step = 1 if "--next-state" in args else (-1 if "--prev-state" in args else 0)
    if "--next-state" in args and "--prev-state" in args:
        return usage

    mode = _extract_flag_value(args, "--mode")
    if mode != "sonic":
        return usage

    live = "--live" in args
    journal = "--journal" in args
    replay = _extract_flag_value(args, "--replay")
    out = _extract_flag_value(args, "--output")
    output_path = Path(out).expanduser() if out else None

    label = _extract_flag_value(args, "--label")
    collection = _extract_flag_value(args, "--collection")
    preset = _extract_flag_value(args, "--preset")
    lens = _extract_flag_value(args, "--lens")
    audio_reactive = "--audio-reactive" in args

    if preset is not None and preset not in VALID_PRESETS:
        return f"Unknown preset: {preset}. Valid presets: {', '.join(sorted(VALID_PRESETS))}"
    if lens is not None and lens not in VALID_LENSES:
        return f"Unknown lens: {lens}. Valid lenses: {', '.join(sorted(VALID_LENSES))}"

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
        if compare_refs is not None:
            if export_bundle_path is not None:
                bundle = export_visual_bloom_bundle(
                    left_ref=compare_refs[0],
                    right_ref=compare_refs[1],
                    output_path=export_bundle_path,
                    journal_dir=journal_dir,
                    with_integrity=with_integrity,
                    bundle_label=bundle_label,
                )
                if save_compare:
                    save_visual_bloom_compare_set(
                        name=save_compare,
                        left_ref=compare_refs[0],
                        right_ref=compare_refs[1],
                        journal_dir=journal_dir,
                        report_path=(bundle / "compare_report.json"),
                        bundle_path=bundle,
                        tags=_extract_flag_value(args, "--tags"),
                    )
                return f"Visual bloom bundle exported: {bundle}"
            generated = launch_compare_bloom(compare_refs[0], compare_refs[1], output_path=output_path, open_browser=True, journal_dir=journal_dir, export_report_path=export_report_path)
            if save_compare:
                save_visual_bloom_compare_set(
                    name=save_compare,
                    left_ref=compare_refs[0],
                    right_ref=compare_refs[1],
                    journal_dir=journal_dir,
                    report_path=export_report_path,
                    tags=_extract_flag_value(args, "--tags"),
                )
            return f"Compare visual bloom generated: {generated}"
        if replay:
            generated = launch_replay_bloom(replay, output_path=output_path, open_browser=True, journal_dir=journal_dir, preset=preset, lens=lens, audio_reactive=audio_reactive, state_idx=state_idx, step=step)
            return f"Replay visual bloom generated: {generated}"
        if live:
            generated = launch_live_bloom(
                output_path=output_path,
                refresh_seconds=refresh_seconds,
                duration=duration,
                open_browser=True,
                journal=journal,
                journal_dir=journal_dir,
                label=label,
                preset=preset,
                lens=lens,
                audio_reactive=audio_reactive,
                collection=collection,
            )
            return f"Live visual bloom running: {generated}"
        generated = launch_bloom(
            output_path=output_path,
            open_browser=True,
            journal=journal,
            journal_dir=journal_dir,
            label=label,
            preset=preset,
            lens=lens,
            audio_reactive=audio_reactive,
            collection=collection,
        )
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
            f"Kernel runtime: {'on' if ((report.get('kernel_runtime') or {}).get('enabled')) else 'off'}",
            f"Adapters: {((report.get('kernel_runtime') or {}).get('configured_adapter') or 'legacy')} / shadow {((report.get('kernel_runtime') or {}).get('shadow_adapter') or 'none')}",
            f"Compare mode: {'on' if ((report.get('kernel_runtime') or {}).get('compare_mode')) else 'off'}",
            f"Recent compare samples: {((report.get('kernel_rollout') or {}).get('recent_samples') or 0)}",
            "Source of truth: PhiKernel",
        ]
    )


def cmd_eval_kernel(args: list[str], session: object | None = None) -> str:
    if "--help" in args or "-h" in args:
        return "Usage: eval-kernel [--input <cases.json>] [--compare <primary> <shadow>] [--report <path.json>] [--json]"

    input_path = _extract_flag_value(args, "--input") if "--input" in args else None
    report_path = _extract_flag_value(args, "--report") if "--report" in args else None

    compare: tuple[str, str] | None = None
    if "--compare" in args:
        idx = args.index("--compare")
        if idx + 2 >= len(args):
            return "Usage: eval-kernel [--input <cases.json>] [--compare <primary> <shadow>] [--report <path.json>] [--json]"
        compare = (args[idx + 1], args[idx + 2])

    try:
        cases = load_eval_cases(input_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return f"Failed to load kernel evaluation cases: {exc}"

    cfg = KernelRuntimeConfig.from_env()
    if compare:
        cfg = KernelRuntimeConfig(enabled=True, adapter=compare[0], shadow_adapter=compare[1], compare_mode=True)

    if not cfg.enabled:
        return "Kernel runtime evaluation is disabled. Set PHIOS_KERNEL_ENABLED=true or pass --compare."

    store = KernelRolloutStore()
    result = run_kernel_evaluation(adapter=PhiKernelCLIAdapter(), cases=cases, config=cfg, store=store)

    export_target = None
    if report_path:
        compare_records = [
            row.get("runtime", {}).get("compare_record")
            for row in result.get("results", [])
            if isinstance(row, dict)
            and isinstance(row.get("runtime"), dict)
            and isinstance(row.get("runtime", {}).get("compare_record"), dict)
        ]
        export_target = str(export_compare_report(report_path, compare_records))

    payload = {
        "config": {
            "enabled": cfg.enabled,
            "adapter": cfg.adapter,
            "shadow_adapter": cfg.shadow_adapter,
            "compare_mode": cfg.compare_mode,
        },
        "summary": result.get("summary", {}),
        "total_cases": result.get("total_cases", 0),
        "recent_rollout": recent_rollout_status(store=store),
    }
    if export_target:
        payload["report_path"] = export_target

    if "--json" in args:
        return json.dumps(payload, indent=2)

    summary = payload.get("summary", {})
    return "\n".join(
        [
            "PHI369 Labs / Parallax · Kernel Rollout Evaluation",
            f"cases: {payload.get('total_cases', 0)}",
            f"primary adapter: {cfg.adapter}",
            f"shadow adapter: {cfg.shadow_adapter or 'none'}",
            f"compare mode: {'on' if cfg.compare_mode else 'off'}",
            f"verdict changes: {summary.get('verdict_changes', 0)}",
            f"recommendation changes: {summary.get('recommendation_changes', 0)}",
            f"null-result disagreement: {summary.get('null_result_disagreement', 0)}",
            f"avg deltas: {json.dumps(summary.get('avg_score_deltas', {}), sort_keys=True)}",
            f"report: {export_target or 'not written'}",
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

    if action == "topic":
        if len(args) < 2:
            return "Usage: memory topic <topic>"
        return json.dumps(get_agent_memory(args[1]), indent=2)

    if action == "coherence":
        if len(args) < 2:
            return "Usage: memory coherence <topic>"
        return json.dumps(get_agent_memory_coherence(args[1]), indent=2)

    if action == "recent":
        local_recent = list_recent_agent_deliberations(limit=10)
        tbrc_recent = bridge.archive_timeline(limit=5)
        return json.dumps({"agent_deliberations": local_recent, "tbrc_recent": tbrc_recent}, indent=2)

    if action == "store":
        if len(args) < 2:
            return "Usage: memory store <topic> --positions <json> --outcome <text> --winner <figure> --trace <comma floats> [--tags a,b] --yes"
        if "--yes" not in args:
            return "Refusing memory store without confirmation. Re-run with --yes"
        decision = is_capability_allowed(CAP_AGENT_MEMORY_WRITE)
        if not decision.allowed:
            return json.dumps(
                {
                    "ok": False,
                    "allowed": False,
                    "reason": decision.reason,
                    "capability_scope": decision.capability_scope,
                    "policy_source": decision.policy_source,
                    "error_code": "AGENT_MEMORY_WRITE_NOT_PERMITTED",
                },
                indent=2,
            )
        topic = args[1]
        positions_raw = _arg_value(args, "--positions")
        outcome = _arg_value(args, "--outcome") or ""
        winner = _arg_value(args, "--winner") or ""
        trace_raw = _arg_value(args, "--trace") or ""
        tags_raw = _arg_value(args, "--tags") or ""
        if not positions_raw or not outcome or not winner:
            return "Usage: memory store <topic> --positions <json> --outcome <text> --winner <figure> --trace <comma floats> [--tags a,b] --yes"
        try:
            parsed_positions = json.loads(positions_raw)
        except Exception:
            return "Invalid --positions JSON"
        if not isinstance(parsed_positions, list):
            return "--positions must be a JSON list"
        trace: list[float] = []
        for token in [part.strip() for part in trace_raw.split(",") if part.strip()]:
            try:
                trace.append(float(token))
            except ValueError:
                return "--trace must be comma-separated floats"
        tags = [part.strip() for part in tags_raw.split(",") if part.strip()]
        result = store_agent_deliberation(
            topic=topic,
            positions=parsed_positions,
            outcome=outcome,
            winning_figure=winner,
            coherence_trace=trace,
            tags=tags,
        )
        return json.dumps(result, indent=2)

    return "Usage: memory [status|search <query>|recent|topic <topic>|coherence <topic>|store <topic> --positions <json> --outcome <text> --winner <figure> --trace <comma floats> [--tags a,b] --yes]"


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


def _arg_value(args: list[str], flag: str) -> str | None:
    if flag not in args:
        return None
    idx = args.index(flag)
    if idx + 1 >= len(args):
        return None
    return args[idx + 1]


def cmd_dispatch(args: list[str], session: object | None = None) -> str:
    if args and args[0] == "optimize":
        graph_raw = _arg_value(args, "--graph") or ""
        if not graph_raw:
            return "Usage: dispatch optimize --graph <json> [--json]"
        try:
            graph_obj = json.loads(graph_raw)
        except Exception:
            return "--graph must be valid JSON object"
        if not isinstance(graph_obj, dict):
            return "--graph must be JSON object"

        plan = optimize_dispatch_graph(graph_obj)
        payload = {
            "ok": bool(plan.get("ok", False)),
            "read_only": True,
            "advisory_only": True,
            "plan": plan,
            "summary": summarize_dispatch_graph_plan(plan),
            "experimental": True,
        }
        if "--json" in args:
            return json.dumps(payload, indent=2)
        if not payload["ok"]:
            return f"Dispatch graph optimization failed: {plan.get('reason', 'invalid graph')}"
        summary = payload["summary"]
        return "\n".join(
            [
                "Dispatch graph optimization",
                f"nodes: {summary.get('nodes', 0)}",
                f"waves: {summary.get('waves', 0)}",
                f"graph_score: {float(summary.get('graph_score', 0.0)):.3f}",
                f"bottlenecks: {', '.join(str(x) for x in summary.get('bottlenecks', [])[:5]) or 'none'}",
            ]
        )

    if not args:
        return (
            "Usage: dispatch <task> [--field-guided] [--arch <name>] [--review-panel] "
            "[--coherence-gate <float>] [--dry-run] [--stream]"
        )

    value_flags = {"--arch", "--coherence-gate"}
    task_tokens: list[str] = []
    skip_next = False
    for token in args:
        if skip_next:
            skip_next = False
            continue
        if token in value_flags:
            skip_next = True
            continue
        if token.startswith("--"):
            continue
        task_tokens.append(token)
    task = " ".join(task_tokens).strip()
    if not task:
        return "Usage: dispatch <task> [--field-guided] [--dry-run]"

    field_guided = "--field-guided" in args
    dry_run = "--dry-run" in args
    review_panel = "--review-panel" in args
    stream = "--stream" in args
    arch = _arg_value(args, "--arch")
    coherence_gate_raw = _arg_value(args, "--coherence-gate")
    coherence_gate = float(coherence_gate_raw) if coherence_gate_raw else None

    dispatch_decision = is_capability_allowed(CAP_AGENT_DISPATCH)
    if not dry_run and not dispatch_decision.allowed:
        return json.dumps(
            {
                "ok": False,
                "allowed": False,
                "reason": dispatch_decision.reason,
                "capability_scope": dispatch_decision.capability_scope,
                "policy_source": dispatch_decision.policy_source,
                "error_code": "AGENT_DISPATCH_NOT_PERMITTED",
            },
            indent=2,
        )

    adapter = PhiKernelCLIAdapter()
    context = build_dispatch_context(
        task=task,
        adapter=adapter,
        field_guided=field_guided,
        arch=arch,
        review_panel=review_panel,
    )

    if coherence_gate is not None and field_guided:
        field = context.get("field_state", {})
        current = field.get("C_current") if isinstance(field, dict) else None
        if isinstance(current, (float, int)) and float(current) < coherence_gate:
            return json.dumps(
                {
                    "ok": False,
                    "allowed": False,
                    "reason": f"Coherence gate not met: C_current={float(current):.3f} < {coherence_gate:.3f}",
                    "error_code": "COHERENCE_GATE_BLOCKED",
                },
                indent=2,
            )

    plan = run_agentception_plan(task=task, context=context)
    if dry_run:
        return json.dumps(
            {
                "ok": True,
                "dry_run": True,
                "task": task,
                "context": context,
                "plan": plan,
            },
            indent=2,
        )

    run = dispatch_agentception_run(task=task, context=context, plan=plan, stream=stream)
    events = stream_agent_run_events(str(run.get("run_id", "")))
    storyboard = persist_dispatch_storyboard(run=run, plan=plan, events=events)
    return json.dumps({"ok": True, "run": run, "storyboard": storyboard}, indent=2)


def cmd_agents(args: list[str], session: object | None = None) -> str:
    action = args[0] if args else "list"
    if action == "list":
        return json.dumps({"runs": list_agent_runs(active_only=False)}, indent=2)

    if action == "status":
        if len(args) < 2:
            return "Usage: agents status <run_id>"
        return json.dumps(get_agent_run_status(args[1]), indent=2)

    if action == "kill":
        if len(args) < 2:
            return "Usage: agents kill <run_id> --yes"
        if "--yes" not in args:
            return "Refusing kill without confirmation. Use: phi agents kill <run_id> --yes"
        kill_decision = is_capability_allowed(CAP_AGENT_KILL)
        if not kill_decision.allowed:
            return json.dumps(
                {
                    "ok": False,
                    "allowed": False,
                    "reason": kill_decision.reason,
                    "capability_scope": kill_decision.capability_scope,
                    "policy_source": kill_decision.policy_source,
                    "error_code": "AGENT_KILL_NOT_PERMITTED",
                },
                indent=2,
            )
        return json.dumps(cancel_agent_run(args[1]), indent=2)

    if action == "log":
        if len(args) < 2:
            return "Usage: agents log <run_id>"
        return json.dumps({"run_id": args[1], "events": stream_agent_run_events(args[1])}, indent=2)

    if action == "figures":
        top_raw = _arg_value(args, "--top")
        sector = _arg_value(args, "--sector")
        try:
            top = int(top_raw) if top_raw else 10
        except ValueError:
            return "--top must be an integer"
        return json.dumps(build_figure_fitness_report(sector=sector, top=top), indent=2)

    if action == "evolve":
        top_raw = _arg_value(args, "--top")
        sector = _arg_value(args, "--sector")
        task_key = _arg_value(args, "--task-key") or "agent_evolution"
        required_skill = _arg_value(args, "--skill")
        min_coherence_raw = _arg_value(args, "--min-coherence")
        try:
            top = int(top_raw) if top_raw else 10
        except ValueError:
            return "--top must be an integer"
        min_coherence = None
        if min_coherence_raw is not None:
            try:
                min_coherence = float(min_coherence_raw)
            except ValueError:
                return "--min-coherence must be float"
        landscape = summarize_figure_fitness_landscape(top=top, sector=sector)
        recommendation = recommend_figure_for_task(
            task_key=task_key,
            sector=sector,
            required_skill=required_skill,
            min_coherence=min_coherence,
        )
        return json.dumps(
            {
                "ok": True,
                "advisory_only": True,
                "landscape": landscape,
                "recommendation": recommendation,
                "experimental": True,
            },
            indent=2,
        )

    return "Usage: agents [list|status <run_id>|kill <run_id> --yes|log <run_id>|figures [--top <n>] [--sector <name>]|evolve [--top <n>] [--sector <name>] [--task-key <key>] [--skill <skill>] [--min-coherence <v>]]"


def cmd_recommend_arch(args: list[str], session: object | None = None) -> str:
    adapter = PhiKernelCLIAdapter()
    context = build_cognitive_arch_context(adapter)
    recommendation = recommend_cognitive_architecture(context)

    payload = {
        "ok": True,
        "read_only": True,
        "experimental": True,
        "recommendation": recommendation,
        "context": context,
    }
    if "--json" in args:
        return json.dumps(payload, indent=2)

    return "\n".join(
        [
            "Field-guided cognitive architecture recommendation",
            f"figure: {recommendation.get('figure', 'unknown')}",
            f"archetype: {recommendation.get('archetype', 'unknown')}",
            f"confidence: {float(recommendation.get('confidence', 0.0)):.3f}",
            f"reason: {recommendation.get('reason', '')}",
            f"signals: observer={context.get('observer_state')} alignment={context.get('self_alignment')} entropy={context.get('entropy_load')} emergence={context.get('emergence_pressure')}",
            "framing: C* theoretical; bio-vacuum target experimental; Hunter's C unconfirmed.",
        ]
    )


def cmd_recommend_atoms(args: list[str], session: object | None = None) -> str:
    adapter = PhiKernelCLIAdapter()
    context = build_sector_atom_context(adapter)
    recommendation = recommend_cognitive_atom_overrides(adapter)

    payload = {
        "ok": True,
        "read_only": True,
        "experimental": True,
        "recommendation": recommendation,
        "context": context,
    }
    if "--json" in args:
        return json.dumps(payload, indent=2)

    atom_overrides = recommendation.get("atom_overrides", {})
    return "\n".join(
        [
            "Sector-to-atom cognitive override recommendation",
            f"confidence: {float(recommendation.get('confidence', 0.0)):.3f}",
            f"epistemic_style: {atom_overrides.get('epistemic_style', 'n/a')}",
            f"creativity_level: {atom_overrides.get('creativity_level', 'n/a')}",
            f"uncertainty_handling: {atom_overrides.get('uncertainty_handling', 'n/a')}",
            f"error_posture: {atom_overrides.get('error_posture', 'n/a')}",
            f"cognitive_rhythm: {atom_overrides.get('cognitive_rhythm', 'n/a')}",
            f"collaboration_posture: {atom_overrides.get('collaboration_posture', 'n/a')}",
            f"communication_style: {atom_overrides.get('communication_style', 'n/a')}",
            "framing: C* theoretical; bio-vacuum target experimental; Hunter's C unconfirmed.",
        ]
    )


def cmd_debate(args: list[str], session: object | None = None) -> str:
    action = args[0] if args else "gate"
    if action != "gate":
        return "Usage: debate gate --session-id <id> --round <n> --positions <json> [--threshold <float>] [--persist] [--json]"

    session_id = _arg_value(args, "--session-id") or ""
    round_raw = _arg_value(args, "--round") or "1"
    positions_raw = _arg_value(args, "--positions") or "[]"
    threshold_raw = _arg_value(args, "--threshold")
    persist = "--persist" in args

    if not session_id:
        return "Usage: debate gate --session-id <id> --round <n> --positions <json> [--threshold <float>] [--persist] [--json]"

    try:
        round_idx = int(round_raw)
    except ValueError:
        return "--round must be an integer"

    try:
        positions_obj = json.loads(positions_raw)
    except Exception:
        return "--positions must be valid JSON list"
    if not isinstance(positions_obj, list):
        return "--positions must be a JSON list"

    threshold = None
    if threshold_raw is not None:
        try:
            threshold = float(threshold_raw)
        except ValueError:
            return "--threshold must be float"

    adapter = PhiKernelCLIAdapter()
    positions = [p for p in positions_obj if isinstance(p, dict)]
    context = build_debate_context(
        adapter=adapter,
        session_id=session_id,
        round_index=round_idx,
        positions=positions,
        threshold=threshold,
    )
    result = evaluate_debate_coherence_gate(context)
    payload: dict[str, object] = {
        "ok": True,
        "session_id": session_id,
        "result": result,
        "position_summary": context.get("position_summary", {}),
        "experimental": True,
    }
    if persist:
        payload["persistence"] = persist_debate_outcome(session_id=session_id, gate_result=result, positions=positions)

    if "--json" in args:
        return json.dumps(payload, indent=2)
    return "\n".join(
        [
            "Debate coherence gate",
            f"session: {session_id}",
            f"round: {result.get('round', round_idx)}",
            f"action: {result.get('action', 'continue')}",
            f"coherence: {float(result.get('coherence', 0.0)):.3f}",
            f"threshold: {float(result.get('threshold', 0.0)):.3f}",
            f"reason: {result.get('reason', '')}",
        ]
    )


def cmd_review(args: list[str], session: object | None = None) -> str:
    action = args[0] if args else "gate"
    if action != "gate":
        return "Usage: review gate --round <n> --reviewer-grades <json> --reviewer-critiques <json> [--panel-id <id>] [--pr-number <n>] [--mediator-summary <text>] [--persist] [--json]"

    round_raw = _arg_value(args, "--round") or "1"
    grades_raw = _arg_value(args, "--reviewer-grades") or "[]"
    critiques_raw = _arg_value(args, "--reviewer-critiques") or "[]"
    panel_id = _arg_value(args, "--panel-id") or "default"
    pr_raw = _arg_value(args, "--pr-number")
    mediator_summary = _arg_value(args, "--mediator-summary")
    persist = "--persist" in args

    try:
        round_idx = int(round_raw)
    except ValueError:
        return "--round must be an integer"

    try:
        grades_obj = json.loads(grades_raw)
    except Exception:
        return "--reviewer-grades must be valid JSON list"
    try:
        critiques_obj = json.loads(critiques_raw)
    except Exception:
        return "--reviewer-critiques must be valid JSON list"

    if not isinstance(grades_obj, list):
        return "--reviewer-grades must be JSON list"
    if not isinstance(critiques_obj, list):
        return "--reviewer-critiques must be JSON list"

    pr_number = None
    if pr_raw is not None:
        try:
            pr_number = int(pr_raw)
        except ValueError:
            return "--pr-number must be an integer"

    adapter = PhiKernelCLIAdapter()
    grades = [g for g in grades_obj if isinstance(g, dict)]
    critiques = [str(c) for c in critiques_obj if isinstance(c, str)]
    context = build_review_context(
        adapter=adapter,
        round_index=round_idx,
        reviewer_grades=grades,
        reviewer_critiques=critiques,
        panel_id=panel_id,
        pr_number=pr_number,
    )
    result = evaluate_review_coherence_gate(context)
    payload: dict[str, object] = {
        "ok": True,
        "panel_id": panel_id,
        "pr_number": pr_number,
        "result": result,
        "grade_summary": context.get("grade_summary", {}),
        "experimental": True,
    }
    if persist:
        payload["persistence"] = persist_review_outcome(
            panel_id=panel_id,
            pr_number=pr_number,
            gate_result=result,
            reviewer_grades=grades,
            reviewer_critiques=critiques,
            mediator_summary=mediator_summary,
        )

    if "--json" in args:
        return json.dumps(payload, indent=2)

    return "\n".join(
        [
            "Review coherence gate",
            f"panel: {panel_id}",
            f"round: {result.get('round', round_idx)}",
            f"action: {result.get('action', 'continue')}",
            f"coherence: {float(result.get('coherence', 0.0)):.3f}",
            f"reason: {result.get('reason', '')}",
        ]
    )


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
    "eval-kernel": cmd_eval_kernel,
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
    "dispatch": cmd_dispatch,
    "agents": cmd_agents,
    "recommend-arch": cmd_recommend_arch,
    "recommend-atoms": cmd_recommend_atoms,
    "debate": cmd_debate,
    "review": cmd_review,
    "build": cmd_build,
}
