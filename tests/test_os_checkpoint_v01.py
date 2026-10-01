from __future__ import annotations

import copy
import importlib.util
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from phios.memory import MemoryStore

FILE = Path(__file__).resolve().parents[1] / 'packaging/linux/updates/recover.py'
spec = importlib.util.spec_from_file_location('phios_os_recovery', FILE)
assert spec is not None and spec.loader is not None
recover = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recover)


def disk() -> dict[str, Any]:
    return {'path': '/dev/vda', 'type': 'disk', 'ro': False, 'pttype': 'gpt', 'size': 32 * 1024**3,
        'serial': 'disposable-test-only', 'maj:min': '252:0', 'mountpoints': [None], 'children': [
            {'path': '/dev/vda1', 'type': 'part', 'ro': False, 'size': 1024**3, 'fstype': 'vfat',
                'uuid': 'ABCD-1234', 'mountpoints': [None]},
            {'path': '/dev/vda2', 'type': 'part', 'ro': False, 'size': 31 * 1024**3, 'fstype': 'btrfs',
                'uuid': 'a' * 8 + '-' + ('a' * 4 + '-') * 3 + 'a' * 12, 'mountpoints': [None]}]}


@pytest.mark.parametrize('case', ['mounted', 'holder', 'wrong-layout', 'read-only', 'no-identity',
    'wrong-uuid', 'whole-device-alias', 'extra-device', 'wrong-esp-size'])
def test_recovery_never_accepts_unrelated_or_busy_disks(case: str) -> None:
    row = disk()
    busy = False
    if case == 'mounted':
        row['children'][1]['mountpoints'] = ['/']
    elif case == 'holder':
        busy = True
    elif case == 'wrong-layout':
        row['children'][1]['fstype'] = 'ext4'
    elif case == 'read-only':
        row['ro'] = True
    elif case == 'no-identity':
        row['serial'] = None
    elif case == 'wrong-uuid':
        row['children'][1]['uuid'] = 'not-a-uuid'
    elif case == 'whole-device-alias':
        row['path'] = '/dev/disk/by-id/unreviewed'
    elif case == 'extra-device':
        row['children'].append(row['children'][1])
    elif case == 'wrong-esp-size':
        row['children'][0]['size'] = 512 * 1024**2
    with pytest.raises(ValueError):
        recover.validate_disk(row, busy=busy)


def checkpoint(identity: dict[str, Any]) -> dict[str, Any]:
    return {'schema_version': recover.FORMAT, 'generation': 'b' * 32,
        'disk': {key: identity[key] for key in ['serial_or_wwn', 'size_bytes', 'root_uuid', 'esp_uuid']},
        'source_commit': 'c' * 40, 'state_schemas': copy.deepcopy(recover.SCHEMA),
        'root_snapshot_uuid': 'd' * 8 + '-' + ('d' * 4 + '-') * 3 + 'd' * 12,
        'boot_files': {name: {'size': 1, 'sha256': 'e' * 64} for name in
            ['vmlinuz-linux', 'initramfs-linux.img', 'initramfs-linux-fallback.img',
             'EFI/BOOT/BOOTX64.EFI', 'loader/entries/phios.conf']},
        'installed': {'source_commit': 'c' * 40, 'install_receipt': {
            'schema_version': 'phios.blank-disk-install.v1', 'installed': True,
            'root_uuid': identity['root_uuid'], 'esp_uuid': identity['esp_uuid'], 'plan': {'username': 'operator'}}},
        'home_snapshot_restored': False, 'authority_restored': False, 'release_ready': False}


@pytest.mark.parametrize('case', ['disk', 'generation', 'schema', 'authority', 'home', 'unknown'])
def test_checkpoint_cannot_cross_disks_restore_authority_or_invent_schema(case: str) -> None:
    identity = recover.validate_disk(disk(), busy=False)
    data = checkpoint(identity)
    assert recover.validate_checkpoint(copy.deepcopy(data), identity, 'b' * 32) == data
    if case == 'disk':
        data['disk']['root_uuid'] = 'different'
    elif case == 'generation':
        data['generation'] = 'e' * 32
    elif case == 'schema':
        data['state_schemas']['memory'] = 2
    elif case == 'authority':
        data['authority_restored'] = True
    elif case == 'home':
        data['home_snapshot_restored'] = True
    elif case == 'unknown':
        data['implicit_migration'] = True
    with pytest.raises(ValueError):
        recover.validate_checkpoint(data, identity, 'b' * 32)


