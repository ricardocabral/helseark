"""Public synthetic regressions: host correction authority and attachment disclosure."""
from pathlib import Path
import subprocess
import sys
import pytest

from helseark.archive import (init_vault, add_person, commit_candidate, iter_current,
                              resolve, doctor)
from helseark.contracts import (PersonDraft, ResourceRef, ObservationFilter,
                                ExportSelection, ArchiveError)
from helseark.intake import add_source, prepare_candidate, read_candidate
from helseark.serialization import encode_json, decode_json, hash_bytes
from helseark.portability import export_person, verify_export
from test_adapters import decision, fhir, csv_mapping, FIXTURES
from test_source_disclosure import decision as disclosure_decision


def inventory(root):
    return {str(p.relative_to(root)): hash_bytes(p.read_bytes())
            for p in root.rglob('*') if p.is_file()}


def structured(tmp_path, family):
    v = init_vault(tmp_path/'vault')
    p = add_person(v, PersonDraft('Synthetic Ada'))
    other = add_person(v, PersonDraft('Synthetic other'))
    if family == 'fhir':
        source, c = fhir(v, p)
    else:
        from helseark.adapters.csv_metrics import import_metrics_csv
        source = add_source(v, p, FIXTURES/'metrics.csv')
        c = import_metrics_csv(source, p, csv_mapping(p))
    proposal = prepare_candidate(v, c)
    commit_candidate(v, proposal, decision(v, proposal))
    old = next(r for r in iter_current(v, p) if r['resourceType']=='Observation')
    return v, p, other, source, c, old


def correct(v, p, old, mode='entered-in-error'):
    ref = f"Observation/{old['id']}/_history/{old['meta']['versionId']}"
    child = subprocess.run([sys.executable, '-m', 'helseark.cli', '--vault', str(v.root),
        'correct', '--person', p, '--resource', ref, '--reason',
        mode+': SYNTHETIC human invalidates local record; no laboratory amendment', '--json'], capture_output=True)
    assert child.returncode == 0, child.stderr
    return read_candidate(v, Path(decode_json(child.stdout)['path']), person=p)


@pytest.mark.parametrize('family', ['fhir', 'csv'])
def test_public_structured_error_correction_preserves_original_authority(tmp_path, family):
    from helseark.query import observations
    v, p, other, source, original, old = structured(tmp_path, family)
    accepted = inventory(v.root/'people'/p/'accepted')
    assets = inventory(v.root/'people'/p/'assets')
    issued = inventory(original.path)
    unrelated = [r for r in iter_current(v,p) if r['resourceType']=='Observation' and r['id']!=old['id']]
    c = correct(v, p, old)
    assert read_candidate(v, original.path).bundle == original.bundle
    row = next(e['resource'] for e in c.bundle['entry'] if e['resource']['resourceType']=='Observation')
    row['status'] = 'entered-in-error'
    (c.path/'bundle.json').write_bytes(encode_json(c.bundle))
    proposal = prepare_candidate(v, read_candidate(v, c.path))
    assert resolve(v, p, ResourceRef('Observation', old['id'])) == old
    commit_candidate(v, proposal, decision(v, proposal))
    current = resolve(v, p, ResourceRef('Observation', old['id']))
    assert current['status']=='entered-in-error'
    for key in old.keys()-{'meta','status'}:
        assert current[key] == old[key]
    assert resolve(v, p, ResourceRef('Observation', old['id'], old['meta']['versionId'])) == old
    assert all(inventory(v.root/'people'/p/'accepted')[k]==digest for k,digest in accepted.items())
    assert inventory(v.root/'people'/p/'assets') == assets
    assert inventory(original.path) == issued
    assert all(resolve(v,p,ResourceRef(r['resourceType'],r['id']))==r for r in unrelated)
    assert not doctor(v).issues
    assert not any(r.resourceRef.id==old['id'] for r in observations(v,p,ObservationFilter()))
    assert any(r.resourceRef.id==old['id'] for r in observations(v,p,ObservationFilter(includeInvalidated=True)))
    assert any(e['role']=='revision' and e['what']['reference']==
               f"Observation/{old['id']}/_history/{old['meta']['versionId']}"
               for r in iter_current(v,p) if r['resourceType']=='Provenance' for e in r['entity'])


