"""The pinned Arch upgrade must retry downloads, never partially installed upgrades."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PREFETCH = ROOT / "packaging/linux/prefetch-snapshot-packages.sh"
BUILD = ROOT / "packaging/linux/build-linux.sh"


@pytest.mark.parametrize("success_at,expected_status,attempts,sleeps", [
    (1, 0, 1, 0),
    (2, 0, 2, 1),
    (99, 1, 3, 2),
])
def test_pinned_arch_upgrade_prefetch_only_retries_downloads(
    tmp_path: Path, success_at: int, expected_status: int, attempts: int, sleeps: int,
) -> None:
    trace = tmp_path / "calls.log"
    program = """
set -euo pipefail
pacman() {
    printf 'pacman:%s\\n' "$*" >> "$TRACE"
    local n
    n=$(grep -c '^pacman:' "$TRACE" || true)
    if [[ "$n" -lt "$SUCCESS_AT" ]]; then
        return 71
    fi
    return 0
}
timeout() {
    # Test transport retry policy without running GNU timeout or real pacman.
    [[ "$1" == "--signal=TERM" ]] || return 91
    [[ "$2" == "--kill-after=15s" ]] || return 92
    [[ "$3" == "600s" ]] || return 93
    shift 3
    "$@"
}
sleep() { printf 'sleep:%s\\n' "$*" >> "$TRACE"; }
source "$PREFETCH_SCRIPT"
phios_prefetch_snapshot_upgrade
"""
    result = subprocess.run(
        ["bash", "-c", program],
        env={
            **os.environ,
            "TRACE": str(trace),
            "SUCCESS_AT": str(success_at),
            "PREFETCH_SCRIPT": str(PREFETCH),
        },
        capture_output=True, text=True, timeout=15,
        check=False,
    )
    assert result.returncode == expected_status, result.stderr
    lines = trace.read_text().splitlines()
    pacman = [line for line in lines if line.startswith("pacman:")]
    assert len(pacman) == attempts
    assert all(line == (
        "pacman:--disable-download-timeout -Syyuu --downloadonly --noconfirm"
    ) for line in pacman)
    assert len([line for line in lines if line == "sleep:5"]) == sleeps
    if expected_status:
        assert "PHIOS_ARCH_UPGRADE_PREFETCH_FAILED" in result.stderr
    else:
        assert "PHIOS_ARCH_UPGRADE_PREFETCH_OK" in result.stdout


def test_release_builder_only_installs_after_successful_pinned_prefetch() -> None:
    source = BUILD.read_text(encoding="utf-8")
    expected = (
        'source "$repo/packaging/linux/prefetch-snapshot-packages.sh"',
        "phios_prefetch_snapshot_upgrade",
        "pacman --disable-download-timeout -Suu --noconfirm",
        "phios_prefetch_snapshot_packages",
    )
    locations = [source.index(text) for text in expected]
    assert locations == sorted(locations)
    assert source.count("phios_prefetch_snapshot_upgrade") == 1
    assert "pacman -Syyuu --noconfirm" not in source
    assert 'Server = https://archive.archlinux.org/repos/$snapshot/' in source
    assert "pacman --disable-download-timeout -S --needed --noconfirm" in source
    assert "archiso $expected_archiso" in source
