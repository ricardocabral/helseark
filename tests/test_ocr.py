"""Real-engine synthetic qualification and immutable intake boundaries."""
from dataclasses import replace
from pathlib import Path
import json
import os
import sys
from uuid import uuid4
import pytest
from helseark.adapters.ocr import OcrConfig, extract_ocr, MODEL_SHA256, _words, _pgm
from helseark.contracts import ArchiveError, SourceReceipt, PersonDraft
from helseark.serialization import decode_json, hash_bytes, encode_json

FIXTURES = Path(__file__).parent/'fixtures/synthetic/ocr'
FACTS = json.loads((Path(__file__).parent/'fixtures/expected/ocr-facts.json').read_text())['cases']


def config(tmp_path, rotation=0):
    engine=Path(os.environ.get('HELSEARK_TEST_TESSERACT','/opt/homebrew/bin/tesseract'))
    renderer=Path(os.environ.get('HELSEARK_TEST_PDFTOPPM','/opt/homebrew/bin/pdftoppm'))
    model=Path(os.environ.get('HELSEARK_TEST_OCR_MODEL','/opt/homebrew/share/tessdata/eng.traineddata'))
    if sys.platform != 'darwin' or not all(p.is_file() for p in (engine,renderer,model)):
        pytest.skip('Optional qualified native OCR tools absent; base remains supported.')
    return OcrConfig(tmp_path/'ocr',engine,hash_bytes(engine.read_bytes()),renderer,
                     hash_bytes(renderer.read_bytes()),model,rotation)


def receipt(path):
    data=path.read_bytes()
    return SourceReceipt(str(uuid4()),hash_bytes(data),len(data),'application/pdf',path)


@pytest.mark.parametrize('case',FACTS,ids=lambda c:c['name'])
def test_real_corpus(tmp_path,case):
    result=extract_ocr(receipt(FIXTURES/(case['name']+'.pdf')),config(tmp_path,case['rotation']))
    artifact=decode_json(result.pagesPath.read_bytes())
    assert artifact['sourceSha256']==hash_bytes((FIXTURES/(case['name']+'.pdf')).read_bytes())
    assert result.pagesSha256==hash_bytes(result.pagesPath.read_bytes())
    assert result.pageCount==1 and {i.code for i in result.issues}=={'OCR_VISUAL_REVIEW'}
    assert artifact['pages'][0]['unresolvedRegions'][0]['bbox']==[0,0,1,1]
    for derivative in artifact['derivatives']:
        data=(result.pagesPath.parent/derivative['path']).read_bytes()
        assert len(data)==derivative['size'] and hash_bytes(data)==derivative['sha256']
    page=artifact['pages'][0]
    for word in page['words']:
        assert page['text'][word['start']:word['end']]==word['text']
        l,t,r,b=word['bbox']; assert 0<=l<r<=1 and 0<=t<b<=1
    # Critical easy-path checks only; degraded cases produce measured errors below.
    if case['name']=='scan':
        assert '1.20' in page['text'] and '<0,05' in page['text']
    if case['name']=='missing-glyph':
        assert '1.20' not in page['text']
    errors=[]
    for fact in case['facts']:
        l,t,r,b=fact['region']
        region=' '.join(w['text'] for w in page['words'] if l <= (w['bbox'][0]+w['bbox'][2])/2 <= r and t <= (w['bbox'][1]+w['bbox'][3])/2 <= b)
        errors.append({'expected':fact['text'],'regionText':region,'textMissing':fact['text'] not in page['text'],
            'locationMismatch':fact['text'] not in region,'unrecoverable':fact.get('unrecoverable',False)})
    print(json.dumps({'case':case['name'],'recognized':page['text'],'facts':errors}))


def test_wrong_model_pin_and_changed_source_fail_without_publication(tmp_path):
    conf=config(tmp_path)
    with pytest.raises(ArchiveError,match='OCR_UNSUPPORTED'):
        extract_ocr(receipt(FIXTURES/'scan.pdf'),replace(conf,engineSha256='0'*64))
    assert not conf.outputDirectory.exists()
    with pytest.raises(ArchiveError,match='SOURCE_RECEIPT_MISMATCH'):
        extract_ocr(replace(receipt(FIXTURES/'scan.pdf'),sourceSha256='0'*64),conf)
    assert not conf.outputDirectory.exists()


