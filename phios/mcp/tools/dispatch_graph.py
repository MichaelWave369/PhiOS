"""MCP tool for deterministic dispatch-graph optimization."""

from __future__ import annotations

from phios.mcp.schema import with_tool_schema
from phios.services.dispatch_graph import optimize_dispatch_graph, summarize_dispatch_graph_plan


def phi_optimize_dispatch_graph(*, graph: dict[str, object]) -> dict[str, object]:
    if not isinstance(graph, dict):
        return with_tool_schema(
            {
                "ok": False,
                "error_code": "INVALID_GRAPH_PAYLOAD",
                "reason": "graph must be a JSON object with a 'nodes' list.",
            }
        )

    optimized = optimize_dispatch_graph(graph)
    return with_tool_schema(
        {
            "ok": bool(optimized.get("ok", False)),
            "read_only": True,
            "plan": optimized,
            "summary": summarize_dispatch_graph_plan(optimized),
            "experimental": True,
        }
    )
