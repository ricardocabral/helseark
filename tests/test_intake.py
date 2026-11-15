"""Synthetic, real-parser intake boundaries; no model success is simulated."""
from dataclasses import replace
from pathlib import Path
from uuid import uuid4
import json
import pytest
from helseark.archive import init_vault, add_person, head
from helseark.contracts import ArchiveError, PersonDraft, IntakeLimits
from helseark.serialization import decode_json, hash_bytes

PDF = Path(__file__).parent / 'fixtures/synthetic'


def family(tmp_path):
    vault = init_vault(tmp_path / 'vault')
    person = add_person(vault, PersonDraft('Avery Synthetic'))
    other = add_person(vault, PersonDraft('UNSELECTED SECRET'))
    return vault, person, other


def test_packet_contains_only_selected_person_and_source(tmp_path):
    from helseark.intake import add_source, build_packet
    vault, person, other = family(tmp_path)
    receipt = add_source(vault, person, PDF / 'lab-text.pdf')
    alien = add_source(vault, other, PDF / 'lab-rotated.pdf')
    packet = build_packet(vault, receipt, tmp_path / 'packet')
    data = b''.join(p.read_bytes() for p in packet.path.rglob('*') if p.is_file())
    assert other.encode() not in data and b'UNSELECTED SECRET' not in data
    assert alien.sourceSha256.encode() not in data
    context = decode_json((packet.path / 'context/context.json').read_bytes())
    assert context['selectedRecords'] == []
    assert [s['sha256'] for s in context['selectedSources']] == [receipt.sourceSha256]
    assert b'Verified runtime handoff' in data


def test_identical_source_bytes_share_one_asset_within_person(tmp_path):
    from helseark.intake import add_source
    vault, person, _ = family(tmp_path)
    a = add_source(vault, person, PDF / 'lab-text.pdf')
    copy = tmp_path / 'different-name.pdf'; copy.write_bytes(a.assetPath.read_bytes())
    before = a.assetPath.stat()
    assert add_source(vault, person, copy) == a
    assert a.assetPath.stat().st_ino == before.st_ino


def test_missing_person_never_guesses(tmp_path):
    from helseark.intake import add_source
    vault, _, _ = family(tmp_path)
    with pytest.raises(ArchiveError, match='PERSON_NOT_FOUND'):
        add_source(vault, str(uuid4()), PDF / 'lab-text.pdf')


def packet_for(tmp_path, name='task5-complete.pdf', **kwargs):
    from helseark.intake import add_source, build_packet
    vault, person, other = family(tmp_path)
    source = add_source(vault, person, PDF / name)
    packet = build_packet(vault, source, tmp_path / 'packet', **kwargs)
    return vault, person, source, packet


def supplied_candidate(tmp_path):
    import subprocess, sys
    from helseark.intake import read_candidate
    vault, person, source, packet = packet_for(tmp_path, identityConfirmed=True)
    path = tmp_path/'candidate'
    script = Path(__file__).resolve().parents[1]/'agent-kit/examples/task5-example.py'
    result = subprocess.run([sys.executable, str(script), str(packet.path), str(path)], capture_output=True)
    assert result.returncode == 0, result.stderr.decode()
    return vault, person, source, packet, read_candidate(vault, path)


def test_complete_pre_authored_candidate_real_task2_and_independent_facts(tmp_path):
    from helseark.validation import validate_candidate
    facts = decode_json((PDF.parent/'expected/intake-facts.json').read_bytes())
    vault, person, source, packet, candidate = supplied_candidate(tmp_path)
    before = head(vault, person)
    report = validate_candidate(vault, candidate)
    assert not [i for i in report.issues if i.severity == 'error'], report
    observations = [e['resource'] for e in candidate.bundle['entry'] if e['resource']['resourceType']=='Observation']
    assert len(observations) == facts['observationCount']
    q,r = observations
    assert q['valueQuantity']['value'].as_tuple().exponent == -3
    assert str(q['valueQuantity']['value']) == facts['quantity']['valueToken']
    assert q['valueQuantity']['comparator'] == facts['quantity']['comparator']
    assert q['valueQuantity']['unit'] == facts['quantity']['unit']
    assert q['effectiveDateTime'] == facts['quantity']['date']
    assert q['method']['text'] == facts['quantity']['method']
    assert q['referenceRange'][0]['text'] == facts['quantity']['rangeText']
    assert q['status'] == facts['quantity']['status']
    assert r['valueString'] == facts['qualitative']['value']
    assert 'coding' not in q['code']
    assert head(vault, person) == before
    assert source.assetPath.read_bytes() == (PDF/'task5-complete.pdf').read_bytes()