def test_collision_preserves_destination(tmp_path):
    conf=config(tmp_path);conf.outputDirectory.mkdir();(conf.outputDirectory/'keep').write_text('untouched')
    with pytest.raises(ArchiveError,match='DESTINATION_EXISTS'):
        extract_ocr(receipt(FIXTURES/'scan.pdf'),conf)
    assert (conf.outputDirectory/'keep').read_text()=='untouched'


def test_pgm_rotation_and_inverse_word_boxes():
    image=b'P5\n2 3\n255\n'+bytes(range(6))
    expected={0:bytes([0,1,2,3,4,5]),90:bytes([4,2,0,5,3,1]),180:bytes([5,4,3,2,1,0]),270:bytes([1,3,5,0,2,4])}
    for rotation in expected:
        assert _pgm(image,rotation)[0].split(b'255\n')[1]==expected[rotation]
    tsv=b'level\tblock_num\tpar_num\tline_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t1\t10\t20\t30\t40\t98.2\t1.20\n'
    _,words=_words(tsv,100,100,90)
    from decimal import Decimal as D
    assert words[0]['bbox']==[D('.2'),D('.6'),D('.6'),D('.9')]


def test_ocr_packet_versions_person_isolation_and_no_history_change(tmp_path):
    from helseark.archive import init_vault,add_person,head
    from helseark.intake import add_source,build_packet,_ocr_extraction
    vault=init_vault(tmp_path/'vault');person=add_person(vault,PersonDraft('Avery Synthetic'))
    other=add_person(vault,PersonDraft('UNSELECTED SECRET'))
    source=add_source(vault,person,FIXTURES/'scan.pdf');before=head(vault,person)
    conf=config(tmp_path)
    packet=build_packet(vault,source,tmp_path/'packet',identityConfirmed=True,ocrConfig=conf)
    meta=decode_json((packet.path/'intake.json').read_bytes());digest=meta['extraction']['pagesSha256']
    assert 'OCR_VISUAL_REVIEW' in {i['code'] for i in meta['issues']}
    content=b''.join(p.read_bytes() for p in packet.path.rglob('*') if p.is_file())
    assert other.encode() not in content and b'UNSELECTED SECRET' not in content
    assert head(vault,person)==before
    again=build_packet(vault,source,tmp_path/'again',ocrConfig=replace(conf,outputDirectory=tmp_path/'ocr2'))
    assert decode_json((again.path/'intake.json').read_bytes())['extraction']['pagesSha256']==digest
    # A preprocessing change is an independent artifact; prior retained bytes remain untouched.
    rotated=build_packet(vault,source,tmp_path/'rotated',ocrConfig=replace(conf,outputDirectory=tmp_path/'ocr3',rotation=180))
    assert decode_json((rotated.path/'intake.json').read_bytes())['extraction']['pagesSha256'] != digest
    assert _ocr_extraction(vault,source,digest)[0]['pagesSha256']==digest
    with pytest.raises(ArchiveError,match='UNSAFE_PATH'):
        _ocr_extraction(vault,replace(source,personId=other),digest)
    artifact=_ocr_extraction(vault,source,digest)[1]
    derivative=vault.root/f"people/{person}/assets/sha256/{artifact['derivatives'][0]['sha256']}/blob"
    derivative.write_bytes(b'corrupt')
    with pytest.raises(ArchiveError,match='INTEGRITY'):
        _ocr_extraction(vault,source,digest)


def bind_scan_candidate(vault, person, source, packet, destination):
    """Hand-authored Task5 clinical oracle, explicitly rebound to OCR provenance.

    This is not an agent or extraction result. Real quote consistency is checked
    against the actual OCR artifact; no source numeric token is corrected here.
    """
    from helseark.intake import _ocr_extraction, read_candidate
    example=Path(__file__).resolve().parents[1]/'agent-kit/examples'
    meta=decode_json((packet.path/'intake.json').read_bytes())
    digest=meta['extraction']['pagesSha256']
    _,artifact,_,_= _ocr_extraction(vault,source,digest)
    replacements={b'11111111-1111-4111-8111-111111111111':person.encode(),
                  b'SOURCE_HASH':source.sourceSha256.encode(),b'EXTRACTION_HASH':digest.encode()}
    def bound(name):
        data=(example/name).read_bytes()
        for key,value in replacements.items():data=data.replace(key,value)
        return decode_json(data)
    bundle=bound('task5-bundle.json');evidence=bound('task5-evidence.json')
    for entry in evidence['entries']:
        if entry['kind']=='source':entry['extraction']=artifact['extraction']
    context=decode_json((packet.path/'context/context.json').read_bytes())
    candidate={'contractVersion':'0.1.0','fhirVersion':'4.0.1','profileVersion':'0.1.0',
        'candidateId':meta['importId'],'personId':person,'baseChangeSha256':context['base']['changeSha256'],
        'sourceSha256':[source.sourceSha256],'bundlePath':'bundle.json','evidencePath':'evidence.json',
        'producer':{'kind':'local-user','name':'hand-authored synthetic OCR oracle; no model run'},
        'producerProvenance':evidence['producerProvenance'],'unresolved':meta['issues']}
    destination.mkdir()
    for name,value in [('candidate.json',candidate),('bundle.json',bundle),('evidence.json',evidence)]:
        (destination/name).write_bytes(encode_json(value))
    return read_candidate(vault,destination)


