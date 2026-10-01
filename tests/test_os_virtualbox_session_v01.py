from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SESSION = REPO / 'packaging/linux/session'


def command(path: Path, body: str) -> None:
    path.write_text('#!/usr/bin/env python3\n' + body)
    path.chmod(0o755)


@pytest.fixture
def commands(tmp_path: Path) -> tuple[dict[str, str], Path]:
    binaries = tmp_path / 'bin'
    binaries.mkdir()
    events = tmp_path / 'events.jsonl'
    for name in ['systemctl', 'dbus-update-activation-environment']:
        command(binaries / name, '''import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
with open(os.environ['EVENTS'], 'a') as stream:
    stream.write(json.dumps({'command': [name, *sys.argv[1:]], 'environment': {
        key: os.environ.get(key) for key in ['WAYLAND_DISPLAY', 'DISPLAY', 'XDG_RUNTIME_DIR', 'XDG_CURRENT_DESKTOP']}}) + '\\n')
label = name + (':' + sys.argv[2] if name == 'systemctl' else '')
sys.exit(19 if os.environ.get('FAIL_COMMAND') == label else 0)
''')
    command(binaries / 'systemd-detect-virt', '''import os, sys
assert sys.argv[1:] == ['--vm']
print(os.environ['VIRTUALIZATION'])
sys.exit(int(os.environ.get('VIRT_STATUS', '0')))
''')
    env = {**os.environ, 'PATH': str(binaries) + os.pathsep + os.environ['PATH'], 'EVENTS': str(events)}
    env.pop('WLR_NO_HARDWARE_CURSORS', None)
    return env, events


def pci_device(root: Path, *, vendor: str = '0x15ad', product: str = '0x0405',
               display_class: str = '0x030000', slot: str = '0000:00:02.0') -> Path:
    device = root / slot
    device.mkdir(parents=True)
    for name, value in [('vendor', vendor), ('device', product), ('class', display_class)]:
        (device / name).write_text(value + '\n')
    return device


