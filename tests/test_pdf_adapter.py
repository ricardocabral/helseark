"""Real-parser qualification; no parser responses or clinical facts are mocked."""
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from helseark.contracts import ArchiveError

FIXTURES = Path(__file__).parent / 'fixtures'
SYNTHETIC = FIXTURES / 'synthetic'
FACTS = json.loads((FIXTURES / 'expected/pdf-facts.json').read_text())


def adapter():
    pytest.importorskip('pypdf', reason='Real PDF qualification requires the optional pdf extra.')
    from helseark.adapters.pdf import extract_pdf
    from helseark.contracts import IntakeLimits
    return extract_pdf, IntakeLimits()


def test_exact_text_provenance_and_original_bytes(tmp_path):
    extract, limits = adapter()
    source = SYNTHETIC / 'lab-text.pdf'
    original = source.read_bytes()
    artifact = extract(source, tmp_path / 'out', limits)
    data = artifact.pagesPath.read_bytes()
    retained = json.loads(data)
    assert artifact.method == 'pdf-text'
    assert artifact.toolVersion == '7.0.0'
    assert artifact.pagesSha256 == sha256(data).hexdigest()
    assert retained['sourceSha256'] == sha256(original).hexdigest()
    assert (tmp_path / 'out/original.pdf').read_bytes() == original == source.read_bytes()
    assert retained['extraction'] == {'provenanceVersion': '1', 'status': 'known',
        'method': 'pdf-text', 'tool': 'pypdf', 'version': '7.0.0',
        'model': None, 'preprocessing': []}
    assert retained['artifactVersion'] == 'helseark-pdf-pages-1'
    with pytest.raises(FrozenInstanceError):
        artifact.pageCount = 100
    with pytest.raises(FrozenInstanceError):
        limits.pdfPages = 1


@pytest.mark.parametrize('name', list(FACTS))
def test_real_fixture_pages_and_independent_facts(name, tmp_path, monkeypatch):
    extract, limits = adapter()
    monkeypatch.chdir(tmp_path)
    # A real unrelated file must remain untouched even for hostile PDF text.
    secret = tmp_path / 'another-person.txt'
    secret.write_text('PRIVATE SENTINEL NOT IN PDF')
    artifact = extract(SYNTHETIC.resolve() / name, tmp_path / 'out', limits)
    data = json.loads(artifact.pagesPath.read_bytes())
    facts = FACTS[name]
    assert artifact.pageCount == facts['pages'] == len(data['pages'])
    for n, page in enumerate(data['pages']):
        assert page['page'] == n + 1
        assert page['rotation'] == facts['rotations'][n]
        assert 'bbox' not in page
        for quote in facts['quotes'][n]:
            assert quote in page['text']
        assert 'PRIVATE SENTINEL' not in page['text']
    assert secret.read_text() == 'PRIVATE SENTINEL NOT IN PDF'
    assert not (tmp_path / 'PDF_EXECUTED').exists()
    if name == 'lab-scan.pdf':
        assert data['pages'][0]['text'] == ''
        assert [i.code for i in artifact.issues].count('OCR_REQUIRED') == 1
    if name == 'lab-two-people.pdf':
        assert 'personId' not in data


@pytest.mark.parametrize(('name', 'code'), [
    ('corrupt.pdf', 'PDF_INVALID'), ('encrypted.pdf', 'PDF_ENCRYPTED'),
    ('failed-page.pdf', 'PDF_INVALID'), ('expansion-limit.pdf', 'PDF_STREAM_LIMIT')])
def test_failures_are_safe_and_leave_no_partial_artifact(name, code, tmp_path, capfd):
    extract, limits = adapter()
    source = SYNTHETIC / 'pdf' / name
    original = source.read_bytes()
    with pytest.raises(ArchiveError) as caught:
        extract(source, tmp_path / 'out', limits)
    assert caught.value.code == code
    assert not (tmp_path / 'out').exists()
    assert source.read_bytes() == original
    assert 'synthetic-only-secret' not in str(caught.value)
    assert capfd.readouterr() == ('', '')


@pytest.mark.parametrize(('changes', 'source', 'code'), [
    ({'sourceBytes': 10}, 'lab-text.pdf', 'SOURCE_TOO_LARGE'),
    ({'pdfPages': 1}, 'lab-text.pdf', 'PAGE_LIMIT'),
    ({'pdfPages': 1}, 'pdf/page-limit.pdf', 'PAGE_LIMIT'),
    ({'textFieldBytes': 10}, 'lab-text.pdf', 'TEXT_FIELD_LIMIT')])
