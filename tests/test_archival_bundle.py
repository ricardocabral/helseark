"""Behavioral tests use synthetic archives; official large inputs stay in dist/."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import socket
import struct
import tarfile
import zipfile

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/build_archival_bundle.py'
spec = importlib.util.spec_from_file_location('archival', SCRIPT)
archival = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archival)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tar_bytes(entries):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w:gz') as tar:
        for name, value in entries:
            member = tarfile.TarInfo(name)
            if value is None:
                member.type = tarfile.SYMTYPE
                member.linkname = '../../escape'
                tar.addfile(member)
            else:
                member.size = len(value)
                tar.addfile(member, io.BytesIO(value))
    return out.getvalue()


def zip_bytes(entries, symlink=False):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as archive:
        for name, value in entries:
            info = zipfile.ZipInfo(name)
            if symlink:
                info.create_system = 3
                info.external_attr = 0o120777 << 16
            archive.writestr(info, value)
    return out.getvalue()


@pytest.fixture
def inputs(tmp_path):
    cache = tmp_path / 'cache'
    cache.mkdir()
    sources = []
    for name, fmt, data in [
        ('core', 'tar.gz', tar_bytes([('package/package.json', b'{"name":"hl7.fhir.r4.core","version":"4.0.1","license":"CC0-1.0"}'), ('package/extra.json', b'untouched')])),
        ('specification', 'zip', zip_bytes([('index.html', b'offline'), ('site\\license.html', b'CC0; trademarks; third-party terms'), ('assets/style.css', b'body {}')])),
        ('schema', 'zip', zip_bytes([('fhir.schema.json', b'{"synthetic":true}')])),
        ('downloads', 'raw', b'downloads page'),
        ('hl7-license', 'raw', b'HL7 license page'),
        ('cc0', 'raw', b'license text'),
    ]:
        path = cache / sha(data)
        path.write_bytes(data)
        entry = dict(id=name, filename=name + '.archive', format=fmt,
                     url='https://hl7.org/fhir/R4/' + name, size=len(data), sha256=sha(data))
        if fmt != 'raw':
            members = archival.archive_inventory(path, fmt)
            entry['membership'] = archival.membership_summary(members)
        sources.append(entry)
    pins = dict(bundleVersion=1, fhirVersion='4.0.1', sources=sources,
                retain=[dict(source='specification', member='site\\license.html', path='licenses/specification-license.html'),
                        dict(source='cc0', path='licenses/cc0.html'),
                        dict(source='core', member='package/package.json', path='licenses/core-package.json'),
                        dict(source='hl7-license', path='licenses/hl7-license.html')])
    manifest = tmp_path / 'pins.json'
    manifest.write_text(json.dumps(pins))
    return manifest, cache


def test_complete_sources_and_reproducible_offline_bundle(inputs, tmp_path, monkeypatch):
    pins, cache = inputs
    def forbidden(*args, **kwargs):
        pytest.fail('network attempted')
    monkeypatch.setattr(socket, 'socket', forbidden)
    first, second = tmp_path / 'first.zip', tmp_path / 'second.zip'
    archival.build(pins, cache, first)
    archival.build(pins, cache, second)
    assert first.read_bytes() == second.read_bytes()
    archival.verify(first)
    with zipfile.ZipFile(first) as bundle:
        lock = json.loads(pins.read_bytes())
        for source in lock['sources']:
            assert bundle.read('sources/' + source['sha256']) == (cache / source['sha256']).read_bytes()
        inventory = json.loads(bundle.read('inventories/specification.json'))
        assert {m['path'] for m in inventory} == {'index.html', 'site\\license.html', 'assets/style.css'}
        assert bundle.read('licenses/specification-license.html') == b'CC0; trademarks; third-party terms'
        assert bundle.read('LICENSE') == (SCRIPT.parents[1] / 'LICENSE').read_bytes()
        assert 'scripts/build_archival_bundle.py' in bundle.namelist()


@pytest.mark.parametrize('fmt', ['tar.gz', 'zip'])
@pytest.mark.parametrize('name', ['../escape', '/absolute', 'a/../../escape', '..\\escape', 'C:/escape', 'a//b', './a'])
def test_unsafe_archive_paths_rejected(tmp_path, fmt, name):
    path = tmp_path / 'bad'
    path.write_bytes(tar_bytes([(name, b'x')]) if fmt == 'tar.gz' else zip_bytes([(name, b'x')]))
    with pytest.raises(ValueError, match='unsafe'):
        archival.archive_inventory(path, fmt)


@pytest.mark.parametrize('fmt', ['tar.gz', 'zip'])
def test_archive_symlinks_rejected(tmp_path, fmt):
    path = tmp_path / 'bad'
    path.write_bytes(tar_bytes([('link', None)]) if fmt == 'tar.gz' else zip_bytes([('link', b'target')], symlink=True))
    with pytest.raises(ValueError, match='type|symlink'):
        archival.archive_inventory(path, fmt)


@pytest.mark.parametrize('fmt', ['tar.gz', 'zip'])
def test_duplicate_members_rejected(tmp_path, fmt):
    path = tmp_path / 'bad'
    entries = [('same', b'one'), ('same', b'two')]
    with pytest.warns(UserWarning) if fmt == 'zip' else __import__('contextlib').nullcontext():
        path.write_bytes(tar_bytes(entries) if fmt == 'tar.gz' else zip_bytes(entries))
    with pytest.raises(ValueError, match='duplicate'):
        archival.archive_inventory(path, fmt)


def test_hash_mismatch_does_not_publish_or_fetch(inputs, tmp_path, monkeypatch):
    pins, cache = inputs
    source = json.loads(pins.read_bytes())['sources'][0]
    (cache / source['sha256']).write_bytes(b'corrupt')
    monkeypatch.setattr(archival, 'download', lambda *a: pytest.fail('attempted repair download'))
    output = tmp_path / 'bundle.zip'
    with pytest.raises(ValueError, match='hash|size'):
        archival.build(pins, cache, output, fetch=True)
    assert not output.exists()


def test_missing_cache_fails_without_network(inputs, tmp_path, monkeypatch):
    pins, cache = inputs
    next(cache.iterdir()).unlink()
    monkeypatch.setattr(archival, 'download', lambda *a: pytest.fail('network attempted'))
    with pytest.raises(ValueError, match='missing'):
        archival.build(pins, cache, tmp_path / 'bundle.zip')


def test_symlink_cache_refused(inputs, tmp_path):
    pins, cache = inputs
    blob = next(cache.iterdir())
    data = blob.read_bytes()
    blob.unlink()
    target = tmp_path / 'target'
    target.write_bytes(data)
    blob.symlink_to(target)
    with pytest.raises(ValueError, match='symlink'):
        archival.build(pins, cache, tmp_path / 'bundle.zip')


def test_membership_pin_mismatch_rejected(inputs, tmp_path):
    pins, cache = inputs
    lock = json.loads(pins.read_bytes())
    lock['sources'][0]['membership']['sha256'] = '0' * 64
    pins.write_text(json.dumps(lock))
    with pytest.raises(ValueError, match='membership'):
        archival.build(pins, cache, tmp_path / 'bundle.zip')


def test_bounds_enforced(tmp_path, monkeypatch):
    path = tmp_path / 'big.zip'
    path.write_bytes(zip_bytes([('big', b'12345')]))
    monkeypatch.setattr(archival, 'MAX_MEMBER', 4)
    with pytest.raises(ValueError, match='limit'):
        archival.archive_inventory(path, 'zip')


def test_existing_output_preserved(inputs, tmp_path):
    pins, cache = inputs
    output = tmp_path / 'bundle.zip'
    output.write_bytes(b'existing')
    with pytest.raises((ValueError, FileExistsError)):
        archival.build(pins, cache, output)
    assert output.read_bytes() == b'existing'


def test_transport_rejects_unreviewed_hosts_before_request():
    for url in ['http://hl7.org/fhir/R4/x', 'https://evil.example/x', 'https://hl7.org@evil.example/x', 'https://hl7.org:443/x']:
        with pytest.raises(ValueError):
            archival.check_url(url)


def test_windows_spec_paths_preserved_and_hashed(tmp_path):
    path = tmp_path / 'windows.zip'
    path.write_bytes(zip_bytes([('site\\index.html', b'offline')]))
    assert archival.archive_inventory(path, 'zip') == [
        {'path': 'site\\index.html', 'type': 'file', 'size': 7,
         'sha256': '8e2c7ac508139a02af859de64a4743c1f3946837279332c35ec8f5ddf20654ae'}]


@pytest.mark.parametrize('entries', [
    [('a', b'file'), ('a/b', b'child')],
    [('site\\index.html', b'one'), ('site/index.html', b'two')],
    [('A', b'one'), ('a', b'two')],
])
def test_archive_aliases_and_parent_files_rejected(tmp_path, entries):
    path = tmp_path / 'bad.zip'
    path.write_bytes(zip_bytes(entries))
    with pytest.raises(ValueError, match='unsafe|duplicate'):
        archival.archive_inventory(path, 'zip')


@pytest.mark.parametrize('limit,value', [('MAX_MEMBERS', 1), ('MAX_EXPANDED', 3)])
def test_aggregate_bounds(tmp_path, monkeypatch, limit, value):
    path = tmp_path / 'bad.zip'
    path.write_bytes(zip_bytes([('one', b'12'), ('two', b'34')]))
    monkeypatch.setattr(archival, limit, value)
    with pytest.raises(ValueError, match='limit'):
        archival.archive_inventory(path, 'zip')


def test_tampered_bundle_rejected(inputs, tmp_path):
    pins, cache = inputs
    good, bad = tmp_path / 'good.zip', tmp_path / 'bad.zip'
    archival.build(pins, cache, good)
    with zipfile.ZipFile(good) as original, zipfile.ZipFile(bad, 'w') as changed:
        for name in original.namelist():
            changed.writestr(name, b'corrupt' if name == 'README.md' else original.read(name))
    with pytest.raises(ValueError, match='manifest'):
        archival.verify(bad)


def test_redirect_policy_checked_before_dispatch():
    from urllib.request import Request
    handler = archival.ReviewedRedirects()
    with pytest.raises(ValueError, match='unreviewed'):
        handler.redirect_request(Request('https://hl7.org/fhir/R4/a'), None, 302, 'Found', {}, 'https://evil.example/redirect')


def test_successful_fetch_is_pinned_and_cached(inputs, tmp_path, monkeypatch):
    pins, cache = inputs
    lock = json.loads(pins.read_bytes())
    source = lock['sources'][-1]
    blob = cache / source['sha256']
    data = blob.read_bytes()
    blob.unlink()
    class Response(io.BytesIO):
        url = source['url']
    class Opener:
        def open(self, request, timeout):
            assert request.full_url == source['url']
            return Response(data)
    monkeypatch.setattr(archival, 'build_opener', lambda *a: Opener())
    archival.build(pins, cache, tmp_path / 'fetched.zip', fetch=True)
    assert blob.read_bytes() == data
    archival.verify(tmp_path / 'fetched.zip')


@pytest.mark.parametrize('data', [b'wrong bytes', b'x' * 100])
def test_failed_fetch_is_never_cached(inputs, tmp_path, monkeypatch, data):
    pins, cache = inputs
    source = json.loads(pins.read_bytes())['sources'][-1]
    blob = cache / source['sha256']
    blob.unlink()
    class Response(io.BytesIO):
        url = source['url']
    class Opener:
        def open(self, *args, **kwargs):
            return Response(data)
    monkeypatch.setattr(archival, 'build_opener', lambda *a: Opener())
    with pytest.raises(ValueError, match='size|hash|limit'):
        archival.build(pins, cache, tmp_path / 'failed.zip', fetch=True)
    assert not blob.exists()
    assert not (tmp_path / 'failed.zip').exists()


def test_gzip_envelope_expansion_is_bounded(tmp_path, monkeypatch):
    # Tar padding/metadata must count too, even if there are no large members.
    path = tmp_path / 'padding.tgz'
    path.write_bytes(tar_bytes([('tiny', b'x')]))
    monkeypatch.setattr(archival, 'MAX_TAR_BYTES', 100)
    with pytest.raises(ValueError, match='limit'):
        archival.archive_inventory(path, 'tar.gz')


def test_bundle_rebuilds_with_its_own_script_and_files(inputs, tmp_path):
    import subprocess
    import sys
    pins, cache = inputs
    first = tmp_path / 'first.zip'
    archival.build(pins, cache, first)
    extracted = tmp_path / 'standalone'
    with zipfile.ZipFile(first) as bundle:
        bundle.extractall(extracted)  # Our generated outer ZIP, not upstream.
    second = tmp_path / 'second.zip'
    runner = '''import runpy,sys

def deny(event, args):
    if event.startswith(('socket.', 'urllib.')):
        raise RuntimeError('network attempted: ' + event)
sys.addaudithook(deny)
script = sys.argv.pop(1)
runpy.run_path(script, run_name='__main__')
'''
    result = subprocess.run([sys.executable, '-c', runner,
                             str(extracted / 'scripts/build_archival_bundle.py'),
                             '--cache-dir', str(extracted / 'sources'),
                             '--output', str(second)], cwd=tmp_path,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert first.read_bytes() == second.read_bytes()


def test_hardlinks_and_devices_rejected(tmp_path):
    for kind in (tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.FIFOTYPE):
        out = io.BytesIO()
        with tarfile.open(fileobj=out, mode='w:gz') as tar:
            member = tarfile.TarInfo('special')
            member.type = kind
            member.linkname = 'other'
            tar.addfile(member)
        path = tmp_path / 'bad.tgz'
        path.write_bytes(out.getvalue())
        with pytest.raises(ValueError, match='type'):
            archival.archive_inventory(path, 'tar.gz')


def test_symlink_output_parent_refused(inputs, tmp_path):
    pins, cache = inputs
    real = tmp_path / 'real'
    real.mkdir()
    link = tmp_path / 'link'
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        archival.build(pins, cache, link / 'output.zip')
    assert not (real / 'output.zip').exists()


def rewrite_bundle(original, output, *, omit=(), change_pins=None, replacements=None):
    # Recompute the manifest, so acceptance cannot rely only on self-consistency.
    with zipfile.ZipFile(original) as archive:
        files = {n: archive.read(n) for n in archive.namelist()
                 if n not in (*omit, 'manifest.json')}
    if change_pins:
        pins = json.loads(files[archival.PINS])
        change_pins(pins)
        files[archival.PINS] = archival.canonical(pins)
    files.update(replacements or {})
    manifest = dict(bundleVersion=1, fhirVersion='4.0.1', files=[
        dict(path=n, size=len(data), sha256=sha(data)) for n, data in sorted(files.items())])
    files['manifest.json'] = archival.canonical(manifest)
    with zipfile.ZipFile(output, 'w') as archive:
        for name, data in files.items():
            archive.writestr(name, data)


@pytest.mark.parametrize('missing', ['README.md', 'scripts/build_archival_bundle.py',
    'docs/reference/archival-bundle.md', 'licenses/cc0.html',
    'licenses/specification-license.html', 'licenses/core-package.json',
    'licenses/hl7-license.html', 'inventories/core.json', 'inventories/specification.json'])
def test_verify_requires_support_even_with_consistent_manifest(inputs, tmp_path, missing):
    pins, cache = inputs
    good, bad = tmp_path / 'good.zip', tmp_path / 'bad.zip'
    archival.build(pins, cache, good)
    rewrite_bundle(good, bad, omit=[missing])
    with pytest.raises(ValueError, match='required|structure'):
        archival.verify(bad)


@pytest.mark.parametrize('role', ['core', 'specification', 'schema', 'downloads', 'hl7-license', 'cc0', 'all'])
def test_build_requires_versioned_source_roles(inputs, tmp_path, role):
    pins, cache = inputs
    lock = json.loads(pins.read_bytes())
    lock['sources'] = [s for s in lock['sources'] if role != 'all' and s['id'] != role]
    lock['retain'] = [r for r in lock['retain'] if role != 'all' and r['source'] != role]
    pins.write_bytes(archival.canonical(lock))
    output = tmp_path / 'bad.zip'
    with pytest.raises(ValueError, match='required|role'):
        archival.build(pins, cache, output)
    assert not output.exists()


def test_verify_rejects_empty_pins_and_self_consistent_bundle(inputs, tmp_path):
    pins, cache = inputs
    good, bad = tmp_path / 'good.zip', tmp_path / 'bad.zip'
    archival.build(pins, cache, good)
    rewrite_bundle(good, bad, change_pins=lambda p: p.update(sources=[], retain=[]))
    with pytest.raises(ValueError, match='required|role'):
        archival.verify(bad)


@pytest.mark.parametrize('role', ['core', 'specification', 'schema'])
def test_empty_archive_is_not_a_complete_role(inputs, tmp_path, role):
    pins, cache = inputs
    lock = json.loads(pins.read_bytes())
    source = next(s for s in lock['sources'] if s['id'] == role)
    data = tar_bytes([]) if role == 'core' else zip_bytes([])
    path = cache / sha(data)
    path.write_bytes(data)
    source.update(size=len(data), sha256=sha(data),
                  membership=archival.membership_summary(archival.archive_inventory(path, source['format'])))
    pins.write_bytes(archival.canonical(lock))
    with pytest.raises(ValueError, match='empty|required'):
        archival.build(pins, cache, tmp_path / 'bad.zip')


@pytest.mark.parametrize('limit', ['MAX_MEMBERS', 'MAX_METADATA', 'MAX_SOURCE'])
@pytest.mark.parametrize('operation', ['inspect', 'verify'])
def test_zip_limits_precede_eager_directory_allocation(tmp_path, monkeypatch, limit, operation):
    path = tmp_path / 'tiny.zip'
    path.write_bytes(zip_bytes([('one', b'12'), ('two', b'34')]))
    monkeypatch.setattr(archival, limit, 1)
    # The boundary spy deliberately fails if any ZipInfo allocation can occur.
    monkeypatch.setattr(zipfile, 'ZipFile', lambda *a, **k: pytest.fail('eager ZIP allocation reached'))
    with pytest.raises(ValueError, match='limit'):
        archival.verify(path) if operation == 'verify' else archival.archive_inventory(path, 'zip')


@pytest.mark.parametrize('mutation', ['understated-count', 'bad-offset', 'multidisk', 'zip64-sentinel', 'zip64-locator'])
def test_zip_inconsistent_directory_rejected_before_allocation(tmp_path, monkeypatch, mutation):
    data = bytearray(zip_bytes([('one', b'1'), ('two', b'2')]))
    end = len(data) - 22
    if mutation == 'understated-count':
        struct.pack_into('<HH', data, end + 8, 1, 1)
    elif mutation == 'bad-offset':
        struct.pack_into('<I', data, end + 16, 0)
    elif mutation == 'multidisk':
        struct.pack_into('<H', data, end + 4, 1)
    elif mutation == 'zip64-sentinel':
        struct.pack_into('<HH', data, end + 8, 65535, 65535)
    else:
        data[end:end] = struct.pack('<4sIQI', b'PK\x06\x07', 0, 0, 1)
    path = tmp_path / 'bad.zip'
    path.write_bytes(data)
    monkeypatch.setattr(zipfile, 'ZipFile', lambda *a, **k: pytest.fail('eager ZIP allocation reached'))
    with pytest.raises(ValueError, match='ZIP|directory'):
        archival.archive_inventory(path, 'zip')


@pytest.mark.parametrize('change', ['wrong-format', 'missing-notice', 'redirected-notice'])
def test_build_and_verify_enforce_roles_and_notice_mapping(inputs, tmp_path, change):
    pins, cache = inputs
    good, bad = tmp_path / 'good.zip', tmp_path / 'bad.zip'
    archival.build(pins, cache, good)
    def mutate(lock):
        if change == 'wrong-format':
            lock['sources'][0]['format'] = 'raw'
        elif change == 'missing-notice':
            lock['retain'].pop()
        else:
            lock['retain'][0]['member'] = 'index.html'
    rewrite_bundle(good, bad, change_pins=mutate)
    lock = json.loads(pins.read_bytes())
    mutate(lock)
    pins.write_bytes(archival.canonical(lock))
    with pytest.raises(ValueError, match='required'):
        archival.build(pins, cache, tmp_path / 'new.zip')
    with pytest.raises(ValueError, match='required'):
        archival.verify(bad)


@pytest.mark.parametrize('operation', ['inspect', 'verify'])
@pytest.mark.parametrize('limit', ['MAX_MEMBER', 'MAX_EXPANDED'])
def test_zip_expanded_bounds_precede_allocation(tmp_path, monkeypatch, operation, limit):
    path = tmp_path / 'small.zip'
    path.write_bytes(zip_bytes([('one', b'12'), ('two', b'34')]))
    monkeypatch.setattr(archival, limit, 1)
    monkeypatch.setattr(zipfile, 'ZipFile', lambda *a, **k: pytest.fail('eager ZIP allocation reached'))
    with pytest.raises(ValueError, match='limit'):
        archival.verify(path) if operation == 'verify' else archival.archive_inventory(path, 'zip')


@pytest.mark.parametrize('kind', ['central-sentinel', 'central-extra', 'bad-extra', 'overstated-count'])
def test_zip_central_consistency_precedes_allocation(tmp_path, monkeypatch, kind):
    data = bytearray(zip_bytes([('one', b'1')]))
    central = data.index(b'PK\x01\x02')
    end = len(data) - 22
    if kind == 'central-sentinel':
        struct.pack_into('<I', data, central + 24, 0xffffffff)
    elif kind == 'overstated-count':
        struct.pack_into('<HH', data, end + 8, 2, 2)
    else:
        extra = struct.pack('<HH', 1 if kind == 'central-extra' else 2, 8)
        struct.pack_into('<H', data, central + 30, len(extra))
        struct.pack_into('<I', data, end + 12, end - central + len(extra))
        data[end:end] = extra
    path = tmp_path / 'bad.zip'
    path.write_bytes(data)
    monkeypatch.setattr(zipfile, 'ZipFile', lambda *a, **k: pytest.fail('eager ZIP allocation reached'))
    with pytest.raises(ValueError, match='ZIP|directory'):
        archival.archive_inventory(path, 'zip')


def test_interrupted_output_copy_removes_partial_staging(inputs, tmp_path, monkeypatch):
    pins, cache = inputs
    output = tmp_path / 'published' / 'bundle.zip'
    def interrupted(source, target, *args):
        target.write(source.read(3))
        raise OSError('injected disk failure after partial copy')
    monkeypatch.setattr(archival.shutil, 'copyfileobj', interrupted)
    with pytest.raises(OSError, match='injected disk failure'):
        archival.build(pins, cache, output)
    assert list(output.parent.iterdir()) == []


def test_interrupted_download_removes_partial_cache(inputs, tmp_path, monkeypatch):
    pins, cache = inputs
    source = json.loads(pins.read_bytes())['sources'][-1]
    blob = cache / source['sha256']
    data = blob.read_bytes()
    blob.unlink()
    before = set(cache.iterdir())
    class Response(io.BytesIO):
        url = source['url']
        def read(self, size=-1):
            if self.tell():
                raise ConnectionResetError('injected connection reset')
            return super().read(3)
    class Opener:
        def open(self, *args, **kwargs):
            return Response(data)
    monkeypatch.setattr(archival, 'build_opener', lambda *a: Opener())
    with pytest.raises(ConnectionResetError, match='injected connection reset'):
        archival.build(pins, cache, tmp_path / 'output.zip', fetch=True)
    assert set(cache.iterdir()) == before
    assert not (tmp_path / 'output.zip').exists()


def test_publication_race_preserves_competing_output(inputs, tmp_path, monkeypatch):
    pins, cache = inputs
    output = tmp_path / 'published' / 'bundle.zip'
    link = archival.os.link
    def race(source, destination):
        if destination == output:
            output.write_bytes(b'competing publisher')
        return link(source, destination)
    monkeypatch.setattr(archival.os, 'link', race)
    with pytest.raises(FileExistsError):
        archival.build(pins, cache, output)
    assert output.read_bytes() == b'competing publisher'
    assert list(output.parent.iterdir()) == [output]


@pytest.mark.parametrize('name', ['LICENSE', 'README.md', 'scripts/build_archival_bundle.py', 'docs/reference/archival-bundle.md'])
def test_verify_rejects_empty_mandatory_support(inputs, tmp_path, name):
    pins, cache = inputs
    good, bad = tmp_path / 'good.zip', tmp_path / 'bad.zip'
    archival.build(pins, cache, good)
    rewrite_bundle(good, bad, replacements={name: b''})
    with pytest.raises(ValueError, match='empty'):
        archival.verify(bad)


def test_verify_rejects_missing_blob_even_with_consistent_manifest(inputs, tmp_path):
    pins, cache = inputs
    good, bad = tmp_path / 'good.zip', tmp_path / 'bad.zip'
    archival.build(pins, cache, good)
    source = json.loads(pins.read_bytes())['sources'][0]
    rewrite_bundle(good, bad, omit=['sources/' + source['sha256']])
    with pytest.raises(ValueError, match='structure'):
        archival.verify(bad)


def test_verify_accepts_legacy_v1_without_project_license(inputs, tmp_path):
    pins, cache = inputs
    current, legacy = tmp_path / 'current.zip', tmp_path / 'legacy.zip'
    archival.build(pins, cache, current)
    # Original version-1 bundles predate the added project-license file.
    rewrite_bundle(current, legacy, omit=['LICENSE'])
    archival.verify(legacy)
