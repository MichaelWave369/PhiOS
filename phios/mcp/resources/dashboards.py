"""Archive-wide discovery dashboard MCP resources (Phase 14, read-only)."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.mcp.discovery import build_mcp_discovery_payload
from phios.mcp.resources.archive import (
    read_archive_atlas_index_resource,
    read_archive_curricula_index_resource,
    read_archive_journey_ensembles_index_resource,
    read_archive_longitudinal_index_resource,
    read_archive_pathways_index_resource,
    read_archive_route_compares_index_resource,
)
from phios.mcp.resources.capstones import (
    read_capstones_atlas_cohorts_rollup_resource,
    read_capstones_dossiers_rollup_family_resource,
    read_capstones_field_libraries_rollup_family_resource,
    read_capstones_storyboards_rollup_family_resource,
    read_capstones_syllabi_rollup_resource,
)
from phios.mcp.resources.catalogs import (
    read_catalog_capstones_resource,
    read_catalog_collections_resource,
    read_catalog_learning_resource,
    read_catalog_programs_resource,
)
from phios.mcp.resources.collections import (
    read_curricula_rollup_resource,
    read_field_libraries_rollup_resource,
    read_journey_ensembles_rollup_resource,
    read_reading_rooms_rollup_resource,
    read_shelves_rollup_resource,
    read_study_halls_rollup_resource,
)
from phios.mcp.resources.maps import (
    read_capstones_map_resource,
    read_collections_map_resource,
    read_learning_map_resource,
    read_programs_map_resource,
)
from phios.mcp.resources.programs import (
    read_programs_curricula_rollup_resource,
    read_programs_journey_ensembles_rollup_resource,
    read_programs_study_halls_rollup_resource,
    read_programs_syllabi_rollup_resource,
    read_programs_thematic_pathways_rollup_resource,
)
from phios.mcp.schema import with_resource_schema


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _as_str_list(value: object) -> list[str]:
    return [item for item in _as_list(value) if isinstance(item, str)]


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


def _dict_int(mapping: dict[str, object], key: str, default: int = 0) -> int:
    return _to_int(mapping.get(key, default), default)


def _collect_titles_and_tags(*catalogs: dict[str, object]) -> tuple[list[str], list[str]]:
    titles: list[str] = []
    tags: set[str] = set()
    for catalog in catalogs:
        for title in _as_str_list(catalog.get("recent_titles", [])):
            if title not in titles:
                titles.append(title)
        for tag in _as_str_list(catalog.get("tag_coverage", [])):
            tags.add(tag)
    return titles[:10], sorted(tags)


def _catalogs() -> dict[str, dict[str, object]]:
    return {
        "learning": read_catalog_learning_resource(),
        "capstones": read_catalog_capstones_resource(),
        "programs": read_catalog_programs_resource(),
        "collections": read_catalog_collections_resource(),
    }


def _maps() -> dict[str, dict[str, object]]:
    return {
        "learning": read_learning_map_resource(),
        "capstones": read_capstones_map_resource(),
        "programs": read_programs_map_resource(),
        "collections": read_collections_map_resource(),
    }


def read_dashboards_discovery_resource(registry: object) -> dict[str, object]:
    discovery = _as_dict(build_mcp_discovery_payload(registry))
    catalogs = _catalogs()
    maps = _maps()
    titles, tags = _collect_titles_and_tags(*catalogs.values())

    dashboard_resources = _as_list(discovery.get("dashboard_resources", []))
    family_resources = _as_list(discovery.get("family_resources", []))
    learning_browse_families = _as_list(discovery.get("learning_browse_families", []))
    browse_family_groups = _as_dict(discovery.get("browse_family_groups", {}))

    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "dashboard": "discovery",
            "count": _dict_int(discovery, "resource_counts"),
            "surface_groups": {
                "browse_resources": _as_list(discovery.get("browse_resources", [])),
                "catalog_resources": _as_list(discovery.get("catalog_resources", [])),
                "learning_maps": _as_list(discovery.get("learning_maps", [])),
                "dashboard_resources": dashboard_resources,
                "family_resources": family_resources,
            },
            "resource_counts": {
                "resources": _dict_int(discovery, "resource_counts"),
                "dashboards": len(dashboard_resources),
                "families": len(family_resources),
            },
            "tool_counts": {
                "tools": _dict_int(discovery, "tool_counts"),
                "dashboard_tools": 1,
            },
            "family_counts": {
                "browse_families": _dict_int(browse_family_groups, "family_count"),
                "learning_families": len(learning_browse_families),
            },
            "catalog_counts": {name: _dict_int(_as_dict(payload), "count") for name, payload in catalogs.items()},
            "map_counts": {name: _dict_int(_as_dict(payload), "count") for name, payload in maps.items()},
            "recent_titles": titles,
            "tag_coverage": tags,
            "availability_flags": {
                "route_available": any(bool(_as_dict(payload).get("route_available")) for payload in maps.values()),
                "longitudinal_available": any(bool(_as_dict(payload).get("longitudinal_available")) for payload in maps.values()),
                "diagnostics_available": any(bool(_as_dict(payload).get("diagnostics_available")) for payload in maps.values()),
            },
            "source": "phios.mcp.resources.dashboards.discovery",
            "read_only": True,
        }
    )


def read_dashboards_archive_resource() -> dict[str, object]:
    catalogs = _catalogs()
    maps = _maps()
    archive_indexes = {
        "pathways": read_archive_pathways_index_resource(limit=10),
        "atlas": read_archive_atlas_index_resource(limit=10),
        "route_compares": read_archive_route_compares_index_resource(limit=10),
        "longitudinal": read_archive_longitudinal_index_resource(),
        "curricula": read_archive_curricula_index_resource(limit=10),
        "journey_ensembles": read_archive_journey_ensembles_index_resource(limit=10),
    }
    titles, tags = _collect_titles_and_tags(*catalogs.values())
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "dashboard": "archive",
            "count": sum(_dict_int(_as_dict(payload), "count") for payload in archive_indexes.values()),
            "surface_groups": {
                "archive_indexes": archive_indexes,
                "program_rollups": {
                    "curricula": read_programs_curricula_rollup_resource(),
                    "study_halls": read_programs_study_halls_rollup_resource(),
                    "thematic_pathways": read_programs_thematic_pathways_rollup_resource(),
                    "syllabi": read_programs_syllabi_rollup_resource(),
                    "journey_ensembles": read_programs_journey_ensembles_rollup_resource(),
                },
            },
            "resource_counts": {name: _dict_int(_as_dict(payload), "count") for name, payload in archive_indexes.items()},
            "tool_counts": {"archive_summary_tools": 3, "summary_tools": 1},
            "family_counts": {
                "collection_rollups": 6,
                "program_rollups": 5,
                "capstone_rollups": 5,
            },
            "catalog_counts": {name: _dict_int(_as_dict(payload), "count") for name, payload in catalogs.items()},
            "map_counts": {name: _dict_int(_as_dict(payload), "count") for name, payload in maps.items()},
            "recent_titles": titles,
            "tag_coverage": tags,
            "availability_flags": {
                "route_available": _dict_int(_as_dict(archive_indexes["route_compares"]), "count") > 0,
                "longitudinal_available": _dict_int(_as_dict(archive_indexes["longitudinal"]), "count") > 0,
                "diagnostics_available": _dict_int(_as_dict(archive_indexes["route_compares"]), "count") > 0,
            },
            "source": "phios.mcp.resources.dashboards.archive",
            "read_only": True,
        }
    )


def read_dashboards_learning_resource() -> dict[str, object]:
    learning_catalog = read_catalog_learning_resource()
    programs_catalog = read_catalog_programs_resource()
    learning_map = read_learning_map_resource()
    programs_map = read_programs_map_resource()
    collection_rollups = {
        "curricula": read_curricula_rollup_resource(),
        "journey_ensembles": read_journey_ensembles_rollup_resource(),
        "study_halls": read_study_halls_rollup_resource(),
    }
    titles, tags = _collect_titles_and_tags(learning_catalog, programs_catalog)
    learning_families = _as_list(_as_dict(learning_catalog).get("families", []))
    program_families = _as_list(_as_dict(programs_catalog).get("families", []))
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "dashboard": "learning",
            "count": _dict_int(_as_dict(learning_catalog), "count"),
            "surface_groups": {
                "catalogs": {"learning": learning_catalog, "programs": programs_catalog},
                "maps": {"learning": learning_map, "programs": programs_map},
                "collection_rollups": collection_rollups,
            },
            "resource_counts": {
                "learning_catalog": _dict_int(_as_dict(learning_catalog), "count"),
                "programs_catalog": _dict_int(_as_dict(programs_catalog), "count"),
                "collection_rollups": sum(_dict_int(_as_dict(payload), "count") for payload in collection_rollups.values()),
            },
            "tool_counts": {"learning_summary_tools": 3},
            "family_counts": {
                "learning_families": len(learning_families),
                "program_families": len(program_families),
            },
            "catalog_counts": {
                "learning": _dict_int(_as_dict(learning_catalog), "count"),
                "programs": _dict_int(_as_dict(programs_catalog), "count"),
            },
            "map_counts": {
                "learning": _dict_int(_as_dict(learning_map), "count"),
                "programs": _dict_int(_as_dict(programs_map), "count"),
            },
            "recent_titles": titles,
            "tag_coverage": tags,
            "availability_flags": {
                "route_available": bool(_as_dict(learning_map).get("route_available")) or bool(_as_dict(programs_map).get("route_available")),
                "longitudinal_available": bool(_as_dict(learning_map).get("longitudinal_available")) or bool(_as_dict(programs_map).get("longitudinal_available")),
                "diagnostics_available": bool(_as_dict(learning_map).get("diagnostics_available")) or bool(_as_dict(programs_map).get("diagnostics_available")),
            },
            "source": "phios.mcp.resources.dashboards.learning",
            "read_only": True,
        }
    )


def read_dashboards_capstones_resource() -> dict[str, object]:
    capstones_catalog = read_catalog_capstones_resource()
    capstones_map = read_capstones_map_resource()
    capstone_rollups = {
        "syllabi": read_capstones_syllabi_rollup_resource(),
        "atlas_cohorts": read_capstones_atlas_cohorts_rollup_resource(),
        "field_libraries_family": read_capstones_field_libraries_rollup_family_resource(),
        "dossiers_family": read_capstones_dossiers_rollup_family_resource(),
        "storyboards_family": read_capstones_storyboards_rollup_family_resource(),
    }
    collection_support = {
        "field_libraries": read_field_libraries_rollup_resource(),
        "shelves": read_shelves_rollup_resource(),
        "reading_rooms": read_reading_rooms_rollup_resource(),
    }
    titles, tags = _collect_titles_and_tags(capstones_catalog)
    capstone_families = _as_list(_as_dict(capstones_catalog).get("families", []))
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "dashboard": "capstones",
            "count": _dict_int(_as_dict(capstones_catalog), "count"),
            "surface_groups": {
                "catalog": capstones_catalog,
                "map": capstones_map,
                "capstone_rollups": capstone_rollups,
                "collection_support": collection_support,
            },
            "resource_counts": {name: _dict_int(_as_dict(payload), "count") for name, payload in capstone_rollups.items()},
            "tool_counts": {"capstone_summary_tools": 3},
            "family_counts": {
                "catalog_families": len(capstone_families),
                "rollup_families": len(capstone_rollups),
            },
            "catalog_counts": {"capstones": _dict_int(_as_dict(capstones_catalog), "count")},
            "map_counts": {"capstones": _dict_int(_as_dict(capstones_map), "count")},
            "recent_titles": titles,
            "tag_coverage": tags,
            "availability_flags": {
                "route_available": bool(_as_dict(capstones_map).get("route_available")),
                "longitudinal_available": bool(_as_dict(capstones_map).get("longitudinal_available")),
                "diagnostics_available": bool(_as_dict(capstones_map).get("diagnostics_available")),
            },
            "source": "phios.mcp.resources.dashboards.capstones",
            "read_only": True,
        }
    )
