"""Structured source Provenance must survive the supported history workflow."""
import pytest

from helseark.archive import init_vault, add_person, commit_candidate, doctor, iter_current, head
from helseark.adapters.fhir_r4 import import_fhir_r4, IdentityMapping
from helseark.contracts import PersonDraft
from helseark.intake import add_source, prepare_candidate
from helseark.query import history
from helseark.serialization import encode_json, decode_json
from test_adapters import decision


@pytest.mark.parametrize('source_profile,target_kind', [
    (None, 'Condition'), ('0.2.0', 'Condition'), ('0.1.0', 'Condition'),
    ('0.1.0', 'DocumentReference'),
    (None, None),  # Isolate native attachment closure without Provenance.
])
def test_structured_provenance_preserves_native_target_through_review(tmp_path, source_profile, target_kind):
    vault = init_vault(tmp_path/'vault')
    person = add_person(vault, PersonDraft('Synthetic provenance patient'))
    original = tmp_path/'source.txt'
    original.write_text('Synthetic assertion: childhood condition was unconfirmed.\n')
    retained = add_source(vault, person, original)
    condition = {'resourceType':'Condition', 'id':'c1', 'subject':{'reference':'Patient/p1'},
                 'code':{'text':'Synthetic childhood condition'},
                 'verificationStatus':{'coding':[{'system':'http://terminology.hl7.org/CodeSystem/condition-ver-status',
                                                  'code':'unconfirmed'}]},
                 'onsetString':'Possibly childhood'}
    document = {'resourceType':'DocumentReference', 'id':'d1', 'status':'current',
                'subject':{'reference':'Patient/p1'}, 'content':[{'attachment':{
                    'url':f'assets/sha256/{retained.sourceSha256}/blob', 'contentType':retained.mediaType,
                    'size':retained.size, 'title':'Synthetic retained source'}}]}
    target = 'Condition/c1' if target_kind == 'Condition' else 'DocumentReference/d1'
    provenance = {'resourceType':'Provenance', 'id':'pr1', 'target':[{'reference':target}],
                  'recorded':'2026-01-01T00:00:00Z',
                  'agent':[{'who':{'identifier':{'system':'urn:synthetic:actor', 'value':'source-author'}}}],
                  'entity':[{'role':'source', 'what':{'reference':'DocumentReference/d1'}}]}
    if source_profile:
        provenance['meta'] = {'profile':[
            'https://github.com/ricardocabral/helseark/fhir/StructureDefinition/helseark-provenance|'+source_profile]}
    records = [{'resourceType':'Patient', 'id':'p1'}, document]
    if target_kind:
        records.append(provenance)
    if target_kind == 'Condition':
        records.append(condition)
    incoming = encode_json({'resourceType':'Bundle', 'type':'collection',
                            'entry':[{'resource':r} for r in records]})
    source = tmp_path/'native.json'; source.write_bytes(incoming)
    receipt = add_source(vault, person, source)
    candidate = import_fhir_r4(receipt, person, IdentityMapping(
        'Patient/p1', person, 'Explicit synthetic assignment', 'https://synthetic.example'))
    proposal = prepare_candidate(vault, candidate)
    commit_candidate(vault, proposal, decision(vault, proposal))
    accepted = list(history(vault, person, ['Condition'])) if target_kind == 'Condition' else list(iter_current(vault, person))
    if target_kind:
        imported = next(r for r in accepted if r['resourceType']=='Provenance' and r['agent'][0]['who'].get('identifier', {}).get('value') == 'source-author')
        assert imported['target'][0]['reference'].startswith(target_kind+'/')
        assert '/_history/' in imported['target'][0]['reference']
        assert imported['recorded'] == '2026-01-01T00:00:00Z'
        from helseark.archive import resolve
        from helseark.contracts import ResourceRef, ExportSelection
        from helseark.portability import export_person, verify_export
        kind, rid, _, version = imported['target'][0]['reference'].split('/')
        exact = resolve(vault, person, ResourceRef(kind, rid, version))
        assert exact['resourceType'] == target_kind
        if target_kind == 'Condition':
            from helseark.presentation import render_static_report
            from helseark.query import timeline
            rows = [r for r in timeline(vault, person) if r.resourceRef.resourceType=='Condition']
            assert len(rows)==1 and rows[0].sourceRefs
            assert exact['verificationStatus']['coding'][0]['code']=='unconfirmed'
            assert exact['onsetString']=='Possibly childhood'
            report = render_static_report(vault, person, tmp_path/'report')
            assert 'Synthetic childhood condition' in report.read_text()
            assert 'evidence.json#' in report.read_text()
            export_person(vault, person, tmp_path/'exchange', ExportSelection(
                'selected-current', (ResourceRef(kind,rid,version),
                                     ResourceRef('Provenance',imported['id'],imported['meta']['versionId'])), False))
            assert not verify_export(tmp_path/'exchange').issues
            exchanged = decode_json((tmp_path/'exchange/collection.json').read_bytes())
            native = next(e['resource'] for e in exchanged['entry']
                          if e['resource']['id']==imported['id'])
            assert native['target'][0]['reference']=='urn:uuid:'+version
            assert decode_json((tmp_path/'exchange/resources'/f"{version}.json").read_bytes())==exact
    assert not doctor(vault).issues
    assert receipt.assetPath.read_bytes() == incoming
    assert retained.assetPath.read_bytes() == original.read_bytes()


