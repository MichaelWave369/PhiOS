"""External normal-user VM fixture; the ISO contains none of this test code."""
from __future__ import annotations

import errno
import json
import os
import pty
import re
import select
import subprocess
import time
from pathlib import Path

PASSWORD = 'phios-qa-only-2026'


def maintenance(argv: list[str], *, cancel: bool = False) -> str:
    child, channel = pty.fork()
    if child == 0:
        os.execvp('sudo', ['sudo', '-n', *argv])
    text = ''
    replied: set[str] = set()
    deadline = time.monotonic() + 900
    status = None
    try:
        while time.monotonic() < deadline:
            if select.select([channel], [], [], 0.2)[0]:
                try:
                    data = os.read(channel, 65536)
                except OSError as exc:
                    if exc.errno != errno.EIO:
                        raise
                    data = b''
                if data:
                    text += data.decode(errors='replace')
            for prompt in ['New account password (12 or more characters): ', 'Repeat new account password: ']:
                if prompt in text and prompt not in replied:
                    os.write(channel, (PASSWORD + '\n').encode())
                    replied.add(prompt)
            phrase = re.search(r'(?:INSTALL|CHECKPOINT|RESTORE) /dev/vda [0-9a-f]{64}\r?\n', text)
            if phrase and 'confirm' not in replied and '> ' in text[phrase.end():]:
                os.write(channel, ('cancel\n' if cancel else phrase[0].strip() + '\n').encode())
                replied.add('confirm')
            ended, result = os.waitpid(child, os.WNOHANG)
            if ended:
                status = result
                while select.select([channel], [], [], 0.1)[0]:
                    try:
                        tail = os.read(channel, 65536)
                    except OSError as exc:
                        if exc.errno != errno.EIO:
                            raise
                        break
                    if not tail:
                        break
                    text += tail.decode(errors='replace')
                break
        print(text, flush=True)
        if status is None or os.waitstatus_to_exitcode(status) != (1 if cancel else 0) or 'confirm' not in replied:
            raise RuntimeError('normal-user production maintenance command did not pass exact confirmation/status')
        return text
    finally:
        os.close(channel)
        if status is None:
            os.kill(child, 9)
            os.waitpid(child, 0)


def drive(stage: str, source: str, generation: str | None) -> None:
    assert os.getuid() == 1000 and os.geteuid() == 1000
    assert Path('/usr/share/phios/source-commit').read_text().strip() == source
    assert Path('/run/archiso/bootmnt').is_dir()
    assert not Path('/usr/local/bin/phios-live-smoke').exists()
    assert not Path('/usr/local/bin/phios-live-install-smoke.py').exists()
    assert not Path('/etc/systemd/system/phios-live-smoke.service').exists()
    assert 'wheel' not in subprocess.check_output(['id', '-nG'], text=True).split()
    row = json.loads(subprocess.check_output(['lsblk', '--nodeps', '--json', '--bytes', '--output', 'SERIAL,TYPE,SIZE', '/dev/vda'], text=True))['blockdevices'][0]
    assert row['serial'] == 'PHIOS_CI_BLANK' and row['type'] == 'disk' and row['size'] == 32 * 1024**3
    if stage == 'install':
        argv = ['phios-install', '--disk', '/dev/vda', '--username', 'operator', '--serial-console']
        maintenance(argv, cancel=True)
        # The subsequent actual install rescans every byte for zeroed contents.
        # It would hold if cancellation modified any byte of this fresh disk.
        installed = maintenance(argv)
        assert '"serial_console_password_login": true' in installed
        assert '"installed": true' in installed
        checkpoint = maintenance(['phios-os-recover', 'checkpoint', '--disk', '/dev/vda'])
        values = set(re.findall(r'"generation": "([0-9a-f]{32})"', checkpoint))
        assert len(values) == 1
        generation = values.pop()
    elif stage == 'restore':
        assert generation is not None and re.fullmatch('[0-9a-f]{32}', generation)
        argv = ['phios-os-recover', 'restore', '--disk', '/dev/vda', '--generation', generation]
        maintenance(argv, cancel=True)
        restored = maintenance(argv)
        assert '"stage": "restored; disk-only boot remains unqualified"' in restored
    else:
        raise ValueError('unsupported normal live stage')
    print('PHIOS_NORMAL_MAINTENANCE_OK:' + json.dumps({'stage': stage, 'source_commit': source,
        'generation': generation, 'fixture_free': True, 'uid': os.getuid(), 'limited_live_sudo': True}), flush=True)
