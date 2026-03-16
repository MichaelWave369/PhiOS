"""Read-only MCP resources for adversarial architecture reviews."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.mcp.schema import with_resource_schema
from phios.services.review_gate import get_review_panel_resource, list_recent_reviews


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_reviews_recent_resource(limit: int = 10) -> dict[str, object]:
    payload = list_recent_reviews(limit=limit)
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "read_only": True,
            "resource_kind": "reviews_recent",
            **payload,
        }
    )


def read_review_panel_resource(panel_id: str, pr_number: int | None = None) -> dict[str, object]:
    payload = get_review_panel_resource(panel_id, pr_number=pr_number)
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "read_only": True,
            "resource_kind": "review_panel",
            **payload,
        }
    )
