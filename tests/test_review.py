"""Real synthetic packet through human review; these fixtures are not model evidence."""
from datetime import datetime, timezone
from dataclasses import replace
from uuid import UUID
import shutil
import pytest
from test_intake import supplied_candidate
from helseark.archive import head, open_vault, resolve
from helseark.contracts import ArchiveError, ReviewDecision, ResourceRef
from helseark.serialization import decode_json, encode_json


def prepare(vault, candidate, **kwargs):
    from helseark.intake import prepare_candidate
    ids = iter(UUID(int=(4 << 76) | (2 << 62) | n) for n in range(1, 100))
    return prepare_candidate(vault, candidate, clock=lambda: datetime(2026,11,14,20,tzinfo=timezone.utc),
                             uuid_factory=lambda: next(ids), **kwargs)


def approve(vault, proposal):
    from helseark.review import render_review, record_review
    view = render_review(vault, proposal)
    acks = tuple({'code':i['code'], 'resourceRef':i['resourceRef'], 'reason':'Human checked original and retained limitation.'}
                 for i in view.issues if i['severity'] in ('review','warning'))
    return record_review(vault, proposal, ReviewDecision(True, 'accept-with-acknowledged-limitations', acks, 'synthetic human'))


def test_pdf_packet_to_reviewed_record_to_reopen(tmp_path):
    from helseark.archive import commit_candidate
    from helseark.review import render_review
    vault, person, source, packet, candidate = supplied_candidate(tmp_path)
    # Independently pre-authored native report groups both emitted measurements.
    from copy import deepcopy
    from pathlib import Path
    from helseark.intake import read_candidate
    report=decode_json((Path(__file__).parent/'fixtures/synthetic/task6-report.json').read_bytes().replace(b'PERSON',person.encode()))
    report_ref='urn:uuid:'+report['id']
    candidate.bundle['entry'].append({'fullUrl':report_ref,'resource':report})
    template=next(e for e in candidate.evidence['entries'] if e['kind']=='source')
    for pointer,quote in [('/status','Status: final'),('/code/text','Report: Synthetic laboratory report'),
        ('/subject/reference','Patient: Avery Synthetic'),('/effectiveDateTime','Collected: 2026-01'),
        ('/result/0/reference','Analyte Q: <0,050 mg/L'),('/result/1/reference','Qualitative: not detected')]:
        entry=deepcopy(template);entry['target']={'reference':report_ref,'pointers':[pointer]};entry['quote']=quote
        candidate.evidence['entries'].append(entry)
    candidate.evidence['entries'].append({'target':{'reference':report_ref,'pointers':['/id','/meta/profile/0']},'kind':'generated','rule':'synthetic-report-fixture-1'})
    (candidate.path/'bundle.json').write_bytes(encode_json(candidate.bundle));(candidate.path/'evidence.json').write_bytes(encode_json(candidate.evidence))
    metadata=decode_json((candidate.path/'candidate.json').read_bytes())
    metadata['producer']={'kind':'external-agent','name':'pre-authored synthetic external-agent candidate; no model run'}
    (candidate.path/'candidate.json').write_bytes(encode_json(metadata))
    candidate=read_candidate(vault,candidate.path)
    proposal = prepare(vault,candidate)
    view = render_review(vault, proposal)
    assert len([r for r in view.resourcesAdded if r['resourceType']=='Observation']) == 2
    assert view.sourceLinks and view.validationCoverage
    receipt = approve(vault,proposal)
    result = commit_candidate(vault,proposal,receipt)
    assert result.disposition == 'committed' and result.head.sequence == 2
    assert commit_candidate(vault,proposal,receipt).disposition == 'already-accepted'
    shutil.rmtree(candidate.path); shutil.rmtree(packet.path)
    shutil.rmtree(vault.root/'work')
    reopened = open_vault(vault.root)
    observations = [r for r in result.logicalResources if r.resourceType=='Observation']
    report_ref=next(r for r in result.logicalResources if r.resourceType=='DiagnosticReport')
    report=resolve(reopened,person,report_ref)
    parts=report['result'][0]['reference'].split('/')
    q = resolve(reopened,person,ResourceRef(parts[0],parts[1],parts[3]))
    assert str(q['valueQuantity']['value']) == '0.050'
    assert q['valueQuantity']['comparator'] == '<' and q['valueQuantity']['unit']=='mg/L'
    import subprocess,sys
    child=subprocess.run([sys.executable,'-c', '''import sys
from pathlib import Path
from helseark.archive import open_vault,resolve
from helseark.contracts import ResourceRef
from helseark.serialization import encode_json
v=open_vault(Path(sys.argv[1]));r=resolve(v,sys.argv[2],ResourceRef('DiagnosticReport',sys.argv[3]))
p=r['result'][0]['reference'].split('/')
sys.stdout.buffer.write(encode_json(resolve(v,sys.argv[2],ResourceRef(p[0],p[1],p[3]))))
''',str(vault.root),person,report_ref.id],capture_output=True)
    assert child.returncode==0,child.stderr
    assert str(decode_json(child.stdout)['valueQuantity']['value'])=='0.050'
    accepted = vault.root/f'people/{person}/accepted/{result.head.sequence:08d}-{result.head.transactionId}'
    evidence = decode_json((accepted/'evidence.json').read_bytes())
    assert any(e.get('sourceSha256')==source.sourceSha256 and e.get('locator',{}).get('page')==1 for e in evidence['entries'])
    assert (accepted/'proposal.json').read_bytes() == encode_json(decode_json((accepted/'proposal.json').read_bytes()))


