"""Behavioral Task 2 checks. All records and source bytes are synthetic."""
from dataclasses import replace, asdict
from decimal import Decimal
from pathlib import Path
import copy
import json
import socket
import subprocess
import sys
from uuid import uuid4

import pytest

from helseark.archive import init_vault, add_person, head
from helseark.contracts import Candidate, PersonDraft, ArchiveError, Issue
from helseark.serialization import encode_json, decode_json, hash_bytes

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/synthetic/validation'
BASE = 'https://github.com/ricardocabral/helseark/fhir/StructureDefinition/helseark-'
PERSON = '11111111-1111-4111-8111-111111111111'
OBS = '33333333-3333-4333-8333-333333333333'
DOC = '77777777-7777-4777-8777-777777777777'


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError('Runtime attempted networking')
    monkeypatch.setattr(socket, 'socket', refuse)
    monkeypatch.setattr(socket, 'create_connection', refuse)


def runtime():
    from helseark import validation
    return validation


def asset(vault, person, data):
    digest = hash_bytes(data)
    path = vault.root / 'people' / person / 'assets/sha256' / digest / 'blob'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return digest


def persist(candidate):
    (candidate.path / 'bundle.json').write_bytes(encode_json(candidate.bundle))
    (candidate.path / 'evidence.json').write_bytes(encode_json(candidate.evidence))
    metadata = {'contractVersion': '0.1.0', 'candidateId': candidate.candidateId,
                'personId': candidate.personId, 'baseChangeSha256': candidate.base.changeSha256,
                'fhirVersion': '4.0.1', 'profileVersion': '0.1.0',
                'sourceSha256': sorted({e['sourceSha256'] for e in candidate.evidence['entries'] if 'sourceSha256' in e}),
                'bundlePath': 'bundle.json', 'evidencePath': 'evidence.json',
                'producer': {'kind': 'external-agent', 'name': 'synthetic'},
                'unresolved': [asdict(i) for i in candidate.unresolved]}
    (candidate.path / 'candidate.json').write_bytes(encode_json(metadata))
    return candidate


def leaves(value, prefix=''):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from leaves(item, prefix + '/' + key.replace('~', '~0').replace('/', '~1'))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from leaves(item, prefix + '/' + str(i))
    else:
        yield prefix, value


@pytest.fixture
def good(tmp_path):
    vault = init_vault(tmp_path / 'vault')
    person = add_person(vault, PersonDraft('Synthetic Person A'))
    bundle = decode_json((FIXTURES / 'candidate-bundle.json').read_bytes())
    # Fixture identity is explicit, rewritten only to the separately created test vault.
    raw = encode_json(bundle).replace(PERSON.encode(), person.encode())
    bundle = decode_json(raw)
    source = (FIXTURES / 'source.json').read_bytes()
    digest = asset(vault, person, source)
    bundle['entry'][1]['resource']['content'][0]['attachment']['url'] = f'assets/sha256/{digest}/blob'
    entries = []
    for entry in bundle['entry']:
        resource = entry['resource']
        ref = entry['fullUrl']
        for pointer, value in leaves(resource):
            if pointer == '/resourceType':
                continue
            if pointer == '/id' or pointer.startswith('/meta/') or pointer.endswith('/url'):
                entries.append({'target': {'reference': ref, 'pointers': [pointer]},
                                'kind': 'generated', 'rule': 'archive-fixture-v1'})
            else:
                source_fields = {'/status': '/docStatus' if resource['resourceType']=='DocumentReference' else '/status',
                                 '/code/text':'/reportLabel' if resource['resourceType']=='DiagnosticReport' else '/label','/subject/reference':'/person','/effectiveDateTime':'/date',
                                 '/valueQuantity/value':'/result','/valueQuantity/comparator':'/result','/valueQuantity/unit':'/result',
                                 '/content/0/attachment/contentType':'/mediaType','/content/0/attachment/title':'/title','/result/0/reference':'/label'}
                source_pointer=source_fields[pointer]
                quote=decode_json(source)[source_pointer.removeprefix('/')]
                entries.append({'target': {'reference': ref, 'pointers': [pointer]}, 'kind': 'source',
                                'sourceSha256': digest, 'sourceDocument': 'urn:uuid:' + DOC,
                                'quote': quote,
                                'locator': {'kind': 'json-pointer', 'pointer': source_pointer}})
    evidence = {'contractVersion': '0.1.0', 'personId': person, 'entries': entries}
    path = tmp_path / 'candidate'
    path.mkdir()
    candidate = Candidate(path, str(uuid4()), person, head(vault, person), bundle, evidence, ())
    return vault, persist(candidate)


def codes(vault, candidate):
    persist(candidate)
    return {i.code for i in runtime().validate_candidate(vault, candidate).issues}


