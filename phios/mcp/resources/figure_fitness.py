"""Read-only MCP resources for figure fitness landscape."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.mcp.schema import with_resource_schema
from phios.services.figure_fitness import (
    build_figure_fitness_report,
    recommend_figure_for_task,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_figures_fitness_resource(top: int = 10, sector: str | None = None) -> dict[str, object]:
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "read_only": True,
            "resource_kind": "figures_fitness",
            "report": build_figure_fitness_report(sector=sector, top=top),
        }
    )


def read_figure_fitness_detail_resource(figure: str, top: int = 20) -> dict[str, object]:
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "read_only": True,
            "resource_kind": "figure_fitness_detail",
            "report": build_figure_fitness_report(figure=figure, top=top),
        }
    )


def read_figure_recommendation_resource(task_key: str, sector: str | None = None) -> dict[str, object]:
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "read_only": True,
            "resource_kind": "figure_recommendation",
            "recommendation": recommend_figure_for_task(task_key=task_key, sector=sector),
        }
    )
