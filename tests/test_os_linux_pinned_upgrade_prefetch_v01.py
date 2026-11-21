"""The pinned Arch upgrade must retry downloads, never partially installed upgrades."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PREFETCH = ROOT / "packaging/linux/prefetch-snapshot-packages.sh"
BUILD = ROOT / "packaging/linux/build-linux.sh"


def _upgrade_mock(tmp_path: Path, *, success_at: int, config_text: str | None = None):
    trace = tmp_path / "calls.log"
    capture = tmp_path / "fallback-captured.conf"
    source = tmp_path / "pacman.conf"
    source.write_text(
        config_text if config_text is not None else
        "[options]\nSigLevel = Required DatabaseOptional\n"
        "[core]\nInclude = /etc/pacman.d/mirrorlist\n",
        encoding="utf-8",
    )
    program = """
set -euo pipefail
pacman() {
    printf 'pacman:%s\\n' "$*" >> "$TRACE"
    if [[ "$1" == "--config" ]]; then
        cp "$2" "$CAPTURE"
    fi
    local n
    n=$(grep -c '^pacman:' "$TRACE" || true)
    if [[ "$n" -lt "$SUCCESS_AT" ]]; then
        return 71
    fi
    return 0
}
timeout() {
    # Test transfer selection, not real pacman, package installs or timers.
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
            **os.environ, "TRACE": str(trace), "CAPTURE": str(capture),
            "SUCCESS_AT": str(success_at),
            "PREFETCH_SCRIPT": str(PREFETCH),
            "PHIOS_PREFETCH_PACMAN_CONFIG": str(source),
        },
        capture_output=True, text=True, timeout=15, check=False,
    )
    calls = [x for x in trace.read_text().splitlines() if x.startswith("pacman:")]
    sleeps = [x for x in trace.read_text().splitlines() if x == "sleep:5"]
    config = capture.read_text() if capture.exists() else ""
    return result, calls, sleeps, config


@pytest.mark.parametrize("success_at,expected_status,attempts,sleep_count", [
    (1, 0, 1, 0),
    (2, 0, 2, 1),
    (99, 1, 3, 2),
])
def test_pinned_arch_upgrade_prefetch_only_retries_downloads(
    tmp_path: Path, success_at: int, expected_status: int, attempts: int, sleep_count: int,
) -> None:
    result, calls, sleeps, config = _upgrade_mock(tmp_path, success_at=success_at)
    assert result.returncode == expected_status, result.stderr
    assert len(calls) == attempts
    assert calls[0] == "pacman:--disable-download-timeout -Syyuu --downloadonly --noconfirm"
    for line in calls[1:]:
        assert line.startswith("pacman:--config /tmp/phios-signed-upgrade-prefetch.")
        assert line.endswith("--disable-download-timeout -Syyuu --downloadonly --noconfirm")
        assert "--skippgpcheck" not in line
        assert "--dbonly" not in line
        assert "--noconfirm -Suu" not in line
    assert len(sleeps) == sleep_count
    if attempts > 1:
        assert "SigLevel = Required DatabaseOptional" in config
        assert "Include = /etc/pacman.d/mirrorlist" in config
        assert "--proto https --proto-redir https" in config
        assert "--connect-timeout 45" in config
        assert "--http1.1" in config
        assert "-C - -o %o %u" in config
        assert "--insecure" not in config
    else:
        assert config == ""
    if expected_status:
        assert "PHIOS_ARCH_UPGRADE_PREFETCH_FAILED" in result.stderr
    else:
        assert "PHIOS_ARCH_UPGRADE_PREFETCH_OK" in result.stdout


@pytest.mark.parametrize("malformed_config,message", [
    ("[options]\nXferCommand = /opt/unreviewed-fetch %u %o\n"
     "[core]\nInclude = /etc/pacman.d/mirrorlist\n", "existing XferCommand needs review"),
    ("[core]\nInclude = /etc/pacman.d/mirrorlist\n", "invalid pacman options section"),
])
def test_upgrade_fallback_refuses_unreviewed_transfer_config(
    tmp_path: Path, malformed_config: str, message: str,
) -> None:
    result, calls, sleeps, config = _upgrade_mock(
        tmp_path, success_at=99, config_text=malformed_config,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert len(calls) == 1  # Never dispatch an unreviewed transfer policy.
    assert len(sleeps) == 1
    assert config == ""
    assert message in result.stderr
    assert "secure transfer fallback unavailable" in result.stderr


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