def shared_attachment(tmp_path, kind):
    from helseark.adapters.fhir_r4 import import_fhir_r4, IdentityMapping
    v = init_vault(tmp_path/'vault')
    p = add_person(v, PersonDraft('Person A'))
    add_person(v, PersonDraft('Person B'))
    original = Path(__file__).parent/'fixtures/synthetic/agent-workflows/shared-report.txt'
    attachment = add_source(v,p,original)
    a = {'url':f'assets/sha256/{attachment.sourceSha256}/blob',
         'contentType':attachment.mediaType, 'size':attachment.size, 'title':'Unchanged synthetic shared report'}
    r = {'resourceType':kind, 'id':'r1', 'status':'current' if kind=='DocumentReference' else 'final',
         'subject':{'reference':'Patient/p1'}}
    if kind=='DocumentReference': r['content']=[{'attachment':a}]
    else: r.update(code={'text':'Synthetic shared report'},presentedForm=[a])
    observation={'resourceType':'Observation','id':'o1','status':'unknown',
                 'subject':{'reference':'Patient/p1'},'code':{'text':'Synthetic result'},
                 'valueString':'synthetic result A'}
    if kind=='DocumentReference':observation['derivedFrom']=[{'reference':'DocumentReference/r1'}]
    else:r['result']=[{'reference':'Observation/o1'}]
    path=tmp_path/'native.json'
    path.write_bytes(encode_json({'resourceType':'Bundle','type':'collection','entry':[
        {'resource':{'resourceType':'Patient','id':'p1'}},{'resource':r},{'resource':observation}]}))
    c=import_fhir_r4(add_source(v,p,path),p,IdentityMapping('Patient/p1',p,
        'Explicit synthetic assignment; no disclosure consent','https://synthetic.example'))
    proposal=prepare_candidate(v,c);commit_candidate(v,proposal,decision(v,proposal))
    return v,p,attachment


@pytest.mark.parametrize('kind',['DocumentReference','DiagnosticReport'])
def test_nonpdf_original_attachment_requires_separate_disclosure(tmp_path,kind):
    v,p,source=shared_attachment(tmp_path,kind)
    before=inventory(v.root/'people')
    assert source.mediaType=='application/octet-stream'
    assert source.sourceSha256=='dc35fde75226b81cdc86b58b7a0aca24822d9a979447ae9b79074aac5c7e4f96'
    assert not doctor(v).issues
    with pytest.raises(ArchiveError,match='SOURCE_SCOPE_REVIEW_REQUIRED'):
        export_person(v,p,tmp_path/'denied',ExportSelection('selected-current',(),True))
    assert not (tmp_path/'denied').exists()
    out=export_person(v,p,tmp_path/'without',ExportSelection('selected-current',(),False)).path
    assert not verify_export(out).issues and not (out/'sources').exists()
    assert inventory(v.root/'people')==before


