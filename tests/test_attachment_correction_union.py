"""Cross-leaf correction admission: retained originals plus native extractions."""
from pathlib import Path
import pytest
from helseark.archive import (init_vault, add_person, commit_candidate, iter_current,
                              resolve, doctor, head)
from helseark.contracts import PersonDraft, ResourceRef, ArchiveError
from helseark.intake import add_source, build_packet, prepare_candidate, read_candidate, start_correction
from helseark.adapters.fhir_r4 import import_fhir_r4, IdentityMapping
from helseark.serialization import encode_json, decode_json, hash_bytes
from test_attachment_authority import decision
from test_structured_correction_disclosure import inventory


@pytest.mark.parametrize('kind', ['DocumentReference', 'DiagnosticReport'])
def test_original_and_extraction_correction_reuse_and_exact_receipt_binding(tmp_path, kind):
    v = init_vault(tmp_path/'vault')
    p = add_person(v, PersonDraft('Synthetic same name'))
    other = add_person(v, PersonDraft('Synthetic same name'))
    source = add_source(v, p, Path(__file__).parent/'fixtures/synthetic/lab-text.pdf')
    build_packet(v, source, tmp_path/'packet', identityConfirmed=True)
    receipt = source.assetPath.parent/'extraction.json'
    pages_hash = decode_json(receipt.read_bytes())['pagesSha256']
    pages = v.root/f'people/{p}/assets/sha256/{pages_hash}/blob'
    attachments = [dict(url=f'assets/sha256/{d}/blob', contentType=m, size=size,
                        title='Synthetic retained original or extraction') for d,m,size in
                   [(source.sourceSha256,'application/pdf',source.size),
                    (pages_hash,'application/json',pages.stat().st_size)]]
    native = dict(resourceType=kind,id='d1',subject={'reference':'Patient/p1'},
                  status='current' if kind=='DocumentReference' else 'final')
    observation = dict(resourceType='Observation',id='o1',status='unknown',
                       subject={'reference':'Patient/p1'},code={'text':'Synthetic assertion'},valueString='synthetic')
    if kind == 'DocumentReference':
        native['content'] = [dict(attachment=a) for a in attachments]
        observation['derivedFrom'] = [{'reference':'DocumentReference/d1'}]
    else:
        native.update(code={'text':'Synthetic report'},presentedForm=attachments,
                      result=[{'reference':'Observation/o1'}])
    bundle = dict(resourceType='Bundle',type='collection',entry=[
        {'resource':dict(resourceType='Patient',id='p1')},{'resource':native},{'resource':observation}])
    mapping = IdentityMapping('Patient/p1',p,'Explicit synthetic assignment','https://synthetic.invalid')
    def publish(candidate):
        proposal = prepare_candidate(v, candidate)
        commit_candidate(v, proposal, decision(v, proposal))
    incoming = tmp_path/'incoming.json'; incoming.write_bytes(encode_json(bundle))
    publish(import_fhir_r4(add_source(v,p,incoming),p,mapping))
    target_kind = 'Observation' if kind=='DocumentReference' else 'DiagnosticReport'
    old = next(r for r in iter_current(v,p) if r['resourceType']==target_kind)
    ref = ResourceRef(target_kind,old['id'])
    prior = inventory(v.root/'people')
    sources = inventory(v.root/'people'/p/'assets')
    c = start_correction(v,p,ref,'transcription: synthetic same-source verification')
    # Both native positions must retain F7 scope before F5 admission executes.
    saved = {f.name:f.read_bytes() for f in c.path.iterdir()}
    metadata = decode_json(saved['candidate.json'])
    for key,value in [('personId',other),('baseChangeSha256','0'*64),
                      ('sourceSha256',metadata['sourceSha256']+['0'*64])]:
        changed = {**metadata,key:value}
        (c.path/'candidate.json').write_bytes(encode_json(changed))
        with pytest.raises(ArchiveError): read_candidate(v,c.path,person=p)
        (c.path/'candidate.json').write_bytes(saved['candidate.json'])
    bundle_copy = decode_json(saved['bundle.json'])
    native_copy = next(e['resource'] for e in bundle_copy['entry']
                       if e['resource']['resourceType']==kind)
    attachment = (native_copy['content'][0]['attachment'] if kind=='DocumentReference'
                  else native_copy['presentedForm'][0])
    attachment['url']='assets/sha256/'+'0'*64+'/blob'
    (c.path/'bundle.json').write_bytes(encode_json(bundle_copy))
    with pytest.raises(ArchiveError,match='CANDIDATE_MISMATCH'): read_candidate(v,c.path)
    (c.path/'bundle.json').write_bytes(saved['bundle.json'])
    control=v.root/f'.runtime/corrections/{c.candidateId}.json'
    control_bytes=control.read_bytes(); control_value=decode_json(control_bytes)
    control_value['targetVersionId']='00000000-0000-4000-8000-000000000000'
    control.write_bytes(encode_json(control_value))
    with pytest.raises(ArchiveError,match='CANDIDATE_MISMATCH'): read_candidate(v,c.path)
    control.write_bytes(control_bytes)
    from shutil import copytree
    copied=tmp_path/'copied-draft'; copytree(c.path,copied)
    with pytest.raises(ArchiveError,match='CANDIDATE_MISMATCH'): read_candidate(v,copied)
    with pytest.raises(ArchiveError): start_correction(v,other,ref,'transcription: wrong selected person')
    with pytest.raises(ArchiveError,match='STALE_BASE'):
        start_correction(v,p,ResourceRef(target_kind,old['id'],'00000000-0000-4000-8000-000000000000'),
                         'transcription: stale explicit target')
    sibling=start_correction(v,p,ref,'transcription: synthetic sibling draft')
    publish(read_candidate(v,c.path,person=p))
    with pytest.raises(ArchiveError,match='STALE_BASE'): read_candidate(v,sibling.path)

    current = resolve(v,p,ref)
    assert current['status']==old['status']
    assert all(current[k]==value for k,value in old.items() if k!='meta')
    assert resolve(v,p,ResourceRef(target_kind,old['id'],old['meta']['versionId']))==old
    assert all(inventory(v.root/'people')[name]==digest for name,digest in prior.items())
    assert inventory(v.root/'people'/p/'assets')==sources
    assert not doctor(v).issues and head(v,other).sequence==1
    # A second genuinely issued import reuses both original and extraction.
    native['id']='reuse'; observation['id']='o2'
    if kind=='DocumentReference': observation['derivedFrom']=[{'reference':'DocumentReference/reuse'}]
    else: native['result']=[{'reference':'Observation/o2'}]
    incoming2=tmp_path/'reuse.json'; incoming2.write_bytes(encode_json(bundle))
    publish(import_fhir_r4(add_source(v,p,incoming2),p,mapping))
    assert not doctor(v).issues
    # The correction's allowed extraction remains independently receipt-bound.
    draft=start_correction(v,p,ref,'transcription: synthetic receipt binding')
    proposal=prepare_candidate(v,read_candidate(v,draft.path)); reviewed=decision(v,proposal)
    accepted_before=inventory(v.root/'people'/p/'accepted')
    receipt_bytes=receipt.read_bytes(); receipt.write_bytes(receipt_bytes+b'\n')
    with pytest.raises(ArchiveError): commit_candidate(v,proposal,reviewed)
    assert inventory(v.root/'people'/p/'accepted')==accepted_before
    # Accepted history independently detects the same edited bound receipt.
    with pytest.raises(ArchiveError, match='INTEGRITY'): head(v,p)
    assert source.assetPath.read_bytes()==(Path(__file__).parent/'fixtures/synthetic/lab-text.pdf').read_bytes()
    assert all(inventory(v.root/'people')[name]==digest for name,digest in prior.items()
               if (v.root/'people'/name)!=receipt)
    assert hash_bytes(pages.read_bytes())==pages_hash
