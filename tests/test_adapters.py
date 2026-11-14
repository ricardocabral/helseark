"""Synthetic human decisions exercise publication; they are not clinical approval."""
from pathlib import Path
from dataclasses import replace
from decimal import Decimal
import pytest
from helseark.archive import init_vault, add_person, commit_candidate, resolve, head
from helseark.contracts import PersonDraft, ReviewDecision, ObservationFilter, ArchiveError, ResourceRef
from helseark.intake import add_source, prepare_candidate, read_candidate
from helseark.review import render_review, record_review
from helseark.query import observations
from helseark.serialization import decode_json, encode_json

FIXTURES = Path(__file__).parent/'fixtures/synthetic/structured'


def setup(tmp_path):
    v=init_vault(tmp_path/'vault'); p=add_person(v,PersonDraft('Synthetic Ada'))
    other=add_person(v,PersonDraft('Synthetic Ada'))
    return v,p,other


def decision(v, proposal):
    view=render_review(v,proposal)
    acks=tuple({'code':i['code'],'resourceRef':i['resourceRef'],
                'reason':'Pre-authored synthetic fixture decision; not real clinical approval.'}
               for i in view.issues if i['severity'] in ('review','warning'))
    acks=tuple({(a['code'],a['resourceRef']):a for a in acks}.values())
    return record_review(v,proposal,ReviewDecision(True,'accept-with-acknowledged-limitations',acks,'synthetic fixture human'))


def publish(v,c):
    proposal=prepare_candidate(v,c)
    return commit_candidate(v,proposal,decision(v,proposal))


def fhir(v,p,provider='https://provider-a.example/fhir',filename='r4.json'):
    from helseark.adapters.fhir_r4 import import_fhir_r4, IdentityMapping
    s=add_source(v,p,FIXTURES/filename)
    return s,import_fhir_r4(s,p,IdentityMapping('Patient/p1',p,'Synthetic fixture explicit assignment',provider))


def test_fhir_full_production_journey(tmp_path):
    v,p,other=setup(tmp_path); s,c=fhir(v,p)
    assert s.assetPath.read_bytes()==(FIXTURES/'r4.json').read_bytes()
    assert not [i for i in c.unresolved if i.severity=='error']
    result=publish(v,c)
    rows=list(observations(v,p,ObservationFilter()))
    assert len(rows)==1 and str(rows[0].value['value'])=='1.200'
    assert rows[0].status=='amended' and rows[0].sourceRefs
    r=resolve(v,p,rows[0].resourceRef)
    assert any(i['value']=='o1/_history/7' for i in r['identifier'])
    report=resolve(v,p,next(x for x in result.logicalResources if x.resourceType=='DiagnosticReport'))
    assert '/_history/' in report['result'][0]['reference']
    assert report['result'][0]['reference'].split('/')[1]==r['id']
    assert list(observations(v,other,ObservationFilter()))==[]
    for e in c.evidence['entries']:
        if e['kind']=='source': assert e['extraction']['method']=='json-pointer'
    with pytest.raises(ArchiveError,match='PERSON_MISMATCH'):
        read_candidate(v,c.path,person=other)


def test_fhir_cross_provider_equal_ids_and_values_distinct(tmp_path):
    v,p,_=setup(tmp_path);s,c=fhir(v,p);publish(v,c)
    # Different provider export bytes, same native IDs and exact measurement.
    raw=decode_json((FIXTURES/'r4.json').read_bytes());raw['identifier']={'system':'https://provider-b.example','value':'export'}
    path=tmp_path/'b.json';path.write_bytes(encode_json(raw))
    from helseark.adapters.fhir_r4 import import_fhir_r4,IdentityMapping
    c=import_fhir_r4(add_source(v,p,path),p,IdentityMapping('Patient/p1',p,'Explicit synthetic assignment','https://provider-b.example/fhir'))
    publish(v,c)
    rows=list(observations(v,p,ObservationFilter()))
    assert len(rows)==2 and rows[0].resourceRef.id!=rows[1].resourceRef.id


