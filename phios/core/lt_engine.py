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


class LtResultDict(TypedDict):
    lt: float
    components: LtComponents


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def compute_lt() -> LtResultDict:
    """Compute a quick coherence score in [0,1] with components."""
    try:
        if psutil is not None:
            cpu = psutil.cpu_percent(interval=None) / 100.0
            mem = psutil.virtual_memory().percent / 100.0
            disk = psutil.disk_usage("/").percent / 100.0
            load = _clamp((cpu + mem + disk) / 3.0)
            stability = _clamp(1.0 - abs(cpu - mem))
            variance = _clamp(1.0 - abs(mem - disk))
        else:
            phase = math.sin(int(time.time()) / 10.0)
            load = _clamp((phase + 1.0) / 2.0)
            stability = _clamp(0.75 + 0.2 * math.cos(int(time.time()) / 15.0))
            variance = _clamp(0.8 + 0.1 * math.sin(int(time.time()) / 20.0))

        components: LtComponents = {
            "A_stability": round(stability, 6),
            "G_load": round(load, 6),
            "C_variance": round(variance, 6),
        }
        return {"lt": round(_clamp(0.4 * stability + 0.35 * (1.0 - load) + 0.25 * variance), 6), "components": components}
    except (OSError, ValueError, RuntimeError):
        return {"lt": 0.5, "components": {"A_stability": 0.5, "G_load": 0.5, "C_variance": 0.5}}
    except Exception:
        fallback = cast(LtResultDict, {"lt": 0.5, "components": {"A_stability": 0.5, "G_load": 0.5, "C_variance": 0.5}})
        return fallback
