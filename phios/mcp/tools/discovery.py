"""MCP discovery tools."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.mcp.discovery import build_mcp_discovery_payload
from phios.mcp.resources.consoles import (
    read_consoles_archive_resource,
    read_consoles_capstones_resource,
    read_consoles_learning_resource,
    read_consoles_navigation_resource,
)
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
from phios.mcp.schema import with_tool_schema


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
    if isinstance(value, (str, bytes, bytearray)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return default


def run_phi_discovery(registry: object) -> dict[str, object]:
    """Return discovery payload through a tool surface."""

    return with_tool_schema(build_mcp_discovery_payload(registry))


def run_phi_discovery_dashboard_summary(
    registry: object,
    *,
    dashboard: str = "discovery",
    family_dashboard: str | None = None,
    include_dashboard_counts: bool = True,
    include_family_counts: bool = True,
    include_family_dashboard_counts: bool = False,
) -> dict[str, object]:
    """Return bounded synthesis over dashboard/family discovery resources."""

    normalized = (dashboard or "discovery").strip().lower()
    builders = {
        "discovery": lambda: read_dashboards_discovery_resource(registry),
        "archive": read_dashboards_archive_resource,
        "learning": read_dashboards_learning_resource,
        "capstones": read_dashboards_capstones_resource,
    }
    selected = builders[normalized]() if normalized in builders else builders["discovery"]()

    families = {
        "overview": read_families_overview_resource(),
        "learning": read_families_learning_resource(),
        "capstones": read_families_capstones_resource(),
    }
    family_dashboard_builders = {
        "dashboard_overview": read_families_dashboard_overview_resource,
        "dashboard_learning": read_families_dashboard_learning_resource,
        "dashboard_capstones": read_families_dashboard_capstones_resource,
    }
    selected_family_dashboard = (family_dashboard or "").strip().lower()
    if selected_family_dashboard not in family_dashboard_builders:
        selected_family_dashboard = ""

    payload: dict[str, object] = {
        "ok": True,
        "generated_at": _utc_now_iso(),
        "dashboard": normalized if normalized in builders else "discovery",
        "dashboard_payload": selected,
        "family_navigation": families,
    }
    if selected_family_dashboard:
        payload["family_dashboard"] = selected_family_dashboard
        payload["family_dashboard_payload"] = family_dashboard_builders[selected_family_dashboard]()

    if include_dashboard_counts:
        payload["dashboard_counts"] = {
            "count": _to_int(_as_dict(selected).get("count")),
            "resource_count": len(_as_dict(_as_dict(selected).get("resource_counts", {}))),
            "map_count": len(_as_dict(_as_dict(selected).get("map_counts", {}))),
        }
    if include_family_counts:
        payload["family_counts"] = {
            name: _to_int(_as_dict(resource).get("count")) for name, resource in families.items()
        }
    if include_family_dashboard_counts:
        payload["family_dashboard_counts"] = {
            name: _to_int(_as_dict(builder()).get("count")) for name, builder in family_dashboard_builders.items()
        }
    return with_tool_schema(payload)


def run_phi_navigation_console_summary(
    registry: object,
    *,
    console: str = "navigation",
    include_console_counts: bool = True,
    include_family_dashboard_counts: bool = True,
) -> dict[str, object]:
    """Return bounded synthesis over Phase 15 navigation consoles."""

    normalized = (console or "navigation").strip().lower()
    builders = {
        "navigation": lambda: read_consoles_navigation_resource(registry),
        "archive": lambda: read_consoles_archive_resource(registry),
        "learning": lambda: read_consoles_learning_resource(registry),
        "capstones": lambda: read_consoles_capstones_resource(registry),
    }
    selected = builders[normalized]() if normalized in builders else builders["navigation"]()

    payload: dict[str, object] = {
        "ok": True,
        "generated_at": _utc_now_iso(),
        "console": normalized if normalized in builders else "navigation",
        "console_payload": selected,
    }
    if include_console_counts:
        payload["console_counts"] = {
            "count": _to_int(_as_dict(selected).get("count")),
            "resource_count": len(_as_dict(_as_dict(selected).get("resource_counts", {}))),
            "dashboard_count": len(_as_dict(_as_dict(selected).get("dashboard_counts", {}))),
        }
    if include_family_dashboard_counts:
        payload["family_dashboard_counts"] = {
            "dashboard_overview": _to_int(_as_dict(read_families_dashboard_overview_resource()).get("count")),
            "dashboard_learning": _to_int(_as_dict(read_families_dashboard_learning_resource()).get("count")),
            "dashboard_capstones": _to_int(_as_dict(read_families_dashboard_capstones_resource()).get("count")),
        }
    return with_tool_schema(payload)
