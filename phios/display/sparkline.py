"""Sparkline and bar display helpers."""

from __future__ import annotations

BLOCKS = "▁▂▃▄▅▆▇█"


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def render_sparkline(history: list[float]) -> str:
    """Render a compact sparkline from values in [0,1]."""
    try:
        if not history:
            return ""
        chars: list[str] = []
        for value in history:
            clamped = _clamp(value)
            idx = min(len(BLOCKS) - 1, int(round(clamped * (len(BLOCKS) - 1))))
            chars.append(BLOCKS[idx])
        return "".join(chars)
    except Exception:
        return ""


def render_bar(value: float, width: int = 20) -> str:
    try:
        width = max(1, int(width))
        clamped = _clamp(value)
        filled = int(round(clamped * width))
        return "█" * filled + "░" * (width - filled)
    except Exception:
        return "░" * max(1, int(width) if isinstance(width, int) else 20)


def trajectory_arrow(trajectory: str) -> str:
    mapping = {
        "rising": "↗",
        "falling": "↘",
        "stable": "→",
        "volatile": "↕",
    }
    return mapping.get(str(trajectory).lower(), "→")