@pytest.mark.parametrize('target',['candidate','resource','source','validation','evidence','proposal','extraction','receipt','derived','source-receipt','input','metadata'])
def test_bound_byte_edit_invalidates_review(tmp_path,target):
    from helseark.archive import commit_candidate
    vault,person,source,packet,candidate = supplied_candidate(tmp_path)
    proposal=prepare(vault,candidate); receipt=approve(vault,proposal); before=head(vault,person)
    inventory=decode_json((proposal.path/'proposal.json').read_bytes())
    path={'candidate':candidate.path/'bundle.json','resource':proposal.path/inventory['resources'][0]['path'],
          'source':source.assetPath,'validation':proposal.path/'validation.json','evidence':proposal.path/'evidence.json',
          'proposal':proposal.path/'proposal.json','extraction':source.assetPath.parent/'extraction.json','receipt':receipt.path, 'derived':vault.root/f"people/{person}/assets/sha256/{decode_json((source.assetPath.parent/'extraction.json').read_bytes())['pagesSha256']}/blob", 'source-receipt':source.assetPath.parent/'source.json', 'input':proposal.path/'inputs/bundle.json', 'metadata':candidate.path/'candidate.json'}[target]
    path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ArchiveError): commit_candidate(vault,proposal,receipt)
    # Source corruption makes history verification fail; inspect immutable count directly.
    assert len(list((vault.root/f'people/{person}/accepted').iterdir()))==before.sequence


def test_concurrent_change_makes_review_stale(tmp_path):
    from helseark.archive import commit_candidate, _publish_change
    from test_archive import update_payload
    vault,person,_,_,candidate=supplied_candidate(tmp_path)
    proposal=prepare(vault,candidate); receipt=approve(vault,proposal)
    payload=tmp_path/'concurrent'; base=update_payload(vault,person,payload)
    _publish_change(vault,person,payload,base)
    with pytest.raises(ArchiveError,match='STALE_BASE'): commit_candidate(vault,proposal,receipt)
    assert head(vault,person).sequence==2


def test_unconfirmed_identity_cannot_be_acknowledged(tmp_path):
    from helseark.review import record_review
    vault,_,_,_,candidate=supplied_candidate(tmp_path); proposal=prepare(vault,candidate)
    with pytest.raises(ArchiveError):
        record_review(vault,proposal,ReviewDecision(False,'accept-with-acknowledged-limitations',(), 'human'))


def test_duplicate_uuid_candidate_fails(tmp_path):
    from helseark.intake import read_candidate
    vault,person,_,_,candidate=supplied_candidate(tmp_path)
    bundle=candidate.bundle; bundle['entry'].append(bundle['entry'][0])
    (candidate.path/'bundle.json').write_bytes(encode_json(bundle))
    with pytest.raises(ArchiveError,match='VALIDATION_BLOCKED'): prepare(vault,read_candidate(vault,candidate.path))
    assert head(vault,person).sequence==1


def rerun_candidate(vault, candidate, **changes):
    from helseark.intake import read_candidate
    meta=decode_json((candidate.path/'candidate.json').read_bytes())
    meta.update(baseChangeSha256=head(vault,candidate.personId).changeSha256, **changes)
    (candidate.path/'candidate.json').write_bytes(encode_json(meta))
    return read_candidate(vault,candidate.path)


