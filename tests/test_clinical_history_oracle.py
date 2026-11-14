"""Independent synthetic source/fact oracle through public archive APIs.

Candidates are pre-authored, not extracted. This tests archive preservation and
review/evidence enforcement; it does not measure extraction accuracy.
"""
import copy
from pathlib import Path
from uuid import uuid4

import pytest

from helseark.archive import add_person, commit_candidate, head, init_vault, open_vault, resolve
from helseark.contracts import ArchiveError, Candidate, Issue, PersonDraft, ResourceRef, ReviewDecision
from helseark.intake import add_source, prepare_candidate
from helseark.query import history, timeline
from helseark.review import record_review, render_review
from helseark.serialization import decode_json, encode_json
from helseark.validation import validate_candidate
from test_validation import leaves, no_network, persist

FIXTURES = Path(__file__).parent / 'fixtures'
SOURCE = FIXTURES / 'synthetic/clinical-history/oracle'
ORACLE = decode_json((FIXTURES / 'expected/clinical-history-facts.json').read_bytes())
# Explicit attribution, independently of the expected native facts.
SOURCE_FIELDS = {
    'MedicationStatement': 'reportedUse', 'MedicationRequest': 'prescription',
    'Condition': 'condition', 'AllergyIntolerance': 'allergy',
    'Immunization': 'vaccination', 'Procedure': 'procedure',
    'Encounter': 'encounter', 'FamilyMemberHistory': 'relative',
}


@pytest.fixture
def oracle_candidate(tmp_path):
    """Bind the fixed proposal to retained source bytes, never generate the source."""
    vault = init_vault(tmp_path / 'vault')
    person = add_person(vault, PersonDraft('Synthetic history oracle patient'))
    receipt = add_source(vault, person, SOURCE / 'source.json')
    source = decode_json((SOURCE / 'source.json').read_bytes())
    resources = decode_json((SOURCE / 'candidate-resources.json').read_bytes().replace(b'PERSON', person.encode()))
    doc_id = str(uuid4())
    resources.append({
        'resourceType': 'DocumentReference', 'id': doc_id, 'status': 'current',
        'meta': {'profile': ['https://github.com/ricardocabral/helseark/fhir/StructureDefinition/helseark-document-reference|0.1.0']},
        'subject': {'reference': 'Patient/' + person},
        'content': [{'attachment': {'url': f'assets/sha256/{receipt.sourceSha256}/blob',
                                   'contentType': 'application/json',
                                   'title': 'Synthetic independent history source'}}],
    })
    entries, evidence = [], []
    for resource in resources:
        kind = resource['resourceType']
        resource.setdefault('id', str(uuid4()))
        alias = 'urn:uuid:' + resource['id']
        entries.append({'fullUrl': alias, 'resource': resource})
        for pointer, _ in leaves(resource):
            if pointer == '/resourceType':
                continue
            item = {'target': {'reference': alias, 'pointers': [pointer]}}
            if pointer == '/id' or pointer.startswith('/meta/') or pointer == '/content/0/attachment/url':
                item.update(kind='generated', rule='synthetic-oracle-bookkeeping-v1')
            else:
                field = ('identity' if pointer in ('/subject/reference', '/patient/reference') else
                         'document' if kind == 'DocumentReference' else SOURCE_FIELDS[kind])
                item.update(kind='source', sourceSha256=receipt.sourceSha256,
                            sourceDocument='urn:uuid:' + doc_id, quote=source[field],
                            locator={'kind': 'json-pointer', 'pointer': '/' + field})
            evidence.append(item)
    path = tmp_path / 'candidate'
    path.mkdir()
    candidate = Candidate(
        path, str(uuid4()), person, head(vault, person),
        {'resourceType': 'Bundle', 'type': 'collection', 'entry': entries},
        {'contractVersion': '0.1.0', 'personId': person, 'entries': evidence},
        (Issue('UNSUPPORTED_CONTENT', 'review', '/unsupported', None, source['unsupported']),),
    )
    return vault, persist(candidate), receipt


def pointer(value, path):
    """Read a test fact; missing paths raise rather than equating absence with null."""
    for part in path.split('/')[1:]:
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def assert_facts(resources):
    selected = [r for r in resources if r['resourceType'] in ORACLE['families']]
    assert len(selected) == 8
    assert {r['resourceType'] for r in selected} == set(ORACLE['families'])
    for resource in selected:
        expected = ORACLE['families'][resource['resourceType']]
        for path, fact in expected['facts'].items():
            # Serialized equality also checks decimal scale, false and native types.
            assert encode_json(pointer(resource, path)) == encode_json(fact), (resource['resourceType'], path)
        for path in expected['absent']:
            with pytest.raises((KeyError, IndexError)):
                pointer(resource, path)
    assert not any(r['resourceType'] == 'ImagingStudy' for r in resources)
    conditions = [r for r in selected if r['resourceType'] == 'Condition']
    assert len(conditions) == 1  # Mother's assertion must not become a second diagnosis.


