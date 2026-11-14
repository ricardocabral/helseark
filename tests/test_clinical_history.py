"""Synthetic native assertions through the real validation/review/query boundary."""
import copy
import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from helseark.archive import add_person, head, commit_candidate
from helseark.contracts import ArchiveError, PersonDraft, ResourceRef
from helseark.intake import prepare_candidate, add_source
from helseark.query import history, timeline
from helseark.serialization import decode_json, encode_json
from helseark.validation import validate_candidate, schema_packet
from test_validation import good, persist
from test_query import enrich
from helseark.review import render_review, record_review
from helseark.contracts import ReviewDecision


def approve(vault, proposal):
    view=render_review(vault,proposal)
    acks={(i["code"],i["resourceRef"]): {"code":i["code"],"resourceRef":i["resourceRef"],"reason":"Synthetic human compared source and retained limitation."}
          for i in view.issues if i["severity"] in ("review","warning")}
    return record_review(vault,proposal,ReviewDecision(True,"accept-with-acknowledged-limitations",tuple(acks.values()),"synthetic human"))

FIXTURES = Path(__file__).parent/'fixtures/synthetic/clinical-history'
KINDS = sorted(p.stem for p in FIXTURES.glob('*.json')) or ['MedicationStatement']


def candidate_for(vault, candidate, kind):
    records = decode_json((FIXTURES/(kind+'.json')).read_bytes().replace(b'PERSON',candidate.personId.encode()))
    resources=[]
    for r in records:
        r=copy.deepcopy(r);r['id']=str(uuid4())
        if kind=='Immunization' and r.get('status')=='completed':
            # A uri and a source quote shaped like an alias are still source text.
            r['education'][0]['reference']='urn:uuid:'+r['id']
            r.setdefault('note',[]).append({'text':'urn:uuid:'+r['id']})
        resources.append({'fullUrl':'urn:uuid:'+r['id'],'resource':r})
    enrich(vault,candidate,resources)
    # Register the source with the same supported intake API used by CLI imports.
    digest=next(e['sourceSha256'] for e in candidate.evidence['entries'] if e['kind']=='source')
    source_path=candidate.path/'source.json'
    source_path.write_bytes((vault.root/f'people/{candidate.personId}/assets/sha256/{digest}/blob').read_bytes())
    add_source(vault,candidate.personId,source_path)
    # The generic fixture's unused lab source is test setup, not accepted history.
    for p in (vault.root/f'people/{candidate.personId}/assets/sha256').iterdir():
        if p.name!=digest:
            shutil.rmtree(p)
    return records,resources