def observation(candidate):
    return candidate.bundle['entry'][0]['resource']


def test_good_candidate_baseline_coverage(good):
    vault, candidate = good
    report = runtime().validate_candidate(vault, candidate)
    assert not [i for i in report.issues if i.severity == 'error'], report
    coverage = {c.family: c.result for c in report.coverage}
    assert coverage['patient-reference-scope'] == 'passed'
    assert coverage['evidence'] == 'passed'
    assert coverage['terminology'] == 'not-checked'
    assert coverage['full-fhir'] == 'not-checked'


def test_wrong_person_child_is_rejected(good):
    v, c = good
    assert c.bundle['entry'][2]['resource']['subject']['reference']=='Patient/'+c.personId
    observation(c)['subject']['reference'] = 'Patient/' + str(uuid4())
    assert 'PERSON_MISMATCH' in codes(v, c)


def test_missing_child_subject_is_not_inherited(good):
    v, c = good
    del observation(c)['subject']
    assert 'SUBJECT_REQUIRED' in codes(v, c)


def test_value_and_absent_reason_conflict(good):
    v, c = good
    observation(c)['dataAbsentReason'] = {'text': 'Not performed'}
    assert 'FHIR_CHOICE_CONFLICT' in codes(v, c)


def test_unknown_modifier_extension_blocks_interpretation(good):
    v, c = good
    observation(c)['code']['modifierExtension'] = [{'url': 'urn:unknown', 'valueBoolean': True}]
    assert 'UNSUPPORTED_MODIFIER' in codes(v, c)


def test_reference_across_fhir_versions_rejected(good):
    v, c = good
    observation(c)['subject']['type'] = 'http://hl7.org/fhir/5.0/StructureDefinition/Patient'
    assert 'FHIR_VERSION_MISMATCH' in codes(v, c)


def test_no_network_for_remote_schema_reference(good):
    v, _ = good
    registry = runtime().load_definition_registry(v)
    with pytest.raises(ArchiveError, match='MISSING_DEFINITION'):
        registry.resolve('https://untrusted.invalid/remote-schema')
    with pytest.raises(ArchiveError, match='MISSING_DEFINITION'):
        registry.validate({'$schema': 'https://json-schema.org/draft/2020-12/schema',
                           '$ref': 'https://untrusted.invalid/remote-schema'}, {})


def test_missing_definition_is_explicit_error(good):
    v, _ = good
    path = v.root / 'definitions/definitions/runtime-core/4.0.1/hl7.fhir.r4.core.tgz'
    assert path.is_file()
    path.unlink()
    with pytest.raises(ArchiveError, match='MISSING_DEFINITION'):
        runtime().load_definition_registry(v)


def test_partial_date_preserved(good):
    v, c = good
    observation(c)['effectiveDateTime'] = '2026-11'
    before = encode_json(c.bundle)
    assert 'FHIR_TIME_INVALID' not in codes(v, c)
    assert encode_json(c.bundle) == before


def test_timestamp_without_offset_needs_review(good):
    v, c = good
    observation(c)['effectiveDateTime'] = '2026-11-10T10:30:00'
    assert 'DATE_TIMEZONE_UNKNOWN' in codes(v, c)
    report = runtime().validate_candidate(v, c)
    assert any(i.severity == 'error' and i.code == 'FHIR_TIME_INVALID' for i in report.issues)


def test_comparator_and_decimal_comma_preserved(good):
    v, c = good
    assert observation(c)['valueQuantity'] == {'value': Decimal('0.050'), 'comparator': '<', 'unit': 'mg/L'}
    entry = next(e for e in c.evidence['entries'] if e['target']['pointers'] == ['/valueQuantity/value'])
    entry.update(quote='<0,050 mg/L', locator={'kind': 'json-pointer', 'pointer': '/result'},
                 transformation={'rule': 'decimal-comma-v1'})
    assert not {'SOURCE_TOKEN_MISMATCH', 'EVIDENCE_QUOTE_MISMATCH'} & codes(v, c)
    observation(c)['valueQuantity']['value'] = Decimal('0.500')
    assert 'SOURCE_TOKEN_MISMATCH' in codes(v, c)


def test_range_text_does_not_become_unsupported_comparator(good):
    v, c = good
    observation(c)['referenceRange'] = [{'text': 'less than 5 mg/L'}]
    assert 'SIMPLE_QUANTITY_COMPARATOR' not in codes(v, c)
    observation(c)['referenceRange'] = [{'low': {'value': 5, 'comparator': '<'}}]
    assert 'SIMPLE_QUANTITY_COMPARATOR' in codes(v, c)


