"""Query contracts over actual accepted synthetic files, never mocked storage."""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
import copy
import shutil

import pytest
from helseark import archive
from helseark.contracts import ArchiveError, ResourceRef, PersonDraft
from helseark.serialization import encode_json, decode_json, hash_bytes
from test_validation import good as clinical_candidate, persist, leaves, BASE, asset, OBS
from test_agent_context import accept_fixture


def api():
    from helseark.query import observations, timeline
    from helseark.contracts import ObservationFilter
    return observations, timeline, ObservationFilter


def enrich(vault, candidate, resources):
    """Source-authored JSON corpus, each leaf independently bound to its source.

    The fixture compiler is the existing test-only compiler, not Task6 code.
    Clinical source facts are not manufactured by the query under test.
    """
    doc = next(e for e in candidate.bundle['entry'] if e['resource']['resourceType']=='DocumentReference')
    candidate.bundle['entry'] = [*resources, doc]
    source = {entry['resource']['id']: copy.deepcopy(entry['resource']) for entry in [*resources, doc]}
    digest = asset(vault, candidate.personId, encode_json(source))
    doc['resource']['content'][0]['attachment']['url'] = f'assets/sha256/{digest}/blob'
    evidence = []
    for entry in [*resources, doc]:
        for pointer, value in leaves(entry['resource']):
            if pointer == '/resourceType':
                continue
            item = {'target': {'reference': entry['fullUrl'], 'pointers': [pointer]}}
            if pointer == '/id' or pointer.startswith('/meta/'):
                item.update(kind='generated', rule='synthetic-query-fixture-v1')
            else:
                item.update(kind='source', sourceSha256=digest, sourceDocument=doc['fullUrl'],
                            quote=str(value) if not isinstance(value, bool) else str(value).lower(),
                            locator={'kind': 'json-pointer', 'pointer': '/' + entry['resource']['id'] + pointer})
            evidence.append(item)
    # Retain original document metadata evidence, binding the new content address.
    # Document asset URL is generated; source description remains source-bound.
    for item in evidence:
        if item['target']['pointers'] == ['/content/0/attachment/url']:
            for key in ('sourceSha256','sourceDocument','quote','locator'): item.pop(key,None)
            item.update(kind='generated',rule='archive-asset-path-v1')
    candidate.evidence['entries'] = evidence
    return persist(candidate)


@pytest.fixture
def corpus(clinical_candidate, tmp_path):
    vault, candidate = clinical_candidate
    template = candidate.bundle['entry'][0]
    resources = []
    facts = [
        ('month', '2026-11', 'final', {'valueQuantity': {'value': Decimal('0.050'), 'comparator': '<', 'unit': 'mg/L'}}, 'serum', 'hs', '0–1'),
        ('day', '2026-11-14', 'final', {'valueQuantity': {'value': Decimal('1.2300'), 'unit': 'mg/dL'}}, 'plasma', 'standard', '2–4'),
        ('before', '2026-10-31', 'final', {'valueQuantity': {'value': 8, 'unit': 'mmol/L'}}, 'serum', 'standard', '5–9'),
        ('unknown', None, 'final', {'valueCodeableConcept': {'text': 'Negative'}}, 'serum', 'hs', 'not detected'),
        ('cancelled', '2026-11-14', 'cancelled', {'dataAbsentReason': {'text': 'Not performed'}}, 'serum', 'hs', 'n/a'),
        ('error', '2026-11-14', 'entered-in-error', {'valueString': 'Synthetic narrative — not a numeric result'}, 'serum', 'hs', 'n/a'),
        ('period', {'start': '2026-10-31', 'end': '2026-11-02'}, 'final', {'valueRange': {'low': {'value': Decimal('2.50')}, 'high': {'value': Decimal('4.00')}}}, 'serum', 'hs', '1–5'),
        ('offset', '2026-11-14T00:15:00+02:00', 'final', {'valueBoolean': False}, 'serum', 'hs', 'n/a'),
        ('local', '2026-11-14', 'final', {'valueString': 'Unzoned'}, 'serum', 'hs', 'n/a'),
    ]
    ids = {}
    for name, effective, status, value, specimen, method, bounds in facts:
        entry = copy.deepcopy(template)
        rid = OBS if name == 'month' else str(uuid4())
        ids[name] = rid
        r = entry['resource']
        r.update(id=rid, status=status, code={'text': 'Proteína C reativa — ultrassensível', 'coding': [{'system':'urn:synthetic:lab', 'code':'crp'}]},
                 method={'text':method}, referenceRange=[{'text':bounds}], note=[{'text':f'Synthetic {specimen} context'}])
        r.pop('effectiveDateTime', None)
        r.pop('valueQuantity', None)
        r.update(value)
        if effective is not None:
            r['effectivePeriod' if isinstance(effective, dict) else 'effectiveDateTime'] = effective
        # Distinct real Specimen resources, no invented grouping or conversion.
        sid = str(uuid4())
        r['specimen'] = {'reference':'urn:uuid:'+sid}
        resources.append({'fullUrl':'urn:uuid:'+sid, 'resource':{'resourceType':'Specimen','id':sid,
            'meta':{'profile':[BASE+'specimen|0.1.0']}, 'subject':{'reference':'Patient/'+candidate.personId}, 'type':{'text':specimen}}})
        entry['fullUrl'] = 'urn:uuid:'+rid
        resources.append(entry)
    report = copy.deepcopy(candidate.bundle['entry'][2])
    report['resource']['effectiveDateTime'] = '2026-11-14'
    resources.append(report)
    enrich(vault, candidate, resources)
    accepted = accept_fixture(vault, candidate, tmp_path)
    return vault, candidate, ids, archive.head(vault, candidate.personId), accepted


