"""MCP discovery resource."""

from __future__ import annotations

from phios.mcp.discovery import build_mcp_discovery_payload
from phios.mcp.schema import with_resource_schema


def read_mcp_discovery_resource(registry: object) -> dict[str, object]:
    """Return client-facing discovery data for resources/tools/prompts/capabilities."""

    return with_resource_schema(build_mcp_discovery_payload(registry))
