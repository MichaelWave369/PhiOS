"""Reviewed, frozen Arch archive mirror consistency in builder and Archiso."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "packaging/linux/build-linux.sh"
PROFILE = ROOT / "packaging/linux/prepare_profile.py"
PREFETCH = ROOT / "packaging/linux/prefetch-snapshot-packages.sh"

SOURCES = (
    "https://umea.archive.pkgbuild.com",
    "https://archive.archlinux.org",
)


def test_builder_mirrorlist_uses_exact_reviewed_historical_sources():
    code = BUILD.read_text(encoding="utf-8")
    block = code.split("cat > /etc/pacman.d/mirrorlist <<MIRRORS\n", 1)[1].split("\nMIRRORS", 1)[0]
    servers = [line.removeprefix("Server = ") for line in block.splitlines()]
    assert servers == [
        source + "/repos/$snapshot/\\$repo/os/\\$arch" for source in SOURCES
    ]
    assert "pacman --disable-download-timeout -Suu --noconfirm" in code
    assert code.index("phios_prefetch_snapshot_upgrade") < code.index(
        "pacman --disable-download-timeout -Suu --noconfirm"
    )


def test_archiso_profile_uses_identical_two_archive_origins_for_both_repositories():
    source = PROFILE.read_text(encoding="utf-8")
    core = source.split("[core]\n", 1)[1].split("[extra]\n", 1)[0].strip().splitlines()
    extra = source.split("[extra]\n", 1)[1].split("[phios-local]\n", 1)[0].strip().splitlines()
    exact = [
        f"Server = {host}/repos/{{snapshot}}/$repo/os/$arch" for host in SOURCES
    ]
    assert core == exact
    assert extra == exact
    assert "SigLevel = Required DatabaseOptional" in source
    assert "SigLevel = Never" not in source


def test_fallback_retains_https_and_signed_package_requirements():
    source = PREFETCH.read_text(encoding="utf-8")
    transfer = (ROOT / "packaging/linux/archive-package-fetch.sh").read_text(encoding="utf-8")
    assert "--proto https --proto-redir https" in transfer
    assert "--connect-timeout 45" in transfer
    assert "--skippgpcheck" not in source + transfer
    assert "archive-package-fetch.sh" in source
    assert "--disable-download-timeout -Syyuu --downloadonly --noconfirm" in source
    assert re.search(r"PHIOS_ARCH_UPGRADE_PREFETCH_FAILED", source)