@pytest.mark.parametrize('family',['fhir','csv'])
def test_correction_controls_deny_counterfeits_and_expansion(tmp_path,family):
    from copy import deepcopy
    from shutil import copytree
    from uuid import uuid4
    from helseark.intake import start_correction
    v,p,other,source,original,old=structured(tmp_path,family)
    accepted=inventory(v.root/'people'/p/'accepted')
    assets=inventory(v.root/'people'/p/'assets')
    ref=ResourceRef('Observation',old['id'],old['meta']['versionId'])
    with pytest.raises(ArchiveError): start_correction(v,other,ref,'transcription: SYNTHETIC wrong person')
    with pytest.raises(ArchiveError,match='STALE_BASE'):
        start_correction(v,p,ResourceRef('Observation',old['id'],str(uuid4())),'transcription: SYNTHETIC stale')
    c=correct(v,p,old,'transcription')
    original_files={f.name:f.read_bytes() for f in c.path.iterdir()}
    control=v.root/f'.runtime/corrections/{c.candidateId}.json'
    control_bytes=control.read_bytes()
    for key,value in [('mode','laboratory-amendment'),('reason','changed'),('sources',[]),('mapping',{}),
                      ('personId',other),('base','0'*64),('targetVersionId',str(uuid4()))]:
        altered=decode_json(control_bytes);altered[key]=value;control.write_bytes(encode_json(altered))
        with pytest.raises(ArchiveError,match='CANDIDATE_MISMATCH'):read_candidate(v,c.path)
        control.write_bytes(control_bytes)
    copied=tmp_path/'copied';copytree(c.path,copied)
    with pytest.raises(ArchiveError,match='CANDIDATE_MISMATCH'):read_candidate(v,copied)
    for key,value in [('sourceSha256',[source.sourceSha256,'0'*64]),('producer',{'kind':'local-user','name':'counterfeit'}),
                      ('candidateId',str(uuid4())),('baseChangeSha256','0'*64),('personId',other)]:
        altered=decode_json(original_files['candidate.json']);altered[key]=value
        (c.path/'candidate.json').write_bytes(encode_json(altered))
        with pytest.raises(ArchiveError):read_candidate(v,c.path,person=p)
        (c.path/'candidate.json').write_bytes(original_files['candidate.json'])
    changed=deepcopy(c.bundle)
    doc=next(e['resource'] for e in changed['entry'] if e['resource']['resourceType']=='DocumentReference')
    doc['content'][0]['attachment']['url']='assets/sha256/'+'0'*64+'/blob'
    (c.path/'bundle.json').write_bytes(encode_json(changed))
    with pytest.raises(ArchiveError,match='CANDIDATE_MISMATCH'):read_candidate(v,c.path)
    (c.path/'bundle.json').write_bytes(original_files['bundle.json'])
    (c.path/'coverage.json').write_bytes(encode_json({'items':[]}))
    with pytest.raises(ArchiveError,match='CANDIDATE_MISMATCH'):read_candidate(v,c.path)
    (c.path/'coverage.json').write_bytes(original_files['coverage.json'])
    # Merely naming a structured input a local correction does not issue it.
    fake=tmp_path/'fake';copytree(original.path,fake)
    metadata=decode_json((fake/'candidate.json').read_bytes())
    metadata.update(candidateId=str(uuid4()),baseChangeSha256=c.base.changeSha256,
                    producer={'kind':'local-user','name':'explicit local correction'},unresolved=[])
    (fake/'candidate.json').write_bytes(encode_json(metadata))
    with pytest.raises(ArchiveError,match='CANDIDATE_MISMATCH'):
        read_candidate(v,fake)
    # A local transcription cannot claim a laboratory amendment.
    row=next(e['resource'] for e in c.bundle['entry'] if e['resource']['resourceType']=='Observation')
    row['status']='amended' if old['status']!='amended' else 'corrected'
    (c.path/'bundle.json').write_bytes(encode_json(c.bundle))
    with pytest.raises(ArchiveError,match='CORRECTION_STATUS'):
        prepare_candidate(v,read_candidate(v,c.path))
    assert inventory(v.root/'people'/p/'accepted')==accepted
    assert inventory(v.root/'people'/p/'assets')==assets


