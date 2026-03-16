"""Preset browse resources for MCP (read-only)."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.mcp.browse_presets import get_browse_preset
from phios.mcp.resources.archive import (
    read_archive_atlas_index_resource,
    read_archive_curricula_index_resource,
    read_archive_journey_ensembles_index_resource,
    read_archive_longitudinal_index_resource,
    read_archive_pathways_index_resource,
    read_archive_route_compares_index_resource,
)
from phios.mcp.resources.capstones import (
    read_capstones_atlas_cohorts_rollup_resource,
    read_capstones_dossiers_rollup_family_resource,
    read_capstones_field_libraries_rollup_family_resource,
    read_capstones_storyboards_rollup_family_resource,
    read_capstones_syllabi_rollup_resource,
)
from phios.mcp.resources.catalogs import (
    read_catalog_capstones_resource,
    read_catalog_collections_resource,
    read_catalog_learning_resource,
    read_catalog_programs_resource,
)
from phios.mcp.resources.collections import (
    read_curricula_rollup_resource,
    read_field_libraries_rollup_resource,
    read_journey_ensembles_rollup_resource,
    read_reading_rooms_rollup_resource,
    read_shelves_rollup_resource,
    read_study_halls_rollup_resource,
)
from phios.mcp.resources.history import read_recent_field_snapshots_resource, read_recent_sessions_resource
from phios.mcp.resources.maps import (
    read_capstones_map_resource,
    read_collections_map_resource,
    read_learning_map_resource,
    read_programs_map_resource,
)
from phios.mcp.resources.observatory import (
    read_observatory_dashboard_resource,
    read_observatory_field_libraries_index_resource,
    read_observatory_reading_rooms_index_resource,
    read_observatory_shelves_index_resource,
    read_observatory_storyboards_index_resource,
    read_observatory_study_halls_index_resource,
)
from phios.mcp.resources.programs import (
    read_programs_curricula_rollup_resource,
    read_programs_journey_ensembles_rollup_resource,
    read_programs_study_halls_rollup_resource,
    read_programs_syllabi_rollup_resource,
    read_programs_thematic_pathways_rollup_resource,
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
    elif name == "learning_paths":
        views = {
            "curricula": read_archive_curricula_index_resource(limit=15),
            "journey_ensembles": read_archive_journey_ensembles_index_resource(limit=15),
            "study_halls": read_observatory_study_halls_index_resource(limit=15),
            "curricula_rollup": read_curricula_rollup_resource(),
            "journey_ensembles_rollup": read_journey_ensembles_rollup_resource(),
        }
    elif name == "collections":
        views = {
            "field_libraries_rollup": read_field_libraries_rollup_resource(),
            "shelves_rollup": read_shelves_rollup_resource(),
            "reading_rooms_rollup": read_reading_rooms_rollup_resource(),
            "study_halls_rollup": read_study_halls_rollup_resource(),
        }
    elif name == "programs":
        views = {
            "curricula_rollup": read_curricula_rollup_resource(),
            "study_halls_rollup": read_study_halls_rollup_resource(),
            "reading_rooms_rollup": read_reading_rooms_rollup_resource(),
        }
    elif name == "comparative":
        views = {
            "route_compares": read_archive_route_compares_index_resource(limit=15),
            "longitudinal": read_archive_longitudinal_index_resource(),
            "atlas": read_archive_atlas_index_resource(limit=15),
        }
    elif name == "curricula":
        views = {
            "curricula_rollup": read_programs_curricula_rollup_resource(),
            "syllabi_rollup": read_programs_syllabi_rollup_resource(),
            "curricula_index": read_archive_curricula_index_resource(limit=15),
        }
    elif name == "cohorts":
        views = {
            "atlas": read_archive_atlas_index_resource(limit=15),
            "journey_ensembles_rollup": read_programs_journey_ensembles_rollup_resource(),
            "thematic_pathways_rollup": read_programs_thematic_pathways_rollup_resource(),
        }
    elif name == "learning_tracks":
        views = {
            "thematic_pathways_rollup": read_programs_thematic_pathways_rollup_resource(),
            "study_halls_rollup": read_programs_study_halls_rollup_resource(),
            "journey_ensembles_rollup": read_programs_journey_ensembles_rollup_resource(),
        }
    elif name == "capstones":
        views = {
            "syllabi_rollup": read_capstones_syllabi_rollup_resource(),
            "atlas_cohorts_rollup": read_capstones_atlas_cohorts_rollup_resource(),
            "dossiers_rollup_family": read_capstones_dossiers_rollup_family_resource(),
            "storyboards_rollup_family": read_capstones_storyboards_rollup_family_resource(),
        }
    elif name == "collections_family":
        views = {
            "field_libraries_rollup_family": read_capstones_field_libraries_rollup_family_resource(),
            "field_libraries_rollup": read_field_libraries_rollup_resource(),
            "shelves_rollup": read_shelves_rollup_resource(),
            "reading_rooms_rollup": read_reading_rooms_rollup_resource(),
        }
    elif name == "learning_programs":
        views = {
            "curricula_rollup": read_programs_curricula_rollup_resource(),
            "thematic_pathways_rollup": read_programs_thematic_pathways_rollup_resource(),
            "syllabi_rollup": read_capstones_syllabi_rollup_resource(),
        }
    elif name == "comparative_learning":
        views = {
            "atlas_cohorts_rollup": read_capstones_atlas_cohorts_rollup_resource(),
            "route_compares": read_archive_route_compares_index_resource(limit=15),
            "longitudinal": read_archive_longitudinal_index_resource(),
        }
    elif name == "study_tracks":
        views = {
            "study_halls_rollup": read_programs_study_halls_rollup_resource(),
            "thematic_pathways_rollup": read_programs_thematic_pathways_rollup_resource(),
            "journey_ensembles_rollup": read_programs_journey_ensembles_rollup_resource(),
        }
    elif name == "observatory_families":
        views = {
            "storyboards_index": read_observatory_storyboards_index_resource(limit=15),
            "study_halls_index": read_observatory_study_halls_index_resource(limit=15),
            "field_libraries_index": read_observatory_field_libraries_index_resource(limit=15),
        }
    elif name == "learning_families":
        views = {
            "learning_catalog": read_catalog_learning_resource(),
            "curricula_rollup": read_programs_curricula_rollup_resource(),
            "thematic_pathways_rollup": read_programs_thematic_pathways_rollup_resource(),
        }
    elif name == "collection_families":
        views = {
            "collections_catalog": read_catalog_collections_resource(),
            "field_libraries_rollup": read_field_libraries_rollup_resource(),
            "shelves_rollup": read_shelves_rollup_resource(),
            "reading_rooms_rollup": read_reading_rooms_rollup_resource(),
        }
    elif name == "capstone_families":
        views = {
            "capstones_catalog": read_catalog_capstones_resource(),
            "syllabi_rollup": read_capstones_syllabi_rollup_resource(),
            "atlas_cohorts_rollup": read_capstones_atlas_cohorts_rollup_resource(),
        }
    elif name == "archive_families":
        views = {
            "programs_catalog": read_catalog_programs_resource(),
            "pathways": read_archive_pathways_index_resource(limit=15),
            "route_compares": read_archive_route_compares_index_resource(limit=15),
            "longitudinal": read_archive_longitudinal_index_resource(),
        }
    elif name == "archive_groups":
        views = {
            "archive_families": read_browse_preset_resource("archive_families"),
            "programs_catalog": read_catalog_programs_resource(),
            "programs_map": read_programs_map_resource(),
        }
    elif name == "learning_maps":
        views = {
            "learning_map": read_learning_map_resource(),
            "capstones_map": read_capstones_map_resource(),
            "programs_map": read_programs_map_resource(),
            "collections_map": read_collections_map_resource(),
        }
    elif name == "cross_catalog":
        views = {
            "learning_catalog": read_catalog_learning_resource(),
            "capstones_catalog": read_catalog_capstones_resource(),
            "programs_catalog": read_catalog_programs_resource(),
            "collections_catalog": read_catalog_collections_resource(),
            "learning_map": read_learning_map_resource(),
        }
    elif name == "program_families":
        views = {
            "curricula_rollup": read_programs_curricula_rollup_resource(),
            "thematic_pathways_rollup": read_programs_thematic_pathways_rollup_resource(),
            "programs_map": read_programs_map_resource(),
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
