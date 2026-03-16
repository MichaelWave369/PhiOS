"""Session/archive read-safe summary tools for MCP Phase 7."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.adapters.phik import PhiKernelCLIAdapter
from phios.mcp.policy import CAP_READ_HISTORY, denied_capability_payload, is_capability_allowed
from phios.mcp.resources.archive import (
    read_archive_atlas_index_resource,
    read_archive_curricula_index_resource,
    read_archive_journey_ensembles_index_resource,
    read_archive_longitudinal_index_resource,
    read_archive_pathways_index_resource,
    read_archive_route_compares_index_resource,
)
from phios.mcp.resources.sessions import (
    read_sessions_current_resource,
    read_sessions_recent_checkins_resource,
    read_sessions_recent_reports_resource,
)
from phios.mcp.schema import with_tool_schema


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_phi_session_summary(adapter: PhiKernelCLIAdapter) -> dict[str, object]:
    """Return bounded summary of current/recent session-oriented read data."""

    decision = is_capability_allowed(CAP_READ_HISTORY)
    if not decision.allowed:
        return with_tool_schema(denied_capability_payload(decision=decision, error_code="SESSION_SUMMARY_NOT_PERMITTED"))

    current = read_sessions_current_resource(adapter)
    checkins = read_sessions_recent_checkins_resource(limit=10)
    reports = read_sessions_recent_reports_resource(limit=10)

    return with_tool_schema(
        {
            "ok": True,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "capability_scope": decision.capability_scope,
            "policy_source": decision.policy_source,
            "generated_at": _utc_now_iso(),
            "summary": {
                "checkin_count": checkins.get("count", 0) if isinstance(checkins, dict) else 0,
                "report_count": reports.get("count", 0) if isinstance(reports, dict) else 0,
                "session_state": current.get("summary", {}).get("session_state", "unknown") if isinstance(current, dict) else "unknown",
            },
            "current": current,
            "recent_checkins": checkins,
            "recent_reports": reports,
        }
    )


def run_phi_archive_summary() -> dict[str, object]:
    """Return bounded summary over archive browsing read-only resources."""

    decision = is_capability_allowed(CAP_READ_HISTORY)
    if not decision.allowed:
        return with_tool_schema(denied_capability_payload(decision=decision, error_code="ARCHIVE_SUMMARY_NOT_PERMITTED"))

    pathways = read_archive_pathways_index_resource(limit=10)
    atlas = read_archive_atlas_index_resource(limit=10)
    curricula = read_archive_curricula_index_resource(limit=10)
    journeys = read_archive_journey_ensembles_index_resource(limit=10)
    route_compares = read_archive_route_compares_index_resource(limit=10)
    longitudinal = read_archive_longitudinal_index_resource()

    return with_tool_schema(
        {
            "ok": True,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "capability_scope": decision.capability_scope,
            "policy_source": decision.policy_source,
            "generated_at": _utc_now_iso(),
            "summary": {
                "pathway_count": pathways.get("count", 0) if isinstance(pathways, dict) else 0,
                "atlas_count": atlas.get("count", 0) if isinstance(atlas, dict) else 0,
                "curricula_count": curricula.get("count", 0) if isinstance(curricula, dict) else 0,
                "journey_ensemble_count": journeys.get("count", 0) if isinstance(journeys, dict) else 0,
                "route_compare_count": route_compares.get("count", 0) if isinstance(route_compares, dict) else 0,
                "longitudinal_count": longitudinal.get("count", 0) if isinstance(longitudinal, dict) else 0,
            },
            "pathways": pathways,
            "atlas": atlas,
            "curricula": curricula,
            "journey_ensembles": journeys,
            "route_compares": route_compares,
            "longitudinal": longitudinal,
        }
    )
