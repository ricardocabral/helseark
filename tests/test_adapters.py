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


def csv_mapping(p, **kw):
    from helseark.adapters.csv_metrics import CsvMetricMapping
    return CsvMetricMapping(';','utf-8-sig','date','value','unit','code','%d/%m/%Y',',',p,
                            'Synthetic explicit assignment',**kw)


def test_csv_full_production_journey_duplicates_and_inert_labels(tmp_path):
    from helseark.adapters.csv_metrics import import_metrics_csv
    from helseark.archive import _history
    from helseark.validation import _pointer
    import csv,io
    v,p,other=setup(tmp_path);s=add_source(v,p,FIXTURES/'metrics.csv')
    c=import_metrics_csv(s,p,csv_mapping(p));publish(v,c)
    rows=list(observations(v,p,ObservationFilter()))
    assert len(rows)==3 and len({r.resourceRef.id for r in rows})==3
    assert [str(r.value['value']) for r in rows].count('0.0500')==2
    assert all(r.status=='unknown' for r in rows)
    assert any(r.code['text']=='=HYPERLINK("https://invalid.example")' for r in rows)
    assert list(observations(v,other,ObservationFilter()))==[]
    assert s.assetPath.read_bytes()==(FIXTURES/'metrics.csv').read_bytes()
    _,directory,_=_history(v,p)[-1]
    evidence=decode_json((directory/'evidence.json').read_bytes())
    source_rows=list(csv.DictReader(io.StringIO(s.assetPath.read_bytes().decode('utf-8-sig')),delimiter=';'))
    for e in evidence['entries']:
        parts=e['target']['reference'].split('/')
        r=resolve(v,p,ResourceRef(parts[0],parts[1],parts[3]))
        for pointer in e['target']['pointers']:_pointer(r,pointer)
        if e['kind']!='source':continue
        loc=e['locator'];assert loc['kind']=='csv-cell'
        assert e['quote']==source_rows[loc['row']-1][loc['column']]
        assert e['extraction']['method']=='csv-cell' and e['extraction']['tool']=='python.csv'
        parts=e['sourceDocument'].split('/')
        doc=resolve(v,p,ResourceRef(parts[0],parts[1],parts[3]))
        assert doc['content'][0]['attachment']['url']==f'assets/sha256/{s.sourceSha256}/blob'


@pytest.mark.parametrize('case',['missing-column','extra-column','duplicate-header','ragged','decimal','encoding','no-mapping','wrong-person'])
def test_csv_unknown_mapping_and_unsupported_data_block(tmp_path,case):
    from helseark.adapters.csv_metrics import import_metrics_csv
    v,p,other=setup(tmp_path);mapping=csv_mapping(p)
    data=b'date;value;unit;code\n01/02/2026;1,200;mg/L;Q\n'
    if case=='missing-column':mapping=replace(mapping,valueColumn='missing')
    if case=='extra-column':data=b'date;value;unit;code;unknown\n01/02/2026;1,200;mg/L;Q;retained\n'
    if case=='duplicate-header':data=b'date;value;unit;code;code\n01/02/2026;1,200;mg/L;Q;other\n'
    if case=='ragged':data+=b'01/02/2026;2,0;mg/L;Q;extra\n'
    if case=='decimal':data=data.replace(b'1,200',b'1.200')
    if case=='encoding':mapping=replace(mapping,encoding='utf-16')
    if case=='no-mapping':mapping=None
    if case=='wrong-person':mapping=replace(mapping,localPersonId=other)
    path=tmp_path/'metrics.csv';path.write_bytes(data);s=add_source(v,p,path);before=head(v,p)
    try:c=import_metrics_csv(s,p,mapping)
    except ArchiveError as e:
        assert e.code in ('CSV_MAPPING_REQUIRED','CSV_INPUT_INVALID','PERSON_MISMATCH');return
    assert any(i.severity=='error' for i in c.unresolved)
    assert decode_json((c.path/'coverage.json').read_bytes())['items']
    with pytest.raises(ArchiveError):prepare_candidate(v,c)
    assert head(v,p)==before and s.assetPath.read_bytes()==data


