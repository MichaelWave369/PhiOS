"""Collection/library rollup MCP resources (Phase 9, read-only)."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.mcp.schema import with_resource_schema
from phios.services.visualizer import (
    list_visual_bloom_curricula,
    list_visual_bloom_field_libraries,
    list_visual_bloom_journey_ensembles,
    list_visual_bloom_reading_rooms,
    list_visual_bloom_shelves,
    list_visual_bloom_study_halls,
)

_MAX_RECENT_NAMES = 5


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_rows(rows: object) -> list[dict[str, object]]:
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _row_name(row: dict[str, object]) -> str | None:
    for key in ("title", "name", "label", "id"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _listify(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _rollup(rows: list[dict[str, object]], *, family: str, source: str) -> dict[str, object]:
    names = [name for row in rows if (name := _row_name(row))]

    tags: set[str] = set()
    families: set[str] = set()
    sectors: dict[str, int] = {}

    route_available = False
    longitudinal_available = False

    for row in rows:
        for key in ("tags", "tag", "labels"):
            tags.update(_listify(row.get(key)))

        for key in ("artifact_family", "family", "type", "kind"):
            families.update(_listify(row.get(key)))

        for key in ("sector", "sector_family"):
            for sector in _listify(row.get(key)):
                sectors[sector] = sectors.get(sector, 0) + 1

        route_available = route_available or any(
            bool(row.get(key)) for key in ("route_compare", "route_compares", "route_path", "route")
        )
        longitudinal_available = longitudinal_available or any(
            bool(row.get(key)) for key in ("longitudinal", "timeline", "trend")
        )

    dominant_sector = max(sectors, key=sectors.get) if sectors else None

    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "family": family,
            "count": len(rows),
            "recent_names": names[:_MAX_RECENT_NAMES],
            "tag_coverage": sorted(tags),
            "artifact_family_coverage": sorted(families),
            "dominant_sector": dominant_sector,
            "availability": {
                "route_compare": route_available,
                "longitudinal": longitudinal_available,
            },
            "source": source,
            "read_only": True,
        }
    )


def read_field_libraries_rollup_resource() -> dict[str, object]:
    return _rollup(
        _as_rows(list_visual_bloom_field_libraries()),
        family="field_libraries",
        source="phios.services.visualizer.list_visual_bloom_field_libraries",
    )


def read_shelves_rollup_resource() -> dict[str, object]:
    return _rollup(
        _as_rows(list_visual_bloom_shelves()),
        family="shelves",
        source="phios.services.visualizer.list_visual_bloom_shelves",
    )


def read_reading_rooms_rollup_resource() -> dict[str, object]:
    return _rollup(
        _as_rows(list_visual_bloom_reading_rooms()),
        family="reading_rooms",
        source="phios.services.visualizer.list_visual_bloom_reading_rooms",
    )


def read_study_halls_rollup_resource() -> dict[str, object]:
    return _rollup(
        _as_rows(list_visual_bloom_study_halls()),
        family="study_halls",
        source="phios.services.visualizer.list_visual_bloom_study_halls",
    )


def read_curricula_rollup_resource() -> dict[str, object]:
    return _rollup(
        _as_rows(list_visual_bloom_curricula()),
        family="curricula",
        source="phios.services.visualizer.list_visual_bloom_curricula",
    )


def read_journey_ensembles_rollup_resource() -> dict[str, object]:
    return _rollup(
        _as_rows(list_visual_bloom_journey_ensembles()),
        family="journey_ensembles",
        source="phios.services.visualizer.list_visual_bloom_journey_ensembles",
    )
