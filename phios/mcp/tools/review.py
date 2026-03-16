"""MCP tool for adversarial review coherence gating."""

from __future__ import annotations

from phios.adapters.phik import PhiKernelCLIAdapter
from phios.mcp.schema import with_tool_schema
from phios.services.review_gate import (
    build_review_context,
    evaluate_review_coherence_gate,
    persist_review_outcome,
)


def phi_review_coherence_gate(
    adapter: PhiKernelCLIAdapter,
    *,
    round: int,
    reviewer_grades: list[dict[str, object]],
    reviewer_critiques: list[str],
    pr_number: int | None = None,
    panel_id: str = "default",
    mediator_summary: str | None = None,
    persist: bool = False,
) -> dict[str, object]:
    if round < 1:
        return with_tool_schema({"ok": False, "error_code": "INVALID_ROUND", "reason": "round must be >= 1"})
    if not isinstance(reviewer_grades, list):
        return with_tool_schema({"ok": False, "error_code": "INVALID_GRADES", "reason": "reviewer_grades must be list"})
    if not isinstance(reviewer_critiques, list):
        return with_tool_schema({"ok": False, "error_code": "INVALID_CRITIQUES", "reason": "reviewer_critiques must be list"})

    grades = [g for g in reviewer_grades if isinstance(g, dict)]
    critiques = [str(c) for c in reviewer_critiques if isinstance(c, str)]

    context = build_review_context(
        adapter=adapter,
        round_index=round,
        reviewer_grades=grades,
        reviewer_critiques=critiques,
        panel_id=panel_id,
        pr_number=pr_number,
    )
    result = evaluate_review_coherence_gate(context)
    out: dict[str, object] = {
        "ok": True,
        "panel_id": panel_id,
        "pr_number": pr_number,
        "result": result,
        "grade_summary": context.get("grade_summary", {}),
        "read_only": not persist,
        "experimental": True,
    }
    if persist:
        out["persistence"] = persist_review_outcome(
            panel_id=panel_id,
            pr_number=pr_number,
            gate_result=result,
            reviewer_grades=grades,
            reviewer_critiques=critiques,
            mediator_summary=mediator_summary,
        )
    return with_tool_schema(out)