def test_query_needs_only_canonical_files(corpus):
    obs, timeline, Filter = api()
    vault, candidate, ids, _, _ = corpus
    derived=vault.root/'derived';derived.mkdir(exist_ok=True)
    (derived/'observations.json').write_text('{"syntheticPoison":999}')
    before = list(obs(vault, candidate.personId, Filter()))
    events = list(timeline(vault, candidate.personId))
    for folder in (vault.root/'.runtime', vault.root/'derived', vault.root/'people'/candidate.personId/'work'):
        if folder.exists(): shutil.rmtree(folder)
    assert list(obs(vault, candidate.personId, Filter())) == before
    assert list(timeline(vault, candidate.personId)) == events
    assert len(before) == 7 and len(events) >= 10


def test_ranges_and_units_stay_per_measurement(corpus):
    obs, _, Filter = api()
    vault, candidate, ids, _, _ = corpus
    rows = {r.resourceRef.id:r for r in obs(vault, candidate.personId, Filter(exactSourceLabel='Proteína C reativa — ultrassensível'))}
    assert rows[ids['month']].unit == 'mg/L' and rows[ids['month']].referenceRanges == [{'text':'0–1'}]
    assert rows[ids['day']].unit == 'mg/dL' and rows[ids['day']].referenceRanges == [{'text':'2–4'}]
    assert rows[ids['before']].unit == 'mmol/L'
    assert rows[ids['month']].method == {'text':'hs'}
    assert rows[ids['day']].method == {'text':'standard'}
    assert rows[ids['month']].specimenRef != rows[ids['day']].specimenRef
    assert rows[ids['unknown']].value == {'text':'Negative'}
    assert rows[ids['unknown']].timeBucket == 'unknown'
    assert rows[ids['offset']].value is False
    assert rows[ids['period']].value == {'low':{'value':Decimal('2.50')},'high':{'value':Decimal('4.00')}}
    assert len(list(obs(vault,candidate.personId,Filter(codeSystem='urn:synthetic:lab',code='crp')))) == 7
    assert not list(obs(vault,candidate.personId,Filter(codeSystem='urn:other',code='crp')))


def test_below_limit_not_point_value(corpus):
    obs, _, Filter = api()
    vault,candidate,ids,_,_ = corpus
    row = next(r for r in obs(vault,candidate.personId,Filter()) if r.resourceRef.id == ids['month'])
    assert row.value['value'].as_tuple() == Decimal('0.050').as_tuple()
    assert row.comparator == '<' and row.valueType == 'valueQuantity'
    assert row.sourceRefs
    for binding in row.sourceRefs:
        evidence = decode_json((vault.root/binding.evidencePath).read_bytes())
        assert hash_bytes((vault.root/binding.evidencePath).read_bytes()) == binding.evidenceSha256
        item = evidence['entries'][int(binding.entryPointer.split('/')[-1])]
        assert item['target']['reference'] == f'Observation/{row.resourceRef.id}/_history/{row.resourceRef.versionId}'
        if binding.sourceSha256:
            assert (vault.root/f'people/{candidate.personId}/assets/sha256/{binding.sourceSha256}/blob').is_file()


