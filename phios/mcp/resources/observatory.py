"""Observatory MCP resources (Phase 3, read-only)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from phios.mcp.schema import with_resource_schema
from phios.services.visualizer import (
    build_visual_bloom_atlas_gallery_model,
    build_visual_bloom_dashboard_model,
    build_visual_bloom_field_library_index,
    list_visual_bloom_dossiers,
    list_visual_bloom_storyboards,
)


_MAX_RECENT = 20


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_observatory_index_resource() -> dict[str, object]:
    """Return discovery index for observatory MCP resources."""

    resources = [
        {
            "uri": "phios://observatory/index",
            "kind": "index",
            "description": "Lists available observatory MCP resources.",
        },
        {
            "uri": "phios://observatory/dashboard",
            "kind": "dashboard",
            "description": "Aggregated observatory dashboard model from local journal artifacts.",
        },
        {
            "uri": "phios://observatory/atlas_gallery",
            "kind": "atlas_gallery",
            "description": "Atlas/route-compare gallery model and sector summaries.",
        },
        {
            "uri": "phios://observatory/storyboards/recent",
            "kind": "storyboards",
            "description": "Recent storyboard summaries.",
        },
        {
            "uri": "phios://observatory/dossiers/recent",
            "kind": "dossiers",
            "description": "Recent dossier summaries.",
        },
        {
            "uri": "phios://observatory/field_libraries/recent",
            "kind": "field_libraries",
            "description": "Recent field library index entries.",
        },
    ]
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "resource_count": len(resources),
            "resources": resources,
            "source": "phios.mcp.resources.observatory",
            "read_only": True,
        }
    )


def read_observatory_dashboard_resource(*, journal_dir: Path | None = None) -> dict[str, object]:
    """Return observatory dashboard model from visualizer helpers."""

    dashboard = build_visual_bloom_dashboard_model(journal_dir=journal_dir)
    sessions = dashboard.get("sessions")
    results = dashboard.get("results")
    summary = {
        "session_count": len(sessions) if isinstance(sessions, list) else 0,
        "result_count": len(results) if isinstance(results, list) else 0,
        "top_level_keys": sorted(dashboard.keys()),
    }
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "summary": summary,
            "dashboard": dashboard,
            "source": "phios.services.visualizer.build_visual_bloom_dashboard_model",
            "read_only": True,
        }
    )


def read_observatory_atlas_gallery_resource(*, journal_dir: Path | None = None) -> dict[str, object]:
    """Return observatory atlas gallery model from visualizer helpers."""

    gallery = build_visual_bloom_atlas_gallery_model(journal_dir=journal_dir)
    entry_count = gallery.get("entry_count", 0)
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "summary": {
                "entry_count": entry_count if isinstance(entry_count, int) else 0,
            },
            "atlas_gallery": gallery,
            "source": "phios.services.visualizer.build_visual_bloom_atlas_gallery_model",
            "read_only": True,
        }
    )


def read_observatory_recent_storyboards_resource(
    *,
    journal_dir: Path | None = None,
    limit: int = _MAX_RECENT,
) -> dict[str, object]:
    """Return recent observatory storyboard summaries."""

    rows = list_visual_bloom_storyboards(journal_dir=journal_dir)
    capped = rows[: max(0, int(limit))]
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "count": len(capped),
            "limit": max(0, int(limit)),
            "storyboards": capped,
            "source": "phios.services.visualizer.list_visual_bloom_storyboards",
            "read_only": True,
        }
    )


def read_observatory_recent_dossiers_resource(
    *,
    journal_dir: Path | None = None,
    limit: int = _MAX_RECENT,
) -> dict[str, object]:
    """Return recent observatory dossier summaries."""

    rows = list_visual_bloom_dossiers(journal_dir=journal_dir)
    capped = rows[: max(0, int(limit))]
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "count": len(capped),
            "limit": max(0, int(limit)),
            "dossiers": capped,
            "source": "phios.services.visualizer.list_visual_bloom_dossiers",
            "read_only": True,
        }
    )


def read_observatory_recent_field_libraries_resource(
    *,
    journal_dir: Path | None = None,
    limit: int = _MAX_RECENT,
) -> dict[str, object]:
    """Return recent field library index entries."""

    rows = build_visual_bloom_field_library_index(journal_dir=journal_dir)
    capped = rows[: max(0, int(limit))]
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "count": len(capped),
            "limit": max(0, int(limit)),
            "field_libraries": capped,
            "source": "phios.services.visualizer.build_visual_bloom_field_library_index",
            "read_only": True,
        }
    )
