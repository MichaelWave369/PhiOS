"""Resource reader for ``phios://field/state``."""

from __future__ import annotations

from phios.adapters.phik import PhiKernelCLIAdapter
from phios.core.phik_service import build_coherence_report


def read_field_state_resource(adapter: PhiKernelCLIAdapter) -> dict[str, object]:
    """Return current coherence/field state.

    Stable JSON shape (minimum fields):
    ``C_current``, ``C_star``, ``distance_to_C_star``, ``phi_flow``,
    ``lambda_node``, ``sigma_feedback``, ``fragmentation_score``, ``recommended_action``.

    Additional source fields are preserved when available via ``phik_field``.
    """

    return build_coherence_report(adapter)