def test_partial_dates_report_overlap(corpus):
    obs,_,Filter = api()
    vault,candidate,ids,_,_ = corpus
    rows={r.resourceRef.id:r for r in obs(vault,candidate.personId,Filter(fromDate='2026-11-14',toDate='2026-11-14'))}
    assert set(rows) == {ids[k] for k in ('month','day','unknown','offset','local')}
    assert rows[ids['month']].effective == '2026-11'
    assert rows[ids['month']].timePrecision == 'month' and rows[ids['month']].timeFilterRelation == 'overlap'
    assert rows[ids['day']].timeFilterRelation == 'contained'
    assert rows[ids['unknown']].timeFilterRelation == 'unknown'
    broad={r.resourceRef.id:r for r in obs(vault,candidate.personId,Filter(fromDate='2026-11',toDate='2026-11'))}
    assert broad[ids['month']].timeFilterRelation == 'contained'
    assert broad[ids['period']].timeFilterRelation == 'overlap'
    precise={r.resourceRef.id:r for r in obs(vault,candidate.personId,Filter(fromDate='2026-11-13T22:00:00Z',toDate='2026-11-13T22:30:00Z'))}
    assert ids['offset'] in precise and precise[ids['offset']].effective.endswith('+02:00')
    assert precise[ids['local']].timeFilterRelation == 'unknown'
    assert ids['period'] in {r.resourceRef.id for r in obs(vault,candidate.personId,Filter(fromDate='2026-11-02',toDate='2026-11-02'))}
    assert ids['period'] not in {r.resourceRef.id for r in obs(vault,candidate.personId,Filter(fromDate='2026-11-03',toDate='2026-11-03'))}


def test_invalidated_are_explicit_history_not_default_trends(corpus):
    obs, timeline, Filter = api()
    v,c,ids,_,_ = corpus
    rows={r.resourceRef.id:r for r in obs(v,c.personId,Filter(includeInvalidated=True))}
    assert len(rows) == 9
    assert rows[ids['error']].value == 'Synthetic narrative — not a numeric result'
    assert rows[ids['cancelled']].dataAbsentReason == {'text':'Not performed'}
    events={r.resourceRef.id:r for r in timeline(v,c.personId)}
    assert events[ids['error']].status == 'entered-in-error'
    assert events[ids['cancelled']].status == 'cancelled'


def test_historical_report_children_and_mismatch(corpus,tmp_path):
    obs,timeline,Filter=api()
    v,c,ids,old_head,accepted=corpus
    old=next(r for r in obs(v,c.personId,Filter()) if r.resourceRef.id==OBS)
    old_resource=archive.resolve(v,c.personId,old.resourceRef)
    item=copy.deepcopy(next(e for e in c.bundle['entry'] if e['resource']['id']==OBS))
    item['resource']['valueQuantity']['value']=Decimal('0.0750')
    item['resource']['specimen']=copy.deepcopy(old_resource['specimen'])
    later=tmp_path/'later';later.mkdir()
    c=replace(c,path=later/'candidate',base=old_head)
    c.path.mkdir()
    enrich(v,c,[item])
    # DocumentReference is also present in fixture compilation, unchanged logical ID.
    supersedes={(e['type'],e['id']):e['versionId'] for e in decode_json((accepted/'proposal.json').read_bytes())['resources']}
    accept_fixture(v,c,later,supersedes)
    current=next(r for r in obs(v,c.personId,Filter()) if r.resourceRef.id==OBS)
    assert current.value['value'].as_tuple()==Decimal('0.0750').as_tuple()
    assert {b.sourceSha256 for b in current.sourceRefs if b.sourceSha256} != {b.sourceSha256 for b in old.sourceRefs if b.sourceSha256}
    for binding in (*old.sourceRefs,*current.sourceRefs):
        if binding.sourceDocument:
            from helseark.query import parse_reference
            document=archive.resolve(v,c.personId,parse_reference(binding.sourceDocument))
            assert binding.sourceSha256 in document['content'][0]['attachment']['url']
    assert next(r for r in obs(v,c.personId,Filter(),at=old_head) if r.resourceRef.id==OBS)==old
    report=next(r for r in timeline(v,c.personId) if r.resourceRef.resourceType=='DiagnosticReport')
    assert report.resultRefs == (old.resourceRef,)
    assert archive.resolve(v,c.personId,report.resultRefs[0])==old_resource
    assert 'REPORT_RESULT_REVISION_MISMATCH' in {i.code for i in report.issues}
    assert 'REPORT_RESULT_REVISION_MISMATCH' in {i.code for i in current.issues}
    historical=next(r for r in timeline(v,c.personId,at=old_head) if r.resourceRef.resourceType=='DiagnosticReport')
    assert not historical.issues


