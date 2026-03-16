"""Prompt implementation for ``field_guidance``."""

from __future__ import annotations

import json

from phios.adapters.phik import PhiKernelCLIAdapter
from phios.core.lt_engine import compute_lt
from phios.core.phik_service import build_coherence_report, build_status_report
from phios.mcp.schema import MCP_SCHEMA_VERSION, PROMPT_VERSION


def build_field_guidance_prompt(adapter: PhiKernelCLIAdapter) -> str:
    """Build live, grounded operator guidance prompt text.

    The prompt intentionally preserves careful framing: it treats runtime values as
    observed state, does not overclaim theoretical or experimental targets, and keeps
    Hunter's C unconfirmed.
    """

    status = build_status_report(adapter)
    coherence = build_coherence_report(adapter)
    lt = compute_lt()

    payload = {
        "schema_version": MCP_SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "status": status,
        "coherence": coherence,
        "lt": lt,
        "observatory_resources": [
            "phios://observatory/index",
            "phios://observatory/dashboard",
            "phios://observatory/atlas_gallery",
            "phios://observatory/storyboards/recent",
            "phios://observatory/dossiers/recent",
            "phios://observatory/field_libraries/recent",
            "phios://observatory/storyboards/index",
            "phios://observatory/dossiers/index",
            "phios://observatory/field_libraries/index",
            "phios://observatory/shelves/index",
            "phios://observatory/reading_rooms/index",
            "phios://observatory/study_halls/index",
            "phios://mcp/discovery",
        ],
        "observatory_summary_tools": [
            "phi_observatory_summary",
            "phi_recent_activity",
            "phi_library_summary",
            "phi_storyboard_summary",
            "phi_atlas_summary",
            "phi_discovery",
            "phi_browse_observatory",
        ],
        "discovery_surfaces": [
            "phios://mcp/discovery",
            "phi_discovery",
        ],
        "session_resources": [
            "phios://sessions/current",
            "phios://sessions/recent_checkins",
            "phios://sessions/recent_reports",
        ],
        "archive_resources": [
            "phios://archive/pathways/index",
            "phios://archive/atlas/index",
            "phios://archive/route_compares/index",
            "phios://archive/longitudinal/index",
            "phios://archive/curricula/index",
            "phios://archive/journey_ensembles/index",
        ],
        "framing": {
            "theoretical_C_star": "Treat C* as a theoretical attractor.",
            "experimental_bio_vacuum_target": (
                "Treat bio-vacuum targets as experimental metadata, not established truth."
            ),
            "hunters_c": "Hunter's C remains unconfirmed.",
        },
    }

    return (
        "You are the PhiOS field guidance operator assistant. Use only the grounded live "
        "state below. Maintain a read-first safety posture, avoid overclaiming, and preserve "
        "the distinction between theoretical C*, experimental bio-vacuum targets, and "
        "unconfirmed Hunter's C.\n\n"
        f"LIVE_STATE_JSON:\n{json.dumps(payload, indent=2)}\n\n"
        "Respond with:\n"
        "1) concise field interpretation,\n"
        "2) low-risk next actions,\n"
        "3) explicit safety posture."
    )