def test_same_source_renamed_is_existing_import_before_allocation(tmp_path):
    from helseark.archive import commit_candidate
    from helseark.intake import prepare_candidate, add_source, read_candidate
    vault,person,source,_,candidate=supplied_candidate(tmp_path)
    proposal=prepare(vault,candidate); receipt=approve(vault,proposal)
    committed=commit_candidate(vault,proposal,receipt)
    def forbidden(): raise AssertionError('Must not allocate metadata for an accepted import')
    # Exact original candidate can be reloaded despite its historical base.
    exact=prepare_candidate(vault,read_candidate(vault,candidate.path),clock=forbidden,uuid_factory=forbidden)
    assert exact.path.name.endswith(committed.head.transactionId)
    renamed=tmp_path/'renamed.pdf'; renamed.write_bytes(source.assetPath.read_bytes())
    assert add_source(vault,person,renamed).sourceSha256==source.sourceSha256
    candidate=rerun_candidate(vault,candidate)
    repeated=prepare_candidate(vault,candidate,clock=forbidden,uuid_factory=forbidden)
    assert repeated.proposalSha256==proposal.proposalSha256
    from helseark.review import read_prepared
    accepted_receipt=decode_json((repeated.path/'review.json').read_bytes())
    from helseark.contracts import ReviewReceipt
    from helseark.serialization import hash_bytes
    receipt=ReviewReceipt(repeated.path/'review.json',repeated.proposalSha256,accepted_receipt['validationSha256'],repeated.base,hash_bytes((repeated.path/'review.json').read_bytes()))
    assert commit_candidate(vault,repeated,receipt).disposition=='already-accepted'
    assert head(vault,person).sequence==2


def test_changed_extraction_omission_is_explicit_and_preserved(tmp_path):
    from helseark.archive import commit_candidate, iter_current
    from helseark.intake import read_candidate, prepare_candidate
    from helseark.review import render_review
    vault,person,_,_,candidate=supplied_candidate(tmp_path)
    proposal=prepare(vault,candidate); commit_candidate(vault,proposal,approve(vault,proposal))
    initial=decode_json((proposal.path/'proposal.json').read_bytes())
    missing=initial['resources'][1]
    candidate=rerun_candidate(vault,candidate)
    removed=candidate.bundle['entry'].pop(1)['fullUrl']
    candidate.evidence['entries'][:]=[e for e in candidate.evidence['entries'] if e.get('target',{}).get('reference')!=removed]
    (candidate.path/'bundle.json').write_bytes(encode_json(candidate.bundle))
    (candidate.path/'evidence.json').write_bytes(encode_json(candidate.evidence))
    candidate=read_candidate(vault,candidate.path)
    with pytest.raises(ArchiveError,match='REEXTRACTION_REQUIRED'): prepare_candidate(vault,candidate)
    second=prepare_candidate(vault,candidate,reextract=True)
    view=render_review(vault,second)
    assert f"Observation/{missing['id']}" in view.omissions
    assert view.revisionsChanged and all(r['resource']['status'] in ('current','final') for r in view.revisionsChanged)
    commit_candidate(vault,second,approve(vault,second))
    assert len([r for r in iter_current(vault,person) if r['resourceType']=='Observation'])==2
    assert resolve(vault,person,ResourceRef('Observation',missing['id'],missing['versionId']))['valueString']=='not detected'


def test_changed_ocr_anchor_requires_explicit_reconciliation(tmp_path):
    from helseark.archive import commit_candidate
    from helseark.intake import prepare_candidate, read_candidate
    vault,person,_,_,candidate=supplied_candidate(tmp_path)
    p=prepare(vault,candidate); commit_candidate(vault,p,approve(vault,p))
    candidate=rerun_candidate(vault,candidate)
    # A different but still source-consistent quote changes the local anchor.
    for e in candidate.evidence['entries']:
        if e.get('quote')=='Analyte Q: <0,050 mg/L': e['quote']='<0,050 mg/L'
    (candidate.path/'evidence.json').write_bytes(encode_json(candidate.evidence))
    candidate=read_candidate(vault,candidate.path)
    with pytest.raises(ArchiveError,match='RECONCILIATION_REQUIRED'): prepare_candidate(vault,candidate,reextract=True)
    original=decode_json((p.path/'proposal.json').read_bytes())['resources'][0]
    mapping={candidate.bundle['entry'][0]['fullUrl']:ResourceRef('Observation',original['id'])}
    second=prepare_candidate(vault,candidate,reextract=True,reconciliation=mapping)
    commit_candidate(vault,second,approve(vault,second))
    assert resolve(vault,person,ResourceRef('Observation',original['id']))['meta']['versionId']!=original['versionId']


