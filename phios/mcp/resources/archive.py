"""Archive browsing MCP resources (Phase 7, read-only)."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.mcp.schema import with_resource_schema
from phios.services.visualizer import (
    build_visual_bloom_dashboard_model,
    build_visual_bloom_longitudinal_summary,
    list_visual_bloom_atlas_cohorts,
    list_visual_bloom_curricula,
    list_visual_bloom_journey_ensembles,
    list_visual_bloom_pathways,
)

_MAX_RECENT = 20


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _index_payload(rows: list[dict[str, object]], *, limit: int, source: str) -> dict[str, object]:
    capped = rows[: max(0, int(limit))]
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "count": len(capped),
            "limit": max(0, int(limit)),
            "index": capped,
            "source": source,
            "read_only": True,
        }
    )


def read_archive_pathways_index_resource(*, limit: int = _MAX_RECENT) -> dict[str, object]:
    return _index_payload(
        [r for r in list_visual_bloom_pathways() if isinstance(r, dict)],
        limit=limit,
        source="phios.services.visualizer.list_visual_bloom_pathways",
    )


def read_archive_atlas_index_resource(*, limit: int = _MAX_RECENT) -> dict[str, object]:
    return _index_payload(
        [r for r in list_visual_bloom_atlas_cohorts() if isinstance(r, dict)],
        limit=limit,
        source="phios.services.visualizer.list_visual_bloom_atlas_cohorts",
    )


def read_archive_curricula_index_resource(*, limit: int = _MAX_RECENT) -> dict[str, object]:
    return _index_payload(
        [r for r in list_visual_bloom_curricula() if isinstance(r, dict)],
        limit=limit,
        source="phios.services.visualizer.list_visual_bloom_curricula",
    )


def read_archive_journey_ensembles_index_resource(*, limit: int = _MAX_RECENT) -> dict[str, object]:
    return _index_payload(
        [r for r in list_visual_bloom_journey_ensembles() if isinstance(r, dict)],
        limit=limit,
        source="phios.services.visualizer.list_visual_bloom_journey_ensembles",
    )


def read_archive_route_compares_index_resource(*, limit: int = _MAX_RECENT) -> dict[str, object]:
    dashboard = build_visual_bloom_dashboard_model()
    rows_obj = dashboard.get("recent_route_compares") if isinstance(dashboard, dict) else []
    rows = [r for r in rows_obj if isinstance(r, dict)] if isinstance(rows_obj, list) else []
    return _index_payload(
        rows,
        limit=limit,
        source="phios.services.visualizer.build_visual_bloom_dashboard_model.recent_route_compares",
    )


def read_archive_longitudinal_index_resource() -> dict[str, object]:
    summary = build_visual_bloom_longitudinal_summary()
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "count": int(summary.get("session_count", 0)) if isinstance(summary, dict) else 0,
            "index": summary if isinstance(summary, dict) else {},
            "source": "phios.services.visualizer.build_visual_bloom_longitudinal_summary",
            "read_only": True,
        }
    )