@pytest.mark.parametrize('kwargs',[{'fromDate':'2026-02-30'},{'fromDate':'2026-12','toDate':'2026-11'}, {'codeSystem':''},{'includeInvalidated':1},{'fromDate':3},{'fromDate':'2026-11-01T00:00:00'}])
def test_invalid_filters_are_typed(kwargs):
    _,_,Filter=api()
    with pytest.raises(ArchiveError,match='INVALID_FILTER'):
        Filter(**kwargs)


def test_person_scope_and_typed_missing_person(corpus):
    obs,_,Filter=api()
    v,c,_,_,_=corpus
    other=archive.add_person(v,PersonDraft('Synthetic Person A'))
    assert list(obs(v,other,Filter()))==[]
    with pytest.raises(ArchiveError,match='INVALID_ID'):
        list(obs(v,None,Filter()))
    with pytest.raises(ArchiveError,match='PERSON_NOT_FOUND'):
        list(obs(v,str(uuid4()),Filter()))


def test_date_context_pages_use_query_without_changing_evidence_authority(corpus,tmp_path):
    from helseark.agent_context import build_agent_context, read_agent_context, render_task_prompt
    from helseark.contracts import ContextRequest
    obs,_,Filter=api()
    v,c,ids,_,_=corpus
    # Host explicitly authorizes this synthetic source. Date filtering must
    # not broaden selected references; projection refusal is tested separately.
    refs=tuple(ResourceRef('Observation',ids[k]) for k in ('month','day','before','unknown'))
    expected={ids[k] for k in ('month','day','unknown')}
    request=ContextRequest(sourceHashes=tuple(sorted({e['sourceSha256'] for e in c.evidence['entries'] if 'sourceSha256' in e})),resourceRefs=refs,fromDate='2026-11-14',toDate='2026-11-14',maxRecords=1)
    seen=[]; token=None
    for index in range(4):
        context=build_agent_context(v,c.personId,'query',replace(request,continuation=token),tmp_path/f'page-{index}')
        seen.extend(decode_json((context.path/f.path).read_bytes())['id'] for f in context.selectedRecords)
        assert context.totalCount==3 and context.returnedCount==1
        assert context.dataBytes<=request.maxDataBytes
        # On-disk packets still need the host's original authority.
        packet=read_agent_context(context.path)
        with pytest.raises(ArchiveError,match='CONTEXT_AUTHORITY_REQUIRED'):
            render_task_prompt(packet,'query-with-evidence',{'source_data':{},'output_directory':str(tmp_path/f'answer-{index}')})
        rendered=render_task_prompt(packet,'query-with-evidence',{'source_data':{},'output_directory':str(tmp_path/f'answer-{index}')},trusted_context_sha256=context.trustedContextSha256)
        assert rendered.text
        token=context.continuation
        if token is None: break
    assert set(seen)==expected and len(seen)==3
    context=build_agent_context(v,c.personId,'query',request,tmp_path/'first')
    with pytest.raises(ArchiveError,match='INVALID_CONTINUATION'):
        build_agent_context(v,c.personId,'query',replace(request,fromDate='2026-10',continuation=context.continuation),tmp_path/'changed')
    # Context filtering uses the same uncertain-time decisions as query rows.
    assert expected <= {r.resourceRef.id for r in obs(v,c.personId,Filter(fromDate=request.fromDate,toDate=request.toDate))}


