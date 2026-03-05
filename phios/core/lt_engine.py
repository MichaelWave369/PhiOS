"""L(t) coherence engine."""

from __future__ import annotations

import math
import time
from typing import Any

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dep
    psutil = None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def compute_lt() -> dict[str, Any]:
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
        score = _clamp(0.4 * stability + 0.35 * (1.0 - load) + 0.25 * variance)
        return {
            "lt": round(score, 6),
            "components": {
                "A_stability": round(stability, 6),
                "G_load": round(load, 6),
                "C_variance": round(variance, 6),
            },
        }
    except Exception:
        return {
            "lt": 0.5,
            "components": {"A_stability": 0.5, "G_load": 0.5, "C_variance": 0.5},
        }
