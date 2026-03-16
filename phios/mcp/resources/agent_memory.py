"""Read-only MCP resources for observatory-backed agent memory."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.mcp.schema import with_resource_schema
from phios.services.agent_memory import (
    get_agent_memory,
    get_agent_memory_coherence,
    list_recent_agent_deliberations,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_agent_memory_topic_resource(topic: str) -> dict[str, object]:
    payload = get_agent_memory(topic)
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "read_only": True,
            "resource_kind": "agent_memory_topic",
            **payload,
        }
    )


def read_agent_memory_coherence_resource(topic: str) -> dict[str, object]:
    payload = get_agent_memory_coherence(topic)
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "read_only": True,
            "resource_kind": "agent_memory_coherence",
            **payload,
        }
    )


def read_recent_agent_deliberations_resource(limit: int = 10) -> dict[str, object]:
    payload = list_recent_agent_deliberations(limit=limit)
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "read_only": True,
            "resource_kind": "agent_deliberations_recent",
            **payload,
        }
    )