def test_real_scan_review_commit_reextract_derivative_closure(tmp_path):
    from helseark.archive import init_vault,add_person,head,commit_candidate,open_vault,resolve
    from helseark.intake import add_source,build_packet,prepare_candidate,read_candidate
    from helseark.review import render_review,record_review
    from helseark.contracts import ReviewDecision, ResourceRef
    from helseark.portability import backup,restore
    vault=init_vault(tmp_path/'vault');person=add_person(vault,PersonDraft('Avery Synthetic'))
    source=add_source(vault,person,FIXTURES/'complete-scan.pdf')
    conf=config(tmp_path)
    packet=build_packet(vault,source,tmp_path/'packet',identityConfirmed=True,ocrConfig=conf)
    candidate=bind_scan_candidate(vault,person,source,packet,tmp_path/'candidate')
    proposal=prepare_candidate(vault,candidate)
    view=render_review(vault,proposal)
    assert 'OCR_VISUAL_REVIEW' in {i['code'] for i in view.issues}
    with pytest.raises(ArchiveError):
        record_review(vault,proposal,ReviewDecision(True,'accept',(),'synthetic human'))
    acks=tuple({'code':i['code'],'resourceRef':i['resourceRef'],'reason':'Synthetic manual source inspection.'}
        for i in view.issues if i['severity'] in ('review','warning'))
    reviewed=record_review(vault,proposal,ReviewDecision(True,'accept-with-acknowledged-limitations',acks,'synthetic human'))
    committed=commit_candidate(vault,proposal,reviewed)
    assert committed.head.sequence==2
    q=next(r for r in committed.logicalResources if r.resourceType=='Observation')
    assert str(resolve(vault,person,q)['valueQuantity']['value'])=='0.050'
    # Replaying the identical candidate is idempotent.
    assert prepare_candidate(vault,read_candidate(vault,candidate.path)).proposalSha256==proposal.proposalSha256
    saved={p.relative_to(vault.root):p.read_bytes() for p in (vault.root/f'people/{person}/accepted').rglob('*') if p.is_file()}
    # New source extraction anchors use existing explicit re-extraction semantics.
    metadata=decode_json((candidate.path/'candidate.json').read_bytes())
    metadata['baseChangeSha256']=head(vault,person).changeSha256
    (candidate.path/'candidate.json').write_bytes(encode_json(metadata))
    evidence=decode_json((candidate.path/'evidence.json').read_bytes())
    # A different valid page locator changes the source anchor; explicit mapping is required.
    source_entry=next(e for e in evidence['entries'] if e['kind']=='source')
    source_entry['locator']['bbox']=[0,0,1,1]
    (candidate.path/'evidence.json').write_bytes(encode_json(evidence))
    changed=read_candidate(vault,candidate.path)
    with pytest.raises(ArchiveError,match='REEXTRACTION_REQUIRED'):
        prepare_candidate(vault,changed,authorized_sources=(source.sourceSha256,))
    with pytest.raises(ArchiveError,match='RECONCILIATION_REQUIRED'):
        prepare_candidate(vault,changed,authorized_sources=(source.sourceSha256,),reextract=True)
    for path,data in saved.items():assert (vault.root/path).read_bytes()==data
    inventory=decode_json((proposal.path/'proposal.json').read_bytes())
    artifact=decode_json((conf.outputDirectory/'pages.json').read_bytes())
    expected={source.sourceSha256,hash_bytes((conf.outputDirectory/'pages.json').read_bytes()),*(d['sha256'] for d in artifact['derivatives'])}
    assert {a['sha256'] for a in inventory['assets']}==expected
    # Accepted closure includes every image/TSV, even after disposable work removal.
    import shutil
    shutil.rmtree(vault.root/'work');shutil.rmtree(vault.root/'.runtime')
    exported=backup(vault,tmp_path/'backup')
    recovered=restore(exported.path,tmp_path/'restored')
    assert str(resolve(recovered,person,q)['valueQuantity']['value'])=='0.050'
    for path,data in saved.items():assert (recovered.root/path).read_bytes()==data


