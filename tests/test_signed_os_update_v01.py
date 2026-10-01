from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

import pytest

FILE = Path(__file__).resolve().parents[1] / 'packaging/linux/updates/verify.py'
spec = importlib.util.spec_from_file_location('phios_os_update_verifier', FILE)
assert spec is not None and spec.loader is not None
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)
BASE = [{'name': 'linux', 'version': '6.18-1'}, {'name': 'phios', 'version': '1.0.0-1'}]
CONTENT = b'public disposable package-signature fixture, not a deployable package'
FILENAME = 'phios-1.0.0-2-any.pkg.tar.xz'


def manifest() -> dict[str, Any]:
    now = datetime.now(UTC)
    return {'schema_version': 'phios.os-package-update.v1', 'channel': 'experimental',
        'architecture': 'x86_64', 'from_source_commit': 'a' * 40, 'source_commit': 'b' * 40,
        'base_sequence': 0, 'sequence': 1, 'created_at': now.isoformat(),
        'expires_at': (now + timedelta(days=1)).isoformat(), 'arch_snapshot': '2026/09/30',
        'state_schemas': dict(verify.SCHEMAS), 'base_packages': copy.deepcopy(BASE),
        'target_packages': [BASE[0], {'name': 'phios', 'version': '1.0.0-2'}],
        'packages': [{'name': 'phios', 'version': '1.0.0-2', 'filename': FILENAME,
                     'sha256': hashlib.sha256(CONTENT).hexdigest(), 'size': len(CONTENT)}]}


@pytest.mark.parametrize('case', ['future-schema', 'boolean-schema', 'wrong-source', 'replay',
    'boolean-sequence', 'expired', 'future', 'unbounded', 'timezone', 'inventory', 'removal',
    'omitted-change', 'path', 'duplicate', 'extra-field', 'oversized', 'bad-date'])
def test_invalid_transitions_are_held_before_signature_or_package_use(case: str) -> None:
    payload = manifest()
    if case == 'future-schema':
        payload['state_schemas']['memory'] = 2
    elif case == 'boolean-schema':
        payload['state_schemas']['memory'] = True
    elif case == 'wrong-source':
        payload['from_source_commit'] = 'c' * 40
    elif case == 'replay':
        payload['sequence'] = 0
    elif case == 'boolean-sequence':
        payload['sequence'] = True
    elif case == 'expired':
        payload['expires_at'] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    elif case == 'future':
        payload['created_at'] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    elif case == 'unbounded':
        payload['expires_at'] = (datetime.now(UTC) + timedelta(days=100)).isoformat()
    elif case == 'timezone':
        payload['created_at'] = '2026-09-30T00:00:00'
    elif case == 'inventory':
        payload['base_packages'][0]['version'] = '6.17-1'
    elif case == 'removal':
        payload['target_packages'].pop(0)
    elif case == 'omitted-change':
        payload['target_packages'][0] = {'name': 'linux', 'version': '6.19-1'}
    elif case == 'path':
        payload['packages'][0]['filename'] = '../' + FILENAME
    elif case == 'duplicate':
        payload['packages'].append(payload['packages'][0])
    elif case == 'extra-field':
        payload['auto_promote'] = True
    elif case == 'oversized':
        payload['packages'][0]['size'] = 3 * 1024**3
    elif case == 'bad-date':
        payload['arch_snapshot'] = '2026/02/31'
    with pytest.raises(ValueError):
        verify.validate_manifest(payload, source='a' * 40, sequence=0, installed=BASE, now=datetime.now(UTC))


@pytest.mark.parametrize('data', [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}'])
def test_ambiguous_json_is_held(data: bytes) -> None:
    with pytest.raises(ValueError):
        verify.strict_json(data)


def test_private_capture_survives_later_bundle_replacement(tmp_path: Path) -> None:
    bundle = tmp_path / 'bundle'
    bundle.mkdir()
    source = bundle / FILENAME
    source.write_bytes(CONTENT)
    directory = os.open(bundle, os.O_RDONLY | os.O_DIRECTORY)
    try:
        destination = tmp_path / 'private'
        result = verify.capture(directory, FILENAME, destination, maximum=len(CONTENT))
        source.write_bytes(b'changed after verification')
        assert destination.read_bytes() == CONTENT
        assert result == {'sha256': hashlib.sha256(CONTENT).hexdigest(), 'size': len(CONTENT)}
        assert destination.stat().st_mode & 0o777 == 0o600
    finally:
        os.close(directory)


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'fifo'])
def test_nonregular_or_alias_inputs_are_held(tmp_path: Path, kind: str) -> None:
    target = tmp_path / 'target'
    target.write_bytes(CONTENT)
    name = tmp_path / FILENAME
    if kind == 'symlink':
        name.symlink_to(target)
    elif kind == 'hardlink':
        os.link(target, name)
    else:
        os.mkfifo(name)
    directory = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises((OSError, ValueError)):
            verify.capture(directory, FILENAME, tmp_path / 'private', maximum=len(CONTENT))
        assert not (tmp_path / 'private').exists()
    finally:
        os.close(directory)


