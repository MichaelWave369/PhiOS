"""Sovereign launcher integration for PhiOS desktop."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from phios.apps.desktop_catalog import snapshot_desktop_catalog
from phios.core.lt_engine import compute_lt
from phios.desktop.wofi_css import WOFI_CSS


@dataclass(frozen=True)
class LauncherAction:
    """One visible launcher choice bound to one exact argv vector."""

    label: str
    argv: tuple[str, ...]


class PhiLauncher:
    """Generate and launch a Wofi-driven PhiOS launcher."""

    def __init__(
        self,
        *,
        desktop_root: Path | None = None,
        applications_root: Path | None = None,
        install_root: Path | None = None,
    ) -> None:
        self.wofi_dir = Path.home() / ".config" / "wofi"
        self.desktop_root = (
            desktop_root
            if desktop_root is not None
            else Path.home() / ".local" / "share" / "phios" / "desktop-apps"
        )
        self.applications_root = (
            applications_root
            if applications_root is not None
            else Path.home() / ".local" / "share" / "applications"
        )
        self.install_root = (
            install_root
            if install_root is not None
            else Path.home() / ".phios" / "apps" / "installed"
        )

    def generate_wofi_config(self) -> str:
        self.wofi_dir.mkdir(parents=True, exist_ok=True)
        config = self.wofi_dir / "config"
        prompt = self.get_prompt_with_lt()
        config.write_text(
            (
                f"show=drun\nwidth=700\nheight=480\nprompt={prompt}\n"
                "allow_images=false\n"
            ),
            encoding="utf-8",
        )
        return str(config)

    def generate_wofi_css(self) -> str:
        self.wofi_dir.mkdir(parents=True, exist_ok=True)
        css = self.wofi_dir / "style.css"
        css.write_text(WOFI_CSS, encoding="utf-8")
        return str(css)

    def generate_phi_actions(self) -> list[LauncherAction]:
        return [
            LauncherAction("phi ask", ("phi", "ask")),
            LauncherAction("phi status", ("phi", "status")),
            LauncherAction("phi coherence", ("phi", "coherence")),
            LauncherAction("phi tbrc status", ("phi", "tbrc", "status")),
            LauncherAction(
                "phi sovereign export ./phi_snapshot.json",
                ("phi", "sovereign", "export", "./phi_snapshot.json"),
            ),
            LauncherAction(
                "phi sovereign verify ./phi_snapshot.json",
                ("phi", "sovereign", "verify", "./phi_snapshot.json"),
            ),
            LauncherAction(
                "phi sovereign compare ./a.json ./b.json",
                ("phi", "sovereign", "compare", "./a.json", "./b.json"),
            ),
            LauncherAction(
                "phi wallpaper generate",
                ("phi", "wallpaper", "generate"),
            ),
            LauncherAction("phi notify status", ("phi", "notify", "status")),
        ]

    def generate_phi_entries(self) -> list[str]:
        """Backward-compatible visible labels for built-in Phi actions."""
        return [action.label for action in self.generate_phi_actions()]

    def generate_governed_app_actions(self) -> list[LauncherAction]:
        try:
            snapshot = snapshot_desktop_catalog(
                desktop_root=self.desktop_root,
                applications_root=self.applications_root,
                install_root=self.install_root,
            )
        except (OSError, ValueError):
            return []

        actions: list[LauncherAction] = []
        for item in snapshot.items:
            if (
                item.status != "ready"
                or item.app_id is None
                or item.app_version is None
                or item.desktop_name is None
            ):
                continue
            label = f"{item.desktop_name} · {item.app_id} {item.app_version}"
            actions.append(
                LauncherAction(
                    label=label,
                    argv=("phi-app", "launch-desktop-bundle", item.bundle_path),
                )
            )
        actions.sort(key=lambda action: action.label.casefold())
        return actions

    def generate_actions(self) -> list[LauncherAction]:
        return self.generate_phi_actions() + self.generate_governed_app_actions()

    def get_prompt_with_lt(self) -> str:
        score = float(compute_lt().get("lt", 0.5))
        return f"φ {score:.3f} ❯"

    def launch(self) -> None:
        self.generate_wofi_config()
        self.generate_wofi_css()
        actions = self.generate_actions()
        action_by_label = {action.label: action for action in actions}

        if shutil.which("wofi"):
            try:
                menu = "\n".join(action.label for action in actions)
                proc = subprocess.run(
                    ["wofi", "--show", "dmenu", "--prompt", self.get_prompt_with_lt()],
                    input=menu,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                selection = proc.stdout.strip()
                action = action_by_label.get(selection)
                if action is not None:
                    subprocess.run(list(action.argv), check=False)
                return
            except OSError:
                pass

        print("Wofi unavailable. Use CLI commands directly:")
        for action in actions:
            print(f" - {action.label}")
        print("Tip: run phi help for the full command set.")
