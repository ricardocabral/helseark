#!/usr/bin/env python3
"""Build/verify the standalone HL7 FHIR R4 archive; maintenance only, stdlib only.

No runtime imports, schema replacements, extraction, or automatic pin updates.
Source archives remain byte-identical, including original member names.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import gzip
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import sys
import tarfile
import tempfile
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

MAX_SOURCE = 512 * 1024 * 1024
MAX_MEMBER = 256 * 1024 * 1024
MAX_EXPANDED = 2 * 1024 * 1024 * 1024
MAX_MEMBERS = 100_000
MAX_TAR_BYTES = MAX_EXPANDED + MAX_MEMBERS * 1024
MAX_METADATA = 32 * 1024 * 1024
CHUNK = 1024 * 1024
ROOT = Path(__file__).resolve().parents[1]
PINS = 'definitions/archival-sources.json'
TOOLS = ('scripts/build_archival_bundle.py', 'docs/reference/archival-bundle.md')
# Version 1 is a complete, standalone R4 preservation contract. These roles and
# notices are defined by the verifier, never inferred from untrusted inventory.
SOURCE_ROLES = dict(core='tar.gz', specification='zip', schema='zip',
                    downloads='raw', **{'hl7-license': 'raw', 'cc0': 'raw'})
REQUIRED_RETAIN = (
    dict(source='core', member='package/package.json', path='licenses/core-package.json'),
    dict(source='specification', member='site\\license.html', path='licenses/specification-license.html'),
    dict(source='hl7-license', path='licenses/hl7-license.html'),
    dict(source='cc0', path='licenses/cc0.html'),
)
README = b'''# Helseark archival definitions bundle\n\nComplete pinned HL7(R) FHIR(R) R4 4.0.1 core and published specification.\nStart with docs/reference/archival-bundle.md. No installation or server needed.\nOriginal archives are in sources/<sha256>; names, URLs, dates and hashes are in\ndefinitions/archival-sources.json. inventories/ records EVERY archive member.\nmanifest.json hashes every other bundle file; obtain the outer ZIP checksum from\nthe release channel separately. No self-hash, signing, or authenticity claim.\n\nVerify offline after unzipping this outer bundle:\n  python3 scripts/build_archival_bundle.py --verify /path/to/original-bundle.zip\nReproduce offline (Python 3.12+):\n  python3 scripts/build_archival_bundle.py --cache-dir sources --output rebuilt.zip\nDo not put rebuilt.zip inside sources. Compare SHA-256 with the original ZIP.\nRead licenses/hl7-license.html and licenses/cc0.html, including third-party and\ntrademark caveats. The complete core is not a complete terminology service or\nJava validator installation. Runtime/wheel integration remains separate work.\n'''


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode()


def safe_name(name, *, windows=False):
    # The official specification ZIP uses Windows separators. Validate their
    # meaning, but retain the ORIGINAL spelling in member inventories/archives.
    normalized = name.replace('\\', '/') if windows else name
    clean = normalized.removesuffix('/')
    if (not clean or len(name) > 1024 or '\\' in clean or ':' in clean
            or any(ord(c) < 32 for c in name) or '\x7f' in name
            or any(p in ('', '.', '..') for p in clean.split('/'))):
        raise ValueError(f'unsafe path: {name!r}')
    return clean


def local_path(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError(f'symlink refused: {item}')
    return path


def stream_hash(stream, limit):
    count = 0
    digest = hashlib.sha256()
    while block := stream.read(min(CHUNK, limit - count + 1)):
        count += len(block)
        if count > limit:
            raise ValueError('byte limit exceeded')
        digest.update(block)
    return count, digest.hexdigest()


def file_record(path):
    with path.open('rb') as stream:
        size, digest = stream_hash(stream, MAX_SOURCE)
    return dict(size=size, sha256=digest)


def preflight_zip(path):
    """Bound eager ZipFile allocation using a fixed tail and streamed directory.

    Only single-disk classic directories are supported. ZIP64 end records,
    sentinels and central-entry extensions are rejected, not interpreted with
    truncated classic values. ZIP64 *local* size headers remain supported (our
    writer uses them); none of the pinned inputs need ZIP64 directories.
    """
    with path.open('rb') as stream:
        size = stream.seek(0, os.SEEK_END)
        if size > MAX_SOURCE:
            raise ValueError('ZIP source size limit exceeded')
        stream.seek(max(0, size - (22 + 65535 + 20)))
        tail = stream.read(22 + 65535 + 20)
        end = tail.rfind(b'PK\x05\x06')
        if end < 0 or len(tail) - end < 22:
            raise ValueError('invalid ZIP end directory')
        _, disk, start_disk, disk_count, count, directory_size, offset, comment = struct.unpack_from('<4s4H2IH', tail, end)
        if end + 22 + comment != len(tail):
            raise ValueError('invalid ZIP end/comment boundary')
        if (count == 65535 or disk_count == 65535
                or directory_size == 0xffffffff or offset == 0xffffffff
                or tail[max(0, end - 20):end - 16] == b'PK\x06\x07'):
            raise ValueError('ZIP64 directory unsupported')
        if disk or start_disk or disk_count != count:
            raise ValueError('multi-disk/inconsistent ZIP directory unsupported')
        if count > MAX_MEMBERS or directory_size > MAX_METADATA:
            raise ValueError('ZIP directory count/size limit exceeded')
        end_offset = size - len(tail) + end
        if offset + directory_size != end_offset:
            raise ValueError('inconsistent ZIP directory bounds')
        stream.seek(offset)
        total, actual = 0, 0
        # Do not trust the EOCD count: Python itself parses until directory_size.
        while stream.tell() < end_offset:
            header = stream.read(min(46, end_offset - stream.tell()))
            if len(header) != 46 or header[:4] != b'PK\x01\x02':
                raise ValueError('invalid ZIP central directory record')
            compressed, expanded = struct.unpack_from('<II', header, 20)
            name_len, extra_len, comment_len, member_disk = struct.unpack_from('<4H', header, 28)
            local_offset = struct.unpack_from('<I', header, 42)[0]
            if 0xffffffff in (compressed, expanded, local_offset) or member_disk == 65535:
                raise ValueError('ZIP64 directory entry unsupported')
            if member_disk:
                raise ValueError('multi-disk ZIP directory unsupported')
            actual += 1
            total += expanded
            if actual > MAX_MEMBERS or expanded > MAX_MEMBER or total > MAX_EXPANDED:
                raise ValueError('ZIP directory member/expanded limit exceeded')
            next_record = stream.tell() + name_len + extra_len + comment_len
            if next_record > end_offset or not name_len:
                raise ValueError('invalid ZIP directory entry bounds')
            stream.seek(name_len, os.SEEK_CUR)
            extra = stream.read(extra_len)  # At most 65535 bytes, never whole directory.
            index = 0
            while index < len(extra):
                if index + 4 > len(extra):
                    raise ValueError('invalid ZIP directory extra field')
                kind, length = struct.unpack_from('<HH', extra, index)
                index += 4 + length
                if kind == 1:
                    raise ValueError('ZIP64 directory extra unsupported')
                if index > len(extra):
                    raise ValueError('invalid ZIP directory extra bounds')
            stream.seek(next_record)
        if actual != count:
            raise ValueError('inconsistent ZIP directory count')


@contextmanager
def members(path, fmt):
    """Expose regular-file streams without ever extracting upstream paths."""
    if fmt == 'tar.gz':
        # Bound the whole decompressed tar, including padding and PAX headers,
        # before tarfile may allocate memory for an extended header.
        with gzip.open(path, 'rb') as compressed, tempfile.TemporaryFile() as unpacked:
            count = 0
            while block := compressed.read(min(CHUNK, MAX_TAR_BYTES - count + 1)):
                count += len(block)
                if count > MAX_TAR_BYTES:
                    raise ValueError('tar envelope limit exceeded')
                unpacked.write(block)
            unpacked.seek(0)
            with tarfile.open(fileobj=unpacked, mode='r:') as archive:
                def entries():
                    for member in archive:
                        if not (member.isfile() or member.isdir()) or member.issparse():
                            raise ValueError(f'unsafe archive type: {member.name}')
                        yield member.name, member.isdir(), member.size, lambda m=member: archive.extractfile(m)
                yield entries()
    elif fmt == 'zip':
        preflight_zip(path)
        with zipfile.ZipFile(path) as archive:
            if len(archive.infolist()) > MAX_MEMBERS:
                raise ValueError('member count limit exceeded')
            def entries():
                for member in archive.infolist():
                    mode = stat.S_IFMT(member.external_attr >> 16)
                    if mode not in (0, stat.S_IFREG, stat.S_IFDIR) or member.flag_bits & 1:
                        raise ValueError(f'unsafe archive type: {member.filename}')
                    directory = member.is_dir() or member.filename.endswith('\\')
                    if mode == stat.S_IFDIR and not directory:
                        raise ValueError('unsafe directory type')
                    yield member.filename, directory, member.file_size, lambda m=member: archive.open(m)
            yield entries()
    else:
        raise ValueError(f'unsupported archive format: {fmt}')


def archive_inventory(path, fmt):
    records, names = [], {}
    total = 0
    with members(path, fmt) as entries:
        for name, directory, size, opener in entries:
            normalized = safe_name(name, windows=(fmt == 'zip'))
            if normalized.casefold() in names:
                raise ValueError(f'duplicate archive path: {name}')
            names[normalized.casefold()] = directory
            total += size
            if len(names) > MAX_MEMBERS or size > MAX_MEMBER or size < 0 or total > MAX_EXPANDED:
                raise ValueError('archive limit exceeded')
            record = dict(path=name, type='directory' if directory else 'file', size=size)
            if directory:
                if size:
                    raise ValueError('unsafe directory payload')
            else:
                with opener() as stream:
                    actual, digest = stream_hash(stream, min(size, MAX_MEMBER))
                if actual != size:
                    raise ValueError('member size mismatch')
                record['sha256'] = digest
            records.append(record)
    for name in names:
        parts = name.split('/')
        if any(names.get('/'.join(parts[:n])) is False for n in range(1, len(parts))):
            raise ValueError('unsafe file/directory collision')
    return sorted(records, key=lambda r: r['path'])


def membership_summary(records):
    return dict(count=len(records), files=sum(r['type'] == 'file' for r in records),
                expandedSize=sum(r['size'] for r in records),
                sha256=hashlib.sha256(canonical(records)).hexdigest())


def check_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.netloc not in ('hl7.org', 'creativecommons.org')
            or parsed.fragment):
        raise ValueError(f'unreviewed HTTPS URL: {url}')


class ReviewedRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def check_blob(path, source):
    if file_record(path) != {k: source[k] for k in ('size', 'sha256')}:
        raise ValueError(f'source size/hash mismatch: {source["id"]}')


def download(source, destination):
    check_url(source['url'])
    opener = build_opener(ReviewedRedirects())
    # Temporary file shares the destination filesystem. A failed request/hash
    # never replaces a cached file. Corrupt existing cache is never repaired.
    with tempfile.TemporaryDirectory(dir=destination.parent) as temp:
        pending = Path(temp) / 'download'
        with opener.open(Request(source['url'], headers={'User-Agent': 'helseark-archival/1'}), timeout=60) as response:
            check_url(response.url)
            with pending.open('wb') as output:
                count = 0
                while block := response.read(min(CHUNK, source['size'] - count + 1)):
                    count += len(block)
                    if count > source['size']:
                        raise ValueError('download size limit exceeded')
                    output.write(block)
        check_blob(pending, source)
        os.link(pending, destination)


def load_pins(path):
    if path.stat().st_size > MAX_METADATA:
        raise ValueError('metadata limit exceeded')
    pins = json.loads(path.read_bytes())
    if pins['bundleVersion'] != 1 or pins['fhirVersion'] != '4.0.1':
        raise ValueError('unsupported bundle/FHIR version')
    ids, hashes = set(), set()
    for source in pins['sources']:
        if not re.fullmatch(r'[a-z][a-z0-9-]*', source['id']) or source['id'] in ids:
            raise ValueError('invalid/duplicate source ID')
        ids.add(source['id'])
        if not re.fullmatch('[a-f0-9]{64}', source['sha256']) or source['sha256'] in hashes:
            raise ValueError('invalid/duplicate source hash')
        hashes.add(source['sha256'])
        if type(source['size']) is not int or not 0 < source['size'] <= MAX_SOURCE:
            raise ValueError('source size limit exceeded')
        if source['format'] not in ('zip', 'tar.gz', 'raw'):
            raise ValueError('unsupported source format')
        check_url(source['url'])
    if {s['id']: s['format'] for s in pins['sources']} != SOURCE_ROLES:
        raise ValueError('required version 1 source roles/formats missing or changed')
    if (len(pins['retain']) != len(REQUIRED_RETAIN)
            or any(r not in pins['retain'] for r in REQUIRED_RETAIN)):
        raise ValueError('required version 1 retained notices missing or changed')
    paths = set()
    for retained in pins['retain']:
        name = safe_name(retained['path'])
        if not name.startswith('licenses/') or name in paths or retained['source'] not in ids:
            raise ValueError('invalid retained license path/source')
        paths.add(name)
    return pins


def inspect_sources(pins, cache, fetch=False):
    inventories = {}
    for source in pins['sources']:
        path = local_path(cache / source['sha256'])
        if not path.exists():
            if not fetch:
                raise ValueError(f'missing cache source: {source["id"]} ({path})')
            download(source, path)
        if not path.is_file():
            raise ValueError('cache source is not a regular file')
        check_blob(path, source)
        if source['format'] != 'raw':
            records = archive_inventory(path, source['format'])
            if not any(r['type'] == 'file' and r['size'] > 0 for r in records):
                raise ValueError('empty required source archive')
            if membership_summary(records) != source['membership']:
                raise ValueError(f'archive membership mismatch: {source["id"]}')
            inventories[source['id']] = records
    sources = {s['id']: s for s in pins['sources']}
    metadata = json.loads(retained_bytes(sources['core'], cache, 'package/package.json'))
    if any(metadata.get(k) != v for k, v in dict(name='hl7.fhir.r4.core', version='4.0.1', license='CC0-1.0').items()):
        raise ValueError('core package identity/license mismatch')
    return inventories


def retained_bytes(source, cache, member=None):
    path = cache / source['sha256']
    if source['format'] == 'raw' and member is None:
        if source['size'] > MAX_METADATA:
            raise ValueError('retained file limit exceeded')
        return path.read_bytes()
    with members(path, source['format']) as entries:
        for name, directory, size, opener in entries:
            if name == member and not directory:
                if size > MAX_METADATA:
                    raise ValueError('retained member limit exceeded')
                with opener() as stream:
                    return stream.read(MAX_METADATA + 1)
    raise ValueError(f'missing retained member: {member}')


def build(pins_path, cache, output, fetch=False):
    pins_path, cache, output = map(local_path, (pins_path, cache, output))
    if output.exists():
        raise FileExistsError(output)
    pins = load_pins(pins_path)
    cache.mkdir(parents=True, exist_ok=True)
    inventories = inspect_sources(pins, cache, fetch)
    sources = {s['id']: s for s in pins['sources']}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        stage = Path(temp)
        files = {PINS: pins_path.read_bytes(), 'README.md': README,
                 'LICENSE': local_path(ROOT / 'LICENSE').read_bytes()}
        for name in TOOLS:
            files[name] = local_path(ROOT / name).read_bytes()
        for key, records in inventories.items():
            files[f'inventories/{key}.json'] = canonical(records)
        for retained in pins['retain']:
            files[retained['path']] = retained_bytes(sources[retained['source']], cache, retained.get('member'))
        paths = {}
        for name, data in files.items():
            path = stage / safe_name(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            paths[name] = path
        for source in pins['sources']:
            paths['sources/' + source['sha256']] = cache / source['sha256']
        manifest = dict(bundleVersion=1, fhirVersion='4.0.1', files=[dict(path=name, **file_record(path)) for name, path in sorted(paths.items())])
        (stage / 'manifest.json').write_bytes(canonical(manifest))
        paths['manifest.json'] = stage / 'manifest.json'
        pending = stage / 'bundle.zip'
        with zipfile.ZipFile(pending, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            for name, path in sorted(paths.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                with archive.open(info, 'w', force_zip64=True) as target, path.open('rb') as stream:
                    shutil.copyfileobj(stream, target, CHUNK)
        result = file_record(pending)
        os.link(pending, output)  # Atomic publication with no overwrite.
    return result


def verify(bundle):
    bundle = local_path(bundle)
    # Validate outer names/types/limits before reading any metadata or writing.
    outer = archive_inventory(bundle, 'zip')
    with zipfile.ZipFile(bundle) as archive, tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve()) as temp:
        stage = Path(temp)
        if archive.getinfo('manifest.json').file_size > MAX_METADATA:
            raise ValueError('manifest limit exceeded')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('bundleVersion') != 1 or manifest.get('fhirVersion') != '4.0.1':
            raise ValueError('unsupported bundle manifest')
        actual = [dict(path=r['path'], size=r['size'], sha256=r['sha256']) for r in outer if r['path'] != 'manifest.json' and r['type'] == 'file']
        if manifest['files'] != actual or len(outer) != len(actual) + 1:
            raise ValueError('bundle manifest hash/membership mismatch')
        if archive.getinfo(PINS).file_size > MAX_METADATA:
            raise ValueError('pins limit exceeded')
        pin_bytes = archive.read(PINS)
        pin_path = stage / 'pins.json'
        pin_path.write_bytes(pin_bytes)
        pins = load_pins(pin_path)
        required = {PINS, 'README.md', 'manifest.json', *TOOLS}
        # Version-1 archives originally had no project license. Retain support
        # for those exact archives; validate the added license when present.
        if 'LICENSE' in archive.namelist():
            required.add('LICENSE')
        required.update(r['path'] for r in REQUIRED_RETAIN)
        required.update('sources/' + s['sha256'] for s in pins['sources'])
        required.update(f'inventories/{s["id"]}.json' for s in pins['sources'] if s['format'] != 'raw')
        if set(archive.namelist()) != required:
            raise ValueError('required version 1 bundle structure mismatch')
        for name in required - {'manifest.json'}:
            info = archive.getinfo(name)
            if not info.file_size or (not name.startswith('sources/') and info.file_size > MAX_METADATA):
                raise ValueError('required bundle support empty or metadata limit exceeded')
        cache = stage / 'cache'
        cache.mkdir()
        for source in pins['sources']:
            with archive.open('sources/' + source['sha256']) as stream, (cache / source['sha256']).open('wb') as target:
                shutil.copyfileobj(stream, target, CHUNK)
        inventories = inspect_sources(pins, cache)
        for key, records in inventories.items():
            if archive.read(f'inventories/{key}.json') != canonical(records):
                raise ValueError('member inventory mismatch')
        sources = {s['id']: s for s in pins['sources']}
        for retained in pins['retain']:
            if archive.read(retained['path']) != retained_bytes(sources[retained['source']], cache, retained.get('member')):
                raise ValueError('retained license mismatch')
    return file_record(bundle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, default=ROOT / PINS)
    parser.add_argument('--cache-dir', type=Path, default=ROOT / 'dist/archival-cache')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/helseark-fhir-r4-4.0.1-archival.zip')
    parser.add_argument('--fetch', action='store_true', help='explicit maintenance download of missing pinned blobs only')
    parser.add_argument('--verify', type=Path, metavar='BUNDLE', help='verify existing bundle offline')
    args = parser.parse_args()
    if args.verify and args.fetch:
        parser.error('--verify is offline; cannot combine with --fetch')
    try:
        result = verify(args.verify) if args.verify else build(args.sources, args.cache_dir, args.output, args.fetch)
    except (ValueError, OSError, KeyError, tarfile.TarError, zipfile.BadZipFile) as exc:
        parser.exit(1, f'archival bundle: {exc}\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
