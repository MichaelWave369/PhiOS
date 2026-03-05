"""Waybar custom module for PhiOS L(t) status."""

from __future__ import annotations

import json
import time

from phios.core.brainc_client import ollama_available
from phios.core.lt_engine import compute_lt
from phios.core.tbrc_bridge import TBRCBridge
from phios.display.sparkline import trajectory_arrow


class PhiTray:
    """Generate tray payloads suitable for Waybar custom JSON modules."""

    def classify(self, score: float) -> str:
        if score >= 0.8:
            return "coherent"
        if score >= 0.5:
            return "degraded"
        return "critical"

    def _trajectory(self, components: dict[str, float]) -> str:
        load = float(components.get("G_load", 0.5))
        variance = float(components.get("C_variance", 0.5))
        if abs(load - variance) > 0.2:
            return "volatile"
        if variance > load:
            return "rising"
        if variance < load:
            return "falling"
        return "stable"

    def payload(self) -> dict[str, object]:
        try:
            lt = compute_lt()
            score = float(lt.get("lt", 0.5))
            components = lt.get("components", {})
            if not isinstance(components, dict):
                components = {"A_stability": 0.5, "G_load": 0.5, "C_variance": 0.5}
            trajectory = self._trajectory(components)
            cls = self.classify(score)
            tbrc_info = "Not connected"
            if TBRCBridge().is_available():
                tbrc_info = "Connected"
            tooltip = "\n".join(
                [
                    f"L(t): {score:.3f} {trajectory_arrow(trajectory)}",
                    f"Coherence: {float(components.get('A_stability', 0.5)):.3f}",
                    f"Boundary: {1.0 - float(components.get('G_load', 0.5)):.3f}",
                    f"Cadence: {float(components.get('C_variance', 0.5)):.3f}",
                    "Sovereignty: ON (placeholder)",
                    "Session: best-effort",
                    f"BrainC: {'Active' if ollama_available() else 'Inactive'}",
                    f"TBRC: {tbrc_info}",
                ]
            )
            return {
                "text": f"φ {score:.3f}",
                "tooltip": tooltip,
                "class": cls,
                "percentage": max(0, min(100, int(round(score * 100)))),
            }
        except Exception:
            return {
                "text": "φ 0.500",
                "tooltip": "L(t): unavailable\nSovereignty: ON (placeholder)",
                "class": "degraded",
                "percentage": 50,
            }


def main() -> int:
    tray = PhiTray()
    try:
        while True:
            print(json.dumps(tray.payload()), flush=True)
            time.sleep(3)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
