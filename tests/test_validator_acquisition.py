"""Acquisition contracts use real local byte streams; no validator conformance claim."""
import hashlib
import glob
from http.client import HTTPResponse
import importlib.util
import io
import json
from pathlib import Path
import socket
from urllib.error import HTTPError, URLError

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('acquire_validator', ROOT/'scripts/acquire_validator.py')
acquisition = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acquisition)


def pin_for(source, expected=b'qualified'):
    return dict(filename='fixture.tgz', url=source.as_uri(), bytes=len(expected),
                sha256=hashlib.sha256(expected).hexdigest())


@pytest.mark.parametrize('body,reason', [
    (b'qualified', None), (b'qualifie', 'pin-mismatch'),
    (b'QUALIFIED', 'pin-mismatch'), (b'qualified' + b'x'*100000, 'pin-mismatch'),
], ids=['exact', 'short', 'wrong-digest', 'oversized'])
def test_exact_size_and_digest_with_bounded_failure_evidence(tmp_path, body, reason):
    source = tmp_path/'source'; source.write_bytes(body)
    target = tmp_path/'download.tgz'
    report = tmp_path/'acquisition.jsonl'
    pin = pin_for(source)
    if reason:
        with pytest.raises(SystemExit, match='fixture.tgz'):
            acquisition.acquire(pin, target, report)
        assert not target.exists()
    else:
        acquisition.acquire(pin, target, report)
        assert target.read_bytes() == body
    record = json.loads(report.read_text())
    observed = body[:pin['bytes']+1]
    assert record['artifact'] == pin['filename']
    assert record['url'] == source.as_uri()
    assert record['expectedBytes'] == pin['bytes']
    assert record['expectedSha256'] == pin['sha256']
    assert record['observedBytes'] == len(observed)
    assert record['observedSha256'] == hashlib.sha256(observed).hexdigest()
    assert record['readLimitBytes'] == pin['bytes']+1
    assert record['digestScope'] == ('bounded-prefix' if len(body)>pin['bytes'] else 'complete-body')
    assert record['result'] == (reason or 'verified')
    assert list(tmp_path.glob('*.part')) == []


def test_open_failure_preserves_identity_without_exception_secrets(tmp_path, monkeypatch):
    pin = pin_for(tmp_path/'missing')
    pin['url'] = 'https://user:secret@example.org/artifact?token=SENSITIVE_TOKEN#fragment'
    def denied(*args, **kwargs):
        raise OSError('SENSITIVE_TOKEN header and token')
    monkeypatch.setattr(acquisition, 'urlopen', denied)
    report = tmp_path/'acquisition.jsonl'
    with pytest.raises(SystemExit, match='fixture.tgz'):
        acquisition.acquire(pin, tmp_path/'download.tgz', report)
    record = json.loads(report.read_text())
    assert record['url'] == 'https://example.org/artifact'
    assert record['observedBytes'] == 0
    assert record['digestScope'] == 'partial-body'
    assert record['result'] == 'transfer-error'
    assert record['errorType'] == 'OSError'
    assert not any(x in report.read_text() for x in ('secret', 'SENSITIVE_TOKEN', 'fragment'))


def test_records_survive_later_artifact_failure_without_corpus(tmp_path):
    source = tmp_path/'source'; source.write_bytes(b'qualified')
    report = tmp_path/'validator'/'acquisition.jsonl'; report.parent.mkdir()
    acquisition.acquire(pin_for(source), report.parent/'good.tgz', report)
    source.write_bytes(b'changed')
    with pytest.raises(SystemExit):
        acquisition.acquire(pin_for(source), report.parent/'bad.tgz', report)
    records = [json.loads(line) for line in report.read_text().splitlines()]
    assert [r['result'] for r in records] == ['verified', 'pin-mismatch']
    assert (report.parent/'good.tgz').read_bytes() == b'qualified'
    assert not (tmp_path/'official-evidence').exists()

    # Exercise the workflow's upload selection with absent corpus output and
    # retained binaries, rather than asserting a particular config string.
    workflow = (ROOT/'.github/workflows/ci.yml').read_text()
    paths = workflow.split('name: official-validator-evidence\n', 1)[1].split('path: |\n', 1)[1].split('if-no-files-found:', 1)[0]
    selected = set()
    for pattern in paths.strip().splitlines():
        pattern = pattern.strip().replace('${{ runner.temp }}', str(tmp_path))
        selected.update(Path(p) for p in glob.glob(pattern))
    assert selected == {report}


def test_http_status_redirect_and_short_reads_are_recorded(tmp_path, monkeypatch):
    class Socket:
        def makefile(self, *args):
            return io.BytesIO(b'HTTP/1.1 200 OK\r\nContent-Length: 9\r\nSecret: SENSITIVE_TOKEN\r\n\r\nqualified')
    response = HTTPResponse(Socket())
    response.begin()
    response.geturl = lambda: 'https://cdn.example.org/asset?signature=SENSITIVE_TOKEN'
    sizes = []
    read = response.read
    def short_read(size):
        sizes.append(size)
        return read(min(size, 3))
    response.read = short_read
    monkeypatch.setattr(acquisition, 'urlopen', lambda *a, **kw: response)
    report = tmp_path/'acquisition.jsonl'
    acquisition.acquire(pin_for(tmp_path/'source'), tmp_path/'good.tgz', report)
    record = json.loads(report.read_text())
    assert record['status'] == 200
    assert record['contentLength'] == 9
    assert record['finalUrl'] == 'https://cdn.example.org/asset'
    assert sizes == [10, 7, 4, 1]
    assert 'SENSITIVE_TOKEN' not in report.read_text()


