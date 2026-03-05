"""L(t) coherence engine."""

from __future__ import annotations

import math
import time
from typing import TypedDict, cast

try:
    import psutil
except ImportError:  # pragma: no cover - optional dep
    psutil = None


class LtComponents(TypedDict):
    A_stability: float
    G_load: float
    C_variance: float


class LtResultDict(TypedDict, total=False):
    lt: float
    system_lt: float
    blended_lt: float
    tbrc_session_lt: float
    phb_contribution: float
    components: LtComponents


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _compute_system_components() -> tuple[float, float, float]:
    if psutil is not None:
        cpu = psutil.cpu_percent(interval=None) / 100.0
        mem = psutil.virtual_memory().percent / 100.0
        disk = psutil.disk_usage("/").percent / 100.0
        load = _clamp((cpu + mem + disk) / 3.0)
        stability = _clamp(1.0 - abs(cpu - mem))
        variance = _clamp(1.0 - abs(mem - disk))
        return stability, load, variance

    now = int(time.time())
    phase = math.sin(now / 10.0)
    load = _clamp((phase + 1.0) / 2.0)
    stability = _clamp(0.75 + 0.2 * math.cos(now / 15.0))
    variance = _clamp(0.8 + 0.1 * math.sin(now / 20.0))
    return stability, load, variance


def compute_lt() -> LtResultDict:
    """Compute coherence and enrich with optional TBRC data."""
    try:
        stability, load, variance = _compute_system_components()
        base_psi_b = _clamp(stability)

        phb_contribution = 0.0
        tbrc_session_lt: float | None = None

        try:
            from phios.core.tbrc_bridge import TBRCBridge

            bridge = TBRCBridge()
            phb_contribution = max(0.0, bridge.get_phb_lt_contribution())
            tbrc_session_lt = bridge.get_session_lt()
        except Exception:
            phb_contribution = 0.0
            tbrc_session_lt = None

        enriched_psi_b = _clamp(base_psi_b + phb_contribution)
        system_lt = _clamp(0.4 * enriched_psi_b + 0.35 * (1.0 - load) + 0.25 * variance)

        result: LtResultDict = {
            "lt": round(system_lt, 6),
            "system_lt": round(system_lt, 6),
            "phb_contribution": round(phb_contribution, 6),
            "components": {
                "A_stability": round(enriched_psi_b, 6),
                "G_load": round(load, 6),
                "C_variance": round(variance, 6),
            },
        }

        if tbrc_session_lt is not None:
            blended = _clamp(0.7 * system_lt + 0.3 * tbrc_session_lt)
            final_lt = max(system_lt, blended)
            result["tbrc_session_lt"] = round(float(tbrc_session_lt), 6)
            result["blended_lt"] = round(blended, 6)
            result["lt"] = round(final_lt, 6)

        return result
    except (OSError, ValueError, RuntimeError):
        return {
            "lt": 0.5,
            "system_lt": 0.5,
            "components": {"A_stability": 0.5, "G_load": 0.5, "C_variance": 0.5},
            "phb_contribution": 0.0,
        }
    except Exception:
        fallback = cast(
            LtResultDict,
            {
                "lt": 0.5,
                "system_lt": 0.5,
                "components": {"A_stability": 0.5, "G_load": 0.5, "C_variance": 0.5},
                "phb_contribution": 0.0,
            },
        )
        return fallback