@pytest.mark.parametrize('kind',['DocumentReference','DiagnosticReport'])
def test_nonpdf_reviewed_original_and_derivative_are_exact_and_bound(tmp_path,kind):
    from helseark.source_disclosure import prepare_disclosure,record_disclosure
    v,p,source=shared_attachment(tmp_path,kind)
    before=inventory(v.root/'people')
    selection=ExportSelection('selected-current')
    plan=prepare_disclosure(v,p,selection,tmp_path/'original-plan')
    record_disclosure(v,plan,disclosure_decision(plan))
    out=export_person(v,p,tmp_path/'original-export',selection,review=plan).path
    assert not verify_export(out).issues
    assert (out/f'sources/people/{p}/assets/sha256/{source.sourceSha256}/blob').read_bytes()==source.assetPath.read_bytes()
    derivative=tmp_path/'supplied.txt';derivative.write_bytes(b'Person A: synthetic result A\n')
    supplied=[dict(sourceSha256=source.sourceSha256,path=str(derivative),mediaType='text/plain',
                   mapping='SYNTHETIC original Person A line retained',omissions='Person B line omitted by human')]
    dplan=prepare_disclosure(v,p,selection,tmp_path/'derivative-plan',derivatives=supplied)
    record_disclosure(v,dplan,disclosure_decision(dplan))
    dout=export_person(v,p,tmp_path/'derivative-export',selection,review=dplan).path
    assert not verify_export(dout).issues
    assert not (dout/'sources').exists()
    assert (dout/f'derivatives/{hash_bytes(derivative.read_bytes())}/blob').read_bytes()==derivative.read_bytes()
    # Explicit selection and all retained historical sources remain bound even
    # though selected-current resources are a narrower clinical closure.
    with pytest.raises(ArchiveError,match='REVIEW_MISMATCH'):
        export_person(v,p,tmp_path/'changed-selection',ExportSelection('selected-current',(ResourceRef('Patient',p),)),review=plan)
    raw=(plan/'plan.json').read_bytes();data=decode_json(raw);data['originalSources']=[]
    (plan/'plan.json').write_bytes(encode_json(data))
    with pytest.raises(ArchiveError,match='REVIEW_MISMATCH'):
        export_person(v,p,tmp_path/'changed-plan',selection,review=plan)
    (plan/'plan.json').write_bytes(raw)
    assert inventory(v.root/'people')==before
    # Public new acceptance makes the earlier Head-bound plan stale.
    from helseark.intake import start_correction
    # A no-op same-source revision is explicit intent; it still needs clinical review.
    if kind=='DiagnosticReport':
        target=next(r for r in iter_current(v,p) if r['resourceType']==kind)
        c=start_correction(v,p,ResourceRef(kind,target['id']),'transcription: SYNTHETIC rechecked unchanged source')
        proposal=prepare_candidate(v,c);commit_candidate(v,proposal,decision(v,proposal))
        with pytest.raises(ArchiveError,match='REVIEW_MISMATCH'):
            export_person(v,p,tmp_path/'stale-plan',selection,review=plan)


def test_text_backed_observation_correction_and_stale_sibling(tmp_path):
    from helseark.intake import start_correction
    from helseark.validation import validate_candidate
    v,p,source=shared_attachment(tmp_path,'DocumentReference')
    old=next(r for r in iter_current(v,p) if r['resourceType']=='Observation')
    accepted=inventory(v.root/'people'/p/'accepted')
    assets=inventory(v.root/'people'/p/'assets')
    c=correct(v,p,old)
    sibling=correct(v,p,old,'transcription')
    row=next(e['resource'] for e in c.bundle['entry'] if e['resource']['resourceType']=='Observation')
    row['status']='entered-in-error'
    (c.path/'bundle.json').write_bytes(encode_json(c.bundle))
    proposal=prepare_candidate(v,read_candidate(v,c.path));commit_candidate(v,proposal,decision(v,proposal))
    assert all(inventory(v.root/'people'/p/'accepted')[k]==h for k,h in accepted.items())
    assert inventory(v.root/'people'/p/'assets')==assets
    assert resolve(v,p,ResourceRef('Observation',old['id'],old['meta']['versionId']))==old
    assert resolve(v,p,ResourceRef('Observation',old['id']))['valueString']=='synthetic result A'
    with pytest.raises(ArchiveError,match='STALE_BASE'):read_candidate(v,sibling.path)
    # A later correction remains possible from its own accepted source/coverage.
    next_draft=start_correction(v,p,ResourceRef('Observation',old['id']),
                               'transcription: SYNTHETIC rechecked source without adding facts')
    proposal=prepare_candidate(v,next_draft);commit_candidate(v,proposal,decision(v,proposal))
    assert source.assetPath.read_bytes()==(Path(__file__).parent/'fixtures/synthetic/agent-workflows/shared-report.txt').read_bytes()