@pytest.mark.parametrize('failure', ['http', 'partial-timeout'])
def test_transfer_errors_fail_without_retry_or_secret_leak(tmp_path, monkeypatch, failure):
    class Transfer:
        status = 200
        headers = {'Content-Length': '9'}
        calls = 0
        def geturl(self):
            return 'https://cdn.example.org/asset?SENSITIVE_TOKEN=token'
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, size):
            self.calls += 1
            if self.calls == 1:
                assert size == 10
                return b'quali'
            assert size == 5
            raise TimeoutError('SENSITIVE_TOKEN token')
    response = Transfer()
    opens = []
    def open_transfer(*args, **kwargs):
        opens.append(args)
        if failure == 'http':
            raise HTTPError(response.geturl(), 503, 'SENSITIVE_TOKEN', {'Secret': 'SENSITIVE_TOKEN'}, io.BytesIO(b'SENSITIVE_TOKEN'))
        return response
    monkeypatch.setattr(acquisition, 'urlopen', open_transfer)
    report = tmp_path/'acquisition.jsonl'
    with pytest.raises(SystemExit, match='transfer-error'):
        acquisition.acquire(pin_for(tmp_path/'source'), tmp_path/'bad.tgz', report)
    record = json.loads(report.read_text())
    assert len(opens) == 1
    assert record['status'] == (503 if failure == 'http' else 200)
    observed = b'' if failure == 'http' else b'quali'
    assert record['observedBytes'] == len(observed)
    assert record['observedSha256'] == hashlib.sha256(observed).hexdigest()
    assert record['digestScope'] == 'partial-body'
    assert 'SENSITIVE_TOKEN' not in report.read_text()
    assert not (tmp_path/'bad.tgz').exists()
    assert not list(tmp_path.glob('*.part'))


@pytest.mark.parametrize('existing', ['good.tgz', 'good.tgz.part'])
def test_existing_files_are_preserved(tmp_path, existing):
    original = tmp_path/existing; original.write_bytes(b'preserve')
    report = tmp_path/'acquisition.jsonl'
    with pytest.raises(SystemExit):
        acquisition.acquire(pin_for(tmp_path/'source'), tmp_path/'good.tgz', report)
    assert original.read_bytes() == b'preserve'


def test_interrupted_chunked_http_includes_exception_partial_bytes(tmp_path, monkeypatch):
    class Socket:
        def makefile(self, *args):
            return io.BytesIO(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nquali\r\n')
    response = HTTPResponse(Socket()); response.begin()
    response.geturl = lambda: 'https://example.org/asset'
    monkeypatch.setattr(acquisition, 'urlopen', lambda *a, **kw: response)
    report = tmp_path/'acquisition.jsonl'
    with pytest.raises(SystemExit, match='transfer-error'):
        acquisition.acquire(pin_for(tmp_path/'source'), tmp_path/'bad.tgz', report)
    record = json.loads(report.read_text())
    assert record['observedBytes'] == 5
    assert record['observedSha256'] == hashlib.sha256(b'quali').hexdigest()
    assert record['errorType'] == 'IncompleteRead'
    assert record['digestScope'] == 'partial-body'


def test_dns_failure_retains_safe_cause(tmp_path, monkeypatch):
    def dns_error(*args, **kwargs):
        raise URLError(socket.gaierror(8, 'SENSITIVE_TOKEN'))
    monkeypatch.setattr(acquisition, 'urlopen', dns_error)
    report = tmp_path/'acquisition.jsonl'
    with pytest.raises(SystemExit):
        acquisition.acquire(pin_for(tmp_path/'source'), tmp_path/'bad.tgz', report)
    record = json.loads(report.read_text())
    assert record['errorType'] == 'URLError'
    assert record['causeType'] == 'gaierror'
    assert record['errno'] == 8
    assert 'SENSITIVE_TOKEN' not in report.read_text()


def test_streaming_reads_stop_at_expected_plus_one(tmp_path, monkeypatch):
    source = tmp_path/'source'; source.write_bytes(b'a'*(2*1024*1024))
    pin = pin_for(source, expected=b'a'*(1024*1024+1))
    sizes = []
    original = acquisition.urlopen
    def open_file(*args, **kwargs):
        response = original(*args, **kwargs)
        read = response.read
        def record_read(size):
            sizes.append(size)
            return read(size)
        response.read = record_read
        return response
    monkeypatch.setattr(acquisition, 'urlopen', open_file)
    report = tmp_path/'acquisition.jsonl'
    with pytest.raises(SystemExit):
        acquisition.acquire(pin, tmp_path/'bad.tgz', report)
    assert sizes == [1024*1024, 2]
    record = json.loads(report.read_text())
    assert record['observedBytes'] == pin['bytes']+1
    assert record['observedSha256'] == hashlib.sha256(b'a'*(pin['bytes']+1)).hexdigest()