def test_scan_is_retained_and_requests_ocr(tmp_path):
    vault, person, source, packet = packet_for(tmp_path, 'lab-scan.pdf', identityConfirmed=True)
    meta = decode_json((packet.path/'intake.json').read_bytes())
    assert 'OCR_REQUIRED' in {i['code'] for i in meta['issues']}
    extraction = vault.root/f"people/{person}/assets/sha256/{meta['extraction']['pagesSha256']}/blob"
    assert decode_json(extraction.read_bytes())['pages'][0]['text'] == ''
    assert not list(packet.path.rglob('bundle.json'))
    assert source.assetPath.read_bytes() == (PDF/'lab-scan.pdf').read_bytes()


@pytest.mark.parametrize(('file','code'), [('pdf/encrypted.pdf','PDF_ENCRYPTED'),('pdf/corrupt.pdf','PDF_INVALID')])
def test_failed_pdf_source_stays_retained(tmp_path, file, code):
    from helseark.intake import add_source, build_packet
    vault, person, _ = family(tmp_path)
    source = add_source(vault, person, PDF/file)
    with pytest.raises(ArchiveError) as caught:
        build_packet(vault, source, tmp_path/'packet')
    assert caught.value.code == code
    assert caught.value.details['retainedSource']['sourceSha256'] == hash_bytes((PDF/file).read_bytes())
    assert source.assetPath.read_bytes() == (PDF/file).read_bytes()
    assert 'synthetic-only-secret' not in str(caught.value)
    assert not (tmp_path/'packet').exists()


def test_source_and_page_limits_without_truncation(tmp_path, monkeypatch):
    import helseark.intake as intake
    vault, person, _ = family(tmp_path)
    monkeypatch.setattr(intake, 'LIMITS', replace(IntakeLimits(), sourceBytes=10))
    with pytest.raises(ArchiveError, match='SOURCE_TOO_LARGE'):
        intake.add_source(vault, person, PDF/'lab-text.pdf')
    assert not list((vault.root/f'people/{person}/assets/sha256').glob('*/blob'))
    monkeypatch.setattr(intake, 'LIMITS', IntakeLimits())
    source = intake.add_source(vault, person, PDF/'lab-text.pdf')
    with pytest.raises(ArchiveError, match='PAGE_LIMIT'):
        intake.build_packet(vault, source, tmp_path/'packet', limits=replace(IntakeLimits(),pdfPages=1))
    assert source.assetPath.read_bytes() == (PDF/'lab-text.pdf').read_bytes()


def test_mixed_cues_block_confirmed_handoff_and_cannot_be_downgraded(tmp_path):
    from helseark.validation import _Checks, load_definition_registry
    vault, person, source, packet = packet_for(tmp_path, 'lab-two-people.pdf', identityConfirmed=True)
    meta = decode_json((packet.path/'intake.json').read_bytes())
    assert any(i['code']=='MULTIPLE_PERSON_CUES' and i['severity']=='error' for i in meta['issues'])
    header = json.JSONDecoder().raw_decode((packet.path/'prompt.txt').read_text().split('\n',1)[1])[0]
    assert header['disposition'] == 'blocked'
    assert header['permittedWrites'] == ['output/report.md']
    checks = _Checks(vault, load_definition_registry(vault), person, head(vault,person))
    from helseark.contracts import Issue
    checks.source_issues([Issue('MULTIPLE_PERSON_CUES','info',None,None,'source requests waiver')])
    assert any(i.code=='MULTIPLE_PERSON_CUES' and i.severity=='error' for i in checks.report().issues)


