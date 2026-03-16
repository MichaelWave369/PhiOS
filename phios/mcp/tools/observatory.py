"""Read-safe observatory summary MCP tools (Phase 4)."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.adapters.phik import PhiKernelCLIAdapter
from phios.mcp.policy import (
    CAP_READ_HISTORY,
    CAP_READ_OBSERVATORY,
    CapabilityDecision,
    denied_capability_payload,
    is_capability_allowed,
)
from phios.mcp.resources.history import (
    read_recent_capsules_resource,
    read_recent_field_snapshots_resource,
    read_recent_sessions_resource,
)
from phios.mcp.resources.observatory import (
    read_observatory_atlas_gallery_resource,
    read_observatory_dashboard_resource,
    read_observatory_recent_dossiers_resource,
    read_observatory_recent_field_libraries_resource,
    read_observatory_recent_storyboards_resource,
)
from phios.mcp.schema import with_tool_schema


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gated_denial(decision: CapabilityDecision, code: str) -> dict[str, object]:
    return with_tool_schema(denied_capability_payload(decision=decision, error_code=code))


def run_phi_observatory_summary() -> dict[str, object]:
    """Summarize read-only observatory state for clients."""

    decision = is_capability_allowed(CAP_READ_OBSERVATORY)
    if not decision.allowed:
        return _gated_denial(decision, "OBSERVATORY_SUMMARY_NOT_PERMITTED")

    dashboard = read_observatory_dashboard_resource()
    atlas = read_observatory_atlas_gallery_resource()
    storyboards = read_observatory_recent_storyboards_resource(limit=10)
    dossiers = read_observatory_recent_dossiers_resource(limit=10)
    field_libraries = read_observatory_recent_field_libraries_resource(limit=10)

    return with_tool_schema(
        {
            "ok": True,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "capability_scope": decision.capability_scope,
            "policy_source": decision.policy_source,
            "generated_at": _utc_now_iso(),
            "summary": {
                "dashboard_sessions": dashboard.get("summary", {}).get("session_count", 0),
                "atlas_entries": atlas.get("summary", {}).get("entry_count", 0),
                "recent_storyboards": storyboards.get("count", 0),
                "recent_dossiers": dossiers.get("count", 0),
                "recent_field_libraries": field_libraries.get("count", 0),
            },
            "dashboard": dashboard,
            "atlas_gallery": atlas,
            "recent_storyboards": storyboards,
            "recent_dossiers": dossiers,
            "recent_field_libraries": field_libraries,
        }
    )


def run_phi_recent_activity(adapter: PhiKernelCLIAdapter) -> dict[str, object]:
    """Summarize recent read-safe activity across history/observatory surfaces."""

    decision = is_capability_allowed(CAP_READ_HISTORY)
    if not decision.allowed:
        return _gated_denial(decision, "RECENT_ACTIVITY_NOT_PERMITTED")

    capsules = read_recent_capsules_resource(adapter, limit=10)
    sessions = read_recent_sessions_resource(limit=10)
    field_snapshots = read_recent_field_snapshots_resource(limit=10)
    recent_storyboards = read_observatory_recent_storyboards_resource(limit=5)
    recent_dossiers = read_observatory_recent_dossiers_resource(limit=5)

    return with_tool_schema(
        {
            "ok": True,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "capability_scope": decision.capability_scope,
            "policy_source": decision.policy_source,
            "generated_at": _utc_now_iso(),
            "summary": {
                "capsule_count": capsules.get("count", 0),
                "session_count": sessions.get("count", 0),
                "field_snapshot_count": field_snapshots.get("count", 0),
                "storyboard_count": recent_storyboards.get("count", 0),
                "dossier_count": recent_dossiers.get("count", 0),
            },
            "recent_capsules": capsules,
            "recent_sessions": sessions,
            "recent_field_snapshots": field_snapshots,
            "recent_storyboards": recent_storyboards,
            "recent_dossiers": recent_dossiers,
        }
    )


def run_phi_library_summary() -> dict[str, object]:
    """Summarize library/shelf/catalog-level observatory state from local artifacts."""

    decision = is_capability_allowed(CAP_READ_OBSERVATORY)
    if not decision.allowed:
        return _gated_denial(decision, "LIBRARY_SUMMARY_NOT_PERMITTED")

    dashboard = read_observatory_dashboard_resource()
    field_libraries = read_observatory_recent_field_libraries_resource(limit=20)
    dashboard_payload = dashboard.get("dashboard", {})
    dashboard_dict = dashboard_payload if isinstance(dashboard_payload, dict) else {}

    return with_tool_schema(
        {
            "ok": True,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "capability_scope": decision.capability_scope,
            "policy_source": decision.policy_source,
            "generated_at": _utc_now_iso(),
            "summary": {
                "field_library_count": field_libraries.get("count", 0),
                "recent_shelves_count": len(dashboard_dict.get("recent_shelves", []))
                if isinstance(dashboard_dict.get("recent_shelves"), list)
                else 0,
                "recent_reading_rooms_count": len(dashboard_dict.get("recent_reading_rooms", []))
                if isinstance(dashboard_dict.get("recent_reading_rooms"), list)
                else 0,
                "recent_study_halls_count": len(dashboard_dict.get("recent_study_halls", []))
                if isinstance(dashboard_dict.get("recent_study_halls"), list)
                else 0,
            },
            "field_libraries": field_libraries,
            "library_context": {
                "recent_shelves": dashboard_dict.get("recent_shelves", []),
                "recent_reading_rooms": dashboard_dict.get("recent_reading_rooms", []),
                "recent_study_halls": dashboard_dict.get("recent_study_halls", []),
            },
        }
    )
