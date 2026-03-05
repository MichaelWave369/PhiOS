"""Simple render helpers."""

from __future__ import annotations

from phios.display.sparkline import render_bar, render_sparkline, trajectory_arrow


def render_lines(lines: list[str]) -> str:
    return "\n".join(lines)


def render_live_panel(payload: dict[str, object]) -> str:
    score = float(payload.get("lt", 0.0))
    components = payload.get("components", {}) if isinstance(payload.get("components"), dict) else {}
    trajectory = str(payload.get("trajectory", "stable"))
    history = payload.get("history", []) if isinstance(payload.get("history"), list) else []

    a_on = float(components.get("A_stability", score)) if isinstance(components, dict) else score
    g_score = float(components.get("G_load", 0.0)) if isinstance(components, dict) else 0.0
    c_score = float(components.get("C_variance", score)) if isinstance(components, dict) else score
    psi_b = 1.0 - g_score

    lines = [
        "φ PhiOS · Live Coherence Monitor",
        f"L(t): {score:.3f} [{render_bar(score)}]",
        f"Coherence: {score:.3f}",
        f"Boundary: {psi_b:.3f}",
        f"Cadence: {c_score:.3f}",
        f"Sovereignty (A_on): {a_on:.3f}",
        f"Trajectory: {trajectory_arrow(trajectory)} {trajectory}",
        f"Session elapsed: {int(payload.get('elapsed_s', 0))}s",
        f"Next 369 resonance in {int(payload.get('resonance_in', 369))}s",
        "Hotkeys: [q] exit [s] snapshot [r] reset history",
        f"History: {render_sparkline([float(x) for x in history][-9:])} {trajectory_arrow(trajectory)}",
    ]

    if bool(payload.get("resonance_now")):
        lines.append("RESonance moment · 369")

    return "\n".join(lines)
