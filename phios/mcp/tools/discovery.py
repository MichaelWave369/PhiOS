"""MCP discovery tool."""

from __future__ import annotations

from phios.mcp.discovery import build_mcp_discovery_payload
from phios.mcp.schema import with_tool_schema


def run_phi_discovery(registry: object) -> dict[str, object]:
    """Return discovery payload through a tool surface."""

    return with_tool_schema(build_mcp_discovery_payload(registry))
