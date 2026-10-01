"""Observe public OS identity and propose one fixed harmless note as UID 1001."""
from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

TEXT = 'PhiOS verified one explicitly approved Linux proof note.\n'


def main() -> None:
    if os.getuid() != 1001 or os.geteuid() != 1001:
        raise ValueError('the isolated phios-agent principal is required')
    source = Path('/usr/share/phios/source-commit').read_text().strip()
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip().replace('-', '')
    if not re.fullmatch('[0-9a-f]{40}', source) or not re.fullmatch('[0-9a-f]{32}', boot):
        raise ValueError('exact observed OS source and boot identity required')
    root = Path('/var/lib/phios-agent')
    info = root.lstat()
    if root.is_symlink() or info.st_uid != 1001 or info.st_mode & 0o077:
        raise ValueError('private agent directory required')
    proposal = {'schema_version': 'phios.linux-proof-proposal.v1', 'principal_uid': 1001,
        'source_commit': source, 'boot_id': boot, 'observed_at': datetime.now(UTC).isoformat(),
        'nonce': uuid.uuid4().hex, 'capability_id': 'linux.proof_note', 'text': TEXT,
        'execution_authority': False, 'effect_performed': False}
    fd, name = tempfile.mkstemp(prefix='.proposal-', dir=root)
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump(proposal, handle, sort_keys=True, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, root / 'proposal.json')
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(name).unlink(missing_ok=True)
    print('One proposal recorded; no approval, lease or effect created.')


if __name__ == '__main__':
    main()
