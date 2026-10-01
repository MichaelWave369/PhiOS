"""External disposable-VM fixture, run by its password-authenticated UID 1000."""
from __future__ import annotations

import errno
import hashlib
import json
import os
import pty
import re
import select
import subprocess
import time
from pathlib import Path

PASSWORD = 'phios-qa-only-2026'


def operator(argv: list[str], *, cancel: bool = False, approval: bool = False, expected: int = 0) -> str:
    child, channel = pty.fork()
    if child == 0:
        os.execvp('sudo', ['sudo', '-k', *argv])
    text = ''
    supplied_password = False
    supplied_phrase = False
    deadline = time.monotonic() + 180
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
                    if 'password for operator:' in text and not supplied_password:
                        os.write(channel, (PASSWORD + '\n').encode())
                        supplied_password = True
                    match = re.search(r'Type exactly APPROVE ([0-9a-f]{64}) or anything else to cancel:', text)
                    if match and approval and not supplied_phrase:
                        answer = 'cancel' if cancel else 'APPROVE ' + match[1]
                        os.write(channel, (answer + '\n').encode())
                        supplied_phrase = True
            ended, result = os.waitpid(child, os.WNOHANG)
            if ended:
                status = result
                drain = time.monotonic() + 1
                while time.monotonic() < drain and select.select([channel], [], [], 0.1)[0]:
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
        if status is None:
            raise RuntimeError('bounded production sudo proof command timed out')
        code = os.waitstatus_to_exitcode(status)
        print(text, flush=True)
        if code != expected or not supplied_password or (approval and not supplied_phrase):
            raise RuntimeError('actual password/production proof command status differs: ' + str(code))
        return text
    finally:
        os.close(channel)
        if status is None:
            os.kill(child, 9)
            os.waitpid(child, 0)


def proof_workflow(source: str) -> dict[str, object]:
    assert os.getuid() == 1000
    assert subprocess.run(['systemctl', 'is-active', '--quiet', 'phios-proof-proposer.service']).returncode != 0
    operator(['systemctl', 'start', 'phios-proof-proposer.service'])
    report = operator(['phios-linux-proof', 'inspect'])
    assert '"principal_uid": 1001' in report and source in report
    cancelled = operator(['phios-linux-proof', 'approve'], approval=True, cancel=True, expected=2)
    assert 'Cancelled; no approval' in cancelled
    approved = operator(['phios-linux-proof', 'approve'], approval=True)
    match = re.search(r'"approval_sha256": "([0-9a-f]{64})"', approved)
    assert match is not None
    digest = match[1]
    permission = ("import os\nprint('AGENT_UID:'+str(os.getuid()),flush=True)\ntry:\n"
        " open('/.snapshots/phios-linux-proof/approvals/" + digest + "')\n"
        "except PermissionError:\n print('AGENT_STORE_DENIED',flush=True)\n raise SystemExit(1)")
    denied = operator(['runuser', '-u', 'phios-agent', '--', 'python', '-c', permission], expected=1)
    assert 'AGENT_UID:1001' in denied and 'AGENT_STORE_DENIED' in denied
    denied_cli = operator(['runuser', '-u', 'phios-agent', '--', 'phios-linux-proof', 'execute', '--approval', digest], expected=1)
    assert 'installed UID 1000 administrator' in denied_cli
    receipt = operator(['phios-linux-proof', 'execute', '--approval', digest])
    value = json.loads(receipt[receipt.index('{'):receipt.rindex('}') + 1])
    assert value['effect_performed'] is True and value['post_effect_verified'] is True
    assert value['execution_authority'] is False and value['authority_replayable'] is False
    actual = operator(['cat', '/.snapshots/phios-linux-proof/notes/' + digest])
    assert 'PhiOS verified one explicitly approved Linux proof note.' in actual
    replay = operator(['phios-linux-proof', 'execute', '--approval', digest], expected=1)
    assert 'lease_consumed' in replay
    another = operator(['phios-linux-proof', 'approve'], approval=True)
    expired = re.search(r'"approval_sha256": "([0-9a-f]{64})"', another)
    assert expired is not None
    until = time.monotonic() + 61
    while time.monotonic() < until:
        time.sleep(1)
    expiry = operator(['phios-linux-proof', 'execute', '--approval', expired[1]], expected=1)
    assert 'lease_expired' in expiry
    absence = operator(['test', '!', '-e', '/.snapshots/phios-linux-proof/notes/' + expired[1]])
    assert 'Linux proof held' not in absence
    result = {'schema_version': 'phios.linux-proof-qualification.v1', 'source_commit': source,
        'approval_sha256': digest, 'expired_approval_sha256': expired[1], 'receipt': value,
        'actual_agent_uid': 1001, 'sudo_password_authentication': True, 'agent_store_denied': True,
        'agent_broker_denied': True, 'cancel_passed': True, 'replay_refused': True, 'expiry_refused': True,
        'hardware_qualified': False, 'release_ready': False}
    target = Path.home() / '.local/state/phios/qa/linux-proof.json'
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(result, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    print('PHIOS_LINUX_PROOF_OK:' + json.dumps(result), flush=True)
    return result


def historical_proof(source: str) -> None:
    value = json.loads((Path.home() / '.local/state/phios/qa/linux-proof.json').read_text())
    assert value['source_commit'] == source
    denied = operator(['phios-linux-proof', 'execute', '--approval', value['approval_sha256']], expected=1)
    assert 'another boot/source/principal' in denied
    note = operator(['cat', '/.snapshots/phios-linux-proof/notes/' + value['approval_sha256']])
    assert 'PhiOS verified one explicitly approved Linux proof note.' in note
    print('PHIOS_LINUX_PROOF_HISTORY_INACTIVE:' + hashlib.sha256(note.encode()).hexdigest(), flush=True)
