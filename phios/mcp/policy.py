"""Lightweight MCP capability policy helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass


CAP_READ_STATE = "read_state"
CAP_READ_HISTORY = "read_history"
CAP_READ_OBSERVATORY = "read_observatory"
CAP_PROMPT_GUIDANCE = "prompt_guidance"
CAP_PULSE_ONCE = "pulse_once"
CAP_AGENT_DISPATCH = "agent_dispatch"
CAP_AGENT_KILL = "agent_kill"

ALL_CAPABILITIES = {
    CAP_READ_STATE,
    CAP_READ_HISTORY,
    CAP_READ_OBSERVATORY,
    CAP_PROMPT_GUIDANCE,
    CAP_PULSE_ONCE,
    CAP_AGENT_DISPATCH,
    CAP_AGENT_KILL,
}

PROFILE_READ_ONLY = "read_only"
PROFILE_OBSERVER = "observer"
PROFILE_OPERATOR = "operator"
PROFILE_DEVELOPER = "developer"

PROFILE_CAPABILITY_PRESETS: dict[str, set[str]] = {
    PROFILE_READ_ONLY: {CAP_READ_STATE, CAP_READ_HISTORY, CAP_READ_OBSERVATORY},
    PROFILE_OBSERVER: {CAP_READ_STATE, CAP_READ_HISTORY, CAP_READ_OBSERVATORY, CAP_PROMPT_GUIDANCE},
    PROFILE_OPERATOR: {CAP_READ_STATE, CAP_READ_HISTORY, CAP_READ_OBSERVATORY, CAP_PROMPT_GUIDANCE, CAP_PULSE_ONCE, CAP_AGENT_DISPATCH, CAP_AGENT_KILL},
    PROFILE_DEVELOPER: {CAP_READ_STATE, CAP_READ_HISTORY, CAP_READ_OBSERVATORY, CAP_PROMPT_GUIDANCE, CAP_PULSE_ONCE, CAP_AGENT_DISPATCH, CAP_AGENT_KILL},
}


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


def resolve_mcp_profile() -> str | None:
    """Resolve optional profile name from local config."""

    raw = os.getenv("PHIOS_MCP_PROFILE")
    if not raw:
        return None
    profile = raw.strip().lower()
    return profile if profile in PROFILE_CAPABILITY_PRESETS else None


def list_mcp_profiles() -> list[str]:
    """List supported lightweight MCP profile names."""

    return sorted(PROFILE_CAPABILITY_PRESETS.keys())


def resolve_profile_capabilities(profile: str | None) -> set[str]:
    """Resolve capabilities from an optional profile preset."""

    if not profile:
        return set()
    return set(PROFILE_CAPABILITY_PRESETS.get(profile, set()))


def resolve_mcp_capabilities() -> tuple[set[str], str]:
    """Resolve allowed MCP capability scopes from lightweight local policy.

    Precedence:
    1) explicit `PHIOS_MCP_CAPABILITIES` (comma-separated)
    2) optional profile preset via `PHIOS_MCP_PROFILE`
    3) default-safe read/prompt set
    """

    raw = os.getenv("PHIOS_MCP_CAPABILITIES")
    if raw and raw.strip():
        parsed = {token.strip() for token in raw.split(",") if token.strip()}
        return parsed, "env:PHIOS_MCP_CAPABILITIES"

    profile = resolve_mcp_profile()
    if profile:
        return resolve_profile_capabilities(profile), f"env:PHIOS_MCP_PROFILE:{profile}"

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
    If explicit capability scopes/profile are configured, `pulse_once` must also be present.
    """

    env_value = os.getenv("PHIOS_MCP_ALLOW_PULSE")
    if not _is_truthy(env_value):
        return CapabilityDecision(
            allowed=False,
            reason="Pulse requires PHIOS_MCP_ALLOW_PULSE=true.",
            capability_scope=CAP_PULSE_ONCE,
            policy_source="default-safe",
        )

    cap = is_capability_allowed(CAP_PULSE_ONCE)
    if not cap.allowed:
        return CapabilityDecision(
            allowed=False,
            reason="Pulse denied: capability scope 'pulse_once' is not enabled.",
            capability_scope=CAP_PULSE_ONCE,
            policy_source=cap.policy_source,
        )

    return CapabilityDecision(
        allowed=True,
        reason="Pulse allowed by capability scope + local policy toggle.",
        capability_scope=CAP_PULSE_ONCE,
        policy_source="env:PHIOS_MCP_ALLOW_PULSE+" + cap.policy_source,
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