def test_source_hash_mismatch_blocks_acceptance(good):
    v, c = good
    digest = next(e['sourceSha256'] for e in c.evidence['entries'] if e['kind'] == 'source')
    (v.root / 'people' / c.personId / 'assets/sha256' / digest / 'blob').write_bytes(b'corrupted')
    assert 'SOURCE_HASH_MISMATCH' in codes(v, c)


def test_invalid_bbox_rejected(good):
    v, c = good
    entry = next(e for e in c.evidence['entries'] if e['kind'] == 'source')
    entry['locator'] = {'kind': 'pdf-page', 'page': 1, 'bbox': [Decimal('.8'), 0, Decimal('.2'), 1],
                        'coordinateSpace': 'displayed-cropbox-top-left-normalized', 'pageRotationApplied': 0}
    assert 'INVALID_BBOX' in codes(v, c)


def test_unknown_loinc_is_not_invented(good):
    v, c = good
    assert 'coding' not in observation(c)['code']
    observation(c)['code']['coding'] = [{'system': 'http://loinc.org', 'code': 'source-unknown'}]
    assert 'CODING_UNVERIFIED' in codes(v, c)
    assert observation(c)['code']['coding'][0]['code'] == 'source-unknown'


@pytest.mark.parametrize('mutation,expected', [
    (lambda o: o.update(status='approved'), 'FHIR_STATUS_INVALID'),
    (lambda o: o.pop('status'), 'FHIR_REQUIRED'),
    (lambda o: o.update(valueString='negative'), 'FHIR_CHOICE_CONFLICT'),
    (lambda o: o.update(implicitRules='urn:untrusted'), 'UNSUPPORTED_MODIFIER'),
    (lambda o: o.update(extension=[{'url': 'urn:unknown', 'valueString': 'x'}]), 'UNSUPPORTED_CONTENT'),
    (lambda o: o.update(valueSampledData={'origin': {'value': 0}, 'period': 1, 'dimensions': 1}), 'UNSUPPORTED_ELEMENT'),
    (lambda o: o.update(effectiveDateTime='2026-02-30'), 'FHIR_TIME_INVALID'),
    (lambda o: o['meta'].update(profile=['urn:wrong']), 'UNSUPPORTED_PROFILE'),
    (lambda o: o.update(hasMember=[{'reference': 'https://example.invalid/Observation/1'}]), 'INVALID_REFERENCE'),
    (lambda o: o.update(hasMember=[{'reference': 'urn:uuid:' + str(uuid4())}]), 'REFERENCE_NOT_FOUND'),
    (lambda o: o.update(method={}), 'FHIR_EMPTY'),
])
def test_fail_closed_boundaries(good, mutation, expected):
    v, c = good
    mutation(observation(c))
    assert expected in codes(v, c)


def test_evidence_pointer_and_field_coverage(good):
    v, c = good
    entry = next(e for e in c.evidence['entries'] if e['target']['pointers'] == ['/valueQuantity/value'])
    entry['target']['pointers'] = ['/missing']
    found = codes(v, c)
    assert {'EVIDENCE_POINTER_INVALID', 'EVIDENCE_MISSING'} <= found


def test_generated_evidence_cannot_cover_clinical_fact(good):
    v, c = good
    entry = next(e for e in c.evidence['entries'] if e['target']['pointers'] == ['/valueQuantity/value'])
    entry.clear()
    entry.update(target={'reference': 'urn:uuid:' + OBS, 'pointers': ['/valueQuantity/value']}, kind='generated', rule='invented')
    assert 'GENERATED_CLINICAL_EVIDENCE' in codes(v, c)


def test_candidate_unknown_envelope_field_and_version(good):
    v, c = good
    p = c.path / 'candidate.json'
    metadata = decode_json(p.read_bytes())
    metadata['unexpected'] = True
    p.write_bytes(encode_json(metadata))
    assert 'INVALID_ENVELOPE' in {i.code for i in runtime().validate_candidate(v, c).issues}
    del metadata['unexpected']
    metadata['fhirVersion'] = '5.0.0'
    p.write_bytes(encode_json(metadata))
    assert 'FHIR_VERSION_MISMATCH' in {i.code for i in runtime().validate_candidate(v, c).issues}


def test_unresolved_source_facts_are_preserved(good):
    v, c = good
    issue = Issue('SOURCE_CONTRADICTION', 'review', '/valueQuantity', 'urn:uuid:' + OBS,
                  'Synthetic source has contradictory values; human review required.')
    c = replace(c, unresolved=(issue,))
    persist(c)
    report = runtime().validate_candidate(v, c)
    assert issue in report.issues


