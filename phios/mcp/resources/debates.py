"""Read-only MCP resources for debate arena observability."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.mcp.schema import with_resource_schema
from phios.services.debate_arena import get_debate_session_resource, list_recent_debates


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_debates_recent_resource(limit: int = 10) -> dict[str, object]:
    payload = list_recent_debates(limit=limit)
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "read_only": True,
            "resource_kind": "debates_recent",
            **payload,
        }
    )


def read_debate_session_resource(session_id: str) -> dict[str, object]:
    payload = get_debate_session_resource(session_id)
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "read_only": True,
            "resource_kind": "debate_session",
            **payload,
        }
    )
