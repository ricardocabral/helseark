"""Issued native attachment admission and disclosure, with synthetic review only."""
from pathlib import Path
import pytest

from helseark.archive import init_vault, add_person, commit_candidate, doctor, head
from helseark.adapters.fhir_r4 import import_fhir_r4, IdentityMapping
from helseark.contracts import PersonDraft, ArchiveError, ExportSelection
from helseark.intake import add_source, prepare_candidate
from helseark.serialization import encode_json, decode_json, hash_bytes
from helseark.review import render_review, record_review
from helseark.contracts import ReviewDecision


def decision(vault, proposal):
    view = render_review(vault, proposal)
    acks = tuple({'issueId':i['issueId'], 'code':i['code'], 'resourceRef':i['resourceRef'],
                  'reason':'SYNTHETIC test review only; no clinical approval.'}
                 for i in view.issues if i['severity'] in ('review','warning'))
    return record_review(vault, proposal, ReviewDecision(
        True, 'accept-with-acknowledged-limitations', acks, 'SYNTHETIC test reviewer'))


def issued(tmp_path, kind, mode='retained', media='application/octet-stream', data=b'SYNTHETIC attachment\n'):
    vault = init_vault(tmp_path/'vault')
    person = add_person(vault, PersonDraft('Synthetic selected'))
    other = add_person(vault, PersonDraft('Synthetic selected'))
    original = tmp_path/'original'; original.write_bytes(data)
    digest = hash_bytes(data)
    blob = vault.root/f'people/{person}/assets/sha256/{digest}/blob'
    if mode == 'raw':
        blob.parent.mkdir(parents=True); blob.write_bytes(data)
    elif mode == 'copied-other':
        add_source(vault, other, original)
        blob.parent.mkdir(parents=True); blob.write_bytes(data)
    elif mode == 'copied-receipt':
        other_source = add_source(vault, other, original)
        blob.parent.mkdir(parents=True); blob.write_bytes(data)
        (blob.parent/'source.json').write_bytes((other_source.assetPath.parent/'source.json').read_bytes())
    elif mode != 'missing':
        retained = add_source(vault, person, original)
    if mode.startswith('receipt-'):
        receipt = decode_json((blob.parent/'source.json').read_bytes())
        field, value = {
            'receipt-person':('personId',other), 'receipt-hash':('sourceSha256','0'*64),
            'receipt-size':('size',len(data)+1), 'receipt-path':('assetPath',f'people/{other}/assets/sha256/{digest}/blob'),
            'receipt-media':('mediaType','application/pdf'), 'receipt-extra':('unknown',True),
        }.get(mode, ('personId',other))
        receipt[field] = value
        if mode == 'receipt-malformed': receipt = {'personId':other}
        (blob.parent/'source.json').write_bytes(encode_json(receipt))
    if mode == 'hash': blob.write_bytes(b'changed SYNTHETIC bytes')
    if mode == 'symlink': blob.unlink(); blob.symlink_to(original)
    if mode == 'limit':
        with blob.open('wb') as stream: stream.truncate(100*1024*1024+1)
    if mode in ('extraction', 'extraction-relation'):
        from helseark.intake import build_packet
        build_packet(vault, retained, tmp_path/'packet', identityConfirmed=True)
        receipt = decode_json((blob.parent/'extraction.json').read_bytes())
        blob = blob.parent.parent/receipt['pagesSha256']/'blob'
        digest = receipt['pagesSha256']; data = blob.read_bytes()
        if mode == 'extraction-relation':
            receipt['sourceSha256'] = '0'*64
            (blob.parent/'extraction.json').write_bytes(encode_json(receipt))
    if mode == 'original-extraction-relation':
        (blob.parent/'extraction.json').write_bytes(encode_json(dict(
            receiptVersion=1, sourceSha256='0'*64, pagesSha256=digest, pageCount=1, issues=[])))
    attachment = dict(url=f'assets/sha256/{digest}/blob', contentType=media, size=len(data), title='SYNTHETIC retained original')
    resource = dict(resourceType=kind, id='r1', subject={'reference':'Patient/p1'},
                    status='current' if kind=='DocumentReference' else 'final')
    if kind == 'DocumentReference':
        resource['content'] = [dict(attachment=attachment)]
    else:
        resource.update(code={'text':'Synthetic report'}, presentedForm=[attachment])
    if mode == 'size': attachment['size'] += 1
    incoming = tmp_path/'incoming.json'
    incoming.write_bytes(encode_json(dict(resourceType='Bundle', type='collection', entry=[
        dict(resource=dict(resourceType='Patient', id='p1')), dict(resource=resource)])))
    source = add_source(vault, person, incoming)
    candidate = import_fhir_r4(source, person, IdentityMapping(
        'Patient/p1', person, 'Explicit SYNTHETIC assignment', 'https://synthetic.example'))
    return vault, person, other, blob, candidate


