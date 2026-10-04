from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from test_os_release_inventory_v01 import fixture, inventory

FILE = Path(__file__).resolve().parents[1] / 'packaging/linux/source_delivery.py'
spec = importlib.util.spec_from_file_location('phios_source_delivery', FILE)
assert spec is not None and spec.loader is not None
delivery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delivery)


def candidate(tmp: Path) -> Path:
    root, output = tmp / 'image', tmp / 'candidate'
    fixture(root, output)
    inventory.record(root, output, 'a' * 40, ci_fixtures=False, epoch=1)
    return output


def complete(output: Path, materials: Path) -> dict:
    manifest = delivery.initialize(output)
    materials.mkdir()
    payloads = [('first-party.tar.gz', 'corresponding-source', (output / 'phios-source.tar.gz').read_bytes()),
        ('supplier-notices.tar.gz', 'notice', (output / 'third-party-notices.tar.gz').read_bytes()),
        ('build/README.txt', 'build-material', b'Disposable test source and build/patch instructions.\n')]
    for name, kind, data in payloads:
        path = materials / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        manifest['materials'].append({'path': name, 'kind': kind, 'sha256': hashlib.sha256(data).hexdigest(),
            'size': len(data), 'origin': 'Disposable local fixture; no upstream claim', 'custody': 'Created by this test'})
    for row in manifest['components']:
        row['review'] = {'disposition': 'source-required', 'reviewer': 'Fixture reviewer; not authenticated',
            'reviewed_at': '2026-10-01T00:00:00Z', 'applicable_terms': 'Disposable test declaration',
            'rationale': 'Tests record a human declaration, never infer compliance from it',
            'source_paths': ['first-party.tar.gz'], 'build_paths': ['build/README.txt'],
            'notice_paths': ['supplier-notices.tar.gz']}
    return manifest


def rebind(output: Path, name: str, value: dict) -> None:
    path = output / name
    path.write_bytes(delivery.wire(value))
    if name != 'provenance.json':
        provenance = json.loads((output / 'provenance.json').read_text())
        provenance['artifacts'][name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'size': path.stat().st_size}
        (output / 'provenance.json').write_bytes(delivery.wire(provenance))
    lines = (output / 'SHA256SUMS').read_text().splitlines()
    for i, line in enumerate(lines):
        digest, filename = line.split('  ')
        if filename in (name, 'provenance.json'):
            digest = hashlib.sha256((output / filename).read_bytes()).hexdigest()
        lines[i] = digest + '  ' + filename
    (output / 'SHA256SUMS').write_text('\n'.join(lines) + '\n')


def test_pending_inventory_is_complete_but_cannot_be_bundled(tmp_path: Path) -> None:
    output = candidate(tmp_path)
    manifest = delivery.initialize(output)
    assert len(manifest['components']) == 5
    report = delivery.verify(output, manifest, tmp_path)
    assert report['delivery_records_complete'] is False
    assert report['components_total'] == len(report['pending_components']) == 5
    assert report['missing_candidate_archives'] == ['first_party_source_archive', 'supplier_notice_archive']
    archive = tmp_path / 'held.tar.gz'
    with pytest.raises(ValueError, match='incomplete'):
        delivery.bundle(output, manifest, tmp_path, archive)
    assert not archive.exists()


def test_actual_material_bytes_pack_with_every_origin_and_no_release_claim(tmp_path: Path) -> None:
    output = candidate(tmp_path)
    materials = tmp_path / 'materials'
    manifest = complete(output, materials)
    archive = tmp_path / 'delivery.tar.gz'
    receipt = delivery.bundle(output, manifest, materials, archive)
    assert receipt['delivery_records_complete'] is True
    for flag in ('release_ready', 'publication_authority', 'license_source_compliance_reviewed'):
        assert receipt[flag] is False
    with tarfile.open(archive, 'r:gz') as packet:
        names = packet.getnames()
        assert all(item.isfile() and item.uid == item.gid == 0 and item.mtime == 1 for item in packet.getmembers())
        assert len(names) == len(set(names))
        sums = packet.extractfile('SHA256SUMS').read().decode().splitlines()
        for line in sums:
            digest, name = line.split('  ')
            assert hashlib.sha256(packet.extractfile(name).read()).hexdigest() == digest
        report = json.load(packet.extractfile('source-delivery-check.json'))
        assert report['component_reviews_recorded'] == 5
        assert report['review_declarations_authenticated'] is False
        assert report['iso_bytes_independently_verified'] is False
        assert report['license_source_compliance_reviewed'] is False
    second = tmp_path / 'same.tar.gz'
    delivery.bundle(output, manifest, materials, second)
    assert second.read_bytes() == archive.read_bytes()
    with pytest.raises(FileExistsError):
        delivery.bundle(output, manifest, materials, archive)


