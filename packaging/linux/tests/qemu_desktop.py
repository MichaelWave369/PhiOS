"""External QMP screen-lock test using the guest's real shortcut and PAM."""
from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path
from typing import Callable

from qemu_boot import capture_display, qmp_request


def qualify_lock(qmp: Path, output: Path, *, source: str, password: str, label: str,
                 program: Callable[[str], None], wait: Callable[[str], re.Match[str]]) -> dict:
    if not re.fullmatch('[a-z0-9-]+', password):
        raise ValueError('only the public disposable test password is accepted by this key driver')

    def state(locked: bool) -> dict:
        nonce = secrets.token_hex(8)
        marker = 'PHIOS_LOCK_STATE_' + nonce + ':'
        program("import os,json,subprocess,time\nfrom pathlib import Path\n"
                "assert os.getuid()==1000\n"
                f"expected={locked!r}\n"
                "for _ in range(30):\n"
                "    active=subprocess.run(['pgrep','-u','1000','-x','swaylock'],capture_output=True).returncode==0\n"
                "    if active==expected: break\n"
                "    time.sleep(1)\n"
                "else: raise RuntimeError('real session lock/PAM state did not match')\n"
                f"print({marker!r}+json.dumps({{'locked':active,'uid':os.getuid(),"
                "'source_commit':Path('/usr/share/phios/source-commit').read_text().strip(),"
                "'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip().replace('-','')}),flush=True)\n")
        result = json.loads(wait(re.escape(marker) + r'(\{[^\r\n]+\})')[1])
        if result['locked'] is not locked or result['uid'] != 1000 or result['source_commit'] != source:
            raise RuntimeError('screen-lock identity/state differs')
        return result

    def keys(value: str) -> None:
        for key in [*value, 'ret']:
            code = 'minus' if key == '-' else key
            qmp_request(qmp, {'execute': 'send-key', 'arguments': {
                'keys': [{'type': 'qcode', 'data': code}], 'hold-time': 80}})
            time.sleep(0.12)

    state(False)
    qmp_request(qmp, {'execute': 'send-key', 'arguments': {
        'keys': [{'type': 'qcode', 'data': key} for key in ['meta_l', 'l']], 'hold-time': 80}})
    locked = state(True)
    capture_display(qmp, output, name=f'screen-{label}-locked')
    keys('wrong-lock-password')
    time.sleep(5)  # Allow the actual PAM refusal/delay before another attempt.
    state(True)
    capture_display(qmp, output, name=f'screen-{label}-wrong-password')
    qmp_request(qmp, {'execute': 'send-key', 'arguments': {
        'keys': [{'type': 'qcode', 'data': key} for key in ['ctrl', 'u']], 'hold-time': 80}})
    time.sleep(0.2)
    keys(password)
    unlocked = state(False)
    capture_display(qmp, output, name=f'screen-{label}-unlocked')
    if locked['boot_id'] != unlocked['boot_id']:
        raise RuntimeError('unlock required an unexpected reboot')
    return {'source_commit': source, 'boot_id': unlocked['boot_id'], 'uid': 1000,
            'actual_super_l_shortcut': True, 'wrong_password_held': True,
            'correct_pam_password_unlocked': True, 'release_ready': False}
