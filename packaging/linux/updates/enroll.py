"""Explicitly enroll one independently authenticated public OS-update key."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

spec = importlib.util.spec_from_file_location('phios_enroll_verifier', Path(__file__).with_name('verify.py'))
assert spec is not None and spec.loader is not None
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


def gpg(home: Path, *args: str) -> bytes:
    result = subprocess.run(['/usr/bin/gpg', '--no-options', '--homedir', str(home), '--batch',
        '--no-auto-key-retrieve', '--auto-key-locate', 'clear', *args], env=verify.ENV, capture_output=True, timeout=60)
    if result.returncode:
        raise ValueError('public key parsing/import/export failed; no trust enrolled')
    return result.stdout


def public_key(home: Path, captured: Path, fingerprint: str, *, now: datetime) -> bytes:
    if re.fullmatch(r'(?:[0-9A-F]{40}|[0-9A-F]{64})', fingerprint) is None:
        raise ValueError('independently authenticated full uppercase fingerprint required')
    rows = [line.split(':') for line in gpg(home, '--with-colons', '--import-options', 'show-only',
        '--dry-run', '--import', str(captured)).decode().splitlines()]
    if any(row[0].startswith(('sec', 'ssb')) for row in rows):
        raise ValueError('secret key material refused; provide only an exported public key')
    if len([row for row in rows if row[0] == 'pub']) != 1:
        raise ValueError('exactly one public primary key required')
    found = next((row[9] for row in rows if row[0] == 'fpr'), '')
    if found != fingerprint:
        raise ValueError('public key differs from independently authenticated fingerprint')
    gpg(home, '--import', str(captured))
    rows = [line.split(':') for line in gpg(home, '--with-colons', '--list-keys', fingerprint).decode().splitlines()]
    primary = [row for row in rows if row[0] == 'pub']
    if (len(primary) != 1 or primary[0][1] in ('r', 'e', 'd') or
            int(primary[0][5]) > int(now.timestamp()) + 300 or
            (primary[0][6] not in ('', '0') and int(primary[0][6]) <= int(now.timestamp()))):
        raise ValueError('expired, revoked, disabled or future primary key refused')
    if any(line.split(':')[0].startswith(('sec', 'ssb')) for line in
            gpg(home, '--with-colons', '--list-secret-keys').decode().splitlines()):
        raise ValueError('secret keys must never enter enrollment')
    exported = gpg(home, '--export', fingerprint)
    if not 0 < len(exported) <= 8 * 1024**2:
        raise ValueError('bounded public key export required')
    return exported


def existing() -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for path in [verify.TRUST, verify.KEYRING]:
        result[path.name] = (hashlib.sha256(verify.protected_file(path, maximum=8 * 1024**2)).hexdigest()
            if path.exists() or path.is_symlink() else None)
    return result


def phrase(plan: dict[str, Any]) -> str:
    return 'ENROLL /etc/phios ' + hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def write(path: Path, data: bytes) -> None:
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(data)
        os.fchmod(handle.fileno(), 0o644)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-key', required=True, type=Path)
    parser.add_argument('--fingerprint', required=True)
    parser.add_argument('--plan', action='store_true')
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise ValueError('root-owned enrollment command requires sudo')
        source = verify.protected_file(verify.SOURCE).decode().strip()
        if re.fullmatch(r'[0-9a-f]{40}', source) is None:
            raise ValueError('packaged PhiOS source identity required')
        with tempfile.TemporaryDirectory(prefix='phios-key-enrollment-') as temporary:
            private = Path(temporary)
            home = private / 'gnupg'
            home.mkdir(mode=0o700)
            try:
                directory = os.open(args.public_key.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    verify.capture(directory, args.public_key.name, private / 'public-key', maximum=8 * 1024**2)
                finally:
                    os.close(directory)
                exported = public_key(home, private / 'public-key', args.fingerprint, now=datetime.now(UTC))
                before = existing()
                policy = {'schema_version': 'phios.os-update-trust.v1', 'channel': 'experimental',
                          'primary_fingerprint': args.fingerprint}
                plan = {'schema_version': 'phios.os-update-enrollment.v1', 'source_commit': source,
                    'public_key_sha256': hashlib.sha256(exported).hexdigest(), 'policy': policy,
                    'current_trust_hashes': before, 'release_ready': False}
                print(json.dumps(plan, indent=2, sort_keys=True), flush=True)
                if args.plan:
                    return 0
                if not sys.stdin.isatty() or not sys.stdout.isatty():
                    raise ValueError('interactive terminal review required; no unattended enrollment')
                print('Authenticate this full fingerprint through an independently trusted maintainer channel.\n'
                    'This explicit local administration changes update signing trust; a key file does not authenticate itself.\n'
                    'Type the exact reviewed phrase, or Ctrl-C to cancel:\n' + phrase(plan), flush=True)
                if input('> ') != phrase(plan):
                    raise ValueError('confirmation did not match; no signing trust changed')
                if existing() != before or public_key(home, private / 'public-key', args.fingerprint, now=datetime.now(UTC)) != exported:
                    raise ValueError('public key validity or current trust changed after review')
                verify.TRUST.parent.mkdir(mode=0o755, exist_ok=True)
                for parent in reversed(verify.TRUST.parents):
                    info = parent.lstat()
                    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                        raise ValueError('unsafe signing trust directory')
                write(verify.KEYRING, exported)
                write(verify.TRUST, (json.dumps(policy, sort_keys=True) + '\n').encode())
                if verify.load_trust() != (policy, exported):
                    raise ValueError('enrolled trust readback failed; preserve evidence and re-enroll')
                print(json.dumps({'trust_enrolled': True, 'primary_fingerprint': args.fingerprint,
                    'release_ready': False}, sort_keys=True))
            finally:
                subprocess.run(['/usr/bin/gpgconf', '--homedir', str(home), '--kill', 'all'],
                               env=verify.ENV, capture_output=True, timeout=15)
        return 0
    except (KeyboardInterrupt, EOFError):
        print('Enrollment cancelled; inspect current trust if writes had begun.')
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print('Key enrollment held: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
