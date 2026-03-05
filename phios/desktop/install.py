"""Desktop layer installer for Wayfire + Waybar PhiOS configuration."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from phios.desktop.waybar_config import WAYBAR_CSS, render_waybar_config
from phios.desktop.wayfire_config import WayfireConfigGenerator

PACKAGES = {
    "apt": ["wayfire", "waybar", "wofi", "wl-clipboard", "fonts-dejavu"],
    "pacman": ["wayfire", "waybar", "wofi", "wl-clipboard", "ttf-dejavu"],
    "dnf": ["wayfire", "waybar", "wofi", "wl-clipboard", "dejavu-sans-fonts"],
}


class PhiDesktopInstaller:
    """Install and manage PhiOS desktop configuration files."""

    def __init__(self) -> None:
        self.home = Path.home()
        self.config_dir = self.home / ".config"
        self.wayfire_ini = self.config_dir / "wayfire.ini"
        self.waybar_dir = self.config_dir / "waybar"

    def detect_package_manager(self) -> str:
        for mgr in ("apt", "pacman", "dnf"):
            if shutil.which(mgr):
                return mgr
        return "unknown"

    def install_packages(self, pkg_manager: str) -> bool:
        if pkg_manager not in PACKAGES:
            return False
        return True

    def backup_existing_configs(self) -> list[str]:
        backups: list[str] = []
        if self.wayfire_ini.exists():
            backup = self.config_dir / "wayfire.ini.phi_backup"
            if backup.exists():
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup = self.config_dir / f"wayfire.ini.phi_backup.{stamp}"
            shutil.copy2(self.wayfire_ini, backup)
            backups.append(str(backup))
        return backups

    def apply_phios_config(self) -> list[str]:
        written: list[str] = []
        generator = WayfireConfigGenerator()
        written.append(generator.generate(str(self.wayfire_ini)))

        self.waybar_dir.mkdir(parents=True, exist_ok=True)
        cfg = self.waybar_dir / "config.jsonc"
        css = self.waybar_dir / "style.css"
        cfg.write_text(render_waybar_config(), encoding="utf-8")
        css.write_text(WAYBAR_CSS, encoding="utf-8")
        written.extend([str(cfg), str(css)])
        return written

    def install(self, dry_run: bool = True) -> dict[str, object]:
        pkg = self.detect_package_manager()
        report: dict[str, object] = {
            "detected_pkg_mgr": pkg,
            "packages_to_install": PACKAGES.get(pkg, []),
            "would_write_files": [str(self.wayfire_ini), str(self.waybar_dir / "config.jsonc"), str(self.waybar_dir / "style.css")],
            "backups_made": [],
            "success": True,
            "warnings": [],
        }
        if dry_run:
            return report

        backups = self.backup_existing_configs()
        report["backups_made"] = backups
        self.install_packages(pkg)
        self.apply_phios_config()
        return report
