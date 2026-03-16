"""Preset browse resources for Phase 8 (read-only)."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.mcp.browse_presets import get_browse_preset
from phios.mcp.resources.archive import (
    read_archive_atlas_index_resource,
    read_archive_curricula_index_resource,
    read_archive_journey_ensembles_index_resource,
    read_archive_pathways_index_resource,
    read_archive_route_compares_index_resource,
)
from phios.mcp.resources.history import read_recent_field_snapshots_resource, read_recent_sessions_resource
from phios.mcp.resources.observatory import (
    read_observatory_dashboard_resource,
    read_observatory_field_libraries_index_resource,
    read_observatory_reading_rooms_index_resource,
    read_observatory_shelves_index_resource,
    read_observatory_storyboards_index_resource,
    read_observatory_study_halls_index_resource,
)
from phios.mcp.resources.sessions import (
    read_sessions_recent_checkins_resource,
    read_sessions_recent_reports_resource,
)
from phios.mcp.schema import with_resource_schema


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_browse_preset_resource(preset: str) -> dict[str, object]:
    """Return deterministic pre-filtered browse views for common client tasks."""

    name = (preset or "").strip().lower()
    definition = get_browse_preset(name)
    if not definition:
        return with_resource_schema(
            {
                "generated_at": _utc_now_iso(),
                "preset": name,
                "available": False,
                "error": {"code": "UNKNOWN_PRESET", "message": f"Unknown browse preset '{name}'."},
            }
        )

    views: dict[str, object] = {}
    if name == "overview":
        views = {
            "dashboard": read_observatory_dashboard_resource(),
            "pathways": read_archive_pathways_index_resource(limit=5),
            "sessions": read_recent_sessions_resource(limit=5),
        }
    elif name == "recent":
        views = {
            "recent_sessions": read_recent_sessions_resource(limit=10),
            "recent_checkins": read_sessions_recent_checkins_resource(limit=10),
            "recent_reports": read_sessions_recent_reports_resource(limit=10),
            "recent_field_snapshots": read_recent_field_snapshots_resource(limit=10),
        }
    elif name == "observatory":
        views = {
            "dashboard": read_observatory_dashboard_resource(),
            "storyboards_index": read_observatory_storyboards_index_resource(limit=10),
            "study_halls_index": read_observatory_study_halls_index_resource(limit=10),
        }
    elif name == "sessions":
        views = {
            "recent_checkins": read_sessions_recent_checkins_resource(limit=15),
            "recent_reports": read_sessions_recent_reports_resource(limit=15),
        }
    elif name == "archive":
        views = {
            "pathways": read_archive_pathways_index_resource(limit=15),
            "atlas": read_archive_atlas_index_resource(limit=15),
            "route_compares": read_archive_route_compares_index_resource(limit=15),
        }
    elif name == "learning":
        views = {
            "curricula": read_archive_curricula_index_resource(limit=15),
            "journey_ensembles": read_archive_journey_ensembles_index_resource(limit=15),
            "study_halls": read_observatory_study_halls_index_resource(limit=15),
        }
    elif name == "libraries":
        views = {
            "field_libraries": read_observatory_field_libraries_index_resource(limit=15),
            "shelves": read_observatory_shelves_index_resource(limit=15),
            "reading_rooms": read_observatory_reading_rooms_index_resource(limit=15),
        }

    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "preset": name,
            "available": True,
            "definition": definition,
            "views": views,
        }
    )