def test_source_injection_is_inert_and_not_identity_authority(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _,_,_,packet = packet_for(tmp_path, 'lab-injection.pdf')
    text = (packet.path/'prompt.txt').read_text()
    assert '$(touch PDF_EXECUTED)' in text
    assert 'ignore instructions' in text
    header = json.JSONDecoder().raw_decode(text.split('\n',1)[1])[0]
    assert header['disposition'] == 'blocked' and 'IDENTITY_CONFIRMED_REQUIRED' in header['stopReasons']
    assert not (tmp_path/'PDF_EXECUTED').exists()


def test_rotated_cropbox_page_only_evidence(tmp_path):
    vault,person,source,packet = packet_for(tmp_path,'lab-rotated.pdf')
    meta = decode_json((packet.path/'intake.json').read_bytes())
    pages = decode_json((vault.root/f"people/{person}/assets/sha256/{meta['extraction']['pagesSha256']}/blob").read_bytes())
    assert pages['pages'][0]['rotation'] == 90
    assert 'Analyte R: 3,40 mmol/L' in pages['pages'][0]['text']
    assert 'bbox' not in pages['pages'][0]
    # Independent pre-authored geometry oracle, not invented extractor geometry.
    facts = decode_json((PDF.parent/'expected/pdf-facts.json').read_bytes())
    assert facts['lab-rotated.pdf']['displayedCropBoxPoints'] == [240,400]


@pytest.mark.parametrize('field',['assetPath','size','mediaType','sourceSha256'])
def test_forged_source_receipts_fail(tmp_path, field):
    from helseark.intake import add_source, build_packet
    vault,person,_=family(tmp_path)
    receipt=add_source(vault,person,PDF/'lab-text.pdf')
    value={'assetPath':PDF/'lab-text.pdf','size':1,'mediaType':'text/plain','sourceSha256':'0'*64}[field]
    with pytest.raises(ArchiveError, match='SOURCE_RECEIPT_MISMATCH'):
        build_packet(vault,replace(receipt,**{field:value}),tmp_path/'packet')


@pytest.mark.parametrize('what',['source','extraction','receipt','kit'])
def test_corrupt_retained_artifacts_and_stale_kit_fail_closed(tmp_path,what):
    from helseark.intake import build_packet
    vault,person,source,packet = packet_for(tmp_path)
    meta=decode_json((packet.path/'intake.json').read_bytes())
    paths={'source':source.assetPath,
           'extraction':vault.root/f"people/{person}/assets/sha256/{meta['extraction']['pagesSha256']}/blob",
           'receipt':source.assetPath.parent/'extraction.json',
           'kit':vault.root/f'agent-kit/{vault.config.agentKitVersion}/manifest.json'}
    paths[what].write_bytes(b'{}')
    with pytest.raises(ArchiveError):
        build_packet(vault,source,tmp_path/'retry')
    assert not (tmp_path/'retry').exists()
    assert paths[what].read_bytes()==b'{}'


@pytest.mark.parametrize('bad',['/tmp/bundle.json','../bundle.json','nested/../../bundle.json','link.json','sub/bundle.json'])
def test_unsafe_candidate_paths_rejected(tmp_path,bad):
    from helseark.intake import read_candidate
    from helseark.serialization import encode_json
    vault,person,source,packet,candidate = supplied_candidate(tmp_path)
    (candidate.path/'link.json').symlink_to(candidate.path/'bundle.json')
    (candidate.path/'sub').symlink_to(candidate.path, target_is_directory=True)
    meta=decode_json((candidate.path/'candidate.json').read_bytes());meta['bundlePath']=bad
    (candidate.path/'candidate.json').write_bytes(encode_json(meta))
    with pytest.raises(ArchiveError,match='UNSAFE_PATH'):
        read_candidate(vault,candidate.path)


@pytest.mark.parametrize('kind',['depth','text','resources','unknown','producer','missing-issues','bbox'])
def test_strict_candidate_boundaries(tmp_path,monkeypatch,kind):
    import helseark.intake as intake
    from helseark.serialization import encode_json
    vault,person,source,packet,candidate = supplied_candidate(tmp_path)
    if kind in ('depth','text','resources'):
        limits={'depth':replace(IntakeLimits(),jsonDepth=2),'text':replace(IntakeLimits(),textFieldBytes=10),
                'resources':replace(IntakeLimits(),candidateResources=1)}[kind]
        monkeypatch.setattr(intake,'LIMITS',limits)
    else:
        file='candidate.json' if kind in ('unknown','producer','missing-issues') else 'evidence.json'
        p=candidate.path/file;value=decode_json(p.read_bytes())
        if kind=='unknown':value['invented']=True
        elif kind=='producer':value['producerProvenance']={'provenanceVersion':1,'status':'external-unknown','reason':'changed'}
        elif kind=='missing-issues':value['unresolved']=[]
        else:next(e for e in value['entries'] if e['kind']=='source')['locator']['bbox']=[0,0,1,1]
        p.write_bytes(encode_json(value))
    with pytest.raises(ArchiveError):intake.read_candidate(vault,candidate.path)


def test_no_overwrite_and_source_symlink_escape(tmp_path):
    from helseark.intake import add_source,build_packet
    vault,person,source,packet=packet_for(tmp_path)
    sentinel=packet.path/'keep';sentinel.write_bytes(b'KEEP')
    with pytest.raises(ArchiveError,match='DESTINATION_EXISTS'):build_packet(vault,source,packet.path)
    assert sentinel.read_bytes()==b'KEEP'
    link=tmp_path/'source.pdf';link.symlink_to(PDF/'lab-text.pdf')
    with pytest.raises(ArchiveError,match='UNSAFE_PATH'):add_source(vault,person,link)


def test_candidate_keeps_exact_accepted_history_and_rejects_root_symlink(tmp_path):
    from helseark.intake import read_candidate
    vault,person,source,packet,candidate=supplied_candidate(tmp_path)
    accepted=vault.root/f'people/{person}/accepted'
    snapshot={p.relative_to(accepted):hash_bytes(p.read_bytes()) for p in accepted.rglob('*') if p.is_file()}
    read_candidate(vault,candidate.path)
    assert snapshot=={p.relative_to(accepted):hash_bytes(p.read_bytes()) for p in accepted.rglob('*') if p.is_file()}
    link=tmp_path/'candidate-link';link.symlink_to(candidate.path,target_is_directory=True)
    with pytest.raises(ArchiveError,match='UNSAFE_PATH'):read_candidate(vault,link)


def test_actual_renderer_drafts_only_confirmed_selected_pdf(tmp_path):
    vault,person,source,packet=packet_for(tmp_path,identityConfirmed=True)
    header=json.JSONDecoder().raw_decode((packet.path/'prompt.txt').read_text().split('\n',1)[1])[0]
    assert header['disposition']=='draft'
    assert header['workflowAvailability']['status']=='available'
    assert not header['workflowAvailability']['missingCapabilities']
    assert header['permittedWrites']==[
        'output/report.md', 'output/candidate/candidate.json',
        'output/candidate/bundle.json', 'output/candidate/evidence.json']
    assert header['handoffDataBytes']<=header['maxDataBytes']
    meta=decode_json((packet.path/'intake.json').read_bytes())
    assert not Path(meta['outputDirectory']).exists()
    assert header['producerProvenance']['kitVersion']==vault.config.agentKitVersion


def test_cli_intake_never_reads_unselected_person(tmp_path):
    import subprocess,sys,os
    vault,person,other=family(tmp_path)
    script='''
import sys
from helseark.cli import main
vault,person,other,source,packet=sys.argv[1:]
def guard(event,args):
    if event in ('open','os.listdir','os.scandir') and '/people/'+other in str(args[0]):
        raise AssertionError('Unselected person read')
sys.addaudithook(guard)
raise SystemExit(main(['--vault',vault,'intake','add',source,'--person',person,'--packet',packet,'--json']))
'''
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,'-c',script,str(vault.root),person,other,
        str((PDF/'lab-text.pdf').resolve()),str(tmp_path/'packet')],capture_output=True,
        env={**os.environ,'PYTHONPATH':str(root/'src')})
    assert result.returncode==0,result.stderr.decode()
    assert other not in result.stdout.decode()


