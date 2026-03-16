"""Family navigation summary MCP resources (Phase 14-15, read-only)."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.mcp.resources.archive import read_archive_pathways_index_resource
from phios.mcp.resources.catalogs import (
    read_catalog_capstones_resource,
    read_catalog_collections_resource,
    read_catalog_learning_resource,
    read_catalog_programs_resource,
)
from phios.mcp.resources.dashboards import (
    read_dashboards_archive_resource,
    read_dashboards_capstones_resource,
    read_dashboards_learning_resource,
)
from phios.mcp.resources.maps import (
    read_capstones_map_resource,
    read_learning_map_resource,
    read_programs_map_resource,
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


def _titles(*payloads: dict[str, object]) -> list[str]:
    titles: list[str] = []
    for payload in payloads:
        for item in _as_str_list(payload.get("recent_titles", [])):
            if item not in titles:
                titles.append(item)
    return titles[:8]


def read_families_overview_resource() -> dict[str, object]:
    learning = read_catalog_learning_resource()
    capstones = read_catalog_capstones_resource()
    programs = read_catalog_programs_resource()
    collections = read_catalog_collections_resource()
    learning_map = read_learning_map_resource()

    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "family": "overview",
            "count": 4,
            "surface_groups": {
                "catalogs": {
                    "learning": learning,
                    "capstones": capstones,
                    "programs": programs,
                    "collections": collections,
                },
                "maps": {"learning": learning_map},
            },
            "family_counts": {
                "learning": len(_as_list(_as_dict(learning).get("families", []))),
                "capstones": len(_as_list(_as_dict(capstones).get("families", []))),
                "programs": len(_as_list(_as_dict(programs).get("families", []))),
                "collections": len(_as_list(_as_dict(collections).get("families", []))),
            },
            "catalog_counts": {
                "learning": _dict_int(_as_dict(learning), "count"),
                "capstones": _dict_int(_as_dict(capstones), "count"),
                "programs": _dict_int(_as_dict(programs), "count"),
                "collections": _dict_int(_as_dict(collections), "count"),
            },
            "map_counts": {"learning": _dict_int(_as_dict(learning_map), "count")},
            "recent_titles": _titles(_as_dict(learning), _as_dict(capstones), _as_dict(programs), _as_dict(collections)),
            "tag_coverage": sorted(
                {
                    tag
                    for payload in (_as_dict(learning), _as_dict(capstones), _as_dict(programs), _as_dict(collections))
                    for tag in _as_str_list(payload.get("tag_coverage", []))
                }
            ),
            "availability_flags": {
                "route_available": bool(_as_dict(learning_map).get("route_available")),
                "longitudinal_available": bool(_as_dict(learning_map).get("longitudinal_available")),
                "diagnostics_available": bool(_as_dict(learning_map).get("diagnostics_available")),
                "archive_pathways_available": _dict_int(_as_dict(read_archive_pathways_index_resource(limit=1)), "count") > 0,
            },
            "source": "phios.mcp.resources.families.overview",
            "read_only": True,
        }
    )


def read_families_learning_resource() -> dict[str, object]:
    learning = read_catalog_learning_resource()
    programs = read_catalog_programs_resource()
    learning_map = read_learning_map_resource()
    programs_map = read_programs_map_resource()
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "family": "learning",
            "count": _dict_int(_as_dict(learning), "count"),
            "surface_groups": {
                "catalogs": {"learning": learning, "programs": programs},
                "maps": {"learning": learning_map, "programs": programs_map},
            },
            "family_counts": {
                "learning": len(_as_list(_as_dict(learning).get("families", []))),
                "programs": len(_as_list(_as_dict(programs).get("families", []))),
            },
            "catalog_counts": {
                "learning": _dict_int(_as_dict(learning), "count"),
                "programs": _dict_int(_as_dict(programs), "count"),
            },
            "map_counts": {
                "learning": _dict_int(_as_dict(learning_map), "count"),
                "programs": _dict_int(_as_dict(programs_map), "count"),
            },
            "recent_titles": _titles(_as_dict(learning), _as_dict(programs)),
            "tag_coverage": sorted(
                {
                    tag
                    for payload in (_as_dict(learning), _as_dict(programs))
                    for tag in _as_str_list(payload.get("tag_coverage", []))
                }
            ),
            "availability_flags": {
                "route_available": bool(_as_dict(learning_map).get("route_available")) or bool(_as_dict(programs_map).get("route_available")),
                "longitudinal_available": bool(_as_dict(learning_map).get("longitudinal_available")) or bool(_as_dict(programs_map).get("longitudinal_available")),
                "diagnostics_available": bool(_as_dict(learning_map).get("diagnostics_available")) or bool(_as_dict(programs_map).get("diagnostics_available")),
            },
            "source": "phios.mcp.resources.families.learning",
            "read_only": True,
        }
    )


def read_families_capstones_resource() -> dict[str, object]:
    capstones = read_catalog_capstones_resource()
    capstones_map = read_capstones_map_resource()
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "family": "capstones",
            "count": _dict_int(_as_dict(capstones), "count"),
            "surface_groups": {
                "catalogs": {"capstones": capstones},
                "maps": {"capstones": capstones_map},
            },
            "family_counts": {"capstones": len(_as_list(_as_dict(capstones).get("families", [])))},
            "catalog_counts": {"capstones": _dict_int(_as_dict(capstones), "count")},
            "map_counts": {"capstones": _dict_int(_as_dict(capstones_map), "count")},
            "recent_titles": _titles(_as_dict(capstones)),
            "tag_coverage": sorted(_as_str_list(_as_dict(capstones).get("tag_coverage", []))),
            "availability_flags": {
                "route_available": bool(_as_dict(capstones_map).get("route_available")),
                "longitudinal_available": bool(_as_dict(capstones_map).get("longitudinal_available")),
                "diagnostics_available": bool(_as_dict(capstones_map).get("diagnostics_available")),
            },
            "source": "phios.mcp.resources.families.capstones",
            "read_only": True,
        }
    )


def _family_dashboard_payload(*, family_dashboard: str, base_family: dict[str, object], dashboard: dict[str, object], related: dict[str, object]) -> dict[str, object]:
    base_family_obj = _as_dict(base_family)
    dashboard_obj = _as_dict(dashboard)
    related_obj = _as_dict(related)
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "family_dashboard": family_dashboard,
            "count": _dict_int(base_family_obj, "count"),
            "surface_groups": {
                "family": base_family,
                "dashboard": dashboard,
                "related": related,
            },
            "family_counts": _as_dict(base_family_obj.get("family_counts", {})),
            "catalog_counts": _as_dict(base_family_obj.get("catalog_counts", {})),
            "map_counts": _as_dict(base_family_obj.get("map_counts", {})),
            "dashboard_counts": {
                "selected_dashboard_count": _dict_int(dashboard_obj, "count"),
                "related_dashboard_count": _dict_int(related_obj, "count"),
            },
            "recent_titles": _titles(base_family_obj, dashboard_obj),
            "tag_coverage": sorted(
                {
                    tag
                    for payload in (base_family_obj, dashboard_obj)
                    for tag in _as_str_list(payload.get("tag_coverage", []))
                }
            ),
            "availability_flags": _as_dict(base_family_obj.get("availability_flags", {})),
            "source": f"phios.mcp.resources.families.{family_dashboard}",
            "read_only": True,
        }
    )


def read_families_dashboard_overview_resource() -> dict[str, object]:
    return _family_dashboard_payload(
        family_dashboard="dashboard_overview",
        base_family=read_families_overview_resource(),
        dashboard=read_dashboards_archive_resource(),
        related=read_dashboards_learning_resource(),
    )


def read_families_dashboard_learning_resource() -> dict[str, object]:
    return _family_dashboard_payload(
        family_dashboard="dashboard_learning",
        base_family=read_families_learning_resource(),
        dashboard=read_dashboards_learning_resource(),
        related=read_dashboards_archive_resource(),
    )


def read_families_dashboard_capstones_resource() -> dict[str, object]:
    return _family_dashboard_payload(
        family_dashboard="dashboard_capstones",
        base_family=read_families_capstones_resource(),
        dashboard=read_dashboards_capstones_resource(),
        related=read_dashboards_archive_resource(),
    )
