"""Real selected extraction capabilities, separate from model accuracy."""
from pathlib import Path
import json
import pytest
from test_intake import packet_for, PDF
from helseark.agent_context import read_agent_context, render_task_prompt, document, build_agent_context
from helseark.contracts import ArchiveError, ContextRequest
from helseark.serialization import decode_json, encode_json, hash_bytes


def header(text):
    return json.JSONDecoder().raw_decode(text.split('\n', 1)[1])[0]


def inputs(packet, tmp_path):
    text = (packet.path/'prompt.txt').read_text()
    data = decode_json(text.split('<SOURCE_DATA_JSON>\n')[1].split('\n</SOURCE_DATA_JSON>')[0].encode())
    return {'source_data':data, 'identity_confirmed':True, 'candidate_id':packet.importId,
            'output_directory':str(tmp_path/'fresh-output')}


def test_selected_exact_extraction_read_and_budget(tmp_path):
    vault, person, source, packet = packet_for(tmp_path, identityConfirmed=True)
    values = inputs(packet, tmp_path)
    context = read_agent_context(packet.path/'context')
    h = header((packet.path/'prompt.txt').read_text())
    extraction = values['source_data']['extractionPath']
    refs = [f for f in h['readableFiles'] if f['path']==extraction]
    assert len(refs)==1, 'Selected retained extraction has no authorized read receipt'
    raw = Path(extraction).read_bytes()
    assert refs[0]['sha256']==hash_bytes(raw)==values['source_data']['extractionReceipt']['pagesSha256']
    assert refs[0]['size']==len(raw)
    assert context.dataBytes==context.identity.size+len(raw)
    assert h['handoffDataBytes']==context.dataBytes+h['inlineDataBytes']
    assert len(context.selectedExtractions)==1
    with pytest.raises(ArchiveError, match='CONTEXT_AUTHORITY_REQUIRED'):
        render_task_prompt(context,'extract-report',values)
    rendered = render_task_prompt(context,'extract-report',values, trusted_context_sha256=packet.trustedContextSha256)
    assert header(rendered.text)['readableFiles']==h['readableFiles']


@pytest.mark.parametrize('attack',['extra','unselected','other-person','edited-context','edited-blob','symlink','rehashed-receipt'])
def test_extraction_cannot_expand_host_scope(tmp_path, attack):
    from helseark.intake import add_source, build_packet
    from helseark.archive import add_person
    from helseark.contracts import PersonDraft
    vault, person, source, packet = packet_for(tmp_path, identityConfirmed=True)
    values = inputs(packet,tmp_path)
    context = read_agent_context(packet.path/'context')
    if attack in ('extra','unselected','other-person'):
        owner = add_person(vault,PersonDraft('Unselected')) if attack=='other-person' else person
        extra = add_source(vault,owner,PDF/'lab-rotated.pdf')
        other = build_packet(vault,extra,tmp_path/'extra-packet')
        other_data=inputs(other,tmp_path)['source_data']
        values['source_data']['extractionPath']=other_data['extractionPath']
        if attack=='extra':
            values['source_data']['artifact']=other_data['artifact']
            values['source_data']['extractionReceipt']=other_data['extractionReceipt']
    elif attack=='rehashed-receipt':
        blob=decode_json(Path(values['source_data']['extractionPath']).read_bytes())
        blob['pages'][0]['text']='Invented replacement'
        raw=encode_json(blob); digest=hash_bytes(raw)
        p=vault.root/f'people/{person}/assets/sha256/{digest}/blob'
        p.parent.mkdir();p.write_bytes(raw)
        receipt=source.assetPath.parent/'extraction.json'
        data=decode_json(receipt.read_bytes());data['pagesSha256']=digest
        receipt.write_bytes(encode_json(data))
    elif attack=='edited-context':
        p=packet.path/'context/context.json'
        data=decode_json(p.read_bytes())
        data['selectedExtractions'][0]['path']=str(tmp_path/'invented')
        p.write_bytes(encode_json(data))
        context=read_agent_context(p.parent)
    else:
        p=Path(values['source_data']['extractionPath'])
        if attack=='symlink':
            original=p.read_bytes(); p.unlink(); target=tmp_path/'copy'; target.write_bytes(original); p.symlink_to(target)
        else: p.write_bytes(b'{}')
    with pytest.raises(ArchiveError):
        render_task_prompt(context,'extract-report',values,trusted_context_sha256=packet.trustedContextSha256)


def test_extraction_budget_and_legacy_no_implicit_reads(tmp_path):
    vault,person,source,packet=packet_for(tmp_path,identityConfirmed=True)
    raw=Path(inputs(packet,tmp_path)['source_data']['extractionPath']).read_bytes()
    identity=read_agent_context(packet.path/'context').identity.size
    with pytest.raises(ArchiveError,match='CONTEXT_BUDGET_EXCEEDED'):
        build_agent_context(vault,person,'import',ContextRequest(sourceHashes=(source.sourceSha256,),
            includeSourceExtractions=True,maxDataBytes=identity+len(raw)-1),tmp_path/'too-small')
    legacy=build_agent_context(vault,person,'import',ContextRequest(sourceHashes=(source.sourceSha256,)),tmp_path/'legacy')
    assert 'selectedExtractions' not in document(legacy)
    h=header(render_task_prompt(legacy,'extract-report',inputs(packet,tmp_path)).text)
    assert not any(f['path']==str(Path(inputs(packet,tmp_path)['source_data']['extractionPath'])) for f in h['readableFiles'])
    assert legacy.dataBytes==identity


