"""Inventory the exact image and artifacts without authorizing publication."""
from __future__ import annotations

import argparse
import email.parser
import gzip
import hashlib
import io
import json
import os
import re
import stat
import tarfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

LIMIT = 4 * 1024**2
FIXTURES = ['usr/local/bin/phios-live-smoke', 'usr/local/bin/phios-live-install-smoke.py',
    'usr/local/bin/phios-live-update-smoke.py', 'etc/systemd/system/phios-live-smoke.service',
    'etc/systemd/system/multi-user.target.wants/phios-live-smoke.service']


def image_path(root: Path, relative: str) -> Path:
    """Resolve guest absolute/relative symlinks inside the image, never the host."""
    parts = list(PurePosixPath(relative).parts)
    if not parts or parts[0] == '/' or '..' in parts:
        raise ValueError('unsafe image-relative path')
    resolved: list[str] = []
    links = 0
    while parts:
        name = parts.pop(0)
        if name in ('', '.'):
            continue
        if name == '..':
            if not resolved:
                raise ValueError('image link escapes its root')
            resolved.pop()
            continue
        path = root.joinpath(*resolved, name)
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            links += 1
            if links > 32:
                raise ValueError('image symlink cycle or excessive depth')
            target = PurePosixPath(os.readlink(path))
            if target.is_absolute():
                resolved = []
                parts = list(target.parts[1:]) + parts
            else:
                parts = list(target.parts) + parts
        else:
            resolved.append(name)
    return root.joinpath(*resolved)


def bounded(path: Path, maximum: int = LIMIT) -> bytes:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
        raise ValueError('bounded regular metadata required: ' + str(path))
    with path.open('rb') as handle:
        data = handle.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError('metadata exceeded its bound')
    return data


def digest(path: Path) -> dict[str, Any]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('artifact must be a regular file')
    with path.open('rb') as handle:
        value = hashlib.file_digest(handle, 'sha256').hexdigest()
    return {'sha256': value, 'size': info.st_size}


def fields(data: bytes) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    current: str | None = None
    for line in data.decode().splitlines():
        if line.startswith('%') and line.endswith('%'):
            current = line.strip('%')
            if current in result:
                raise ValueError('duplicate package metadata field')
            result[current] = []
        elif line and current is not None:
            result[current].append(line)
    return result


def one(data: dict[str, list[str]], name: str) -> str:
    values = data.get(name, [])
    if len(values) != 1 or not values[0] or any(ord(c) < 32 for c in values[0]):
        raise ValueError('exact package ' + name + ' required')
    return values[0]


def licenses(labels: list[str]) -> list[dict[str, Any]]:
    # Preserve supplier declarations; never invent SPDX conclusions.
    return [{'license': {'name': label, 'acknowledgement': 'declared'}} for label in sorted(set(labels)) if label]


def component(kind: str, name: str, version: str, *, path: str, labels: list[str], namespace: str = '') -> dict[str, Any]:
    encoded_name = quote(name, safe='/')
    purl = f'pkg:{kind}/{namespace}{encoded_name}@{quote(version, safe="")}'
    return {'type': 'application' if kind == 'alpm' else 'library', 'bom-ref': purl + '#' + quote(path, safe=''),
        'name': name, 'version': version, 'purl': purl, 'licenses': licenses(labels),
        'properties': [{'name': 'phios:inventory-path', 'value': path},
                       {'name': 'phios:license-review', 'value': 'pending; supplier declarations only'}]}


