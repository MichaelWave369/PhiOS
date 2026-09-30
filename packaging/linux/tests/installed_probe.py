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


def probe(source: str, phase: int) -> None:
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
    # The host enters the same fresh account at greetd; the compositor and
    # browser must be launched by the configured login/session services.
    for _ in range(90):
        try:
            with urllib.request.urlopen("http://127.0.0.1:3969/api/v1/health", timeout=2) as response:
                assert response.status == 200
            break
        except OSError:
            time.sleep(1)
    else:
        raise RuntimeError("installed graphical login did not start observer")
    for name in ["wayfire", "chromium"]:
        subprocess.run(["pgrep", "-u", "1000", "-x", name], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["systemctl", "--user", "is-active", "phios-observer.service", "phios-browser.service"], check=True)
    boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip().replace("-", "")
    print("PHIOS_INSTALLED_CHECK_OK:" + json.dumps({"source_commit": source, "phase": phase,
          "boot_id": boot_id, "record_sha256": record.record_sha256}), flush=True)
