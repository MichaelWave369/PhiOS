from __future__ import annotations

import json
import math
import re
from pathlib import Path

from phios.desktop.install import PACKAGES, PhiDesktopInstaller
from phios.desktop.phi_tray import PhiTray
from phios.desktop.sovereignty_indicator import indicator_payload
from phios.desktop.wallpaper import PHI, SacredGeometryWallpaper
from phios.desktop.waybar_config import WAYBAR_CONFIG, WAYBAR_CSS
from phios.desktop.wayfire_config import PHIOS_COLORS, WayfireConfigGenerator
from phios.shell.phi_router import route_command


def test_wayfire_config_generates_without_error(tmp_path):
    path = tmp_path / "wayfire.ini"
    out = WayfireConfigGenerator().generate(str(path))
    assert Path(out).exists()


def test_golden_split_sums_to_total():
    a, b = WayfireConfigGenerator().golden_split(1000)
    assert a + b == 1000


def test_golden_split_ratio_is_phi():
    a, b = WayfireConfigGenerator().golden_split(10000)
    ratio = a / b
    assert abs(ratio - 1.6180339887) < 0.001


def test_fibonacci_gaps_sequence_correct():
    gen = WayfireConfigGenerator()
    assert gen.fibonacci_gaps(0) == 8
    assert gen.fibonacci_gaps(1) == 13


def test_color_palette_all_hex_valid():
    for value in PHIOS_COLORS.values():
        assert re.match(r"^#[0-9A-Fa-f]{6}$", value)


def test_wayfire_config_contains_phi_keybindings(tmp_path):
    p = Path(WayfireConfigGenerator().generate(str(tmp_path / "wayfire.ini"))).read_text(encoding="utf-8")
    assert "super_return = phi" in p
    assert "super_l = phi coherence live" in p


def test_wayfire_config_contains_3x3_workspaces(tmp_path):
    p = Path(WayfireConfigGenerator().generate(str(tmp_path / "wayfire.ini"))).read_text(encoding="utf-8")
    assert "rows = 3" in p
    assert "columns = 3" in p
    assert "workspace_9 = 9" in p


def test_installer_detects_package_manager(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/apt" if x == "apt" else None)
    assert PhiDesktopInstaller().detect_package_manager() == "apt"


def test_installer_dry_run_by_default():
    report = PhiDesktopInstaller().install()
    assert report["success"] is True
    assert isinstance(report["packages_to_install"], list)


def test_installer_backs_up_existing_config(tmp_path, monkeypatch):
    installer = PhiDesktopInstaller()
    monkeypatch.setattr(installer, "home", tmp_path)
    installer.config_dir = tmp_path / ".config"
    installer.wayfire_ini = installer.config_dir / "wayfire.ini"
    installer.waybar_dir = installer.config_dir / "waybar"
    installer.config_dir.mkdir(parents=True, exist_ok=True)
    installer.wayfire_ini.write_text("old", encoding="utf-8")
    backups = installer.backup_existing_configs()
    assert backups
    assert Path(backups[0]).exists()


def test_installer_report_schema_correct():
    report = PhiDesktopInstaller().install(dry_run=True)
    for k in ["detected_pkg_mgr", "packages_to_install", "would_write_files", "backups_made", "success", "warnings"]:
        assert k in report


def test_phi_desktop_status_degrades_without_wayfire(monkeypatch, tmp_path):
    installer = PhiDesktopInstaller()
    monkeypatch.setattr("phios.shell.phi_commands.PhiDesktopInstaller", lambda: installer)
    monkeypatch.setattr(installer, "wayfire_ini", tmp_path / "missing.ini")
    monkeypatch.setattr(installer, "waybar_dir", tmp_path / "waybar")
    out, code = route_command(["desktop", "status"])
    assert code == 0
    data = json.loads(out)
    assert data["installed"] is False


def test_phi_tray_outputs_valid_json():
    payload = PhiTray().payload()
    assert isinstance(json.dumps(payload), str)


def test_phi_tray_never_raises(monkeypatch):
    monkeypatch.setattr("phios.desktop.phi_tray.compute_lt", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    payload = PhiTray().payload()
    assert isinstance(payload, dict)


def test_phi_tray_class_coherent_above_0_8():
    assert PhiTray().classify(0.9) == "coherent"


def test_phi_tray_class_degraded_between_0_5_and_0_8():
    assert PhiTray().classify(0.6) == "degraded"


def test_phi_tray_class_critical_below_0_5():
    assert PhiTray().classify(0.2) == "critical"


def test_phi_tray_tooltip_contains_all_fields():
    tooltip = PhiTray().payload()["tooltip"]
    for f in ["L(t)", "Coherence", "Boundary", "Cadence", "Sovereignty", "BrainC", "TBRC"]:
        assert f in str(tooltip)


def test_phi_tray_percentage_in_range():
    pct = int(PhiTray().payload()["percentage"])
    assert 0 <= pct <= 100


def test_waybar_config_has_phi_tray_center():
    assert "custom/phi-tray" in WAYBAR_CONFIG["modules-center"]


def test_waybar_css_contains_tiekat_colors():
    for color in ["#C9A84C", "#2EA8A8", "#5B4FCF", "#A9B0C3", "#070A0F", "#E8EEF5"]:
        assert color in WAYBAR_CSS


def test_sovereignty_indicator_outputs_valid_json():
    payload = indicator_payload()
    assert set(["text", "tooltip", "class", "percentage"]).issubset(payload.keys())


def test_wallpaper_generates_without_pillow(monkeypatch, tmp_path):
    monkeypatch.setitem(__import__("sys").modules, "PIL", None)
    out = SacredGeometryWallpaper().generate(output_path=str(tmp_path / "wallpaper.png"))
    assert Path(out).exists()


def test_wallpaper_falls_back_to_solid_color(monkeypatch, tmp_path):
    monkeypatch.setitem(__import__("sys").modules, "PIL", None)
    path = Path(SacredGeometryWallpaper().generate(output_path=str(tmp_path / "wallpaper.png")))
    assert "PHIOS_SOLID_FALLBACK" in path.read_text(encoding="utf-8")


def test_wallpaper_output_path_created(tmp_path):
    out = SacredGeometryWallpaper().generate(output_path=str(tmp_path / "wallpaper.png"))
    assert Path(out).exists()


def test_wallpaper_phi_ratio_in_geometry():
    assert abs(PHI - ((1 + math.sqrt(5)) / 2)) < 0.000001


def test_wallpaper_regenerate_threshold_respected(monkeypatch):
    called = {"n": 0}

    def fake_generate(*args, **kwargs):
        called["n"] += 1
        return "ok"

    seq = iter([{"lt": 0.1}, {"lt": 0.15}, {"lt": 0.35}])
    monkeypatch.setattr("phios.desktop.wallpaper.compute_lt", lambda: next(seq))
    monkeypatch.setattr("phios.desktop.wallpaper.time.sleep", lambda *_: None)
    monkeypatch.setattr(SacredGeometryWallpaper, "generate", fake_generate)
    SacredGeometryWallpaper().regenerate_on_lt_change(threshold=0.1, iterations=2)
    assert called["n"] == 1
