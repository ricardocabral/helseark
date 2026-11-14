"""Retain explicit-person sources, render bounded import handoffs, read candidates.

No model execution, inferred identity, accepted-history mutation or review waiver.
Source/extraction bytes are content addressed; existing objects are verified, never
repaired. Local single-writer trees and external host/tool isolation are required.
"""
import os
from datetime import datetime
from typing import Callable
from uuid import UUID
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
                        PreparedProposal, ContextRequest, IntakeLimits, Issue, uuid_string, sha256_string)
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
    return {'receiptVersion': 1, **document(source), 'existingImport':None,
            'assetPath': source.assetPath.relative_to(vault.root).as_posix()}


def add_source(vault: Vault, person: str, source: Path) -> SourceReceipt:
    """Retain bounded original bytes independently of parser success; never guess identity."""
    _person(vault, person)
    data = _regular(source, LIMITS.sourceBytes)
    with _writer_lock(vault):
        _person(vault, person)
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
        from .portability import _remember_external
        if not Path(source).absolute().is_relative_to(vault.root):
            _remember_external(vault,[person],Path(source).absolute())
    from dataclasses import replace
    from .archive import _history
    existing = next((h.transactionId for h,d,_ in reversed(_history(vault,person))
        if receipt.sourceSha256 in _bounded_json(d/'proposal.json',LIMITS).get('importReview',{}).get('sourceHashes',[])),None)
    return replace(receipt,existingImport=existing)


def _source_bytes(vault, source):
    _person(vault, source.personId)
    sha256_string(source.sourceSha256)
    path = _safe(vault.root, f'people/{source.personId}/assets/sha256/{source.sourceSha256}/blob')
    if source.assetPath != path:
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


def _extraction(vault, source, limits, *, retained_only=False):
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
        if retained_only:
            raise ArchiveError('INTEGRITY', 'Selected source lacks retained extraction.')
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


def _extraction_files(vault, person, sources):
    """Resolve exact retained pages from selected originals, never supplied paths.

    Context owns selection/budget/host authority; intake owns immutable extraction
    receipts and bounded no-follow reads. This path never invokes the PDF parser.
    """
    from .contracts import ContextFile
    files = []
    for selected in sources:
        source = SourceReceipt(person, selected.sha256, selected.size,
                               'application/pdf', Path(selected.path))
        _source_bytes(vault, source)
        receipt, _, path, _ = _extraction(vault, source, LIMITS, retained_only=True)
        data = _regular(path, ARTIFACT_BYTES)
        if hash_bytes(data) != receipt['pagesSha256']:
            raise ArchiveError('INTEGRITY', 'Selected extraction changed during read.')
        file = ContextFile(str(path), receipt['pagesSha256'], len(data), str(path))
        if file not in files:
            files.append(file)
    return tuple(files)


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
            ContextRequest(sourceHashes=(source.sourceSha256,), includeSourceExtractions=
                'selectedExtractions' in load_definition_registry(vault).resolve(
                    'urn:helseark:schema:0.1.0:agent-context')['properties']), destination / 'context')
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
        with _writer_lock(vault):
            _person(vault, source.personId)
            # Retain original host workflow selection outside mutable agent packets.
            control = _safe(vault.root, f'.runtime/intake/{candidate_id}.json')
            _mkdir(control.parent)
            _write(control, encode_json({'personId':source.personId,'sourceHashes':[source.sourceSha256],
                'identityConfirmed':confirmed,'packetPath':str(destination),'outputDirectory':str(output),'trustedContextSha256':context.trustedContextSha256}))
        _write(destination / 'ENTRY.md', b'# Import handoff\n\nRead prompt.txt and context/context.json. Read only their selected routes.\nWrite only to the explicit output directory. Host filesystem/tool isolation is required.\nCandidate validation is not acceptance; a human controls preparation/review/publication.\n')
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