def test_history_reextraction_links_exact_prior_revision(tmp_path):
    from helseark.contracts import ResourceRef, ExportSelection, ArchiveError
    from helseark.portability import export_person, verify_export
    from helseark.presentation import render_static_report
    from helseark.serialization import hash_bytes

    vault = init_vault(tmp_path/'vault')
    person = add_person(vault, PersonDraft('Synthetic revision patient'))
    other = add_person(vault, PersonDraft('Synthetic revision patient'))
    incoming = encode_json({'resourceType':'Bundle', 'type':'collection', 'entry':[
        {'resource':{'resourceType':'Patient', 'id':'p1'}},
        {'resource':{'resourceType':'Condition', 'id':'c1',
                     'subject':{'reference':'Patient/p1'},
                     'code':{'text':'Synthetic uncertain childhood assertion'},
                     'verificationStatus':{'coding':[{
                         'system':'http://terminology.hl7.org/CodeSystem/condition-ver-status',
                         'code':'unconfirmed'}]}, 'onsetString':'Possibly childhood'}}]})
    path = tmp_path/'source.json'; path.write_bytes(incoming)
    source = add_source(vault, person, path)

    def candidate(reason):
        return import_fhir_r4(source, person, IdentityMapping(
            'Patient/p1', person, reason, 'https://synthetic.example'))

    first = prepare_candidate(vault, candidate('Initial explicit synthetic assignment'))
    commit_candidate(vault, first, decision(vault, first))
    initial_head = head(vault, person)
    old = next(r for r in history(vault, person, ['Condition']) if r['resourceType']=='Condition')
    old_ref = f"Condition/{old['id']}/_history/{old['meta']['versionId']}"
    frozen = {p: p.read_bytes() for p in (vault.root/'people'/person/'accepted').rglob('*') if p.is_file()}
    revised = prepare_candidate(vault, candidate('Rechecked explicit synthetic assignment'), reextract=True)
    assert head(vault, person) == initial_head
    # Diagnostic copies isolate reference checks; issued inputs and accepted bytes
    # stay untouched. None of these altered proposals is reviewed or published.
    import shutil
    from uuid import uuid4
    from helseark.serialization import decode_json
    from helseark.validation import validate_proposal
    metadata = decode_json((revised.path/'proposal.json').read_bytes())
    item = next(i for i in metadata['resources'] if i['type']=='Provenance')
    original_provenance = decode_json((revised.path/item['path']).read_bytes())
    revision_index = next(i for i,e in enumerate(original_provenance['entity'])
                          if e['role']=='revision' and e['what']['reference']==old_ref)
    adversaries = [
        ('versionless', revision_index, {'reference':old_ref.split('/_history/')[0]}, 'REVISION_REQUIRED'),
        ('unresolved', revision_index, {'reference':old_ref.rsplit('/',1)[0]+'/'+str(uuid4())}, 'REFERENCE_NOT_FOUND'),
        ('wrong-person', revision_index, {'reference':'Patient/'+other}, 'PERSON_MISMATCH'),
        ('wrong-type', revision_index, {'reference':old_ref, 'type':'DocumentReference'}, 'REFERENCE_TYPE_MISMATCH'),
        ('unsupported-type', revision_index, {'reference':'Organization/'+str(uuid4())+'/_history/'+str(uuid4())}, 'UNSUPPORTED_RESOURCE'),
        ('source-type', 0, {'reference':old_ref}, 'REFERENCE_TYPE_MISMATCH'),
    ]
    for name, index, what, code in adversaries:
        diagnostic = tmp_path/name
        shutil.copytree(revised.path, diagnostic)
        resource = decode_json(encode_json(original_provenance))
        resource['entity'][index]['what'] = what
        data = encode_json(resource)
        (diagnostic/item['path']).write_bytes(data)
        manifest = decode_json(encode_json(metadata))
        next(i for i in manifest['resources'] if i['path']==item['path'])['sha256'] = hash_bytes(data)
        (diagnostic/'proposal.json').write_bytes(encode_json(manifest))
        errors = [i for i in validate_proposal(vault, diagnostic).issues if i.severity=='error']
        assert any(i.code==code and i.pointer.startswith(f'/entity/{index}/what') for i in errors), errors
    assert all(p.read_bytes()==data for p,data in frozen.items())
    with pytest.raises(ArchiveError, match='REVIEW_REQUIRED'):
        commit_candidate(vault, revised, None)
    commit_candidate(vault, revised, decision(vault, revised))
    current = list(history(vault, person, ['Condition']))
    new = next(r for r in current if r['resourceType']=='Condition')
    assert new['id'] == old['id'] and new['meta']['versionId'] != old['meta']['versionId']
    assert new['onsetString'] == 'Possibly childhood'
    compiler = next(r for r in current if r['resourceType']=='Provenance')
    revisions = [e['what']['reference'] for e in compiler['entity'] if e['role']=='revision']
    assert old_ref in revisions
    assert f"Condition/{new['id']}/_history/{new['meta']['versionId']}" in [t['reference'] for t in compiler['target']]
    historical = next(r for r in history(vault, person, ['Condition'], at=initial_head) if r['resourceType']=='Condition')
    assert historical == old
    assert all(p.read_bytes() == data for p, data in frozen.items())
    assert source.assetPath.read_bytes() == incoming
    report = render_static_report(vault, person, tmp_path/'report')
    assert 'Synthetic uncertain childhood assertion' in report.read_text()
    from test_presentation import Page
    from urllib.parse import urlsplit, unquote
    from pathlib import Path
    from helseark.serialization import decode_json
    from helseark.validation import _pointer
    links = [urlsplit(link) for link in Page(report.read_text()).links if link.startswith('file:')]
    assert links
    for link in links:
        evidence_path = Path(unquote(link.path))
        assert evidence_path.is_relative_to(vault.root/'people'/person/'accepted')
        assert _pointer(decode_json(evidence_path.read_bytes()), link.fragment)
    export_person(vault, person, tmp_path/'exchange', ExportSelection(
        'selected-current', (ResourceRef('Condition',new['id']),
                             ResourceRef('Provenance',compiler['id'],compiler['meta']['versionId'])), False))
    assert not verify_export(tmp_path/'exchange').issues
    exchanged = decode_json((tmp_path/'exchange/collection.json').read_bytes())
    native = next(e['resource'] for e in exchanged['entry'] if e['resource']['id']==compiler['id'])
    assert 'urn:uuid:'+old['meta']['versionId'] in [e['what']['reference'] for e in native['entity'] if e['role']=='revision']
    assert decode_json((tmp_path/'exchange/resources'/f"{old['meta']['versionId']}.json").read_bytes())==old
    assert not doctor(vault).issues