def test_schema_export_contains_pinned_offline_runtime(good, tmp_path):
    v, _ = good
    out = runtime().schema_packet(v, ['Observation'], tmp_path / 'packet')
    assert (out / 'definitions/lock.json').read_bytes() == (v.root / 'definitions/lock.json').read_bytes()
    assert (out / 'profiles/r4/0.1.0/StructureDefinition-helseark-observation.json').is_file()
    assert (out / 'definitions/runtime-core/4.0.1/hl7.fhir.r4.core.tgz').is_file()
    assert runtime().load_definition_registry(v).resolve('http://hl7.org/fhir/StructureDefinition/SimpleQuantity')['id']=='SimpleQuantity'
    assert (out / 'schemas/0.1.0/candidate.schema.json').is_file()
    assert not runtime().load_definition_registry(v).validate('urn:helseark:schema:0.1.0:evidence', {'unexpected': True})


def prepare(vault, candidate, tmp_path):
    """Independent test-only preparation; Task 6 owns production compilation."""
    from helseark.archive import _versions
    path = tmp_path / 'prepared'
    path.mkdir()
    bundle = copy.deepcopy(candidate.bundle)
    mapping = {}
    resources = []
    for entry in bundle['entry']:
        r = entry['resource']
        version = str(uuid4())
        r['meta'].update(versionId=version, lastUpdated='2026-11-14T12:00:00Z')
        mapping[entry['fullUrl']] = f"{r['resourceType']}/{r['id']}/_history/{version}"
        content = encode_json(r)
        filename = f"resources/{r['resourceType']}-{r['id']}.json"
        target = path / filename
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(content)
        resources.append({'type':r['resourceType'],'id':r['id'],'versionId':version,
                          'path':filename,'sha256':hash_bytes(content),'supersedesVersionId':None})
    # Rewrite only the complete known candidate mapping into immutable references.
    for entry,item in zip(bundle['entry'],resources):
        r=entry['resource']
        for _,node in walk_for_test(r):
            if isinstance(node,dict) and node.get('reference') in mapping:
                node['reference']=mapping[node['reference']]
        content=encode_json(r)
        (path/item['path']).write_bytes(content);item['sha256']=hash_bytes(content)
    evidence = copy.deepcopy(candidate.evidence)
    for entry in evidence['entries']:
        entry['target']['reference'] = mapping[entry['target']['reference']]
        if 'sourceDocument' in entry:
            entry['sourceDocument'] = mapping[entry['sourceDocument']]
    # Preparation adds evidence for archive metadata without fabricating quotes.
    for entry in bundle['entry']:
        r=entry['resource']
        evidence['entries'].append({'target':{'reference':mapping[entry['fullUrl']],
                                              'pointers':['/meta/versionId','/meta/lastUpdated']},
                                     'kind':'generated','rule':'archive-revision-v1'})
    evidence_bytes=encode_json(evidence)
    (path/'evidence.json').write_bytes(evidence_bytes)
    digests=sorted({e['sourceSha256'] for e in evidence['entries'] if 'sourceSha256' in e})
    proposal={'contractVersion':'0.1.0','personId':candidate.personId,'transactionId':str(uuid4()),
              'kind':'import','unresolved':[asdict(i) for i in candidate.unresolved],'candidateSha256':hash_bytes((candidate.path/'candidate.json').read_bytes()),
              'baseChangeSha256':candidate.base.changeSha256,'versions':_versions(vault),
              'resources':resources,'assets':[{'sha256':d,'size':len((vault.root/'people'/candidate.personId/'assets/sha256'/d/'blob').read_bytes()),
                  'mediaType':'application/json','path':f'assets/sha256/{d}/blob'} for d in digests],
              'evidenceSha256':hash_bytes(evidence_bytes)}
    (path/'proposal.json').write_bytes(encode_json(proposal))
    return path


def test_prepared_proposal_digest_and_bytes(good, tmp_path):
    v,c=good
    path=prepare(v,c,tmp_path)
    report=runtime().validate_proposal(v,path)
    assert report.checkedProposalSha256 == hash_bytes((path/'proposal.json').read_bytes())
    assert not [i for i in report.issues if i.severity=='error'], report
    r=next((path/'resources').iterdir())
    resource=decode_json(r.read_bytes())
    resource['status']='entered-in-error'
    r.write_bytes(encode_json(resource))
    assert 'RESOURCE_HASH_MISMATCH' in {i.code for i in runtime().validate_proposal(v,path).issues}


def test_prepared_proposal_wrong_person(good, tmp_path):
    v,c=good
    observation(c)['subject']['reference']='Patient/'+str(uuid4())
    path=prepare(v,c,tmp_path)
    assert 'PERSON_MISMATCH' in {i.code for i in runtime().validate_proposal(v,path).issues}


def test_proposal_requires_exact_nonpatient_references(good, tmp_path):
    v,c=good
    observation(c)['derivedFrom']=[{'reference':'DocumentReference/'+DOC}]
    path=prepare(v,c,tmp_path)
    assert 'REVISION_REQUIRED' in {i.code for i in runtime().validate_proposal(v,path).issues}