@pytest.mark.parametrize('stamp,zone,code',[
 ('01/11/2026 01:30:00','America/New_York','CSV_TIME_AMBIGUOUS'),
 ('08/03/2026 02:30:00','America/New_York','CSV_TIME_NONEXISTENT'),
 ('02/02/2026 12:30:00',None,'CSV_TIMEZONE_REQUIRED'),
])
def test_csv_uncertain_local_clocks_block(tmp_path,stamp,zone,code):
    from helseark.adapters.csv_metrics import import_metrics_csv
    v,p,_=setup(tmp_path);path=tmp_path/'clock.csv';path.write_text('date;value;unit;code\n'+stamp+';1,200;mg/L;Q\n')
    mapping=replace(csv_mapping(p,timezone=zone),dateFormat='%d/%m/%Y %H:%M:%S')
    c=import_metrics_csv(add_source(v,p,path),p,mapping)
    assert code in {i.code for i in c.unresolved if i.severity=='error'}
    with pytest.raises(ArchiveError):prepare_candidate(v,c)


def test_csv_declared_timezone_and_utf16(tmp_path):
    from helseark.adapters.csv_metrics import import_metrics_csv
    v,p,_=setup(tmp_path);path=tmp_path/'utf16.csv'
    path.write_bytes('date;value;unit;code\n02/02/2026 12:30:00;-0,0000;µg/L;Q\n'.encode('utf-16'))
    mapping=replace(csv_mapping(p,timezone='UTC'),encoding='utf-16',dateFormat='%d/%m/%Y %H:%M:%S')
    c=import_metrics_csv(add_source(v,p,path),p,mapping);publish(v,c)
    row=list(observations(v,p,ObservationFilter()))[0]
    assert row.effective=='2026-02-02T12:30:00+00:00' and str(row.value['value'])=='-0.0000' and row.unit=='µg/L'


def test_csv_public_cli_and_real_human_confirmation_required(tmp_path):
    import subprocess,sys
    from helseark.agent_context import document
    v,p,_=setup(tmp_path);before=head(v,p)
    mapping=tmp_path/'mapping.json';mapping.write_bytes(encode_json(document(csv_mapping(p))))
    result=subprocess.run([sys.executable,'-m','helseark.cli','--vault',str(v.root),'intake','metrics-csv',str(FIXTURES/'metrics.csv'),'--person',p,'--mapping',str(mapping),'--json'],capture_output=True)
    assert result.returncode==0,result.stderr
    candidate=read_candidate(v,Path(decode_json(result.stdout)['path']),person=p)
    assert head(v,p)==before
    proposal=prepare_candidate(v,candidate)
    with pytest.raises(ArchiveError,match='REVIEW_REQUIRED'):
        record_review(v,proposal,ReviewDecision(False,'accept',(),'not-confirmed'))
    with pytest.raises(ArchiveError):commit_candidate(v,proposal,None)
    assert head(v,p)==before


@pytest.mark.parametrize('text,fmt,expected', [('2026','%Y','2026'),('2026-02','%Y-%m','2026-02'),('2026-02-01T10:00:00-0300','%Y-%m-%dT%H:%M:%S%z','2026-02-01T10:00:00-03:00')])
def test_csv_explicit_time_precision(tmp_path,text,fmt,expected):
    from helseark.adapters.csv_metrics import import_metrics_csv
    v,p,_=setup(tmp_path);path=tmp_path/'partial.csv';path.write_text('date;value;unit;code\n'+text+';1,200;mg/L;Q\n')
    c=import_metrics_csv(add_source(v,p,path),p,replace(csv_mapping(p),dateFormat=fmt))
    assert not [i for i in c.unresolved if i.severity=='error']
    r=next(e['resource'] for e in c.bundle['entry'] if e['resource']['resourceType']=='Observation')
    assert r['effectiveDateTime']==expected


