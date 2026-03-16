"""Read-only resource for current cognitive atom override recommendation."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.adapters.phik import PhiKernelCLIAdapter
from phios.mcp.schema import with_resource_schema
from phios.services.cognitive_atoms import (
    build_sector_atom_context,
    recommend_cognitive_atom_overrides,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_cognition_atoms_resource(adapter: PhiKernelCLIAdapter) -> dict[str, object]:
    context = build_sector_atom_context(adapter)
    recommendation = recommend_cognitive_atom_overrides(adapter)
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "read_only": True,
            "resource_kind": "cognitive_atom_recommendation",
            "recommendation": recommendation,
            "context": context,
        }
    )