def test_limits_reject_instead_of_clinically_truncating(changes, source, code, tmp_path):
    extract, limits = adapter()
    with pytest.raises(ArchiveError) as caught:
        extract(SYNTHETIC / source, tmp_path / 'out', replace(limits, **changes))
    assert caught.value.code == code
    assert not (tmp_path / 'out').exists()


def test_no_overwrite_or_symlink_paths(tmp_path):
    extract, limits = adapter()
    source = SYNTHETIC / 'lab-text.pdf'
    existing = tmp_path / 'existing'; existing.mkdir()
    sentinel = existing / 'pages.json'; sentinel.write_bytes(b'keep')
    link = tmp_path / 'link'; link.symlink_to(existing, target_is_directory=True)
    source_link = tmp_path / 'source.pdf'; source_link.symlink_to(source.resolve())
    for src, dest in [(source, existing), (source, link / 'out'),
                      (source_link, tmp_path / 'out'), (source, tmp_path / '..' / 'escape')]:
        with pytest.raises(ArchiveError) as caught:
            extract(src, dest, limits)
        assert caught.value.code in {'UNSAFE_PATH', 'DESTINATION_EXISTS'}
    assert sentinel.read_bytes() == b'keep'
    assert not (existing / 'out').exists()


def test_missing_dependency_is_typed_exit_six_without_runtime_install(tmp_path):
    # -S removes site-packages, with the actual library imported via src only.
    code = '''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from helseark.adapters.pdf import extract_pdf
from helseark.contracts import IntakeLimits, ArchiveError
try:
    extract_pdf(Path(sys.argv[2]), Path(sys.argv[3]), IntakeLimits())
except ArchiveError as e:
    assert e.code == 'PDF_DEPENDENCY_UNSUPPORTED', e.code
    assert e.details == {'exitCode': 6}
else:
    raise AssertionError('missing dependency accepted')
'''
    result = subprocess.run([sys.executable, '-S', '-c', code,
        str(Path(__file__).resolve().parents[1] / 'src'),
        str(SYNTHETIC / 'lab-text.pdf'), str(tmp_path / 'out')], capture_output=True)
    assert result.returncode == 0, result.stderr.decode()
    assert not (tmp_path / 'out').exists()