def collect(root: Path) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], set[str]]:
    components: list[dict[str, Any]] = []
    inventory: dict[str, list[dict[str, Any]]] = {'native': [], 'python': [], 'javascript': []}
    notices: set[str] = set()
    database = image_path(root, 'var/lib/pacman/local')
    rows = sorted(database.glob('*/desc'))
    if not 1 <= len(rows) <= 20000:
        raise ValueError('complete bounded native package database required')
    names: set[str] = set()
    for desc in rows:
        desc = image_path(root, desc.relative_to(root).as_posix())
        data = fields(bounded(desc, 65536))
        name, version, arch = [one(data, key) for key in ['NAME', 'VERSION', 'ARCH']]
        if name in names or re.fullmatch(r'[a-z0-9][a-z0-9@._+\-]{0,127}', name) is None:
            raise ValueError('duplicate or invalid native package')
        names.add(name)
        labels = data.get('LICENSE', [])
        path = desc.relative_to(root).as_posix()
        item = {'name': name, 'version': version, 'architecture': arch,
                'package_base': data.get('BASE', [name])[0], 'declared_licenses': labels,
                'upstream_urls': data.get('URL', []), 'metadata': digest(desc)}
        inventory['native'].append(item)
        comp = component('alpm', name, version, path=path, labels=labels, namespace='arch/')
        comp['purl'] += '?arch=' + quote(arch, safe='')
        components.append(comp)
        files = image_path(root, desc.with_name('files').relative_to(root).as_posix())
        for relative in fields(bounded(files)).get('FILES', []):
            if not relative.endswith('/') and (relative.startswith('usr/share/licenses/') or
                    relative.endswith('/copyright') or relative.endswith('/COPYING')):
                notices.add(relative)
    for path in sorted(root.glob('usr/lib/python*/site-packages/*.dist-info/METADATA')):
        path = image_path(root, path.relative_to(root).as_posix())
        metadata = email.parser.BytesParser().parsebytes(bounded(path))
        name, version = metadata.get('Name'), metadata.get('Version')
        if not name or not version:
            raise ValueError('Python distribution identity missing')
        labels = metadata.get_all('License-Expression', []) or metadata.get_all('License', [])
        labels = [' '.join(label.split()) for label in labels if label.strip() not in ('', 'UNKNOWN')]
        relative = path.relative_to(root).as_posix()
        inventory['python'].append({'name': name, 'version': version, 'declared_licenses': labels,
                                    'metadata': digest(path), 'path': relative})
        components.append(component('pypi', re.sub(r'[-_.]+', '-', name).lower(), version, path=relative, labels=labels))
        for notice in path.parent.rglob('*'):
            if notice.is_file() and re.search(r'license|copying|notice|copyright', notice.name, re.I):
                notices.add(notice.relative_to(root).as_posix())
    package = json.loads(bounded(image_path(root, 'usr/lib/phishell/package.json')))
    if not package.get('name') or not package.get('version'):
        raise ValueError('installed PhiShell identity missing')
    lock = json.loads(bounded(image_path(root, 'usr/lib/phishell/node_modules/.package-lock.json')))
    rows = lock.get('packages')
    if not isinstance(rows, dict) or len(rows) > 20000:
        raise ValueError('bounded installed npm lock required')
    for relative, row in sorted(rows.items()):
        if not relative:
            continue
        parts = relative.split('node_modules/')[-1]
        name = row.get('name') or parts
        version = row.get('version')
        if not isinstance(version, str) or not version or row.get('link'):
            raise ValueError('installed npm identity/version/link unsupported')
        directory = image_path(root, 'usr/lib/phishell/' + relative)
        actual = json.loads(bounded(image_path(root, directory.relative_to(root).as_posix() + '/package.json')))
        if actual.get('name') != name or actual.get('version') != version:
            raise ValueError('installed npm package differs from lock')
        label = actual.get('license')
        labels = [label] if isinstance(label, str) and label else []
        path = directory.relative_to(root).as_posix()
        inventory['javascript'].append({'name': name, 'version': version, 'declared_licenses': labels,
                                        'lock_integrity': row.get('integrity'), 'path': path})
        components.append(component('npm', name, version, path=path, labels=labels))
        for notice in directory.iterdir():
            if notice.is_file() and re.search(r'license|copying|notice|copyright', notice.name, re.I):
                notices.add(notice.relative_to(root).as_posix())
    inventory['native'].sort(key=lambda row: row['name'])
    return sorted(components, key=lambda row: row['bom-ref']), inventory, notices


def notice_files(root: Path, notices: set[str]) -> list[str]:
    queue = sorted(notices)
    result: set[str] = set()
    visited_directories: set[str] = set()
    while queue:
        relative = queue.pop(0)
        path = image_path(root, relative)
        if path.is_dir():
            canonical = path.relative_to(root).as_posix()
            if canonical in visited_directories:
                continue
            visited_directories.add(canonical)
            queue.extend(relative.rstrip('/') + '/' + child.name for child in sorted(path.iterdir()))
        elif path.is_file():
            result.add(relative)
        else:
            raise ValueError('notice is not a directory or regular file')
        if len(result) + len(queue) + len(visited_directories) > 20000:
            raise ValueError('notice file count exceeds its bound')
    return sorted(result)


def json_file(path: Path, value: Any) -> None:
    with path.open('x') as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write('\n')


