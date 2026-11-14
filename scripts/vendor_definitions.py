#!/usr/bin/env python3
"""Maintain the pinned HL7® FHIR® R4 upstream subset (Python stdlib only).

Default / --verify: offline byte, inventory, dialect and definition-closure checks.
--fetch: explicit maintenance-time acquisition; downloads only pinned URLs and
refuses changed upstream bytes. --cache-dir stores source blobs by SHA-256 and
can reproduce the distribution without networking when all blobs are present.
--root selects a checkout or staging directory containing the reviewed inventory.

To update pins: independently acquire/review official versioned downloads, review
licenses and subset selection, then explicitly update upstream-inventory.json.
This script never generates pins, changes definitions/lock.json, or runs at runtime.
Upstream files are copied verbatim; no schema rewriting or terminology resolution.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import sys
import tarfile
from urllib.request import Request, urlopen
import zipfile

INVENTORY = 'definitions/upstream-inventory.json'
PREFIXES = ('definitions/hl7.fhir.r4.core/4.0.1/',
            'definitions/fhir-r4-json-schema/', 'definitions/docs/r4/')
CORE = PREFIXES[0] + 'package/'
SCHEMA = PREFIXES[1] + 'fhir.schema.json'
CANONICAL = 'http://hl7.org/fhir/StructureDefinition/'
MAX_SOURCE = 16 * 1024 * 1024
MAX_FILE = 8 * 1024 * 1024


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_bytes(data: bytes, entry: dict, label: str) -> None:
    if len(data) != entry['size'] or digest(data) != entry['sha256']:
        raise ValueError(f'byte/hash mismatch: {label}')


def confined(root: Path, name: str) -> Path:
    parts = PurePosixPath(name).parts
    if not parts or name != '/'.join(parts) or any(p in ('.', '..') for p in parts):
        raise ValueError(f'unsafe path: {name}')
    if PurePosixPath(name).is_absolute() or '\\' in name:
        raise ValueError(f'unsafe path: {name}')
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f'symlink refused: {path}')
    return path


def load_inventory(root: Path) -> dict:
    inv = json.loads(confined(root, INVENTORY).read_bytes())
    if inv['inventoryVersion'] != 1 or inv['fhirVersion'] != '4.0.1':
        raise ValueError('unsupported upstream inventory version')
    sources = {s['id']: s for s in inv['sources']}
    if len(sources) != len(inv['sources']):
        raise ValueError('duplicate source')
    for entry in inv['sources'] + inv['files']:
        h = entry['sha256']
        if len(h) != 64 or any(c not in '0123456789abcdef' for c in h):
            raise ValueError('invalid SHA-256 pin')
        limit = MAX_SOURCE if 'url' in entry else MAX_FILE
        if type(entry['size']) is not int or not 0 < entry['size'] <= limit:
            raise ValueError('invalid size pin')
    paths = set()
    for entry in inv['files']:
        name = entry['path']
        confined(root, name)
        if not name.startswith(PREFIXES) or name in paths:
            raise ValueError(f'out-of-scope or duplicate output: {name}')
        paths.add(name)
        if entry['source'] not in sources:
            raise ValueError(f'unknown source: {name}')
    for s in sources.values():
        if not (s['url'].startswith('https://hl7.org/fhir/R4/') or
                s['url'] == 'https://creativecommons.org/publicdomain/zero/1.0/legalcode.en'):
            raise ValueError('only official pinned HTTPS sources allowed')
        if s['format'] not in ('raw', 'tar.gz', 'zip'):
            raise ValueError('unsupported source format')
    return inv


def verify_artifacts(files: dict[str, bytes], inv: dict) -> None:
    package = json.loads(files[CORE + 'package.json'])
    if (package['name'], package['version'], package['license']) != (
            'hl7.fhir.r4.core', '4.0.1', 'CC0-1.0'):
        raise ValueError('unexpected upstream package identity/license')
    definitions = {}
    for path, data in files.items():
        if path.startswith(CORE + 'StructureDefinition-'):
            d = json.loads(data)
            if d['resourceType'] != 'StructureDefinition' or d['fhirVersion'] != '4.0.1':
                raise ValueError(f'wrong definition identity: {path}')
            if d['url'] in definitions:
                raise ValueError('duplicate StructureDefinition URL')
            definitions[d['url']] = d
    pending = [CANONICAL + t for t in inv['selection']['resources']]
    reached = set()
    while pending:
        url = pending.pop()
        if url in reached:
            continue
        if url not in definitions:
            raise ValueError(f'missing core definition: {url}')
        reached.add(url)
        d = definitions[url]
        refs = [d['baseDefinition']] if 'baseDefinition' in d else []
        for e in d.get('snapshot', {}).get('element', []):
            for t in e.get('type', []):
                code = t['code']
                if not code.startswith('http://hl7.org/fhirpath/System.'):
                    refs.append(code if '://' in code else CANONICAL + code)
        pending.extend(refs)
    if reached != set(definitions):
        raise ValueError('core subset contains unrelated definitions')
    schema = json.loads(files[SCHEMA])
    if schema['$schema'] != 'http://json-schema.org/draft-06/schema#':
        raise ValueError('upstream schema dialect changed')
    for resource in inv['selection']['resources']:
        if resource not in schema['definitions']:
            raise ValueError(f'missing resource schema: {resource}')

    def references(node):
        if isinstance(node, dict):
            if '$ref' in node:
                ref = node['$ref']
                if not ref.startswith('#/'):
                    raise ValueError(f'nonlocal schema reference: {ref}')
                target = schema
                for token in ref[2:].split('/'):
                    target = target[token.replace('~1', '/').replace('~0', '~')]
            for value in node.values():
                references(value)
        elif isinstance(node, list):
            for value in node:
                references(value)
    references(schema)


def acquire(source: dict, cache: Path | None) -> bytes:
    cached = confined(cache, source['sha256']) if cache else None
    if cached and cached.exists():
        if cached.stat().st_size != source['size']:
            raise ValueError(f"byte/hash mismatch: {cached}")
        data = cached.read_bytes()
    else:
        request = Request(source['url'], headers={
            'User-Agent': 'Mozilla/5.0 (compatible; HelsearkDefinitionVendor/1.0)'})
        with urlopen(request, timeout=60) as response:
            if not response.geturl().startswith('https://'):
                raise ValueError('non-HTTPS redirect refused')
            data = response.read(source['size'] + 1)
        check_bytes(data, source, source['url'])
        if cached:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(data)
    check_bytes(data, source, source['url'])
    return data


def fetch(root: Path, inv: dict, cache: Path | None) -> None:
    files = {}
    # No writes to definitions until ALL sources, members and semantics pass.
    for source in inv['sources']:
        data = acquire(source, cache)
        selected = [f for f in inv['files'] if f['source'] == source['id']]
        if source['format'] == 'tar.gz':
            with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
                members = {m.name: m for m in archive}
                for entry in selected:
                    member = members[entry['member']]
                    if not member.isfile() or member.size != entry['size']:
                        raise ValueError('invalid tar member')
                    with archive.extractfile(member) as stream:
                        files[entry['path']] = stream.read(entry['size'] + 1)
        elif source['format'] == 'zip':
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for entry in selected:
                    member = archive.getinfo(entry['member'])
                    if member.file_size != entry['size']:
                        raise ValueError('invalid zip member')
                    files[entry['path']] = archive.read(member)
        else:
            for entry in selected:
                files[entry['path']] = data
    for entry in inv['files']:
        check_bytes(files[entry['path']], entry, entry['path'])
        path = confined(root, entry['path'])
        if path.exists():
            if path.stat().st_size != entry['size']:
                raise ValueError(f'byte/hash mismatch: {path}')
            check_bytes(path.read_bytes(), entry, str(path))
    verify_artifacts(files, inv)
    for name, data in files.items():
        path = confined(root, name)
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        # A failed run can leave a partial distribution; --verify detects it and
        # --fetch safely resumes missing files. Existing changed files are refused.
        with path.open('xb') as stream:
            stream.write(data)


def verify(root: Path, inv: dict) -> None:
    files = {}
    for entry in inv['files']:
        path = confined(root, entry['path'])
        if path.stat().st_size != entry['size']:
            raise ValueError(f'byte/hash mismatch: {path}')
        data = path.read_bytes()
        check_bytes(data, entry, str(path))
        files[entry['path']] = data
    for prefix in PREFIXES:
        for path in confined(root, prefix.rstrip('/')).rglob('*'):
            if path.is_symlink():
                raise ValueError(f'symlink refused: {path}')
            if path.is_file() and path.relative_to(root).as_posix() not in files:
                raise ValueError(f'uninventoried file: {path}')
    verify_artifacts(files, inv)
    print(f'Verified {len(files)} upstream files, {sum(map(len, files.values()))} bytes; '
          'SHA-256 pins, FHIR 4.0.1 closure, draft-06 and local schema references.')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--verify', action='store_true', help='offline verification (default)')
    modes.add_argument('--fetch', action='store_true', help='explicit maintainer acquisition')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--cache-dir', type=Path, help='optional SHA-256 source blob cache')
    args = parser.parse_args()
    try:
        root = args.root.resolve(strict=True)
        inv = load_inventory(root)
        if args.fetch:
            fetch(root, inv, args.cache_dir)
        verify(root, inv)
    except (OSError, ValueError, KeyError, tarfile.TarError, zipfile.BadZipFile) as error:
        print(f'vendoring failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