@pytest.mark.parametrize('budget', ['WALL_SECONDS', 'MEMORY_BYTES', 'ARTIFACT_BYTES'])
def test_actual_worker_budget_failure_is_cleaned_and_reaped(tmp_path, monkeypatch, budget):
    import helseark.adapters.pdf as pdf
    extract, limits = adapter()
    # Reduce only the controller's budget; still run the real pinned parser.
    monkeypatch.setattr(pdf, budget, 0 if budget == 'WALL_SECONDS' else 1)
    started = []
    real_popen = subprocess.Popen
    def record_process(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        started.append(process)
        return process
    monkeypatch.setattr(subprocess, 'Popen', record_process)
    with pytest.raises(ArchiveError) as caught:
        extract(SYNTHETIC / 'lab-text.pdf', tmp_path / 'out', limits)
    assert caught.value.code == 'PDF_RESOURCE_LIMIT'
    assert len(started) == 1 and started[0].poll() is not None
    assert not (tmp_path / 'out').exists()


def test_retained_pages_resolve_in_actual_task2_validator(tmp_path):
    # Task2's independently authored, persisted candidate supplies surrounding
    # FHIR evidence. Replace only its source label evidence with real PDF output.
    from test_validation import good, asset, codes
    from helseark.serialization import decode_json
    vault, candidate = good.__wrapped__(tmp_path)
    extract, limits = adapter()
    artifact = extract(SYNTHETIC / 'lab-rotated.pdf', tmp_path / 'out', limits)
    original_digest = asset(vault, candidate.personId, (tmp_path / 'out/original.pdf').read_bytes())
    extraction_digest = asset(vault, candidate.personId, artifact.pagesPath.read_bytes())
    document = candidate.bundle['entry'][1]['resource']
    document['content'].append({'attachment': {'url': f'assets/sha256/{original_digest}/blob',
                                               'contentType': 'application/pdf',
                                               'title': 'ROTATED DISPLAY TEST'}})
    entry = next(e for e in candidate.evidence['entries']
                 if e['kind'] == 'source' and e['target']['pointers'] == ['/code/text'])
    entry.update(sourceSha256=original_digest, quote='Analyte R: 3,40 mmol/L',
                 extraction=decode_json(artifact.pagesPath.read_bytes())['extraction'],
                 locator={'kind': 'pdf-page', 'extractionSha256': extraction_digest,
                          'page': 1, 'pageRotationApplied': 90,
                          'coordinateSpace': 'displayed-cropbox-top-left-normalized'})
    # Cover the extra attachment leaves without claiming they are PDF quotations.
    candidate.evidence['entries'].append({'target': {'reference': 'urn:uuid:' + document['id'],
        'pointers': ['/content/1/attachment/url']},
        'kind': 'generated', 'rule': 'synthetic-pdf-link-v1'})
    import copy
    for pointer, quote in [('/content/1/attachment/contentType', 'application/pdf'),
                           ('/content/1/attachment/title', 'ROTATED DISPLAY TEST')]:
        metadata_evidence = copy.deepcopy(entry)
        metadata_evidence.update(target={'reference': 'urn:uuid:' + document['id'],
                                          'pointers': [pointer]}, quote=quote)
        candidate.evidence['entries'].append(metadata_evidence)
    observed = codes(vault, candidate)
    from helseark.validation import validate_candidate
    assert not [i for i in validate_candidate(vault, candidate).issues if i.severity == 'error']
    assert not observed.intersection({'EVIDENCE_LOCATOR_INVALID', 'EVIDENCE_QUOTE_MISMATCH',
        'EXTRACTION_PROVENANCE_UNKNOWN', 'ENVELOPE_INVALID', 'SOURCE_DOCUMENT_MISMATCH'})
    entry['locator']['pageRotationApplied'] = 0
    assert 'EVIDENCE_LOCATOR_INVALID' in codes(vault, candidate)
    entry['locator']['pageRotationApplied'] = 90
    entry['quote'] = 'NOT IN THE SYNTHETIC PDF'
    assert 'EVIDENCE_QUOTE_MISMATCH' in codes(vault, candidate)


def test_empty_page_among_text_pages_is_retained_and_flagged(tmp_path):
    extract, limits = adapter()
    from pypdf import PdfReader, PdfWriter
    writer = PdfWriter()
    writer.add_page(PdfReader(SYNTHETIC / 'lab-text.pdf').pages[0])
    writer.add_page(PdfReader(SYNTHETIC / 'lab-scan.pdf').pages[0])
    writer.add_page(PdfReader(SYNTHETIC / 'lab-text.pdf').pages[1])
    source = tmp_path / 'mixed.pdf'; writer.write(source)
    result = extract(source, tmp_path / 'out', limits)
    pages = json.loads(result.pagesPath.read_bytes())['pages']
    assert [page['page'] for page in pages] == [1, 2, 3]
    assert pages[1]['text'] == '' and 'Status: final' in pages[2]['text']
    assert [(i.code, i.pointer) for i in result.issues if i.code == 'OCR_REQUIRED'] == [
        ('OCR_REQUIRED', '/pages/1')]


@pytest.mark.parametrize('value', [0, -1, True, 1.5])
def test_invalid_limits_fail_before_extraction(value):
    _, limits = adapter()
    with pytest.raises(ArchiveError) as caught:
        replace(limits, sourceBytes=value)
    assert caught.value.code == 'INVALID_LIMIT'


def test_unqualified_dependency_version_is_exit_six(tmp_path, monkeypatch):
    import helseark.adapters.pdf as pdf
    extract, limits = adapter()
    monkeypatch.setattr(pdf, 'PIN', '0.0.0')
    with pytest.raises(ArchiveError) as caught:
        extract(SYNTHETIC / 'lab-text.pdf', tmp_path / 'out', limits)
    assert caught.value.code == 'PDF_DEPENDENCY_UNSUPPORTED'
    assert caught.value.details == {'exitCode': 6}
    assert not (tmp_path / 'out').exists()


def test_nonregular_source_cannot_block_or_parse(tmp_path):
    import os
    extract, limits = adapter()
    source = tmp_path / 'pipe.pdf'; os.mkfifo(source)
    with pytest.raises(ArchiveError) as caught:
        extract(source, tmp_path / 'out', limits)
    assert caught.value.code == 'UNSAFE_PATH'
    assert not (tmp_path / 'out').exists()


def test_cleanup_io_failure_remains_typed_and_private(tmp_path, monkeypatch):
    import os
    extract, limits = adapter()
    unlink = os.unlink
    def fail_cleanup(path, *args, **kwargs):
        if path == 'original.pdf':
            raise PermissionError('PRIVATE I/O DETAIL')
        return unlink(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(os, 'unlink', fail_cleanup)
        with pytest.raises(ArchiveError) as caught:
            extract(SYNTHETIC / 'pdf/encrypted.pdf', tmp_path / 'out', limits)
    assert caught.value.code == 'PDF_IO'
    assert 'PRIVATE' not in str(caught.value)
    assert 'PRIVATE' not in repr(caught.value.details)


def test_signalled_real_child_cannot_publish_success(tmp_path, monkeypatch):
    extract, limits = adapter()
    real_popen = subprocess.Popen
    def killed_child(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        process.kill(); process.wait()
        return process
    monkeypatch.setattr(subprocess, 'Popen', killed_child)
    with pytest.raises(ArchiveError) as caught:
        extract(SYNTHETIC / 'lab-text.pdf', tmp_path / 'out', limits)
    assert caught.value.code == 'PDF_RESOURCE_LIMIT'
    assert not (tmp_path / 'out').exists()


def test_truncated_actual_parser_result_cannot_publish_success(tmp_path, monkeypatch):
    import os
    import helseark.adapters.pdf as pdf
    extract, limits = adapter()
    real_worker = pdf._run_worker
    def truncate_result(source_fd, result_fd, limits):
        real_worker(source_fd, result_fd, limits)
        os.ftruncate(result_fd, 10)
    monkeypatch.setattr(pdf, '_run_worker', truncate_result)
    with pytest.raises(ArchiveError) as caught:
        extract(SYNTHETIC / 'lab-text.pdf', tmp_path / 'out', limits)
    assert caught.value.code == 'PDF_INVALID'
    assert not (tmp_path / 'out').exists()


def test_unavailable_memory_accounting_is_unsupported(tmp_path, monkeypatch):
    import helseark.adapters.pdf as pdf
    extract, limits = adapter()
    def unavailable():
        raise OSError('PRIVATE PLATFORM DETAIL')
    monkeypatch.setattr(pdf, '_resident_reader', unavailable)
    with pytest.raises(ArchiveError) as caught:
        extract(SYNTHETIC / 'lab-text.pdf', tmp_path / 'out', limits)
    assert caught.value.code == 'PDF_PLATFORM_UNSUPPORTED'
    assert caught.value.details == {'exitCode': 6}
    assert not (tmp_path / 'out').exists()


@pytest.mark.parametrize('finish', ['success', 'kill', 'invalid', 'collision-empty', 'collision-sentinel'])
def test_final_absent_while_real_child_stopped_and_atomic_publication(tmp_path, monkeypatch, finish):
    """Catches visible partial output and check-then-overwriting publication."""
    import os
    import signal
    import stat
    extract, limits = adapter()
    source = SYNTHETIC / ('pdf/corrupt.pdf' if finish == 'invalid' else 'lab-text.pdf')
    destination = tmp_path / 'out'
    processes = []
    real_popen = subprocess.Popen

    def stopped_child(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        try:
            os.kill(process.pid, signal.SIGSTOP)
            pid, status = os.waitpid(process.pid, os.WUNTRACED)
            assert pid == process.pid and os.WIFSTOPPED(status)
            assert not destination.exists()
            stages = list(tmp_path.iterdir())
            assert len(stages) == 1 and stages[0].name.startswith('.pdf-')
            assert stat.S_IMODE(stages[0].stat().st_mode) == 0o700
            assert (stages[0] / 'original.pdf').read_bytes() == source.read_bytes()
            if finish.startswith('collision'):
                destination.mkdir()
                if finish == 'collision-sentinel':
                    (destination / 'sentinel').write_bytes(b'unchanged')
            if finish == 'kill':
                process.kill()
            else:
                os.kill(process.pid, signal.SIGCONT)
            return process
        except BaseException:
            process.kill()
            process.wait()
            raise

    monkeypatch.setattr(subprocess, 'Popen', stopped_child)
    if finish == 'success':
        receipt = extract(source, destination, limits)
        assert set(p.name for p in destination.iterdir()) == {'original.pdf', 'pages.json'}
        assert json.loads(receipt.pagesPath.read_bytes())['pages'][1]['page'] == 2
        assert (destination / 'original.pdf').read_bytes() == source.read_bytes()
        assert stat.S_IMODE(destination.stat().st_mode) == 0o700
        assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in destination.iterdir())
    else:
        with pytest.raises(ArchiveError) as caught:
            extract(source, destination, limits)
        assert caught.value.code == {'kill': 'PDF_RESOURCE_LIMIT', 'invalid': 'PDF_INVALID',
            'collision-empty': 'DESTINATION_EXISTS', 'collision-sentinel': 'DESTINATION_EXISTS'}[finish]
        if finish.startswith('collision'):
            assert sorted(p.name for p in destination.iterdir()) == (
                ['sentinel'] if finish.endswith('sentinel') else [])
            if finish.endswith('sentinel'):
                assert (destination / 'sentinel').read_bytes() == b'unchanged'
        else:
            assert not destination.exists()
    assert not list(tmp_path.glob('.pdf-*'))
    assert len(processes) == 1 and processes[0].poll() is not None
    with pytest.raises(ChildProcessError):
        os.waitpid(processes[0].pid, os.WNOHANG)


@pytest.mark.parametrize('kind', ['empty', 'sentinel', 'file', 'symlink'])
def test_preexisting_destination_never_replaced(tmp_path, kind):
    extract, limits = adapter()
    destination = tmp_path / 'out'
    if kind in ('empty', 'sentinel'):
        destination.mkdir()
        if kind == 'sentinel':
            (destination / 'sentinel').write_bytes(b'keep')
    elif kind == 'file':
        destination.write_bytes(b'keep')
    else:
        target = tmp_path / 'target'; target.mkdir()
        destination.symlink_to(target, target_is_directory=True)
    before = destination.lstat()
    with pytest.raises(ArchiveError) as caught:
        extract(SYNTHETIC / 'lab-text.pdf', destination, limits)
    assert caught.value.code == 'DESTINATION_EXISTS'
    assert destination.lstat().st_ino == before.st_ino
    assert not list(tmp_path.glob('.pdf-*'))
    if kind == 'sentinel':
        assert (destination / 'sentinel').read_bytes() == b'keep'
    if kind == 'file':
        assert destination.read_bytes() == b'keep'


def test_default_page_boundary_keeps_all_empty_pages(tmp_path):
    extract, limits = adapter()
    from pypdf import PdfWriter
    for count in (500, 501):
        writer = PdfWriter()
        for _ in range(count):
            writer.add_blank_page(width=100, height=100)
        source = tmp_path / f'pages-{count}.pdf'; writer.write(source)
        destination = tmp_path / f'out-{count}'
        if count == 500:
            result = extract(source, destination, limits)
            pages = json.loads(result.pagesPath.read_bytes())['pages']
            assert len(pages) == result.pageCount == 500
            assert [p['page'] for p in pages] == list(range(1, 501))
            assert all(p['text'] == '' for p in pages)
            assert sum(i.code == 'OCR_REQUIRED' for i in result.issues) == 500
        else:
            with pytest.raises(ArchiveError) as caught:
                extract(source, destination, limits)
            assert caught.value.code == 'PAGE_LIMIT'
            assert not destination.exists()
    assert not list(tmp_path.glob('.pdf-*'))


def text_pdf(path, text):
    """Synthetic single text operation; expectations are supplied independently."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject
    writer = PdfWriter()
    page = writer.add_page(PdfReader(SYNTHETIC / 'lab-text.pdf').pages[0])
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 10 10 Td (' + text + b') Tj ET')
    page[NameObject('/Contents')] = writer._add_object(stream.flate_encode())
    writer.write(path)


@pytest.mark.parametrize('extra', [0, 1])
def test_default_text_utf8_byte_boundary_not_character_count(tmp_path, extra):
    extract, limits = adapter()
    # WinAnsi e-acute maps to two UTF-8 bytes, not one; no slicing is allowed.
    source = tmp_path / 'text.pdf'
    text_pdf(source, b'\xe9' * 524288 + b'A' * extra)
    destination = tmp_path / 'out'
    if extra:
        with pytest.raises(ArchiveError) as caught:
            extract(source, destination, limits)
        assert caught.value.code == 'TEXT_FIELD_LIMIT'
        assert not destination.exists()
    else:
        result = extract(source, destination, limits)
        text = json.loads(result.pagesPath.read_bytes())['pages'][0]['text']
        assert text == 'é' * 524288
        assert len(text.encode('utf-8')) == 1048576
    assert not list(tmp_path.glob('.pdf-*'))


@pytest.mark.parametrize('extra', [0, 1])
def test_default_decoded_stream_exact_boundary(tmp_path, extra):
    extract, limits = adapter()
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject
    writer = PdfWriter(); page = writer.add_blank_page(width=100, height=100)
    stream = DecodedStreamObject(); stream.set_data(b' ' * (16777216 + extra))
    page[NameObject('/Contents')] = writer._add_object(stream.flate_encode())
    source = tmp_path / 'stream.pdf'; writer.write(source)
    destination = tmp_path / 'out'
    if extra:
        with pytest.raises(ArchiveError) as caught:
            extract(source, destination, limits)
        assert caught.value.code == 'PDF_STREAM_LIMIT'
        assert not destination.exists()
    else:
        result = extract(source, destination, limits)
        assert json.loads(result.pagesPath.read_bytes())['pages'] == [
            {'page': 1, 'rotation': 0, 'text': ''}]
    assert not list(tmp_path.glob('.pdf-*'))


def test_source_bytes_exact_and_default_boundaries(tmp_path):
    extract, limits = adapter()
    source = SYNTHETIC / 'lab-text.pdf'
    assert source.stat().st_size == 1975
    result = extract(source, tmp_path / 'exact', replace(limits, sourceBytes=1975))
    assert result.pageCount == 2
    with pytest.raises(ArchiveError) as caught:
        extract(source, tmp_path / 'over', replace(limits, sourceBytes=1974))
    assert caught.value.code == 'SOURCE_TOO_LARGE'
    assert not (tmp_path / 'over').exists()
    # Sparse zero-filled files: bounded retention, never parser expansion bombs.
    for size, expected in [(104857600, 'PDF_INVALID'), (104857601, 'SOURCE_TOO_LARGE')]:
        source = tmp_path / f'{size}.pdf'
        with source.open('wb') as stream:
            stream.truncate(size)
        with pytest.raises(ArchiveError) as caught:
            extract(source, tmp_path / 'invalid', limits)
        assert caught.value.code == expected
        assert not (tmp_path / 'invalid').exists()
    assert not list(tmp_path.glob('.pdf-*'))


def test_default_wall_timeout_stopped_child_reaped_with_no_final_path(tmp_path, monkeypatch):
    import os
    import signal
    import time
    extract, limits = adapter()
    real_popen = subprocess.Popen
    children = []
    def stopped(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        children.append(child)
        os.kill(child.pid, signal.SIGSTOP)
        assert os.WIFSTOPPED(os.waitpid(child.pid, os.WUNTRACED)[1])
        assert not (tmp_path / 'out').exists()
        return child
    monkeypatch.setattr(subprocess, 'Popen', stopped)
    start = time.monotonic()
    with pytest.raises(ArchiveError) as caught:
        extract(SYNTHETIC / 'lab-text.pdf', tmp_path / 'out', limits)
    assert caught.value.code == 'PDF_RESOURCE_LIMIT'
    assert time.monotonic() - start >= 15
    assert children[0].poll() == -signal.SIGKILL
    with pytest.raises(ChildProcessError):
        os.waitpid(children[0].pid, os.WNOHANG)
    assert not list(tmp_path.iterdir())


def test_output_envelope_exact_measured_boundary_without_truncation(tmp_path, monkeypatch):
    import helseark.adapters.pdf as pdf
    extract, limits = adapter()
    source = tmp_path / 'bounded.pdf'; text_pdf(source, b'A' * 4096)
    receipt = extract(source, tmp_path / 'baseline', limits)
    complete = receipt.pagesPath.read_bytes()
    # A reduced controller cap exercises real worker output and final encoding.
    # It does not claim saturation of the fixed 64 MiB child result ceiling.
    monkeypatch.setattr(pdf, 'ARTIFACT_BYTES', len(complete))
    exact = extract(source, tmp_path / 'exact', limits)
    assert exact.pagesPath.read_bytes() == complete
    monkeypatch.setattr(pdf, 'ARTIFACT_BYTES', len(complete) - 1)
    with pytest.raises(ArchiveError) as caught:
        extract(source, tmp_path / 'over', limits)
    assert caught.value.code == 'PDF_RESOURCE_LIMIT'
    assert not (tmp_path / 'over').exists()
    assert not list(tmp_path.glob('.pdf-*'))


@pytest.mark.parametrize('name', list(FACTS))
def test_complete_page_text_against_independent_render_transcription(name, tmp_path):
    extract, limits = adapter()
    expected = json.loads((FIXTURES / 'expected/pdf-pages.json').read_text())
    receipt = extract(SYNTHETIC / name, tmp_path / 'out', limits)
    assert [p['text'] for p in json.loads(receipt.pagesPath.read_bytes())['pages']] == expected[name]
