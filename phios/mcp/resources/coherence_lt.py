"""Resource reader for ``phios://coherence/lt``."""

from __future__ import annotations

from phios.core.lt_engine import compute_lt


def read_coherence_lt_resource() -> dict[str, object]:
    """Return current L(t) coherence report.

    Stable JSON shape (minimum fields):
    ``lt``, ``system_lt``, ``blended_lt`` (optional), ``components``,
    ``phb_contribution``.
    """

    return compute_lt()
