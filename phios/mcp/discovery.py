"""Discovery payload helpers for MCP clients."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.mcp.policy import CAP_PULSE_ONCE, evaluate_pulse_policy, resolve_mcp_capabilities
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


def build_mcp_discovery_payload(registry: object) -> dict[str, object]:
    """Build stable discovery payload from registry + policy state."""

    allowed_caps, policy_source = resolve_mcp_capabilities()
    pulse = evaluate_pulse_policy()
    resource_list = list_mcp_resources(registry)
    tool_list = list_mcp_tools(registry)
    prompt_list = list_mcp_prompts(registry)

    return {
        "schema_version": MCP_SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "policy_source": policy_source,
        "capabilities": {
            "allowed": sorted(allowed_caps),
            "denied": sorted([
                "read_state",
                "read_history",
                "read_observatory",
                "prompt_guidance",
                CAP_PULSE_ONCE,
            ] if not allowed_caps else [
                cap for cap in [
                    "read_state",
                    "read_history",
                    "read_observatory",
                    "prompt_guidance",
                    CAP_PULSE_ONCE,
                ] if cap not in allowed_caps
            ]),
            "pulse": {
                "enabled": pulse.allowed,
                "reason": pulse.reason,
                "policy_source": pulse.policy_source,
            },
        },
        "resources": resource_list,
        "tools": tool_list,
        "prompts": prompt_list,
        "summary": {
            "resource_count": len(resource_list),
            "tool_count": len(tool_list),
            "prompt_count": len(prompt_list),
        },
    }
