"""Prepare and verify offline source delivery records; never authorize release."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import stat
import tarfile
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Iterator

JSON_LIMIT = 16 * 1024**2
FILE_LIMIT = 8 * 1024**3
TOTAL_LIMIT = 32 * 1024**3
SHA256 = re.compile(r'[0-9a-f]{64}')
METADATA = ('provenance.json', 'sbom.cdx.json', 'source-review.json', 'third-party-notices.json')
KINDS = {'corresponding-source', 'build-material', 'notice'}
SCHEMA = 'phios.source-delivery-manifest.v1'


def relative_path(value: Any) -> str:
    if (not isinstance(value, str) or len(value) > 512 or
            not re.fullmatch(r'[A-Za-z0-9._+@=-]+(?:/[A-Za-z0-9._+@=-]+)*', value) or
            any(p in ('.', '..') for p in value.split('/'))):
        raise ValueError('safe relative file path required')
    return value


@contextmanager
def regular(root: Path, relative: str, maximum: int) -> Iterator[BinaryIO]:
    """Open beneath an explicit local root without following any child symlink."""
    parts = relative_path(relative).split('/')
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or not 0 <= info.st_size <= maximum:
                raise ValueError('bounded regular file required: ' + relative)
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                yield stream
        finally:
            os.close(fd)
    finally:
        os.close(directory)


def read(root: Path, name: str) -> bytes:
    with regular(root, name, JSON_LIMIT) as stream:
        data = stream.read(JSON_LIMIT + 1)
    if len(data) > JSON_LIMIT:
        raise ValueError('metadata exceeds its bound')
    return data


def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key: ' + key)
        result[key] = value
    return result


def decode(data: bytes) -> Any:
    def invalid(value: str) -> None:
        raise ValueError('non-finite JSON value: ' + value)
    return json.loads(data, object_pairs_hook=unique, parse_constant=invalid)


def wire(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()


def record(value: Any) -> dict[str, Any]:
    if (not isinstance(value, dict) or set(value) != {'sha256', 'size'} or
            not isinstance(value['sha256'], str) or not SHA256.fullmatch(value['sha256']) or
            type(value['size']) is not int or not 0 < value['size'] <= FILE_LIMIT):
        raise ValueError('exact SHA-256 and positive bounded file size required')
    return value


def hash_file(root: Path, name: str, destination: BinaryIO | None = None) -> dict[str, Any]:
    hasher, size = hashlib.sha256(), 0
    with regular(root, name, FILE_LIMIT) as stream:
        while data := stream.read(1024**2):
            size += len(data)
            if size > FILE_LIMIT:
                raise ValueError('material exceeds its bound')
            hasher.update(data)
            if destination is not None:
                destination.write(data)
    return {'sha256': hasher.hexdigest(), 'size': size}


def candidate(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, bytes]]:
    payload = {name: read(root, name) for name in METADATA}
    payload['SHA256SUMS'] = read(root, 'SHA256SUMS')
    sums: dict[str, str] = {}
    for line in payload['SHA256SUMS'].decode().splitlines():
        if not re.fullmatch(r'[0-9a-f]{64}  [A-Za-z0-9._+@=-]+', line):
            raise ValueError('invalid candidate checksum record')
        digest, name = line.split('  ')
        relative_path(name)
        if name in sums:
            raise ValueError('duplicate candidate checksum')
        sums[name] = digest
    for name in METADATA:
        if sums.get(name) != hashlib.sha256(payload[name]).hexdigest():
            raise ValueError('candidate checksum mismatch: ' + name)
    provenance = decode(payload['provenance.json'])
    if (provenance.get('schema_version') != 'phios.os-build-provenance.v1' or
            provenance.get('ci_fixture_build') is not False or
            not isinstance(provenance.get('source_commit'), str) or
            not re.fullmatch('[0-9a-f]{40}', provenance['source_commit']) or
            type(provenance.get('source_date_epoch')) is not int or not 0 <= provenance['source_date_epoch'] < 2**32):
        raise ValueError('exact normal candidate provenance required; QA images refused')
    artifacts = provenance['artifacts']
    for name in METADATA[1:]:
        if record(artifacts[name]) != {'sha256': hashlib.sha256(payload[name]).hexdigest(), 'size': len(payload[name])}:
            raise ValueError('candidate metadata differs from provenance: ' + name)
    iso = provenance['iso']
    relative_path(iso['filename'])
    iso_record = record({k: iso[k] for k in ('sha256', 'size')})
    if record(artifacts[iso['filename']]) != iso_record or sums.get(iso['filename']) != iso_record['sha256']:
        raise ValueError('ISO provenance/checksum identity mismatch')
    source = record(artifacts['phios-source.tar.gz'])
    notices = record(artifacts['third-party-notices.tar.gz'])
    if any(sums.get(name) != artifacts[name]['sha256'] for name in ('phios-source.tar.gz', 'third-party-notices.tar.gz')):
        raise ValueError('source/notice archive checksum identity mismatch')
    review, bom = decode(payload['source-review.json']), decode(payload['sbom.cdx.json'])
    if (review.get('schema_version') != 'phios.distribution-source-review.v1' or
            review.get('source_commit') != provenance['source_commit'] or
            review.get('first_party_source_archive') != source or
            bom.get('bomFormat') != 'CycloneDX' or bom.get('specVersion') != '1.6'):
        raise ValueError('source review differs from candidate identity')
    properties = bom.get('metadata', {}).get('properties', [])
    if [p.get('value') for p in properties if p.get('name') == 'phios:source-commit'] != [provenance['source_commit']]:
        raise ValueError('SBOM source identity mismatch')
    rows = review['required_review']
    components = bom['components']
    if not isinstance(rows, list) or not 1 <= len(rows) <= 20000 or not isinstance(components, list):
        raise ValueError('bounded complete component inventory required')
    indexed: dict[str, dict[str, Any]] = {}
    for row in components:
        ref = row['bom-ref']
        if not isinstance(ref, str) or not ref or ref in indexed:
            raise ValueError('unique SBOM component identities required')
        indexed[ref] = {'component': ref, 'name': row['name'], 'version': row['version'], 'declared_licenses': row.get('licenses', [])}
    required = [{key: row[key] for key in ('component', 'name', 'version', 'declared_licenses')} for row in rows]
    if len({row['component'] for row in required}) != len(required) or indexed != {row['component']: row for row in required}:
        raise ValueError('source review does not cover exactly the SBOM components')
    identity = {'source_commit': provenance['source_commit'], 'source_date_epoch': provenance['source_date_epoch'],
        'iso': iso, 'first_party_source_archive': source, 'supplier_notice_archive': notices,
        'metadata': {name: {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)} for name, data in payload.items()}}
    return identity, sorted(required, key=lambda row: row['component']), payload


def initialize(root: Path) -> dict[str, Any]:
    identity, rows, _ = candidate(root)
    return {'schema_version': SCHEMA, 'candidate': identity, 'materials': [],
        'components': [{**row, 'review': {'disposition': 'pending', 'reviewer': None, 'reviewed_at': None,
            'applicable_terms': None, 'rationale': None, 'source_paths': [], 'build_paths': [], 'notice_paths': []}} for row in rows],
        'release_ready': False, 'publication_authority': False, 'license_source_compliance_reviewed': False}


def text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 4096 or any(ord(c) < 32 for c in value):
        raise ValueError('bounded review text required: ' + name)
    return value


def verify(root: Path, manifest: dict[str, Any], materials_root: Path) -> dict[str, Any]:
    expected = initialize(root)
    if (set(manifest) != set(expected) or manifest['schema_version'] != SCHEMA or
            manifest['candidate'] != expected['candidate'] or
            any(manifest[k] is not False for k in ('release_ready', 'publication_authority', 'license_source_compliance_reviewed'))):
        raise ValueError('manifest identity/scope differs from exact normal candidate')
    materials: dict[str, dict[str, Any]] = {}
    if not isinstance(manifest['materials'], list) or len(manifest['materials']) > 40000:
        raise ValueError('bounded material catalog required')
    total = 0
    for item in manifest['materials']:
        if set(item) != {'path', 'kind', 'sha256', 'size', 'origin', 'custody'}:
            raise ValueError('exact material record required')
        name = relative_path(item['path'])
        if name in materials or item['kind'] not in KINDS:
            raise ValueError('duplicate material path or unsupported kind')
        declared = record({k: item[k] for k in ('sha256', 'size')})
        total += declared['size']
        if total > TOTAL_LIMIT:
            raise ValueError('total source material exceeds its bound')
        for key in ('origin', 'custody'):
            text(item[key], key)
        if item['kind'] in ('corresponding-source', 'build-material') and ('.pkg.tar.' in name or name.endswith(('.iso', '.whl'))):
            raise ValueError('binary package/image is not source or build material')
        if hash_file(materials_root, name) != declared:
            raise ValueError('delivered material hash/size mismatch: ' + name)
        materials[name] = item
    wanted = {row['component']: row for row in expected['components']}
    rows = manifest['components']
    if not isinstance(rows, list) or len(rows) != len(wanted):
        raise ValueError('complete component review coverage required')
    seen: set[str] = set()
    pending: list[str] = []
    references: set[str] = set()
    for row in rows:
        ref = row['component']
        if ref in seen or ref not in wanted or set(row) != set(wanted[ref]) or any(row[k] != wanted[ref][k] for k in row if k != 'review'):
            raise ValueError('duplicate, missing or mismatched component review')
        seen.add(ref)
        review = row['review']
        if not isinstance(review, dict) or set(review) != set(wanted[ref]['review']):
            raise ValueError('exact component review record required')
        disposition = review['disposition']
        if disposition not in ('pending', 'source-required', 'no-source-required'):
            raise ValueError('explicit source disposition required')
        for key, kind in [('source_paths', 'corresponding-source'), ('build_paths', 'build-material'), ('notice_paths', 'notice')]:
            paths = review[key]
            if not isinstance(paths, list) or len(paths) > 256 or len(set(paths)) != len(paths):
                raise ValueError('bounded unique material references required')
            for name in paths:
                relative_path(name)
                if name not in materials or materials[name]['kind'] != kind:
                    raise ValueError('missing material or incorrect material kind')
                references.add(name)
        if disposition == 'pending':
            pending.append(ref)
            continue
        for key in ('reviewer', 'reviewed_at', 'applicable_terms', 'rationale'):
            text(review[key], key)
        stamp = datetime.fromisoformat(review['reviewed_at'].replace('Z', '+00:00'))
        if stamp.utcoffset() is None:
            raise ValueError('review timestamp requires an explicit timezone')
        if disposition == 'source-required' and (not review['source_paths'] or not review['build_paths']):
            raise ValueError('required corresponding source and build/patch material missing')
    absent_archives = []
    for key, kind in [('first_party_source_archive', 'corresponding-source'), ('supplier_notice_archive', 'notice')]:
        bound = expected['candidate'][key]
        matches = [name for name, item in materials.items() if item['kind'] == kind and
                   {k: item[k] for k in ('sha256', 'size')} == bound]
        if not matches:
            absent_archives.append(key)
        references.update(matches)
    if set(materials) - references:
        raise ValueError('unreferenced material is not part of this delivery packet')
    return {'schema_version': 'phios.source-delivery-check.v1', 'candidate': expected['candidate'],
        'canonical_manifest_sha256': hashlib.sha256(wire(manifest)).hexdigest(),
        'components_total': len(wanted), 'component_reviews_recorded': len(wanted) - len(pending),
        'pending_components': sorted(pending), 'missing_candidate_archives': absent_archives,
        'verified_material_files': len(materials), 'verified_material_bytes': total,
        'delivery_records_complete': not pending and not absent_archives,
        'review_declarations_authenticated': False, 'license_source_compliance_reviewed': False,
        'iso_bytes_independently_verified': False, 'release_ready': False, 'publication_authority': False}


def bundle(root: Path, manifest: dict[str, Any], materials_root: Path, output: Path) -> dict[str, Any]:
    report = verify(root, manifest, materials_root)
    if not report['delivery_records_complete']:
        raise ValueError('source delivery remains incomplete; bundle held')
    identity, _, candidate_files = candidate(root)
    if identity != report['candidate']:
        raise ValueError('candidate changed while sealing delivery packet')
    # Seal bytes while rechecking every material. No input archive is extracted.
    with tempfile.TemporaryDirectory(prefix='phios-source-delivery-', dir=output.parent) as directory:
        stage = Path(directory)
        files = {**{'candidate/' + k: v for k, v in candidate_files.items()},
            'source-delivery-manifest.json': wire(manifest), 'source-delivery-check.json': wire(report)}
        for name, data in files.items():
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        for item in manifest['materials']:
            target = stage / 'materials' / item['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                observed = hash_file(materials_root, item['path'], stream)
            if observed != {k: item[k] for k in ('sha256', 'size')}:
                raise ValueError('material changed while sealing delivery packet')
        paths = sorted(path for path in stage.rglob('*') if path.is_file())
        (stage / 'SHA256SUMS').write_text(''.join(hash_file(stage, p.relative_to(stage).as_posix())['sha256'] +
            '  ' + p.relative_to(stage).as_posix() + '\n' for p in paths))
        paths.append(stage / 'SHA256SUMS')
        epoch = report['candidate']['source_date_epoch']
        with output.open('xb') as raw:
            try:
                with gzip.GzipFile(fileobj=raw, mode='wb', mtime=epoch, filename='') as compressed:
                    with tarfile.open(fileobj=compressed, mode='w|', format=tarfile.PAX_FORMAT) as archive:
                        for path in sorted(paths):
                            info = tarfile.TarInfo(path.relative_to(stage).as_posix())
                            info.size, info.mode, info.mtime = path.stat().st_size, 0o644, epoch
                            with path.open('rb') as stream:
                                archive.addfile(info, stream)
            except BaseException:
                output.unlink()
                raise
    return {'schema_version': 'phios.source-delivery-bundle.v1', 'archive': hash_file(output.parent, output.name),
        'candidate': report['candidate'], 'delivery_records_complete': True,
        'review_declarations_authenticated': False, 'iso_bytes_independently_verified': False,
        'license_source_compliance_reviewed': False, 'release_ready': False, 'publication_authority': False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('init', 'check', 'bundle'))
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--materials', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'init':
            if args.output is None:
                raise ValueError('init requires --output')
            data = wire(initialize(args.candidate))
            with args.output.open('xb') as stream:
                stream.write(data)
            print(json.dumps({'manifest_written': str(args.output), 'release_ready': False}))
            return 0
        if args.manifest is None or args.materials is None:
            raise ValueError('check/bundle requires --manifest and --materials')
        manifest = decode(read(args.manifest.parent, args.manifest.name))
        if args.command == 'bundle':
            if args.output is None:
                raise ValueError('bundle requires --output')
            result = bundle(args.candidate, manifest, args.materials, args.output)
        else:
            result = verify(args.candidate, manifest, args.materials)
        print(wire(result).decode(), end='')
        return 0 if result['delivery_records_complete'] else 2
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        parser.exit(1, 'Source delivery held: ' + str(exc) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
