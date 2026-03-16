"""Session/archive/read-safe summary tools for MCP phases."""

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
from phios.mcp.resources.maps import (
    read_capstones_map_resource,
    read_collections_map_resource,
    read_learning_map_resource,
    read_programs_map_resource,
)
from phios.mcp.resources.programs import (
    read_programs_curricula_rollup_resource,
    read_programs_journey_ensembles_rollup_resource,
    read_programs_study_halls_rollup_resource,
    read_programs_syllabi_rollup_resource,
    read_programs_thematic_pathways_rollup_resource,
)
from phios.mcp.resources.sessions import (
    read_sessions_current_resource,
    read_sessions_recent_checkins_resource,
    read_sessions_recent_reports_resource,
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


def run_phi_session_summary(adapter: PhiKernelCLIAdapter) -> dict[str, object]:
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
                "checkin_count": _dict_int(checkins, "count"),
                "report_count": _dict_int(reports, "count"),
                "session_state": str(_as_dict(_as_dict(current).get("summary", {})).get("session_state", "unknown")),
            },
            "current": current,
            "recent_checkins": checkins,
            "recent_reports": reports,
        }
    )


def run_phi_archive_summary(*, preset: str = "overview", limit: int = 10, include_rollups: bool = True) -> dict[str, object]:
    decision = is_capability_allowed(CAP_READ_HISTORY)
    if not decision.allowed:
        return with_tool_schema(denied_capability_payload(decision=decision, error_code="ARCHIVE_SUMMARY_NOT_PERMITTED"))

    safe_limit = max(0, _to_int(limit))
    pathways = read_archive_pathways_index_resource(limit=safe_limit)
    atlas = read_archive_atlas_index_resource(limit=safe_limit)
    curricula = read_archive_curricula_index_resource(limit=safe_limit)
    journeys = read_archive_journey_ensembles_index_resource(limit=safe_limit)
    route_compares = read_archive_route_compares_index_resource(limit=safe_limit)
    longitudinal = read_archive_longitudinal_index_resource()

    summary = {
        "pathway_count": _dict_int(pathways, "count"),
        "atlas_count": _dict_int(atlas, "count"),
        "curricula_count": _dict_int(curricula, "count"),
        "journey_ensemble_count": _dict_int(journeys, "count"),
        "route_compare_count": _dict_int(route_compares, "count"),
        "longitudinal_count": _dict_int(longitudinal, "count"),
    }

    payload: dict[str, object] = {
        "ok": True,
        "allowed": decision.allowed,
        "reason": decision.reason,
        "capability_scope": decision.capability_scope,
        "policy_source": decision.policy_source,
        "generated_at": _utc_now_iso(),
        "preset": preset,
        "limit": safe_limit,
        "summary": summary,
        "pathways": pathways,
        "atlas": atlas,
        "curricula": curricula,
        "journey_ensembles": journeys,
        "route_compares": route_compares,
        "longitudinal": longitudinal,
    }
    if include_rollups:
        payload["rollups"] = {
            "family_counts": {
                "pathways": summary["pathway_count"],
                "atlas": summary["atlas_count"],
                "learning": summary["curricula_count"] + summary["journey_ensemble_count"],
                "comparisons": summary["route_compare_count"],
                "longitudinal": summary["longitudinal_count"],
            },
            "availability": {
                "route_compares_available": summary["route_compare_count"] > 0,
                "longitudinal_available": summary["longitudinal_count"] > 0,
            },
        }
    return with_tool_schema(payload)


