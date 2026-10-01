"""Offline matched Btrfs/EFI checkpoints for the experimental PhiOS installer."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

ENV = {'PATH': '/usr/bin', 'LANG': 'C.UTF-8', 'HOME': '/root'}
FORMAT = 'phios.os-checkpoint.v1'
SCHEMA = {'memory': 1, 'data_backup': 'phios.data-backup.v1'}
GEN = r'[0-9a-f]{32}'
ENTROPY = 'loader/random-seed'


def run(*args: str) -> str:
    command = shutil.which(args[0], path=ENV['PATH'])
    if command is None:
        raise ValueError(f'required program unavailable: {args[0]}')
    result = subprocess.run([command, *args[1:]], env=ENV, capture_output=True, text=True, timeout=600)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed (exit {result.returncode}): {result.stderr[-2000:]}')
    return result.stdout


def regular(path: Path, *, owner: int = 0, maximum: int = 2 * 1024**2) -> bytes:
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != owner or info.st_mode & 0o022 or
            info.st_nlink != 1 or info.st_size > maximum):
        raise ValueError('unsafe checkpoint/installed metadata file')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as handle:
        actual = os.fstat(handle.fileno())
        if (actual.st_dev, actual.st_ino, actual.st_size, actual.st_mtime_ns, actual.st_ctime_ns) != (
                info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns):
            raise ValueError('metadata changed during intake')
        data = handle.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError('metadata exceeds its bound')
    return data


def safe_directory(path: Path, *, owner: int = 0) -> None:
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != owner or info.st_mode & 0o022:
        raise ValueError('unsafe checkpoint/installed directory')


def write_json(path: Path, data: dict[str, Any]) -> None:
    safe_directory(path.parent)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(data, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def validate_disk(row: dict[str, Any], *, busy: bool) -> dict[str, Any]:
    path = row.get('path')
    if (not isinstance(path, str) or re.fullmatch(r'/dev/(sd[a-z]+|vd[a-z]+|nvme[0-9]+n[0-9]+|mmcblk[0-9]+)', path) is None or
            row.get('type') != 'disk' or row.get('ro') not in (False, 0) or row.get('pttype') != 'gpt' or
            type(row.get('size')) is not int or row['size'] < 16 * 1024**3 or busy):
        raise ValueError('an idle, canonical whole PhiOS installation disk is required')
    serial = row.get('serial') or row.get('wwn')
    if not isinstance(serial, str) or not serial.strip() or any(ord(c) < 32 or ord(c) == 127 for c in serial):
        raise ValueError('stable disk identity is required')
    children = row.get('children')
    suffix = 'p' if path[-1].isdigit() else ''
    if not isinstance(children, list) or len(children) != 2:
        raise ValueError('only the installer two-partition layout is supported')
    children = sorted(children, key=lambda item: item.get('path', ''))
    for index, (child, filesystem) in enumerate(zip(children, ['vfat', 'btrfs'], strict=True), start=1):
        if (child.get('path') != f'{path}{suffix}{index}' or child.get('type') != 'part' or
                child.get('fstype') != filesystem or child.get('children') or
                any(child.get('mountpoints') or []) or child.get('ro') not in (False, 0)):
            raise ValueError('partition identity, filesystem or mounted state is unsupported')
    if any(row.get('mountpoints') or []) or children[0].get('size') != 1024**3:
        raise ValueError('mounted target or unexpected ESP size')
    root_uuid, esp_uuid = children[1].get('uuid'), children[0].get('uuid')
    if (not isinstance(root_uuid, str) or re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', root_uuid) is None or
            not isinstance(esp_uuid, str) or re.fullmatch(r'[0-9A-F]{4}-[0-9A-F]{4}', esp_uuid) is None):
        raise ValueError('invalid installed filesystem UUID')
    return {'path': path, 'serial_or_wwn': serial.strip(), 'size_bytes': row['size'],
            'major_minor': row.get('maj:min'), 'root_uuid': root_uuid, 'esp_uuid': esp_uuid,
            'esp': children[0]['path'], 'system': children[1]['path']}


def inventory(device: str) -> dict[str, Any]:
    path = Path(device)
    if not path.is_absolute() or path.resolve() != path or not stat.S_ISBLK(path.stat().st_mode):
        raise ValueError('canonical real whole disk required')
    run('udevadm', 'settle')
    rows = json.loads(run('lsblk', '--json', '--bytes', '--paths', '--tree', '--output',
        'PATH,TYPE,SIZE,RO,SERIAL,WWN,MOUNTPOINTS,FSTYPE,PTTYPE,UUID,MAJ:MIN', device))['blockdevices']
    if len(rows) != 1:
        raise ValueError('ambiguous target')
    nodes = [rows[0], *rows[0].get('children', [])]
    mounted = {line.split()[2] for line in Path('/proc/self/mountinfo').read_text().splitlines()}
    swap_devices = {Path(line.split()[0]).stat().st_rdev for line in Path('/proc/swaps').read_text().splitlines()[1:]}
    busy = False
    for node in nodes:
        info = Path(node['path']).stat()
        number = f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}'
        sys_device = Path('/sys/dev/block') / number
        if (number != node.get('maj:min') or number in mounted or info.st_rdev in swap_devices or
                list((sys_device / 'holders').iterdir()) or list((sys_device / 'slaves').iterdir())):
            busy = True
    return validate_disk(rows[0], busy=busy)


@contextmanager
def mounted(identity: dict[str, Any], *, writable: bool) -> Iterator[tuple[Path, Path]]:
    if inventory(identity['path']) != identity:
        raise ValueError('disk changed after review; no target writes performed')
    workspace = Path(tempfile.mkdtemp(prefix='phios-recovery-', dir='/run'))
    top, esp = workspace / 'top', workspace / 'efi'
    top.mkdir(mode=0o700)
    esp.mkdir(mode=0o700)
    mounts: list[Path] = []
    try:
        options = 'rw,subvolid=5' if writable else 'ro,nologreplay,subvolid=5'
        run('mount', '-t', 'btrfs', '-o', options, identity['system'], str(top))
        mounts.append(top)
        # Multi-device Btrfs would cross the selected-disk boundary.
        if len(list((Path('/sys/fs/btrfs') / identity['root_uuid'] / 'devices').iterdir())) != 1:
            raise ValueError('multi-device Btrfs is unsupported')
        run('mount', '-t', 'vfat', '-o', ('rw' if writable else 'ro') + ',umask=0077', identity['esp'], str(esp))
        mounts.append(esp)
        yield top, esp
    finally:
        failures = []
        for path in reversed(mounts):
            try:
                run('umount', str(path))
            except (OSError, ValueError, RuntimeError) as exc:
                failures.append(str(exc))
        if failures:
            raise RuntimeError('recovery mounts remain active; preserve evidence and do not reboot: ' + '; '.join(failures))
        shutil.rmtree(workspace)


def boot_inventory(esp: Path, *, owner: int = 0) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    total = 0
    safe_directory(esp, owner=owner)
    for current, dirs, files in os.walk(esp, followlinks=False):
        directory = Path(current)
        for name in dirs:
            safe_directory(directory / name, owner=owner)
        for name in files:
            path = directory / name
            relative = path.relative_to(esp).as_posix()
            if relative == ENTROPY:
                continue
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != owner or info.st_nlink != 1:
                raise ValueError('EFI contents contain nonregular files or links')
            total += info.st_size
            if len(result) >= 512 or total > 1024**3:
                raise ValueError('EFI file inventory exceeds its bound')
            digest = hashlib.sha256()
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as handle:
                for chunk in iter(lambda: handle.read(1024**2), b''):
                    digest.update(chunk)
            result[relative] = {'size': info.st_size, 'sha256': digest.hexdigest()}
    if not {'vmlinuz-linux', 'initramfs-linux.img', 'initramfs-linux-fallback.img',
            'EFI/BOOT/BOOTX64.EFI', 'loader/entries/phios.conf'} <= result.keys():
        raise ValueError('matching installed kernel, initramfs and fallback EFI loader required')
    return result


def installed(top: Path, identity: dict[str, Any]) -> dict[str, Any]:
    for name in ['@root', '@home', '@log', '@snapshots']:
        safe_directory(top / name)
        run('btrfs', 'subvolume', 'show', str(top / name))
    root = top / '@root'
    for relative in ['var', 'var/lib', 'var/lib/phios', 'usr', 'usr/share', 'usr/share/phios']:
        safe_directory(root / relative)
    receipt = json.loads(regular(root / 'var/lib/phios/install-receipt.json'))
    target = receipt.get('plan', {}).get('target', {})
    source = regular(root / 'usr/share/phios/source-commit').decode().strip()
    if (receipt.get('schema_version') != 'phios.blank-disk-install.v1' or receipt.get('installed') is not True or
            receipt.get('root_uuid') != identity['root_uuid'] or receipt.get('esp_uuid') != identity['esp_uuid'] or
            target.get('serial_or_wwn') != identity['serial_or_wwn'] or target.get('size_bytes') != identity['size_bytes'] or
            re.fullmatch(r'[0-9a-f]{40}', source) is None):
        raise ValueError('selected disk does not match a supported PhiOS installation receipt')
    return {'source_commit': source, 'install_receipt': receipt}


def validate_checkpoint(data: Any, identity: dict[str, Any], generation: str) -> dict[str, Any]:
    keys = {'schema_version', 'generation', 'disk', 'source_commit', 'state_schemas', 'root_snapshot_uuid',
            'boot_files', 'installed', 'home_snapshot_restored', 'authority_restored', 'release_ready'}
    if (not isinstance(data, dict) or set(data) != keys or data['schema_version'] != FORMAT or
            data['generation'] != generation or re.fullmatch(GEN, generation) is None or
            data['disk'] != {key: identity[key] for key in ['serial_or_wwn', 'size_bytes', 'root_uuid', 'esp_uuid']} or
            data['state_schemas'] != SCHEMA or type(data['state_schemas'].get('memory')) is not int or
            not isinstance(data['source_commit'], str) or re.fullmatch(r'[0-9a-f]{40}', data['source_commit']) is None or
            any(data[key] is not False for key in ['home_snapshot_restored', 'authority_restored', 'release_ready'])):
        raise ValueError('unsupported or wrong-disk checkpoint')
    installed_info, boot = data['installed'], data['boot_files']
    if (not isinstance(data['root_snapshot_uuid'], str) or
            re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', data['root_snapshot_uuid']) is None or
            not isinstance(installed_info, dict) or set(installed_info) != {'source_commit', 'install_receipt'} or
            installed_info['source_commit'] != data['source_commit'] or not isinstance(installed_info['install_receipt'], dict) or
            installed_info['install_receipt'].get('schema_version') != 'phios.blank-disk-install.v1' or
            installed_info['install_receipt'].get('installed') is not True or
            installed_info['install_receipt'].get('root_uuid') != identity['root_uuid'] or
            installed_info['install_receipt'].get('esp_uuid') != identity['esp_uuid'] or
            not isinstance(installed_info['install_receipt'].get('plan'), dict) or
            not isinstance(installed_info['install_receipt']['plan'].get('username'), str) or
            re.fullmatch(r'[a-z][a-z0-9_-]{0,30}', installed_info['install_receipt']['plan']['username']) is None or
            not isinstance(boot, dict) or not 5 <= len(boot) <= 512):
        raise ValueError('invalid checkpoint root, installed identity or boot inventory')
    total = 0
    for name, file in boot.items():
        if (not isinstance(name, str) or Path(name).is_absolute() or '..' in Path(name).parts or
                not isinstance(file, dict) or set(file) != {'size', 'sha256'} or type(file['size']) is not int or
                file['size'] < 0 or not isinstance(file['sha256'], str) or re.fullmatch(r'[0-9a-f]{64}', file['sha256']) is None):
            raise ValueError('invalid checkpoint boot-file hash or path')
        total += file['size']
    if total > 1024**3:
        raise ValueError('checkpoint boot inventory exceeds its bound')
    return data


def snapshot_uuid(path: Path) -> str:
    text = run('btrfs', 'subvolume', 'show', str(path))
    matches = re.findall(r'^\s*UUID:\s*([0-9a-f-]{36})\s*$', text, flags=re.M)
    if len(matches) != 1:
        raise ValueError('ambiguous Btrfs snapshot identity')
    return matches[0]


def checkpoint_data(top: Path, esp: Path, identity: dict[str, Any], generation: str) -> tuple[dict[str, Any], Path]:
    folder = top / '@snapshots/recovery' / generation
    for path in [top / '@snapshots', folder.parent, folder, folder / 'root', folder / 'efi']:
        safe_directory(path)
    data = validate_checkpoint(json.loads(regular(folder / 'checkpoint.json')), identity, generation)
    if (run('btrfs', 'property', 'get', '-t', 's', str(folder / 'root'), 'ro').strip() != 'ro=true' or
            snapshot_uuid(folder / 'root') != data['root_snapshot_uuid'] or
            boot_inventory(folder / 'efi') != data['boot_files'] or
            regular(folder / 'root/usr/share/phios/source-commit').decode().strip() != data['source_commit']):
        raise ValueError('checkpoint root or matching boot files failed integrity checks')
    return data, folder


def ensure_no_active_authority(top: Path, username: str, *, uid: int = 1000) -> None:
    """Preserve current home data; refuse rollback over active/unknown authority."""
    if re.fullmatch(r'[a-z][a-z0-9_-]{0,30}', username) is None:
        raise ValueError('invalid installed account')
    home = top / '@home' / username
    safe_directory(home, owner=uid)
    # Custom state roots need a separately reviewed maintenance procedure.
    for relative in ['.local/state/phios', '.phios']:
        state = home / relative
        if not state.exists():
            continue
        for parent in [*reversed(state.parents), state]:
            if parent == home or parent.is_relative_to(home):
                safe_directory(parent, owner=uid)
        database = state / 'memory/canonical.sqlite3'
        published: list[dict[str, Any]] = []
        if database.exists():
            safe_directory(database.parent, owner=uid)
            info = database.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid or info.st_mode & 0o022 or
                    info.st_nlink != 1 or any(database.with_name(database.name + suffix).exists()
                                              for suffix in ['-wal', '-journal'])):
                raise ValueError('canonical state requires explicit data recovery before OS rollback')
            # The trusted live runtime validates schema, structural integrity,
            # record hashes and zero-authority outbox receipts without mutation.
            from phios.state_recovery import _database
            published = [row for row, is_published in _database(database) if is_published]
        spine = state / 'spine-v0.1'
        if not spine.exists():
            if published:
                raise ValueError('published memory has no matching active receipt ledger')
            continue
        safe_directory(spine, owner=uid)
        actual_receipts: list[dict[str, Any]] = []
        for path in spine.rglob('*'):
            if path.is_dir() and not path.is_symlink():
                safe_directory(path, owner=uid)
                continue
            if path.relative_to(spine).as_posix() != 'ledger/mandala-receipts.jsonl':
                raise ValueError('active spine/authority history requires data-only recovery and explicit revalidation first')
            # This allowlist never restores an old decision/binding/lease. The
            # memory ledger remains in current @home and must be zero-authority.
            rows = regular(path, owner=uid, maximum=128 * 1024**2).splitlines()
            for row in rows:
                value = json.loads(row)
                if (not isinstance(value, dict) or not isinstance(value.get('operation_id'), str) or
                        value.get('action_authority') is not False or value.get('execution_authority') is not False):
                    raise ValueError('memory history contains authority; recovery held')
                actual_receipts.append(value)
        if sorted(actual_receipts, key=lambda row: row['operation_id']) != sorted(published, key=lambda row: row['operation_id']):
            raise ValueError('memory receipt history does not match current canonical state')
    config = home / '.config/phios/memory.json'
    if config.exists():
        if json.loads(regular(config, owner=uid)).get('enabled') is not False:
            raise ValueError('disable memory configuration and review state before OS rollback')


def phrase(plan: dict[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return f"{plan['operation'].upper()} {plan['disk']['path']} {digest}"


def execute(identity: dict[str, Any], operation: str, generation: str, reviewed: dict[str, Any]) -> dict[str, Any]:
    with mounted(identity, writable=True) as (top, esp):
        # Recheck reviewed source/checkpoint/boot identity before creating a
        # checkpoint or activating restored root/EFI contents.
        if operation == 'checkpoint':
            current = installed(top, identity)
            if current != reviewed['installed'] or boot_inventory(esp) != reviewed['boot_files']:
                raise ValueError('installed source or boot files changed after review')
            ensure_no_active_authority(top, current['install_receipt']['plan']['username'])
            base = top / '@snapshots/recovery'
            if not base.exists():
                base.mkdir(mode=0o700)
            safe_directory(base)
            folder = base / generation
            folder.mkdir(mode=0o700)
            run('btrfs', 'subvolume', 'snapshot', '-r', str(top / '@root'), str(folder / 'root'))
            run('btrfs', 'subvolume', 'snapshot', '-r', str(top / '@home'), str(folder / 'home-forensic-only'))
            (folder / 'efi').mkdir(mode=0o700)
            run('rsync', '-r', '--exclude=/' + ENTROPY, str(esp) + '/', str(folder / 'efi') + '/')
            if boot_inventory(folder / 'efi') != reviewed['boot_files']:
                raise ValueError('checkpoint EFI copy differs from reviewed boot files')
            data = {'schema_version': FORMAT, 'generation': generation,
                'disk': {key: identity[key] for key in ['serial_or_wwn', 'size_bytes', 'root_uuid', 'esp_uuid']},
                'source_commit': current['source_commit'], 'state_schemas': SCHEMA,
                'root_snapshot_uuid': snapshot_uuid(folder / 'root'), 'boot_files': reviewed['boot_files'],
                'installed': current, 'home_snapshot_restored': False, 'authority_restored': False, 'release_ready': False}
            write_json(folder / 'checkpoint.json', data)
            run('btrfs', 'filesystem', 'sync', str(top))
            os.sync()
            return data
        data, folder = checkpoint_data(top, esp, identity, generation)
        if data != reviewed['checkpoint']:
            raise ValueError('checkpoint changed after review')
        ensure_no_active_authority(top, data['installed']['install_receipt']['plan']['username'])
        transaction = folder / ('restore-' + uuid.uuid4().hex)
        transaction.mkdir(mode=0o700)
        (transaction / 'efi-before').mkdir(mode=0o700)
        run('rsync', '-r', '--exclude=/' + ENTROPY, str(esp) + '/', str(transaction / 'efi-before') + '/')
        token = uuid.uuid4().hex
        staged, failed = top / ('@recovered-' + token), top / ('@failed-' + token)
        journal = {'schema_version': 'phios.os-restore-transaction.v1', 'generation': generation,
            'failed_root': failed.name, 'staged_root': staged.name, 'stage': 'preparing',
            'home_restored': False, 'authority_restored': False, 'release_ready': False}
        write_json(transaction / 'transaction.json', journal)
        run('btrfs', 'subvolume', 'snapshot', str(folder / 'root'), str(staged))
        seed = staged / 'var/lib/systemd/random-seed'
        seed.unlink(missing_ok=True)
        # An older root must never silently reinstate an earlier trust policy.
        for name in ['os-update-trust.json', 'os-update-keyring.gpg']:
            (staged / 'etc/phios' / name).unlink(missing_ok=True)
        counters = []
        for root in [top / '@root', staged]:
            counter = root / 'var/lib/phios/os-update-generation.json'
            if counter.exists():
                value = json.loads(regular(counter))
                if type(value.get('sequence')) is not int or value['sequence'] < 0:
                    raise ValueError('update generation requires explicit recovery review')
                counters.append(value['sequence'])
        write_json(staged / 'var/lib/phios/os-update-generation.json', {
            'schema_version': 'phios.os-update-generation.v1',
            'sequence': max(counters, default=0) + 1, 'source_commit': data['source_commit']})
        journal['stage'] = 'switching root; keep live recovery media'
        write_json(transaction / 'transaction.json', journal)
        if (top / '@root').exists():
            os.rename(top / '@root', failed)
        run('btrfs', 'filesystem', 'sync', str(top))
        os.rename(staged, top / '@root')
        run('btrfs', 'filesystem', 'sync', str(top))
        journal['stage'] = 'restoring matching EFI; do not reboot'
        write_json(transaction / 'transaction.json', journal)
        run('rsync', '-r', '--delete', '--exclude=/' + ENTROPY, str(folder / 'efi') + '/', str(esp) + '/')
        (esp / ENTROPY).unlink(missing_ok=True)
        if boot_inventory(esp) != data['boot_files']:
            raise ValueError('restored EFI verification failed; preserve transaction and use live recovery')
        os.sync()
        journal['stage'] = 'restored; disk-only boot remains unqualified'
        write_json(transaction / 'transaction.json', journal)
        run('btrfs', 'filesystem', 'sync', str(top))
        os.sync()
        return journal


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['checkpoint', 'restore'])
    parser.add_argument('--disk', required=True)
    parser.add_argument('--generation', help='Exact checkpoint ID required for restore')
    parser.add_argument('--plan', action='store_true', help='Read-only probe; never changes the target')
    args = parser.parse_args()
    try:
        if os.geteuid() != 0 or not Path('/run/archiso/bootmnt').is_dir() or not Path('/sys/firmware/efi').is_dir():
            raise ValueError('run this root-owned tool from a PhiOS UEFI live image with the target offline')
        generation = args.generation if args.operation == 'restore' else uuid.uuid4().hex
        if generation is None or re.fullmatch(GEN, generation) is None:
            raise ValueError('exact checkpoint generation required')
        identity = inventory(args.disk)
        with mounted(identity, writable=False) as (top, esp):
            plan = {'schema_version': 'phios.os-maintenance-plan.v1', 'operation': args.operation,
                'disk': identity, 'generation': generation, 'home_restored': False,
                'authority_restored': False, 'atomic': False, 'release_ready': False}
            if args.operation == 'checkpoint':
                plan.update(installed=installed(top, identity), boot_files=boot_inventory(esp))
                ensure_no_active_authority(top, plan['installed']['install_receipt']['plan']['username'])
            else:
                data, _folder = checkpoint_data(top, esp, identity, generation)
                ensure_no_active_authority(top, data['installed']['install_receipt']['plan']['username'])
                plan['checkpoint'] = data
        print(json.dumps(plan, indent=2, sort_keys=True), flush=True)
        if args.plan:
            return 0
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise ValueError('interactive terminal review required; no unattended bypass')
        print('Same-disk recovery is not a backup. Preserve a verified data backup on separate storage.\n'
              'Root/EFI activation is not atomic. Keep live recovery media available.\n'
              'Type the exact reviewed confirmation, or Ctrl-C to cancel:\n' + phrase(plan), flush=True)
        if input('> ') != phrase(plan):
            raise ValueError('confirmation did not match; no target writes performed')
        print(json.dumps(execute(identity, args.operation, generation, plan), indent=2, sort_keys=True))
        return 0
    except (KeyboardInterrupt, EOFError):
        print('Maintenance cancelled; preserve transaction evidence if writes had begun.')
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f'OS maintenance held: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
