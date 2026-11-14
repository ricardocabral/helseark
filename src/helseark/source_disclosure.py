"""Host-recorded human source disclosure, separate from untrusted agent packets.

Plans/receipts are ephemeral and denied without their original host digest pins.
Only exact original inclusion can accompany a recovery chain. Supplied derivatives
are exchange attachments, never substitutes for immutable evidence or its quotes.
Local reviewer labels and unsigned digests do not authenticate a person's identity.
"""
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft202012Validator

from .archive import (_read, _json, _write, _safe, _history, _writer_lock,
                      head, open_vault, doctor, _bundled_root)
from .contracts import ArchiveError, ExportSelection, uuid_string
from .serialization import encode_json, hash_bytes

LIMITATIONS = [
    'No automatic patient recognition, OCR, redaction, clinical correction or source overwrite.',
    'Local reviewer labels are not authenticated identities; hashes are not signatures.',
    'Original vault, household backups, earlier exports and unknown external copies remain; no erasure is promised.',
]
DERIVATIVE_LIMITATIONS = [
    'All original source files, source receipts and extraction artifacts are omitted from this exchange snapshot.',
    'Supplied derivative mapping and omissions are human assertions, not machine-verified redaction or medical losslessness.',
    'Original resource bytes and source hash references remain unchanged; derivative bytes do not satisfy original evidence references or source quotes.',
    'Original-source evidence verification and full history recovery are unsupported from this derivative snapshot; obtain the originals separately if required.',
]


def _schema(value):
    schema = _json(_bundled_root(), 'schemas/0.1.0/source-disclosure.schema.json')
    if not Draft202012Validator(schema).is_valid(value):
        raise ArchiveError('REVIEW_MISMATCH', 'Invalid source disclosure contract.')


def _source_inventory(vault, person):
    """Exact accepted asset/receipt closure shared by capture and recovery verification."""
    sources, paths = {}, set()
    for _, directory, change in _history(vault, person):
        for asset in change['assets']:
            relative = f"people/{person}/{asset['path']}"
            sources[relative] = dict(path=relative, sha256=asset['sha256'], size=asset['size'], mediaType=asset['mediaType'])
            paths.add(relative)
        proposal = _json(directory, 'proposal.json')
        paths.update(f"people/{person}/{b['path']}" for b in proposal.get('importReview', {}).get('bindings', []))
    files = []
    for path in sorted(paths):
        data = _read(vault.root, path)
        files.append(dict(path=path, sha256=hash_bytes(data), size=len(data)))
    return [sources[p] for p in sorted(sources)], files


def _capture(vault, person, selection):
    from .portability import fhir_collection, _blocked
    uuid_string(person)
    open_vault(vault.root)
    _blocked(doctor(vault))
    at = head(vault, person)
    if at is None:
        raise ArchiveError('PERSON_NOT_FOUND', 'Selected person has no accepted history.')
    sources, files = _source_inventory(vault,person)
    _, mapping = fhir_collection(vault, person, selection.resourceRefs, at=at)
    return dict(vaultId=vault.config.vaultId, personId=person, head=asdict(at),
                selection={**asdict(selection), 'resourceRefs':[asdict(r) for r in selection.resourceRefs]},
                referenceMap=mapping, originalSources=sources, sourceFiles=files)


