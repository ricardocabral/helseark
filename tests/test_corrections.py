"""Synthetic local correction facts; predetermined candidates are not accuracy evidence."""
from decimal import Decimal
import pytest
from test_intake import supplied_candidate
from test_review import approve
from helseark.archive import commit_candidate, resolve, iter_current
from helseark.contracts import ResourceRef, ObservationFilter, ArchiveError
from helseark.intake import prepare_candidate, read_candidate
from helseark.serialization import encode_json
from helseark.query import observations


def accepted(tmp_path):
    v,p,_,_,c=supplied_candidate(tmp_path)
    c.bundle['entry'][0]['resource']['method']['text']='M? — synthetic transcription mistake'
    (c.path/'bundle.json').write_bytes(encode_json(c.bundle))
    c=read_candidate(v,c.path)
    proposal=prepare_candidate(v,c)
    commit_candidate(v,proposal,approve(v,proposal))
    r=next(r for r in iter_current(v,p) if r['resourceType']=='Observation' and 'valueQuantity' in r)
    return v,p,r


def test_transcription_and_error_preserve_history_and_native_revision(tmp_path):
    from helseark.intake import start_correction
    v,p,old=accepted(tmp_path)
    ref=ResourceRef('Observation',old['id'])
    c=start_correction(v,p,ref,'transcription: human checked the source decimal')
    row=next(e['resource'] for e in c.bundle['entry'] if e['resource']['resourceType']=='Observation')
    row['method']['text']='M1'
    row['valueQuantity']['value']=Decimal('0.050')
    (c.path/'bundle.json').write_bytes(encode_json(c.bundle))
    proposal=prepare_candidate(v,read_candidate(v,c.path))
    assert resolve(v,p,ref)==old
    commit_candidate(v,proposal,approve(v,proposal))
    current=resolve(v,p,ref)
    assert current['status']=='final' and str(current['valueQuantity']['value'])=='0.050'
    assert current['method']['text']=='M1' and old['method']['text']!=current['method']['text']
    assert resolve(v,p,ResourceRef('Observation',old['id'],old['meta']['versionId']))==old
    provenance=next(r for r in iter_current(v,p) if r['resourceType']=='Provenance' and any(e['role']=='revision' and e['what']['reference'].endswith(old['meta']['versionId']) for e in r['entity']))
    assert provenance['target']
    c=start_correction(v,p,ref,'entered-in-error: assigned result was invalid')
    next(e['resource'] for e in c.bundle['entry'] if e['resource']['resourceType']=='Observation')['status']='entered-in-error'
    (c.path/'bundle.json').write_bytes(encode_json(c.bundle))
    proposal=prepare_candidate(v,read_candidate(v,c.path));commit_candidate(v,proposal,approve(v,proposal))
    assert all(r.resourceRef.id!=old['id'] for r in observations(v,p,ObservationFilter()))
    assert any(r.resourceRef.id==old['id'] for r in observations(v,p,ObservationFilter(includeInvalidated=True)))


def test_transcription_cannot_claim_laboratory_amendment(tmp_path):
    from helseark.intake import start_correction
    v,p,old=accepted(tmp_path)
    c=start_correction(v,p,ResourceRef('Observation',old['id']),'transcription: corrected reading')
    next(e['resource'] for e in c.bundle['entry'] if e['resource']['resourceType']=='Observation')['status']='amended'
    (c.path/'bundle.json').write_bytes(encode_json(c.bundle))
    with pytest.raises(ArchiveError,match='CORRECTION_STATUS'):
        prepare_candidate(v,read_candidate(v,c.path))


