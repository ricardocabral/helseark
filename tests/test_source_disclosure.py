"""Explicitly synthetic disclosure decisions; no real-user approval is created."""
from dataclasses import asdict
from pathlib import Path
import pytest
from helseark.archive import init_vault, add_person, head, _publish_change
from helseark.contracts import PersonDraft, ExportSelection, ArchiveError, ResourceRef
from helseark.serialization import encode_json, decode_json, hash_bytes
from helseark.portability import export_person, restore, verify_export


def corpus(tmp_path):
    from test_archive import update_payload, rebind_proposal
    v=init_vault(tmp_path/'vault'); p=add_person(v,PersonDraft('Selected Synthetic'))
    other=add_person(v,PersonDraft('Excluded Synthetic'))
    payload=tmp_path/'payload'; base=update_payload(v,p,payload)
    data=(Path(__file__).parent/'fixtures/synthetic/lab-two-people.pdf').read_bytes()
    digest=hash_bytes(data); asset=f'assets/sha256/{digest}/blob'
    target=v.root/f'people/{p}/{asset}'; target.parent.mkdir(parents=True); target.write_bytes(data)
    proposal=decode_json((payload/'proposal.json').read_bytes())
    proposal['assets']=[dict(path=asset,sha256=digest,size=len(data),mediaType='application/pdf')]
    rebind_proposal(payload,proposal); _publish_change(v,p,payload,base)
    return v,p,other,target


def decision(plan):
    return dict(format='helseark-source-decision-1',planSha256=hash_bytes((plan/'plan.json').read_bytes()),
                humanReviewed=True,confirmedPerson=True,acknowledgedDisclosure=True,
                reviewer={'kind':'synthetic-test','label':'SYNTHETIC qualification only'},
                reason='SYNTHETIC knowingly reviewed all scope and remaining copies')


def test_exact_inclusion_and_recovery(tmp_path):
    from helseark.source_disclosure import prepare_disclosure, record_disclosure
    v,p,other,source=corpus(tmp_path); selection=ExportSelection('full-person')
    with pytest.raises(ArchiveError,match='SOURCE_SCOPE_REVIEW_REQUIRED'):
        export_person(v,p,tmp_path/'denied',selection)
    plan=prepare_disclosure(v,p,selection,tmp_path/'plan')
    content=decode_json((plan/'plan.json').read_bytes())
    assert content['personId']==p and content['head']==asdict(head(v,p))
    assert content['originalSources'][0]['sha256']==hash_bytes(source.read_bytes())
    record_disclosure(v,plan,decision(plan))
    receipt=export_person(v,p,tmp_path/'export',selection,review=plan)
    assert not verify_export(receipt.path).issues
    assert b'ORIGINAL SHARED SOURCES' in (receipt.path/'README.md').read_bytes()
    manifest=decode_json((receipt.path/'export.json').read_bytes())
    assert manifest['format']=='helseark-export-2'
    assert manifest['sourceDisclosure']['plan']['originalDisposition']=='included-exact'
    recovered=restore(receipt.path,tmp_path/'restored')
    before={f.relative_to(v.root).as_posix():f.read_bytes() for f in (v.root/f'people/{p}').rglob('*') if f.is_file()}
    assert all((recovered.root/name).read_bytes()==data for name,data in before.items())
    assert not (recovered.root/f'people/{other}').exists()
    # Full recovery accounting must enumerate the actual retained source closure.
    raw=(receipt.path/'export.json').read_bytes(); manifest=decode_json(raw)
    manifest['sourceDisclosure']['plan']['originalSources']=[]
    manifest['sourceDisclosure']['plan']['sourceFiles']=[]
    manifest['sourceDisclosure']['review']['decision']['planSha256']=hash_bytes(encode_json(manifest['sourceDisclosure']['plan']))
    (receipt.path/'export.json').write_bytes(encode_json(manifest))
    assert verify_export(receipt.path).issues
    (receipt.path/'export.json').write_bytes(raw)



@pytest.mark.parametrize('attack',['plan','receipt','head','selection','person','source','unrecorded','source-data'])
def test_changed_or_untrusted_authority_denied(tmp_path,attack):
    from helseark.source_disclosure import prepare_disclosure, record_disclosure
    v,p,other,source=corpus(tmp_path); selection=ExportSelection('full-person')
    plan=prepare_disclosure(v,p,selection,tmp_path/'plan')
    if attack not in ('unrecorded','source-data'):record_disclosure(v,plan,decision(plan))
    if attack=='plan':
        value=decode_json((plan/'plan.json').read_bytes());value['personId']=other
        (plan/'plan.json').write_bytes(encode_json(value))
    elif attack=='receipt':
        value=decode_json((plan/'review.json').read_bytes());value['decision']['reason']='edited'
        (plan/'review.json').write_bytes(encode_json(value))
    elif attack=='head':
        from test_archive import update_payload
        payload=tmp_path/'update';base=update_payload(v,p,payload);_publish_change(v,p,payload,base)
    elif attack=='selection':selection=ExportSelection('selected-current')
    elif attack=='person':p=other
    elif attack=='source':source.write_bytes(b'changed source')
    elif attack=='source-data':(plan/'review.json').write_bytes(encode_json({'source_data':{'approved':True}}))
    with pytest.raises(ArchiveError):export_person(v,p,tmp_path/'denied',selection,review=plan)
    assert not (tmp_path/'denied').exists()


