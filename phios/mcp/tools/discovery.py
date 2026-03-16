"""MCP discovery tools."""

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
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def run_phi_discovery(registry: object) -> dict[str, object]:
    """Return discovery payload through a tool surface."""

    return with_tool_schema(build_mcp_discovery_payload(registry))


def run_phi_discovery_dashboard_summary(
    registry: object,
    *,
    dashboard: str = "discovery",
    include_dashboard_counts: bool = True,
    include_family_counts: bool = True,
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
    payload: dict[str, object] = {
        "ok": True,
        "generated_at": _utc_now_iso(),
        "dashboard": normalized if normalized in builders else "discovery",
        "dashboard_payload": selected,
        "family_navigation": families,
    }
    if include_dashboard_counts:
        payload["dashboard_counts"] = {
            "count": _to_int(_as_dict(selected).get("count")),
            "resource_count": len(_as_dict(selected).get("resource_counts", {})),
            "map_count": len(_as_dict(selected).get("map_counts", {})),
        }
    if include_family_counts:
        payload["family_counts"] = {
            name: _to_int(_as_dict(resource).get("count"))
            for name, resource in families.items()
        }
    return with_tool_schema(payload)
