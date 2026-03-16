"""MCP tools for experimental figure fitness tracking."""

from __future__ import annotations

from phios.mcp.policy import (
    CAP_FIGURE_FITNESS_WRITE,
    denied_capability_payload,
    is_capability_allowed,
)
from phios.mcp.schema import with_tool_schema
from phios.services.figure_fitness import (
    build_figure_fitness_report,
    record_figure_outcome,
    recommend_figure_for_task,
)


def phi_record_figure_outcome(
    *,
    figure: str,
    skills: list[str],
    run_id: str,
    pr_grade: str,
    merge_time_minutes: float,
    redispatch_count: int,
    issue_closed: bool,
    coherence_at_completion: float,
    sector_at_dispatch: str,
    timestamp: str | None = None,
) -> dict[str, object]:
    decision = is_capability_allowed(CAP_FIGURE_FITNESS_WRITE)
    if not decision.allowed:
        return with_tool_schema(
            denied_capability_payload(decision=decision, error_code="FIGURE_FITNESS_WRITE_NOT_PERMITTED")
        )

    result = record_figure_outcome(
        figure=figure,
        skills=skills,
        run_id=run_id,
        pr_grade=pr_grade,
        merge_time_minutes=merge_time_minutes,
        redispatch_count=redispatch_count,
        issue_closed=issue_closed,
        coherence_at_completion=coherence_at_completion,
        sector_at_dispatch=sector_at_dispatch,
        timestamp=timestamp,
    )
    if not result.get("ok"):
        return with_tool_schema({"ok": False, "error_code": result.get("error_code", "STORE_FAILED"), "reason": result.get("reason", "store failed")})
    return with_tool_schema({"ok": True, **result})


def phi_figure_fitness_report(
    *,
    figure: str | None = None,
    sector: str | None = None,
    top: int = 10,
) -> dict[str, object]:
    return with_tool_schema(
        {
            "ok": True,
            "read_only": True,
            "report": build_figure_fitness_report(figure=figure, sector=sector, top=top),
            "experimental": True,
        }
    )


def phi_recommend_figure_for_task(
    *,
    task_key: str,
    sector: str | None = None,
    required_skill: str | None = None,
    min_coherence: float | None = None,
) -> dict[str, object]:
    return with_tool_schema(
        {
            "ok": True,
            "read_only": True,
            "recommendation": recommend_figure_for_task(
                task_key=task_key,
                sector=sector,
                required_skill=required_skill,
                min_coherence=min_coherence,
            ),
            "experimental": True,
        }
    )
