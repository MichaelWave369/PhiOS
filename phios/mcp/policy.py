"""Lightweight MCP capability policy helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass


CAP_READ_STATE = "read_state"
CAP_READ_HISTORY = "read_history"
CAP_READ_OBSERVATORY = "read_observatory"
CAP_PROMPT_GUIDANCE = "prompt_guidance"
CAP_PULSE_ONCE = "pulse_once"


@dataclass(frozen=True, slots=True)
class CapabilityDecision:
    allowed: bool
    reason: str
    capability_scope: str
    policy_source: str


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on", "allow", "enabled"}


def resolve_mcp_capabilities() -> tuple[set[str], str]:
    """Resolve allowed MCP capability scopes from lightweight local policy.

    `PHIOS_MCP_CAPABILITIES` can be a comma-separated list, e.g.
    `read_state,read_history,read_observatory,prompt_guidance,pulse_once`.

    Default-safe behavior permits read/prompt scopes and denies pulse mutation scope.
    """

    raw = os.getenv("PHIOS_MCP_CAPABILITIES")
    if raw and raw.strip():
        parsed = {token.strip() for token in raw.split(",") if token.strip()}
        return parsed, "env:PHIOS_MCP_CAPABILITIES"

    return {
        CAP_READ_STATE,
        CAP_READ_HISTORY,
        CAP_READ_OBSERVATORY,
        CAP_PROMPT_GUIDANCE,
    }, "default-safe"


def is_capability_allowed(capability_scope: str) -> CapabilityDecision:
    """Return inspectable capability decision for a single scope."""

    allowed_caps, source = resolve_mcp_capabilities()
    if capability_scope in allowed_caps:
        return CapabilityDecision(
            allowed=True,
            reason=f"Capability '{capability_scope}' is allowed.",
            capability_scope=capability_scope,
            policy_source=source,
        )

    return CapabilityDecision(
        allowed=False,
        reason=f"Capability '{capability_scope}' is not permitted by local MCP policy.",
        capability_scope=capability_scope,
        policy_source=source,
    )


def evaluate_pulse_policy() -> CapabilityDecision:
    """Evaluate if MCP pulse action is allowed.

    Pulse remains explicitly gated by `PHIOS_MCP_ALLOW_PULSE=true`.
    If explicit capability scopes are configured, `pulse_once` must also be present.
    """

    env_value = os.getenv("PHIOS_MCP_ALLOW_PULSE")
    if not _is_truthy(env_value):
        return CapabilityDecision(
            allowed=False,
            reason="Pulse requires PHIOS_MCP_ALLOW_PULSE=true.",
            capability_scope=CAP_PULSE_ONCE,
            policy_source="default-safe",
        )

    scopes_raw = os.getenv("PHIOS_MCP_CAPABILITIES")
    if scopes_raw and scopes_raw.strip():
        cap = is_capability_allowed(CAP_PULSE_ONCE)
        if not cap.allowed:
            return CapabilityDecision(
                allowed=False,
                reason="Pulse denied: capability scope 'pulse_once' missing from PHIOS_MCP_CAPABILITIES.",
                capability_scope=CAP_PULSE_ONCE,
                policy_source=cap.policy_source,
            )
        return CapabilityDecision(
            allowed=True,
            reason="Pulse allowed by explicit capability scope + local policy toggle.",
            capability_scope=CAP_PULSE_ONCE,
            policy_source="env:PHIOS_MCP_ALLOW_PULSE+" + cap.policy_source,
        )

    return CapabilityDecision(
        allowed=True,
        reason="Pulse allowed by local policy toggle.",
        capability_scope=CAP_PULSE_ONCE,
        policy_source="env:PHIOS_MCP_ALLOW_PULSE",
    )


def denied_capability_payload(*, decision: CapabilityDecision, error_code: str) -> dict[str, object]:
    """Build a structured non-throwing denial payload for gated surfaces."""

    return {
        "ok": False,
        "allowed": decision.allowed,
        "reason": decision.reason,
        "capability_scope": decision.capability_scope,
        "policy_source": decision.policy_source,
        "error_code": error_code,
        "error": {
            "code": error_code,
            "message": decision.reason,
        },
    }
