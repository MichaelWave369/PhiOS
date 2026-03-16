"""Discovery payload helpers for MCP clients."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.mcp.browse_presets import BROWSE_PRESETS, list_mcp_browse_presets
from phios.mcp.policy import (
    ALL_CAPABILITIES,
    evaluate_pulse_policy,
    list_mcp_profiles,
    resolve_mcp_capabilities,
    resolve_mcp_profile,
)
from phios.mcp.schema import MCP_SCHEMA_VERSION


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_mcp_resources(registry: object) -> list[str]:
    return [str(item) for item in getattr(registry, "resources", ())]


def list_mcp_tools(registry: object) -> list[str]:
    return [str(item) for item in getattr(registry, "tools", ())]


def list_mcp_prompts(registry: object) -> list[str]:
    return [str(item) for item in getattr(registry, "prompts", ())]


def list_mcp_session_resources(registry: object) -> list[str]:
    return [uri for uri in list_mcp_resources(registry) if uri.startswith("phios://sessions/")]


def list_mcp_archive_resources(registry: object) -> list[str]:
    return [uri for uri in list_mcp_resources(registry) if uri.startswith("phios://archive/")]


def list_mcp_observatory_resources(registry: object) -> list[str]:
    return [uri for uri in list_mcp_resources(registry) if uri.startswith("phios://observatory/")]


def list_mcp_browse_resources(registry: object) -> list[str]:
    return [uri for uri in list_mcp_resources(registry) if uri.startswith("phios://browse/")]


def list_mcp_collection_rollups(registry: object) -> list[str]:
    return [uri for uri in list_mcp_resources(registry) if uri.startswith("phios://collections/")]


def list_mcp_program_rollups(registry: object) -> list[str]:
    return [uri for uri in list_mcp_resources(registry) if uri.startswith("phios://programs/")]


def list_mcp_capstone_rollups(registry: object) -> list[str]:
    return [uri for uri in list_mcp_resources(registry) if uri.startswith("phios://capstones/")]


def list_mcp_catalog_resources(registry: object) -> list[str]:
    return [uri for uri in list_mcp_resources(registry) if uri.startswith("phios://catalogs/")]


def list_mcp_browse_families(registry: object) -> list[str]:
    family_names = {"observatory_families", "learning_families", "collection_families", "capstone_families", "archive_families"}
    return [uri for uri in list_mcp_browse_resources(registry) if uri.split("/")[-1] in family_names]


def build_mcp_discovery_payload(registry: object) -> dict[str, object]:
    """Build stable discovery payload from registry + policy state."""

    allowed_caps, policy_source = resolve_mcp_capabilities()
    pulse = evaluate_pulse_policy()
    profile = resolve_mcp_profile()
    resource_list = list_mcp_resources(registry)
    tool_list = list_mcp_tools(registry)
    prompt_list = list_mcp_prompts(registry)
    session_resources = list_mcp_session_resources(registry)
    archive_resources = list_mcp_archive_resources(registry)
    observatory_resources = list_mcp_observatory_resources(registry)
    browse_resources = list_mcp_browse_resources(registry)
    collection_rollups = list_mcp_collection_rollups(registry)
    program_rollups = list_mcp_program_rollups(registry)
    capstone_rollups = list_mcp_capstone_rollups(registry)
    catalog_resources = list_mcp_catalog_resources(registry)
    browse_families = list_mcp_browse_families(registry)

    tool_groups = {
        "core": [t for t in tool_list if t in {"phi_status", "phi_ask", "phi_pulse_once", "phi_discovery"}],
        "observatory": [t for t in tool_list if "observatory" in t or t in {"phi_storyboard_summary", "phi_atlas_summary", "phi_library_summary"}],
        "session_archive": [t for t in tool_list if t in {"phi_session_summary", "phi_archive_summary", "phi_collection_summary", "phi_program_summary", "phi_curation_summary", "phi_capstone_summary", "phi_catalog_summary"}],
    }

    archive_rollups = {
        "archive_resource_count": len(archive_resources),
        "archive_tool_count": len(tool_groups["session_archive"]),
        "archive_available": len(archive_resources) > 0,
    }

    return {
        "schema_version": MCP_SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "profile": profile or "none",
        "supported_profiles": list_mcp_profiles(),
        "policy_source": policy_source,
        "capabilities": {
            "allowed": sorted(allowed_caps),
            "denied": sorted([cap for cap in ALL_CAPABILITIES if cap not in allowed_caps]),
            "pulse": {
                "enabled": pulse.allowed,
                "reason": pulse.reason,
                "policy_source": pulse.policy_source,
            },
        },
        "resolved_capabilities": sorted(allowed_caps),
        "resources": resource_list,
        "session_resources": session_resources,
        "archive_resources": archive_resources,
        "observatory_resources": observatory_resources,
        "browse_resources": browse_resources,
        "collection_rollups": collection_rollups,
        "program_rollups": program_rollups,
        "capstone_rollups": capstone_rollups,
        "catalog_resources": catalog_resources,
        "resource_groups": {
            "sessions": session_resources,
            "archive": archive_resources,
            "observatory": observatory_resources,
            "browse": browse_resources,
        },
        "tools": tool_list,
        "tool_groups": tool_groups,
        "prompts": prompt_list,
        "browse_presets": {
            "supported": list_mcp_browse_presets(),
            "definitions": BROWSE_PRESETS,
        },
        "learning_presets": [p for p in list_mcp_browse_presets() if p in {"learning", "learning_paths", "programs", "collections", "curricula", "cohorts", "learning_tracks", "capstones", "collections_family", "learning_programs", "comparative_learning", "study_tracks", "observatory_families", "learning_families", "collection_families", "capstone_families", "archive_families"}],
        "collection_groups": {
            "libraries": [uri for uri in collection_rollups if any(k in uri for k in ("field_libraries", "shelves", "reading_rooms", "study_halls"))],
            "learning": [uri for uri in collection_rollups if any(k in uri for k in ("curricula", "journey_ensembles"))],
        },
        "browse_surface_counts": {
            "browse_resources": len(browse_resources),
            "collection_rollups": len(collection_rollups),
            "program_rollups": len(program_rollups),
            "capstone_rollups": len(capstone_rollups),
            "catalog_resources": len(catalog_resources),
            "learning_presets": len([p for p in list_mcp_browse_presets() if p in {"learning", "learning_paths", "programs", "collections", "curricula", "cohorts", "learning_tracks", "capstones", "collections_family", "learning_programs", "comparative_learning", "study_tracks", "observatory_families", "learning_families", "collection_families", "capstone_families", "archive_families"}]),
        },
        "learning_groups": {
            "programs": program_rollups,
            "collections": collection_rollups,
            "capstones": capstone_rollups,
            "catalogs": catalog_resources,
            "learning_browse_resources": [uri for uri in browse_resources if any(key in uri for key in ("learning", "program", "curricula", "cohorts", "tracks", "capstone", "family"))],
        },
        "observatory_family_groups": {
            "browse_families": browse_families,
            "observatory_resources": observatory_resources,
        },
        "browse_family_groups": {
            "family_resources": browse_families,
            "family_count": len(browse_families),
        },
        "collection_family_rollups": [uri for uri in capstone_rollups if "rollup_family" in uri],
        "learning_browse_families": [p for p in list_mcp_browse_presets() if p in {"learning", "learning_paths", "learning_tracks", "learning_programs", "capstones", "collections_family", "comparative_learning", "study_tracks"}],
        "program_surface_counts": {
            "program_rollups": len(program_rollups),
            "capstone_rollups": len(capstone_rollups),
            "catalog_resources": len(catalog_resources),
            "program_tools": len([t for t in tool_list if t in {"phi_program_summary", "phi_curation_summary", "phi_capstone_summary"}]),
        },
        "capstone_surface_counts": {
            "capstone_rollups": len(capstone_rollups),
            "catalog_resources": len(catalog_resources),
            "collection_family_rollups": len([uri for uri in capstone_rollups if "rollup_family" in uri]),
            "capstone_tools": len([t for t in tool_list if t in {"phi_capstone_summary", "phi_curation_summary"}]),
        },
        "catalog_surface_counts": {
            "catalog_resources": len(catalog_resources),
            "browse_families": len(browse_families),
            "catalog_tools": len([t for t in tool_list if t in {"phi_catalog_summary"}]),
        },
        "archive_rollups": archive_rollups,
        "resource_counts": len(resource_list),
        "tool_counts": len(tool_list),
        "prompt_counts": len(prompt_list),
        "summary": {
            "resource_count": len(resource_list),
            "tool_count": len(tool_list),
            "prompt_count": len(prompt_list),
        },
    }
