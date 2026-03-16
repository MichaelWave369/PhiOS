"""MCP tool for field-guided cognitive architecture recommendation."""

from __future__ import annotations

from datetime import datetime, timezone

from phios.adapters.phik import PhiKernelCLIAdapter
from phios.mcp.policy import CAP_READ_STATE, denied_capability_payload, is_capability_allowed
from phios.mcp.schema import with_tool_schema
from phios.services.cognitive_arch import build_cognitive_arch_context, recommend_cognitive_architecture
from phios.services.cognitive_atoms import recommend_cognitive_atom_overrides


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_phi_recommend_cognitive_arch(adapter: PhiKernelCLIAdapter) -> dict[str, object]:
    """Return read-only experimental cognitive architecture recommendation."""

    decision = is_capability_allowed(CAP_READ_STATE)
    if not decision.allowed:
        return with_tool_schema(
            denied_capability_payload(decision=decision, error_code="READ_STATE_NOT_PERMITTED")
        )

    context = build_cognitive_arch_context(adapter)
    recommendation = recommend_cognitive_architecture(context)
    atom_recommendation = recommend_cognitive_atom_overrides(adapter)
    return with_tool_schema(
        {
            "ok": True,
            "read_only": True,
            "generated_at": _utc_now_iso(),
            "recommendation": recommendation,
            "atom_recommendation": atom_recommendation,
            "context": context,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "capability_scope": decision.capability_scope,
            "policy_source": decision.policy_source,
        }
    )