@pytest.mark.parametrize('conflicting',[False,True])
def test_different_sources_equal_values_and_conflicts_remain_separate(tmp_path,conflicting):
    from helseark.intake import add_source, build_packet, prepare_candidate, read_candidate
    from helseark.archive import commit_candidate, iter_current
    from helseark.review import render_review
    vault,person,source,_,candidate=supplied_candidate(tmp_path)
    first=prepare(vault,candidate); commit_candidate(vault,first,approve(vault,first))
    # PDF comments change the source bytes without changing its clinical assertion.
    external=tmp_path/'independent.pdf'
    if conflicting:
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import DecodedStreamObject, NameObject
        writer=PdfWriter(clone_from=PdfReader(source.assetPath))
        stream=DecodedStreamObject()
        stream.set_data(writer.pages[0].get_contents().get_data().replace(b'<0,050',b'<0,075'))
        writer.pages[0][NameObject('/Contents')]=stream
        writer.write(external)
    else: external.write_bytes(source.assetPath.read_bytes()+b'\n% independent synthetic issuer\n')
    other=add_source(vault,person,external)
    packet=build_packet(vault,other,tmp_path/'packet-two',identityConfirmed=True)
    meta=decode_json((packet.path/'intake.json').read_bytes())
    data=(candidate.path/'evidence.json').read_bytes().replace(source.sourceSha256.encode(),other.sourceSha256.encode())
    old=decode_json((source.assetPath.parent/'extraction.json').read_bytes())['pagesSha256']
    data=data.replace(old.encode(),meta['extraction']['pagesSha256'].encode())
    if conflicting: data=data.replace(b'<0,050',b'<0,075')
    (candidate.path/'evidence.json').write_bytes(data)
    bundle=(candidate.path/'bundle.json').read_bytes().replace(source.sourceSha256.encode(),other.sourceSha256.encode())
    if conflicting: bundle=bundle.replace(b'0.050',b'0.075')
    (candidate.path/'bundle.json').write_bytes(bundle)
    candidate=rerun_candidate(vault,candidate,sourceSha256=[other.sourceSha256],candidateId=meta['importId'])
    second=prepare_candidate(vault,candidate)
    view=render_review(vault,second)
    assert view.duplicateCandidates and any(i['code']=='POSSIBLE_DUPLICATE_OR_CONTRADICTION' for i in view.issues)
    commit_candidate(vault,second,approve(vault,second))
    observations=[r for r in iter_current(vault,person) if r['resourceType']=='Observation']
    assert len(observations)==4
    assert len({r['id'] for r in observations})==4
    assert sorted(str(r['valueQuantity']['value']) for r in observations if 'valueQuantity' in r)==(['0.050','0.075'] if conflicting else ['0.050','0.050'])
    # Conflicting extraction from independent source still does not supersede first.
    assert all(i['supersedesVersionId'] is None for i in decode_json((second.path/'proposal.json').read_bytes())['resources'])


@pytest.mark.parametrize('code',['SOURCE_IDENTITY_UNRESOLVED','IDENTITY_UNRESOLVED','UNSUPPORTED_MODIFIER'])
def test_blocking_error_cannot_be_acknowledged(tmp_path,code):
    from helseark.intake import read_candidate
    vault,person,_,_,candidate=supplied_candidate(tmp_path)
    metadata=decode_json((candidate.path/'candidate.json').read_bytes())
    metadata['unresolved'].append({'code':code,'severity':'error','pointer':None,'resourceRef':None,'message':'Synthetic blocking uncertainty'})
    (candidate.path/'candidate.json').write_bytes(encode_json(metadata))
    with pytest.raises(ArchiveError,match='VALIDATION_BLOCKED'): prepare(vault,read_candidate(vault,candidate.path))
    assert head(vault,person).sequence==1


def test_human_must_acknowledge_exact_limitations(tmp_path):
    from helseark.review import record_review
    vault,_,_,_,candidate=supplied_candidate(tmp_path); p=prepare(vault,candidate)
    with pytest.raises(ArchiveError,match='REVIEW_REQUIRED'): record_review(vault,p,ReviewDecision(True,'accept',(), 'human'))


def test_preparation_uses_injected_clock_and_uuid_once(tmp_path):
    vault,_,_,_,candidate=supplied_candidate(tmp_path); p=prepare(vault,candidate)
    inventory=decode_json((p.path/'proposal.json').read_bytes())
    assert inventory['transactionId']==str(UUID(int=(4<<76)|(2<<62)|1))
    assert all(decode_json((p.path/i['path']).read_bytes())['meta']['lastUpdated']=='2026-11-14T20:00:00Z' for i in inventory['resources'])