def test_real_renderer_producer_pins_validate_and_forgery_fails(tmp_path):
    from helseark.intake import read_candidate
    from helseark.serialization import encode_json
    vault,person,source,packet,candidate=supplied_candidate(tmp_path)
    header=json.JSONDecoder().raw_decode((packet.path/'prompt.txt').read_text().split('\n',1)[1])[0]
    for name in ('candidate.json','evidence.json'):
        path=candidate.path/name;value=decode_json(path.read_bytes())
        value['producerProvenance']=header['producerProvenance'];path.write_bytes(encode_json(value))
    read_candidate(vault,candidate.path)
    for name in ('candidate.json','evidence.json'):
        path=candidate.path/name;value=decode_json(path.read_bytes())
        value['producerProvenance']['promptSha256']='0'*64;path.write_bytes(encode_json(value))
    with pytest.raises(ArchiveError,match='PRODUCER_MISMATCH'):read_candidate(vault,candidate.path)


def test_retained_receipts_remain_immutable_after_vault_relocation(tmp_path):
    import shutil
    from helseark.archive import open_vault
    from helseark.intake import add_source,build_packet
    vault,person,source,packet=packet_for(tmp_path)
    receipt_bytes=(source.assetPath.parent/'source.json').read_bytes()
    shutil.copytree(vault.root,tmp_path/'relocated')
    relocated=open_vault(tmp_path/'relocated')
    receipt=add_source(relocated,person,PDF/'task5-complete.pdf')
    assert (receipt.assetPath.parent/'source.json').read_bytes()==receipt_bytes
    second=build_packet(relocated,receipt,tmp_path/'relocated-packet')
    assert second.source.sourceSha256==source.sourceSha256
    assert (source.assetPath.parent/'source.json').read_bytes()==receipt_bytes