def compatibility(env: dict[str, str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(['bash', '-c',
        'set -euo pipefail; source "$1"; phios_virtualbox_cursor_compat "$2"; '
        'printf "%s" "${WLR_NO_HARDWARE_CURSORS-unset}"',
        'compat-test', str(SESSION / 'virtualbox-compat.sh'), str(root)],
        env=env, capture_output=True, text=True, timeout=10)


def test_only_detected_virtualbox_with_vmsvga_selects_software_cursor(commands, tmp_path):
    env, _ = commands
    pci_device(tmp_path / 'pci', vendor='0x8086', product='0x1234', slot='0000:00:01.0')
    pci_device(tmp_path / 'pci')
    result = compatibility({**env, 'VIRTUALIZATION': 'oracle'}, tmp_path / 'pci')
    assert result.returncode == 0 and result.stdout == '1'


@pytest.mark.parametrize('hypervisor', ['none', 'kvm', 'qemu', 'vmware', 'microsoft', 'docker', ''])
def test_vmsvga_pci_identity_alone_never_enables_virtualbox_fix(commands, tmp_path, hypervisor):
    env, _ = commands
    pci_device(tmp_path / 'pci')
    result = compatibility({**env, 'VIRTUALIZATION': hypervisor}, tmp_path / 'pci')
    assert result.returncode == 0 and result.stdout == 'unset'


@pytest.mark.parametrize('device', ['vboxsvga', 'nvidia', 'wrong_class', 'missing_id', 'empty', 'unavailable'])
def test_unmatched_or_incomplete_display_observation_does_not_change_cursor(commands, tmp_path, device):
    env, _ = commands
    root = tmp_path / 'pci'
    if device == 'vboxsvga':
        pci_device(root, vendor='0x80ee', product='0xbeef')
    elif device == 'nvidia':
        pci_device(root, vendor='0x10de', product='0x2f04')
    elif device == 'wrong_class':
        pci_device(root, display_class='0x020000')
    elif device == 'missing_id':
        pci_device(root).joinpath('device').unlink()
    elif device == 'empty':
        pci_device(root).joinpath('vendor').write_text('')
    result = compatibility({**env, 'VIRTUALIZATION': 'oracle'}, root)
    assert result.returncode == 0 and result.stdout == 'unset'


def test_detection_failure_is_nonfatal_and_does_not_select_a_fix(commands, tmp_path):
    env, _ = commands
    pci_device(tmp_path / 'pci')
    result = compatibility({**env, 'VIRTUALIZATION': 'oracle', 'VIRT_STATUS': '1'}, tmp_path / 'pci')
    assert result.returncode == 0 and result.stdout == 'unset'


def test_nonvirtualbox_operator_cursor_environment_is_preserved(commands, tmp_path):
    env, _ = commands
    result = compatibility({**env, 'VIRTUALIZATION': 'none', 'WLR_NO_HARDWARE_CURSORS': '1'}, tmp_path / 'pci')
    assert result.returncode == 0 and result.stdout == '1'


@pytest.fixture
def wayland():
    with tempfile.TemporaryDirectory(prefix='phios-session-test-') as directory:
        runtime = Path(directory)
        # This shell test checks file type; the QEMU probe connects to the real
        # compositor. A socket inode needs no listener/network permission here.
        os.mknod(runtime / 'wayland-1', stat.S_IFSOCK | 0o600)
        yield runtime


def ready(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(['bash', str(SESSION / 'phios-session-ready')], env=env,
                          capture_output=True, text=True, timeout=10)


def recorded(events: Path) -> list[dict]:
    return [json.loads(line) for line in events.read_text().splitlines()] if events.exists() else []


@pytest.mark.parametrize('absolute_display', [False, True])
@pytest.mark.parametrize('xwayland_display', ['', ':1'])
def test_new_socket_environment_is_imported_before_active_services_are_restarted(
    commands, wayland, absolute_display, xwayland_display,
):
    env, events = commands
    env.update({'XDG_RUNTIME_DIR': str(wayland), 'XDG_CURRENT_DESKTOP': 'Wayfire',
                'WAYLAND_DISPLAY': str(wayland / 'wayland-1') if absolute_display else 'wayland-1'})
    env.pop('DISPLAY', None)
    if xwayland_display:
        env['DISPLAY'] = xwayland_display
    result = ready(env)
    assert result.returncode == 0, result.stderr
    rows = recorded(events)
    assert [row['command'] for row in rows] == [
        ['systemctl', '--user', 'import-environment', 'WAYLAND_DISPLAY', 'DISPLAY',
         'XDG_CURRENT_DESKTOP', 'XDG_RUNTIME_DIR'],
        ['dbus-update-activation-environment', '--systemd', 'WAYLAND_DISPLAY', 'DISPLAY',
         'XDG_CURRENT_DESKTOP', 'XDG_RUNTIME_DIR'],
        ['systemctl', '--user', 'stop', 'phios-session.target'],
        ['systemctl', '--user', 'start', 'phios-session.target'],
    ]
    assert all(row['environment'] == {'WAYLAND_DISPLAY': env['WAYLAND_DISPLAY'],
        'DISPLAY': xwayland_display, 'XDG_RUNTIME_DIR': str(wayland), 'XDG_CURRENT_DESKTOP': 'Wayfire'}
        for row in rows)


@pytest.mark.parametrize('case', ['no_display', 'no_runtime', 'no_socket', 'regular_file'])
def test_no_services_or_activation_environment_change_without_wayland_socket(commands, wayland, case):
    env, events = commands
    env.update({'WAYLAND_DISPLAY': 'wayland-1', 'XDG_RUNTIME_DIR': str(wayland), 'XDG_CURRENT_DESKTOP': 'Wayfire'})
    if case == 'no_display':
        env.pop('WAYLAND_DISPLAY')
    elif case == 'no_runtime':
        env.pop('XDG_RUNTIME_DIR')
    else:
        env['WAYLAND_DISPLAY'] = 'absent'
        if case == 'regular_file':
            (wayland / 'absent').write_text('not a Wayland socket')
    result = ready(env)
    assert result.returncode != 0 and 'require' in result.stderr
    assert recorded(events) == []


@pytest.mark.parametrize(('failure', 'calls'), [
    ('systemctl:import-environment', 1), ('dbus-update-activation-environment', 2),
    ('systemctl:stop', 3), ('systemctl:start', 4),
])
def test_import_or_stop_failure_cannot_start_services_and_start_failure_is_reported(commands, wayland, failure, calls):
    env, events = commands
    result = ready({**env, 'WAYLAND_DISPLAY': 'wayland-1', 'XDG_RUNTIME_DIR': str(wayland),
                    'XDG_CURRENT_DESKTOP': 'Wayfire', 'FAIL_COMMAND': failure})
    assert result.returncode == 19
    assert len(recorded(events)) == calls