@pytest.mark.parametrize('value', [
    {'valueQuantity':{'value':Decimal('1.200'),'comparator':'>','unit':'mg/L'}},
    {'valueQuantity':{'value':Decimal('1.200'),'comparator':'>=','unit':'mg/L'}},
    {'valueQuantity':{'value':Decimal('1.200'),'comparator':'<=','unit':'mg/L'}},
    {'valueRatio':{'numerator':{'value':Decimal('1.20')},'denominator':{'value':Decimal('2.00')}}},
    {'valueInteger':0}, {'valueString':'Synthetic nested narrative'},
    {'component':[{'code':{'text':'Systolic synthetic'},'valueQuantity':{'value':120,'unit':'mmHg'},'referenceRange':[{'text':'source range'}]},
                  {'code':{'text':'Diastolic synthetic'},'valueQuantity':{'value':80,'unit':'mmHg'}}]},
])
def test_native_shapes_are_never_numeric_coercions(clinical_candidate,tmp_path,value):
    obs,_,Filter=api()
    v,c=clinical_candidate
    item=copy.deepcopy(c.bundle['entry'][0]);item['resource'].pop('valueQuantity')
    item['resource'].update(copy.deepcopy(value))
    enrich(v,c,[item])
    accept_fixture(v,c,tmp_path)
    row=list(obs(v,c.personId,Filter()))[0]
    if 'component' in value:
        assert row.component==value['component'] and row.value is None
    else:
        key=next(iter(value))
        assert row.valueType==key and encode_json(row.value)==encode_json(value[key])


def test_fractional_instants_use_exact_boundaries(clinical_candidate,tmp_path):
    obs,_,Filter=api()
    v,c=clinical_candidate
    item=copy.deepcopy(c.bundle['entry'][0])
    item['resource']['effectiveDateTime']='2026-11-14T23:59:59.9999999Z'
    enrich(v,c,[item]);accept_fixture(v,c,tmp_path)
    assert len(list(obs(v,c.personId,Filter(fromDate='2026-11-14',toDate='2026-11-14'))))==1
    assert not list(obs(v,c.personId,Filter(toDate='2026-11-14T23:59:59.9999998Z')))
    assert len(list(obs(v,c.personId,Filter(fromDate='2026-11-14T23:59:59.9999999Z',toDate='2026-11-14T23:59:59.9999999Z'))))==1


def test_accepted_limitations_bind_the_original_revision(corpus):
    obs,_,Filter=api()
    v,c,ids,_,_=corpus
    rows=list(obs(v,c.personId,Filter()))
    assert len(rows)==7
    for row in rows:
        assert 'CODING_UNVERIFIED' in {i.code for i in row.issues}


@pytest.mark.parametrize('offset', ['+00:60', '+01:99', '+02:60', '-00:60', '-01:99', '-02:60',
                                    '+14:01', '-14:01', '+15:00', '-15:00', '+24:00', '+1:00', '+0100'])
def test_filter_rejects_malformed_or_out_of_range_offsets(offset):
    _, _, Filter = api()
    with pytest.raises(ArchiveError, match='INVALID_FILTER'):
        Filter(fromDate='2024-02-29T00:00:00.00000001'+offset)


@pytest.mark.parametrize('stamp', ['2023-02-29T00:00:00Z', '2024-02-30T00:00:00Z',
                                   '2024-02-29T24:00:00Z', '2024-02-29T00:60:00Z',
                                   '2024-02-29T00:00:60Z'])
def test_filter_rejects_invalid_timestamp_day_or_clock(stamp):
    _, _, Filter = api()
    with pytest.raises(ArchiveError, match='INVALID_FILTER'):
        Filter(toDate=stamp)


@pytest.mark.parametrize('stamp', ['2024-02-29T14:00:00.00000001+14:00',
                                   '2024-02-28T10:00:00.00000001-14:00',
                                   '2024-02-28T23:01:00.00000001-00:59',
                                   '2024-02-29T13:59:00.00000001+13:59'])
def test_valid_offset_boundaries_preserve_inclusive_fractional_instant(stamp):
    from helseark.query import matches_dates
    _, _, Filter = api()
    resource = {'effectiveDateTime': stamp}
    assert matches_dates(resource, Filter(fromDate='2024-02-29T00:00:00.00000001Z',
                                         toDate='2024-02-29T00:00:00.00000001Z'))
    assert not matches_dates(resource, Filter(toDate='2024-02-29T00:00:00.000000009Z'))
    assert not matches_dates(resource, Filter(fromDate='2024-02-29T00:00:00.000000011Z'))