def test_structured_correction_does_not_waive_source_token_checks(tmp_path):
    from decimal import Decimal
    from helseark.validation import validate_candidate
    v,p,_,source,original,old=structured(tmp_path,'csv')
    c=correct(v,p,old,'transcription')
    row=next(e['resource'] for e in c.bundle['entry'] if e['resource']['resourceType']=='Observation')
    row['valueQuantity']['value']=Decimal('99.0000')
    target='urn:uuid:'+row['id']
    e=next(e for e in c.evidence['entries'] if e['target']['reference']==target
           and '/valueQuantity/value' in e['target']['pointers'])
    e['transformation']['rule']='decimal-comma-v1'
    (c.path/'bundle.json').write_bytes(encode_json(c.bundle))
    (c.path/'evidence.json').write_bytes(encode_json(c.evidence))
    fresh=read_candidate(v,c.path)
    assert any(i.code=='SOURCE_TOKEN_MISMATCH' and i.severity=='error' for i in validate_candidate(v,fresh).issues)
    with pytest.raises(ArchiveError,match='VALIDATION_BLOCKED'):prepare_candidate(v,fresh)


def test_correction_rejects_malformed_editable_shapes(tmp_path):
    v,p,_,_,_,old=structured(tmp_path,'fhir')
    c=correct(v,p,old,'transcription')
    bundle_bytes=(c.path/'bundle.json').read_bytes()
    for entries in ([None],[{'fullUrl':'urn:uuid:'+old['id'],'resource':{}}]):
        bundle=decode_json(bundle_bytes);bundle['entry']=entries
        (c.path/'bundle.json').write_bytes(encode_json(bundle))
        with pytest.raises(ArchiveError,match='CANDIDATE_MISMATCH'):read_candidate(v,c.path)
    (c.path/'bundle.json').write_bytes(bundle_bytes)
    intake=v.root/f'.runtime/intake/{c.candidateId}.json'
    intake.write_bytes(b'[]')
    with pytest.raises(ArchiveError,match='CANDIDATE_MISMATCH'):read_candidate(v,c.path)


def test_correction_cannot_promote_accepted_extraction_to_new_attachment(tmp_path):
    from test_intake import supplied_candidate
    from test_review import approve
    from helseark.intake import start_correction
    v,p,source,_,c=supplied_candidate(tmp_path)
    proposal=prepare_candidate(v,c);commit_candidate(v,proposal,approve(v,proposal))
    old=next(r for r in iter_current(v,p) if r['resourceType']=='Observation')
    c=start_correction(v,p,ResourceRef('Observation',old['id']),'transcription: SYNTHETIC source checked')
    extraction=decode_json((source.assetPath.parent/'extraction.json').read_bytes())['pagesSha256']
    original=next(e['resource'] for e in c.bundle['entry'] if e['resource']['resourceType']=='DocumentReference')
    original['content'].append({'attachment':{'url':f'assets/sha256/{extraction}/blob','contentType':'application/json'}})
    (c.path/'bundle.json').write_bytes(encode_json(c.bundle))
    with pytest.raises(ArchiveError,match='CANDIDATE_MISMATCH'):read_candidate(v,c.path)
