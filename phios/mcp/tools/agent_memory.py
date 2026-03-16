"""MCP tools for observatory-backed agent deliberation memory."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.mcp.policy import (
    CAP_AGENT_MEMORY_WRITE,
    denied_capability_payload,
    is_capability_allowed,
)
from phios.mcp.schema import with_tool_schema
from phios.services.agent_memory import store_agent_deliberation


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def phi_store_deliberation(
    *,
    topic: str,
    positions: list[dict[str, object]],
    outcome: str,
    winning_figure: str,
    coherence_trace: list[float],
    tags: list[str] | None = None,
    run_id: str | None = None,
    recommendation: dict[str, object] | None = None,
) -> dict[str, object]:
    """Store a deliberation in local observatory-backed memory."""

    decision = is_capability_allowed(CAP_AGENT_MEMORY_WRITE)
    if not decision.allowed:
        return with_tool_schema(
            denied_capability_payload(decision=decision, error_code="AGENT_MEMORY_WRITE_NOT_PERMITTED")
        )

    result = store_agent_deliberation(
        topic=topic,
        positions=positions,
        outcome=outcome,
        winning_figure=winning_figure,
        coherence_trace=coherence_trace,
        tags=tags or [],
        metadata={
            "run_id": run_id or "",
            "recommendation": recommendation or {},
            "stored_via": "mcp.tool.phi_store_deliberation",
            "generated_at": _utc_now_iso(),
        },
    )
    if not result.get("ok"):
        return with_tool_schema({"ok": False, "error_code": result.get("error_code", "STORE_FAILED"), "reason": result.get("reason", "store failed")})

    return with_tool_schema({"ok": True, **result})
