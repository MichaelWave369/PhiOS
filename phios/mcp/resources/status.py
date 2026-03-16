"""Resource reader for ``phios://system/status``."""

from __future__ import annotations

from phios.adapters.phik import PhiKernelCLIAdapter
from phios.core.phik_service import build_status_report
from phios.mcp.schema import with_resource_schema


def read_system_status_resource(adapter: PhiKernelCLIAdapter) -> dict[str, object]:
    """Return current PhiOS/PhiKernel status composition.

    Stable JSON shape (minimum fields):
    ``anchor_verification_state``, ``heart_state``, ``field_action``,
    ``field_drift_band``, ``capsule_count``.

    Additional source fields are preserved under ``phik_status``.
    """

    return with_resource_schema(build_status_report(adapter))
