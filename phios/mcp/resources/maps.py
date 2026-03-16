"""Cross-catalog learning map MCP resources (Phase 13, read-only)."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.mcp.resources.catalogs import (
    read_catalog_capstones_resource,
    read_catalog_collections_resource,
    read_catalog_learning_resource,
    read_catalog_programs_resource,
)
from phios.mcp.schema import with_resource_schema


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


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _build_learning_map(*, map_name: str, primary_catalog: str, linked_catalogs: list[str]) -> dict[str, object]:
    catalogs = {
        "learning": read_catalog_learning_resource(),
        "capstones": read_catalog_capstones_resource(),
        "programs": read_catalog_programs_resource(),
        "collections": read_catalog_collections_resource(),
    }

    primary = catalogs[primary_catalog]
    linked = {name: catalogs[name] for name in linked_catalogs}

    family_counts: dict[str, int] = {}
    tag_coverage: set[str] = set()
    artifact_family_counts: dict[str, int] = {}
    dominant_sector_counts: dict[str, int] = {}
    recent_titles: list[str] = []

    for payload in [primary, *linked.values()]:
        if not isinstance(payload, dict):
            continue
        for family, count in _as_dict(payload.get("artifact_family_counts", {})).items():
            if isinstance(family, str):
                family_counts[family] = family_counts.get(family, 0) + _to_int(count)
                artifact_family_counts[family] = artifact_family_counts.get(family, 0) + _to_int(count)

        tags = payload.get("tag_coverage", [])
        if isinstance(tags, list):
            for tag in tags:
                if isinstance(tag, str):
                    tag_coverage.add(tag)

        sectors = payload.get("dominant_sector_counts", {})
        if isinstance(sectors, dict):
            for sector, value in sectors.items():
                if isinstance(sector, str):
                    dominant_sector_counts[sector] = dominant_sector_counts.get(sector, 0) + _to_int(value)

        titles = payload.get("recent_titles", [])
        if isinstance(titles, list):
            for title in titles:
                if isinstance(title, str) and title not in recent_titles:
                    recent_titles.append(title)

    route_available = any(bool(_as_dict(_as_dict(catalogs[name]).get("availability", {})).get("route")) for name in [primary_catalog, *linked_catalogs])
    longitudinal_available = any(bool(_as_dict(_as_dict(catalogs[name]).get("availability", {})).get("longitudinal")) for name in [primary_catalog, *linked_catalogs])
    diagnostics_available = any(bool(_as_dict(_as_dict(catalogs[name]).get("availability", {})).get("diagnostics")) for name in [primary_catalog, *linked_catalogs])

    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "map": map_name,
            "count": _to_int(_as_dict(primary).get("count", 0)),
            "families": _as_str_list(_as_dict(primary).get("families", [])),
            "linked_catalogs": linked_catalogs,
            "family_counts": family_counts,
            "tag_coverage": sorted(tag_coverage),
            "artifact_family_counts": artifact_family_counts,
            "dominant_sector_counts": dominant_sector_counts,
            "route_available": route_available,
            "longitudinal_available": longitudinal_available,
            "diagnostics_available": diagnostics_available,
            "recent_titles": recent_titles[:10],
            "availability": {
                "route": route_available,
                "longitudinal": longitudinal_available,
                "diagnostics": diagnostics_available,
            },
            "primary_catalog": primary,
            "linked": linked,
            "source": "phios.mcp.resources.maps",
            "read_only": True,
        }
    )


def read_learning_map_resource() -> dict[str, object]:
    return _build_learning_map(
        map_name="learning",
        primary_catalog="learning",
        linked_catalogs=["programs", "capstones", "collections"],
    )


def read_capstones_map_resource() -> dict[str, object]:
    return _build_learning_map(
        map_name="capstones",
        primary_catalog="capstones",
        linked_catalogs=["learning", "programs"],
    )


def read_programs_map_resource() -> dict[str, object]:
    return _build_learning_map(
        map_name="programs",
        primary_catalog="programs",
        linked_catalogs=["learning", "capstones", "collections"],
    )


def read_collections_map_resource() -> dict[str, object]:
    return _build_learning_map(
        map_name="collections",
        primary_catalog="collections",
        linked_catalogs=["learning", "programs", "capstones"],
    )