def test_fhir_native_metadata_must_be_valid_r4_before_remapping(tmp_path):
    from helseark.adapters.fhir_r4 import import_fhir_r4,IdentityMapping
    v,p,_=setup(tmp_path);raw=decode_json((FIXTURES/'r4.json').read_bytes())
    raw['entry'][1]['resource']['meta']['lastUpdated']='not-an-instant'
    path=tmp_path/'invalid-native.json';path.write_bytes(encode_json(raw))
    c=import_fhir_r4(add_source(v,p,path),p,IdentityMapping('Patient/p1',p,'Synthetic assignment','https://provider.example/fhir'))
    assert any(i.severity=='error' for i in c.unresolved)
    with pytest.raises(ArchiveError):prepare_candidate(v,c)


def test_fhir_identical_bytes_cross_provider_explicit_new_assertions(tmp_path):
    v,p,_=setup(tmp_path);s,c=fhir(v,p);publish(v,c)
    _,second=fhir(v,p,provider='https://provider-b.example/fhir')
    with pytest.raises(ArchiveError,match='REEXTRACTION_REQUIRED'):prepare_candidate(v,second)
    # Byte identity is the existing Task6 source boundary. The human host must
    # explicitly declare these new provider assertions, including their document.
    proposal=prepare_candidate(v,second,reextract=True,
        reconciliation={e['fullUrl']:None for e in second.bundle['entry']})
    commit_candidate(v,proposal,decision(v,proposal))
    rows=list(observations(v,p,ObservationFilter()))
    assert len(rows)==2 and len({r.resourceRef.id for r in rows})==2


@pytest.mark.parametrize('family',['fhir','csv'])
@pytest.mark.parametrize('change_id',[False,True])
def test_adapter_errors_cannot_be_removed_from_untrusted_candidate(tmp_path,family,change_id):
    v,p,_=setup(tmp_path)
    if family=='fhir':
        from helseark.adapters.fhir_r4 import import_fhir_r4,IdentityMapping
        raw=decode_json((FIXTURES/'r4.json').read_bytes())
        raw['entry'].append({'resource':{'resourceType':'Medication','id':'m1','status':'active'}})
        path=tmp_path/'unsupported.json';path.write_bytes(encode_json(raw))
        c=import_fhir_r4(add_source(v,p,path),p,IdentityMapping('Patient/p1',p,'Synthetic assignment','https://provider.example/fhir'))
    else:
        from helseark.adapters.csv_metrics import import_metrics_csv
        path=tmp_path/'unsupported.csv';path.write_text('date;value;unit;code;unmapped\n01/02/2026;1,200;mg/L;Q;retained\n')
        c=import_metrics_csv(add_source(v,p,path),p,csv_mapping(p))
    assert any(i.severity=='error' for i in c.unresolved)
    metadata=decode_json((c.path/'candidate.json').read_bytes());metadata['unresolved']=[]
    if change_id:
        from uuid import uuid4
        metadata['candidateId']=str(uuid4())
    (c.path/'candidate.json').write_bytes(encode_json(metadata))
    before=head(v,p)
    with pytest.raises(ArchiveError,match='CANDIDATE_MISMATCH'):
        edited=read_candidate(v,c.path,person=p)
        prepare_candidate(v,edited,authorized_sources=tuple(metadata['sourceSha256']))
    assert head(v,p)==before


def test_csv_host_mapping_remains_in_accepted_evidence_after_cleanup(tmp_path):
    from helseark.adapters.csv_metrics import import_metrics_csv
    from helseark.archive import _history
    from helseark.agent_context import document
    import shutil
    v,p,_=setup(tmp_path);mapping=csv_mapping(p)
    c=import_metrics_csv(add_source(v,p,FIXTURES/'metrics.csv'),p,mapping);publish(v,c)
    for path in (v.root/'people'/p/'work',v.root/'work',v.root/'.runtime'):
        if path.exists():shutil.rmtree(path)
    _,directory,_=_history(v,p)[-1]
    entries=decode_json((directory/'evidence.json').read_bytes())['entries']
    descriptions=[e.get('transformation',{}).get('description','') for e in entries if e['kind']=='source']
    assert descriptions and all('Trusted local mapping JSON: ' in text for text in descriptions)
    for text in descriptions:
        assert decode_json(text.split('Trusted local mapping JSON: ',1)[1].encode())==document(mapping)