def run_phi_collection_summary() -> dict[str, object]:
    decision = is_capability_allowed(CAP_READ_HISTORY)
    if not decision.allowed:
        return with_tool_schema(denied_capability_payload(decision=decision, error_code="COLLECTION_SUMMARY_NOT_PERMITTED"))

    field_libraries = read_field_libraries_rollup_resource()
    shelves = read_shelves_rollup_resource()
    reading_rooms = read_reading_rooms_rollup_resource()
    study_halls = read_study_halls_rollup_resource()
    curricula = read_curricula_rollup_resource()
    journey_ensembles = read_journey_ensembles_rollup_resource()

    total_items = sum(_dict_int(r, "count") for r in (field_libraries, shelves, reading_rooms, study_halls, curricula, journey_ensembles))
    return with_tool_schema(
        {
            "ok": True,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "capability_scope": decision.capability_scope,
            "policy_source": decision.policy_source,
            "generated_at": _utc_now_iso(),
            "summary": {
                "rollup_count": 6,
                "total_collection_items": total_items,
                "learning_family_items": _dict_int(curricula, "count") + _dict_int(journey_ensembles, "count"),
                "library_family_items": _dict_int(field_libraries, "count") + _dict_int(shelves, "count") + _dict_int(reading_rooms, "count") + _dict_int(study_halls, "count"),
            },
            "rollups": {
                "field_libraries": field_libraries,
                "shelves": shelves,
                "reading_rooms": reading_rooms,
                "study_halls": study_halls,
                "curricula": curricula,
                "journey_ensembles": journey_ensembles,
            },
        }
    )


def run_phi_program_summary() -> dict[str, object]:
    decision = is_capability_allowed(CAP_READ_HISTORY)
    if not decision.allowed:
        return with_tool_schema(denied_capability_payload(decision=decision, error_code="PROGRAM_SUMMARY_NOT_PERMITTED"))

    curricula = read_programs_curricula_rollup_resource()
    study_halls = read_programs_study_halls_rollup_resource()
    thematic_pathways = read_programs_thematic_pathways_rollup_resource()
    syllabi = read_programs_syllabi_rollup_resource()
    journeys = read_programs_journey_ensembles_rollup_resource()

    return with_tool_schema(
        {
            "ok": True,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "capability_scope": decision.capability_scope,
            "policy_source": decision.policy_source,
            "generated_at": _utc_now_iso(),
            "summary": {
                "program_rollup_count": 5,
                "curricula_count": _dict_int(curricula, "count"),
                "study_halls_count": _dict_int(study_halls, "count"),
                "thematic_pathways_count": _dict_int(thematic_pathways, "count"),
                "syllabi_count": _dict_int(syllabi, "count"),
                "journey_ensembles_count": _dict_int(journeys, "count"),
            },
            "program_rollups": {
                "curricula": curricula,
                "study_halls": study_halls,
                "thematic_pathways": thematic_pathways,
                "syllabi": syllabi,
                "journey_ensembles": journeys,
            },
        }
    )


def run_phi_capstone_summary() -> dict[str, object]:
    decision = is_capability_allowed(CAP_READ_HISTORY)
    if not decision.allowed:
        return with_tool_schema(denied_capability_payload(decision=decision, error_code="CAPSTONE_SUMMARY_NOT_PERMITTED"))

    syllabi = read_capstones_syllabi_rollup_resource()
    atlas_cohorts = read_capstones_atlas_cohorts_rollup_resource()
    field_libraries_family = read_capstones_field_libraries_rollup_family_resource()
    dossiers_family = read_capstones_dossiers_rollup_family_resource()
    storyboards_family = read_capstones_storyboards_rollup_family_resource()
    total_items = sum(_dict_int(item, "count") for item in (syllabi, atlas_cohorts, field_libraries_family, dossiers_family, storyboards_family))

    return with_tool_schema(
        {
            "ok": True,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "capability_scope": decision.capability_scope,
            "policy_source": decision.policy_source,
            "generated_at": _utc_now_iso(),
            "summary": {
                "capstone_rollup_count": 5,
                "total_capstone_items": total_items,
                "syllabi_count": _dict_int(syllabi, "count"),
                "atlas_cohorts_count": _dict_int(atlas_cohorts, "count"),
                "family_rollup_count": _dict_int(field_libraries_family, "count") + _dict_int(dossiers_family, "count") + _dict_int(storyboards_family, "count"),
            },
            "capstone_rollups": {
                "syllabi": syllabi,
                "atlas_cohorts": atlas_cohorts,
                "field_libraries_family": field_libraries_family,
                "dossiers_family": dossiers_family,
                "storyboards_family": storyboards_family,
            },
        }
    )


