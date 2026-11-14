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
