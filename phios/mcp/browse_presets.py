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
    "learning_paths": {
        "description": "Learning-path focused view across curricula/journeys/study halls.",
        "resources": [
            "phios://browse/learning_paths",
            "phios://archive/curricula/index",
            "phios://archive/journey_ensembles/index",
            "phios://collections/curricula/rollup",
        ],
        "tools": ["phi_archive_summary", "phi_collection_summary"],
    },
    "collections": {
        "description": "Collection/library rollup browsing view.",
        "resources": [
            "phios://browse/collections",
            "phios://collections/field_libraries/rollup",
            "phios://collections/shelves/rollup",
            "phios://collections/reading_rooms/rollup",
        ],
        "tools": ["phi_collection_summary", "phi_library_summary"],
    },
    "programs": {
        "description": "Program-like learning surfaces (curricula, study halls, reading rooms).",
        "resources": [
            "phios://browse/programs",
            "phios://collections/curricula/rollup",
            "phios://collections/study_halls/rollup",
            "phios://collections/reading_rooms/rollup",
        ],
        "tools": ["phi_collection_summary", "phi_archive_summary"],
    },
    "comparative": {
        "description": "Comparative/archive diagnostics view with route and longitudinal context.",
        "resources": [
            "phios://browse/comparative",
            "phios://archive/route_compares/index",
            "phios://archive/longitudinal/index",
        ],
        "tools": ["phi_archive_summary", "phi_atlas_summary"],
    },
    "curricula": {
        "description": "Curriculum-first program browsing view.",
        "resources": [
            "phios://browse/curricula",
            "phios://programs/curricula/rollup",
            "phios://programs/syllabi/rollup",
        ],
        "tools": ["phi_program_summary", "phi_curation_summary"],
    },
    "cohorts": {
        "description": "Cohort-level learning view grounded in atlas and journeys.",
        "resources": [
            "phios://browse/cohorts",
            "phios://archive/atlas/index",
            "phios://programs/journey_ensembles/rollup",
        ],
        "tools": ["phi_program_summary"],
    },
    "learning_tracks": {
        "description": "Learning-track view across thematic pathways and study halls.",
        "resources": [
            "phios://browse/learning_tracks",
            "phios://programs/thematic_pathways/rollup",
            "phios://programs/study_halls/rollup",
        ],
        "tools": ["phi_program_summary", "phi_curation_summary"],
    },
    "capstones": {
        "description": "Capstone-family browse over syllabi/atlas/dossier/storyboard artifacts.",
        "resources": [
            "phios://browse/capstones",
            "phios://capstones/syllabi/rollup",
            "phios://capstones/atlas_cohorts/rollup",
            "phios://capstones/dossiers/rollup_family",
            "phios://capstones/storyboards/rollup_family",
        ],
        "tools": ["phi_capstone_summary", "phi_curation_summary"],
    },
    "collections_family": {
        "description": "Collection-family rollup browse view.",
        "resources": [
            "phios://browse/collections_family",
            "phios://capstones/field_libraries/rollup_family",
            "phios://collections/field_libraries/rollup",
            "phios://collections/shelves/rollup",
        ],
        "tools": ["phi_capstone_summary", "phi_collection_summary"],
    },
    "learning_programs": {
        "description": "Program + capstone learning family view.",
        "resources": [
            "phios://browse/learning_programs",
            "phios://programs/curricula/rollup",
            "phios://programs/thematic_pathways/rollup",
            "phios://capstones/syllabi/rollup",
        ],
        "tools": ["phi_program_summary", "phi_capstone_summary"],
    },
    "comparative_learning": {
        "description": "Comparative learning view with atlas cohorts + route compare context.",
        "resources": [
            "phios://browse/comparative_learning",
            "phios://capstones/atlas_cohorts/rollup",
            "phios://archive/route_compares/index",
            "phios://archive/longitudinal/index",
        ],
        "tools": ["phi_archive_summary", "phi_capstone_summary"],
    },
    "study_tracks": {
        "description": "Study-track view across study halls and thematic pathways.",
        "resources": [
            "phios://browse/study_tracks",
            "phios://programs/study_halls/rollup",
            "phios://programs/thematic_pathways/rollup",
        ],
        "tools": ["phi_program_summary", "phi_capstone_summary"],
    },
    "observatory_families": {
        "description": "Grouped observatory-family navigation surface.",
        "resources": [
            "phios://browse/observatory_families",
            "phios://observatory/storyboards/index",
            "phios://observatory/dossiers/index",
            "phios://observatory/field_libraries/index",
        ],
        "tools": ["phi_browse_observatory", "phi_observatory_summary"],
    },
    "learning_families": {
        "description": "Grouped learning family navigation across catalogs/programs.",
        "resources": [
            "phios://browse/learning_families",
            "phios://catalogs/learning",
            "phios://programs/curricula/rollup",
            "phios://programs/thematic_pathways/rollup",
        ],
        "tools": ["phi_program_summary", "phi_catalog_summary"],
    },
    "collection_families": {
        "description": "Grouped collection family browsing using rollups and catalogs.",
        "resources": [
            "phios://browse/collection_families",
            "phios://catalogs/collections",
            "phios://collections/field_libraries/rollup",
            "phios://collections/shelves/rollup",
        ],
        "tools": ["phi_collection_summary", "phi_catalog_summary"],
    },
    "capstone_families": {
        "description": "Grouped capstone family browsing using capstone catalog surfaces.",
        "resources": [
            "phios://browse/capstone_families",
            "phios://catalogs/capstones",
            "phios://capstones/syllabi/rollup",
            "phios://capstones/atlas_cohorts/rollup",
        ],
        "tools": ["phi_capstone_summary", "phi_catalog_summary"],
    },
    "archive_families": {
        "description": "Grouped archive-family browsing with archive indexes and catalogs.",
        "resources": [
            "phios://browse/archive_families",
            "phios://catalogs/programs",
            "phios://archive/pathways/index",
            "phios://archive/route_compares/index",
        ],
        "tools": ["phi_archive_summary", "phi_catalog_summary"],
    },
    "archive_groups": {
        "description": "Grouped archive-family navigation including map and catalog context.",
        "resources": [
            "phios://browse/archive_groups",
            "phios://browse/archive_families",
            "phios://catalogs/programs",
            "phios://maps/programs",
        ],
        "tools": ["phi_archive_summary", "phi_learning_map_summary"],
    },
    "learning_maps": {
        "description": "Cross-catalog learning map browsing surface.",
        "resources": [
            "phios://browse/learning_maps",
            "phios://maps/learning",
            "phios://maps/capstones",
            "phios://maps/programs",
        ],
        "tools": ["phi_learning_map_summary", "phi_catalog_summary"],
    },
    "cross_catalog": {
        "description": "Cross-catalog family navigation across learning/program/capstone/collection surfaces.",
        "resources": [
            "phios://browse/cross_catalog",
            "phios://catalogs/learning",
            "phios://catalogs/capstones",
            "phios://catalogs/programs",
            "phios://catalogs/collections",
        ],
        "tools": ["phi_catalog_summary", "phi_learning_map_summary"],
    },
    "program_families": {
        "description": "Program-family browse view with rollups and maps.",
        "resources": [
            "phios://browse/program_families",
            "phios://programs/curricula/rollup",
            "phios://programs/thematic_pathways/rollup",
            "phios://maps/programs",
        ],
        "tools": ["phi_program_summary", "phi_learning_map_summary"],
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