def test_unsupported_schema_dialect(good):
    v,_=good
    with pytest.raises(ArchiveError,match='UNSUPPORTED_DIALECT'):
        runtime().load_definition_registry(v).validate({'$schema':'urn:unknown'}, {})


def test_source_quote_must_resolve_to_retained_bytes(good):
    v,c=good
    entry=next(e for e in c.evidence['entries'] if e['kind']=='source')
    entry['quote']='not in source'
    assert 'EVIDENCE_QUOTE_MISMATCH' in codes(v,c)


def test_text_span_uses_unicode_codepoint_offsets(good):
    v,c=good
    text='é β Synthetic Person A ✓'
    digest=asset(v,c.personId,text.encode())
    entry=next(e for e in c.evidence['entries'] if e['kind']=='source')
    entry['quote']='Synthetic Person A'
    entry['locator']={'kind':'text-span','extractionSha256':digest,'start':4,'end':22}
    assert 'EVIDENCE_QUOTE_MISMATCH' not in codes(v,c)
    entry['locator']['end']=500
    assert 'EVIDENCE_LOCATOR_INVALID' in codes(v,c)


def test_pdf_page_and_rotation_checked_against_retained_extraction(good):
    v,c=good
    entry=next(e for e in c.evidence['entries'] if e['kind']=='source')
    pages={'sourceSha256':entry['sourceSha256'],'pages':[{'page':1,'rotation':90,'text':'Synthetic Person A'}]}
    digest=asset(v,c.personId,encode_json(pages))
    entry['quote']='Synthetic Person A'
    entry['locator']={'kind':'pdf-page','extractionSha256':digest,'page':1,'pageRotationApplied':90,
                      'coordinateSpace':'displayed-cropbox-top-left-normalized','bbox':[0,0,1,1]}
    assert 'EVIDENCE_LOCATOR_INVALID' not in codes(v,c)
    entry['locator']['page']=2
    assert 'EVIDENCE_LOCATOR_INVALID' in codes(v,c)


def test_source_asset_symlink_rejected(good,tmp_path):
    v,c=good
    digest=next(e['sourceSha256'] for e in c.evidence['entries'] if e['kind']=='source')
    path=v.root/'people'/c.personId/'assets/sha256'/digest/'blob'
    outside=tmp_path/'outside';outside.write_bytes(path.read_bytes())
    path.unlink();path.symlink_to(outside)
    assert 'SOURCE_MISSING' in codes(v,c)


def test_schema_export_cli_offline(good,tmp_path):
    v,_=good
    import os
    # A subprocess audit hook blocks socket construction, DNS and connections.
    guard=tmp_path/'guard';guard.mkdir()
    (guard/'sitecustomize.py').write_text("import sys\ndef deny(event,args):\n if event.startswith('socket.'): raise RuntimeError('network attempted')\nsys.addaudithook(deny)\n")
    env={**os.environ,'PYTHONPATH':str(guard)+os.pathsep+str(ROOT/'src')}
    out=tmp_path/'cli-packet'
    result=subprocess.run([sys.executable,'-m','helseark.cli','--vault',str(v.root),
                           'schema','export','--resource','Observation','--out',str(out),'--json'],
                          env=env,capture_output=True)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['path']==str(out)
    assert (out/'definitions/lock.json').is_file()


def test_cli_good_candidate_and_wrong_person_failure(good,tmp_path):
    import os
    v,c=good
    env={**os.environ,'PYTHONPATH':str(ROOT/'src')}
    args=[sys.executable,'-m','helseark.cli','--vault',str(v.root),'validate','candidate',
          str(c.path),'--person',c.personId,'--json']
    result=subprocess.run(args,env=env,capture_output=True)
    assert result.returncode==0,result.stderr
    assert not [i for i in json.loads(result.stdout)['issues'] if i['severity']=='error']
    observation(c)['subject']['reference']='Patient/'+str(uuid4());persist(c)
    result=subprocess.run(args,env=env,capture_output=True)
    assert result.returncode==2,result.stderr
    assert 'PERSON_MISMATCH' in {i['code'] for i in json.loads(result.stdout)['issues']}
    args[args.index('--person')+1]=str(uuid4())
    result=subprocess.run(args,env=env,capture_output=True)
    assert result.returncode==2
    assert b'Synthetic' not in result.stderr


def test_primitive_extensions_fail_closed_at_nested_depth(good):
    v,c=good
    observation(c)['valueQuantity']['_value']={'extension':[{'url':'urn:unknown','valueString':'unknown'}]}
    assert 'UNSUPPORTED_CONTENT' in codes(v,c)


