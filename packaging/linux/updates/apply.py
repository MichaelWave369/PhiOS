"""Apply a pinned signed offline transition to a staged experimental OS root."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def sibling(name: str) -> Any:
    # Isolated Python does not import the script directory. Load only these
    # fixed, packaged root-owned siblings, never a caller-provided module.
    spec = importlib.util.spec_from_file_location('phios_os_' + name, Path(__file__).with_name(name + '.py'))
    if spec is None or spec.loader is None:
        raise ValueError('packaged OS maintenance module missing')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


recover, verify = sibling('recover'), sibling('verify')


def packages(root: Path) -> list[dict[str, str]]:
    for name in ['var', 'var/lib', 'var/lib/pacman', 'var/lib/pacman/local']:
        recover.safe_directory(root / name)
    text = recover.run('pacman', '--dbpath', str(root / 'var/lib/pacman'), '-Q')
    rows = [dict(zip(['name', 'version'], line.split(), strict=True)) for line in text.splitlines()]
    verify.inventory(rows)
    return rows


def sequence(top: Path, source: str) -> int:
    value = recover.generation_record(top / '@root/var/lib/phios/os-update-generation.json', 'phios.os-update-generation.v1')
    anchor = recover.generation_record(top / '@snapshots/os-update-counter.json', 'phios.os-update-counter.v1')
    if value is None and anchor is None:
        return 0
    if (value is None or anchor is None or value['source_commit'] != source or anchor['source_commit'] != source or
            value['sequence'] != anchor['sequence']):
        raise ValueError('root and independent update counter differ; use explicit live recovery')
    return value['sequence']


def generated_file(root: Path, relative: str, data: bytes, *, mode: int = 0o600) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    recover.safe_directory(path.parent)
    if path.is_symlink():
        path.unlink()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(mode)


def supported_versions(payload: dict[str, Any], baseline: list[dict[str, str]]) -> None:
    before = verify.inventory(baseline)
    for row in payload['packages']:
        if row['name'] in before and int(recover.run('vercmp', row['version'], before[row['name']]).strip()) < 0:
            raise ValueError('package downgrades require explicit OS recovery, not update')


def execute(plan: dict[str, Any], payload: dict[str, Any], private: Path,
            trust: tuple[dict[str, Any], bytes]) -> dict[str, Any]:
    identity, generation = plan['disk'], plan['checkpoint_generation']
    # Recheck key enrollment and validity after terminal review; keep using the
    # captured, signature-verified package bytes, never reread the supplied bundle.
    if verify.load_trust() != trust:
        raise ValueError('signing trust changed after review')
    verify.validate_manifest(payload, source=plan['installed']['source_commit'], sequence=plan['base_sequence'],
        installed=plan['base_packages'], now=datetime.now(UTC))
    for row in payload['packages']:
        verify.verify_signature(private / 'gnupg', private / (row['filename'] + '.sig'), private / row['filename'],
            trust[0]['primary_fingerprint'], now=datetime.now(UTC))
    supported_versions(payload, plan['base_packages'])
    recover.execute(identity, 'checkpoint', generation, {'installed': plan['installed'], 'boot_files': plan['boot_files']})
    with recover.mounted(identity, writable=True) as (top, esp):
        current = recover.installed(top, identity)
        if (current != plan['installed'] or packages(top / '@root') != plan['base_packages'] or
                sequence(top, current['source_commit']) != plan['base_sequence'] or
                recover.boot_inventory(esp) != plan['boot_files']):
            raise ValueError('installed source, inventory, generation or boot files changed after review')
        recover.ensure_no_active_authority(top, current['install_receipt']['plan']['username'])
        folder = top / '@snapshots/recovery' / generation
        journal = {'schema_version': 'phios.os-package-update-transaction.v1', 'generation': generation,
            'manifest_sha256': plan['manifest_sha256'], 'source_commit': payload['source_commit'],
            'sequence': payload['sequence'], 'stage': 'preparing staged root', 'activated': False,
            'atomic': False, 'authority_restored': False, 'release_ready': False}
        token = uuid.uuid4().hex
        staged, previous = top / ('@update-' + token), top / ('@previous-' + token)
        journal.update(staged_root=staged.name, previous_root=previous.name)
        recover.write_json(folder / 'update-transaction.json', journal)
        staged_mounted = False
        try:
            recover.run('btrfs', 'subvolume', 'snapshot', str(top / '@root'), str(staged))
            # arch-chroot/mkinitcpio need the staged root to be an actual
            # mountpoint so root filesystem detection sees Btrfs correctly.
            recover.run('mount', '--bind', str(staged), str(staged))
            staged_mounted = True
            inputs = staged / '.phios-update-inputs'
            inputs.mkdir(mode=0o700)
            (inputs / 'cache').mkdir(mode=0o700)
            (inputs / 'gnupg').mkdir(mode=0o700)
            generated_file(inputs, 'public-keys.gpg', trust[1])
            generated_file(inputs, 'ownertrust.txt', (trust[0]['primary_fingerprint'] + ':6:\n').encode())
            generated_file(inputs, 'gnupg/gpg.conf', b'no-auto-key-retrieve\nauto-key-locate clear\n')
            generated_file(inputs, 'pacman.conf', b'[options]\nArchitecture = x86_64\n'
                b'SigLevel = Required DatabaseOptional\nLocalFileSigLevel = Required\n'
                b'GPGDir = /.phios-update-inputs/gnupg\nCacheDir = /.phios-update-inputs/cache\n')
            for row in payload['packages']:
                for filename in [row['filename'], row['filename'] + '.sig']:
                    shutil.copyfile(private / filename, inputs / filename)
                    (inputs / filename).chmod(0o600)
                with (inputs / row['filename']).open('rb') as handle:
                    if hashlib.file_digest(handle, 'sha256').hexdigest() != row['sha256']:
                        raise ValueError('captured package changed before staged installation')
            recover.run('rsync', '-r', '--exclude=/' + recover.ENTROPY, str(esp) + '/', str(staged / 'boot') + '/')
            try:
                recover.run('arch-chroot', str(staged), 'gpg', '--no-options', '--homedir', '/.phios-update-inputs/gnupg',
                    '--batch', '--import', '/.phios-update-inputs/public-keys.gpg')
                recover.run('arch-chroot', str(staged), 'gpg', '--no-options', '--homedir', '/.phios-update-inputs/gnupg',
                    '--batch', '--import-ownertrust', '/.phios-update-inputs/ownertrust.txt')
                journal['stage'] = 'installing signed packages in staged root; active root unchanged'
                recover.write_json(folder / 'update-transaction.json', journal)
                recover.run('arch-chroot', str(staged), 'pacman', '--config', '/.phios-update-inputs/pacman.conf',
                    '-U', '--noconfirm', *['/.phios-update-inputs/' + row['filename'] for row in payload['packages']])
            finally:
                # GnuPG agents retain their chroot. Reap only this private
                # staging home's agents before unmounting the selected disk.
                recover.run('arch-chroot', str(staged), 'gpgconf', '--homedir', '/.phios-update-inputs/gnupg', '--kill', 'all')
            if verify.inventory(packages(staged)) != verify.inventory(payload['target_packages']):
                raise ValueError('staged full inventory differs from the signed target')
            if recover.regular(staged / 'usr/share/phios/source-commit').decode().strip() != payload['source_commit']:
                raise ValueError('staged PhiOS source identity differs from the signed target')
            kernels = list((staged / 'usr/lib/modules').glob('*/vmlinuz'))
            if len(kernels) != 1:
                raise ValueError('exactly one staged Linux kernel is required')
            shutil.copyfile(kernels[0], staged / 'boot/vmlinuz-linux')
            recover.run('arch-chroot', str(staged), 'mkinitcpio', '-P')
            for relative in ['EFI/BOOT/BOOTX64.EFI', 'EFI/systemd/systemd-bootx64.efi']:
                shutil.copyfile(staged / 'usr/lib/systemd/boot/efi/systemd-bootx64.efi', staged / 'boot' / relative)
            generated_file(staged, 'etc/pacman.d/mirrorlist',
                f'Server = https://archive.archlinux.org/repos/{payload["arch_snapshot"]}/$repo/os/$arch\n'.encode(), mode=0o644)
            generated_file(staged, 'etc/phios/os-update-trust.json', json.dumps(trust[0], sort_keys=True).encode(), mode=0o644)
            generated_file(staged, 'etc/phios/os-update-keyring.gpg', trust[1], mode=0o644)
            recover.write_json(staged / 'var/lib/phios/os-update-generation.json', {
                'schema_version': 'phios.os-update-generation.v1', 'sequence': payload['sequence'],
                'source_commit': payload['source_commit']})
            journal['target_boot_files'] = recover.boot_inventory(staged / 'boot')
            target_efi = folder / 'efi-target'
            target_efi.mkdir(mode=0o700)
            recover.run('rsync', '-r', str(staged / 'boot') + '/', str(target_efi) + '/')
            shutil.rmtree(inputs)
            for path in (staged / 'boot').iterdir():
                shutil.rmtree(path) if path.is_dir() else path.unlink()
            recover.run('umount', str(staged))
            staged_mounted = False
            journal['stage'] = 'switching root; live recovery may be required'
            recover.write_json(folder / 'update-transaction.json', journal)
            recover.write_json(top / '@snapshots/os-update-counter.json', {
                'schema_version': 'phios.os-update-counter.v1', 'sequence': payload['sequence'],
                'source_commit': payload['source_commit']})
            recover.run('btrfs', 'filesystem', 'sync', str(top))
            os.rename(top / '@root', previous)
            recover.run('btrfs', 'filesystem', 'sync', str(top))
            os.rename(staged, top / '@root')
            recover.run('btrfs', 'filesystem', 'sync', str(top))
            journal['stage'] = 'switching matched EFI; do not reboot'
            recover.write_json(folder / 'update-transaction.json', journal)
            recover.run('rsync', '-r', '--delete', '--exclude=/' + recover.ENTROPY, str(target_efi) + '/', str(esp) + '/')
            (esp / recover.ENTROPY).unlink(missing_ok=True)
            if recover.boot_inventory(esp) != journal['target_boot_files']:
                raise ValueError('updated EFI files failed verification; use live recovery checkpoint')
            os.sync()
            journal.update(stage='activated; disk-only boot remains unqualified', activated=True)
            recover.write_json(folder / 'update-transaction.json', journal)
            recover.run('btrfs', 'filesystem', 'sync', str(top))
            os.sync()
            return journal
        except BaseException as exc:
            journal['error'] = str(exc)
            recover.write_json(folder / 'update-transaction.json', journal)
            recover.run('btrfs', 'filesystem', 'sync', str(top))
            os.sync()
            raise
        finally:
            if staged_mounted:
                recover.run('umount', str(staged))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disk', required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--plan', action='store_true', help='Read-only target probe and signed-byte verification')
    args = parser.parse_args()
    try:
        if os.geteuid() != 0 or not Path('/run/archiso/bootmnt').is_dir() or not Path('/sys/firmware/efi').is_dir():
            raise ValueError('run the root-owned updater from PhiOS UEFI live media with the target offline')
        identity, trust = recover.inventory(args.disk), verify.load_trust()
        with recover.mounted(identity, writable=False) as (top, esp):
            installed = recover.installed(top, identity)
            recover.ensure_no_active_authority(top, installed['install_receipt']['plan']['username'])
            baseline, counter = packages(top / '@root'), sequence(top, installed['source_commit'])
            boot = recover.boot_inventory(esp)
        with verify.verified_bundle(args.bundle, source=installed['source_commit'], sequence=counter,
                installed=baseline, trust=trust) as (payload, private):
            supported_versions(payload, baseline)
            plan = {'schema_version': 'phios.os-update-plan.v1', 'operation': 'update', 'disk': identity,
                'installed': installed, 'base_sequence': counter, 'base_packages': baseline, 'boot_files': boot,
                'signed_transition': payload, 'signer': trust[0]['primary_fingerprint'],
                'manifest_sha256': hashlib.sha256((private / 'manifest.json').read_bytes()).hexdigest(),
                'checkpoint_generation': uuid.uuid4().hex, 'atomic': False, 'release_ready': False}
            print(json.dumps(plan, indent=2, sort_keys=True), flush=True)
            if args.plan:
                return 0
            if not sys.stdin.isatty() or not sys.stdout.isatty():
                raise ValueError('interactive terminal review required; no unattended bypass')
            print('A matched recovery checkpoint is created first. Root/EFI activation is not atomic.\n'
                'Keep live recovery media and a separate verified data backup.\n'
                'Type the exact signed transition confirmation, or Ctrl-C to cancel:\n' + recover.phrase(plan), flush=True)
            if input('> ') != recover.phrase(plan):
                raise ValueError('confirmation did not match; no target writes performed')
            print(json.dumps(execute(plan, payload, private, trust), indent=2, sort_keys=True))
        return 0
    except (KeyboardInterrupt, EOFError):
        print('OS update cancelled; preserve transaction evidence if writes had begun.')
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f'OS update held: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