def test_new_laboratory_source_explicit_mapping(tmp_path):
    from helseark.intake import add_source, build_packet
    from test_review import rerun_candidate
    from pypdf import PdfReader,PdfWriter
    from pypdf.generic import DecodedStreamObject,NameObject
    from helseark.serialization import decode_json
    v,p,source,packet,c=supplied_candidate(tmp_path)
    first=prepare_candidate(v,c);commit_candidate(v,first,approve(v,first))
    old=next(r for r in iter_current(v,p) if r['resourceType']=='Observation' and 'valueQuantity' in r)
    writer=PdfWriter(clone_from=PdfReader(source.assetPath));stream=DecodedStreamObject()
    stream.set_data(writer.pages[0].get_contents().get_data().replace(b'Status: final',b'Status: amended'))
    writer.pages[0][NameObject('/Contents')]=stream
    file=tmp_path/'amended.pdf';writer.write(file)
    new=add_source(v,p,file);new_packet=build_packet(v,new,tmp_path/'new-packet',identityConfirmed=True)
    info=decode_json((new_packet.path/'intake.json').read_bytes())
    old_pages=decode_json((source.assetPath.parent/'extraction.json').read_bytes())['pagesSha256']
    evidence=encode_json(c.evidence).replace(source.sourceSha256.encode(),new.sourceSha256.encode()).replace(old_pages.encode(),info['extraction']['pagesSha256'].encode()).replace(b'Status: final',b'Status: amended')
    c.evidence.update(decode_json(evidence))
    c.bundle.update(decode_json(encode_json(c.bundle).replace(source.sourceSha256.encode(),new.sourceSha256.encode())))
    removed=[e['fullUrl'] for e in c.bundle['entry'] if e['resource']['resourceType']=='Observation' and 'valueQuantity' not in e['resource']]
    c.bundle['entry'][:]=[e for e in c.bundle['entry'] if e['fullUrl'] not in removed]
    c.evidence['entries'][:]=[e for e in c.evidence['entries'] if e['target']['reference'] not in removed]
    next(e['resource'] for e in c.bundle['entry'] if e['resource']['resourceType']=='Observation')['status']='amended'
    (c.path/'bundle.json').write_bytes(encode_json(c.bundle));(c.path/'evidence.json').write_bytes(encode_json(c.evidence))
    c=rerun_candidate(v,c,sourceSha256=[new.sourceSha256],candidateId=info['importId'])
    proposal=prepare_candidate(v,c,authorized_sources=(new.sourceSha256,),amendment_target=ResourceRef('Observation',old['id']),amendment_reason='Synthetic human matched laboratory amendment')
    commit_candidate(v,proposal,approve(v,proposal))
    assert resolve(v,p,ResourceRef('Observation',old['id']))['status']=='amended'
    assert resolve(v,p,ResourceRef('Observation',old['id'],old['meta']['versionId']))==old
    assert new.assetPath.read_bytes()==file.read_bytes() and source.assetPath.exists()


def test_stale_report_warning_and_cancellation_do_not_cascade(tmp_path):
    from copy import deepcopy
    from pathlib import Path
    from helseark.serialization import decode_json
    from helseark.intake import start_correction
    from helseark.query import timeline
    from helseark.review import render_review
    v,p,_,_,c=supplied_candidate(tmp_path)
    report=decode_json((Path(__file__).parent/'fixtures/synthetic/task6-report.json').read_bytes().replace(b'PERSON',p.encode()))
    report_ref='urn:uuid:'+report['id'];c.bundle['entry'].append({'fullUrl':report_ref,'resource':report})
    template=next(e for e in c.evidence['entries'] if e['kind']=='source')
    for pointer,quote in [('/status','Status: final'),('/code/text','Report: Synthetic laboratory report'),('/subject/reference','Patient: Avery Synthetic'),('/effectiveDateTime','Collected: 2026-01'),('/result/0/reference','Analyte Q: <0,050 mg/L'),('/result/1/reference','Qualitative: not detected')]:
        entry=deepcopy(template);entry['target']={'reference':report_ref,'pointers':[pointer]};entry['quote']=quote;c.evidence['entries'].append(entry)
    c.evidence['entries'].append({'target':{'reference':report_ref,'pointers':['/id','/meta/profile/0']},'kind':'generated','rule':'synthetic-report-fixture-1'})
    (c.path/'bundle.json').write_bytes(encode_json(c.bundle));(c.path/'evidence.json').write_bytes(encode_json(c.evidence))
    first=prepare_candidate(v,read_candidate(v,c.path));commit_candidate(v,first,approve(v,first))
    old=next(r for r in iter_current(v,p) if r['resourceType']=='Observation')
    report=next(r for r in iter_current(v,p) if r['resourceType']=='DiagnosticReport');old_report=deepcopy(report)
    child=ResourceRef('Observation',old['id'])
    c=start_correction(v,p,child,'transcription: checked source')
    proposal=prepare_candidate(v,c)
    assert any(i['code']=='REPORT_RESULT_REVISION_MISMATCH' for i in render_review(v,proposal).issues)
    commit_candidate(v,proposal,approve(v,proposal))
    assert resolve(v,p,ResourceRef('DiagnosticReport',report['id']))==old_report
    assert any(i.code=='REPORT_RESULT_REVISION_MISMATCH' for row in timeline(v,p) for i in row.issues)
    c=start_correction(v,p,ResourceRef('DiagnosticReport',report['id']),'cancellation: human recorded withdrawal')
    next(e['resource'] for e in c.bundle['entry'] if e['resource']['resourceType']=='DiagnosticReport')['status']='cancelled'
    (c.path/'bundle.json').write_bytes(encode_json(c.bundle))
    proposal=prepare_candidate(v,read_candidate(v,c.path))
    assert any(i['code']=='REPORT_INVALIDATED_WITH_RESULTS' or 'linked result' in i['message'] for i in render_review(v,proposal).issues)
    commit_candidate(v,proposal,approve(v,proposal))
    assert resolve(v,p,child)['status']=='final'
    assert resolve(v,p,ResourceRef('DiagnosticReport',report['id']))['status']=='cancelled'