def test_source_clock_without_offset_retained_as_text_needs_review(good):
    v,c=good
    entry=next(e for e in c.evidence['entries'] if e['target']['pointers']==['/effectiveDateTime'])
    entry.update(quote='2026-11-10 10:30 (timezone not stated)',locator={'kind':'json-pointer','pointer':'/timezone'})
    assert 'DATE_TIMEZONE_UNKNOWN' in codes(v,c)
    assert observation(c)['effectiveDateTime']=='2026-11'


def test_observation_coding_overlap_conflicts_with_root_value(good):
    v,c=good
    observation(c)['code']['coding']=[{'system':'urn:source','code':'same','display':'label A'}]
    observation(c)['component']=[{'code':{'coding':[{'system':'urn:source','code':'same','display':'label B'}]},'valueInteger':1}]
    assert 'OBS_7_CONFLICT' in codes(v,c)


def test_failed_envelope_does_not_claim_unexecuted_checks_passed(good):
    v,c=good
    (c.path/'candidate.json').write_bytes(encode_json({'unknown':True}))
    report=runtime().validate_candidate(v,c)
    coverage={c.family:c.result for c in report.coverage}
    assert coverage['local-envelopes']=='failed'
    assert coverage['patient-reference-scope']=='not-checked'


def test_prepared_assets_bind_attachment_media_type(good,tmp_path):
    v,c=good
    path=prepare(v,c,tmp_path)
    proposal=decode_json((path/'proposal.json').read_bytes())
    proposal['assets'][0]['mediaType']='image/png'
    (path/'proposal.json').write_bytes(encode_json(proposal))
    assert 'SOURCE_MEDIA_TYPE_MISMATCH' in {i.code for i in runtime().validate_proposal(v,path).issues}


def test_prepared_extraction_must_be_in_asset_inventory(good,tmp_path):
    v,c=good
    digest=asset(v,c.personId,b'Synthetic Person A')
    entry=next(e for e in c.evidence['entries'] if e['kind']=='source')
    entry['quote']='Synthetic Person A'
    entry['locator']={'kind':'text-span','extractionSha256':digest,'start':0,'end':18}
    path=prepare(v,c,tmp_path)
    assert 'SOURCE_NOT_DECLARED' in {i.code for i in runtime().validate_proposal(v,path).issues}


def test_source_expected_facts_are_independent_and_exact(good):
    v,c=good
    facts=json.loads((ROOT/'tests/fixtures/expected/validation-facts.json').read_text())['facts']
    before=encode_json(c.bundle)
    report=runtime().validate_candidate(v,c)
    assert not [i for i in report.issues if i.severity=='error']
    o=observation(c)
    assert str(o['valueQuantity']['value'])==facts['numericValue']
    assert o['valueQuantity']['comparator']==facts['comparator']
    assert o['valueQuantity']['unit']==facts['unit']
    assert o['effectiveDateTime']==facts['effectiveDateTime']
    assert o['code']['text']==facts['label']
    assert encode_json(c.bundle)==before


def test_malformed_proposal_returns_report(good,tmp_path):
    v,_=good
    path=tmp_path/'bad';path.mkdir();(path/'proposal.json').write_bytes(b'{')
    report=runtime().validate_proposal(v,path)
    assert any(i.severity=='error' for i in report.issues)


def test_prepared_references_cannot_use_candidate_urns(good,tmp_path):
    v,c=good
    path=prepare(v,c,tmp_path)
    p=decode_json((path/'proposal.json').read_bytes())
    item=p['resources'][0]
    r=decode_json((path/item['path']).read_bytes())
    docversion=p['resources'][1]['versionId']
    r['derivedFrom']=[{'reference':'urn:uuid:'+docversion}]
    content=encode_json(r);(path/item['path']).write_bytes(content);item['sha256']=hash_bytes(content)
    (path/'proposal.json').write_bytes(encode_json(p))
    assert 'REVISION_REQUIRED' in {i.code for i in runtime().validate_proposal(v,path).issues}


def test_full_genuine_core_is_installed_and_resolves_beyond_bounded_subset(good):
    v,_=good
    registry=runtime().load_definition_registry(v)
    element=registry.resolve('http://hl7.org/fhir/StructureDefinition/ElementDefinition|4.0.1')
    assert element['resourceType']=='StructureDefinition'
    assert element['url']=='http://hl7.org/fhir/StructureDefinition/ElementDefinition'
    core=v.root/'definitions/definitions/runtime-core/4.0.1/hl7.fhir.r4.core.tgz'
    assert hash_bytes(core.read_bytes())=='b090bf929e1f665cf2c91583720849695bc38d2892a7c5037c56cb00817fb091'