def prepare_disclosure(vault, person: str, selection: ExportSelection, destination: Path, *, derivatives=()) -> Path:
    """Capture a reviewable plan; read only individually specified derivative files.

    derivatives: [{sourceSha256, path, mediaType, mapping, omissions}]. Every PDF
    must be covered for derivative delivery; all original source files are omitted.
    """
    from .portability import _destination, _publish
    from tempfile import mkdtemp
    import shutil
    destination = _destination(destination, vault.root)
    if not selection.includeSources or derivatives and selection.mode != 'selected-current':
        raise ArchiveError('INVALID_INPUT', 'Derivative delivery requires selected-current; recovery retains exact originals.')
    stage = Path(mkdtemp(prefix='.helseark-disclosure-', dir=destination.parent))
    try:
        with _writer_lock(vault):
            captured = _capture(vault, person, selection)
            entries = []
            if not isinstance(derivatives, (list, tuple)):
                raise ArchiveError('INVALID_INPUT', 'Expected individually mapped derivative files.')
            for supplied in derivatives:
                if not isinstance(supplied, dict) or set(supplied) != {'sourceSha256','path','mediaType','mapping','omissions'} or any(not isinstance(x,str) or not x.strip() for x in supplied.values()):
                    raise ArchiveError('INVALID_INPUT', 'Each derivative needs an exact source hash, file, media type, human mapping and omissions.')
                if supplied['sourceSha256'] not in {s['sha256'] for s in captured['originalSources']}:
                    raise ArchiveError('REVIEW_MISMATCH', 'Derivative is unrelated to selected original sources.')
                path = Path(supplied['path']).absolute()
                data = _read(path.parent, path.name)
                digest = hash_bytes(data)
                if digest in {s['sha256'] for s in captured['originalSources']}:
                    raise ArchiveError('INVALID_INPUT', 'Unchanged original bytes require the original-inclusion route.')
                relative = f'derivatives/{digest}/blob'
                target = stage/relative
                target.parent.mkdir(parents=True, exist_ok=True)
                _write(target, data)
                entries.append({k:v for k,v in supplied.items() if k!='path'} | dict(path=relative, sha256=digest, size=len(data)))
            if entries and {s['sha256'] for s in captured['originalSources'] if s['mediaType']=='application/pdf'} - {e['sourceSha256'] for e in entries}:
                raise ArchiveError('INVALID_INPUT', 'Map every original PDF explicitly or use original inclusion.')
            plan = dict(format='helseark-source-plan-1', planId=str(uuid4()), **captured,
                        originalDisposition='omitted-all' if entries else 'included-exact', derivatives=entries,
                        limitations=LIMITATIONS + (DERIVATIVE_LIMITATIONS if entries else [
                            'ORIGINAL SHARED SOURCES included byte-for-byte: may disclose excluded people on any page and retained extraction/receipt text.']))
            _schema(plan)
            raw = encode_json(plan)
            _write(stage/'plan.json', raw)
            _publish(stage, destination)
            control = _safe(vault.root, f".runtime/source-disclosures/{plan['planId']}.json")
            control.parent.mkdir(parents=True, exist_ok=True)
            _write(control, encode_json({'planSha256':hash_bytes(raw)}))
        return destination
    finally:
        if stage.exists():shutil.rmtree(stage)


def _verified_plan(vault, folder, person=None, selection=None):
    plan = _json(folder, 'plan.json'); _schema(plan)
    if plan['format'] != 'helseark-source-plan-1':
        raise ArchiveError('REVIEW_MISMATCH', 'Expected source disclosure plan.')
    control = _safe(vault.root, f".runtime/source-disclosures/{plan['planId']}.json")
    if not control.exists():
        raise ArchiveError('REVIEW_MISMATCH', 'Original host disclosure control is missing; prepare and review again.')
    pin = _json(control.parent, control.name)
    if hash_bytes(_read(folder, 'plan.json')) != pin.get('planSha256'):
        raise ArchiveError('REVIEW_MISMATCH', 'Disclosure plan changed after capture.')
    if selection is None:
        from .contracts import ResourceRef
        s = plan['selection']
        selection = ExportSelection(s['mode'], tuple(ResourceRef(**r) for r in s['resourceRefs']), s['includeSources'])
    current = _capture(vault, person or plan['personId'], selection)
    if encode_json(current) != encode_json({k:plan[k] for k in current}):
        raise ArchiveError('REVIEW_MISMATCH', 'Disclosure person, Head, selection or source bytes changed; prepare and review again.')
    for item in plan['derivatives']:
        data = _read(folder, item['path'])
        if len(data)!=item['size'] or hash_bytes(data)!=item['sha256']:
            raise ArchiveError('REVIEW_MISMATCH', 'Reviewed derivative bytes changed.')
    review_control = control.with_suffix('.review.json')
    if review_control.exists():
        pin['receiptSha256'] = _json(review_control.parent,review_control.name).get('receiptSha256')
    return plan, control, pin


def record_disclosure(vault, folder: Path, decision: dict) -> Path:
    """Record an explicit human decision; never infer one from source/agent text."""
    folder = Path(folder)
    _schema(decision)
    with _writer_lock(vault):
        plan, control, pin = _verified_plan(vault, folder)
        if pin.get('receiptSha256'):
            raise ArchiveError('REVIEW_MISMATCH', 'This plan already has a recorded decision; prepare a fresh plan to review again.')
        if decision.get('format')!='helseark-source-decision-1' or decision.get('planSha256')!=pin['planSha256']:
            raise ArchiveError('REVIEW_MISMATCH', 'Decision must bind the exact displayed plan digest.')
        receipt = dict(format='helseark-source-review-1', planId=plan['planId'], decision=decision,
                       reviewedAt=datetime.now(timezone.utc).isoformat())
        _schema(receipt)
        raw = encode_json(receipt)
        _write(folder/'review.json', raw)
        _write(control.with_suffix('.review.json'), encode_json({'receiptSha256':hash_bytes(raw)}))
    return folder/'review.json'