@pytest.fixture(scope='module')
def signing_keys(tmp_path_factory: pytest.TempPathFactory) -> Iterator[list[tuple[Path, str, bytes]]]:
    keys = []
    homes = []
    try:
        for label in ['accepted', 'untrusted']:
            home = tmp_path_factory.mktemp('phios-disposable-key-' + label)
            home.chmod(0o700)
            homes.append(home)
            # These ephemeral keys are never retained or supplied to a release.
            subprocess.run(['/usr/bin/gpg', '--no-options', '--homedir', str(home), '--batch',
                '--pinentry-mode', 'loopback', '--passphrase', '', '--quick-generate-key',
                f'PhiOS Disposable Test {label} <{label}@example.invalid>', 'ed25519', 'sign', '1d'],
                check=True, capture_output=True, timeout=60)
            listing = subprocess.check_output(['/usr/bin/gpg', '--no-options', '--homedir', str(home),
                '--with-colons', '--list-keys'], text=True)
            fingerprint = next(row.split(':')[9] for row in listing.splitlines() if row.startswith('fpr:'))
            public = subprocess.check_output(['/usr/bin/gpg', '--no-options', '--homedir', str(home), '--export', fingerprint])
            keys.append((home, fingerprint, public))
        yield keys
    finally:
        for home in homes:
            subprocess.run(['gpgconf', '--homedir', str(home), '--kill', 'all'], capture_output=True, timeout=15)


def sign(home: Path, path: Path) -> None:
    subprocess.run(['/usr/bin/gpg', '--no-options', '--homedir', str(home), '--batch', '--yes',
        '--pinentry-mode', 'loopback', '--passphrase', '', '--detach-sign', str(path)],
        check=True, capture_output=True, timeout=30)


@pytest.mark.parametrize('case', ['valid', 'manifest-tamper', 'package-tamper', 'wrong-key', 'missing-signature', 'wrong-pin'])
def test_real_detached_signatures_and_pinned_identity(
    tmp_path: Path, signing_keys: list[tuple[Path, str, bytes]], case: str,
) -> None:
    home, fingerprint, public = signing_keys[0]
    bundle = tmp_path / 'bundle'
    bundle.mkdir()
    payload = manifest()
    data = bundle / 'manifest.json'
    data.write_text(json.dumps(payload))
    package = bundle / FILENAME
    package.write_bytes(CONTENT)
    signer = signing_keys[1][0] if case == 'wrong-key' else home
    sign(signer, data)
    sign(signer, package)
    if case == 'manifest-tamper':
        data.write_text(json.dumps({**payload, 'source_commit': 'c' * 40}))
    elif case == 'package-tamper':
        package.write_bytes(b'x' * len(CONTENT))
    elif case == 'missing-signature':
        (bundle / (FILENAME + '.sig')).unlink()
    elif case == 'wrong-pin':
        fingerprint = signing_keys[1][1]
    trust = ({'primary_fingerprint': fingerprint}, public)
    if case != 'valid':
        with pytest.raises((OSError, ValueError)):
            with verify.verified_bundle(bundle, source='a' * 40, sequence=0, installed=BASE, trust=trust):
                pytest.fail('invalid update must never reach a package consumer')
        return
    with verify.verified_bundle(bundle, source='a' * 40, sequence=0, installed=BASE, trust=trust) as (checked, private):
        assert checked == payload
        assert (private / FILENAME).read_bytes() == CONTENT
        package.write_bytes(b'replaced after verification')
        assert (private / FILENAME).read_bytes() == CONTENT
    assert not private.exists()