@pytest.mark.parametrize('kind',KINDS)
def test_source_assertions_review_native_query_and_restore(good,tmp_path,kind):
    from helseark.portability import backup,restore,export_person,verify_export
    from helseark.contracts import ExportSelection
    vault,candidate=good
    original,entries=candidate_for(vault,candidate,kind)
    report=validate_candidate(vault,candidate)
    assert not [i for i in report.issues if i.severity=='error'], report.issues
    assert len(original)>0
    packet=schema_packet(vault,[kind],tmp_path/'schemas')
    assert (packet/'profiles/r4/0.2.0').is_dir()
    initial=head(vault,candidate.personId)
    sources=tuple(sorted({e['sourceSha256'] for e in candidate.evidence['entries'] if e['kind']=='source'}))
    proposal=prepare_candidate(vault,candidate,authorized_sources=sources)
    assert head(vault,candidate.personId)==initial
    # No receipt means no publication; real explicit synthetic human review follows.
    with pytest.raises((ArchiveError,AttributeError,TypeError)):
        commit_candidate(vault,proposal,None)
    assert head(vault,candidate.personId)==initial
    commit_candidate(vault,proposal,approve(vault,proposal))
    native=list(history(vault,candidate.personId,[kind]))
    selected=[r for r in native if r['resourceType']==kind]
    assert len(selected)==len(original)
    assert any(r['resourceType']=='Provenance' for r in native)
    def clinical(r):
        return encode_json({k:v for k,v in r.items() if k not in ('id','meta')})
    assert sorted(map(clinical,selected))==sorted(map(clinical,[e['resource'] for e in entries]))
    rows=[r for r in timeline(vault,candidate.personId) if r.resourceRef.resourceType==kind]
    assert len(rows)==len(original) and all(r.sourceRefs for r in rows)
    assert all(r.resource in selected for r in rows)
    expected_times = {
        'MedicationStatement': {'effectivePeriod', None},
        'MedicationRequest': {'authoredOn', None},
        'Condition': {'onsetString', 'onsetDateTime', None},
        'AllergyIntolerance': {None},
        'Immunization': {'occurrenceDateTime', 'occurrenceString'},
        'Procedure': {'performedPeriod', None},
        'Encounter': {'period', None},
        'FamilyMemberHistory': {'date', None},
    }
    assert {r.effectiveType for r in rows} == expected_times[kind]
    assert any(r.timeBucket=='unknown' for r in rows)
    if kind=='MedicationStatement':
        use=next(r for r in selected if r['status']=='active')
        assert str(use['dosage'][0]['doseAndRate'][0]['doseQuantity']['value'])=='1.250'
    if kind=='MedicationRequest':
        order=next(r for r in selected if r['status']=='active')
        assert str(order['dosageInstruction'][0]['doseAndRate'][0]['doseQuantity']['value'])=='2.500'
    if kind=='Condition':
        assert {r['verificationStatus']['coding'][0]['code'] for r in selected}=={'unconfirmed','refuted','confirmed'}
        assert all(r.effectiveType!='recordedDate' for r in rows)
    if kind=='AllergyIntolerance':
        assert any(r['code']['text'].startswith('No known allergies') for r in selected)
    if kind=='Immunization':
        vaccine=next(r for r in selected if r['status']=='completed')
        assert vaccine['occurrenceDateTime']=='2020'
        assert str(vaccine['doseQuantity']['value'])=='0.500'
        assert vaccine['protocolApplied'][0]['doseNumberString']=='Unknown per source'
    if kind=='FamilyMemberHistory':
        relative=next(r for r in selected if r['status']=='completed')
        assert str(relative['condition'][0]['onsetAge']['value'])=='45.00'
        assert not list(history(vault,candidate.personId,['Condition']))
    assert not list(history(vault,candidate.personId,[kind],initial))
    # Same-label relative cannot see these assertions.
    other=add_person(vault,PersonDraft('Synthetic Person A'))
    assert not list(history(vault,other,[kind]))
    before={p.relative_to(vault.root).as_posix():p.read_bytes() for p in (vault.root/'people').rglob('*') if p.is_file()}
    backup(vault,tmp_path/'backup')
    recovered=restore(tmp_path/'backup',tmp_path/'restored')
    assert before=={p.relative_to(recovered.root).as_posix():p.read_bytes() for p in (recovered.root/'people').rglob('*') if p.is_file()}
    assert encode_json(list(history(vault,candidate.personId,[kind])))==encode_json(list(history(recovered,candidate.personId,[kind])))
    export_person(vault,candidate.personId,tmp_path/'export',ExportSelection('selected-current',tuple(ResourceRef(kind,r['id']) for r in selected),False))
    assert not verify_export(tmp_path/'export').issues


@pytest.mark.parametrize('kind',KINDS)
def test_patient_and_scalar_evidence_cannot_be_inherited(good,kind):
    vault,candidate=good
    _,entries=candidate_for(vault,candidate,kind)
    field='patient' if kind in ('AllergyIntolerance','Immunization','FamilyMemberHistory') else 'subject'
    entries[0]['resource'][field]={'reference':'Patient/'+str(uuid4())}
    persist(candidate)
    assert 'PERSON_MISMATCH' in {i.code for i in validate_candidate(vault,candidate).issues}
    entries[0]['resource'][field]={'reference':'Patient/'+candidate.personId}
    candidate.evidence['entries']=[e for e in candidate.evidence['entries'] if e['target']['reference']!=entries[0]['fullUrl'] or e['kind']=='generated']
    persist(candidate)
    assert 'EVIDENCE_MISSING' in {i.code for i in validate_candidate(vault,candidate).issues}


