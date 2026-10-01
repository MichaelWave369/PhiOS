"""Validate a candidate SBOM against hash-pinned official CycloneDX schemas."""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

import jsonschema


def validate(sbom: Path) -> None:
    lock = json.loads(Path(__file__).with_name('sbom-schema-lock.json').read_text())
    store = {}
    schemas = {}
    for name, expected in lock['files'].items():
        with urllib.request.urlopen(lock['base_url'] + name, timeout=30) as response:
            data = response.read(1024**2 + 1)
        if len(data) > 1024**2 or hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('official schema bytes differ from reviewed lock')
        schema = json.loads(data)
        schemas[name] = schema
        for protocol in ['http', 'https']:
            store[f'{protocol}://cyclonedx.org/schema/{name}'] = schema
    # This supported resolver API also works with the Ubuntu runner's system
    # jsonschema package; every external schema is captured and hash checked.
    resolver = jsonschema.RefResolver.from_schema(schemas['bom-1.6.schema.json'], store=store)
    jsonschema.Draft7Validator(schemas['bom-1.6.schema.json'], resolver=resolver).validate(json.loads(sbom.read_text()))
    print('Candidate SBOM matches pinned official CycloneDX 1.6 schemas')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sbom', type=Path)
    validate(parser.parse_args().sbom)