@pytest.mark.parametrize('mutation', ['unknown-patient','wrong-local','extension','resource','field','dangling','other-subject','duplicate-id'])
def test_fhir_mapping_and_unhandled_content_block(tmp_path,mutation):
    from helseark.adapters.fhir_r4 import import_fhir_r4,IdentityMapping
    v,p,other=setup(tmp_path);raw=decode_json((FIXTURES/'r4.json').read_bytes())
    mapping=IdentityMapping('Patient/p1',p,'Explicit synthetic assignment','https://provider-a.example/fhir')
    if mutation=='unknown-patient':mapping=replace(mapping,patientReference='Patient/missing')
    if mutation=='wrong-local':mapping=replace(mapping,localPersonId=other)
    obs=raw['entry'][1]['resource']
    if mutation=='extension':obs['extension']=[{'url':'https://example.test/unsupported','valueString':'retained'}]
    if mutation=='resource':raw['entry'].append({'resource':{'resourceType':'Medication','id':'m1','status':'active'}})
    if mutation=='field':obs['unhandled']='retained'
    if mutation=='dangling':raw['entry'][2]['resource']['result'][0]['reference']='Observation/missing'
    if mutation=='other-subject':obs['subject']['reference']='Patient/other'
    if mutation=='duplicate-id':raw['entry'].append(raw['entry'][1])
    path=tmp_path/'input.json';path.write_bytes(encode_json(raw));s=add_source(v,p,path);before=head(v,p)
    try:
        c=import_fhir_r4(s,p,mapping)
    except ArchiveError as e:
        assert e.code in ('IDENTITY_MAPPING_REQUIRED','PERSON_MISMATCH','AMBIGUOUS_REFERENCE');return
    assert any(i.severity=='error' for i in c.unresolved)
    assert (c.path/'coverage.json').exists()
    with pytest.raises(ArchiveError):prepare_candidate(v,c)
    assert head(v,p)==before and s.assetPath.read_bytes()==path.read_bytes()


def test_fhir_patient_extensions_and_nested_unhandled_inventory(tmp_path):
    from helseark.adapters.fhir_r4 import import_fhir_r4,IdentityMapping
    v,p,_=setup(tmp_path);raw=decode_json((FIXTURES/'r4.json').read_bytes())
    raw['entry'][0]['resource']['extension']=[{'url':'https://example.test/identity','valueString':'unknown'}]
    raw['entry'][1]['resource']['valueQuantity']['unhandled']='retained'
    path=tmp_path/'unsupported.json';path.write_bytes(encode_json(raw))
    c=import_fhir_r4(add_source(v,p,path),p,IdentityMapping('Patient/p1',p,'Synthetic assignment','https://provider.example/fhir'))
    assert any(i.severity=='error' and '/entry/0/resource/extension' in (i.pointer or '') for i in c.unresolved)
    coverage=decode_json((c.path/'coverage.json').read_bytes())
    assert any('unhandled' in str(i) for i in coverage['items'])


def test_fhir_source_and_scalar_evidence_resolve_after_commit(tmp_path):
    from helseark.validation import _pointer
    from helseark.archive import _history
    v,p,_=setup(tmp_path);s,c=fhir(v,p);publish(v,c)
    _,directory,_=_history(v,p)[-1]
    evidence=decode_json((directory/'evidence.json').read_bytes())
    for e in evidence['entries']:
        parts=e['target']['reference'].split('/')
        resource=resolve(v,p,ResourceRef(parts[0],parts[1],parts[3]))
        for pointer in e['target']['pointers']:_pointer(resource,pointer)
        if e['kind']!='source':continue
        assert _pointer(decode_json(s.assetPath.read_bytes()),e['locator']['pointer']) is not None
        parts=e['sourceDocument'].split('/')
        document=resolve(v,p,ResourceRef(parts[0],parts[1],parts[3]))
        assert document['content'][0]['attachment']['url']==f'assets/sha256/{s.sourceSha256}/blob'


def test_fhir_public_cli_creates_only_candidate(tmp_path):
    import subprocess,sys
    from helseark.agent_context import document
    from helseark.adapters.fhir_r4 import IdentityMapping
    v,p,_=setup(tmp_path);before=head(v,p)
    mapping=tmp_path/'mapping.json'
    mapping.write_bytes(encode_json(document(IdentityMapping('Patient/p1',p,'Synthetic explicit assignment','https://provider.example/fhir'))))
    result=subprocess.run([sys.executable,'-m','helseark.cli','--vault',str(v.root),'intake','fhir-r4',str(FIXTURES/'r4.json'),'--person',p,'--mapping',str(mapping),'--json'],capture_output=True)
    assert result.returncode==0,result.stderr
    candidate=read_candidate(v,Path(decode_json(result.stdout)['path']),person=p)
    assert candidate.bundle['entry'] and head(v,p)==before
