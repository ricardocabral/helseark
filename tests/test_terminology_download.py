"""Explicit account acquisition contracts, using only synthetic HTTP responses."""
import base64
from email.message import Message
import hashlib
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.request
import urllib.response
import warnings
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / 'skills/helseark/scripts/loinc_download.py'
BASE = 'https://loinc.regenstrief.org/api/v1/Loinc'
VERSION = '2.83'
DOWNLOAD_URL = BASE + '/Download?version=2.83'
USERNAME = 'synthetic-user'
PASSWORD = 'synthetic-password'
REAL_BUILD_OPENER = urllib.request.build_opener
AUTHORIZATION = 'Basic ' + base64.b64encode(b'synthetic-user:synthetic-password').decode('ascii')


def zip_bytes():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('LoincTable/Loinc.csv', 'LOINC_NUM,COMPONENT\n1234-5,Invented\n')
    return stream.getvalue()


class BrokenBody(io.BytesIO):
    def read(self, size=-1):
        raise http.client.IncompleteRead(b'synthetic-password')


class InterruptBody(io.BytesIO):
    def read(self, size=-1):
        raise KeyboardInterrupt


class SyntheticHTTPS(urllib.request.BaseHandler):
    """Replace socket I/O while retaining real urllib redirect/error processing."""
    handler_order = 100

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.on_request = None

    def https_open(self, request):
        self.requests.append(request)
        if self.on_request:
            self.on_request(request)
        if not self.responses:
            raise AssertionError('unexpected network request')
        body, code, supplied_headers = self.responses.pop(0)
        headers = Message()
        for key, value in supplied_headers.items():
            headers[key] = str(value)
        response = urllib.response.addinfourl(
            body if hasattr(body, 'read') else io.BytesIO(body), headers, request.full_url, code)
        response.msg = 'Synthetic response'
        return response


class TerminologyDownloadTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.exists(), 'explicit acquisition script is not implemented')
        spec = importlib.util.spec_from_file_location('loinc_download', SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.destination = self.root / 'acquired'
        self.archive = zip_bytes()
        self.metadata = {
            'version': VERSION, 'releaseDate': '2026-08-18T00:00:00',
            'relmaVersion': 'synthetic', 'numberOfLoincs': 1, 'maxLoinc': '1234-5',
            'downloadUrl': DOWNLOAD_URL,
            'downloadMD5Hash': hashlib.md5(self.archive).hexdigest(),
        }

    def transport(self, metadata=None, archive=None, responses=None):
        if responses is None:
            responses = [(json.dumps(self.metadata if metadata is None else metadata).encode(), 200, {}),
                         (self.archive if archive is None else archive, 200, {})]
        transport = SyntheticHTTPS(responses)
        binding = patch.object(self.module.urllib.request, 'build_opener',
                               side_effect=lambda *handlers: REAL_BUILD_OPENER(transport, *handlers))
        binding.start()
        self.addCleanup(binding.stop)
        return transport

    def download(self):
        return self.module.download(VERSION, self.destination, USERNAME, PASSWORD)

    def assert_no_output(self):
        self.assertEqual(list(self.root.iterdir()), [])

    def test_download_verifies_documented_metadata_and_retains_private_original_bytes(self):
        transport = self.transport()
        transport.on_request = lambda _: self.assertFalse(self.destination.exists())
        receipt = self.download()
        self.assertEqual([request.full_url for request in transport.requests],
                         [BASE + '?version=2.83', DOWNLOAD_URL])
        self.assertTrue(all(request.get_header('Authorization') == AUTHORIZATION
                            for request in transport.requests))
        self.assertEqual((self.destination / 'loinc.zip').read_bytes(), self.archive)
        self.assertEqual(receipt, json.loads((self.destination / 'receipt.json').read_bytes()))
        self.assertEqual(receipt['loinc_version'], VERSION)
        self.assertEqual(receipt['md5'], hashlib.md5(self.archive).hexdigest())
        self.assertEqual(receipt['sha256'], hashlib.sha256(self.archive).hexdigest())
        self.assertEqual(receipt['bytes'], len(self.archive))
        self.assertEqual(receipt['source'], BASE + '?version=2.83')
        self.assertEqual(set(self.destination.iterdir()),
                         {self.destination / 'loinc.zip', self.destination / 'receipt.json'})
        self.assertEqual(stat.S_IMODE(self.destination.stat().st_mode), 0o700)
        for path in self.destination.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        for secret in (USERNAME, PASSWORD, AUTHORIZATION):
            self.assertNotIn(secret, json.dumps(receipt))

    def test_refuses_existing_directory_file_and_symlink_without_network(self):
        transport = self.transport()
        for kind in ('directory', 'file', 'symlink'):
            with self.subTest(kind=kind):
                if kind == 'directory':
                    self.destination.mkdir()
                elif kind == 'file':
                    self.destination.write_text('keep')
                else:
                    self.destination.symlink_to(self.root / 'absent')
                before = self.destination.lstat()
                with self.assertRaises(self.module.DownloadError):
                    self.download()
                self.assertEqual(self.destination.lstat(), before)
                if kind == 'directory':
                    self.destination.rmdir()
                else:
                    self.destination.unlink()
        self.assertEqual(transport.requests, [])

    def test_refuses_symlink_parent_without_network(self):
        transport = self.transport()
        (self.root / 'link').symlink_to(self.root, target_is_directory=True)
        self.destination = self.root / 'link' / 'acquired'
        with self.assertRaises(self.module.DownloadError):
            self.download()
        self.assertEqual(transport.requests, [])

    def test_wrong_release_missing_or_invalid_digest_and_bad_json_never_publish(self):
        for changes in ({'version': '2.82'}, {'version': 2.83},
                        {'downloadMD5Hash': ''}, {'downloadMD5Hash': 'z' * 32},
                        {'downloadMD5Hash': None}, {'downloadUrl': None}):
            with self.subTest(changes=changes):
                metadata = dict(self.metadata, **changes)
                self.transport(metadata=metadata)
                with self.assertRaises(self.module.DownloadError):
                    self.download()
                self.assert_no_output()
        for malformed in (b'not JSON', b'[]', b'null', b'\xff', b'[' * 10000 + b']' * 10000):
            with self.subTest(malformed=malformed):
                self.transport(responses=[(malformed, 200, {})])
                with self.assertRaises(self.module.DownloadError):
                    self.download()
                self.assert_no_output()

    def test_foreign_insecure_userinfo_and_invalid_download_urls_never_receive_auth(self):
        for url in ('https://attacker.invalid/file', 'http://loinc.regenstrief.org/file',
                    'https://loinc.regenstrief.org:444/file',
                    'https://user:password@loinc.regenstrief.org/file',
                    '//loinc.regenstrief.org/file', '/file',
                    'https://loinc.regenstrief.org/file#fragment',
                    'https://loinc.regenstrief.org/\nfile',
                    'https://loinc.regenstrief.org:bad/file'):
            with self.subTest(url=url):
                transport = self.transport(metadata=dict(self.metadata, downloadUrl=url))
                with self.assertRaises(self.module.DownloadError):
                    self.download()
                self.assertEqual(len(transport.requests), 1)
                self.assert_no_output()

    def test_redirects_at_either_request_are_not_followed_even_to_same_origin(self):
        for stage in ('metadata', 'archive'):
            for status in (301, 302, 303, 307, 308):
                with self.subTest(stage=stage, status=status):
                    responses = [(b'', status, {'Location': BASE + '/other'})]
                    if stage == 'archive':
                        responses.insert(0, (json.dumps(self.metadata).encode(), 200, {}))
                    transport = self.transport(responses=responses)
                    with self.assertRaises(self.module.DownloadError):
                        self.download()
                    self.assertEqual(len(transport.requests), 1 if stage == 'metadata' else 2)
                    self.assert_no_output()

    def test_auth_http_and_interrupted_download_errors_are_sanitized_and_cleanup(self):
        for stage in ('metadata', 'archive'):
            for body, status in ((b'synthetic-user:synthetic-password', 401),
                                 (b'synthetic-password', 500),
                                 (BrokenBody(), 200), (InterruptBody(), 200)):
                with self.subTest(stage=stage, status=status, body=type(body)):
                    responses = [(body, status, {})]
                    if stage == 'archive':
                        responses.insert(0, (json.dumps(self.metadata).encode(), 200, {}))
                    self.transport(responses=responses)
                    with self.assertRaises((self.module.DownloadError, KeyboardInterrupt)) as caught:
                        self.download()
                    self.assertNotIn(PASSWORD, str(caught.exception))
                    self.assertNotIn(USERNAME, str(caught.exception))
                    self.assert_no_output()

    def test_digest_mismatch_and_empty_download_never_publish(self):
        for archive in (b'damaged', b''):
            with self.subTest(archive=archive):
                self.transport(archive=archive)
                with self.assertRaises(self.module.DownloadError):
                    self.download()
                self.assert_no_output()

    def test_response_bounds_apply_without_content_length_and_before_large_announced_body(self):
        for stage in ('metadata', 'archive'):
            for announced in (False, True):
                with self.subTest(stage=stage, announced=announced):
                    body = b'x' * 65
                    responses = [(body, 200, {'Content-Length': '65'} if announced else {})]
                    if stage == 'archive':
                        responses.insert(0, (json.dumps(self.metadata).encode(), 200, {}))
                    self.transport(responses=responses)
                    limit = 'MAX_METADATA_BYTES' if stage == 'metadata' else 'MAX_ARCHIVE_BYTES'
                    with patch.object(self.module, limit, 64):
                        with self.assertRaises(self.module.DownloadError):
                            self.download()
                    self.assert_no_output()

    def test_truncated_declared_length_and_invalid_lengths_fail_without_publication(self):
        for length in ('-1', 'invalid', str(len(self.archive) + 1)):
            with self.subTest(length=length):
                self.transport(responses=[(json.dumps(self.metadata).encode(), 200, {}),
                                          (self.archive, 200, {'Content-Length': length})])
                with self.assertRaises(self.module.DownloadError):
                    self.download()
                self.assert_no_output()

    def test_raced_destination_is_preserved_without_receipt_or_cleanup_of_others(self):
        transport = self.transport()
        def race(request):
            if request.full_url == DOWNLOAD_URL:
                self.destination.mkdir()
                (self.destination / 'other-session').write_text('keep')
        transport.on_request = race
        with self.assertRaises(self.module.DownloadError):
            self.download()
        self.assertEqual((self.destination / 'other-session').read_text(), 'keep')
        self.assertEqual(list(self.root.iterdir()), [self.destination])
        self.assertFalse((self.destination / 'receipt.json').exists())

    def test_symlink_parent_created_during_download_is_rejected(self):
        transport = self.transport()
        (self.root / 'cache').mkdir()
        self.destination = self.root / 'cache' / 'acquired'
        def race(request):
            if request.full_url == DOWNLOAD_URL:
                (self.root / 'cache').rename(self.root / 'original-cache')
                (self.root / 'cache').symlink_to(self.root / 'original-cache', target_is_directory=True)
        transport.on_request = race
        with self.assertRaises(self.module.DownloadError):
            self.download()
        self.assertFalse((self.root / 'original-cache' / 'acquired').exists())

    def test_publication_failure_preserves_another_sessions_file(self):
        self.transport()
        real_link = self.module.os.link
        def race(source, target):
            if target.name == 'receipt.json':
                target.write_text('other session')
            real_link(source, target)
        with patch.object(self.module.os, 'link', side_effect=race):
            with self.assertRaises(self.module.DownloadError):
                self.download()
        self.assertEqual((self.destination / 'receipt.json').read_text(), 'other session')
        self.assertFalse((self.destination / 'loinc.zip').exists())
        self.assertEqual(list(self.root.iterdir()), [self.destination])

    def test_interrupted_publication_removes_only_our_unfinished_files(self):
        self.transport()
        real_link = self.module.os.link
        def interrupt(source, target):
            if target.name == 'receipt.json':
                raise KeyboardInterrupt
            real_link(source, target)
        with patch.object(self.module.os, 'link', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.download()
        self.assert_no_output()

    def test_interruption_immediately_after_receipt_link_does_not_leave_false_completion(self):
        self.transport()
        real_link = self.module.os.link
        def interrupt(source, target):
            real_link(source, target)
            if target.name == 'receipt.json':
                raise KeyboardInterrupt
        with patch.object(self.module.os, 'link', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.download()
        self.assert_no_output()

    def test_cli_success_uses_two_hidden_prompts_and_real_download(self):
        transport = self.transport()
        args = ['--version', VERSION, '--destination', str(self.destination)]
        stderr, stdout = io.StringIO(), io.StringIO()
        with patch.object(self.module.sys.stdin, 'isatty', return_value=True), \
             patch.object(stderr, 'isatty', return_value=True), \
             patch.object(self.module.sys, 'stderr', stderr), \
             patch.object(self.module.sys, 'stdout', stdout), \
             patch.object(self.module.getpass, 'getpass', side_effect=[USERNAME, PASSWORD]) as prompt:
            self.assertEqual(self.module.main(args), 0)
        self.assertEqual(prompt.call_count, 2)
        self.assertTrue(all(request.get_header('Authorization') == AUTHORIZATION
                            for request in transport.requests))
        self.assertEqual(json.loads(stdout.getvalue())['loinc_version'], VERSION)
        self.assertNotIn(PASSWORD, stdout.getvalue() + stderr.getvalue())
        self.assertNotIn(USERNAME, stdout.getvalue() + stderr.getvalue())

    @unittest.skipUnless(os.name == 'posix', 'native POSIX terminal check')
    def test_native_terminal_hides_both_fields_and_restores_echo(self):
        import fcntl
        import pty
        import select
        import termios
        master, terminal = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, terminal)
        def own_terminal():
            os.setsid()
            fcntl.ioctl(terminal, termios.TIOCSCTTY, 0)
        launcher = (
            'import importlib.util,sys,termios; '
            'spec=importlib.util.spec_from_file_location("acquisition",sys.argv.pop(1)); '
            'module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); '
            'module.download=lambda version,destination,username,password: '
            '{"entered_both": bool(username and password), '
            '"echo_restored": bool(termios.tcgetattr(sys.stdin)[3] & termios.ECHO)}; '
            'raise SystemExit(module.main())'
        )
        process = subprocess.Popen(
            [sys.executable, '-c', launcher, str(SCRIPT), '--version', VERSION,
             '--destination', str(self.destination)],
            stdin=terminal, stdout=terminal, stderr=terminal, preexec_fn=own_terminal)
        def cleanup_process():
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        self.addCleanup(cleanup_process)
        output = bytearray()
        def until(marker):
            deadline = time.monotonic() + 5
            while marker not in output:
                remaining = deadline - time.monotonic()
                self.assertGreater(remaining, 0, 'terminal prompt timed out')
                ready, _, _ = select.select([master], [], [], remaining)
                self.assertTrue(ready, 'terminal prompt timed out')
                output.extend(os.read(master, 4096))
        until(b'username (hidden): ')
        self.assertFalse(termios.tcgetattr(terminal)[3] & termios.ECHO)
        os.write(master, (USERNAME + '\n').encode())
        until(b'password (hidden): ')
        self.assertFalse(termios.tcgetattr(terminal)[3] & termios.ECHO)
        os.write(master, (PASSWORD + '\n').encode())
        until(b'"echo_restored": true')
        self.assertIn(b'"entered_both": true', output)
        self.assertEqual(process.wait(timeout=5), 0)
        self.assertNotIn(USERNAME.encode(), output)
        self.assertNotIn(PASSWORD.encode(), output)
        self.assert_no_output()

    def test_cli_requires_terminal_and_rejects_credential_arguments(self):
        result = subprocess.run([sys.executable, str(SCRIPT), '--version', VERSION,
                                 '--destination', str(self.destination)],
                                input=PASSWORD, text=True, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(PASSWORD, result.stderr + result.stdout)
        self.assertNotIn('Traceback', result.stderr)
        self.assert_no_output()
        result = subprocess.run([sys.executable, str(SCRIPT), '--version', VERSION,
                                 '--destination', str(self.destination), '--password', PASSWORD],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(PASSWORD, result.stderr + result.stdout)

    def test_cli_hidden_prompts_refuse_getpass_echo_fallback_and_sanitize_errors(self):
        args = ['--version', VERSION, '--destination', str(self.destination)]
        for failure in ('echo', 'network', 'interrupt'):
            with self.subTest(failure=failure):
                stderr, stdout = io.StringIO(), io.StringIO()
                def prompt(*_args, **_kwargs):
                    if failure == 'echo':
                        warnings.warn('synthetic-password', self.module.getpass.GetPassWarning)
                    return PASSWORD
                with patch.object(self.module.sys.stdin, 'isatty', return_value=True), \
                     patch.object(stderr, 'isatty', return_value=True), \
                     patch.object(self.module.sys, 'stderr', stderr), \
                     patch.object(self.module.sys, 'stdout', stdout), \
                     patch.object(self.module.getpass, 'getpass', side_effect=prompt), \
                     patch.object(self.module, 'download', side_effect=(
                         KeyboardInterrupt() if failure == 'interrupt' else
                         self.module.DownloadError('safe download error'))):
                    self.assertIn(self.module.main(args), (2, 130))
                self.assertNotIn(PASSWORD, stderr.getvalue() + stdout.getvalue())
                self.assertNotIn('Traceback', stderr.getvalue())
                self.assert_no_output()


if __name__ == '__main__':
    unittest.main()
