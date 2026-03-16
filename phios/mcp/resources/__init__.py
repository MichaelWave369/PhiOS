"""Read-only MCP resources for PhiOS Phase 1-15."""

from .agents import (
    read_agent_run_events_resource,
    read_agent_run_resource,
    read_agents_active_resource,
)
from .archive import (
    read_archive_atlas_index_resource,
    read_archive_curricula_index_resource,
    read_archive_journey_ensembles_index_resource,
    read_archive_longitudinal_index_resource,
    read_archive_pathways_index_resource,
    read_archive_route_compares_index_resource,
)
from .browse import read_browse_preset_resource
from .capstones import (
    read_capstones_atlas_cohorts_rollup_resource,
    read_capstones_dossiers_rollup_family_resource,
    read_capstones_field_libraries_rollup_family_resource,
    read_capstones_storyboards_rollup_family_resource,
    read_capstones_syllabi_rollup_resource,
)
from .catalogs import (
    read_catalog_capstones_resource,
    read_catalog_collections_resource,
    read_catalog_learning_resource,
    read_catalog_programs_resource,
)
from .coherence_lt import read_coherence_lt_resource
from .collections import (
    read_curricula_rollup_resource,
    read_field_libraries_rollup_resource,
    read_journey_ensembles_rollup_resource,
    read_reading_rooms_rollup_resource,
    read_shelves_rollup_resource,
    read_study_halls_rollup_resource,
)
from .consoles import (
    read_consoles_archive_resource,
    read_consoles_capstones_resource,
    read_consoles_learning_resource,
    read_consoles_navigation_resource,
)
from .dashboards import (
    read_dashboards_archive_resource,
    read_dashboards_capstones_resource,
    read_dashboards_discovery_resource,
    read_dashboards_learning_resource,
)
from .discovery import read_mcp_discovery_resource
from .families import (
    read_families_capstones_resource,
    read_families_dashboard_capstones_resource,
    read_families_dashboard_learning_resource,
    read_families_dashboard_overview_resource,
    read_families_learning_resource,
    read_families_overview_resource,
)
from .field_state import read_field_state_resource
from .history import (
    read_recent_capsules_resource,
    read_recent_field_snapshots_resource,
    read_recent_sessions_resource,
)
from .maps import (
    read_capstones_map_resource,
    read_collections_map_resource,
    read_learning_map_resource,
    read_programs_map_resource,
)
from .observatory import (
    read_observatory_atlas_gallery_resource,
    read_observatory_dashboard_resource,
    read_observatory_dossiers_index_resource,
    read_observatory_field_libraries_index_resource,
    read_observatory_index_resource,
    read_observatory_reading_rooms_index_resource,
    read_observatory_recent_dossiers_resource,
    read_observatory_recent_field_libraries_resource,
    read_observatory_recent_storyboards_resource,
    read_observatory_shelves_index_resource,
    read_observatory_storyboards_index_resource,
    read_observatory_study_halls_index_resource,
)
from .programs import (
    read_programs_curricula_rollup_resource,
    read_programs_journey_ensembles_rollup_resource,
    read_programs_study_halls_rollup_resource,
    read_programs_syllabi_rollup_resource,
    read_programs_thematic_pathways_rollup_resource,
)
from .sessions import (
    read_sessions_current_resource,
    read_sessions_recent_checkins_resource,
    read_sessions_recent_reports_resource,
)
from .status import read_system_status_resource

__all__ = [
    "read_field_state_resource",
    "read_coherence_lt_resource",
    "read_system_status_resource",
    "read_recent_capsules_resource",
    "read_recent_sessions_resource",
    "read_recent_field_snapshots_resource",
    "read_observatory_index_resource",
    "read_observatory_dashboard_resource",
    "read_observatory_atlas_gallery_resource",
    "read_observatory_recent_storyboards_resource",
    "read_observatory_recent_dossiers_resource",
    "read_observatory_recent_field_libraries_resource",
    "read_observatory_storyboards_index_resource",
    "read_observatory_dossiers_index_resource",
    "read_observatory_field_libraries_index_resource",
    "read_observatory_shelves_index_resource",
    "read_observatory_reading_rooms_index_resource",
    "read_observatory_study_halls_index_resource",
    "read_sessions_current_resource",
    "read_sessions_recent_checkins_resource",
    "read_sessions_recent_reports_resource",
    "read_archive_pathways_index_resource",
    "read_archive_atlas_index_resource",
    "read_archive_route_compares_index_resource",
    "read_archive_longitudinal_index_resource",
    "read_archive_curricula_index_resource",
    "read_archive_journey_ensembles_index_resource",
    "read_mcp_discovery_resource",
    "read_families_capstones_resource",
    "read_families_learning_resource",
    "read_families_overview_resource",
    "read_dashboards_capstones_resource",
    "read_dashboards_learning_resource",
    "read_dashboards_archive_resource",
    "read_dashboards_discovery_resource",
    "read_browse_preset_resource",
    "read_field_libraries_rollup_resource",
    "read_shelves_rollup_resource",
    "read_reading_rooms_rollup_resource",
    "read_study_halls_rollup_resource",
    "read_curricula_rollup_resource",
    "read_journey_ensembles_rollup_resource",
    "read_programs_curricula_rollup_resource",
    "read_programs_study_halls_rollup_resource",
    "read_programs_thematic_pathways_rollup_resource",
    "read_programs_syllabi_rollup_resource",
    "read_programs_journey_ensembles_rollup_resource",
    "read_capstones_syllabi_rollup_resource",
    "read_capstones_atlas_cohorts_rollup_resource",
    "read_capstones_field_libraries_rollup_family_resource",
    "read_capstones_dossiers_rollup_family_resource",
    "read_capstones_storyboards_rollup_family_resource",
    "read_catalog_learning_resource",
    "read_catalog_capstones_resource",
    "read_catalog_programs_resource",
    "read_catalog_collections_resource",
    "read_learning_map_resource",
    "read_capstones_map_resource",
    "read_programs_map_resource",
    "read_collections_map_resource",
    "read_dashboards_discovery_resource",
    "read_dashboards_archive_resource",
    "read_dashboards_learning_resource",
    "read_dashboards_capstones_resource",
    "read_families_overview_resource",
    "read_families_learning_resource",
    "read_families_capstones_resource",
    "read_families_dashboard_overview_resource",
    "read_families_dashboard_learning_resource",
    "read_families_dashboard_capstones_resource",
    "read_consoles_navigation_resource",
    "read_consoles_archive_resource",
    "read_consoles_learning_resource",
    "read_consoles_capstones_resource",
    "read_agents_active_resource",
    "read_agent_run_resource",
    "read_agent_run_events_resource",
]