def record(root: Path, output: Path, source: str, *, ci_fixtures: bool, epoch: int) -> None:
    if re.fullmatch(r'[0-9a-f]{40}', source) is None or epoch < 0:
        raise ValueError('exact source identity and source epoch required')
    if bounded(image_path(root, 'usr/share/phios/source-commit')).decode().strip() != source:
        raise ValueError('image source differs from build')
    release = json.loads(bounded(output / 'release.json'))
    observed = [path for path in FIXTURES if (root / path).exists() or (root / path).is_symlink()]
    if bool(observed) != ci_fixtures or (ci_fixtures and set(observed) != set(FIXTURES)):
        raise ValueError('actual fixture inventory differs from requested build scope')
    for path in ['etc/phios/os-update-trust.json', 'etc/phios/os-update-keyring.gpg',
                 'usr/share/phios-ci-update/verified.txt']:
        if (root / path).exists() or (root / path).is_symlink():
            raise ValueError('enrolled PhiOS trust or test package present in distributable source image')
    components, inventory, notice_paths = collect(root)
    native_text = ''.join(row['name'] + ' ' + row['version'] + '\n' for row in inventory['native'])
    if native_text != bounded(output / 'image-packages.txt').decode():
        raise ValueError('native package database differs from independently recorded pacman inventory')
    license_index: list[dict[str, Any]] = []
    total = 0
    with (output / 'third-party-notices.tar.gz').open('xb') as raw:
        with gzip.GzipFile(fileobj=raw, mode='wb', mtime=epoch, filename='') as compressed:
            with tarfile.open(fileobj=compressed, mode='w|', format=tarfile.PAX_FORMAT) as archive:
                for relative in notice_files(root, notice_paths):
                    path = image_path(root, relative)
                    data = bounded(path, 16 * 1024**2)
                    total += len(data)
                    if total > 128 * 1024**2:
                        raise ValueError('notice inventory exceeds its bound')
                    info = tarfile.TarInfo(relative)
                    info.size, info.mode, info.mtime = len(data), 0o644, epoch
                    archive.addfile(info, io.BytesIO(data))
                    license_index.append({'path': relative, 'resolved_image_path': path.relative_to(root).as_posix(),
                        'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    for ecosystem, rows in inventory.items():
        json_file(output / (ecosystem + '-packages.json'), rows)
    json_file(output / 'third-party-notices.json', {'schema_version': 'phios.bundled-notices.v1',
        'files': license_index, 'license_compliance_reviewed': False})
    json_file(output / 'fixture-inventory.json', {'schema_version': 'phios.image-fixtures.v1',
        'ci_fixture_build': ci_fixtures, 'observed_fixture_paths': observed, 'fixture_free': not ci_fixtures,
        'release_ready': False})
    json_file(output / 'sbom.cdx.json', {'$schema': 'http://cyclonedx.org/schema/bom-1.6.schema.json',
        'bomFormat': 'CycloneDX', 'specVersion': '1.6', 'version': 1,
        'metadata': {'timestamp': datetime.now(UTC).isoformat(), 'component': {'type': 'operating-system',
            'name': 'PhiOS Linux Preview', 'version': release['os_version']},
            'properties': [{'name': 'phios:source-commit', 'value': source},
                           {'name': 'phios:ci-fixture-build', 'value': str(ci_fixtures).lower()},
                           {'name': 'phios:release-ready', 'value': 'false'}]}, 'components': components})
    json_file(output / 'source-review.json', {'schema_version': 'phios.distribution-source-review.v1',
        'source_commit': source, 'first_party_source_archive': digest(output / 'phios-source.tar.gz'),
        'third_party_source_compliance_reviewed': False, 'release_ready': False,
        'required_review': [{'component': row['bom-ref'], 'name': row['name'], 'version': row['version'],
            'declared_licenses': row['licenses'], 'source_delivery_review': 'pending'} for row in components]})
    artifacts = [path for path in output.iterdir() if path.is_file() and path.name not in
        ['build.log', 'mkarchiso.log', 'SHA256SUMS', 'provenance.json']]
    archive_hash = bounded(output / 'source-archive-sha256.txt').decode().strip()
    if digest(output / 'phios-source.tar.gz')['sha256'] != archive_hash:
        raise ValueError('source archive digest differs from recorded build input')
    isos = [path for path in artifacts if path.suffix == '.iso']
    if len(isos) != 1:
        raise ValueError('exactly one ISO required')
    json_file(output / 'provenance.json', {'schema_version': 'phios.os-build-provenance.v1', 'source_commit': source,
        'source_date_epoch': epoch, 'arch_snapshot': release['arch_snapshot'],
        'archiso_version': release['archiso_version'], 'builder_image': release['builder_image'],
        'ci_fixture_build': ci_fixtures, 'iso': {'filename': isos[0].name, **digest(isos[0])},
        'artifacts': {path.name: digest(path) for path in sorted(artifacts)},
        'signed': False, 'reproducible_build_demonstrated': False, 'hardware_qualified': False,
        'license_source_compliance_reviewed': False, 'release_ready': False})
    artifacts.append(output / 'provenance.json')
    with (output / 'SHA256SUMS').open('w') as handle:
        for path in sorted(artifacts):
            handle.write(digest(path)['sha256'] + '  ' + path.name + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--source', required=True)
    parser.add_argument('--epoch', required=True, type=int)
    parser.add_argument('--ci-fixtures', action='store_true')
    args = parser.parse_args()
    record(args.root, args.output, args.source, ci_fixtures=args.ci_fixtures, epoch=args.epoch)
