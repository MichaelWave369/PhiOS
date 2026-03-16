"""MCP debate coherence-gate tool."""

from __future__ import annotations

from phios.adapters.phik import PhiKernelCLIAdapter
from phios.mcp.schema import with_tool_schema
from phios.services.debate_arena import (
    build_debate_context,
    evaluate_debate_coherence_gate,
    persist_debate_outcome,
)


def phi_debate_coherence_gate(
    adapter: PhiKernelCLIAdapter,
    *,
    session_id: str,
    round: int,
    positions: list[dict[str, object]],
    threshold: float | None = None,
    persist: bool = False,
) -> dict[str, object]:
    if not session_id.strip():
        return with_tool_schema({"ok": False, "error_code": "INVALID_SESSION_ID", "reason": "session_id is required"})
    if round < 1:
        return with_tool_schema({"ok": False, "error_code": "INVALID_ROUND", "reason": "round must be >= 1"})
    if not isinstance(positions, list):
        return with_tool_schema({"ok": False, "error_code": "INVALID_POSITIONS", "reason": "positions must be a list"})

    normalized_positions = [p for p in positions if isinstance(p, dict)]
    context = build_debate_context(
        adapter=adapter,
        session_id=session_id,
        round_index=round,
        positions=normalized_positions,
        threshold=threshold,
    )
    gate = evaluate_debate_coherence_gate(context)
    out: dict[str, object] = {
        "ok": True,
        "session_id": session_id,
        "result": gate,
        "position_summary": context.get("position_summary", {}),
        "read_only": not persist,
        "experimental": True,
    }
    if persist:
        out["persistence"] = persist_debate_outcome(session_id=session_id, gate_result=gate, positions=normalized_positions)
    return with_tool_schema(out)
