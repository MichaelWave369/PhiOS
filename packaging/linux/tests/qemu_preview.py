"""Qualify an unmodified fixture-free ISO through normal PAM and user commands."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from qemu_boot import capture_display, enter_live_login, qmp_request
from qemu_install import stop

PROBE = '''
import json,os,subprocess,time,urllib.request
from pathlib import Path
assert os.getuid()==1000
assert Path('/usr/share/phios/source-commit').read_text().strip()==SOURCE
assert Path('/sys/firmware/efi').is_dir()
assert Path('/run/archiso/bootmnt').is_dir()
assert not list(Path('/usr/local/bin').glob('phios-live-*-smoke*'))
assert not Path('/usr/local/bin/phios-live-smoke').exists()
assert not Path('/etc/systemd/system/phios-live-smoke.service').exists()
assert not Path('/etc/phios/os-update-trust.json').exists()
assert not Path('/etc/phios/os-update-keyring.gpg').exists()
assert not Path('/usr/share/phios-ci-update').exists()
assert Path.home().stat().st_mode&0o777==0o700
assert (Path.home()/'.local/state/phios').stat().st_mode&0o777==0o700
assert 'wheel' not in subprocess.check_output(['id','-nG'],text=True).split()
for _ in range(90):
    try:
        with urllib.request.urlopen('http://127.0.0.1:3969/api/v1/health',timeout=2) as response:
            assert response.status==200
        if any(subprocess.run(['pgrep','-u','1000','-x',name],capture_output=True).returncode for name in ['wayfire','chromium']):
            time.sleep(1);continue
        subprocess.run(['systemctl','--user','is-active','phios-observer.service','phios-browser.service'],check=True)
        break
    except (OSError,subprocess.CalledProcessError):
        time.sleep(1)
else:
    raise RuntimeError('complete supervised desktop did not become ready')
with urllib.request.urlopen('http://127.0.0.1:3969/',timeout=3) as response:
    assert b'<div id="root">' in response.read()
with urllib.request.urlopen('http://127.0.0.1:3969/api/v1/package-observation',timeout=3) as response:
    value=json.load(response)['observation']
    assert value['adapter']=='arch-pacman-local' and value['availability']=='available'
    assert value['executionAuthority'] is False and value['effectPerformed'] is False
for pid in subprocess.check_output(['pgrep','-u','1000','-x','chromium'],text=True).split():
    assert b'--no-sandbox' not in Path('/proc/'+pid+'/cmdline').read_bytes().split(b'\\0')
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip().replace('-','')
print('PHIOS_PREVIEW_OK:'+json.dumps({'source_commit':SOURCE,'boot_id':boot,'stage':STAGE,'uid':os.getuid(),'fixture_free':True}),flush=True)
'''

LIFECYCLE = '''
import json,os,subprocess,time,urllib.request
from pathlib import Path
args=['systemctl','--user']
def pid():
    return subprocess.check_output(args+['show','phios-observer.service','--property=MainPID','--value'],text=True).strip()
previous=pid()
assert previous.isdigit() and int(previous)>0
subprocess.run(args+['kill','--signal=KILL','phios-observer.service'],check=True)
for _ in range(60):
    current=pid()
    try:
        with urllib.request.urlopen('http://127.0.0.1:3969/api/v1/health',timeout=2) as response:
            if current!=previous and int(current)>0 and response.status==200: break
    except OSError:
        pass
    time.sleep(1)
else:
    raise RuntimeError('observer restart failed')
subprocess.run(['pkill','-TERM','-u',str(os.getuid()),'-x','wayfire'],check=True)
for _ in range(30):
    active=subprocess.run(args+['is-active','--quiet','phios-session.target'],capture_output=True).returncode==0
    try:
        urllib.request.urlopen('http://127.0.0.1:3969/api/v1/health',timeout=2).close()
        reachable=True
    except OSError:
        reachable=False
    if not active and not reachable: break
    time.sleep(1)
else:
    raise RuntimeError('logout did not stop the supervised session')
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip().replace('-','')
print('PHIOS_PREVIEW_LOGOUT_OK:'+json.dumps({'boot_id':boot,'old_observer_pid':previous,'new_observer_pid':current}),flush=True)
'''


def qualify(iso: Path, source: str, output: Path) -> None:
    if not re.fullmatch(r'[0-9a-f]{40}', source) or not iso.is_file() or output.exists():
        raise ValueError('exact ISO/source and fresh evidence directory required')
    output.mkdir(parents=True, mode=0o700)
    variables = output / 'OVMF_VARS.fd'
    shutil.copyfile('/usr/share/OVMF/OVMF_VARS_4M.fd', variables)
    accelerator = 'kvm' if os.access('/dev/kvm', os.R_OK | os.W_OK) else 'tcg'
    qmp, serial = output / 'qmp.sock', output / 'serial.sock'
    command = ['qemu-system-x86_64', '-machine', 'q35,accel=' + accelerator, '-cpu',
        'host' if accelerator == 'kvm' else 'max', '-m', '4096', '-smp', '2',
        '-drive', 'if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd',
        '-drive', 'if=pflash,format=raw,file=' + str(variables), '-cdrom', str(iso.resolve()), '-boot', 'd',
        '-nic', 'none', '-vga', 'none', '-device', 'virtio-vga', '-display', 'none', '-monitor', 'none',
        '-serial', f'unix:{serial},server=on,wait=off', '-qmp', f'unix:{qmp},server=on,wait=off']
    with iso.open('rb') as handle:
        iso_hash = hashlib.file_digest(handle, 'sha256').hexdigest()
    receipt: dict[str, Any] = {'schema_version': 'phios.fixture-free-live-evidence.v1', 'source_commit': source,
        'iso_sha256': iso_hash, 'command': command, 'accelerator': accelerator, 'boots': [],
        'fixture_free_qualified': False, 'hardware_qualified': False, 'release_ready': False,
        'public_volatile_credentials': True, 'test_code_injected_into_image': False}
    with (output / 'qemu.log').open('w') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + (900 if accelerator == 'kvm' else 1800)
            while not serial.exists() and time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('VM exited before normal serial transport')
                time.sleep(0.1)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
                channel.settimeout(1)
                channel.connect(str(serial))
                text = ''
                with (output / 'serial.log').open('wb') as transcript:
                    def wait(pattern: str) -> re.Match[str]:
                        nonlocal text
                        while time.monotonic() < deadline:
                            match = re.search(pattern, text)
                            if match:
                                return match
                            if process.poll() is not None:
                                raise RuntimeError('VM exited during normal user qualification')
                            try:
                                data = channel.recv(65536)
                            except socket.timeout:
                                continue
                            if not data:
                                raise RuntimeError('normal serial channel closed')
                            transcript.write(data)
                            transcript.flush()
                            text += data.decode(errors='replace')
                            if '\nTraceback (most recent call last):' in text:
                                # Preserve the actual guest exception before shutting down.
                                drain_until = time.monotonic() + 3
                                while time.monotonic() < drain_until:
                                    try:
                                        tail = channel.recv(65536)
                                    except socket.timeout:
                                        continue
                                    if not tail:
                                        break
                                    transcript.write(tail)
                                    transcript.flush()
                                raise RuntimeError('normal-user preview probe failed; see preserved serial log')
                        raise RuntimeError('normal PAM/desktop qualification timed out')

                    def program(value: str) -> None:
                        channel.sendall(("python - <<'PHIOS_NORMAL_PROBE'\n" + value + '\nPHIOS_NORMAL_PROBE\n').encode())

                    for boot in [1, 2]:
                        wait(r'login: ')
                        channel.sendall(b'phios\n')
                        wait(r'Password:')
                        channel.sendall(b'phios\n')
                        time.sleep(2)
                        text = ''
                        program(f'SOURCE={source!r}\nSTAGE="first"\n' + PROBE)
                        first = json.loads(wait(r'PHIOS_PREVIEW_OK:(\{[^\r\n]+\})')[1])
                        assert first['source_commit'] == source and first['stage'] == 'first'
                        time.sleep(2)
                        capture_display(qmp, output, name=f'screen-{boot}-first')
                        text = ''
                        program(LIFECYCLE)
                        lifecycle = json.loads(wait(r'PHIOS_PREVIEW_LOGOUT_OK:(\{[^\r\n]+\})')[1])
                        assert lifecycle['boot_id'] == first['boot_id']
                        enter_live_login(qmp)
                        text = ''
                        program(f'SOURCE={source!r}\nSTAGE="reauthenticated"\n' + PROBE)
                        second = json.loads(wait(r'PHIOS_PREVIEW_OK:(\{[^\r\n]+\})')[1])
                        assert second['boot_id'] == first['boot_id'] and second['stage'] == 'reauthenticated'
                        time.sleep(2)
                        capture_display(qmp, output, name=f'screen-{boot}-reauthenticated')
                        receipt['boots'].append({'first': first, 'lifecycle': lifecycle, 'reauthenticated': second})
                        if boot == 1:
                            qmp_request(qmp, {'execute': 'system_reset'})
                            text = ''
                            deadline = time.monotonic() + (900 if accelerator == 'kvm' else 1800)
                    if len({boot['first']['boot_id'] for boot in receipt['boots']}) != 2:
                        raise RuntimeError('second distinct boot not observed')
                    receipt['fixture_free_qualified'] = True
        except BaseException as exc:
            receipt['error'] = str(exc)
            raise
        finally:
            if process.poll() is None:
                try:
                    capture_display(qmp, output)
                except (OSError, ValueError, RuntimeError) as exc:
                    receipt['display_capture_error'] = str(exc)
            stop(process)
            (output / 'preview-evidence.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('Fixture-free UEFI image passed two PAM/graphical/session-lifecycle boots: ' + iso_hash)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iso', required=True, type=Path)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    qualify(args.iso, args.source, args.output.resolve())
