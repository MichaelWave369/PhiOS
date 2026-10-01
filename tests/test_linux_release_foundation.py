from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from phios.desktop.install import PhiDesktopInstaller
from phios.shell.phi_router import route_command

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare_profile", REPO / "packaging/linux/prepare_profile.py")
assert spec is not None and spec.loader is not None
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


def test_incomplete_template_rejected_without_output(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="complete Archiso"):
        profile.prepare(tmp_path / "missing", tmp_path / "output", REPO, tmp_path, smoke=False)
    assert not (tmp_path / "output").exists()


def test_profile_drops_root_autologin_and_keeps_required_boot_inputs(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream"
    inputs = {
        "profiledef.sh": "upstream identity",
        "efiboot/loader/entries/01-archiso-linux.conf": "title Arch Linux\noptions archisobasedir=%INSTALL_DIR% archisosearchuuid=%ARCHISO_UUID%\n",
        "airootfs/etc/mkinitcpio.conf.d/archiso.conf": "HOOKS=(base udev archiso filesystems)\n",
        "airootfs/etc/systemd/system/getty@tty1.service.d/autologin.conf": "root autologin",
    }
    for name, text in inputs.items():
        path = upstream / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    destination = tmp_path / "candidate"
    profile.prepare(upstream, destination, REPO, tmp_path / "packages", smoke=False)
    assert "uefi.systemd-boot" in (destination / "profiledef.sh").read_text()
    assert "%ARCHISO_UUID%" in (destination / "efiboot/loader/entries/01-archiso-linux.conf").read_text()
    assert not (destination / "airootfs/etc/systemd/system/getty@tty1.service.d/autologin.conf").exists()
    assert not (destination / "airootfs/usr/local/bin/phios-live-smoke").exists()
    assert "user = \"phios\"" in (destination / "airootfs/etc/greetd/config.toml").read_text()
    assert (destination / "airootfs/etc/systemd/system/systemd-firstboot.service").readlink() == Path("/dev/null")
    assert (destination / "airootfs/etc/localtime").readlink() == Path("/usr/share/zoneinfo/UTC")
    assert (destination / "airootfs/etc/vconsole.conf").read_text() == "KEYMAP=us\n"
    wants = destination / 'airootfs/etc/systemd/system/multi-user.target.wants'
    assert (wants / 'NetworkManager.service').is_symlink()
    assert not (wants / 'systemd-networkd.service').exists()
    assert not (wants / 'iwd.service').exists()
    network = (destination / 'airootfs/etc/NetworkManager/conf.d/10-phios.conf').read_text()
    assert 'dns=systemd-resolved' in network and 'enabled=false' in network and 'interval=0' in network
    for name, text in inputs.items():
        assert (upstream / name).read_text() == text
    with pytest.raises(ValueError, match="refusing to overwrite"):
        profile.prepare(upstream, destination, REPO, tmp_path, smoke=False)


def test_missing_desktop_dependencies_never_claim_applied(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _: None)
    installer = PhiDesktopInstaller()
    installer.config_dir = tmp_path
    installer.wayfire_ini = tmp_path / "wayfire.ini"
    installer.waybar_dir = tmp_path / "waybar"
    result = installer.install(dry_run=False)
    assert result["success"] is False
    assert result["applied"] is False
    assert not installer.wayfire_ini.exists()


def test_image_build_failure_reaches_process_exit_status(monkeypatch) -> None:
    monkeypatch.setattr("phios.shell.phi_commands.subprocess.run",
                        lambda *args, **kwargs: SimpleNamespace(returncode=42, stdout="failed", stderr=""))
    output, code = route_command(["build", "iso", "--yes"])
    assert code == 1
    assert "exit 42" in output


def test_current_image_status_hashes_candidate_without_claiming_release(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    artifact = tmp_path / "dist/linux/phios-linux-0.1.0-alpha.1-x86_64.iso"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"candidate")
    output, code = route_command(["build", "status"])
    status = json.loads(output)
    assert code == 0 and status["exists"]
    assert len(status["sha256"]) == 64
    assert status["release_ready"] is False
