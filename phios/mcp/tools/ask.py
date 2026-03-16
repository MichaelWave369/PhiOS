"""Implementation for ``phi_ask`` MCP tool."""

from __future__ import annotations

from phios.adapters.phik import PhiKernelCLIAdapter
from phios.core.phik_service import build_ask_report


def run_phi_ask(adapter: PhiKernelCLIAdapter, prompt: str) -> dict[str, object]:
    """Run a grounded ask request.

    Stable JSON shape includes:
    ``coach``, ``field_action``, ``body``, ``next_actions``, ``safety_posture``.
    Additional raw fields are preserved in ``phik_ask``.
    """

    normalized_prompt = prompt.strip()
    if not normalized_prompt:
        raise ValueError("prompt must be a non-empty string")
    return build_ask_report(adapter, normalized_prompt)