def reviewed_disclosure(vault, person, selection, folder):
    """Called under the export writer lock; no packet or standalone receipt grants authority."""
    folder = Path(folder)
    plan, _, pin = _verified_plan(vault, folder, person, selection)
    if not pin.get('receiptSha256') or hash_bytes(_read(folder,'review.json'))!=pin['receiptSha256']:
        raise ArchiveError('REVIEW_MISMATCH', 'No unchanged host-recorded human disclosure decision.')
    receipt = _json(folder, 'review.json'); _schema(receipt)
    if receipt['format']!='helseark-source-review-1' or receipt['planId']!=plan['planId'] or receipt['decision']['planSha256']!=pin['planSha256']:
        raise ArchiveError('REVIEW_MISMATCH', 'Disclosure receipt does not bind this plan.')
    return {'plan':plan, 'review':receipt}


def verify_disclosure(bundle, manifest):
    """Verify portable accounting, not host authority or authenticated identity.

    Export execution requires original host controls; a portable unsigned receipt
    only records what was declared and cannot grant a future export decision.
    """
    from .archive import _files
    plan = manifest['sourceDisclosure']['plan']; receipt = manifest['sourceDisclosure']['review']
    _schema(plan); _schema(receipt)
    def reject():
        raise ArchiveError('INTEGRITY','Export source disclosure accounting differs from its captured plan.')
    if (manifest['kind']=='backup' or manifest['people']!=[plan['personId']] or
        manifest['heads']!={plan['personId']:plan['head']} or manifest['kind']!=plan['selection']['mode'] or
        receipt['planId']!=plan['planId'] or receipt['decision']['planSha256']!=hash_bytes(encode_json(plan))):reject()
    derivatives = plan['derivatives']; omitted = plan['originalDisposition']=='omitted-all'
    if bool(derivatives)!=omitted or omitted and manifest['kind']!='selected-current':reject()
    if plan['limitations'] != LIMITATIONS + (DERIVATIVE_LIMITATIONS if omitted else [
        'ORIGINAL SHARED SOURCES included byte-for-byte: may disclose excluded people on any page and retained extraction/receipt text.']):reject()
    if manifest['kind']=='selected-current' and encode_json(manifest['referenceMap'])!=encode_json(plan['referenceMap']):reject()
    if manifest['kind']=='full-person':
        originals, retained = _source_inventory(open_vault(bundle/'vault'),plan['personId'])
        if encode_json(originals)!=encode_json(plan['originalSources']) or encode_json(retained)!=encode_json(plan['sourceFiles']):reject()
    files = {f['path']:f for f in manifest['files']}
    source_files = {f['path']:f for f in plan['sourceFiles']}
    if len(source_files)!=len(plan['sourceFiles']):reject()
    for source in plan['originalSources']:
        if source_files.get(source['path'])!={k:source[k] for k in ('path','sha256','size')}:reject()
    prefix = 'vault/' if manifest['kind']=='full-person' else 'sources/'
    expected = set()
    if not omitted:
        for item in source_files.values():
            path = prefix+item['path']; expected.add(path)
            if files.get(path)!={**item,'path':path}:reject()
    actual = _files(bundle)
    if manifest['kind']=='selected-current' and {p for p in actual if p.startswith('sources/')}!=expected:reject()
    derivative_paths = set()
    originals = {s['sha256'] for s in plan['originalSources']}
    for item in derivatives:
        if item['sourceSha256'] not in originals or item['sha256'] in originals or item['path']!=f"derivatives/{item['sha256']}/blob":reject()
        derivative_paths.add(item['path'])
        if files.get(item['path'])!={k:item[k] for k in ('path','sha256','size')}:reject()
    if {p for p in actual if p.startswith('derivatives/')}!=derivative_paths:reject()
    if omitted and {s['sha256'] for s in plan['originalSources'] if s['mediaType']=='application/pdf'} - {d['sourceSha256'] for d in derivatives}:reject()
