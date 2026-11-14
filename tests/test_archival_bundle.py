"""Behavioral tests use synthetic archives; official large inputs stay in dist/."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import socket
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
        ('specification', 'zip', zip_bytes([('index.html', b'offline'), ('license.html', b'CC0; trademarks; third-party terms'), ('assets/style.css', b'body {}')])),
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
                retain=[dict(source='specification', member='license.html', path='licenses/hl7.html'),
                        dict(source='cc0', path='licenses/cc0.html')])
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
        assert {m['path'] for m in inventory} == {'index.html', 'license.html', 'assets/style.css'}
        assert bundle.read('licenses/hl7.html') == b'CC0; trademarks; third-party terms'
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