def test_reviewed_derivative_is_exchange_only(tmp_path):
    from helseark.source_disclosure import prepare_disclosure, record_disclosure
    v,p,_,source=corpus(tmp_path)
    derivative=tmp_path/'supplied.pdf';derivative.write_bytes(b'%PDF-1.4\nSYNTHETIC manually supplied derivative\n')
    supplied=[dict(sourceSha256=hash_bytes(source.read_bytes()),path=str(derivative),mediaType='application/pdf',
                   mapping='SYNTHETIC original page 1 to derivative page 1; not machine verified',
                   omissions='SYNTHETIC excluded page 2; evidence equivalence unsupported')]
    with pytest.raises(ArchiveError):prepare_disclosure(v,p,ExportSelection('full-person'),tmp_path/'bad',derivatives=supplied)
    selection=ExportSelection('selected-current')
    plan=prepare_disclosure(v,p,selection,tmp_path/'plan',derivatives=supplied)
    record_disclosure(v,plan,decision(plan))
    out=export_person(v,p,tmp_path/'exchange',selection,review=plan).path
    assert not verify_export(out).issues
    assert not (out/'sources').exists()
    assert (out/f'derivatives/{hash_bytes(derivative.read_bytes())}/blob').read_bytes()==derivative.read_bytes()
    assert source.read_bytes() not in [f.read_bytes() for f in out.rglob('*') if f.is_file()]
    disclosure=decode_json((out/'export.json').read_bytes())['sourceDisclosure']['plan']
    assert disclosure['originalDisposition']=='omitted-all'
    assert disclosure['derivatives'][0]['sourceSha256']==hash_bytes(source.read_bytes())
    assert 'evidence' in ' '.join(disclosure['limitations'])
    with pytest.raises(ArchiveError):restore(out,tmp_path/'not-recovery')
    # Same mode and closure, different explicit selection: intent is also bound.
    with pytest.raises(ArchiveError,match='REVIEW_MISMATCH'):
        export_person(v,p,tmp_path/'changed-selection',ExportSelection('selected-current',(ResourceRef('Patient',p),)),review=plan)

    derivative_plan=decode_json((plan/'plan.json').read_bytes())
    (plan/derivative_plan['derivatives'][0]['path']).write_bytes(b'changed')
    with pytest.raises(ArchiveError):export_person(v,p,tmp_path/'changed',selection,review=plan)


def test_only_explicit_complete_human_decisions_are_recorded(tmp_path):
    from copy import deepcopy
    from helseark.source_disclosure import prepare_disclosure, record_disclosure
    v,p,_,_=corpus(tmp_path)
    plan=prepare_disclosure(v,p,ExportSelection('full-person'),tmp_path/'plan')
    good=decision(plan)
    attacks=[]
    for field,value in [('humanReviewed',False),('confirmedPerson',False),('acknowledgedDisclosure',False),
                        ('reason',' '),('planSha256','0'*64),('format','helseark-source-decision-2'),
                        ('reviewer',{'kind':'model','label':'SYNTHETIC model output'}),
                        ('reviewer',{'kind':'local-user','label':' '})]:
        bad=deepcopy(good);bad[field]=value;attacks.append(bad)
    attacks += [{'source_data':good},good|{'source_scope_confirmed':True}]
    for bad in attacks:
        with pytest.raises(ArchiveError,match='REVIEW_MISMATCH'):record_disclosure(v,plan,bad)
        assert not (plan/'review.json').exists()
    record_disclosure(v,plan,good)
    with pytest.raises(ArchiveError,match='REVIEW_MISMATCH'):record_disclosure(v,plan,good)


def test_derivative_mapping_and_portable_accounting_fail_closed(tmp_path):
    from helseark.source_disclosure import prepare_disclosure, record_disclosure
    v,p,_,source=corpus(tmp_path)
    file=tmp_path/'derivative';file.write_bytes(b'SYNTHETIC supplied file')
    supplied=dict(sourceSha256=hash_bytes(source.read_bytes()),path=str(file),mediaType='application/pdf',
                  mapping='SYNTHETIC mapping',omissions='SYNTHETIC omission')
    for n,bad in enumerate([supplied|{'sourceSha256':'0'*64},supplied|{'omissions':''},supplied|{'path':str(file.parent)}]):
        with pytest.raises(ArchiveError):
            prepare_disclosure(v,p,ExportSelection('selected-current'),tmp_path/str(n),derivatives=[bad])
    plan=prepare_disclosure(v,p,ExportSelection('selected-current'),tmp_path/'plan',derivatives=[supplied])
    record_disclosure(v,plan,decision(plan))
    out=export_person(v,p,tmp_path/'out',ExportSelection('selected-current'),review=plan).path
    original=(out/'export.json').read_bytes()
    value=decode_json(original);value['sourceDisclosure']['plan']['derivatives'][0]['sourceSha256']='0'*64
    # Rehash the portable plan too: unsigned receipt cannot hide contradictory source accounting.
    value['sourceDisclosure']['review']['decision']['planSha256']=hash_bytes(encode_json(value['sourceDisclosure']['plan']))
    (out/'export.json').write_bytes(encode_json(value))
    assert verify_export(out).issues
    (out/'export.json').write_bytes(original)
    assert not verify_export(out).issues
