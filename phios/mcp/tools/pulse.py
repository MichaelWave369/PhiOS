"""Implementation for ``phi_pulse_once`` MCP tool."""

from __future__ import annotations

from phios.adapters.phik import PhiKernelCLIAdapter
from phios.core.phik_service import run_pulse_once


def run_phi_pulse_once(
    adapter: PhiKernelCLIAdapter,
    *,
    checkpoint: str | None = None,
    passphrase: str | None = None,
) -> dict[str, object]:
    """Run a single bounded pulse cycle via existing PhiKernel adapter API.

    Stable JSON shape is passed through from existing pulse response; this preserves
    existing source-of-truth semantics while exposing a single-cycle action only.
    """

    return run_pulse_once(adapter, checkpoint=checkpoint, passphrase=passphrase)