def test_real_native_network_denial_and_timeout(tmp_path):
    from helseark.adapters.ocr import _run
    import socket
    import subprocess
    import threading
    config(tmp_path) # Qualified native platform gate.
    listener=socket.socket(); listener.bind(('127.0.0.1',0));listener.listen();listener.settimeout(3)
    url=f'http://127.0.0.1:{listener.getsockname()[1]}/'
    def serve():
        with listener.accept()[0] as connection:
            connection.recv(4096);connection.sendall(b'HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\nOK')
    worker=threading.Thread(target=serve);worker.start()
    # Successful unsandboxed control isolates the network denial from connectivity.
    assert subprocess.run(['/usr/bin/curl','-fsS',url],capture_output=True).stdout==b'OK'
    worker.join();listener.close()
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen();listener.settimeout(.2)
    url=f'http://127.0.0.1:{listener.getsockname()[1]}/'
    try:
        with pytest.raises(ArchiveError,match='OCR_INVALID'):
            _run(['/usr/bin/curl','-fsS','--max-time','1',url],tmp_path)
        with pytest.raises(socket.timeout):listener.accept()
    finally:listener.close()
    with pytest.raises(ArchiveError,match='OCR_RESOURCE_LIMIT'):
        _run(['/bin/sleep','5'],tmp_path,seconds=.05)


def test_real_mixed_person_packet_blocks_drafting(tmp_path):
    from helseark.archive import init_vault,add_person
    from helseark.intake import add_source,build_packet
    vault=init_vault(tmp_path/'vault');person=add_person(vault,PersonDraft('Avery Synthetic'))
    source=add_source(vault,person,FIXTURES/'mixed.pdf')
    packet=build_packet(vault,source,tmp_path/'packet',identityConfirmed=True,ocrConfig=config(tmp_path))
    metadata=decode_json((packet.path/'intake.json').read_bytes())
    assert any(i['code']=='MULTIPLE_PERSON_CUES' and i['severity']=='error' for i in metadata['issues'])
    handoff,_=json.JSONDecoder().raw_decode(metadata['renderedPrompt']['text'].split('\n',1)[1])
    assert handoff['disposition']=='blocked' and handoff['permittedWrites']==['output/report.md']


def test_missing_native_tool_is_typed_optional_failure(tmp_path):
    conf=OcrConfig(tmp_path/'out',tmp_path/'absent-engine','0'*64,tmp_path/'absent-renderer','0'*64,tmp_path/'absent-model')
    with pytest.raises(ArchiveError) as failure:
        extract_ocr(receipt(FIXTURES/'scan.pdf'),conf)
    assert failure.value.code=='OCR_UNSUPPORTED' and failure.value.details['exitCode']==6
    assert not conf.outputDirectory.exists()


def test_ocr_honors_intake_text_limit(tmp_path):
    from helseark.archive import init_vault,add_person,head
    from helseark.intake import add_source,build_packet
    from helseark.contracts import IntakeLimits
    vault=init_vault(tmp_path/'vault');person=add_person(vault,PersonDraft('Avery Synthetic'))
    source=add_source(vault,person,FIXTURES/'scan.pdf');before=head(vault,person)
    with pytest.raises(ArchiveError,match='TEXT_FIELD_LIMIT'):
        build_packet(vault,source,tmp_path/'packet',ocrConfig=config(tmp_path),limits=IntakeLimits(textFieldBytes=1))
    assert not (tmp_path/'packet').exists() and head(vault,person)==before
    assert hash_bytes(source.assetPath.read_bytes())==source.sourceSha256


def test_word_coordinates_ignore_ambient_decimal_precision():
    from decimal import Context, localcontext, getcontext
    tsv=b'level\tblock_num\tpar_num\tline_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t1\t10\t20\t30\t40\t98.2\t1.20\n'
    expected=_words(tsv,300,300,90)
    with localcontext(Context(prec=2)):
        assert _words(tsv,300,300,90)==expected
        assert getcontext().prec==2