@pytest.mark.parametrize('defect,expected', [
    ('other-person', 'SOURCE_MISSING'), ('missing', 'SOURCE_MISSING'),
    ('size', 'SOURCE_SIZE_MISMATCH'), ('profile', 'FHIR_UNHANDLED'),
])
def test_native_attachment_and_profile_controls(tmp_path, defect, expected):
    from helseark.contracts import ArchiveError
    from helseark.validation import validate_candidate

    vault = init_vault(tmp_path/'vault')
    person = add_person(vault, PersonDraft('Synthetic selected patient'))
    owner = add_person(vault, PersonDraft('Synthetic other patient')) if defect=='other-person' else person
    path = tmp_path/'attachment.txt'; path.write_text('Synthetic retained attachment.\n')
    attachment = add_source(vault, owner, path)
    digest = '0'*64 if defect=='missing' else attachment.sourceSha256
    document = {'resourceType':'DocumentReference', 'id':'d1', 'status':'current',
                'subject':{'reference':'Patient/p1'}, 'content':[{'attachment':{
                    'url':f'assets/sha256/{digest}/blob', 'contentType':attachment.mediaType,
                    'size':attachment.size+(1 if defect=='size' else 0), 'title':'Synthetic source'}}]}
    provenance = {'resourceType':'Provenance', 'id':'pr1',
                  'target':[{'reference':'DocumentReference/d1'}], 'recorded':'2026-01-01T00:00:00Z',
                  'agent':[{'who':{'identifier':{'value':'synthetic author'}}}],
                  'entity':[{'role':'source','what':{'reference':'DocumentReference/d1'}}]}
    if defect=='profile':
        provenance['meta']={'profile':[
            'https://github.com/ricardocabral/helseark/fhir/StructureDefinition/helseark-provenance|9.9.9']}
    path = tmp_path/'source.json'
    path.write_bytes(encode_json({'resourceType':'Bundle','type':'collection','entry':[
        {'resource':{'resourceType':'Patient','id':'p1'}}, {'resource':document}, {'resource':provenance}]}))
    source = add_source(vault, person, path)
    before = head(vault, person)
    frozen = {p:p.read_bytes() for p in (vault.root/'people').rglob('*') if p.is_file()}
    candidate = import_fhir_r4(source, person, IdentityMapping(
        'Patient/p1', person, 'Explicit synthetic assignment', 'https://synthetic.example'))
    errors = [i for i in validate_candidate(vault, candidate).issues if i.severity=='error']
    assert any(i.code==expected for i in errors), errors
    with pytest.raises(ArchiveError, match='VALIDATION_BLOCKED'):
        prepare_candidate(vault, candidate)
    assert head(vault, person)==before
    assert all(p.read_bytes()==data for p,data in frozen.items())


