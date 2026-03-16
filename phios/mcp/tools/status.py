"""Implementation for ``phi_status`` MCP tool."""

from __future__ import annotations

from phios.adapters.phik import PhiKernelCLIAdapter
from phios.core.lt_engine import compute_lt
from phios.core.phik_service import build_coherence_report, build_status_report


def run_phi_status(adapter: PhiKernelCLIAdapter) -> dict[str, object]:
    """Return a combined status payload for MCP tool use.

    Stable JSON shape:
    - ``status``: output from ``build_status_report``
    - ``coherence``: output from ``build_coherence_report``
    - ``lt``: output from ``compute_lt``
    """

    return {
        "status": build_status_report(adapter),
        "coherence": build_coherence_report(adapter),
        "lt": compute_lt(),
    }
