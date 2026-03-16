"""Read-only MCP resources for agent dispatch runs/events."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.mcp.schema import with_resource_schema
from phios.services.agent_dispatch import (
    get_agent_run_status,
    list_agent_runs,
    stream_agent_run_events,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_agents_active_resource() -> dict[str, object]:
    runs = list_agent_runs(active_only=True)
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "read_only": True,
            "resource_kind": "agents_active",
            "runs": runs,
            "count": len(runs),
        }
    )


def read_agent_run_resource(run_id: str) -> dict[str, object]:
    run = get_agent_run_status(run_id)
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "read_only": True,
            "resource_kind": "agent_run",
            "run_id": run_id,
            "run": run if run.get("ok") is not False else None,
            "found": run.get("ok") is not False,
        }
    )


def read_agent_run_events_resource(run_id: str) -> dict[str, object]:
    events = stream_agent_run_events(run_id)
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "read_only": True,
            "resource_kind": "agent_run_events",
            "run_id": run_id,
            "events": events,
            "count": len(events),
        }
    )