@pytest.mark.parametrize('kind',KINDS)
def test_invalid_status_and_missing_patient_block(good,kind):
    vault,candidate=good
    _,entries=candidate_for(vault,candidate,kind)
    r=entries[0]['resource']
    if kind in ('Condition','AllergyIntolerance'):
        r['verificationStatus']['coding'][0]['code']='invented-confirmation'
    else:r['status']='invented-status'
    persist(candidate)
    assert 'FHIR_STATUS_INVALID' in {i.code for i in validate_candidate(vault,candidate).issues}
    field='patient' if kind in ('AllergyIntolerance','Immunization','FamilyMemberHistory') else 'subject'
    del r[field];persist(candidate)
    assert 'SUBJECT_REQUIRED' in {i.code for i in validate_candidate(vault,candidate).issues}


@pytest.mark.parametrize('kind',KINDS)
def test_profile_and_fixture_are_r4_resources(kind):
    import json
    from jsonschema import Draft6Validator
    root=Path(__file__).resolve().parents[1]
    validator=Draft6Validator(json.loads((root/'definitions/fhir-r4-json-schema/fhir.schema.json').read_text()))
    fixture=decode_json((FIXTURES/(kind+'.json')).read_bytes().replace(b'PERSON',b'11111111-1111-4111-8111-111111111111'))
    assert fixture
    for r in fixture:validator.validate(r)
    for p in (root/'profiles/r4/0.2.0').glob('StructureDefinition-*.json'):
        profile=json.loads(p.read_text());validator.validate(profile)
        assert len(profile['differential']['element'])>5


def test_condition_status_conflicts_are_not_confirmed_diagnoses(good):
    vault,candidate=good
    _,entries=candidate_for(vault,candidate,'Condition')
    r=entries[0]['resource']
    r['verificationStatus']['coding'][0]['code']='entered-in-error'
    persist(candidate)
    assert 'CONDITION_STATUS_CONFLICT' in {i.code for i in validate_candidate(vault,candidate).issues}
    r['verificationStatus']['coding'][0]['code']='confirmed'
    r['abatementString']='Source states resolved'
    persist(candidate)
    assert 'CONDITION_STATUS_CONFLICT' in {i.code for i in validate_candidate(vault,candidate).issues}


def test_allergy_absence_and_status_are_explicit_assertions(good):
    vault,candidate=good
    _,entries=candidate_for(vault,candidate,'AllergyIntolerance')
    r=entries[1]['resource']
    del r['code'];persist(candidate)
    assert 'FHIR_REQUIRED' in {i.code for i in validate_candidate(vault,candidate).issues}
    r['code']={'text':'No known allergies per source'}
    r['verificationStatus']['coding'][0]['code']='entered-in-error';persist(candidate)
    assert 'ALLERGY_STATUS_CONFLICT' in {i.code for i in validate_candidate(vault,candidate).issues}


def test_immunization_date_is_not_inferred_from_age(good):
    vault,candidate=good
    _,entries=candidate_for(vault,candidate,'Immunization')
    del entries[0]['resource']['occurrenceDateTime'];persist(candidate)
    assert 'FHIR_REQUIRED' in {i.code for i in validate_candidate(vault,candidate).issues}


def test_encounter_status_history_is_not_free_text(good):
    vault,candidate=good
    _,entries=candidate_for(vault,candidate,'Encounter')
    entries[0]['resource']['statusHistory'][0]['status']='invented-status';persist(candidate)
    assert 'FHIR_STATUS_INVALID' in {i.code for i in validate_candidate(vault,candidate).issues}


def test_relative_age_is_not_an_invented_birth_date(good):
    vault,candidate=good
    _,entries=candidate_for(vault,candidate,'FamilyMemberHistory')
    r=entries[0]['resource'];r['ageString']='Age unknown';r['bornString']='Birth date unknown';persist(candidate)
    assert 'FAMILY_AGE_CONFLICT' in {i.code for i in validate_candidate(vault,candidate).issues}
    del r['ageString'];r['estimatedAge']=True;persist(candidate)
    assert 'FAMILY_AGE_CONFLICT' in {i.code for i in validate_candidate(vault,candidate).issues}