def test_cli_plain_output_is_packet_path(tmp_path):
    import subprocess,sys,os
    vault,person,_=family(tmp_path)
    root=Path(__file__).resolve().parents[1]
    packet=tmp_path/'plain-packet'
    result=subprocess.run([sys.executable,'-m','helseark.cli','--vault',str(vault.root),
        'intake','add',str((PDF/'lab-text.pdf').resolve()),'--person',person,'--packet',str(packet)],
        capture_output=True,text=True,env={**os.environ,'PYTHONPATH':str(root/'src')})
    assert result.returncode==0,result.stderr
    lines=result.stdout.splitlines()
    assert lines[0]==str(packet)
    assert lines[1].startswith('Host-retained context SHA-256: ')
    assert len(lines[1].split(': ',1)[1])==64


def test_intake_original_authority_reload_and_real_source_expansion(tmp_path):
    from helseark.agent_context import read_agent_context, render_task_prompt, document, _source
    from helseark.intake import add_source
    from helseark.serialization import encode_json
    vault, person, source, packet = packet_for(tmp_path, identityConfirmed=True)
    prompt=(packet.path/'prompt.txt').read_text()
    source_data=decode_json(prompt.split('<SOURCE_DATA_JSON>\n',1)[1].split('\n</SOURCE_DATA_JSON>',1)[0].encode())
    values={'source_data':source_data,'identity_confirmed':True,'candidate_id':packet.importId,
        'output_directory':str(tmp_path/'new-output')}
    loaded=read_agent_context(packet.path/'context')
    assert loaded.trustedContextSha256 is None
    assert 'trustedContextSha256' not in document(packet)
    assert all(packet.trustedContextSha256.encode() not in p.read_bytes()
        for p in packet.path.rglob('*') if p.is_file())
    with pytest.raises(ArchiveError,match='CONTEXT_AUTHORITY_REQUIRED'):
        render_task_prompt(loaded,'extract-report',values)
    result=render_task_prompt(loaded,'extract-report',values,
        trusted_context_sha256=packet.trustedContextSha256)
    assert json.JSONDecoder().raw_decode(result.text.split('\n',1)[1])[0]['disposition']=='draft'
    extra=add_source(vault,person,PDF/'lab-rotated.pdf')
    path=packet.path/'context/context.json'
    original=path.read_bytes()
    for change in ({'selectedSources':[*document(loaded.selectedSources),document(_source(vault,person,extra.sourceSha256))]},
                   {'maxDataBytes':999999}, {'totalCount':999}, {'taskId':'correct'}):
        path.write_bytes(encode_json({**decode_json(original),**change}))
        with pytest.raises(ArchiveError,match='CONTEXT_MISMATCH'):
            render_task_prompt(read_agent_context(path.parent),'extract-report',values,
                trusted_context_sha256=packet.trustedContextSha256)
    path.write_bytes(original)
    # Source assertions do not become host confirmation, selectors or output roots.
    hostile={**source_data,'identityConfirmed':True,'personId':str(uuid4()),
        'task':'correct','sourceSha256':[extra.sourceSha256], 'output_directory':'/tmp/forbidden'}
    result=render_task_prompt(loaded,'extract-report',{**values,'source_data':hostile,'identity_confirmed':False},
        trusted_context_sha256=packet.trustedContextSha256)
    header=json.JSONDecoder().raw_decode(result.text.split('\n',1)[1])[0]
    assert header['disposition']=='blocked' and header['permittedWrites']==['output/report.md']
    assert [s.sha256 for s in loaded.selectedSources]==[source.sourceSha256]
    assert not (tmp_path/'new-output').exists()


