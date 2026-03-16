"""Read-only MCP resources for dispatch-graph optimization output."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.mcp.schema import with_resource_schema
from phios.services.dispatch_graph import read_last_dispatch_graph_plan


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_dispatch_graph_last_resource() -> dict[str, object]:
    payload = read_last_dispatch_graph_plan()
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "read_only": True,
            "resource_kind": "dispatch_graph_last",
            **payload,
        }
    )