@pytest.mark.parametrize('kind', ['DocumentReference', 'DiagnosticReport'])
@pytest.mark.parametrize('media', ['text/plain', 'application/octet-stream', 'application/fhir+json'])
def test_pdf_cannot_be_declared_text(tmp_path, kind, media):
    data = (Path(__file__).parent/'fixtures/synthetic/lab-two-people.pdf').read_bytes()
    vault, person, _, blob, candidate = issued(tmp_path, kind, media=media, data=data)
    before = head(vault, person)
    with pytest.raises(ArchiveError, match='SOURCE_MEDIA_TYPE_MISMATCH'):
        prepare_candidate(vault, candidate)
    assert head(vault, person) == before and blob.read_bytes() == data


@pytest.mark.parametrize('kind', ['DocumentReference', 'DiagnosticReport'])
@pytest.mark.parametrize('explicit', [False, True])
def test_raw_cas_is_not_retained_source_authority(tmp_path, kind, explicit):
    vault, person, _, _, candidate = issued(tmp_path, kind, mode='raw')
    before = head(vault, person)
    sources = tuple(decode_json((candidate.path/'candidate.json').read_bytes())['sourceSha256'])
    with pytest.raises(ArchiveError, match='SOURCE_AUTHORITY_REQUIRED'):
        prepare_candidate(vault, candidate, authorized_sources=sources if explicit else None)
    assert head(vault, person) == before


@pytest.mark.parametrize('kind', ['DocumentReference', 'DiagnosticReport'])
@pytest.mark.parametrize('mode', ['copied-other', 'copied-receipt', 'receipt-malformed', 'receipt-person',
    'receipt-hash', 'receipt-size', 'receipt-path', 'receipt-media', 'receipt-extra',
    'original-extraction-relation', 'missing', 'hash', 'size', 'symlink', 'limit'])
def test_unverified_attachment_never_advances_head(tmp_path, kind, mode):
    vault, person, _, blob, candidate = issued(tmp_path, kind, mode=mode)
    before = head(vault, person)
    frozen = {p:p.read_bytes() for p in (vault.root/'people').rglob('*')
              if p.is_file() and not p.is_symlink() and p.stat().st_size < 1024**2}
    with pytest.raises(ArchiveError):
        prepare_candidate(vault, candidate)
    assert head(vault, person) == before
    assert all(p.read_bytes() == data for p,data in frozen.items())