def test_unresolved_identity_is_fatal_even_if_producer_labels_review(good):
    v,c=good
    c=replace(c,unresolved=(Issue('PERSON_MISMATCH','review',None,None,'Synthetic source identity is unresolved.'),))
    persist(c)
    assert any(i.code=='PERSON_MISMATCH' and i.severity=='error' for i in runtime().validate_candidate(v,c).issues)


def test_proposal_preserves_unresolved_source_facts(good,tmp_path):
    v,c=good
    c=replace(c,unresolved=(Issue('SOURCE_CONTRADICTION','review',None,None,'Synthetic source values conflict.'),))
    path=prepare(v,c,tmp_path)
    assert any(i.code=='SOURCE_CONTRADICTION' for i in runtime().validate_proposal(v,path).issues)


def test_full_clinical_corpus_runtime_and_independent_facts(good):
    v,c=good
    profile_fixtures=ROOT/'tests/fixtures/synthetic/profiles'
    bundle=decode_json((profile_fixtures/'collection.json').read_bytes())
    old_person=bundle['entry'][0]['resource']['id']
    bundle=decode_json(encode_json(bundle).replace(old_person.encode(),c.personId.encode()))
    mapping={f"{e['resource']['resourceType']}/{e['resource']['id']}/_history/{e['resource']['meta']['versionId']}":
             'urn:uuid:'+e['resource']['id'] for e in bundle['entry']}
    for e in bundle['entry']:
        r=e['resource']
        del r['meta']['versionId'];del r['meta']['lastUpdated']
        e['fullUrl']='urn:uuid:'+r['id']
        for _,node in walk_for_test(r):
            if isinstance(node,dict) and 'reference' in node and node['reference'] in mapping:
                node['reference']=mapping[node['reference']]
    source=(FIXTURES/'corpus-source.txt').read_bytes()
    digest=asset(v,c.personId,source)
    extraction=asset(v,c.personId,source)
    doc=next(e for e in bundle['entry'] if e['resource']['resourceType']=='DocumentReference')
    doc['resource']['content'][0]['attachment']['url']=f'assets/sha256/{digest}/blob'
    evidence=[]
    for e in bundle['entry']:
        for pointer,value in leaves(e['resource']):
            if pointer=='/resourceType': continue
            base={'target':{'reference':e['fullUrl'],'pointers':[pointer]}}
            if pointer=='/id' or pointer.startswith('/meta/') or pointer.endswith('/attachment/url'):
                base.update(kind='generated',rule='synthetic-archive-fixture')
            else:
                base.update(kind='source',sourceSha256=digest,sourceDocument=doc['fullUrl'],
                            quote=source.decode(),locator={'kind':'text-span','extractionSha256':extraction,
                                                          'start':0,'end':len(source.decode())})
            evidence.append(base)
    c=replace(c,bundle=bundle,evidence={'contractVersion':'0.1.0','personId':c.personId,'entries':evidence},
              unresolved=(Issue('SOURCE_CONTRADICTION','review',None,None,'Synthetic rows 2.0 and 3.0 remain unresolved.'),
                          Issue('DATE_TIMEZONE_UNKNOWN','review',None,None,'Synthetic local clock retained as text.')))
    persist(c)
    before=encode_json(c.bundle)
    report=runtime().validate_candidate(v,c)
    assert not [i for i in report.issues if i.severity=='error'], report
    expected=decode_json((profile_fixtures/'expected-facts.json').read_bytes())['observations']
    observations={e['resource']['code']['text']:e['resource'] for e in bundle['entry'] if e['resource']['resourceType']=='Observation'}
    for name, fields in expected.items():
        for field,value in fields.items():
            assert observations[name][field]==value
    exact=observations['Exact synthetic concentration']['valueQuantity']['value']
    assert str(exact)=='1.234567890123456789012345678900'
    assert str(observations['Trace analyte']['valueQuantity']['value'])=='0.0500'
    assert encode_json(c.bundle)==before
    assert {'CODING_UNVERIFIED','SOURCE_CONTRADICTION','DATE_TIMEZONE_UNKNOWN'} <= {i.code for i in report.issues}


def walk_for_test(value):
    yield '',value
    if isinstance(value,dict):
        for key,item in value.items():
            yield from walk_for_test(item)
    elif isinstance(value,list):
        for item in value:
            yield from walk_for_test(item)


def test_base_target_profile_is_checked_for_every_reference(good):
    v,c=good
    observation(c)['performer']=[{'reference':'urn:uuid:'+DOC}]
    assert 'REFERENCE_TYPE_MISMATCH' in codes(v,c)


def test_zero_ratio_and_reversed_ranges_fail(good):
    v,c=good
    o=observation(c);del o['valueQuantity']
    o['valueRatio']={'numerator':{'value':1},'denominator':{'value':0}}
    assert 'RATIO_ZERO_DENOMINATOR' in codes(v,c)
    del o['valueRatio'];o['valueRange']={'low':{'value':5,'unit':'mm'},'high':{'value':2,'unit':'mm'}}
    assert 'RANGE_ORDER_INVALID' in codes(v,c)