def read_candidate(vault: Vault, candidateDirectory: Path, *, person: str | None = None) -> Candidate:
    """Read strict untrusted envelopes for real Task2 checks; never accept records."""
    directory = Path(candidateDirectory).absolute()
    fd = _directory(directory)
    os.close(fd)
    limits = LIMITS
    metadata = _bounded_json(directory / 'candidate.json', limits)
    if isinstance(metadata, dict) and any(metadata.get(k) != v for k, v in
            {'fhirVersion': vault.config.fhirVersion, 'profileVersion': vault.config.profileVersion,
             'contractVersion': vault.config.contractVersion}.items() if k in metadata):
        raise ArchiveError('UNSUPPORTED_VERSION', 'Candidate version pins are unsupported.')
    registry = load_definition_registry(vault)
    if not registry.validate('urn:helseark:schema:0.1.0:candidate', metadata):
        raise ArchiveError('INVALID_ENVELOPE', 'Candidate metadata violates pinned contract.')
    # Caller authority is checked before metadata can select history or assets.
    if person is not None and metadata['personId'] != person:
        raise ArchiveError('PERSON_MISMATCH', 'Candidate differs from explicitly selected person.')
    person = metadata['personId']
    _person(vault, person)
    base = head(vault, person)
    if metadata['baseChangeSha256'] != base.changeSha256:
        # Historical reload is permitted only for byte-identical accepted inputs.
        from .archive import _history
        _, digest = _candidate_inputs(directory)
        history = _history(vault, person)
        matches = [n for n, (_, path, _) in enumerate(history)
                   if _bounded_json(path/'proposal.json', limits).get('candidateSha256') == digest
                   and 'importReview' in _bounded_json(path/'proposal.json', limits)]
        if not matches:
            raise ArchiveError('STALE_BASE', 'Candidate differs from current selected-person head.')
        base = history[matches[0]-1][0] if matches[0] else None
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


def _candidate_inputs(directory):
    """Digest original serialized candidate artifacts, including exact decimal tokens."""
    metadata = _bounded_json(directory / 'candidate.json', LIMITS)
    paths = ('candidate.json', metadata['bundlePath'], metadata['evidencePath'])
    data = [_regular(_safe(directory, p), CANDIDATE_FILE_BYTES) for p in paths]
    return data, hash_bytes(encode_json([{'path':p,'sha256':hash_bytes(b)} for p,b in zip(paths,data)]))


def _resource_references(value, aliases):
    """Map native Reference.reference fields in a validated FHIR resource.

    The supported native schemas reserve this field for References, including
    nested References. Literals, identifiers, codes and attachment URLs are data.
    Root resource IDs are handled separately by the caller.
    """
    if isinstance(value, list):
        return [_resource_references(v, aliases) for v in value]
    if isinstance(value, dict):
        return {k: aliases.get(v, v) if k == 'reference' and isinstance(v, str)
                else _resource_references(v, aliases) for k,v in value.items()}
    return value


def _evidence_references(evidence, aliases):
    """Map only the envelope's declared resource links; preserve source prose."""
    from copy import deepcopy
    result = deepcopy(evidence)
    for entry in result['entries']:
        for field in ('resourceRef', 'sourceDocument'):
            if field in entry:
                entry[field] = aliases.get(entry[field], entry[field])
        if 'target' in entry:
            ref = entry['target']['reference']
            entry['target']['reference'] = aliases.get(ref, ref)
    return result


def _extraction_identity(candidate):
    """Source-local anchors are evidence coordinates, never medical equivalence."""
    aliases = {}
    anchors = {}
    for entry in candidate.bundle['entry']:
        r = entry['resource']; ref = entry['fullUrl']
        evidence = [e for e in candidate.evidence['entries'] if e.get('target',{}).get('reference',e.get('resourceRef')) in (ref, r['resourceType']+'/'+r['id']) and e['kind']=='source']
        coordinates = [{'source':e['sourceSha256'],'locator':e['locator'],'quote':e['quote'],
                        'pointers':e.get('target',{}).get('pointers',[e.get('pointer')])} for e in evidence]
        anchor = hash_bytes(encode_json({'type':r['resourceType'], 'evidence':sorted(coordinates,key=encode_json)}))
        if anchor in anchors.values():
            raise ArchiveError('RECONCILIATION_REQUIRED','Source-local anchors must distinguish each emitted resource.')
        anchors[ref] = anchor
        aliases[ref] = aliases[r['resourceType']+'/'+r['id']] = anchor
    normalized_resources = []
    for entry in candidate.bundle['entry']:
        resource = _resource_references(entry['resource'], aliases)
        resource['id'] = anchors[entry['fullUrl']]
        normalized_resources.append(resource)
    normalized_resources.sort(key=encode_json)
    normalized_evidence = sorted(_evidence_references(candidate.evidence, aliases)['entries'],key=encode_json)
    return anchors, hash_bytes(encode_json({'resources':normalized_resources,'evidence':normalized_evidence,
        'unresolved':[document(i) for i in candidate.unresolved]}))


