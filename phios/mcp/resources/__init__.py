"""Read-only MCP resources for PhiOS Phase 1/2/3/4/5/6."""

from .coherence_lt import read_coherence_lt_resource
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
    "read_mcp_discovery_resource",
]
