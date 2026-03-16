"""Stable client-oriented browsing preset definitions (Phase 8)."""

from __future__ import annotations

BROWSE_PRESETS: dict[str, dict[str, object]] = {
    "overview": {
        "description": "Broad cross-surface overview for quick client orientation.",
        "resources": [
            "phios://mcp/discovery",
            "phios://field/state",
            "phios://system/status",
            "phios://browse/overview",
        ],
        "tools": ["phi_discovery", "phi_observatory_summary", "phi_archive_summary"],
    },
    "recent": {
        "description": "Recent activity-first view across history/sessions/observatory.",
        "resources": [
            "phios://history/recent_sessions",
            "phios://history/recent_field_snapshots",
            "phios://sessions/recent_checkins",
            "phios://browse/recent",
        ],
        "tools": ["phi_recent_activity", "phi_session_summary"],
    },
    "observatory": {
        "description": "Observatory browsing-focused view.",
        "resources": [
            "phios://observatory/dashboard",
            "phios://observatory/atlas_gallery",
            "phios://observatory/storyboards/index",
            "phios://browse/observatory",
        ],
        "tools": ["phi_observatory_summary", "phi_browse_observatory", "phi_storyboard_summary"],
    },
    "sessions": {
        "description": "Session-oriented read workflow view.",
        "resources": [
            "phios://sessions/current",
            "phios://sessions/recent_checkins",
            "phios://sessions/recent_reports",
            "phios://browse/sessions",
        ],
        "tools": ["phi_session_summary"],
    },
    "archive": {
        "description": "Archive navigation-oriented view.",
        "resources": [
            "phios://archive/pathways/index",
            "phios://archive/atlas/index",
            "phios://archive/route_compares/index",
            "phios://browse/archive",
        ],
        "tools": ["phi_archive_summary", "phi_atlas_summary"],
    },
    "learning": {
        "description": "Learning/curriculum/journey oriented archive view.",
        "resources": [
            "phios://archive/curricula/index",
            "phios://archive/journey_ensembles/index",
            "phios://observatory/study_halls/index",
            "phios://browse/learning",
        ],
        "tools": ["phi_archive_summary", "phi_library_summary"],
    },
    "libraries": {
        "description": "Library/shelf/reading-room focused observatory view.",
        "resources": [
            "phios://observatory/field_libraries/index",
            "phios://observatory/shelves/index",
            "phios://observatory/reading_rooms/index",
            "phios://browse/libraries",
        ],
        "tools": ["phi_library_summary", "phi_browse_observatory"],
    },
}


def list_mcp_browse_presets() -> list[str]:
    return sorted(BROWSE_PRESETS.keys())


def get_browse_preset(preset: str) -> dict[str, object]:
    return dict(BROWSE_PRESETS[preset]) if preset in BROWSE_PRESETS else {}
