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
        return f"""# PhiOS Wayfire Config
# Sacred geometry workspace map: 3x3 with 3/6/9 coherence anchors

[core]
plugins = grid move resize animate waybar wofi
# custom phi-tray module is integrated through Waybar custom/phi-tray
background_color = {PHIOS_COLORS['deep']}

[decoration]
border_color = {PHIOS_COLORS['gold']}
border_size = 1
gap_size = {self.fibonacci_gaps(0)}

[grid]
# Golden ratio guidance for primary layout: 61.8 / 38.2
primary_split = 61.8
secondary_split = 38.2

[workspaces]
rows = 3
columns = 3
workspace_1 = 1
workspace_2 = 2
workspace_3 = 3  # 3 anchor
workspace_4 = 4
workspace_5 = 5
workspace_6 = 6  # 6 anchor
workspace_7 = 7
workspace_8 = 8
workspace_9 = 9  # 9 anchor

[keybindings]
super_return = phi
super_space = phi launcher
super_l = phi coherence live
super_s = phi sovereign export ./phi_snapshot_toggle.json
super_shift_q = close
super_1 = workspace 1
super_2 = workspace 2
super_3 = workspace 3
super_4 = workspace 4
super_5 = workspace 5
super_6 = workspace 6
super_7 = workspace 7
super_8 = workspace 8
super_9 = workspace 9

[animate]
open_animation = fade scale_center
close_animation = fade scale_center
workspace_switch_animation = smooth_slide
duration = 200
"""

    def generate(self, output_path: str = "~/.config/wayfire.ini") -> str:
        config_path = Path(output_path).expanduser()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        text = self._config_text()
        config_path.write_text(text, encoding="utf-8")
        return str(config_path)
