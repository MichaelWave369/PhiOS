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

    tool_groups = {
        "core": [t for t in tool_list if t in {"phi_status", "phi_ask", "phi_pulse_once", "phi_discovery"}],
        "observatory": [t for t in tool_list if "observatory" in t or t in {"phi_storyboard_summary", "phi_atlas_summary", "phi_library_summary"}],
        "session_archive": [t for t in tool_list if t in {"phi_session_summary", "phi_archive_summary"}],
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
