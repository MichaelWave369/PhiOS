from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

FILE = Path(__file__).resolve().parents[1] / 'packaging/linux/release_inventory.py'
spec = importlib.util.spec_from_file_location('phios_release_inventory', FILE)
assert spec is not None and spec.loader is not None
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)


def put(root: Path, name: str, data: str | bytes) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode() if isinstance(data, str) else data)
    return path


def fixture(root: Path, output: Path) -> None:
    put(root, 'usr/share/phios/source-commit', 'a' * 40 + '\n')
    for name in ['a', 'a-b']:
        put(root, 'var/lib/pacman/local/' + name + '-z-1/desc',
            f'%NAME%\n{name}\n\n%VERSION%\nz-1\n\n%ARCH%\nx86_64\n\n%LICENSE%\nGPL\n\n')
        put(root, 'var/lib/pacman/local/' + name + '-z-1/files', '%FILES%\nusr/share/licenses/shared\n\n')
    put(root, 'usr/share/licenses/common/LICENSE', 'disposable declared notice\n')
    (root / 'usr/share/licenses/shared').symlink_to('/usr/share/licenses/common')
    put(root, 'usr/lib/python3.14/site-packages/test-1.0.dist-info/METADATA', 'Name: Test\nVersion: 1.0\nLicense: Custom License\n')
    put(root, 'usr/lib/phishell/package.json', json.dumps({'name': 'phishell', 'version': '0.16.0'}))
    put(root, 'usr/lib/phishell/node_modules/.package-lock.json', json.dumps({'packages': {
        'node_modules/react': {'version': '19.0.0', 'integrity': 'disposable'}}}))
    put(root, 'usr/lib/phishell/node_modules/react/package.json', json.dumps({'name': 'react', 'version': '19.0.0', 'license': 'MIT'}))
    put(root, 'usr/lib/phishell/node_modules/react/LICENSE', 'disposable MIT notice\n')
    put(output, 'release.json', json.dumps({'os_version': '0.1.0-alpha.1', 'arch_snapshot': '2026/09/30',
        'archiso_version': '91-1', 'builder_image': 'archlinux@sha256:' + 'b' * 64}))
    put(output, 'image-packages.txt', 'a z-1\na-b z-1\n')
    put(output, 'phios-source.tar.gz', b'disposable source archive')
    put(output, 'source-archive-sha256.txt', hashlib.sha256(b'disposable source archive').hexdigest() + '\n')
    put(output, 'phios-linux.iso', b'disposable ISO fixture')


def test_inventory_tracks_actual_bytes_without_concluding_compliance(tmp_path: Path) -> None:
    root, output = tmp_path / 'root', tmp_path / 'output'
    fixture(root, output)
    inventory.record(root, output, 'a' * 40, ci_fixtures=False, epoch=1)
    provenance = json.loads((output / 'provenance.json').read_text())
    assert provenance['iso']['sha256'] == hashlib.sha256(b'disposable ISO fixture').hexdigest()
    assert provenance['release_ready'] is False
    assert provenance['license_source_compliance_reviewed'] is False
    bom = json.loads((output / 'sbom.cdx.json').read_text())
    assert len(bom['components']) == 4
    assert len({row['bom-ref'] for row in bom['components']}) == 4
    assert all(row['licenses'][0]['license']['acknowledgement'] == 'declared' for row in bom['components'])
    notices = json.loads((output / 'third-party-notices.json').read_text())
    assert {row['path'] for row in notices['files']} == {
        'usr/share/licenses/shared/LICENSE', 'usr/lib/phishell/node_modules/react/LICENSE'}
    assert json.loads((output / 'source-review.json').read_text())['third_party_source_compliance_reviewed'] is False
    for line in (output / 'SHA256SUMS').read_text().splitlines():
        digest, filename = line.split('  ')
        assert hashlib.sha256((output / filename).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize('case', ['source', 'inventory', 'npm', 'archive', 'fixture', 'trust'])
def test_inconsistent_image_or_artifact_cannot_get_provenance(tmp_path: Path, case: str) -> None:
    root, output = tmp_path / 'root', tmp_path / 'output'
    fixture(root, output)
    if case == 'source':
        put(root, 'usr/share/phios/source-commit', 'c' * 40)
    elif case == 'inventory':
        put(output, 'image-packages.txt', 'unrelated 1-1\n')
    elif case == 'npm':
        put(root, 'usr/lib/phishell/node_modules/react/package.json', '{"name":"react","version":"wrong"}')
    elif case == 'archive':
        put(output, 'phios-source.tar.gz', b'changed archive')
    elif case == 'fixture':
        put(root, inventory.FIXTURES[0], 'test fixture')
    else:
        put(root, 'etc/phios/os-update-keyring.gpg', b'unrequested trust')
    with pytest.raises(ValueError):
        inventory.record(root, output, 'a' * 40, ci_fixtures=False, epoch=1)
    assert not (output / 'provenance.json').exists()


def test_guest_symlinks_do_not_read_the_build_host_and_cycles_are_held(tmp_path: Path) -> None:
    put(tmp_path, 'guest/data', 'image-only notice')
    (tmp_path / 'alias').symlink_to('/guest/data')
    assert inventory.image_path(tmp_path, 'alias').read_text() == 'image-only notice'
    (tmp_path / 'escape').symlink_to('../../etc/passwd')
    with pytest.raises(ValueError, match='escapes'):
        inventory.image_path(tmp_path, 'escape')
    (tmp_path / 'cycle').symlink_to('cycle')
    with pytest.raises(ValueError, match='cycle'):
        inventory.image_path(tmp_path, 'cycle')