@pytest.mark.parametrize('boundary,sequence',[('before-rename',1),('after-rename',2)])
def test_reviewed_publication_real_process_death(tmp_path,boundary,sequence):
    import os, subprocess, sys
    from test_cli_journey import run
    from helseark.archive import commit_candidate
    vault,person,_,_,candidate=supplied_candidate(tmp_path)
    p=prepare(vault,candidate); receipt=approve(vault,p)
    child=run('--vault',vault.root,'candidate','commit',p.path,'--person',person,'--json',env={**os.environ,'_HELSEARK_TEST_CRASH_AT':boundary})
    assert child.returncode==91,child.stderr
    reopened=open_vault(vault.root)
    assert head(reopened,person).sequence==sequence
    retry=commit_candidate(reopened,p,receipt)
    assert retry.disposition==('committed' if sequence==1 else 'already-accepted')
    assert head(reopened,person).sequence==2


def test_mutable_packet_cannot_broaden_source_authority(tmp_path):
    from helseark.intake import add_source, build_packet, prepare_candidate, read_candidate
    from test_intake import PDF
    vault,person,_,packet,candidate=supplied_candidate(tmp_path)
    other=add_source(vault,person,PDF/'lab-text.pdf')
    build_packet(vault,other,tmp_path/'other-packet',identityConfirmed=True)
    metadata=decode_json((candidate.path/'candidate.json').read_bytes())
    metadata['sourceSha256'].append(other.sourceSha256)
    (candidate.path/'candidate.json').write_bytes(encode_json(metadata))
    forged=decode_json((packet.path/'intake.json').read_bytes()); forged['source']['sourceSha256']=other.sourceSha256
    (packet.path/'intake.json').write_bytes(encode_json(forged))
    candidate=read_candidate(vault,candidate.path)
    with pytest.raises(ArchiveError,match='SOURCE_SCOPE_MISMATCH'): prepare_candidate(vault,candidate)
    assert head(vault,person).sequence==1


def test_mutable_packet_cannot_confirm_host_identity(tmp_path):
    from helseark.intake import build_packet, prepare_candidate, read_candidate
    vault,person,source,_,candidate=supplied_candidate(tmp_path)
    packet=build_packet(vault,source,tmp_path/'unconfirmed',identityConfirmed=False)
    forged=decode_json((packet.path/'intake.json').read_bytes());forged['identityConfirmed']=True
    (packet.path/'intake.json').write_bytes(encode_json(forged))
    metadata=decode_json((candidate.path/'candidate.json').read_bytes());metadata['candidateId']=packet.importId
    (candidate.path/'candidate.json').write_bytes(encode_json(metadata))
    with pytest.raises(ArchiveError,match='IDENTITY_UNCONFIRMED'): prepare_candidate(vault,read_candidate(vault,candidate.path))
    assert head(vault,person).sequence==1


def test_generated_provenance_does_not_authorize_clinical_reason(tmp_path):
    from helseark.validation import validate_proposal
    from helseark.serialization import hash_bytes
    vault,_,_,_,candidate=supplied_candidate(tmp_path);p=prepare(vault,candidate)
    inventory=decode_json((p.path/'proposal.json').read_bytes());item=next(i for i in inventory['resources'] if i['type']=='Provenance')
    resource=decode_json((p.path/item['path']).read_bytes());resource['reason']=[{'text':'invented clinical rationale'}]
    (p.path/item['path']).write_bytes(encode_json(resource));item['sha256']=hash_bytes(encode_json(resource))
    evidence=decode_json((p.path/'evidence.json').read_bytes())
    entry=next(e for e in evidence['entries'] if e.get('rule')=='prepare-provenance-1');entry['target']['pointers'].append('/reason')
    (p.path/'evidence.json').write_bytes(encode_json(evidence));inventory['evidenceSha256']=hash_bytes(encode_json(evidence))
    (p.path/'proposal.json').write_bytes(encode_json(inventory))
    report=validate_proposal(vault,p.path)
    assert any(i.code=='GENERATED_CLINICAL_EVIDENCE' and i.severity=='error' for i in report.issues)


def test_missing_unaccepted_review_is_explicitly_review_needed(tmp_path):
    from helseark.intake import prepare_candidate
    from test_cli_journey import run
    v,p,_,_,c=supplied_candidate(tmp_path)
    proposal=prepare_candidate(v,c)
    child=run('--vault',v.root,'candidate','commit',proposal.path,'--person',p,'--json')
    assert child.returncode==3 and b'REVIEW_REQUIRED' in child.stderr
    assert head(v,p).sequence==1