def _accepted_proposal(vault, person, directory, base):
    from .review import read_prepared
    return read_prepared(vault, directory, candidate_path=None, base=base)


def prepare_candidate(vault: Vault, candidate: Candidate, *, clock: Callable[[], datetime] | None = None,
                      uuid_factory: Callable[[], UUID] | None = None, reextract=False, reconciliation=None,
                      authorized_sources: tuple[str, ...] | None = None,
                      amendment_target=None, amendment_reason: str | None = None) -> PreparedProposal:
    """Prepare under the writer lock so person removal cannot race draft writes."""
    with _writer_lock(vault):
        return _prepare_candidate_locked(vault,candidate,clock=clock,uuid_factory=uuid_factory,
            reextract=reextract,reconciliation=reconciliation,authorized_sources=authorized_sources,
            amendment_target=amendment_target,amendment_reason=amendment_reason)


def _prepare_candidate_locked(vault: Vault, candidate: Candidate, *, clock: Callable[[], datetime] | None = None,
                      uuid_factory: Callable[[], UUID] | None = None, reextract=False, reconciliation=None,
                      authorized_sources: tuple[str, ...] | None = None,
                      amendment_target=None, amendment_reason: str | None = None) -> PreparedProposal:
    """Compile once for human review. Re-extraction intent/mappings are host inputs.

    Unknown changed anchors require an explicit old ResourceRef or None (new fact).
    Missing old facts are retained and listed; nothing here deletes accepted history.
    """
    from copy import deepcopy
    from datetime import datetime, timezone
    from .archive import _history, _versions, resolve
    from .contracts import PreparedProposal, ResourceRef
    from .validation import validate_candidate, validate_proposal
    from .review import _blocked, read_prepared
    raw, candidate_digest = _candidate_inputs(candidate.path)
    history = _history(vault,candidate.personId)
    for index, (_, directory, _) in enumerate(history):
        old = decode_json(_regular(directory/'proposal.json',CANDIDATE_FILE_BYTES))
        if old['candidateSha256']==candidate_digest and 'importReview' in old:
            return _accepted_proposal(vault,candidate.personId,directory,history[index-1][0] if index else None)
    fresh = read_candidate(vault,candidate.path,person=candidate.personId)
    if fresh != candidate:
        raise ArchiveError('CANDIDATE_MISMATCH','Candidate differs from strict read-time content.')
    selected = decode_json(raw[0])['sourceSha256']
    if authorized_sources is None:
        control = _safe(vault.root,f'.runtime/intake/{fresh.candidateId}.json')
        if not control.exists():
            raise ArchiveError('SOURCE_AUTHORITY_REQUIRED','Original host source selection or explicit authorized_sources required.')
        authority = _bounded_json(control,LIMITS)
        if authority.get('personId') != fresh.personId or authority.get('sourceHashes') != selected:
            raise ArchiveError('SOURCE_SCOPE_MISMATCH','Candidate differs from original host source selection.')
        if authority.get('identityConfirmed') is not True:
            raise ArchiveError('IDENTITY_UNCONFIRMED','Original host assignment is unconfirmed; rebuild under explicit human control.')
    elif (not isinstance(authorized_sources,tuple) or set(authorized_sources) != set(selected) or len(authorized_sources)!=len(selected)):
        raise ArchiveError('SOURCE_SCOPE_MISMATCH','Explicit host sources must exactly match candidate sources.')
    _blocked(validate_candidate(vault,fresh))
    anchors, fingerprint = _extraction_identity(fresh)
    metadata=decode_json(raw[0]); sources=metadata['sourceSha256']
    correction = None
    control = _safe(vault.root, f'.runtime/corrections/{fresh.candidateId}.json')
    if control.exists():
        correction = _bounded_json(control, LIMITS)
        if correction['personId'] != fresh.personId or correction['base'] != fresh.base.changeSha256 or correction['sources'] != sources:
            raise ArchiveError('STALE_BASE', 'Correction control differs from current candidate scope.')
        reextract = True
    if amendment_target is not None:
        if correction or not isinstance(amendment_reason,str) or not amendment_reason.strip() or authorized_sources is None:
            raise ArchiveError('INVALID_INPUT', 'Laboratory amendment requires explicit new sources, target and reason.')
        old = resolve(vault,fresh.personId,amendment_target,at=fresh.base)
        if old['meta']['versionId'] != resolve(vault,fresh.personId,ResourceRef(old['resourceType'],old['id']),at=fresh.base)['meta']['versionId']:
            raise ArchiveError('STALE_BASE','Laboratory amendment target is no longer current.')
        matches = [e for e in fresh.bundle['entry'] if e['resource']['resourceType']==amendment_target.resourceType]
        if len(matches)!=1 or matches[0]['resource'].get('status') not in ('amended','corrected'):
            raise ArchiveError('CORRECTION_STATUS', 'Laboratory amendment requires one amended/corrected target.')
        old_sources = {a['sha256'] for _,_,c in history for a in c['assets']}
        if not set(sources)-old_sources:
            raise ArchiveError('INVALID_INPUT', 'Laboratory amendment requires a newly retained source.')
        correction = {'mode':'laboratory-amendment','reason':amendment_reason,
            'mapping':{matches[0]['fullUrl']:f"{old['resourceType']}/{old['id']}"}}
    prior = []
    for index,(_,directory,_) in enumerate(history):
        old=decode_json(_regular(directory/'proposal.json',CANDIDATE_FILE_BYTES))
        info=old.get('importReview')
        if info and set(info['sourceHashes']) & set(sources):
            if not correction and info['fingerprint']==fingerprint and set(info['sourceHashes'])==set(sources):
                return _accepted_proposal(vault,candidate.personId,directory,history[index-1][0] if index else None)
            prior.append(old)
    if prior and not reextract:
        raise ArchiveError('REEXTRACTION_REQUIRED','Existing source has a changed extraction; explicit human workflow intent required.')
    reconciliation = correction['mapping'] if correction else (reconciliation or {})
    if correction and correction['mode']!='laboratory-amendment' and set(reconciliation)!=set(anchors):
        raise ArchiveError('INVALID_INPUT','Local correction scope must match its original draft.')
    if set(reconciliation)-set(anchors):
        raise ArchiveError('INVALID_INPUT','Reconciliation contains unknown candidate references.')
    old_anchors={a:ref for p in prior for a,ref in p['importReview']['anchors'].items()}
    old_refs={ref for p in prior for ref in p['importReview']['anchors'].values()}
    factory=uuid_factory or uuid4
    def new_id(): return uuid_string(str(factory()))
    instant=(clock or (lambda:datetime.now(timezone.utc)))()
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ArchiveError('INVALID_INPUT','Preparation clock requires a timezone.')
    now=instant.astimezone(timezone.utc).isoformat().replace('+00:00','Z')
    transaction=new_id(); aliases={}; inventory=[]; resources=[]; used=set(); duplicates=[]
    for entry in fresh.bundle['entry']:
        r=deepcopy(entry['resource']); ref=entry['fullUrl']; anchor=anchors[ref]
        previous=None
        selected=reconciliation.get(ref,old_anchors.get(anchor))
        if prior and anchor not in old_anchors and ref not in reconciliation:
            raise ArchiveError('RECONCILIATION_REQUIRED','Changed evidence anchors require explicit mapping or new-fact decision.')
        if selected is not None:
            if isinstance(selected,ResourceRef):
                selected=f'{selected.resourceType}/{selected.id}'
            if (not correction and selected not in old_refs) or not selected.startswith(r['resourceType']+'/'):
                raise ArchiveError('INVALID_REFERENCE','Reconciliation must name an existing same-source resource of the same type.')
            old=resolve(vault,fresh.personId,ResourceRef(*selected.split('/')),at=fresh.base)
            if correction:
                mode = correction['mode']
                expected = ({'entered-in-error':'entered-in-error','cancellation':'cancelled'}.get(mode,old.get('status'))
                    if selected == correction.get('target') else old.get('status'))
                if mode != 'laboratory-amendment' and r.get('status') != expected:
                    raise ArchiveError('CORRECTION_STATUS','Local correction must preserve source status or explicitly invalidate the selected record.')
            rid=old['id']; previous=old['meta']['versionId']; duplicates.append(selected)
        else: rid=new_id()
        if rid in used: raise ArchiveError('DUPLICATE_RESOURCE','Multiple candidate resources map to one identity.')
        used.add(rid); version=new_id(); final=f"{r['resourceType']}/{rid}/_history/{version}"
        aliases[ref]=aliases[r['resourceType']+'/'+r['id']]=final
        r['id']=rid; r['meta'].update(versionId=version,lastUpdated=now)
        resources.append(r)
        inventory.append({'type':r['resourceType'],'id':rid,'versionId':version,'path':f"resources/{r['resourceType']}-{rid}.json",'sha256':'','supersedesVersionId':previous})
    resources=[_resource_references(r,aliases) for r in resources]
    evidence=_evidence_references(fresh.evidence,aliases)
    for final in dict.fromkeys(aliases.values()):
        evidence['entries'].append({'target':{'reference':final,'pointers':['/meta/versionId','/meta/lastUpdated']},'kind':'generated','rule':'prepare-revisions-1'})
    # Native FHIR Provenance records local compilation, never a clinical approver.
    provenance_id=new_id(); provenance_version=new_id(); provenance_ref=f'Provenance/{provenance_id}/_history/{provenance_version}'
    documents=[v for k,v in aliases.items() if k.startswith('DocumentReference/')]
    if not documents: raise ArchiveError('VALIDATION_BLOCKED','Imports require an evidenced source DocumentReference.')
    provenance={'resourceType':'Provenance','id':provenance_id,'meta':{'profile':['https://github.com/ricardocabral/helseark/fhir/StructureDefinition/helseark-provenance|0.1.0'],'versionId':provenance_version,'lastUpdated':now},
        'target':[{'reference':v} for v in dict.fromkeys(aliases.values())], 'recorded':now,
        'agent':[{'who':{'identifier':{'system':'urn:helseark:local-actor','value':'proposal-compiler'}}}],
        'entity':[{'role':'source','what':{'reference':v}} for v in documents] +
                 [{'role':'revision','what':{'reference':f"{i['type']}/{i['id']}/_history/{i['supersedesVersionId']}"}} for i in inventory if i['supersedesVersionId']]}
    resources.append(provenance)
    inventory.append({'type':'Provenance','id':provenance_id,'versionId':provenance_version,'path':f'resources/Provenance-{provenance_id}.json','sha256':'','supersedesVersionId':None})
    evidence['entries'].append({'target':{'reference':provenance_ref,'pointers':['/'+k for k in provenance]},'kind':'generated','rule':'prepare-provenance-1'})
    path=_safe(vault.root,f'work/proposals/{transaction}'); _new_directory(path)
    _mkdir(path/'resources'); _mkdir(path/'inputs')
    for item,r in zip(inventory,resources):
        data=encode_json(r); item['sha256']=hash_bytes(data); _write(path/item['path'],data)
    inputs=[]
    for name,data in zip(('candidate','bundle','evidence'),raw):
        relative=f'inputs/{name}.json'; _write(path/relative,data); inputs.append({'path':relative,'sha256':hash_bytes(data)})
    assets=[]; bindings=[]
    digests=set(sources)
    for e in evidence['entries']:
        digest=e.get('locator',{}).get('extractionSha256')
        if digest: digests.add(digest)
    for digest in sorted(digests):
        relative=f'assets/sha256/{digest}/blob'; data=_regular(_safe(vault.root,f'people/{fresh.personId}/{relative}'),LIMITS.sourceBytes)
        assets.append({'path':relative,'sha256':digest,'size':len(data),'mediaType':'application/pdf' if data.startswith(b'%PDF-') else 'application/json'})
        for name in ('source.json','extraction.json'):
            receipt=_safe(vault.root,f'people/{fresh.personId}/assets/sha256/{digest}/{name}')
            if receipt.exists(): bindings.append({'path':receipt.relative_to(vault.root/f'people/{fresh.personId}').as_posix(),'sha256':hash_bytes(_regular(receipt,65536))})
    _write(path/'evidence.json',encode_json(evidence))
    retained={f"{i['type']}/{i['id']}" for i in inventory}
    omissions=sorted(old_refs-retained)
    # These are review suggestions only. Independent sources retain distinct IDs.
    from .archive import iter_current
    possible = []
    for old in iter_current(vault, fresh.personId, at=fresh.base):
        for resource in resources:
            if (resource['resourceType'] == old['resourceType'] == 'Observation' and
                    resource.get('code') == old.get('code') and
                    resource.get('effectiveDateTime') == old.get('effectiveDateTime') and
                    f"Observation/{old['id']}" not in retained):
                possible.append(f"Observation/{old['id']}")
    duplicates.extend(sorted(set(possible)))
    unresolved=[document(i) for i in fresh.unresolved]
    replaced = {f"{i['type']}/{i['id']}/_history/{i['supersedesVersionId']}" for i in inventory if i['supersedesVersionId']}
    for parent in iter_current(vault,fresh.personId,at=fresh.base):
        if parent['resourceType']=='DiagnosticReport' and f"DiagnosticReport/{parent['id']}" not in retained and any(r['reference'] in replaced for r in parent.get('result',[])):
            unresolved.append(document(Issue('REPORT_RESULT_REVISION_MISMATCH','warning','/result',
                f"DiagnosticReport/{parent['id']}/_history/{parent['meta']['versionId']}",
                'Current report will retain its exact older child; explicitly review whether the parent needs a separate revision.')))
    if possible:
        unresolved.append(document(Issue('POSSIBLE_DUPLICATE_OR_CONTRADICTION','review',None,None,'Independent source assertions remain separate; compare values and source evidence.')))
    if correction:
        unresolved.append(document(Issue('EXPLICIT_CORRECTION','review',None,None,
            correction['mode']+': '+correction['reason'])))
    if prior:
        unresolved.append(document(Issue('REEXTRACTION_RECONCILIATION','review',None,None,'Review changed extraction, identity mappings and preserved omissions.')))
    proposal={'contractVersion':'0.1.0','personId':fresh.personId,'transactionId':transaction,'kind':'correction' if correction else 'reextract' if prior else 'import',
        'candidateSha256':candidate_digest,'baseChangeSha256':fresh.base.changeSha256,'versions':_versions(vault),
        'resources':inventory,'assets':assets,'evidenceSha256':hash_bytes(encode_json(evidence)),'unresolved':unresolved,'inputs':inputs,
        'importReview':{'fingerprint':fingerprint,'sourceHashes':sources,'anchors':{anchors[k]:aliases[k].split('/_history/')[0] for k in anchors},
        'omissions':omissions,'duplicateCandidates':duplicates,'bindings':bindings}}
    _write(path/'proposal.json',encode_json(proposal))
    report=validate_proposal(vault,path); _blocked(report)
    _write(path/'validation.json',encode_json(document(report)))
    result=PreparedProposal(path,fresh.personId,candidate_digest,hash_bytes(encode_json(proposal)),fresh.base,report,fresh.path)
    # Host workflow control lives outside editable packet/proposal trees.
    control=_safe(vault.root,f'.runtime/prepared/{result.proposalSha256}.json'); _mkdir(control.parent)
    _write(control,encode_json({'candidatePath':str(fresh.path),'personId':fresh.personId}))
    return result