def test_supplementary_independent_qualitative_is_a_value_under_review(tmp_path):
    """Pre-authored candidate proves expressiveness, never model compliance."""
    from uuid import uuid4
    from helseark.intake import read_candidate
    from helseark.validation import validate_candidate
    from helseark.contracts import Issue
    vault,person,source,packet=packet_for(tmp_path,'task5-distinct-results.pdf',identityConfirmed=True)
    data=inputs(packet,tmp_path)['source_data']
    facts=decode_json((PDF.parent/'expected/intake-distinct-facts.json').read_bytes())
    replacements={'11111111-1111-4111-8111-111111111111':person,
        'SOURCE_HASH':source.sourceSha256,'EXTRACTION_HASH':data['extractionReceipt']['pagesSha256'],
        'Analyte Q':facts['quantity']['label'],'Qualitative':facts['qualitative']['label'],
        'not detected':facts['qualitative']['value'],'0.050':facts['quantity']['valueToken'],
        '0,050':facts['quantity']['valueToken'].replace('.',','), '"<"':'">"', '<2,700':'>2,700'}
    example=Path(__file__).resolve().parents[1]/'agent-kit/examples'
    def bound(name):
        text=(example/name).read_text()
        for old,new in replacements.items(): text=text.replace(old,new)
        return decode_json(text.encode())
    candidate=tmp_path/'candidate';candidate.mkdir()
    meta={'contractVersion':'0.1.0','fhirVersion':'4.0.1','profileVersion':'0.1.0',
        'candidateId':str(uuid4()),'personId':person,
        'baseChangeSha256':read_agent_context(packet.path/'context').base.changeSha256,
        'sourceSha256':[source.sourceSha256],'bundlePath':'bundle.json','evidencePath':'evidence.json',
        'producer':{'kind':'local-user','name':'supplementary pre-authored fixture'},
        'producerProvenance':bound('task5-evidence.json')['producerProvenance'],
        'unresolved':data['issues']+[document(Issue('QUALITATIVE_ATTRIBUTION_REVIEW','review',None,None,
            'Review both independently labeled assertions and their source context.'))]}
    for name,value in [('candidate.json',meta),('bundle.json',bound('task5-bundle.json')),('evidence.json',bound('task5-evidence.json'))]:
        (candidate/name).write_bytes(encode_json(value))
    c=read_candidate(vault,candidate,person=person)
    report=validate_candidate(vault,c)
    assert not [i for i in report.issues if i.severity=='error'],report
    observations=[e['resource'] for e in c.bundle['entry'] if e['resource']['resourceType']=='Observation']
    assert len(observations)==facts['observationCount']
    q,r=observations
    assert str(q['valueQuantity']['value'])==facts['quantity']['valueToken']
    assert q['valueQuantity']['comparator']==facts['quantity']['comparator']
    assert r['code']=={'text':facts['qualitative']['label']}
    assert r['valueString']==facts['qualitative']['value']
    assert 'note' not in r and 'interpretation' not in r
    assert all(o['status']==facts['status'] and o['effectiveDateTime']==facts['date'] for o in observations)
    assert any(i.severity=='review' for i in report.issues)
    # Missing required status is blocked, never filled in by intake/validation.
    del r['status']
    (candidate/'bundle.json').write_bytes(encode_json(c.bundle))
    missing=validate_candidate(vault,read_candidate(vault,candidate,person=person))
    assert any(i.severity=='error' for i in missing.issues)


@pytest.mark.parametrize('value',[None,[],"extractionPath"])
def test_extraction_context_invalid_source_data_is_typed_error(tmp_path,value):
    _,_,_,packet=packet_for(tmp_path,identityConfirmed=True)
    context=read_agent_context(packet.path/'context')
    with pytest.raises(ArchiveError,match='INVALID_VARIABLE'):
        render_task_prompt(context,'extract-report',{**inputs(packet,tmp_path),'source_data':value},
            trusted_context_sha256=packet.trustedContextSha256)


def test_missing_retained_extraction_never_regenerates_during_render(tmp_path,monkeypatch):
    import helseark.intake as intake
    _,_,source,packet=packet_for(tmp_path,identityConfirmed=True)
    context=read_agent_context(packet.path/'context')
    (source.assetPath.parent/'extraction.json').unlink()
    def unexpected(*args,**kwargs):
        raise AssertionError('Verification must not extract or write')
    monkeypatch.setattr(intake,'extract_pdf',unexpected)
    with pytest.raises(ArchiveError,match='INTEGRITY'):
        render_task_prompt(context,'extract-report',inputs(packet,tmp_path),
            trusted_context_sha256=packet.trustedContextSha256)
    assert not (source.assetPath.parent/'extraction.json').exists()
