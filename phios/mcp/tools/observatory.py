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
from phios.mcp.resources.maps import (
    read_capstones_map_resource,
    read_collections_map_resource,
    read_learning_map_resource,
    read_programs_map_resource,
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


def _to_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, (str, bytes, bytearray)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return default


def _as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _dict_int(mapping: object, key: str, default: int = 0) -> int:
    return _to_int(_as_dict(mapping).get(key, default), default)


def _dict_list(mapping: object, key: str) -> list[object]:
    value = _as_dict(mapping).get(key, [])
    return value if isinstance(value, list) else []


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
                "dashboard_sessions": _dict_int(_as_dict(dashboard).get("summary", {}), "session_count"),
                "atlas_entries": _dict_int(_as_dict(atlas).get("summary", {}), "entry_count"),
                "recent_storyboards": _dict_int(storyboards, "count"),
                "recent_dossiers": _dict_int(dossiers, "count"),
                "recent_field_libraries": _dict_int(field_libraries, "count"),
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
                "capsule_count": _dict_int(capsules, "count"),
                "session_count": _dict_int(sessions, "count"),
                "field_snapshot_count": _dict_int(field_snapshots, "count"),
                "storyboard_count": _dict_int(recent_storyboards, "count"),
                "dossier_count": _dict_int(recent_dossiers, "count"),
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
    dashboard_payload = _as_dict(dashboard).get("dashboard", {})
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
                "field_library_count": _dict_int(field_libraries, "count"),
                "recent_shelves_count": len(_dict_list(dashboard_dict, "recent_shelves")),
                "recent_reading_rooms_count": len(_dict_list(dashboard_dict, "recent_reading_rooms")),
                "recent_study_halls_count": len(_dict_list(dashboard_dict, "recent_study_halls")),
            },
            "field_libraries": field_libraries,
            "library_context": {
                "recent_shelves": _dict_list(dashboard_dict, "recent_shelves"),
                "recent_reading_rooms": _dict_list(dashboard_dict, "recent_reading_rooms"),
                "recent_study_halls": _dict_list(dashboard_dict, "recent_study_halls"),
            },
        }
    )



def run_phi_storyboard_summary() -> dict[str, object]:
    """Return a bounded summary of recent storyboard artifacts."""

    decision = is_capability_allowed(CAP_READ_OBSERVATORY)
    if not decision.allowed:
        return _gated_denial(decision, "STORYBOARD_SUMMARY_NOT_PERMITTED")

    storyboards = read_observatory_recent_storyboards_resource(limit=20)
    rows = _as_dict(storyboards).get("storyboards", [])
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
                "storyboard_count": _dict_int(storyboards, "count"),
                "non_empty_sections": sum(1 for row in safe_rows if isinstance(row, dict) and _to_int(row.get("section_count", 0)) > 0),
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
    atlas_payload = _as_dict(atlas_dict.get("atlas_gallery", {}))

    return with_tool_schema(
        {
            "ok": True,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "capability_scope": decision.capability_scope,
            "policy_source": decision.policy_source,
            "generated_at": _utc_now_iso(),
            "summary": {
                "entry_count": _dict_int(atlas_dict.get("summary", {}), "entry_count"),
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
    learning_map: str | None = None,
    cross_catalog: bool = False,
    include_map_counts: bool = False,
) -> dict[str, object]:
    """Browse richer observatory index surfaces in one bounded response."""

    decision = is_capability_allowed(CAP_READ_OBSERVATORY)
    if not decision.allowed:
        return _gated_denial(decision, "BROWSE_OBSERVATORY_NOT_PERMITTED")

    safe_limit = max(0, _to_int(limit))
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

    map_payload: dict[str, object] = {}
    if learning_map:
        map_name = learning_map.strip().lower()
        if map_name == "learning":
            map_payload = {"learning": read_learning_map_resource()}
        elif map_name == "capstones":
            map_payload = {"capstones": read_capstones_map_resource()}
        elif map_name == "programs":
            map_payload = {"programs": read_programs_map_resource()}
        elif map_name == "collections":
            map_payload = {"collections": read_collections_map_resource()}

    if cross_catalog and not map_payload:
        map_payload = {
            "learning": read_learning_map_resource(),
            "capstones": read_capstones_map_resource(),
            "programs": read_programs_map_resource(),
            "collections": read_collections_map_resource(),
        }

    summary = {
        "storyboards": _dict_int(storyboards, "count"),
        "dossiers": _dict_int(dossiers, "count"),
        "field_libraries": _dict_int(libraries, "count"),
        "shelves": _dict_int(shelves, "count"),
        "reading_rooms": _dict_int(reading_rooms, "count"),
        "study_halls": _dict_int(study_halls, "count"),
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
        "learning_map": learning_map or "",
        "cross_catalog": bool(cross_catalog),
        "limit": safe_limit,
        "views": views,
    }
    if include_counts:
        payload["summary"] = summary
    if catalog_payload:
        payload["catalogs"] = catalog_payload
    if include_catalog_counts and catalog_payload:
        payload["catalog_counts"] = {k: _dict_int(v, "count") for k, v in catalog_payload.items()}
    if map_payload:
        payload["maps"] = map_payload
    if include_map_counts and map_payload:
        payload["map_counts"] = {k: _dict_int(v, "count") for k, v in map_payload.items()}
    if include_rollups:
        payload["rollups"] = {
            "family_counts": {
                "narrative": summary["storyboards"] + summary["dossiers"],
                "library": summary["field_libraries"] + summary["shelves"] + summary["reading_rooms"],
                "learning": summary["study_halls"],
            }
        }

    return with_tool_schema(payload)

