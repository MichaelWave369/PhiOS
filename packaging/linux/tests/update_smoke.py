"""CI-only signed package and interrupted-staging qualification fixture.

Never included in normal images. Private signing keys exist only in the live
VM's volatile /run. Only the named, fresh 32-GiB disposable target is supported.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

spec = importlib.util.spec_from_file_location('phios_ci_installer', '/usr/local/bin/phios-live-install-smoke.py')
assert spec is not None and spec.loader is not None
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
spec = importlib.util.spec_from_file_location('phios_ci_application', '/usr/lib/phios-updates/apply.py')
assert spec is not None and spec.loader is not None
apply = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apply)

PLAN = '@snapshots/phios-ci-qualification.json'
PACKAGE = 'phios-ci-update'
FILE = 'usr/share/' + PACKAGE + '/verified.txt'
CONTENT = b'authenticated disposable PhiOS package update\n'


def command(*args: str, **kwargs: Any) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, **kwargs)


@contextmanager
def disk(*, writable: bool = False) -> Iterator[tuple[Path, Path]]:
    identity = apply.recover.inventory('/dev/vda')
    if identity['serial_or_wwn'] != 'PHIOS_CI_BLANK' or identity['size_bytes'] != 32 * 1024**3:
        raise ValueError('signed-update fixture requires its exact disposable disk')
    with apply.recover.mounted(identity, writable=writable) as pair:
        yield pair


def state(top: Path, esp: Path) -> dict[str, Any]:
    root = top / '@root'
    source = (root / 'usr/share/phios/source-commit').read_text().strip()
    return {'source_commit': source, 'packages': apply.packages(root), 'sequence': apply.sequence(top, source),
            'boot_files': apply.recover.boot_inventory(esp)}


def signer(base: Path, label: str) -> tuple[Path, str, bytes]:
    home = base / label
    home.mkdir(mode=0o700)
    command('gpg', '--no-options', '--homedir', str(home), '--batch', '--pinentry-mode', 'loopback',
        '--passphrase', '', '--quick-generate-key', 'PhiOS Disposable ' + label + ' <ci@example.invalid>',
        'ed25519', 'sign', '1d')
    listing = command('gpg', '--no-options', '--homedir', str(home), '--with-colons', '--list-keys')
    fingerprint = next(row.split(':')[9] for row in listing.splitlines() if row.startswith('fpr:'))
    public = subprocess.check_output(['gpg', '--no-options', '--homedir', str(home), '--export', fingerprint])
    return home, fingerprint, public


def sign(home: Path, path: Path) -> None:
    command('gpg', '--no-options', '--homedir', str(home), '--batch', '--yes', '--pinentry-mode', 'loopback',
            '--passphrase', '', '--detach-sign', str(path))


def package(base: Path, name: str, *, missing_dependency: bool = False, interrupt: bool = False) -> Path:
    # Use Arch's actual package builder, including PKGINFO, BUILDINFO and MTREE.
    # Only this CI profile adds fakeroot. There are no network dependencies.
    work = Path(tempfile.mkdtemp(prefix='phios-ci-package-', dir='/home/phios'))
    try:
        work.chmod(0o700)
        (work / 'data').write_bytes(CONTENT)
        shutil.copyfile('/usr/share/licenses/phios/LICENSE', work / 'LICENSE')
        build = "pkgname=" + name + "\npkgver=1.0.0\npkgrel=1\narch=('any')\n" + \
            "pkgdesc='Disposable PhiOS qualification package'\nlicense=('MIT')\noptions=('!strip' '!debug')\n"
        if missing_dependency:
            build += "depends=('phios-ci-never-exists=999')\n"
        if interrupt:
            build += "install=interrupt.install\n"
            (work / 'interrupt.install').write_text('post_install() {\n'
                "  printf 'staged pacman hook reached\\n' > /.phios-ci-stage-in-progress\n"
                '  /usr/bin/sync\n  /usr/bin/sleep 600\n}\n')
        build += 'package() {\n  install -Dm644 data "$pkgdir/usr/share/$pkgname/verified.txt"\n' + \
            '  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"\n}\n'
        (work / 'PKGBUILD').write_text(build)
        for path in [work, *work.iterdir()]:
            os.chown(path, 1000, 1000)
        command('runuser', '-u', 'phios', '--', 'bash', '-c',
            'cd "$1"; exec makepkg --nodeps --force --noconfirm', 'phios-ci-build', str(work), timeout=120)
        archives = [path for path in work.glob('*.pkg.tar.*') if not path.name.endswith('.sig')]
        if len(archives) != 1:
            raise ValueError('actual makepkg output must be exactly one archive')
        target = base / archives[0].name
        shutil.copyfile(archives[0], target)
        return target
    finally:
        shutil.rmtree(work)


def bundle(base: Path, name: str, current: dict[str, Any], key: tuple[Path, str, bytes],
           *, missing_dependency: bool = False, interrupt: bool = False) -> Path:
    destination = base / ('bundle-' + name)
    destination.mkdir(mode=0o700)
    archive = package(destination, name, missing_dependency=missing_dependency, interrupt=interrupt)
    now = datetime.now(UTC)
    payload = {'schema_version': 'phios.os-package-update.v1', 'channel': 'experimental', 'architecture': 'x86_64',
        'from_source_commit': current['source_commit'], 'source_commit': current['source_commit'],
        'base_sequence': current['sequence'], 'sequence': current['sequence'] + 1,
        'created_at': now.isoformat(), 'expires_at': (now + timedelta(days=1)).isoformat(),
        'arch_snapshot': '2026/09/30', 'state_schemas': dict(apply.verify.SCHEMAS),
        'base_packages': current['packages'], 'target_packages': sorted([*current['packages'],
            {'name': name, 'version': '1.0.0-1'}], key=lambda row: row['name']),
        'packages': [{'name': name, 'version': '1.0.0-1', 'filename': archive.name,
            'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'size': archive.stat().st_size}]}
    manifest = destination / 'manifest.json'
    manifest.write_text(json.dumps(payload, sort_keys=True))
    sign(key[0], manifest)
    sign(key[0], archive)
    return destination


def initial() -> None:
    with tempfile.TemporaryDirectory(prefix='phios-ci-signing-', dir='/run') as temporary:
        base = Path(temporary)
        accepted, wrong = signer(base, 'accepted'), signer(base, 'untrusted')
        try:
            # Test-only manual enrollment into the volatile live environment;
            # no trust or private key was shipped by the production image.
            apply.generated_file(Path('/'), 'etc/phios/os-update-keyring.gpg', accepted[2], mode=0o644)
            apply.generated_file(Path('/'), 'etc/phios/os-update-trust.json', json.dumps({
                'schema_version': 'phios.os-update-trust.v1', 'channel': 'experimental',
                'primary_fingerprint': accepted[1]}).encode(), mode=0o644)
            with disk() as (top, esp):
                before = state(top, esp)
            valid = bundle(base, PACKAGE, before, accepted)
            for case in ['missing-signature', 'wrong-key', 'tampered', 'expired']:
                invalid = base / case
                shutil.copytree(valid, invalid)
                manifest = invalid / 'manifest.json'
                payload = json.loads(manifest.read_text())
                archive = invalid / payload['packages'][0]['filename']
                if case == 'missing-signature':
                    (invalid / (archive.name + '.sig')).unlink()
                elif case == 'wrong-key':
                    sign(wrong[0], manifest)
                    sign(wrong[0], archive)
                elif case == 'tampered':
                    data = bytearray(archive.read_bytes())
                    data[-1] ^= 1
                    archive.write_bytes(data)
                else:
                    payload.update(created_at=(datetime.now(UTC) - timedelta(days=1)).isoformat(),
                        expires_at=(datetime.now(UTC) - timedelta(hours=1)).isoformat())
                    manifest.write_text(json.dumps(payload, sort_keys=True))
                    sign(accepted[0], manifest)
                result = installer.drive_installer(cancel=False, update=invalid, reject=True, plan=True)
                if 'OS update held:' not in result:
                    raise ValueError('invalid signed bundle did not fail at the production update boundary')
                with disk() as (top, esp):
                    if state(top, esp) != before:
                        raise ValueError('rejected bundle changed active root or EFI')
                print('PHIOS_SIGNED_REFUSAL_OK:' + case, flush=True)
            installer.drive_installer(cancel=True, update=valid)
            with disk() as (top, esp):
                if state(top, esp) != before:
                    raise ValueError('cancelled signed update changed the active system')
            result = installer.drive_installer(cancel=False, update=valid)
            with disk() as (top, esp):
                current = state(top, esp)
                if current['sequence'] != 1 or (top / '@root' / FILE).read_bytes() != CONTENT:
                    raise ValueError('signed package or persistent generation was not actually installed')
                expected = sorted([*before['packages'], {'name': PACKAGE, 'version': '1.0.0-1'}], key=lambda row: row['name'])
                if current['packages'] != expected:
                    raise ValueError('actual installed inventory differs from the signed complete target')
                matches = [path for path in (top / '@snapshots/recovery').glob('*/update-transaction.json')
                           if json.loads(path.read_text()).get('activated') is True]
                if len(matches) != 1:
                    raise ValueError('exactly one successful update transaction required')
                generation = matches[0].parent.name
            installer.drive_installer(cancel=False, update=valid, reject=True, plan=True)
            with disk() as (top, esp):
                if state(top, esp) != current:
                    raise ValueError('replayed transition changed the active system')
            print('PHIOS_SIGNED_REFUSAL_OK:replay', flush=True)
            bad = bundle(base, 'phios-ci-bad-dependency', current, accepted, missing_dependency=True)
            result = installer.drive_installer(cancel=False, update=bad, reject=True)
            if 'phios-ci-never-exists' not in result or 'OS update held:' not in result:
                raise ValueError('missing dependency did not fail through actual pacman')
            with disk() as (top, esp):
                if state(top, esp) != current:
                    raise ValueError('failed staged dependency transaction changed active root or EFI')
            print('PHIOS_SIGNED_REFUSAL_OK:dependency', flush=True)
            interrupted = bundle(base, 'phios-ci-interrupt', current, accepted, interrupt=True)
            manifest_hash = hashlib.sha256((interrupted / 'manifest.json').read_bytes()).hexdigest()
            with disk(writable=True) as (top, _esp):
                apply.recover.write_json(top / PLAN, {'schema_version': 'phios.disposable-update-qualification.v1',
                    'stage': 'awaiting actual VM interruption', 'restore_generation': generation,
                    'before_interruption': current, 'interrupted_manifest_sha256': manifest_hash})
                command('btrfs', 'filesystem', 'sync', str(top))
                os.sync()
            print('PHIOS_SIGNED_UPDATE_OK:' + json.dumps({'generation': generation, 'sequence': 1,
                'signer': accepted[1], 'ephemeral_test_key': True}), flush=True)
            # The host kills this VM only after the actual pacman post_install
            # hook has written and synced its marker inside the staged root.
            installer.drive_installer(cancel=False, update=interrupted, interrupt=True)
            raise RuntimeError('host did not interrupt the actual staged package transaction')
        finally:
            for key in [accepted, wrong]:
                subprocess.run(['gpgconf', '--homedir', str(key[0]), '--kill', 'all'], capture_output=True, timeout=15)


def resume_or_restore() -> None:
    with disk() as (top, esp):
        plan = json.loads(apply.recover.regular(top / PLAN))
        if plan.get('schema_version') != 'phios.disposable-update-qualification.v1':
            raise ValueError('unsupported disposable fixture state')
        generation = plan['restore_generation']
        if plan['stage'] == 'awaiting actual VM interruption':
            if state(top, esp) != plan['before_interruption'] or (top / '@root/usr/share/phios-ci-interrupt/verified.txt').exists():
                raise ValueError('interrupted staging changed the active installed system')
            journals = [path for path in (top / '@snapshots/recovery').glob('*/update-transaction.json')
                if json.loads(path.read_text()).get('manifest_sha256') == plan['interrupted_manifest_sha256']]
            if len(journals) != 1:
                raise ValueError('interrupted transaction journal missing or ambiguous')
            journal = json.loads(journals[0].read_text())
            marker = top / journal['staged_root'] / '.phios-ci-stage-in-progress'
            if journal['activated'] is not False or not marker.is_file() or 'installing signed packages' not in journal['stage']:
                raise ValueError('interruption was not during actual staged pacman execution')
            source = plan['before_interruption']['source_commit']
            resumed = True
        elif plan['stage'] == 'ready for deliberate boot failure and recovery':
            resumed = False
        else:
            raise ValueError('unexpected disposable fixture stage')
    if resumed:
        with disk(writable=True) as (top, _esp):
            plan['stage'] = 'ready for deliberate boot failure and recovery'
            apply.recover.write_json(top / PLAN, plan)
            command('btrfs', 'filesystem', 'sync', str(top))
            os.sync()
        print('PHIOS_INTERRUPTED_UPDATE_HELD_OK', flush=True)
        print('PHIOS_OS_CHECKPOINT_OK:' + generation, flush=True)
        print('PHIOS_INSTALLED_DISK_OK:' + source, flush=True)
        return
    installer.drive_installer(cancel=True, recovery=['restore', '--generation', generation])
    print('PHIOS_OS_RESTORE_CANCEL_OK', flush=True)
    installer.drive_installer(cancel=False, recovery=['restore', '--generation', generation])
    with disk() as (top, _esp):
        source = (top / '@root/usr/share/phios/source-commit').read_text().strip()
        if apply.sequence(top, source) != 2 or (top / '@root' / FILE).exists():
            raise ValueError('recovery did not remove the added package and advance the independent counter')
        if (top / '@root/etc/phios/os-update-keyring.gpg').exists() or (top / '@root/etc/phios/os-update-trust.json').exists():
            raise ValueError('rolled-back signing trust remained active')
    print('PHIOS_SIGNED_UPDATE_RECOVERY_OK', flush=True)
    print('PHIOS_OS_RESTORE_OK:' + generation, flush=True)


if __name__ == '__main__':
    raise RuntimeError('fixture is invoked only by the exact disposable installer fixture')