def test_review_binds_boot_hash_root_snapshot_and_disk_identity() -> None:
    identity = recover.validate_disk(disk(), busy=False)
    plan = {'operation': 'restore', 'disk': identity, 'checkpoint': checkpoint(identity)}
    original = recover.phrase(plan)
    for change in ['disk', 'boot', 'snapshot']:
        altered = copy.deepcopy(plan)
        if change == 'disk':
            altered['disk']['serial_or_wwn'] = 'replacement'
        elif change == 'boot':
            altered['checkpoint']['boot_files']['vmlinuz-linux'] = {'sha256': 'f' * 64, 'size': 1}
        else:
            altered['checkpoint']['root_snapshot_uuid'] = 'e' * 36
        assert recover.phrase(altered) != original


def boot_files(root: Path) -> None:
    for name in ['vmlinuz-linux', 'initramfs-linux.img', 'initramfs-linux-fallback.img',
                 'EFI/BOOT/BOOTX64.EFI', 'loader/entries/phios.conf']:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_bytes(('disposable test ' + name).encode())


def test_matched_boot_inventory_detects_missing_changed_or_linked_files(tmp_path: Path) -> None:
    boot_files(tmp_path)
    initial = recover.boot_inventory(tmp_path, owner=os.getuid())
    (tmp_path / 'loader/random-seed').write_bytes(b'entropy must not be replayed')
    assert recover.boot_inventory(tmp_path, owner=os.getuid()) == initial
    (tmp_path / 'vmlinuz-linux').write_bytes(b'different kernel')
    assert recover.boot_inventory(tmp_path, owner=os.getuid()) != initial
    (tmp_path / 'vmlinuz-linux').unlink()
    with pytest.raises(ValueError):
        recover.boot_inventory(tmp_path, owner=os.getuid())
    (tmp_path / 'vmlinuz-linux').symlink_to(tmp_path / 'initramfs-linux.img')
    with pytest.raises(ValueError):
        recover.boot_inventory(tmp_path, owner=os.getuid())


def test_metadata_refuses_links_hardlinks_and_writable_trust(tmp_path: Path) -> None:
    path = tmp_path / 'checkpoint.json'
    path.write_text('{}')
    path.chmod(0o666)
    with pytest.raises(ValueError):
        recover.regular(path, owner=os.getuid())
    path.chmod(0o600)
    os.link(path, tmp_path / 'alias')
    with pytest.raises(ValueError):
        recover.regular(path, owner=os.getuid())


def state_home(top: Path) -> tuple[Path, Path]:
    home = top / '@home/operator'
    root = home / '.local/state/phios'
    root.mkdir(parents=True, mode=0o700)
    return home, root


def test_authority_history_requires_explicit_data_recovery_without_mutation(tmp_path: Path) -> None:
    _home, root = state_home(tmp_path)
    ledger = root / 'spine-v0.1/ledger/ghostwalk-action-lease-records.jsonl'
    ledger.parent.mkdir(parents=True, mode=0o700)
    ledger.write_text('{"execution_authority":true}\n')
    original = ledger.read_bytes()
    with pytest.raises(ValueError, match='authority history'):
        recover.ensure_no_active_authority(tmp_path, 'operator', uid=os.getuid())
    assert ledger.read_bytes() == original


def test_unknown_canonical_schema_is_held_without_data_changes(tmp_path: Path) -> None:
    _home, root = state_home(tmp_path)
    database = root / 'memory/canonical.sqlite3'
    MemoryStore(database)
    with sqlite3.connect(database) as conn:
        conn.execute("UPDATE store_metadata SET value='99' WHERE key='schema_version'")
    original = database.read_bytes()
    with pytest.raises(ValueError, match='schema'):
        recover.ensure_no_active_authority(tmp_path, 'operator', uid=os.getuid())
    assert database.read_bytes() == original


def test_enabled_configuration_requires_revalidation_before_rollback(tmp_path: Path) -> None:
    home, _root = state_home(tmp_path)
    config = home / '.config/phios/memory.json'
    config.parent.mkdir(parents=True, mode=0o700)
    config.write_text(json.dumps({'enabled': True}))
    original = config.read_bytes()
    with pytest.raises(ValueError, match='disable memory'):
        recover.ensure_no_active_authority(tmp_path, 'operator', uid=os.getuid())
    assert config.read_bytes() == original