@pytest.mark.parametrize('kind', ['DocumentReference', 'DiagnosticReport'])
@pytest.mark.parametrize('media,data', [
    ('application/octet-stream', b'SYNTHETIC original\n'),
    ('text/plain', b'SYNTHETIC original\n'),
    ('application/json', b'{"synthetic":true}\n'),
    ('application/fhir+json', b'{"resourceType":"Patient","id":"synthetic"}\n'),
    ('text/csv', b'label,value\nSYNTHETIC,1.20\n'),
    ('application/pdf', None),
])
def test_retained_attachment_public_review_and_export(tmp_path, kind, media, data):
    from helseark.portability import export_person, verify_export
    from helseark.source_disclosure import prepare_disclosure, record_disclosure
    if data is None:
        data = (Path(__file__).parent/'fixtures/synthetic/lab-two-people.pdf').read_bytes()
    vault, person, other, blob, candidate = issued(tmp_path, kind, media=media, data=data)
    frozen = {p:p.read_bytes() for p in (vault.root/'people').rglob('*') if p.is_file()}
    proposal = prepare_candidate(vault, candidate)
    metadata = decode_json((proposal.path/'proposal.json').read_bytes())
    asset = next(a for a in metadata['assets'] if a['sha256'] == hash_bytes(data))
    assert asset['mediaType'] == media and asset['size'] == len(data)
    binding = next(b for b in metadata['importReview']['bindings'] if b['path'] ==
                   f'assets/sha256/{hash_bytes(data)}/source.json')
    assert binding['sha256'] == hash_bytes((blob.parent/'source.json').read_bytes())
    with pytest.raises(ArchiveError, match='REVIEW_REQUIRED'):
        commit_candidate(vault, proposal, None)
    commit_candidate(vault, proposal, decision(vault, proposal))
    assert not doctor(vault).issues
    selection = ExportSelection('selected-current', (), True)
    with pytest.raises(ArchiveError, match='SOURCE_SCOPE_REVIEW_REQUIRED'):
        export_person(vault, person, tmp_path/'denied', selection)
    plan = prepare_disclosure(vault, person, selection, tmp_path/'plan')
    plan_data = decode_json((plan/'plan.json').read_bytes())
    assert plan_data['personId'] == person
    assert hash_bytes(data) in {a['sha256'] for a in plan_data['originalSources']}
    def disclose(plan):
        record_disclosure(vault, plan, dict(format='helseark-source-decision-1',
            planSha256=hash_bytes((plan/'plan.json').read_bytes()), humanReviewed=True,
            confirmedPerson=True, acknowledgedDisclosure=True,
            reviewer={'kind':'synthetic-test','label':'SYNTHETIC review only'},
            reason='SYNTHETIC scope and omissions review; no clinical approval'))
    disclose(plan)
    export = export_person(vault, person, tmp_path/'original-export', selection, review=plan)
    assert decode_json((export.path/'export.json').read_bytes())['sourceDisclosure']['plan']['originalDisposition'] == 'included-exact'
    derivative = tmp_path/'derivative.txt'; derivative.write_bytes(b'SYNTHETIC supplied selected subset\n')
    plan2 = prepare_disclosure(vault, person, selection, tmp_path/'derivative-plan', derivatives=[dict(
        sourceSha256=hash_bytes(data), path=str(derivative), mediaType='text/plain',
        mapping='SYNTHETIC manually supplied subset', omissions='SYNTHETIC excluded other person; not machine verified')])
    disclose(plan2)
    derived = export_person(vault, person, tmp_path/'derivative-export', selection, review=plan2)
    assert not verify_export(derived.path).issues and not (derived.path/'sources').exists()
    assert (derived.path/f'derivatives/{hash_bytes(derivative.read_bytes())}/blob').read_bytes() == derivative.read_bytes()
    manifest = decode_json((derived.path/'export.json').read_bytes())
    assert manifest['sourceDisclosure']['plan']['originalDisposition'] == 'omitted-all'
    assert manifest['sourceDisclosure']['plan']['derivatives'][0]['omissions']
    assert not verify_export(export.path).issues
    assert (export.path/f'sources/people/{person}/assets/sha256/{hash_bytes(data)}/blob').read_bytes() == data
    assert all(p.read_bytes() == old for p,old in frozen.items())
    assert head(vault, other).sequence == 1
    # A second issued source legitimately reuses this retained same-person blob.
    old_accepted = {p:p.read_bytes() for p in (vault.root/'people'/person/'accepted').rglob('*') if p.is_file()}
    incoming = decode_json((tmp_path/'incoming.json').read_bytes())
    incoming['entry'][1]['resource']['id'] = 'reuse'
    reused = tmp_path/'reuse.json'; reused.write_bytes(encode_json(incoming))
    source2 = add_source(vault, person, reused)
    candidate2 = import_fhir_r4(source2, person, IdentityMapping(
        'Patient/p1', person, 'SYNTHETIC same-person retained reuse', 'https://synthetic.example'))
    proposal2 = prepare_candidate(vault, candidate2)
    commit_candidate(vault, proposal2, decision(vault, proposal2))
    assert head(vault, person).sequence == 3 and not doctor(vault).issues
    assert all(p.read_bytes() == old for p,old in old_accepted.items())
    assert blob.read_bytes() == data


