"""Implementation for ``phi_pulse_once`` MCP tool."""

from __future__ import annotations

from phios.adapters.phik import PhiKernelCLIAdapter
from phios.core.phik_service import run_pulse_once
from phios.mcp.policy import denied_capability_payload, evaluate_pulse_policy
from phios.mcp.schema import with_tool_schema


def run_phi_pulse_once(
    adapter: PhiKernelCLIAdapter,
    *,
    checkpoint: str | None = None,
    passphrase: str | None = None,
) -> dict[str, object]:
    """Run a single bounded pulse cycle via existing PhiKernel adapter API.

    Capability gating is applied before execution with default-safe deny behavior.
    Stable tool payload always includes policy fields: ``allowed``, ``reason``,
    ``capability_scope``, ``policy_source``.
    """

    decision = evaluate_pulse_policy()
    if not decision.allowed:
        return with_tool_schema(
            denied_capability_payload(decision=decision, error_code="PULSE_NOT_PERMITTED")
        )

    pulse = run_pulse_once(adapter, checkpoint=checkpoint, passphrase=passphrase)
    return with_tool_schema(
        {
            "ok": True,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "capability_scope": decision.capability_scope,
            "policy_source": decision.policy_source,
            "pulse": pulse,
        }
    )