def start_correction(vault: Vault, person: str, target, reason: str) -> Candidate:
    """Draft one current revision and its source document; no acceptance authority.

    Prefix reason with transcription:, entered-in-error: or cancellation:.
    Laboratory amendments use a new intake and explicit prepare-time mapping.
    """
    from copy import deepcopy
    from .archive import _history, resolve
    from .contracts import ResourceRef
    mode = reason.split(':', 1)[0] if isinstance(reason, str) else ''
    if mode not in ('transcription', 'entered-in-error', 'cancellation') or not reason.partition(':')[2].strip():
        raise ArchiveError('INVALID_INPUT', 'Use transcription:, entered-in-error: or cancellation: followed by a reason.')
    if target.resourceType not in ('Observation', 'DiagnosticReport'):
        raise ArchiveError('INVALID_REFERENCE', 'Corrections currently support observations and reports.')
    with _writer_lock(vault):
        current = resolve(vault, person, ResourceRef(target.resourceType, target.id))
        if target.versionId and target.versionId != current['meta']['versionId']:
            raise ArchiveError('STALE_BASE', 'Correction target is no longer current.')
        for _, directory, change in reversed(_history(vault, person)):
            if any(i['type']==target.resourceType and i['id']==target.id and i['versionId']==current['meta']['versionId'] for i in change['resources']):
                break
        proposal = _bounded_json(directory/'proposal.json', LIMITS)
        if 'importReview' not in proposal:
            raise ArchiveError('INVALID_INPUT', 'Target has no supported reviewed source.')
        resources = [current] + [_bounded_json(directory/i['path'], LIMITS) for i in change['resources'] if i['type']=='DocumentReference']
        if len(resources)==1:
            raise ArchiveError('INVALID_INPUT', 'Target requires its retained source document.')
        evidence = deepcopy(_bounded_json(directory/'evidence.json', LIMITS))
        refs = {f"{r['resourceType']}/{r['id']}/_history/{r['meta']['versionId']}":'urn:uuid:'+r['id'] for r in resources}
        evidence['entries'] = [e for e in evidence['entries'] if e.get('target',{}).get('reference') in refs]
        for e in evidence['entries']:
            e['target']['reference'] = refs[e['target']['reference']]
        for r in resources:
            r['meta'].pop('versionId',None); r['meta'].pop('lastUpdated',None)
        for e in evidence['entries']:
            e['target']['pointers'] = [p for p in e['target']['pointers'] if p not in ('/meta/versionId','/meta/lastUpdated')]
        evidence['entries'] = [e for e in evidence['entries'] if e['target']['pointers']]
        identifier = str(uuid4()); path = _safe(vault.root, f'work/corrections/{identifier}')
        _new_directory(path)
        metadata = {'contractVersion':'0.1.0','candidateId':identifier,'personId':person,
            'baseChangeSha256':head(vault,person).changeSha256,'fhirVersion':vault.config.fhirVersion,
            'profileVersion':vault.config.profileVersion,'sourceSha256':proposal['importReview']['sourceHashes'],
            'bundlePath':'bundle.json','evidencePath':'evidence.json','producer':{'kind':'local-user','name':'explicit local correction'},
            'producerProvenance':evidence['producerProvenance'],'unresolved':[i for i in proposal['unresolved']
                if i['code'] not in {'EXPLICIT_CORRECTION','REEXTRACTION_RECONCILIATION','POSSIBLE_DUPLICATE_OR_CONTRADICTION','REPORT_RESULT_REVISION_MISMATCH'}]}
        bundle = {'resourceType':'Bundle','type':'collection','entry':[{'fullUrl':'urn:uuid:'+r['id'],'resource':r} for r in resources]}
        for name,value in [('candidate',metadata),('bundle',bundle),('evidence',evidence)]:
            _write(path/(name+'.json'),encode_json(value))
        control = _safe(vault.root, f'.runtime/corrections/{identifier}.json'); _mkdir(control.parent)
        _write(control,encode_json({'personId':person,'base':metadata['baseChangeSha256'],'reason':reason,'mode':mode,'target':f'{target.resourceType}/{target.id}',
            'mapping':{'urn:uuid:'+r['id']:f"{r['resourceType']}/{r['id']}" for r in resources},'sources':metadata['sourceSha256']}))
        authority = _safe(vault.root, f'.runtime/intake/{identifier}.json'); _mkdir(authority.parent)
        _write(authority,encode_json({'personId':person,'sourceHashes':metadata['sourceSha256'],'identityConfirmed':True}))
    return read_candidate(vault,path,person=person)
