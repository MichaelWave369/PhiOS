"""History/snapshot resources for MCP Phase 2."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from phios.adapters.phik import PhiKernelCLIAdapter
from phios.mcp.schema import with_resource_schema
from phios.services.visualizer import (
    VisualizerError,
    list_visual_bloom_sessions,
    load_visual_bloom_session,
)

_MAX_RECENT = 20


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_recent_capsules_resource(
    adapter: PhiKernelCLIAdapter,
    *,
    limit: int = _MAX_RECENT,
) -> dict[str, object]:
    """Return recent capsule list from PhiKernel-backed adapter data.

    Stable JSON shape:
    - ``capsules``: list of recent capsules (if present)
    - ``count``: number of returned capsules
    - ``limit``: applied cap
    - ``generated_at``: UTC ISO timestamp
    """

    raw = adapter.capsule_list()
    capsule_items = raw.get("capsules", []) if isinstance(raw, dict) else []
    capsules = capsule_items if isinstance(capsule_items, list) else []
    capped = capsules[: max(0, int(limit))]
    return with_resource_schema(
        {
            "capsules": capped,
            "count": len(capped),
            "limit": max(0, int(limit)),
            "generated_at": _utc_now_iso(),
            "source": "phik.capsule_list",
            "raw": raw,
        }
    )


def read_recent_sessions_resource(
    *,
    journal_dir: Path | None = None,
    limit: int = _MAX_RECENT,
) -> dict[str, object]:
    """Return recent local visual bloom session summaries when available."""

    sessions = list_visual_bloom_sessions(journal_dir=journal_dir)
    capped = sessions[: max(0, int(limit))]
    return with_resource_schema(
        {
            "sessions": capped,
            "count": len(capped),
            "limit": max(0, int(limit)),
            "generated_at": _utc_now_iso(),
            "source": "phios.services.visualizer.list_visual_bloom_sessions",
        }
    )


def read_recent_field_snapshots_resource(
    *,
    journal_dir: Path | None = None,
    limit: int = _MAX_RECENT,
) -> dict[str, object]:
    """Return recent field-like snapshots grounded in saved local session states."""

    snapshots: list[dict[str, object]] = []
    sessions = list_visual_bloom_sessions(journal_dir=journal_dir)[: max(0, int(limit))]

    for session in sessions:
        session_id = str(session.get("session_id", ""))
        if not session_id:
            continue
        try:
            doc = load_visual_bloom_session(session_id, journal_dir=journal_dir)
        except VisualizerError:
            continue

        states = doc.get("states")
        if not isinstance(states, list) or not states:
            continue
        latest = states[-1]
        if not isinstance(latest, dict):
            continue

        snapshots.append(
            {
                "session_id": session_id,
                "session_label": doc.get("label", ""),
                "state_index": len(states) - 1,
                "state_timestamp": latest.get("stateTimestamp", ""),
                "coherenceC": latest.get("coherenceC"),
                "driftBand": latest.get("driftBand"),
                "mode": doc.get("mode", "unknown"),
            }
        )

    return with_resource_schema(
        {
            "field_snapshots": snapshots,
            "count": len(snapshots),
            "limit": max(0, int(limit)),
            "generated_at": _utc_now_iso(),
            "source": "visual_bloom_journal",
        }
    )
