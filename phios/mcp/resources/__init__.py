"""Read-only MCP resources for PhiOS Phase 1/2/3/4/5/6/7/8."""

from .archive import (
    read_archive_atlas_index_resource,
    read_archive_curricula_index_resource,
    read_archive_journey_ensembles_index_resource,
    read_archive_longitudinal_index_resource,
    read_archive_pathways_index_resource,
    read_archive_route_compares_index_resource,
)
from .browse import read_browse_preset_resource
from .coherence_lt import read_coherence_lt_resource
from .collections import (
    read_curricula_rollup_resource,
    read_field_libraries_rollup_resource,
    read_journey_ensembles_rollup_resource,
    read_reading_rooms_rollup_resource,
    read_shelves_rollup_resource,
    read_study_halls_rollup_resource,
)
from .discovery import read_mcp_discovery_resource
from .field_state import read_field_state_resource
from .history import (
    read_recent_capsules_resource,
    read_recent_field_snapshots_resource,
    read_recent_sessions_resource,
)
from .observatory import (
    read_observatory_atlas_gallery_resource,
    read_observatory_dashboard_resource,
    read_observatory_index_resource,
    read_observatory_recent_dossiers_resource,
    read_observatory_recent_field_libraries_resource,
    read_observatory_recent_storyboards_resource,
    read_observatory_dossiers_index_resource,
    read_observatory_field_libraries_index_resource,
    read_observatory_reading_rooms_index_resource,
    read_observatory_shelves_index_resource,
    read_observatory_storyboards_index_resource,
    read_observatory_study_halls_index_resource,
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
    "read_browse_preset_resource",
]