def test_provenance_source_and_actor_requirements(good):
    v,c=good
    r={'resourceType':'Provenance','id':str(uuid4()),'meta':{'profile':[BASE+'provenance|0.1.0']},
       'target':[{'reference':'urn:uuid:'+OBS}],'recorded':'2026-11-14T12:00:00Z',
       'agent':[{'who':{'display':'not an identified actor'}}]}
    c.bundle['entry'].append({'fullUrl':'urn:uuid:'+r['id'],'resource':r})
    assert {'PROVENANCE_SOURCE_REQUIRED','PROVENANCE_ACTOR_REQUIRED'} <= codes(v,c)
    r['agent'][0]['who']={'identifier':{'system':'urn:synthetic-local','value':'owner'}}
    r['entity']=[{'role':'source','what':{'reference':'urn:uuid:'+OBS}}]
    assert 'REFERENCE_TYPE_MISMATCH' in codes(v,c)


def test_candidate_root_symlink_is_rejected(good,tmp_path):
    v,c=good
    link=tmp_path/'linked';link.symlink_to(c.path,target_is_directory=True)
    report=runtime().validate_candidate(v,replace(c,path=link))
    assert 'UNSAFE_PATH' in {i.code for i in report.issues}


def test_schema_export_without_vault_uses_installed_pins(tmp_path):
    import os
    env={k:v for k,v in os.environ.items() if k!='HELSEARK_VAULT'}
    env['PYTHONPATH']=str(ROOT/'src')
    out=tmp_path/'standalone-schema'
    result=subprocess.run([sys.executable,'-m','helseark.cli','schema','export','--resource','Observation','--out',str(out),'--json'],
                          capture_output=True,env=env)
    assert result.returncode==0,result.stderr
    assert (out/'definitions/lock.json').is_file()


def test_source_size_is_bounded_before_reading(good):
    v,c=good
    digest=next(e['sourceSha256'] for e in c.evidence['entries'] if e['kind']=='source')
    path=v.root/'people'/c.personId/'assets/sha256'/digest/'blob'
    with path.open('r+b') as stream: stream.truncate(100*1024*1024+1)
    assert 'SOURCE_LIMIT' in codes(v,c)


def test_malformed_resource_does_not_claim_profile_checks_passed(good):
    v,c=good
    observation(c)['meta']='malformed'
    report=runtime().validate_candidate(v,persist(c))
    assert {i.code for i in report.issues} & {'FHIR_SCHEMA_INVALID','INVALID_ENVELOPE'}
    assert next(x for x in report.coverage if x.family=='supported-profile-rules').result!='passed'


def test_container_decimal_transformation_checks_its_numeric_leaves(good):
    v,c=good
    entry=next(e for e in c.evidence['entries'] if e['target']['pointers']==['/valueQuantity/value'])
    entry['target']['pointers']=['/valueQuantity']
    entry['transformation']={'rule':'decimal-comma-v1'}
    observation(c)['valueQuantity']['value']=Decimal('9.990')
    assert 'SOURCE_TOKEN_MISMATCH' in codes(v,c)


def test_proposal_cli_stale_base_exit_four(good,tmp_path):
    v,c=good
    path=prepare(v,c,tmp_path)
    p=decode_json((path/'proposal.json').read_bytes());p['baseChangeSha256']='a'*64
    (path/'proposal.json').write_bytes(encode_json(p))
    result=subprocess.run([sys.executable,'-m','helseark.cli','--vault',str(v.root),'validate','proposal',
                           str(path),'--person',c.personId,'--json'],capture_output=True)
    assert result.returncode==4,result.stderr


def test_meta_source_semantics_cannot_be_generated_bookkeeping(good):
    v,c=good
    observation(c)['meta']['security']=[{'system':'urn:source','code':'confidential'}]
    assert 'UNSUPPORTED_ELEMENT' in codes(v,c)


def test_prepared_evidence_targets_exact_revisions(good,tmp_path):
    v,c=good
    path=prepare(v,c,tmp_path)
    evidence=decode_json((path/'evidence.json').read_bytes())
    evidence['entries'][0]['target']['reference']='Observation/'+OBS
    data=encode_json(evidence);(path/'evidence.json').write_bytes(data)
    p=decode_json((path/'proposal.json').read_bytes());p['evidenceSha256']=hash_bytes(data)
    (path/'proposal.json').write_bytes(encode_json(p))
    assert 'EVIDENCE_TARGET_INVALID' in {i.code for i in runtime().validate_proposal(v,path).issues}
