"""Offline maintainer regressions; synthetic archives, plus real installed pins."""
import copy
from email.message import Message
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import BaseHandler, build_opener
from urllib.response import addinfourl
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('vendor', ROOT / 'scripts/vendor_definitions.py')
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)
NETWORK_BLOCKED = False


def deny_network(event, args):
    if NETWORK_BLOCKED and event.startswith('socket.'):
        raise AssertionError('unexpected network: ' + event)


sys.addaudithook(deny_network)


def pin(data):
    return {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def encoded(value):
    return json.dumps(value).encode()


class Transport(BaseHandler):
    """Deterministic transport; urllib's real error/redirect processors remain."""
    handler_order = 100

    def __init__(self, routes):
        self.routes = routes
        self.visited = []

    def https_open(self, request):
        self.visited.append(request.full_url)
        status, location, data = self.routes[request.full_url]
        headers = Message()
        if location:
            headers['Location'] = location
        response = addinfourl(io.BytesIO(data), headers, request.full_url, status)
        response.msg = 'synthetic response'
        return response

    http_open = https_open


class VendorTests(unittest.TestCase):
    def setUp(self):
        global NETWORK_BLOCKED
        NETWORK_BLOCKED = True
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'checkout'
        self.root.mkdir()
        self.cache = Path(self.temp.name) / 'cache'
        self.cache.mkdir()
        self.files = {
            v.CORE + 'package.json': encoded({
                'name': 'hl7.fhir.r4.core', 'version': '4.0.1', 'license': 'CC0-1.0'}),
            v.CORE + 'StructureDefinition-Patient.json': encoded({
                'resourceType': 'StructureDefinition', 'fhirVersion': '4.0.1',
                'url': v.CANONICAL + 'Patient'}),
            v.SCHEMA: encoded({'$schema': 'http://json-schema.org/draft-06/schema#',
                              'definitions': {'Patient': {'$ref': '#/definitions/leaf'},
                                              'leaf': {}}}),
            v.PREFIXES[2] + 'license.html': b'synthetic license\r\n',
        }
        self.inv = {'inventoryVersion': 1, 'fhirVersion': '4.0.1',
                    'selection': {'resources': ['Patient']}, 'sources': [], 'files': []}
        self.rebuild()

    def tearDown(self):
        global NETWORK_BLOCKED
        NETWORK_BLOCKED = False

    def rebuild(self, tar_kind=None, zip_link=False):
        """Re-pin synthetic inputs so semantic/archive tests pass the hash gate."""
        self.inv['sources'] = []
        self.inv['files'] = []
        for source_id, fmt in [('core', 'tar.gz'), ('schema', 'zip'), ('license', 'raw')]:
            selected = {p: b for p, b in self.files.items() if (
                p.startswith(v.CORE) if source_id == 'core' else
                p == v.SCHEMA if source_id == 'schema' else p.startswith(v.PREFIXES[2]))}
            output = io.BytesIO()
            if fmt == 'tar.gz':
                with tarfile.open(fileobj=output, mode='w:gz') as archive:
                    for path, data in selected.items():
                        member = tarfile.TarInfo('package/' + Path(path).name)
                        member.size = len(data)
                        if tar_kind in ('symlink', 'hardlink') and 'Patient' in path:
                            member.type = (tarfile.SYMTYPE if tar_kind == 'symlink'
                                           else tarfile.LNKTYPE)
                            member.linkname = '../../escape'
                        archive.addfile(member, io.BytesIO(data) if member.isfile() else None)
                    if tar_kind == 'hostile':
                        for name in ('../../escape', '/absolute', 'unused/../escape'):
                            member = tarfile.TarInfo(name)
                            member.size = 1
                            archive.addfile(member, io.BytesIO(b'x'))
                        member = tarfile.TarInfo('unselected-link')
                        member.type = tarfile.SYMTYPE
                        member.linkname = '../../escape'
                        archive.addfile(member)
                blob = output.getvalue()
            elif fmt == 'zip':
                with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
                    for path, data in selected.items():
                        member = zipfile.ZipInfo(Path(path).name)
                        if zip_link:
                            member.create_system = 3
                            member.external_attr = 0o120777 << 16
                        archive.writestr(member, data)
                    archive.writestr('../../escape', b'x')
                blob = output.getvalue()
            else:
                blob = next(iter(selected.values()))
            source = {'id': source_id, 'format': fmt,
                      'url': 'https://hl7.org/fhir/R4/' + source_id, **pin(blob)}
            self.inv['sources'].append(source)
            (self.cache / source['sha256']).write_bytes(blob)
            for path, data in selected.items():
                self.inv['files'].append({'path': path, 'source': source_id, **pin(data),
                                          'member': ('package/' if fmt == 'tar.gz' else '')
                                          + Path(path).name})
        inventory = self.root / v.INVENTORY
        inventory.parent.mkdir(exist_ok=True)
        inventory.write_bytes(encoded(self.inv))

    def fetch(self):
        v.fetch(self.root, v.load_inventory(self.root), self.cache)

    def assert_files(self):
        actual = {p.relative_to(self.root).as_posix(): p.read_bytes()
                  for p in self.root.rglob('*') if p.is_file() and p != self.root / v.INVENTORY}
        self.assertEqual(actual, self.files)

    def cli(self, root, *args, success=True):
        wrapper = """import runpy, sys
sys.addaudithook(lambda event, args: (_ for _ in ()).throw(AssertionError('NETWORK ATTEMPT')) if event.startswith('socket.') else None)
script = sys.argv.pop(1)
runpy.run_path(script, run_name='__main__')
"""
        result = subprocess.run([sys.executable, '-B', '-c', wrapper,
                                 str(ROOT / 'scripts/vendor_definitions.py'),
                                 '--root', str(root), *args], capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        self.assertNotIn('NETWORK ATTEMPT', result.stderr)
        return result

    def test_real_installed_inventory_offline(self):
        for entry in v.load_inventory(ROOT)['files']:
            self.assertEqual(pin((ROOT / entry['path']).read_bytes()),
                             {'size': entry['size'], 'sha256': entry['sha256']})
        self.cli(ROOT)
        self.cli(ROOT, '--verify')

    def test_reproduction_idempotence_and_missing_repair_offline(self):
        self.cli(self.root, success=False)
        for _ in range(2):
            self.cli(self.root, '--fetch', '--cache-dir', str(self.cache))
            self.assert_files()
        (self.root / v.SCHEMA).unlink()
        self.fetch()
        self.assert_files()
        self.cli(self.root)

    def test_installed_and_cache_tampering_refused(self):
        self.fetch()
        path = self.root / v.SCHEMA
        original = path.read_bytes()
        path.write_bytes(b'X' + original[1:])
        self.cli(self.root, success=False)
        with self.assertRaisesRegex(ValueError, 'byte/hash mismatch'):
            self.fetch()
        self.assertEqual(path.read_bytes(), b'X' + original[1:])
        path.unlink()
        source = self.inv['sources'][0]
        cached = self.cache / source['sha256']
        cached.write_bytes(b'X' + cached.read_bytes()[1:])
        with self.assertRaisesRegex(ValueError, 'byte/hash mismatch'):
            self.fetch()
        self.assertFalse(path.exists())

    def test_corrupt_cache_publishes_no_artifacts_in_fresh_tree(self):
        source = self.inv['sources'][0]
        cached = self.cache / source['sha256']
        cached.write_bytes(b'X' + cached.read_bytes()[1:])
        with self.assertRaisesRegex(ValueError, 'byte/hash mismatch'):
            self.fetch()
        self.assertEqual([p for p in self.root.rglob('*') if p.is_file()],
                         [self.root / v.INVENTORY])

    def test_unsafe_inventory_paths(self):
        for name in ('../escape', '/absolute', 'definitions/docs/r4/../escape',
                     'definitions//docs/r4/a', 'definitions/docs/r4/./a',
                     'definitions/docs/r4/back\\slash'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                v.confined(self.root, name)

    def test_symlinks_and_unlisted_files(self):
        self.fetch()
        for name in (v.SCHEMA, v.PREFIXES[2].rstrip('/'), v.INVENTORY):
            path = self.root / name
            saved = path.with_name(path.name + '.saved')
            path.rename(saved)
            path.symlink_to(saved)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'symlink'):
                v.verify(self.root, v.load_inventory(self.root))
            path.unlink()
            saved.rename(path)
        extra = self.root / v.PREFIXES[2] / 'extra'
        extra.symlink_to(self.root / 'absent')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            v.verify(self.root, self.inv)
        extra.unlink()
        extra.write_bytes(b'extra')
        with self.assertRaisesRegex(ValueError, 'uninventoried'):
            v.verify(self.root, self.inv)

    def test_hostile_unselected_archive_names_never_become_paths(self):
        self.rebuild(tar_kind='hostile', zip_link=True)
        self.fetch()
        self.assert_files()
        self.assertFalse((self.root / v.SCHEMA).is_symlink())

    def test_selected_tar_links_refused_before_publication(self):
        for kind in ('symlink', 'hardlink'):
            self.rebuild(tar_kind=kind)
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'invalid tar member'):
                self.fetch()
            self.assertEqual(list(self.root.rglob('*.*')), [self.root / v.INVENTORY])

    def test_semantic_errors_after_repin(self):
        original = copy.deepcopy(self.files)
        for kind in ('external', 'missing-target', 'dialect', 'version', 'missing-core'):
            self.files = copy.deepcopy(original)
            schema = json.loads(self.files[v.SCHEMA])
            patient = v.CORE + 'StructureDefinition-Patient.json'
            if kind == 'external':
                schema['definitions']['Patient']['$ref'] = 'https://unapproved.invalid/schema'
            elif kind == 'missing-target':
                schema['definitions']['Patient']['$ref'] = '#/definitions/absent'
            elif kind == 'dialect':
                schema['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
            elif kind == 'version':
                definition = json.loads(self.files[patient])
                definition['fhirVersion'] = '5.0.0'
                self.files[patient] = encoded(definition)
            else:
                del self.files[patient]
            self.files[v.SCHEMA] = encoded(schema)
            self.rebuild()
            with self.subTest(kind=kind), self.assertRaises((ValueError, KeyError)):
                self.fetch()
            self.assertFalse((self.root / v.SCHEMA).exists())

    def redirect_acquire(self, target, allowed):
        start = 'https://hl7.org/fhir/R4/license.html'
        payload = b'synthetic exact bytes'
        transport = Transport({start: (302, target, b''),
                               target: (200, None, payload)})
        real_builder = build_opener
        def opener(*handlers):
            return real_builder(transport, *handlers)
        with patch.object(v, 'build_opener', side_effect=opener):
            source = {'url': start, **pin(payload)}
            if allowed:
                self.assertEqual(v.acquire(source, None), payload)
                self.assertEqual(transport.visited, [start, target])
            else:
                with self.assertRaises(ValueError):
                    v.acquire(source, self.cache)
                self.assertEqual(transport.visited, [start])
                self.assertFalse((self.cache / source['sha256']).exists())

    def test_legitimate_absolute_redirects(self):
        for target in ('https://hl7.org/fhir/R4/moved',
                       'https://creativecommons.org/publicdomain/zero/1.0/legalcode.en'):
            with self.subTest(target=target):
                self.redirect_acquire(target, True)

    def test_relative_redirect(self):
        start = 'https://hl7.org/fhir/R4/license.html'
        end = 'https://hl7.org/fhir/R4/moved'
        transport = Transport({start: (302, 'moved', b''), end: (200, None, b'x')})
        with patch.object(v, 'build_opener', return_value=build_opener(
                transport, v.ApprovedRedirectHandler())):
            self.assertEqual(v.acquire({'url': start, **pin(b'x')}, None), b'x')
        self.assertEqual(transport.visited, [start, end])

    def test_redirect_downgrade_and_unapproved_authorities_never_dispatched(self):
        for target in ('http://hl7.org/fhir/R4/moved', 'http://unapproved.invalid/payload',
                       'https://unapproved.invalid/payload', 'https://hl7.org.evil.invalid/a',
                       'https://hl7.org:8443/a', 'https://user@hl7.org/a'):
            with self.subTest(target=target):
                self.redirect_acquire(target, False)

    def test_initial_transport_url_checked_before_dispatch(self):
        with patch.object(v, 'build_opener', side_effect=AssertionError('dispatched')):
            with self.assertRaises(ValueError):
                v.acquire({'url': 'http://hl7.org/fhir/R4/license.html', **pin(b'x')}, None)

    def test_every_redirect_in_chain_is_checked(self):
        start = 'https://hl7.org/fhir/R4/license.html'
        middle = 'https://hl7.org/fhir/R4/moved'
        end = 'http://unapproved.invalid/payload'
        transport = Transport({start: (301, middle, b''), middle: (307, end, b''),
                               end: (200, None, b'x')})
        with patch.object(v, 'build_opener', return_value=build_opener(
                transport, v.ApprovedRedirectHandler())):
            with self.assertRaises(ValueError):
                v.acquire({'url': start, **pin(b'x')}, None)
        self.assertEqual(transport.visited, [start, middle])

    def test_acquisition_checks_size_and_hash_before_cache_publication(self):
        url = 'https://hl7.org/fhir/R4/synthetic'
        for payload in (b'wrong', b'too long', b'x'):
            transport = Transport({url: (200, None, payload)})
            with patch.object(v, 'build_opener', return_value=build_opener(
                    transport, v.ApprovedRedirectHandler())):
                with self.subTest(payload=payload), self.assertRaisesRegex(
                        ValueError, 'byte/hash mismatch'):
                    v.acquire({'url': url, **pin(b'right')}, self.cache)
            self.assertFalse((self.cache / pin(b'right')['sha256']).exists())

    def test_write_failure_leaves_no_partial_cache_or_artifact(self):
        url = 'https://hl7.org/fhir/R4/synthetic'
        source = {'url': url, **pin(b'right')}
        transport = Transport({url: (200, None, b'right')})
        with patch.object(v, 'build_opener', return_value=build_opener(
                transport, v.ApprovedRedirectHandler())), patch.object(
                    v.os, 'fsync', side_effect=OSError('synthetic write failure')):
            with self.assertRaisesRegex(OSError, 'synthetic write failure'):
                v.acquire(source, self.cache)
            with self.assertRaisesRegex(OSError, 'synthetic write failure'):
                self.fetch()
        self.assertFalse((self.cache / source['sha256']).exists())
        self.assertFalse((self.root / v.CORE / 'package.json').exists())
        self.assertEqual(list(Path(self.temp.name).rglob('.vendor-*.tmp')), [])
        self.fetch()
        self.assert_files()

    def test_atomic_publication_preserves_existing_bytes(self):
        path = self.root / 'output'
        v.publish_missing(path, b'complete')
        v.publish_missing(path, b'complete')
        with self.assertRaisesRegex(ValueError, 'byte/hash mismatch'):
            v.publish_missing(path, b'changed')
        self.assertEqual(path.read_bytes(), b'complete')
        self.assertEqual(list(self.root.glob('.vendor-*.tmp')), [])

    def test_interrupted_publication_and_explicit_temp_recovery(self):
        # Real child process exit during write, before link, and after real link.
        for phase in ('write', 'before-link', 'after-link'):
            directory = Path(self.temp.name) / phase
            directory.mkdir()
            destination = directory / 'output'
            child = '''import importlib.util, os, pathlib, sys
spec = importlib.util.spec_from_file_location('vendor', sys.argv[1])
v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
phase = sys.argv[3]
if phase == 'write':
    original = v.tempfile.NamedTemporaryFile
    def temporary(*args, **kwargs):
        stream = original(*args, **kwargs)
        write = stream.write
        def partial(data):
            write(data[:3]); stream.flush(); os._exit(73)
        stream.write = partial
        return stream
    v.tempfile.NamedTemporaryFile = temporary
else:
    link = v.os.link
    def interrupted(*args):
        if phase == 'before-link': os._exit(73)
        link(*args); os._exit(73)
    v.os.link = interrupted
v.publish_missing(pathlib.Path(sys.argv[2]), b'complete')
'''
            result = subprocess.run([sys.executable, '-B', '-c', child,
                                     str(ROOT / 'scripts/vendor_definitions.py'),
                                     str(destination), phase], capture_output=True)
            self.assertEqual(result.returncode, 73, result.stderr)
            self.assertEqual(destination.exists(), phase == 'after-link')
            if destination.exists():
                self.assertEqual(destination.read_bytes(), b'complete')
            leftovers = list(directory.glob('.vendor-*.tmp'))
            self.assertEqual(len(leftovers), 1)
            v.publish_missing(destination, b'complete')
            self.assertEqual(destination.read_bytes(), b'complete')
            # Documented recovery removes only the identified task-owned temp.
            leftovers[0].unlink()
            self.assertEqual(list(directory.glob('.vendor-*.tmp')), [])


if __name__ == '__main__':
    unittest.main()