def test_native_report_attachment_is_in_prepared_inventory(tmp_path):
    from helseark.serialization import decode_json

    vault = init_vault(tmp_path/'vault')
    person = add_person(vault, PersonDraft('Synthetic report patient'))
    path = tmp_path/'report.txt'; path.write_text('Synthetic source report.\n')
    retained = add_source(vault, person, path)
    report = {'resourceType':'DiagnosticReport', 'id':'r1', 'status':'final',
              'code':{'text':'Synthetic source report'}, 'subject':{'reference':'Patient/p1'},
              'presentedForm':[{'contentType':retained.mediaType, 'size':retained.size,
                                'url':f'assets/sha256/{retained.sourceSha256}/blob'}]}
    path = tmp_path/'source.json'
    path.write_bytes(encode_json({'resourceType':'Bundle','type':'collection','entry':[
        {'resource':{'resourceType':'Patient','id':'p1'}}, {'resource':report}]}))
    source = add_source(vault, person, path)
    candidate = import_fhir_r4(source, person, IdentityMapping(
        'Patient/p1', person, 'Explicit synthetic assignment', 'https://synthetic.example'))
    proposal = prepare_candidate(vault, candidate)
    inventory = decode_json((proposal.path/'proposal.json').read_bytes())['assets']
    asset = next(a for a in inventory if a['sha256']==retained.sourceSha256)
    assert asset['mediaType']==retained.mediaType and asset['size']==retained.size
    commit_candidate(vault, proposal, decision(vault, proposal))
    assert not doctor(vault).issues