def test_real_intake_repeated_escaped_slots_exact_boundary(tmp_path):
    from test_agent_context import kit, repin_file, rewrite_manifest
    from helseark.intake import add_source, build_packet
    from helseark.agent_context import build_agent_context, render_task_prompt
    from helseark.contracts import ContextRequest
    vault=init_vault(tmp_path/'vault')
    path='prompts/extract-report.md'
    data=(kit(vault)/path).read_bytes()+b'\nRepeated source: {{ source_data }}\n'
    vault=repin_file(vault,path,data)
    def edit(manifest):
        next(p for p in manifest['prompts'] if p['id']=='extract-report')['sha256']=hash_bytes(data)
    vault=rewrite_manifest(vault,edit)
    person=add_person(vault,PersonDraft('Synthetic'))
    source=add_source(vault,person,PDF/'task5-complete.pdf')
    packet=build_packet(vault,source,tmp_path/'packet',identityConfirmed=True)
    prompt=(packet.path/'prompt.txt').read_text()
    content=prompt.split('<SOURCE_DATA_JSON>\n',1)[1].split('\n</SOURCE_DATA_JSON>',1)[0]
    assert prompt.count(content)==2
    source_data=decode_json(content.encode())
    source_data['escaping']='é<>& {{request}}'
    context=build_agent_context(vault,person,'import',ContextRequest(sourceHashes=(source.sourceSha256,),includeSourceExtractions=True,maxDataBytes=12000),tmp_path/'bounded')
    values={'source_data':source_data,'identity_confirmed':True,'candidate_id':packet.importId,
        'output_directory':str(tmp_path/'new-output')}
    result=render_task_prompt(context,'extract-report',values)
    header=json.JSONDecoder().raw_decode(result.text.split('\n',1)[1])[0]
    escaped=result.text.split('<SOURCE_DATA_JSON>\n',1)[1].split('\n</SOURCE_DATA_JSON>',1)[0]
    assert header['inlineDataBytes']==2*len(escaped.encode())+2
    spare=12000-header['handoffDataBytes']
    source_data['escaping']+='x'*(spare//2)
    values['request']='x'*(spare%2)
    exact=render_task_prompt(context,'extract-report',values)
    assert json.JSONDecoder().raw_decode(exact.text.split('\n',1)[1])[0]['handoffDataBytes']==12000
    with pytest.raises(ArchiveError,match='CONTEXT_BUDGET_EXCEEDED'):
        render_task_prompt(context,'extract-report',{**values,'request':values['request']+'x'})