def run_phi_curation_summary() -> dict[str, object]:
    decision = is_capability_allowed(CAP_READ_HISTORY)
    if not decision.allowed:
        return with_tool_schema(denied_capability_payload(decision=decision, error_code="CURATION_SUMMARY_NOT_PERMITTED"))

    collection_summary = run_phi_collection_summary()
    program_summary = run_phi_program_summary()
    capstone_summary = run_phi_capstone_summary()
    collection_total = _dict_int(_as_dict(collection_summary).get("summary", {}), "total_collection_items")
    capstone_total = _dict_int(_as_dict(capstone_summary).get("summary", {}), "total_capstone_items")
    program_total = 0
    if isinstance(program_summary, dict):
        summary_obj = program_summary.get("summary", {})
        if isinstance(summary_obj, dict):
            program_total = sum(_dict_int(summary_obj, k) for k in ("curricula_count", "study_halls_count", "thematic_pathways_count", "syllabi_count", "journey_ensembles_count"))

    return with_tool_schema(
        {
            "ok": True,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "capability_scope": decision.capability_scope,
            "policy_source": decision.policy_source,
            "generated_at": _utc_now_iso(),
            "summary": {
                "collection_total": collection_total,
                "program_total": program_total,
                "capstone_total": capstone_total,
                "combined_total": collection_total + program_total + capstone_total,
            },
            "collection_summary": collection_summary,
            "program_summary": program_summary,
            "capstone_summary": capstone_summary,
        }
    )


def run_phi_catalog_summary() -> dict[str, object]:
    decision = is_capability_allowed(CAP_READ_HISTORY)
    if not decision.allowed:
        return with_tool_schema(denied_capability_payload(decision=decision, error_code="CATALOG_SUMMARY_NOT_PERMITTED"))

    learning = read_catalog_learning_resource()
    capstones = read_catalog_capstones_resource()
    programs = read_catalog_programs_resource()
    collections = read_catalog_collections_resource()
    total = sum(_dict_int(item, "count") for item in (learning, capstones, programs, collections))

    return with_tool_schema(
        {
            "ok": True,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "capability_scope": decision.capability_scope,
            "policy_source": decision.policy_source,
            "generated_at": _utc_now_iso(),
            "summary": {
                "catalog_count": 4,
                "total_items": total,
                "learning_count": _dict_int(learning, "count"),
                "capstones_count": _dict_int(capstones, "count"),
                "programs_count": _dict_int(programs, "count"),
                "collections_count": _dict_int(collections, "count"),
            },
            "catalogs": {
                "learning": learning,
                "capstones": capstones,
                "programs": programs,
                "collections": collections,
            },
        }
    )


def run_phi_learning_map_summary(*, include_map_counts: bool = True) -> dict[str, object]:
    decision = is_capability_allowed(CAP_READ_HISTORY)
    if not decision.allowed:
        return with_tool_schema(denied_capability_payload(decision=decision, error_code="LEARNING_MAP_SUMMARY_NOT_PERMITTED"))

    learning_map = read_learning_map_resource()
    capstones_map = read_capstones_map_resource()
    programs_map = read_programs_map_resource()
    collections_map = read_collections_map_resource()

    payload: dict[str, object] = {
        "ok": True,
        "allowed": decision.allowed,
        "reason": decision.reason,
        "capability_scope": decision.capability_scope,
        "policy_source": decision.policy_source,
        "generated_at": _utc_now_iso(),
        "maps": {
            "learning": learning_map,
            "capstones": capstones_map,
            "programs": programs_map,
            "collections": collections_map,
        },
    }
    if include_map_counts:
        payload["summary"] = {
            "map_count": 4,
            "learning_count": _dict_int(learning_map, "count"),
            "capstones_count": _dict_int(capstones_map, "count"),
            "programs_count": _dict_int(programs_map, "count"),
            "collections_count": _dict_int(collections_map, "count"),
            "combined_count": _dict_int(learning_map, "count")
            + _dict_int(capstones_map, "count")
            + _dict_int(programs_map, "count")
            + _dict_int(collections_map, "count"),
        }
    return with_tool_schema(payload)
