"""Discovery payload helpers for MCP clients."""

from __future__ import annotations

from datetime import datetime, timezone

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
    resources = getattr(registry, "resources", ())
    return [str(item) for item in resources]


def list_mcp_tools(registry: object) -> list[str]:
    tools = getattr(registry, "tools", ())
    return [str(item) for item in tools]


def list_mcp_prompts(registry: object) -> list[str]:
    prompts = getattr(registry, "prompts", ())
    return [str(item) for item in prompts]


def list_mcp_session_resources(registry: object) -> list[str]:
    return [uri for uri in list_mcp_resources(registry) if uri.startswith("phios://sessions/")]


def list_mcp_archive_resources(registry: object) -> list[str]:
    return [uri for uri in list_mcp_resources(registry) if uri.startswith("phios://archive/")]


def build_mcp_discovery_payload(registry: object) -> dict[str, object]:
    """Build stable discovery payload from registry + policy state."""

    allowed_caps, policy_source = resolve_mcp_capabilities()
    pulse = evaluate_pulse_policy()
    profile = resolve_mcp_profile()
    resource_list = list_mcp_resources(registry)
    tool_list = list_mcp_tools(registry)
    prompt_list = list_mcp_prompts(registry)

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
        "session_resources": list_mcp_session_resources(registry),
        "archive_resources": list_mcp_archive_resources(registry),
        "tools": tool_list,
        "prompts": prompt_list,
        "resource_counts": len(resource_list),
        "tool_counts": len(tool_list),
        "prompt_counts": len(prompt_list),
        "summary": {
            "resource_count": len(resource_list),
            "tool_count": len(tool_list),
            "prompt_count": len(prompt_list),
        },
    }
