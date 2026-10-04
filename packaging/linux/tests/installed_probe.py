"""Run as the password-authenticated test user on the installed disposable VM."""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

from phios.memory import MemoryStore
from phios.state_io import append_jsonl, read_jsonl
from phios.state_recovery import restore, verify_backup


def probe(source: str, phase: int, *, signed_update: bool = False, desktop_check=None) -> None:
    root = Path.home() / ".local/state/phios"
    assert os.getuid() == 1000
    assert Path("/usr/share/phios/source-commit").read_text().strip() == source
    assert Path("/sys/firmware/efi").is_dir()
    assert "archisobasedir" not in Path("/proc/cmdline").read_text()
    assert not Path("/run/archiso/bootmnt").exists()
    assert root.stat().st_mode & 0o777 == 0o700
    record = MemoryStore(root / "memory/canonical.sqlite3").get("installed-proof")
    assert record is not None and record.text == "Persist this acknowledged installed-OS record"
    backup = root.parent / "phios-ci-data-backup"
    verify_backup(backup)
    restored = root.parent / "phios-ci-restored"
    if phase == 1:
        restore(backup, restored)
        append_jsonl(root / "qa/acknowledged.jsonl", {"source_commit": source, "execution_authority": False})
    assert MemoryStore(restored / "memory/canonical.sqlite3").get("installed-proof") == record
    assert read_jsonl(root / "qa/acknowledged.jsonl") == [{"source_commit": source, "execution_authority": False}]
    assert not (Path.home() / ".config/phios/memory.json").exists()
    assert not (root / "spine-v0.1/ledger/ghostwalk-authorization-decisions.jsonl").exists()
    if signed_update:
        package = Path('/usr/share/phios-ci-update/verified.txt')
        if phase < 3:
            assert package.read_bytes() == b'authenticated disposable PhiOS package update\n'
            assert subprocess.check_output(['pacman', '-Q', 'phios-ci-update'], text=True).strip() == 'phios-ci-update 1.0.0-1'
        else:
            assert not package.exists()
            assert subprocess.run(['pacman', '-Q', 'phios-ci-update'], capture_output=True).returncode == 1
        assert not Path('/usr/share/phios-ci-interrupt/verified.txt').exists()
    # The host enters the same fresh account at greetd; the compositor and
    # browser must be launched by the configured login/session services.
    for _ in range(90):
        try:
            with urllib.request.urlopen("http://127.0.0.1:3969/api/v1/health", timeout=2) as response:
                assert response.status == 200
            with urllib.request.urlopen("http://127.0.0.1:3969/", timeout=2) as response:
                assert response.status == 200
            # Observer health precedes browser startup. Require the whole
            # supervised desktop to be ready within the same bounded wait.
            if any(subprocess.run(["pgrep", "-u", "1000", "-x", name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode for name in ["wayfire", "chromium"]):
                time.sleep(1)
                continue
            if subprocess.run(["systemctl", "--user", "is-active", "phios-observer.service", "phios-browser.service"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5).returncode:
                time.sleep(1)
                continue
            break
        except OSError:
            time.sleep(1)
    else:
        subprocess.run(["journalctl", "--user", "--no-pager", "-n", "60", "-u", "phios-browser.service",
            "-u", "phios-curiosity-reader.service", "-u", "phios-observer.service"], timeout=15)
        raise RuntimeError("installed graphical login did not start the complete supervised desktop")
    time.sleep(2)  # Preserve a rendered application screenshot after process readiness.
    if desktop_check is None:
        raise RuntimeError('external desktop service verifier is required')
    desktop_check(source)
    boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip().replace("-", "")
    print("PHIOS_INSTALLED_CHECK_OK:" + json.dumps({"source_commit": source, "phase": phase,
          "boot_id": boot_id, "record_sha256": record.record_sha256}), flush=True)
