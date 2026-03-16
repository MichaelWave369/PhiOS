"""Lightweight MCP capability policy helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PulsePolicyDecision:
    allowed: bool
    reason: str
    capability_scope: str
    policy_source: str


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on", "allow", "enabled"}


def evaluate_pulse_policy() -> PulsePolicyDecision:
    """Evaluate if MCP pulse action is allowed.

    Default is safe/disabled unless explicit local opt-in is provided.
    """

    env_value = os.getenv("PHIOS_MCP_ALLOW_PULSE")
    if _is_truthy(env_value):
        return PulsePolicyDecision(
            allowed=True,
            reason="Pulse allowed by local policy toggle.",
            capability_scope="mcp:phi_pulse_once",
            policy_source="env:PHIOS_MCP_ALLOW_PULSE",
        )

    return PulsePolicyDecision(
        allowed=False,
        reason="Pulse disabled by default-safe MCP policy. Set PHIOS_MCP_ALLOW_PULSE=true to allow.",
        capability_scope="mcp:phi_pulse_once",
        policy_source="default-safe",
    )
