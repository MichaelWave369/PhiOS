"""Waybar configuration templates for PhiOS desktop layer."""

from __future__ import annotations

import json

WAYBAR_CONFIG = {
    "layer": "top",
    "position": "top",
    "modules-left": ["custom/phi-logo", "wlr/workspaces"],
    "modules-center": ["custom/phi-tray"],
    "modules-right": ["custom/sovereignty", "network", "memory", "cpu", "clock"],
    "custom/phi-logo": {
        "format": "φ",
        "tooltip": False,
    },
    "custom/phi-tray": {
        "exec": "python -m phios.desktop.phi_tray",
        "interval": 3,
        "return-type": "json",
    },
    "custom/sovereignty": {
        "exec": "python -m phios.desktop.sovereignty_indicator",
        "interval": 5,
        "return-type": "json",
    },
}

WAYBAR_CSS = """
* {
  font-family: Inter, Sans;
  color: #E8EEF5;
}
window#waybar {
  background: #070A0F;
  border-bottom: 1px solid #C9A84C;
}
#custom-phi-tray { color: #C9A84C; }
#custom-phi-logo { color: #2EA8A8; }
#custom-sovereignty { color: #5B4FCF; }
#memory, #cpu, #clock, #network { color: #A9B0C3; }
"""


def render_waybar_config() -> str:
    return json.dumps(WAYBAR_CONFIG, indent=2)
