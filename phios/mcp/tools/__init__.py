"""MCP tools for PhiOS Phase 1-15."""

from .ask import run_phi_ask
from .agent_memory import phi_store_deliberation
from .cognitive_arch import run_phi_recommend_cognitive_arch
from .debate import phi_debate_coherence_gate
from .review import phi_review_coherence_gate
from .agents import (
    run_phi_agent_status,
    run_phi_dispatch_agents,
    run_phi_kill_agent,
    run_phi_list_agents,
)
from .discovery import (
    run_phi_discovery,
    run_phi_discovery_dashboard_summary,
    run_phi_navigation_console_summary,
)
from .observatory import (
    run_phi_atlas_summary,
    run_phi_library_summary,
    run_phi_observatory_summary,
    run_phi_recent_activity,
    run_phi_storyboard_summary,
    run_phi_browse_observatory,
)
from .pulse import run_phi_pulse_once
from .session_archive import (
    run_phi_archive_summary,
    run_phi_capstone_summary,
    run_phi_catalog_summary,
    run_phi_learning_map_summary,
    run_phi_collection_summary,
    run_phi_curation_summary,
    run_phi_program_summary,
    run_phi_session_summary,
)
from .status import run_phi_status

__all__ = [
    "run_phi_status",
    "run_phi_ask",
    "run_phi_pulse_once",
    "run_phi_discovery",
    "run_phi_discovery_dashboard_summary",
    "run_phi_navigation_console_summary",
    "run_phi_observatory_summary",
    "run_phi_recent_activity",
    "run_phi_library_summary",
    "run_phi_storyboard_summary",
    "run_phi_atlas_summary",
    "run_phi_browse_observatory",
    "run_phi_session_summary",
    "run_phi_archive_summary",
    "run_phi_capstone_summary",
    "run_phi_catalog_summary",
    "run_phi_learning_map_summary",
    "run_phi_collection_summary",
    "run_phi_program_summary",
    "run_phi_curation_summary",
    "run_phi_dispatch_agents",
    "run_phi_list_agents",
    "run_phi_agent_status",
    "run_phi_kill_agent",
    "run_phi_recommend_cognitive_arch",
    "phi_store_deliberation",
    "phi_debate_coherence_gate",
    "phi_review_coherence_gate",
]
