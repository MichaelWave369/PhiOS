"""Drive the unmodified normal ISO via real public-user PAM and narrow sudo."""
from __future__ import annotations

import json
import re
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from qemu_boot import capture_display


def drive_live(common: list[str], iso: Path, source: str, output: Path, receipt: dict[str, Any],
               *, stage: str, generation: str | None = None) -> dict[str, Any]:
    prefix = 'normal-' + stage + '-live'
    qmp, serial = output / (prefix + '-qmp.sock'), output / (prefix + '-serial.sock')
    command = common + ['-drive', f'file={iso.resolve()},if=none,id=installation,format=raw,media=cdrom,readonly=on',
        '-device', 'ide-cd,drive=installation,bootindex=1', '-serial', f'unix:{serial},server=on,wait=off',
        '-qmp', f'unix:{qmp},server=on,wait=off']
    receipt['commands'].append(command)
    with (output / (prefix + '-qemu.log')).open('w') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 1800
            while not serial.exists() and time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('normal live VM exited before transport')
                time.sleep(0.1)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
                channel.settimeout(1)
                channel.connect(str(serial))
                text = ''
                with (output / (prefix + '-serial.log')).open('wb') as transcript:
                    def wait(pattern: str) -> re.Match[str]:
                        nonlocal text
                        while time.monotonic() < deadline:
                            match = re.search(pattern, text)
                            if match:
                                return match
                            if process.poll() is not None:
                                raise RuntimeError('normal live maintenance VM exited')
                            try:
                                data = channel.recv(65536)
                            except socket.timeout:
                                continue
                            if not data:
                                raise RuntimeError('normal live channel closed')
                            transcript.write(data)
                            transcript.flush()
                            text += data.decode(errors='replace')
                            if 'Traceback (most recent call last)' in text:
                                drain = time.monotonic() + 3
                                while time.monotonic() < drain:
                                    try:
                                        tail = channel.recv(65536)
                                    except socket.timeout:
                                        continue
                                    if not tail:
                                        break
                                    transcript.write(tail)
                                    transcript.flush()
                                raise RuntimeError('normal-user maintenance failed; preserve serial evidence')
                        raise RuntimeError('normal live PAM/maintenance timed out')
                    wait(r'login: ')
                    channel.sendall(b'phios\n')
                    wait(r'Password:')
                    channel.sendall(b'phios\n')
                    time.sleep(2)
                    text = ''
                    program = Path(__file__).with_name('normal_live_probe.py').read_text() + f'\ndrive({stage!r},{source!r},{generation!r})\n'
                    if max(map(len, program.splitlines())) >= 4096:
                        raise ValueError('guest program exceeds canonical terminal line bound')
                    channel.sendall(("python - <<'PHIOS_NORMAL_MAINTENANCE'\n" + program + '\nPHIOS_NORMAL_MAINTENANCE\n').encode())
                    result = json.loads(wait(r'PHIOS_NORMAL_MAINTENANCE_OK:(\{[^\r\n]+\})')[1])
                    if (result['source_commit'] != source or result['stage'] != stage or result['uid'] != 1000
                            or result['fixture_free'] is not True or result['limited_live_sudo'] is not True):
                        raise RuntimeError('normal maintenance identity/evidence mismatch')
                    return result
        finally:
            if process.poll() is None:
                try:
                    capture_display(qmp, output, name='screen-' + prefix)
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