@pytest.mark.parametrize('case', ['source', 'iso', 'provenance', 'component-omit', 'component-duplicate',
    'component-version', 'component-license', 'material-tamper', 'material-size', 'material-kind',
    'path-escape', 'material-duplicate', 'missing-build', 'missing-source', 'reviewer', 'rationale',
    'timezone', 'release-ready', 'publication', 'compliance', 'unreferenced', 'missing-reference'])
def test_mismatched_or_unsafe_delivery_is_held(tmp_path: Path, case: str) -> None:
    output = candidate(tmp_path)
    materials = tmp_path / 'materials'
    manifest = complete(output, materials)
    row, item = manifest['components'][0], manifest['materials'][0]
    if case == 'source':
        manifest['candidate']['source_commit'] = 'b' * 40
    elif case == 'iso':
        manifest['candidate']['iso']['sha256'] = 'b' * 64
    elif case == 'provenance':
        manifest['candidate']['metadata']['provenance.json']['sha256'] = 'b' * 64
    elif case == 'component-omit':
        manifest['components'].pop()
    elif case == 'component-duplicate':
        manifest['components'][-1] = row
    elif case == 'component-version':
        row['version'] = 'wrong'
    elif case == 'component-license':
        row['declared_licenses'] = []
    elif case == 'material-tamper':
        (materials / item['path']).write_bytes(b'tampered')
    elif case == 'material-size':
        item['size'] = True
    elif case == 'material-kind':
        item['kind'] = 'notice'
    elif case == 'path-escape':
        item['path'] = '../first-party.tar.gz'
    elif case == 'material-duplicate':
        manifest['materials'].append(item)
    elif case == 'missing-build':
        row['review']['build_paths'] = []
    elif case == 'missing-source':
        row['review']['source_paths'] = []
    elif case in ('reviewer', 'rationale'):
        row['review'][case] = ' '
    elif case == 'timezone':
        row['review']['reviewed_at'] = '2026-10-01T00:00:00'
    elif case == 'release-ready':
        manifest['release_ready'] = True
    elif case == 'publication':
        manifest['publication_authority'] = True
    elif case == 'compliance':
        manifest['license_source_compliance_reviewed'] = True
    elif case == 'unreferenced':
        extra = dict(item, path='unreferenced.tar.gz')
        extra['sha256'] = hashlib.sha256(b'unrelated').hexdigest()
        extra['size'] = len(b'unrelated')
        (materials / extra['path']).write_bytes(b'unrelated')
        manifest['materials'].append(extra)
    else:
        row['review']['source_paths'] = ['unknown.tar.gz']
    with pytest.raises((ValueError, OSError)):
        delivery.verify(output, manifest, materials)


@pytest.mark.parametrize('case', ['file', 'directory', 'fifo'])
def test_material_links_and_special_files_cannot_import_host_data(tmp_path: Path, case: str) -> None:
    output = candidate(tmp_path)
    materials = tmp_path / 'materials'
    manifest = complete(output, materials)
    if case == 'directory':
        (materials / 'build/README.txt').unlink()
        (materials / 'build').rmdir()
        (materials / 'build').symlink_to(output, target_is_directory=True)
    else:
        path = materials / 'first-party.tar.gz'
        path.unlink()
        if case == 'file':
            path.symlink_to(output / 'phios-source.tar.gz')
        else:
            import os
            os.mkfifo(path)
    with pytest.raises((ValueError, OSError)):
        delivery.verify(output, manifest, materials)


