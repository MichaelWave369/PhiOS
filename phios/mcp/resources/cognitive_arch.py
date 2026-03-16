"""Read-only resource for current field-guided cognitive architecture recommendation."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.adapters.phik import PhiKernelCLIAdapter
from phios.mcp.schema import with_resource_schema
from phios.services.cognitive_arch import build_cognitive_arch_context, recommend_cognitive_architecture
from phios.services.cognitive_atoms import recommend_cognitive_atom_overrides


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_cognition_recommendation_resource(adapter: PhiKernelCLIAdapter) -> dict[str, object]:
    context = build_cognitive_arch_context(adapter)
    recommendation = recommend_cognitive_architecture(context)
    atom_recommendation = recommend_cognitive_atom_overrides(adapter)
    return with_resource_schema(
        {
            "generated_at": _utc_now_iso(),
            "read_only": True,
            "resource_kind": "cognitive_arch_recommendation",
            "recommendation": recommendation,
            "atom_recommendation": atom_recommendation,
            "context": context,
        }
    )
