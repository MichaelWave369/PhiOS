"""Wayfire configuration generator for PhiOS desktop layer."""

from __future__ import annotations

from pathlib import Path

PHI = 1.6180339887
FIBONACCI = [8, 13, 21, 34, 55, 89]
PHIOS_COLORS = {
    "deep": "#070A0F",
    "deep_2": "#0D1320",
    "gold": "#C9A84C",
    "teal": "#2EA8A8",
    "purple": "#5B4FCF",
    "silver": "#A9B0C3",
    "text": "#E8EEF5",
}


class WayfireConfigGenerator:
    """Generate a PhiOS-aligned wayfire.ini configuration."""

    def golden_split(self, total: int) -> tuple[int, int]:
        primary = round(total * 0.618)
        secondary = total - primary
        return primary, secondary

    def fibonacci_gaps(self, level: int) -> int:
        if level < 0:
            return FIBONACCI[0]
        if level >= len(FIBONACCI):
            return FIBONACCI[-1]
        return FIBONACCI[level]

    def _config_text(self) -> str:
        return """# PhiOS Wayfire 0.11 configuration
[core]
plugins = autostart command decoration move resize place grid vswitch wm-actions
vwidth = 3
vheight = 3
close_top_view = <super> KEY_Q | <alt> KEY_F4

[autostart]
autostart_wf_shell = false
phios = /usr/lib/phishell/session-ready

[command]
binding_terminal = <super> KEY_ENTER
command_terminal = foot phi
binding_launcher = <super> KEY_SPACE
command_launcher = wofi --show drun
binding_coherence = <super> KEY_L
command_coherence = foot phi coherence live
binding_shell = <super> KEY_P
command_shell = phios-open-shell

[move]
activate = <super> BTN_LEFT

[resize]
activate = <super> BTN_RIGHT
"""

    def generate(self, output_path: str = "~/.config/wayfire.ini") -> str:
        config_path = Path(output_path).expanduser()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        text = self._config_text()
        config_path.write_text(text, encoding="utf-8")
        return str(config_path)
