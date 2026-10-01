"""CI-only live fixture: drives the production CLI on a named disposable disk.

This file is excluded from normal profiles and never retained by the installer.
No credential, authority or installed automatic login is supplied to a release.
"""
from __future__ import annotations

import json
import os
import pty
import re
import select
import subprocess
import time
from pathlib import Path

PASSWORD = "phios-qa-only-2026"  # Public ephemeral VM credential, never a release default.


def command(*args: str, data: str | None = None) -> str:
    return subprocess.check_output(args, input=data, text=True, stderr=subprocess.STDOUT)


def drive_installer(*, cancel: bool) -> None:
    pid, fd = pty.fork()
    if pid == 0:
        os.execv("/usr/bin/phios-install", ["phios-install", "--disk", "/dev/vda", "--username", "operator"])
    text = ""
    replied: set[str] = set()
    deadline = time.monotonic() + 900
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([fd], [], [], 1)
            if ready:
                try:
                    data = os.read(fd, 65536)
                except OSError:
                    break
                if not data:
                    break
                chunk = data.decode(errors="replace")
                text += chunk
                print(chunk, end="", flush=True)
            for prompt in ["New account password (12 or more characters): ", "Repeat new account password: "]:
                if prompt in text and prompt not in replied:
                    os.write(fd, (PASSWORD + "\n").encode())
                    replied.add(prompt)
            match = re.search(r"INSTALL /dev/vda [0-9a-f]{64}\r?\n", text)
            if match and "confirm" not in replied and "> " in text[match.end():]:
                os.write(fd, ("cancel\n" if cancel else match[0].strip() + "\n").encode())
                replied.add("confirm")
            ended, status = os.waitpid(pid, os.WNOHANG)
            if ended:
                expected = 1 if cancel else 0
                if os.waitstatus_to_exitcode(status) != expected:
                    raise RuntimeError("production installer returned an unexpected status")
                return
        ended, status = os.waitpid(pid, os.WNOHANG)
        for _ in range(50):
            if ended:
                break
            time.sleep(0.1)
            ended, status = os.waitpid(pid, os.WNOHANG)
        if not ended or os.waitstatus_to_exitcode(status) != (1 if cancel else 0):
            raise RuntimeError("production installer failed or timed out")
    finally:
        try:
            ended, _ = os.waitpid(pid, os.WNOHANG)
            if not ended:
                os.kill(pid, 9)
                os.waitpid(pid, 0)
        except ChildProcessError:
            pass
        os.close(fd)


def main() -> None:
    row = json.loads(command("lsblk", "--nodeps", "--json", "--output", "SERIAL,TYPE,SIZE", "--bytes", "/dev/vda"))["blockdevices"][0]
    if os.geteuid() != 0 or row["serial"] != "PHIOS_CI_BLANK" or row["type"] != "disk" or row["size"] != 32 * 1024**3:
        raise RuntimeError("CI install fixture requires its exact disposable virtual disk")
    drive_installer(cancel=True)
    signatures = json.loads(command("wipefs", "--no-act", "--json", "/dev/vda"))["signatures"]
    if signatures:
        raise RuntimeError("cancelled installer changed the disk")
    print("PHIOS_INSTALL_CANCEL_OK", flush=True)
    drive_installer(cancel=False)
    root = Path("/run/phios-ci-installed")
    root.mkdir(mode=0o700)
    mounts = []
    try:
        command("mount", "-o", "subvol=@root", "/dev/vda2", str(root))
        mounts.append(root)
        command("mount", "-o", "subvol=@home", "/dev/vda2", str(root / "home"))
        mounts.append(root / "home")
        command("mount", "/dev/vda1", str(root / "boot"))
        mounts.append(root / "boot")
        if ("initial_session" in (root / "etc/greetd/config.toml").read_text() or
            (root / "etc/sudoers.d/phios-live-installer").exists() or
            list((root / "usr/local/bin").glob("phios-live-*")) or
            list((root / "etc/systemd/system").glob("phios-live-*.service"))):
            raise RuntimeError("live credentials, autologin or test fixtures survived installation")
        seed = '''
from pathlib import Path
from phios.memory import MemoryOperatorRuntime, MemoryRecord, MemoryRuntimeConfig
from phios.state_recovery import backup
root=Path('/home/operator/.local/state/phios')
runtime=MemoryOperatorRuntime(state_root=root/'memory',
    config=MemoryRuntimeConfig(enabled=True,principal_id='operator',scopes=('private',),
        classifications=('operator',),retention_policy_id='retain'),
    allowed_permissions=('memory.write','memory.read'))
record=MemoryRecord.build(record_id='installed-proof',revision=1,source_id='operator',source_kind='human',
    provenance_refs=(),created_at='2026-09-30T00:00:00+00:00',scope_id='private',classification='operator',
    retention_policy_id='retain',expires_at=None,epistemic_kind='source',text='Persist this acknowledged installed-OS record')
assert runtime.put(record,operation_id='installed-proof-put',task_id='ci-only').status=='ok'
assert runtime.store.get('installed-proof')==record
backup(root,root.parent/'phios-ci-data-backup')
print('PHIOS_INSTALLED_SEED_OK:'+record.record_sha256)
'''
        print(command("arch-chroot", str(root), "runuser", "-u", "operator", "--", "python", "-c", seed), flush=True)
        # Serial access is injected only into this disposable installed test
        # target so the host can exercise password/PAM login and data checks.
        entry = root / "boot/loader/entries/phios.conf"
        entry.write_text(entry.read_text().rstrip() + " console=tty0 console=ttyS0,115200\n")
        getty = root / "etc/systemd/system/getty.target.wants/serial-getty@ttyS0.service"
        getty.parent.mkdir(parents=True, exist_ok=True)
        getty.symlink_to("/usr/lib/systemd/system/serial-getty@.service")
        receipt = json.loads((root / "var/lib/phios/install-receipt.json").read_text())
        os.sync()
    finally:
        for path in reversed(mounts):
            command("umount", str(path))
    print("PHIOS_INSTALLED_DISK_OK:" + receipt["plan"]["source_commit"], flush=True)


if __name__ == "__main__":
    main()
