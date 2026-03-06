"""Sovereign launcher integration for PhiOS desktop."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from phios.core.lt_engine import compute_lt
from phios.desktop.wofi_css import WOFI_CSS


class PhiLauncher:
    """Generate and launch a Wofi-driven PhiOS launcher."""

    def __init__(self) -> None:
        self.wofi_dir = Path.home() / ".config" / "wofi"

    def generate_wofi_config(self) -> str:
        self.wofi_dir.mkdir(parents=True, exist_ok=True)
        config = self.wofi_dir / "config"
        prompt = self.get_prompt_with_lt()
        config.write_text(
            f"show=drun\nwidth=700\nheight=480\nprompt={prompt}\nallow_images=false\n", encoding="utf-8"
        )
        return str(config)

    def generate_wofi_css(self) -> str:
        self.wofi_dir.mkdir(parents=True, exist_ok=True)
        css = self.wofi_dir / "style.css"
        css.write_text(WOFI_CSS, encoding="utf-8")
        return str(css)

    def generate_phi_entries(self) -> list[str]:
        return [
            "phi ask",
            "phi status",
            "phi coherence",
            "phi tbrc status",
            "phi sovereign export ./phi_snapshot.json",
            "phi sovereign verify ./phi_snapshot.json",
            "phi sovereign compare ./a.json ./b.json",
            "phi wallpaper generate",
            "phi notify status",
        ]

    def get_prompt_with_lt(self) -> str:
        score = float(compute_lt().get("lt", 0.5))
        return f"φ {score:.3f} ❯"

    def launch(self) -> None:
        self.generate_wofi_config()
        self.generate_wofi_css()
        entries = self.generate_phi_entries()

        if shutil.which("wofi"):
            try:
                menu = "\n".join(entries)
                proc = subprocess.run(
                    ["wofi", "--show", "dmenu", "--prompt", self.get_prompt_with_lt()],
                    input=menu,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                selection = proc.stdout.strip()
                if selection:
                    subprocess.run(selection.split(), check=False)
                return
            except OSError:
                pass

        print("Wofi unavailable. Use CLI commands directly:")
        for entry in entries:
            print(f" - {entry}")
        print("Tip: run `phi help` for the full command set.")
