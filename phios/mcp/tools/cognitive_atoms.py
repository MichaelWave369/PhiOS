"""MCP tool for field-guided cognitive atom override recommendations."""

from __future__ import annotations

from phios.adapters.phik import PhiKernelCLIAdapter
from phios.mcp.schema import with_tool_schema
from phios.services.cognitive_atoms import (
    build_sector_atom_context,
    recommend_cognitive_atom_overrides,
)


def run_phi_recommend_cognitive_atoms(adapter: PhiKernelCLIAdapter) -> dict[str, object]:
    context = build_sector_atom_context(adapter)
    recommendation = recommend_cognitive_atom_overrides(adapter)
    return with_tool_schema(
        {
            "ok": True,
            "read_only": True,
            "experimental": True,
            "recommendation": recommendation,
            "context": context,
        }
    )
