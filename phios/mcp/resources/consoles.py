"""Archive-wide navigation console MCP resources (Phase 15, read-only)."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.mcp.discovery import build_mcp_discovery_payload
from phios.mcp.resources.dashboards import (
    read_dashboards_archive_resource,
    read_dashboards_capstones_resource,
    read_dashboards_discovery_resource,
    read_dashboards_learning_resource,
)
from phios.mcp.resources.families import (
    read_families_capstones_resource,
    read_families_dashboard_capstones_resource,
    read_families_dashboard_learning_resource,
    read_families_dashboard_overview_resource,
    read_families_learning_resource,
    read_families_overview_resource,
)
from phios.mcp.resources.maps import (
    read_capstones_map_resource,
    read_collections_map_resource,
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


def _title_tag_coverage(*payloads: dict[str, object]) -> tuple[list[str], list[str]]:
    titles: list[str] = []
    tags: set[str] = set()
    for payload in payloads:
        for title in _as_str_list(payload.get("recent_titles", [])):
            if title not in titles:
                titles.append(title)
        for tag in _as_str_list(payload.get("tag_coverage", [])):
            tags.add(tag)
    return titles[:10], sorted(tags)


def _maps() -> dict[str, dict[str, object]]:
    return {
        "learning": read_learning_map_resource(),
        "capstones": read_capstones_map_resource(),
        "programs": read_programs_map_resource(),
        "collections": read_collections_map_resource(),
    }


def _dashboard_counts(registry: object) -> dict[str, int]:
    discovery = _as_dict(build_mcp_discovery_payload(registry))
    return {
        "dashboards": len(_as_list(discovery.get("dashboard_resources", []))),
        "consoles": len(_as_list(discovery.get("console_resources", []))),
        "families": len(_as_list(discovery.get("family_resources", []))),
    }


def _base_console_payload(
    *,
    registry: object,
    console: str,
    primary_dashboard: dict[str, object],
    family_payload: dict[str, object],
    extra_dashboards: dict[str, dict[str, object]],
    family_dashboards: dict[str, dict[str, object]],
) -> dict[str, object]:
    maps = _maps()
    titles, tags = _title_tag_coverage(_as_dict(primary_dashboard), _as_dict(family_payload), *[_as_dict(v) for v in extra_dashboards.values()])
    availability_flags = {
        "route_available": any(bool(_as_dict(m).get("route_available")) for m in maps.values()),
        "longitudinal_available": any(bool(_as_dict(m).get("longitudinal_available")) for m in maps.values()),
        "diagnostics_available": any(bool(_as_dict(m).get("diagnostics_available")) for m in maps.values()),
    }
    family_counts = _as_dict(_as_dict(family_payload).get("family_counts", {}))
    catalog_counts = _as_dict(_as_dict(family_payload).get("catalog_counts", {}))
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "console": console,
            "count": _dict_int(_as_dict(primary_dashboard), "count"),
            "surface_groups": {
                "dashboard": primary_dashboard,
                "related_dashboards": extra_dashboards,
                "family": family_payload,
                "family_dashboards": family_dashboards,
                "maps": maps,
            },
            "resource_counts": {
                "dashboard_count": _dict_int(_as_dict(primary_dashboard), "count"),
                "related_dashboards": len(extra_dashboards),
                "family_resources": len(family_dashboards) + 1,
            },
            "tool_counts": {
                "navigation_tools": 2,
                "summary_tools": 1,
            },
            "family_counts": {
                "family_count": len(family_counts),
                "family_dashboard_count": len(family_dashboards),
            },
            "catalog_counts": catalog_counts,
            "map_counts": {name: _dict_int(_as_dict(payload), "count") for name, payload in maps.items()},
            "dashboard_counts": _dashboard_counts(registry),
            "recent_titles": titles,
            "tag_coverage": tags,
            "availability_flags": availability_flags,
            "source": f"phios.mcp.resources.consoles.{console}",
            "read_only": True,
        }
    )


def read_consoles_navigation_resource(registry: object) -> dict[str, object]:
    return _base_console_payload(
        registry=registry,
        console="navigation",
        primary_dashboard=read_dashboards_discovery_resource(registry),
        family_payload=read_families_overview_resource(),
        extra_dashboards={
            "archive": read_dashboards_archive_resource(),
            "learning": read_dashboards_learning_resource(),
            "capstones": read_dashboards_capstones_resource(),
        },
        family_dashboards={
            "dashboard_overview": read_families_dashboard_overview_resource(),
            "dashboard_learning": read_families_dashboard_learning_resource(),
            "dashboard_capstones": read_families_dashboard_capstones_resource(),
        },
    )


def read_consoles_archive_resource(registry: object) -> dict[str, object]:
    return _base_console_payload(
        registry=registry,
        console="archive",
        primary_dashboard=read_dashboards_archive_resource(),
        family_payload=read_families_overview_resource(),
        extra_dashboards={"discovery": read_dashboards_discovery_resource(registry)},
        family_dashboards={"dashboard_overview": read_families_dashboard_overview_resource()},
    )


def read_consoles_learning_resource(registry: object) -> dict[str, object]:
    return _base_console_payload(
        registry=registry,
        console="learning",
        primary_dashboard=read_dashboards_learning_resource(),
        family_payload=read_families_learning_resource(),
        extra_dashboards={"discovery": read_dashboards_discovery_resource(registry)},
        family_dashboards={"dashboard_learning": read_families_dashboard_learning_resource()},
    )


def read_consoles_capstones_resource(registry: object) -> dict[str, object]:
    return _base_console_payload(
        registry=registry,
        console="capstones",
        primary_dashboard=read_dashboards_capstones_resource(),
        family_payload=read_families_capstones_resource(),
        extra_dashboards={"discovery": read_dashboards_discovery_resource(registry)},
        family_dashboards={"dashboard_capstones": read_families_dashboard_capstones_resource()},
    )
