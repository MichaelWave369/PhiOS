"""Session-oriented MCP resources (Phase 7, read-only)."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.adapters.phik import PhiKernelCLIAdapter
from phios.core.session_layer import build_session_checkin_report, build_session_start_report
from phios.mcp.schema import with_resource_schema
from phios.services.visualizer import list_visual_bloom_sessions


_MAX_RECENT = 20


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_sessions_current_resource(adapter: PhiKernelCLIAdapter) -> dict[str, object]:
    """Return current session-oriented state from existing session-layer reports."""

    start = build_session_start_report(adapter)
    checkin = build_session_checkin_report(adapter)
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "summary": {
                "session_state": checkin.get("session_state", "unknown"),
                "recommended_action": checkin.get("recommended_action", "unknown"),
                "next_step": checkin.get("next_step", ""),
            },
            "session_start": start,
            "session_checkin": checkin,
            "source": "phios.core.session_layer",
            "read_only": True,
        }
    )


def read_sessions_recent_checkins_resource(*, limit: int = _MAX_RECENT) -> dict[str, object]:
    """Return recent local session rows from visual bloom journal summaries."""

    rows = list_visual_bloom_sessions()[: max(0, int(limit))]
    normalized = [
        {
            "session_id": row.get("session_id", ""),
            "created_at": row.get("created_at", ""),
            "updated_at": row.get("updated_at", ""),
            "label": row.get("label", ""),
            "collection": row.get("collection", ""),
            "mode": row.get("mode", "unknown"),
            "latest_timestamp": row.get("latest_timestamp", ""),
        }
        for row in rows
        if isinstance(row, dict)
    ]
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "count": len(normalized),
            "limit": max(0, int(limit)),
            "checkins": normalized,
            "source": "phios.services.visualizer.list_visual_bloom_sessions",
            "read_only": True,
        }
    )


def read_sessions_recent_reports_resource(*, limit: int = _MAX_RECENT) -> dict[str, object]:
    """Return recent session report summaries from the same local session list."""

    rows = list_visual_bloom_sessions()[: max(0, int(limit))]
    reports = [
        {
            "session_id": row.get("session_id", ""),
            "mode": row.get("mode", "unknown"),
            "preset": row.get("preset", "none"),
            "lens": row.get("lens", "none"),
            "audio": row.get("audio", "off"),
        }
        for row in rows
        if isinstance(row, dict)
    ]
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "count": len(reports),
            "limit": max(0, int(limit)),
            "reports": reports,
            "source": "phios.services.visualizer.list_visual_bloom_sessions",
            "read_only": True,
        }
    )
