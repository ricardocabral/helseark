"""Retain explicit-person sources, render bounded import handoffs, read candidates.

No model execution, inferred identity, accepted-history mutation or review waiver.
Source/extraction bytes are content addressed; existing objects are verified, never
repaired. Local single-writer trees and external host/tool isolation are required.
"""
import os
from pathlib import Path
import re
import shutil
import stat
from tempfile import TemporaryDirectory
from uuid import uuid4

from .archive import _safe, _writer_lock, _write, head
from .agent_context import build_agent_context, render_task_prompt, document, _verify_producer
from .adapters.pdf import extract_pdf, _directory, _publish_directory, ARTIFACT_BYTES
from .contracts import (ArchiveError, Vault, SourceReceipt, ImportPacket, Candidate,
                        ContextRequest, IntakeLimits, Issue, uuid_string, sha256_string)
from .serialization import decode_json, encode_json, hash_bytes
from .validation import load_definition_registry

LIMITS = IntakeLimits()
# Bounded input allocation in addition to individual fields/depth/resources.
CANDIDATE_FILE_BYTES = 64 * 1024 * 1024


def _regular(path: Path, maximum: int) -> bytes:
    path = Path(path)
    parent = _directory(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ArchiveError('UNSAFE_PATH', 'Expected a regular file.')
            if before.st_size > maximum:
                raise ArchiveError('SOURCE_TOO_LARGE', 'Input exceeds its byte limit.')
            data = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
            if len(data) > maximum:
                raise ArchiveError('SOURCE_TOO_LARGE', 'Input exceeds its byte limit.')
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                    after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise ArchiveError('SOURCE_CHANGED', 'Input changed while reading.')
            return data
    except OSError:
        raise ArchiveError('UNSAFE_PATH', 'Cannot open a regular input without symlinks.') from None
    finally:
        os.close(parent)


def _mkdir(path: Path):
    """Create directories through held no-follow descriptors, including ancestors."""
    if '..' in path.parts:
        raise ArchiveError('UNSAFE_PATH', 'Traversal is forbidden.')
    path = path.absolute()
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            try:
                os.mkdir(part, mode=0o700, dir_fd=fd)
            except FileExistsError:
                pass
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
    except OSError:
        raise ArchiveError('UNSAFE_PATH', 'Directory crosses an unsafe boundary.') from None
    finally:
        os.close(fd)


def _new_directory(path: Path):
    _mkdir(path.parent)
    fd = _directory(path.parent)
    try:
        os.mkdir(path.name, mode=0o700, dir_fd=fd)
    except FileExistsError:
        raise ArchiveError('DESTINATION_EXISTS', 'Output destination must be absent.') from None
    finally:
        os.close(fd)


def _asset(vault, person, data):
    digest = hash_bytes(data)
    root = _safe(vault.root, f'people/{person}/assets/sha256')
    _mkdir(root)
    destination = root / digest
    if destination.exists() or destination.is_symlink():
        if _regular(destination / 'blob', max(len(data), 1)) != data:
            raise ArchiveError('INTEGRITY', 'Retained content-addressed bytes differ.')
        return destination / 'blob'
    stage = root / ('.intake-' + str(uuid4()))
    _new_directory(stage)
    try:
        _write(stage / 'blob', data)
        fd = _directory(root)
        try:
            _publish_directory(fd, stage.name, destination.name)
        finally:
            os.close(fd)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return destination / 'blob'


def _person(vault, person):
    uuid_string(person)
    if head(vault, person) is None:
        raise ArchiveError('PERSON_NOT_FOUND', 'Explicit person has no accepted identity.')


def _source_record(vault, source):
    # Durable receipts stay relocatable; live SourceReceipt paths are explicit.
    return {'receiptVersion': 1, **document(source),
            'assetPath': source.assetPath.relative_to(vault.root).as_posix()}


def add_source(vault: Vault, person: str, source: Path) -> SourceReceipt:
    """Retain bounded original bytes independently of parser success; never guess identity."""
    _person(vault, person)
    data = _regular(source, LIMITS.sourceBytes)
    with _writer_lock(vault):
        path = _asset(vault, person, data)
        media = 'application/pdf' if data.startswith(b'%PDF-') else 'application/octet-stream'
        receipt = SourceReceipt(person, hash_bytes(data), len(data), media, path)
        value = _source_record(vault, receipt)
        stored = path.parent / 'source.json'
        if stored.exists():
            if _regular(stored, 8192) != encode_json(value):
                raise ArchiveError('INTEGRITY', 'Retained source receipt differs from real bytes.')
        else:
            _write(stored, encode_json(value))
    return receipt


def _source_bytes(vault, source):
    _person(vault, source.personId)
    sha256_string(source.sourceSha256)
    path = _safe(vault.root, f'people/{source.personId}/assets/sha256/{source.sourceSha256}/blob')
    if source.assetPath != path or source.existingImport is not None:
        raise ArchiveError('SOURCE_RECEIPT_MISMATCH', 'Source receipt path or disposition is unsupported.')
    data = _regular(path, LIMITS.sourceBytes)
    media = 'application/pdf' if data.startswith(b'%PDF-') else 'application/octet-stream'
    if hash_bytes(data) != source.sourceSha256 or len(data) != source.size or media != source.mediaType:
        raise ArchiveError('SOURCE_RECEIPT_MISMATCH', 'Source receipt differs from retained bytes.')
    stored = decode_json(_regular(path.parent / 'source.json', 8192))
    if stored != _source_record(vault, source):
        raise ArchiveError('SOURCE_RECEIPT_MISMATCH', 'Retained source receipt differs.')
    return data


def _cue_issues(pages):
    # Conservative repeated explicit labels only; never assign a person from text.
    cues = {m.group(1).strip().casefold() for page in pages for m in
            re.finditer(r'(?im)^\s*(?:patient|paciente)\s*:\s*([^\r\n]+)', page['text'])}
    issues = [Issue('SOURCE_IDENTITY_REVIEW', 'review', None, None,
        'Review original person assignment and all identity uncertainty; cue detection is incomplete.')]
    if len(cues) > 1:
        issues.append(Issue('MULTIPLE_PERSON_CUES', 'error', None, None,
            'Multiple explicit patient labels occur in source; separate and reconcile before acceptance.'))
    return issues


def _extraction(vault, source, limits):
    """Immutable source-local receipt binds the exact derived CAS object."""
    receipt_path = source.assetPath.parent / 'extraction.json'
    if receipt_path.exists() or receipt_path.is_symlink():
        raw = _regular(receipt_path, 65536)
        receipt = decode_json(raw)
        if (not isinstance(receipt, dict) or set(receipt) != {
                'receiptVersion','sourceSha256','pagesSha256','pageCount','issues'} or
                receipt['receiptVersion'] != 1 or receipt['sourceSha256'] != source.sourceSha256):
            raise ArchiveError('INTEGRITY', 'Extraction receipt is invalid.')
        sha256_string(receipt['pagesSha256'])
        path = _safe(vault.root, f"people/{source.personId}/assets/sha256/{receipt['pagesSha256']}/blob")
        data = _regular(path, ARTIFACT_BYTES)
        if hash_bytes(data) != receipt['pagesSha256']:
            raise ArchiveError('INTEGRITY', 'Retained extraction bytes differ.')
        pages = decode_json(data)
    else:
        with TemporaryDirectory(prefix='helseark-intake-', dir=source.assetPath.parent) as temp:
            artifact = extract_pdf(source.assetPath, Path(temp) / 'extracted', limits)
            data = _regular(artifact.pagesPath, ARTIFACT_BYTES)
            if hash_bytes(data) != artifact.pagesSha256:
                raise ArchiveError('INTEGRITY', 'Extractor receipt differs from real bytes.')
            pages = decode_json(data)
            path = _asset(vault, source.personId, data)
            receipt = {'receiptVersion': 1, 'sourceSha256': source.sourceSha256,
                'pagesSha256': artifact.pagesSha256, 'pageCount': artifact.pageCount,
                'issues': [document(i) for i in artifact.issues] + [document(i) for i in _cue_issues(pages['pages'])]}
            _write(receipt_path, encode_json(receipt))
    expected = {'provenanceVersion': '1', 'status': 'known', 'method': 'pdf-text',
                'tool': 'pypdf', 'version': '7.0.0', 'model': None, 'preprocessing': []}
    if (not isinstance(pages, dict) or set(pages) != {'artifactVersion','sourceSha256','extraction','pages'} or
            pages['artifactVersion'] != 'helseark-pdf-pages-1' or pages['sourceSha256'] != source.sourceSha256 or
            pages['extraction'] != expected or type(pages['pages']) is not list or
            type(receipt['pageCount']) is not int or len(pages['pages']) != receipt['pageCount']):
        raise ArchiveError('INTEGRITY', 'Unsupported or inconsistent retained extraction.')
    if receipt['pageCount'] > limits.pdfPages:
        raise ArchiveError('PAGE_LIMIT', 'PDF exceeds the page limit.')
    for n, page in enumerate(pages['pages']):
        if (not isinstance(page, dict) or set(page) != {'page','rotation','text'} or type(page['page']) is not int or page['page'] != n+1 or
                type(page['rotation']) is not int or page['rotation'] not in (0,90,180,270) or not isinstance(page['text'], str)):
            raise ArchiveError('INTEGRITY', 'Invalid retained page.')
        if len(page['text'].encode()) > limits.textFieldBytes:
            raise ArchiveError('TEXT_FIELD_LIMIT', 'Page text exceeds byte limit.')
    try:
        issues = tuple(Issue(**i) for i in receipt['issues'])
        if any(not isinstance(i.code, str) or not i.code or
               i.severity not in ('error','review','warning','info') or
               not isinstance(i.message, str) or not i.message or
               i.pointer is not None and not isinstance(i.pointer, str) or
               i.resourceRef is not None and not isinstance(i.resourceRef, str) for i in issues):
            raise TypeError
    except (TypeError, KeyError):
        raise ArchiveError('INTEGRITY', 'Invalid extraction issues.') from None
    # Recompute mandatory cues even if someone removed them from a receipt.
    issues += tuple(_cue_issues(pages['pages']))
    return receipt, pages, path, tuple(dict.fromkeys(issues))


def build_packet(vault: Vault, source: SourceReceipt, destination: Path, *,
                 identityConfirmed: bool = False, outputDirectory: Path | None = None,
                 limits: IntakeLimits = LIMITS) -> ImportPacket:
    """Create a real context/renderer packet; false confirmation renders report-only.

    The three required arguments are Task5's public interface. Optional keyword
    decisions come from the caller/CLI, never PDF prose. Output defaults to a new
    sibling named <packet>-agent-output and is explicitly recorded in the handoff.
    """
    if type(identityConfirmed) is not bool or not isinstance(limits, IntakeLimits):
        raise ArchiveError('INVALID_INPUT', 'Confirmation must be boolean and limits typed.')
    data = _source_bytes(vault, source)
    if len(data) > limits.sourceBytes:
        raise ArchiveError('SOURCE_TOO_LARGE', 'Source exceeds the byte limit.')
    destination = Path(destination).absolute()
    if '..' in destination.parts:
        raise ArchiveError('UNSAFE_PATH', 'Traversal is forbidden.')
    work = vault.root / 'people' / source.personId / 'work'
    if (destination == vault.root or vault.root in destination.parents) and work not in destination.parents:
        raise ArchiveError('UNSAFE_PATH', 'Packet must be outside vault or in selected person work.')
    output = Path(outputDirectory).absolute() if outputDirectory is not None else destination.with_name(destination.name+'-agent-output')
    with _writer_lock(vault):
        _source_bytes(vault, source)
        try:
            receipt, pages, extraction_path, issues = _extraction(vault, source, limits)
        except ArchiveError as error:
            raise ArchiveError(error.code, error.safeMessage,
                {**error.details, 'retainedSource': document(source)}) from None
    _new_directory(destination)
    try:
        context = build_agent_context(vault, source.personId, 'import',
            ContextRequest(sourceHashes=(source.sourceSha256,)), destination / 'context')
        candidate_id = str(uuid4())
        confirmed = identityConfirmed and not any(i.severity == 'error' for i in issues)
        source_data = {'sourceReceipt': document(source), 'extractionReceipt': receipt,
            'extractionPath': str(extraction_path), 'artifact': pages,
            'issues': document(issues),
            'sourceAssertionsAreUntrusted': True}
        rendered = render_task_prompt(context, 'extract-report', {
            'output_directory': str(output), 'identity_confirmed': confirmed,
            'candidate_id': candidate_id, 'source_data': source_data,
            'request': 'Draft only from this selected source. Review every uncertainty; no acceptance is available.'})
        _write(destination / 'prompt.txt', rendered.text.encode())
        _write(destination / 'intake.json', encode_json({'packetVersion': 1, 'importId': candidate_id,
            'personId': source.personId, 'source': document(source), 'extraction': receipt,
            'issues': document(issues), 'identityConfirmed': identityConfirmed,
            'outputDirectory': str(output), 'renderedPrompt': document(rendered)}))
        _write(destination / 'ENTRY.md', b'# Import handoff\n\nRead prompt.txt and context/context.json. Read only their selected routes.\nWrite only to the explicit output directory. Host filesystem/tool isolation is required.\nCandidate validation is not acceptance; Task6 review/publication is unavailable.\n')
    except BaseException:
        shutil.rmtree(destination)
        raise
    return ImportPacket(destination, candidate_id, source.personId, source,
                        context.trustedContextSha256)


def _bounded_json(path, limits):
    value = decode_json(_regular(path, CANDIDATE_FILE_BYTES))
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > limits.jsonDepth:
            raise ArchiveError('DEPTH_LIMIT', 'Candidate nesting exceeds limit.')
        if isinstance(item, str) and len(item.encode()) > limits.textFieldBytes:
            raise ArchiveError('TEXT_FIELD_LIMIT', 'Candidate text exceeds limit.')
        if isinstance(item, dict):
            pending.extend((x, depth+1) for pair in item.items() for x in pair)
        elif isinstance(item, list):
            pending.extend((x, depth+1) for x in item)
    return value


def read_candidate(vault: Vault, candidateDirectory: Path) -> Candidate:
    """Read strict untrusted envelopes for real Task2 checks; never accept records."""
    directory = Path(candidateDirectory).absolute()
    fd = _directory(directory)
    os.close(fd)
    limits = LIMITS
    metadata = _bounded_json(directory / 'candidate.json', limits)
    registry = load_definition_registry(vault)
    if not registry.validate('urn:helseark:schema:0.1.0:candidate', metadata):
        raise ArchiveError('INVALID_ENVELOPE', 'Candidate metadata violates pinned contract.')
    person = metadata['personId']
    _person(vault, person)
    base = head(vault, person)
    if metadata['baseChangeSha256'] != base.changeSha256:
        raise ArchiveError('STALE_BASE', 'Candidate differs from current selected-person head.')
    if metadata['bundlePath'] == metadata['evidencePath'] or 'candidate.json' in (metadata['bundlePath'], metadata['evidencePath']):
        raise ArchiveError('INVALID_ENVELOPE', 'Candidate artifact paths must be distinct.')
    bundle = _bounded_json(_safe(directory, metadata['bundlePath']), limits)
    evidence = _bounded_json(_safe(directory, metadata['evidencePath']), limits)
    if not isinstance(bundle, dict) or not isinstance(bundle.get('entry'), list):
        raise ArchiveError('INVALID_ENVELOPE', 'Expected collection Bundle entries.')
    if len(bundle['entry']) > limits.candidateResources:
        raise ArchiveError('RESOURCE_LIMIT', 'Candidate exceeds resource count limit.')
    if not registry.validate('urn:helseark:schema:0.1.0:evidence', evidence):
        raise ArchiveError('INVALID_ENVELOPE', 'Evidence violates pinned contract.')
    if evidence.get('producerProvenance') != metadata['producerProvenance']:
        raise ArchiveError('PRODUCER_MISMATCH', 'Candidate and evidence producer provenance differ.')
    _verify_producer(vault, metadata['producerProvenance'], registry)
    retained_issues = []
    for digest in metadata['sourceSha256']:
        path = _safe(vault.root, f'people/{person}/assets/sha256/{digest}/blob')
        data = _regular(path, limits.sourceBytes)
        if hash_bytes(data) != digest:
            raise ArchiveError('SOURCE_HASH_MISMATCH', 'Declared source bytes differ.')
        # Legacy non-intake Task2 assets remain supported; PDF intake originals
        # always require their real source/extraction receipts, not agent claims.
        if data.startswith(b'%PDF-'):
            receipt = SourceReceipt(person, digest, len(data), 'application/pdf', path)
            _source_bytes(vault, receipt)
            if not (path.parent / 'extraction.json').exists():
                raise ArchiveError('INTEGRITY', 'PDF source lacks retained extraction receipt.')
            extraction, pages, _, issues = _extraction(vault, receipt, limits)
            retained_issues.extend(issues)
            for entry in evidence['entries']:
                if entry.get('sourceSha256') == digest and entry.get('kind') == 'source':
                    if (entry.get('extraction') != pages['extraction'] or
                            entry.get('locator', {}).get('kind') != 'pdf-page' or
                            entry['locator'].get('extractionSha256') != extraction['pagesSha256'] or
                            'bbox' in entry['locator']):
                        raise ArchiveError('EXTRACTION_MISMATCH', 'PDF evidence differs from retained page-only extraction.')
    candidate = Candidate(directory, metadata['candidateId'], person, base, bundle, evidence,
        tuple(Issue(**i) for i in metadata['unresolved']))
    # Preserve exact envelope binding: mandatory intake issues must be present,
    # not silently appended to an in-memory candidate unlike its bytes on disk.
    required = {i.code: i for i in retained_issues}
    supplied = {i.code: i for i in candidate.unresolved}
    if any(code not in supplied or supplied[code].severity != issue.severity for code, issue in required.items()):
        raise ArchiveError('INTAKE_ISSUES_MISSING', 'Candidate omitted or downgraded retained intake issues.')
    return candidate