@pytest.mark.parametrize('case', ['checksum', 'qa', 'coverage', 'sbom-source', 'duplicates'])
def test_candidate_metadata_cannot_be_silently_rebound(tmp_path: Path, case: str) -> None:
    output = candidate(tmp_path)
    if case == 'checksum':
        (output / 'sbom.cdx.json').write_text('{}')
    elif case == 'qa':
        data = json.loads((output / 'provenance.json').read_text())
        data['ci_fixture_build'] = True
        rebind(output, 'provenance.json', data)
    elif case == 'coverage':
        data = json.loads((output / 'source-review.json').read_text())
        data['required_review'].pop()
        rebind(output, 'source-review.json', data)
    elif case == 'sbom-source':
        data = json.loads((output / 'sbom.cdx.json').read_text())
        data['metadata']['properties'][0]['value'] = 'b' * 40
        rebind(output, 'sbom.cdx.json', data)
    else:
        path = output / 'source-review.json'
        path.write_text('{"schema_version":"old","schema_version":"new"}')
    with pytest.raises(ValueError):
        delivery.initialize(output)


def test_binary_arch_package_cannot_satisfy_a_source_record(tmp_path: Path) -> None:
    output = candidate(tmp_path)
    materials = tmp_path / 'materials'
    manifest = complete(output, materials)
    old = manifest['materials'][0]['path']
    new = 'arch-binary.pkg.tar.zst'
    (materials / old).rename(materials / new)
    manifest['materials'][0]['path'] = new
    for row in manifest['components']:
        row['review']['source_paths'] = [new]
    with pytest.raises(ValueError, match='binary package'):
        delivery.verify(output, manifest, materials)


def test_changed_bytes_during_sealing_do_not_leave_a_packet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = candidate(tmp_path)
    materials = tmp_path / 'materials'
    manifest = complete(output, materials)
    original = delivery.hash_file
    def changed(root: Path, name: str, destination=None):
        if destination is not None:
            (materials / name).write_bytes(b'changed between verification and sealing')
        return original(root, name, destination)
    monkeypatch.setattr(delivery, 'hash_file', changed)
    archive = tmp_path / 'held.tar.gz'
    with pytest.raises(ValueError, match='changed while sealing'):
        delivery.bundle(output, manifest, materials, archive)
    assert not archive.exists()


def test_candidate_change_after_check_cannot_seal_unmatched_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = candidate(tmp_path)
    materials = tmp_path / 'materials'
    manifest = complete(output, materials)
    original = delivery.verify
    def changed(*args):
        report = original(*args)
        provenance = json.loads((output / 'provenance.json').read_text())
        provenance['source_date_epoch'] += 1
        rebind(output, 'provenance.json', provenance)
        return report
    monkeypatch.setattr(delivery, 'verify', changed)
    archive = tmp_path / 'held.tar.gz'
    with pytest.raises(ValueError, match='candidate changed'):
        delivery.bundle(output, manifest, materials, archive)
    assert not archive.exists()


def test_explicit_no_source_requirement_is_a_recorded_unauthenticated_assertion(tmp_path: Path) -> None:
    output = candidate(tmp_path)
    materials = tmp_path / 'materials'
    manifest = complete(output, materials)
    row = manifest['components'][0]['review']
    row['disposition'], row['source_paths'], row['build_paths'] = 'no-source-required', [], []
    report = delivery.verify(output, manifest, materials)
    assert report['delivery_records_complete'] is True
    assert report['review_declarations_authenticated'] is False
    assert report['license_source_compliance_reviewed'] is False


def test_cli_distinguishes_pending_from_invalid_and_never_overwrites(tmp_path: Path) -> None:
    output = candidate(tmp_path)
    manifest_path = tmp_path / 'manifest.json'
    run = subprocess.run([sys.executable, str(FILE), 'init', '--candidate', str(output), '--output', str(manifest_path)], capture_output=True, text=True)
    assert run.returncode == 0
    command = [sys.executable, str(FILE), 'check', '--candidate', str(output), '--manifest', str(manifest_path), '--materials', str(tmp_path)]
    pending = subprocess.run(command, capture_output=True, text=True)
    assert pending.returncode == 2 and json.loads(pending.stdout)['delivery_records_complete'] is False
    data = json.loads(manifest_path.read_text())
    data['candidate']['source_commit'] = 'b' * 40
    manifest_path.write_text(json.dumps(data))
    assert subprocess.run(command, capture_output=True).returncode == 1
    before = manifest_path.read_bytes()
    assert subprocess.run(run.args, capture_output=True).returncode == 1
    assert manifest_path.read_bytes() == before
