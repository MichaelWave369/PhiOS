"""Archive-wide catalog MCP resources (Phase 12, read-only)."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.mcp.resources.collections import _as_rows, _listify, _row_name
from phios.mcp.schema import with_resource_schema
from phios.services.visualizer import (
    list_visual_bloom_atlas_cohorts,
    list_visual_bloom_curricula,
    list_visual_bloom_dossiers,
    list_visual_bloom_field_libraries,
    list_visual_bloom_journey_ensembles,
    list_visual_bloom_reading_rooms,
    list_visual_bloom_shelves,
    list_visual_bloom_storyboards,
    list_visual_bloom_study_halls,
    list_visual_bloom_syllabi,
    list_visual_bloom_thematic_pathways,
)

_MAX_RECENT_TITLES = 8


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _catalog_payload(rows: list[dict[str, object]], *, catalog: str, families: list[str], source: str) -> dict[str, object]:
    titles = [title for row in rows if (title := _row_name(row))]

    tags: set[str] = set()
    sectors: dict[str, int] = {}
    family_counts: dict[str, int] = {family: 0 for family in families}
    route_available = False
    longitudinal_available = False
    diagnostics_available = False

    for row in rows:
        for key in ("tags", "tag", "labels"):
            tags.update(_listify(row.get(key)))

        for key in ("sector", "sector_family"):
            for sector in _listify(row.get(key)):
                sectors[sector] = sectors.get(sector, 0) + 1

        row_family = row.get("family") or row.get("artifact_family") or row.get("type") or row.get("kind")
        row_family_norm = row_family.strip() if isinstance(row_family, str) else None
        if row_family_norm and row_family_norm in family_counts:
            family_counts[row_family_norm] += 1

        route_available = route_available or any(bool(row.get(k)) for k in ("route", "route_path", "route_compare", "route_compares"))
        longitudinal_available = longitudinal_available or any(bool(row.get(k)) for k in ("longitudinal", "timeline", "trend"))
        diagnostics_available = diagnostics_available or any(bool(row.get(k)) for k in ("diagnostics", "compare", "comparison"))

    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "catalog": catalog,
            "count": len(rows),
            "families": families,
            "recent_titles": titles[:_MAX_RECENT_TITLES],
            "tag_coverage": sorted(tags),
            "artifact_family_counts": family_counts,
            "dominant_sector_counts": sectors,
            "availability": {
                "route": route_available,
                "longitudinal": longitudinal_available,
                "diagnostics": diagnostics_available,
            },
            "source": source,
            "read_only": True,
        }
    )


def read_catalog_learning_resource() -> dict[str, object]:
    rows = _as_rows(list_visual_bloom_curricula()) + _as_rows(list_visual_bloom_study_halls()) + _as_rows(list_visual_bloom_thematic_pathways())
    return _catalog_payload(
        rows,
        catalog="learning",
        families=["curricula", "study_halls", "thematic_pathways"],
        source="phios.services.visualizer.learning_family_lists",
    )


def read_catalog_capstones_resource() -> dict[str, object]:
    rows = _as_rows(list_visual_bloom_syllabi()) + _as_rows(list_visual_bloom_atlas_cohorts()) + _as_rows(list_visual_bloom_dossiers()) + _as_rows(list_visual_bloom_storyboards())
    return _catalog_payload(
        rows,
        catalog="capstones",
        families=["syllabi", "atlas_cohorts", "dossiers", "storyboards"],
        source="phios.services.visualizer.capstone_family_lists",
    )


def read_catalog_programs_resource() -> dict[str, object]:
    rows = _as_rows(list_visual_bloom_curricula()) + _as_rows(list_visual_bloom_journey_ensembles()) + _as_rows(list_visual_bloom_syllabi()) + _as_rows(list_visual_bloom_thematic_pathways())
    return _catalog_payload(
        rows,
        catalog="programs",
        families=["curricula", "journey_ensembles", "syllabi", "thematic_pathways"],
        source="phios.services.visualizer.program_family_lists",
    )


def read_catalog_collections_resource() -> dict[str, object]:
    rows = _as_rows(list_visual_bloom_field_libraries()) + _as_rows(list_visual_bloom_shelves()) + _as_rows(list_visual_bloom_reading_rooms())
    return _catalog_payload(
        rows,
        catalog="collections",
        families=["field_libraries", "shelves", "reading_rooms"],
        source="phios.services.visualizer.collection_family_lists",
    )