@pytest.mark.parametrize('kind', ['DocumentReference', 'DiagnosticReport'])
@pytest.mark.parametrize('mode', ['extraction', 'extraction-relation'])
def test_extracted_attachment_binds_verified_original_closure(tmp_path, kind, mode):
    data = (Path(__file__).parent/'fixtures/synthetic/lab-text.pdf').read_bytes()
    vault, person, _, blob, candidate = issued(tmp_path, kind, mode=mode, media='application/json', data=data)
    before = head(vault, person)
    if mode == 'extraction-relation':
        with pytest.raises(ArchiveError): prepare_candidate(vault, candidate)
        assert head(vault, person) == before
        return
    proposal = prepare_candidate(vault, candidate)
    metadata = decode_json((proposal.path/'proposal.json').read_bytes())
    assert {hash_bytes(data), hash_bytes(blob.read_bytes())}.issubset({a['sha256'] for a in metadata['assets']})
    assert next(a for a in metadata['assets'] if a['sha256'] == hash_bytes(data))['mediaType'] == 'application/pdf'
    assert len(metadata['importReview']['bindings']) >= 3
    commit_candidate(vault, proposal, decision(vault, proposal))
    assert not doctor(vault).issues


@pytest.mark.parametrize('kind', ['DocumentReference', 'DiagnosticReport'])
def test_non_pdf_cannot_claim_pdf_media(tmp_path, kind):
    vault, person, _, _, candidate = issued(tmp_path, kind, media='application/pdf')
    before = head(vault, person)
    with pytest.raises(ArchiveError, match='SOURCE_MEDIA_TYPE_MISMATCH'):
        prepare_candidate(vault, candidate)
    assert head(vault, person) == before


@pytest.mark.parametrize('kind', ['DocumentReference', 'DiagnosticReport'])
def test_attachment_receipt_edit_invalidates_exact_review(tmp_path, kind):
    vault, person, other, blob, candidate = issued(tmp_path, kind)
    before = head(vault, person)
    proposal = prepare_candidate(vault, candidate)
    review = decision(vault, proposal)
    path = blob.parent/'source.json'
    receipt = decode_json(path.read_bytes()); receipt['personId'] = other
    path.write_bytes(encode_json(receipt))
    with pytest.raises(ArchiveError): commit_candidate(vault, proposal, review)
    assert head(vault, person) == before


def test_genuine_legacy_correction_preserves_explicit_prior_authority(tmp_path):
    from test_validation import good
    from helseark.intake import read_candidate, start_correction
    from helseark.contracts import ResourceRef
    from helseark.archive import iter_current
    vault, candidate = good.__wrapped__(tmp_path)
    sources = tuple(decode_json((candidate.path/'candidate.json').read_bytes())['sourceSha256'])
    proposal = prepare_candidate(vault, read_candidate(vault, candidate.path), authorized_sources=sources)
    commit_candidate(vault, proposal, decision(vault, proposal))
    person = candidate.personId
    old = next(r for r in iter_current(vault, person) if r['resourceType']=='Observation')
    frozen = {p:p.read_bytes() for p in (vault.root/'people'/person/'accepted').rglob('*') if p.is_file()}
    correction = start_correction(vault, person, ResourceRef('Observation',old['id']),
                                  'transcription: SYNTHETIC rechecked original')
    revised = prepare_candidate(vault, correction)
    commit_candidate(vault, revised, decision(vault, revised))
    assert head(vault, person).sequence == 3 and not doctor(vault).issues
    assert all(p.read_bytes() == data for p,data in frozen.items())