def test_context_rejects_malformed_offset_before_writing(corpus, tmp_path):
    from helseark.contracts import ContextRequest
    from helseark.agent_context import build_agent_context
    v, c, _, _, _ = corpus
    for index, offset in enumerate(('+00:60', '+01:99', '+02:60', '-00:60', '-02:60')):
        destination = tmp_path/f'invalid-context-{index}'
        with pytest.raises(ArchiveError, match='INVALID_FILTER'):
            build_agent_context(v, c.personId, 'query',
                                ContextRequest(fromDate='2024-02-29T00:00:00'+offset), destination)
        assert not destination.exists()


def test_query_verifies_history_once_for_eight_report_children(clinical_candidate, tmp_path):
    import sys
    obs, timeline, Filter = api()
    v, c = clinical_candidate
    template = c.bundle['entry'][0]
    resources = []
    for index in range(8):
        entry = copy.deepcopy(template)
        rid = OBS if index == 0 else str(uuid4())
        entry['fullUrl'] = 'urn:uuid:'+rid
        entry['resource']['id'] = rid
        resources.append(entry)
    report = copy.deepcopy(c.bundle['entry'][2])
    report['resource']['result'] = [{'reference': e['fullUrl']} for e in resources]
    enrich(v, c, [*resources, report])
    accept_fixture(v, c, tmp_path)
    opens = []
    active = False
    def count(event, args):
        if active and event == 'open' and str(args[0]).endswith('/change.json'):
            opens.append(str(args[0]))
    sys.addaudithook(count)
    for query in (lambda: list(obs(v, c.personId, Filter())), lambda: list(timeline(v, c.personId))):
        opens.clear()
        active = True
        try:
            rows = query()
        finally:
            active = False
        assert rows
        assert len(opens) == len(set(opens)) == 2
    # A second call must verify again, including accepted payloads from genesis.
    patient = next((v.root/'people'/c.personId/'accepted').glob('*/resources/Patient-*.json'))
    patient.write_bytes(patient.read_bytes()+b' ')
    with pytest.raises(ArchiveError, match='INTEGRITY'):
        list(obs(v, c.personId, Filter()))


def test_verified_snapshot_rejects_unknown_and_other_person_references(corpus):
    v, c, _, base, _ = corpus
    snapshot = archive._ResourceSnapshot(v, c.personId, base)
    other = archive.add_person(v, PersonDraft('Synthetic unrelated person'))
    for ref in (ResourceRef('Observation', str(uuid4())),
                ResourceRef('Observation', OBS, str(uuid4())),
                ResourceRef('Patient', other)):
        with pytest.raises(ArchiveError, match='RESOURCE_NOT_FOUND'):
            snapshot.resolve(ref)
    with pytest.raises(ArchiveError, match='UNKNOWN_HEAD'):
        archive._ResourceSnapshot(v, c.personId, replace(base, changeSha256='0'*64))


@pytest.mark.parametrize('operation', ['observations', 'timeline'])
def test_snapshot_second_read_checksum_error_has_safe_resource_path(corpus, operation):
    import os
    import sys
    obs, timeline, Filter = api()
    v, c, _, _, _ = corpus
    query = (lambda: list(obs(v, c.personId, Filter()))) if operation == 'observations' else (
        lambda: list(timeline(v, c.personId)))
    before = query()
    target = next((v.root/'people'/c.personId/'accepted').glob('*/resources/Patient-*.json'))
    original = target.read_bytes()
    fd = os.open(target, os.O_RDWR)
    reads = 0
    active = True

    def change_on_second_open(event, args):
        nonlocal reads
        if active and event == 'open' and str(args[0]) == str(target):
            reads += 1
            if reads == 2:
                # Alter real bytes after history verification, before snapshot parsing.
                os.pwrite(fd, b'X', 0)

    sys.addaudithook(change_on_second_open)
    try:
        with pytest.raises(ArchiveError) as caught:
            query()
        assert reads == 2
        assert caught.value.code == 'INTEGRITY'
        assert caught.value.details == {'path': target.relative_to(v.root).as_posix()}
    finally:
        active = False
        os.pwrite(fd, original, 0)
        os.ftruncate(fd, len(original))
        os.close(fd)
    assert target.read_bytes() == original
    assert query() == before
