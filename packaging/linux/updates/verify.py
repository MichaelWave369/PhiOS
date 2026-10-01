"""Verify a complete offline OS package transition; never install or mint authority."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

TRUST = Path('/etc/phios/os-update-trust.json')
KEYRING = Path('/etc/phios/os-update-keyring.gpg')
SOURCE = Path('/usr/share/phios/source-commit')
GENERATION = Path('/var/lib/phios/os-update-generation.json')
ENV = {'PATH': '/usr/bin', 'LANG': 'C.UTF-8', 'HOME': '/root'}
SCHEMAS = {'memory': 1, 'data_backup': 'phios.data-backup.v1'}
SHA = r'[0-9a-f]{64}'
PACKAGE = r'[a-z0-9][a-z0-9@._+\-]{0,127}'


def stable_identity(info: os.stat_result) -> tuple[int, ...]:
    # Reads can update atime. Compare ownership, identity and modification
    # fields, including nanoseconds, instead of mistaking atime for mutation.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def strict_json(data: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result

    def invalid(value: str) -> None:
        raise ValueError(f'non-finite JSON number: {value}')

    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)


def protected_file(path: Path, *, maximum: int = 2 * 1024**2) -> bytes:
    """Root-owned trust/installed metadata; inspect every ancestor without links."""
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('an absolute protected path is required')
    for parent in [*reversed(path.parents), path]:
        info = parent.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('trust or installed metadata has unsafe owner, permissions or links')
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > maximum:
        raise ValueError('protected metadata must be one bounded regular file')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as handle:
        if stable_identity(os.fstat(handle.fileno())) != stable_identity(info):
            raise ValueError('protected metadata changed during intake')
        data = handle.read(maximum + 1)
        if stable_identity(os.fstat(handle.fileno())) != stable_identity(info):
            raise ValueError('protected metadata changed during intake')
    if len(data) > maximum:
        raise ValueError('protected metadata exceeds its bound')
    return data


def load_trust() -> tuple[dict[str, Any], bytes]:
    policy = strict_json(protected_file(TRUST))
    if (not isinstance(policy, dict) or set(policy) != {'schema_version', 'primary_fingerprint', 'channel'} or
            policy['schema_version'] != 'phios.os-update-trust.v1' or policy['channel'] != 'experimental' or
            not isinstance(policy['primary_fingerprint'], str) or
            re.fullmatch(r'(?:[0-9A-F]{40}|[0-9A-F]{64})', policy['primary_fingerprint']) is None):
        raise ValueError('unsupported trust policy; maintainer enrollment is required')
    return policy, protected_file(KEYRING, maximum=8 * 1024**2)


def inventory(rows: Any) -> dict[str, str]:
    if not isinstance(rows, list) or not 1 <= len(rows) <= 20000:
        raise ValueError('complete bounded package inventory required')
    packages: dict[str, str] = {}
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'name', 'version'} or
                not isinstance(row['name'], str) or re.fullmatch(PACKAGE, row['name']) is None or
                not isinstance(row['version'], str) or not 1 <= len(row['version']) <= 256 or
                any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in row['version']) or
                row['name'] in packages):
            raise ValueError('invalid or duplicate package identity')
        packages[row['name']] = row['version']
    return packages


def validate_manifest(payload: Any, *, source: str, sequence: int, installed: list[dict[str, str]],
                      now: datetime) -> dict[str, Any]:
    keys = {'schema_version', 'channel', 'architecture', 'from_source_commit', 'source_commit',
            'base_sequence', 'sequence', 'created_at', 'expires_at', 'arch_snapshot',
            'state_schemas', 'base_packages', 'target_packages', 'packages'}
    if not isinstance(payload, dict) or set(payload) != keys:
        raise ValueError('unknown update manifest fields or schema')
    if (payload['schema_version'] != 'phios.os-package-update.v1' or payload['channel'] != 'experimental' or
            payload['architecture'] != 'x86_64' or payload['state_schemas'] != SCHEMAS or
            type(payload['state_schemas'].get('memory')) is not int):
        raise ValueError('unsupported channel, architecture or state schema; no implicit migration')
    if (payload['from_source_commit'] != source or re.fullmatch(r'[0-9a-f]{40}', source) is None or
            not isinstance(payload['source_commit'], str) or
            re.fullmatch(r'[0-9a-f]{40}', payload['source_commit']) is None or
            type(payload['base_sequence']) is not int or payload['base_sequence'] != sequence or
            type(payload['sequence']) is not int or payload['sequence'] != sequence + 1):
        raise ValueError('stale, replayed or wrong-source update transition')
    if not isinstance(payload['arch_snapshot'], str) or re.fullmatch(r'20\d\d/\d\d/\d\d', payload['arch_snapshot']) is None:
        raise ValueError('exact Arch snapshot is required')
    datetime.strptime(payload['arch_snapshot'], '%Y/%m/%d')
    try:
        created, expires = [datetime.fromisoformat(payload[key]) for key in ['created_at', 'expires_at']]
    except (TypeError, ValueError) as exc:
        raise ValueError('invalid update validity window') from exc
    if (created.tzinfo is None or expires.tzinfo is None or created > now + timedelta(minutes=5) or
            not created < expires or not now < expires or expires - created > timedelta(days=90)):
        raise ValueError('expired, future or unbounded update validity window')
    before, after = inventory(payload['base_packages']), inventory(payload['target_packages'])
    if before != inventory(installed) or not before.keys() <= after.keys():
        raise ValueError('update requires the exact base inventory; removals are unsupported')
    rows = payload['packages']
    if not isinstance(rows, list) or not 1 <= len(rows) <= 2000:
        raise ValueError('bounded signed package set required')
    names: set[str] = set()
    files: set[str] = set()
    size = 0
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'name', 'version', 'filename', 'sha256', 'size'} or
                not isinstance(row['name'], str) or row['name'] not in after or row['name'] in names or
                row['version'] != after[row['name']] or not isinstance(row['filename'], str) or
                re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9@._+\-]{0,240}\.pkg\.tar\.(zst|xz)', row['filename']) is None or
                row['filename'] in files or not isinstance(row['sha256'], str) or
                re.fullmatch(SHA, row['sha256']) is None or type(row['size']) is not int or
                not 0 < row['size'] <= 2 * 1024**3):
            raise ValueError('invalid, repeated or unsafe update package')
        names.add(row['name'])
        files.add(row['filename'])
        size += row['size']
    if size > 16 * 1024**3 or any(before.get(name) != version and name not in names for name, version in after.items()):
        raise ValueError('package set exceeds its bound or omits a target change')
    return payload


def capture(directory: int, name: str, destination: Path, *, maximum: int) -> dict[str, Any]:
    """Copy untrusted bytes once; verify and later use only this private copy."""
    if Path(name).name != name or name.startswith('-'):
        raise ValueError('unsafe bundle filename')
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    digest = hashlib.sha256()
    total = 0
    with os.fdopen(fd, 'rb') as reader:
        info = os.fstat(reader.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= maximum:
            raise ValueError('bundle input is not a bounded, singly linked regular file')
        out = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(out, 'wb') as writer:
            for data in iter(lambda: reader.read(1024**2), b''):
                total += len(data)
                if total > maximum:
                    raise ValueError('bundle input grew beyond its bound')
                writer.write(data)
                digest.update(data)
            writer.flush()
            os.fsync(writer.fileno())
        if stable_identity(os.fstat(reader.fileno())) != stable_identity(info) or total != info.st_size:
            raise ValueError('bundle input changed during capture')
    return {'sha256': digest.hexdigest(), 'size': total}


def verify_signature(home: Path, signature: Path, content: Path, fingerprint: str, *, now: datetime) -> None:
    result = subprocess.run(['/usr/bin/gpg', '--no-options', '--homedir', str(home), '--batch',
              '--no-auto-key-retrieve', '--auto-key-locate', 'clear', '--status-fd', '1', '--verify',
              str(signature), str(content)], env=ENV, capture_output=True, text=True, timeout=60)
    statuses = [line.split()[1:] for line in result.stdout.splitlines() if line.startswith('[GNUPG:] ')]
    refused = {'BADSIG', 'ERRSIG', 'EXPSIG', 'EXPKEYSIG', 'REVKEYSIG', 'KEYEXPIRED', 'SIGEXPIRED', 'NO_PUBKEY', 'FAILURE'}
    valid = [row[1:] for row in statuses if row[0] == 'VALIDSIG']
    if result.returncode or any(row[0] in refused for row in statuses) or len(valid) != 1:
        raise ValueError('signature is missing, invalid, expired, revoked or ambiguous')
    row = valid[0]
    if (len(row) < 9 or (row[9] if len(row) > 9 else row[0]) != fingerprint or
            row[7] not in {'8', '9', '10'} or int(row[2]) > int(now.timestamp()) + 300 or
            (int(row[3]) != 0 and int(row[3]) <= int(now.timestamp()))):
        raise ValueError('signature signer, digest or validity does not match pinned trust')


@contextmanager
def verified_bundle(bundle: Path, *, source: str, sequence: int, installed: list[dict[str, str]],
                    trust: tuple[dict[str, Any], bytes] | None = None,
                    now: datetime | None = None) -> Iterator[tuple[dict[str, Any], Path]]:
    """Caller must keep this context alive through any eventual package use."""
    policy, public_keys = trust if trust is not None else load_trust()
    now = now or datetime.now(UTC)
    with tempfile.TemporaryDirectory(prefix='phios-verified-update-') as temporary:
        private = Path(temporary)
        home = private / 'gnupg'
        home.mkdir(mode=0o700)
        keys = private / 'public-keys.gpg'
        keys.write_bytes(public_keys)
        keys.chmod(0o600)
        subprocess.run(['/usr/bin/gpg', '--no-options', '--homedir', str(home), '--batch', '--import', str(keys)],
                       env=ENV, capture_output=True, check=True, timeout=60)
        directory = os.open(bundle, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            capture(directory, 'manifest.json', private / 'manifest.json', maximum=2 * 1024**2)
            capture(directory, 'manifest.json.sig', private / 'manifest.json.sig', maximum=65536)
            verify_signature(home, private / 'manifest.json.sig', private / 'manifest.json', policy['primary_fingerprint'], now=now)
            payload = validate_manifest(strict_json((private / 'manifest.json').read_bytes()),
                        source=source, sequence=sequence, installed=installed, now=now)
            for package in payload['packages']:
                filename = package['filename']
                identity = capture(directory, filename, private / filename, maximum=package['size'])
                if identity != {'sha256': package['sha256'], 'size': package['size']}:
                    raise ValueError('signed package hash or length mismatch')
                capture(directory, filename + '.sig', private / (filename + '.sig'), maximum=65536)
                verify_signature(home, private / (filename + '.sig'), private / filename, policy['primary_fingerprint'], now=now)
        finally:
            os.close(directory)
        yield payload, private


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    args = parser.parse_args()
    try:
        source = protected_file(SOURCE).decode().strip()
        sequence = 0
        if GENERATION.exists():
            generation = strict_json(protected_file(GENERATION))
            if (set(generation) != {'schema_version', 'sequence', 'source_commit'} or
                    generation['schema_version'] != 'phios.os-update-generation.v1' or
                    generation['source_commit'] != source or type(generation['sequence']) is not int or generation['sequence'] < 0):
                raise ValueError('installed update generation is invalid')
            sequence = generation['sequence']
        result = subprocess.run(['/usr/bin/pacman', '-Q'], env=ENV, capture_output=True, text=True, check=True, timeout=30)
        installed = [dict(zip(['name', 'version'], row.split(), strict=True)) for row in result.stdout.splitlines()]
        with verified_bundle(args.bundle, source=source, sequence=sequence, installed=installed) as (payload, _private):
            print(json.dumps({'schema_version': 'phios.os-update-verification.v1',
                'source_commit': payload['source_commit'], 'sequence': payload['sequence'],
                'signed_package_count': len(payload['packages']), 'signed_bytes_verified': True,
                'installed': False, 'execution_authority': False, 'release_ready': False}, indent=2))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f'OS update verification held: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
