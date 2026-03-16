"""Resource reader for ``phios://coherence/lt``."""

from __future__ import annotations

from phios.core.lt_engine import LtResultDict, compute_lt
from phios.mcp.schema import with_resource_schema


def read_coherence_lt_resource() -> dict[str, object]:
    """Return current L(t) coherence report.

    Stable JSON shape (minimum fields):
    ``lt``, ``system_lt``, ``blended_lt`` (optional), ``components``,
    ``phb_contribution``.

    Note: ``compute_lt`` returns ``LtResultDict``; we normalize to a plain ``dict``
    for MCP JSON payload consistency and mypy compatibility.
    """

    payload: LtResultDict = compute_lt()
    return with_resource_schema(dict(payload))
