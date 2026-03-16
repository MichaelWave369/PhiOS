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


def _to_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _title_tag_coverage(*payloads: dict[str, object]) -> tuple[list[str], list[str]]:
    titles: list[str] = []
    tags: set[str] = set()
    for payload in payloads:
        for title in _as_dict(payload).get("recent_titles", []):
            if isinstance(title, str) and title not in titles:
                titles.append(title)
        for tag in _as_dict(payload).get("tag_coverage", []):
            if isinstance(tag, str):
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
    discovery = build_mcp_discovery_payload(registry)
    return {
        "dashboards": len(_as_dict(discovery).get("dashboard_resources", [])),
        "consoles": len(_as_dict(discovery).get("console_resources", [])),
        "families": len(_as_dict(discovery).get("family_resources", [])),
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
    titles, tags = _title_tag_coverage(primary_dashboard, family_payload, *extra_dashboards.values())
    availability_flags = {
        "route_available": any(bool(_as_dict(m).get("route_available")) for m in maps.values()),
        "longitudinal_available": any(bool(_as_dict(m).get("longitudinal_available")) for m in maps.values()),
        "diagnostics_available": any(bool(_as_dict(m).get("diagnostics_available")) for m in maps.values()),
    }
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "console": console,
            "count": _to_int(_as_dict(primary_dashboard).get("count")),
            "surface_groups": {
                "dashboard": primary_dashboard,
                "related_dashboards": extra_dashboards,
                "family": family_payload,
                "family_dashboards": family_dashboards,
                "maps": maps,
            },
            "resource_counts": {
                "dashboard_count": _to_int(_as_dict(primary_dashboard).get("count")),
                "related_dashboards": len(extra_dashboards),
                "family_resources": len(family_dashboards) + 1,
            },
            "tool_counts": {
                "navigation_tools": 2,
                "summary_tools": 1,
            },
            "family_counts": {
                "family_count": len(_as_dict(family_payload).get("family_counts", {})),
                "family_dashboard_count": len(family_dashboards),
            },
            "catalog_counts": _as_dict(family_payload).get("catalog_counts", {}),
            "map_counts": {name: _to_int(_as_dict(payload).get("count")) for name, payload in maps.items()},
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