def test_independent_facts_survive_review_publication_and_reopen(oracle_candidate):
    vault, candidate, receipt = oracle_candidate
    assert_facts([e['resource'] for e in candidate.bundle['entry']])
    report = validate_candidate(vault, candidate)
    assert not [i for i in report.issues if i.severity == 'error'], report.issues
    assert {c.family: c.result for c in report.coverage}['extraction-accuracy'] == 'not-checked'
    initial = head(vault, candidate.personId)
    proposal = prepare_candidate(vault, candidate, authorized_sources=(receipt.sourceSha256,))
    assert head(vault, candidate.personId) == initial
    with pytest.raises((ArchiveError, AttributeError, TypeError)):
        commit_candidate(vault, proposal, None)
    assert head(vault, candidate.personId) == initial
    view = render_review(vault, proposal)
    assert any(i['code'] == 'UNSUPPORTED_CONTENT' and i['message'] == ORACLE['unsupported'] for i in view.issues)
    assert_facts(view.resourcesAdded)
    acks = {(i['code'], i['resourceRef']): {'code': i['code'], 'resourceRef': i['resourceRef'],
            'reason': 'Synthetic reviewer compared the independent source; retain unknowns and source-only ImagingStudy.'}
            for i in view.issues if i['severity'] in ('review', 'warning')}
    review = record_review(vault, proposal, ReviewDecision(
        True, 'accept-with-acknowledged-limitations', tuple(acks.values()), 'synthetic human'))
    commit_candidate(vault, proposal, review)
    reopened = open_vault(vault.root)
    native = list(history(reopened, candidate.personId, list(ORACLE['families'])))
    assert_facts(native)
    assert any(r['resourceType'] == 'Provenance' for r in native)
    assert not list(history(reopened, candidate.personId, list(ORACLE['families']), initial))
    rows = [r for r in timeline(reopened, candidate.personId) if r.resourceRef.resourceType in ORACLE['families']]
    assert len(rows) == 8
    assert_facts([r.resource for r in rows])
    for row in rows:
        expected = ORACLE['families'][row.resourceRef.resourceType]
        assert row.effectiveType == expected['effectiveType']
        assert row.timePrecision == expected['timePrecision']
        assert row.sourceRefs
        assert encode_json(resolve(reopened, candidate.personId, row.resourceRef)) == encode_json(row.resource)
    blob = vault.root / f'people/{candidate.personId}/assets/sha256/{receipt.sourceSha256}/blob'
    assert blob.read_bytes() == (SOURCE / 'source.json').read_bytes()
    assert decode_json(blob.read_bytes())['unsupported'] == ORACLE['unsupported']
    other = add_person(reopened, PersonDraft('Synthetic history oracle patient'))
    assert not list(history(reopened, other, list(ORACLE['families'])))


@pytest.mark.parametrize('kind', sorted(SOURCE_FIELDS))
def test_single_clinical_leaf_requires_source_evidence(oracle_candidate, kind):
    vault, candidate, _ = oracle_candidate
    baseline = validate_candidate(vault, candidate)
    assert_facts([e['resource'] for e in candidate.bundle['entry']])
    assert not [i for i in baseline.issues if i.severity == 'error'], baseline.issues
    original = copy.deepcopy(candidate.evidence['entries'])
    entry = next(e for e in candidate.bundle['entry'] if e['resource']['resourceType'] == kind)
    leaf = ORACLE['families'][kind]['attackLeaf']
    target = {'reference': entry['fullUrl'], 'pointers': [leaf]}
    selected = [e for e in original if e['target'] == target]
    assert len(selected) == 1 and selected[0]['kind'] == 'source'
    assert selected[0]['locator']['pointer'] == ORACLE['families'][kind]['sourcePointer']
    for attack, expected_code in [('remove', 'EVIDENCE_MISSING'), ('generated', 'GENERATED_CLINICAL_EVIDENCE')]:
        candidate.evidence['entries'] = [copy.deepcopy(e) for e in original if e['target'] != target]
        if attack == 'generated':
            candidate.evidence['entries'].append({'target': target, 'kind': 'generated', 'rule': 'forged-clinical-fact'})
        persist(candidate)
        errors = [i for i in validate_candidate(vault, candidate).issues if i.severity == 'error']
        issue_ref = entry['fullUrl'] if attack == 'generated' else f"{kind}/{entry['resource']['id']}"
        assert any(i.code == expected_code and i.pointer == leaf and i.resourceRef == issue_ref for i in errors), errors
        assert {i.code for i in errors} <= {'EVIDENCE_MISSING', 'GENERATED_CLINICAL_EVIDENCE'}, errors
    candidate.evidence['entries'] = original
    persist(candidate)
    assert not [i for i in validate_candidate(vault, candidate).issues if i.severity == 'error']
