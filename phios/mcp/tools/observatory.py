"""Read-safe observatory summary MCP tools (Phase 4/5/6/7/8)."""

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
from phios.mcp.resources.catalogs import (
    read_catalog_capstones_resource,
    read_catalog_collections_resource,
    read_catalog_learning_resource,
    read_catalog_programs_resource,
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
    read_observatory_storyboards_index_resource,
    read_observatory_dossiers_index_resource,
    read_observatory_field_libraries_index_resource,
    read_observatory_shelves_index_resource,
    read_observatory_reading_rooms_index_resource,
    read_observatory_study_halls_index_resource,
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
                "dashboard_sessions": dashboard.get("summary", {}).get("session_count", 0) if isinstance(dashboard, dict) else 0,
                "atlas_entries": atlas.get("summary", {}).get("entry_count", 0) if isinstance(atlas, dict) else 0,
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



def run_phi_storyboard_summary() -> dict[str, object]:
    """Return a bounded summary of recent storyboard artifacts."""

    decision = is_capability_allowed(CAP_READ_OBSERVATORY)
    if not decision.allowed:
        return _gated_denial(decision, "STORYBOARD_SUMMARY_NOT_PERMITTED")

    storyboards = read_observatory_recent_storyboards_resource(limit=20)
    rows = storyboards.get("storyboards", []) if isinstance(storyboards, dict) else []
    safe_rows = rows if isinstance(rows, list) else []

    return with_tool_schema(
        {
            "ok": True,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "capability_scope": decision.capability_scope,
            "policy_source": decision.policy_source,
            "generated_at": _utc_now_iso(),
            "summary": {
                "storyboard_count": storyboards.get("count", 0) if isinstance(storyboards, dict) else 0,
                "non_empty_sections": sum(1 for row in safe_rows if isinstance(row, dict) and int(row.get("section_count", 0) or 0) > 0),
            },
            "recent_storyboards": storyboards,
        }
    )


def run_phi_atlas_summary() -> dict[str, object]:
    """Return a bounded summary of atlas gallery state."""

    decision = is_capability_allowed(CAP_READ_OBSERVATORY)
    if not decision.allowed:
        return _gated_denial(decision, "ATLAS_SUMMARY_NOT_PERMITTED")

    atlas = read_observatory_atlas_gallery_resource()
    atlas_dict = atlas if isinstance(atlas, dict) else {}
    atlas_payload = atlas_dict.get("atlas_gallery", {}) if isinstance(atlas_dict.get("atlas_gallery", {}), dict) else {}

    return with_tool_schema(
        {
            "ok": True,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "capability_scope": decision.capability_scope,
            "policy_source": decision.policy_source,
            "generated_at": _utc_now_iso(),
            "summary": {
                "entry_count": atlas_dict.get("summary", {}).get("entry_count", 0) if isinstance(atlas_dict.get("summary", {}), dict) else 0,
                "gallery_version": atlas_payload.get("gallery_version", ""),
            },
            "atlas_gallery": atlas,
        }
    )



def run_phi_browse_observatory(
    *,
    preset: str = "overview",
    artifact_family: str | None = None,
    limit: int = 20,
    include_counts: bool = True,
    include_rollups: bool = True,
    family_group: str | None = None,
    catalog: str | None = None,
    include_catalog_counts: bool = False,
) -> dict[str, object]:
    """Browse richer observatory index surfaces in one bounded response."""

    decision = is_capability_allowed(CAP_READ_OBSERVATORY)
    if not decision.allowed:
        return _gated_denial(decision, "BROWSE_OBSERVATORY_NOT_PERMITTED")

    safe_limit = max(0, int(limit))
    storyboards = read_observatory_storyboards_index_resource(limit=safe_limit)
    dossiers = read_observatory_dossiers_index_resource(limit=safe_limit)
    libraries = read_observatory_field_libraries_index_resource(limit=safe_limit)
    shelves = read_observatory_shelves_index_resource(limit=safe_limit)
    reading_rooms = read_observatory_reading_rooms_index_resource(limit=safe_limit)
    study_halls = read_observatory_study_halls_index_resource(limit=safe_limit)

    views: dict[str, object] = {
        "storyboards_index": storyboards,
        "dossiers_index": dossiers,
        "field_libraries_index": libraries,
        "shelves_index": shelves,
        "reading_rooms_index": reading_rooms,
        "study_halls_index": study_halls,
    }

    preset_norm = (preset or "").strip().lower() or "overview"
    if preset_norm == "libraries":
        views = {
            "field_libraries_index": libraries,
            "shelves_index": shelves,
            "reading_rooms_index": reading_rooms,
        }
    elif preset_norm == "learning":
        views = {
            "storyboards_index": storyboards,
            "study_halls_index": study_halls,
            "dossiers_index": dossiers,
        }
    elif preset_norm == "recent":
        views = {
            "storyboards_index": storyboards,
            "dossiers_index": dossiers,
        }

    if artifact_family:
        fam = artifact_family.strip().lower()
        views = {k: v for k, v in views.items() if fam in k}

    if family_group:
        group = family_group.strip().lower()
        group_map = {
            "observatory": {"storyboards_index", "dossiers_index"},
            "libraries": {"field_libraries_index", "shelves_index", "reading_rooms_index"},
            "learning": {"storyboards_index", "study_halls_index"},
        }
        allowed = group_map.get(group, set())
        if allowed:
            views = {k: v for k, v in views.items() if k in allowed}

    catalog_payload: dict[str, object] = {}
    if catalog:
        cat = catalog.strip().lower()
        if cat == "learning":
            catalog_payload = {"learning": read_catalog_learning_resource()}
        elif cat == "capstones":
            catalog_payload = {"capstones": read_catalog_capstones_resource()}
        elif cat == "programs":
            catalog_payload = {"programs": read_catalog_programs_resource()}
        elif cat == "collections":
            catalog_payload = {"collections": read_catalog_collections_resource()}

    summary = {
        "storyboards": storyboards.get("count", 0) if isinstance(storyboards, dict) else 0,
        "dossiers": dossiers.get("count", 0) if isinstance(dossiers, dict) else 0,
        "field_libraries": libraries.get("count", 0) if isinstance(libraries, dict) else 0,
        "shelves": shelves.get("count", 0) if isinstance(shelves, dict) else 0,
        "reading_rooms": reading_rooms.get("count", 0) if isinstance(reading_rooms, dict) else 0,
        "study_halls": study_halls.get("count", 0) if isinstance(study_halls, dict) else 0,
    }

    payload: dict[str, object] = {
        "ok": True,
        "allowed": decision.allowed,
        "reason": decision.reason,
        "capability_scope": decision.capability_scope,
        "policy_source": decision.policy_source,
        "generated_at": _utc_now_iso(),
        "preset": preset_norm,
        "artifact_family": artifact_family or "",
        "family_group": family_group or "",
        "catalog": catalog or "",
        "limit": safe_limit,
        "views": views,
    }
    if include_counts:
        payload["summary"] = summary
    if catalog_payload:
        payload["catalogs"] = catalog_payload
    if include_catalog_counts and catalog_payload:
        payload["catalog_counts"] = {k: int(v.get("count", 0)) for k, v in catalog_payload.items() if isinstance(v, dict)}
    if include_rollups:
        payload["rollups"] = {
            "family_counts": {
                "narrative": summary["storyboards"] + summary["dossiers"],
                "library": summary["field_libraries"] + summary["shelves"] + summary["reading_rooms"],
                "learning": summary["study_halls"],
            }
        }

    return with_tool_schema(payload)

