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


def _to_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, (str, bytes, bytearray)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return default


def _as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _as_rows(rows: object) -> list[dict[str, object]]:
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _index_payload(rows: list[dict[str, object]], *, limit: int, source: str) -> dict[str, object]:
    safe_limit = max(0, _to_int(limit))
    capped = rows[:safe_limit]
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "count": len(capped),
            "limit": safe_limit,
            "index": capped,
            "source": source,
            "read_only": True,
        }
    )


def read_archive_pathways_index_resource(*, limit: int = _MAX_RECENT) -> dict[str, object]:
    return _index_payload(
        _as_rows(list_visual_bloom_pathways()),
        limit=limit,
        source="phios.services.visualizer.list_visual_bloom_pathways",
    )


def read_archive_atlas_index_resource(*, limit: int = _MAX_RECENT) -> dict[str, object]:
    return _index_payload(
        _as_rows(list_visual_bloom_atlas_cohorts()),
        limit=limit,
        source="phios.services.visualizer.list_visual_bloom_atlas_cohorts",
    )


def read_archive_curricula_index_resource(*, limit: int = _MAX_RECENT) -> dict[str, object]:
    return _index_payload(
        _as_rows(list_visual_bloom_curricula()),
        limit=limit,
        source="phios.services.visualizer.list_visual_bloom_curricula",
    )


def read_archive_journey_ensembles_index_resource(*, limit: int = _MAX_RECENT) -> dict[str, object]:
    return _index_payload(
        _as_rows(list_visual_bloom_journey_ensembles()),
        limit=limit,
        source="phios.services.visualizer.list_visual_bloom_journey_ensembles",
    )


def read_archive_route_compares_index_resource(*, limit: int = _MAX_RECENT) -> dict[str, object]:
    dashboard = _as_dict(build_visual_bloom_dashboard_model())
    rows = _as_rows(dashboard.get("recent_route_compares", []))
    return _index_payload(
        rows,
        limit=limit,
        source="phios.services.visualizer.build_visual_bloom_dashboard_model.recent_route_compares",
    )


def read_archive_longitudinal_index_resource() -> dict[str, object]:
    summary = _as_dict(build_visual_bloom_longitudinal_summary())
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "count": _to_int(summary.get("session_count", 0)),
            "index": summary,
            "source": "phios.services.visualizer.build_visual_bloom_longitudinal_summary",
            "read_only": True,
        }
    )
