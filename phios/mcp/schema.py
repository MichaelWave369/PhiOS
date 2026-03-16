"""Schema/version helpers for PhiOS MCP payload contracts."""

from __future__ import annotations

from typing import Mapping

MCP_SCHEMA_VERSION = "2.0"
RESOURCE_VERSION = "2.0"
TOOL_VERSION = "2.0"
PROMPT_VERSION = "2.0"


def with_resource_schema(payload: Mapping[str, object]) -> dict[str, object]:
    """Attach stable resource schema markers without removing existing fields."""

    out = dict(payload)
    out.setdefault("schema_version", MCP_SCHEMA_VERSION)
    out.setdefault("resource_version", RESOURCE_VERSION)
    return out


def with_tool_schema(payload: Mapping[str, object]) -> dict[str, object]:
    """Attach stable tool schema markers without removing existing fields."""

    out = dict(payload)
    out.setdefault("schema_version", MCP_SCHEMA_VERSION)
    out.setdefault("tool_version", TOOL_VERSION)
    return out
