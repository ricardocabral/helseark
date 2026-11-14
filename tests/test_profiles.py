"""Artifact/fixture qualification, not a FHIRPath or profile validator."""
import copy
import json
import socket
from decimal import Decimal
from pathlib import Path

import pytest
from jsonschema import Draft6Validator

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / 'profiles/r4/0.1.0'
FIXTURES = ROOT / 'tests/fixtures/synthetic/profiles'
CORE = ROOT / 'definitions/hl7.fhir.r4.core/4.0.1/package'
BASE = 'https://github.com/ricardocabral/helseark/fhir/StructureDefinition/'
NAMES = {
    'Patient': 'patient', 'Observation': 'observation',
    'DiagnosticReport': 'diagnostic-report', 'Specimen': 'specimen',
    'DocumentReference': 'document-reference', 'Provenance': 'provenance',
}


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'), parse_float=Decimal)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError('Profile artifact checks must stay offline')

    monkeypatch.setattr(socket, 'socket', refuse)
    monkeypatch.setattr(socket, 'create_connection', refuse)


@pytest.fixture(scope='module')
def schema():
    value = read(ROOT / 'definitions/fhir-r4-json-schema/fhir.schema.json')
    assert value['$schema'] == 'http://json-schema.org/draft-06/schema#'
    Draft6Validator.check_schema(value)
    return Draft6Validator(value)


@pytest.fixture(scope='module')
def corpus():
    return read(FIXTURES / 'collection.json')


@pytest.mark.parametrize('kind,slug', NAMES.items())
def test_profiles_are_upstream_structures_with_narrowing_differentials(schema, kind, slug):
    profile = read(PROFILES / f'StructureDefinition-helseark-{slug}.json')
    schema.validate(profile)
    upstream = read(CORE / f'StructureDefinition-{kind}.json')
    assert profile['url'] == BASE + 'helseark-' + slug
    assert profile['version'] == '0.1.0'
    assert profile['fhirVersion'] == upstream['fhirVersion'] == '4.0.1'
    assert profile['baseDefinition'] == upstream['url']
    assert profile['type'] == upstream['type'] == kind
    assert profile['kind'] == 'resource'
    assert profile['derivation'] == 'constraint'
    assert profile['abstract'] is False
    elements = profile['differential']['element']
    assert len(elements) > 5
    assert len({e['id'] for e in elements}) == len(elements)
    # Traverse genuine base metadata, including children of complex datatypes.
    base_elements = {e['path']: e for e in upstream['snapshot']['element']}
    for element in elements:
        path = element['path']
        if path not in base_elements:
            parent, child = path.rsplit('.', 1)
            parent_element = base_elements[parent]
            assert len(parent_element['type']) == 1
            datatype = parent_element['type'][0]['code']
            definition = read(CORE / f'StructureDefinition-{datatype}.json')
            base_elements[path] = next(e for e in definition['snapshot']['element']
                                       if e['path'] == datatype + '.' + child)
        base = base_elements[path]
        assert element.get('min', base['min']) >= base['min']
        limit = lambda n: float('inf') if n == '*' else int(n)
        assert limit(element.get('max', base['max'])) <= limit(base['max'])
        if 'type' in element:
            assert {t['code'] for t in element['type']} <= {t['code'] for t in base['type']}
            for typ in element['type']:
                for target in typ.get('targetProfile', []):
                    target_kind = next(k for k, s in NAMES.items()
                                       if target == BASE + 'helseark-' + s + '|0.1.0')
                    allowed = next(t for t in base['type'] if t['code'] == typ['code'])['targetProfile']
                    assert 'http://hl7.org/fhir/StructureDefinition/' + target_kind in allowed or \
                           'http://hl7.org/fhir/StructureDefinition/Resource' in allowed
    by_path = {e['path']: e for e in elements}
    assert by_path[kind + '.id']['min'] == 1
    assert by_path[kind + '.implicitRules']['max'] == '0'
    assert by_path[kind + '.contained']['max'] == '0'
    assert by_path[kind + '.modifierExtension']['max'] == '0'
    if kind in {'Observation', 'DiagnosticReport', 'Specimen', 'DocumentReference'}:
        assert by_path[kind + '.subject']['min'] == 1
        assert by_path[kind + '.subject.reference']['min'] == 1
    assert any(c['severity'] == 'error' for e in elements for c in e.get('constraint', []))


def test_package_exact_release_dependencies():
    package = read(PROFILES / 'package.json')
    assert package['version'] == '0.1.0'
    assert package['canonical'] == BASE.removesuffix('/StructureDefinition/')
    assert package['fhirVersions'] == ['4.0.1']
    assert package['dependencies'] == {'hl7.fhir.r4.core': '4.0.1'}
    assert len(list(PROFILES.glob('StructureDefinition-*.json'))) == 6


def test_synthetic_collection_upstream_schema(schema, corpus):
    schema.validate(corpus)
    resources = [entry['resource'] for entry in corpus['entry']]
    assert {r['resourceType'] for r in resources} == set(NAMES)
    assert len({e['fullUrl'] for e in corpus['entry']}) == len(resources)
    for r in resources:
        schema.validate(r)
        assert r['meta']['profile'] == [BASE + 'helseark-' + NAMES[r['resourceType']] + '|0.1.0']


def test_source_facts_remain_native_and_exact(corpus):
    resources = {r['resource']['id']: r['resource'] for r in corpus['entry']}
    cases = read(FIXTURES / 'expected-facts.json')
    by_label = {r['code']['text']: r for r in resources.values() if r['resourceType'] == 'Observation'}
    for label, facts in cases['observations'].items():
        for field, expected in facts.items():
            assert by_label[label][field] == expected
    q = by_label['Trace analyte']['valueQuantity']
    assert q['value'].as_tuple() == Decimal('0.0500').as_tuple()
    assert by_label['Exact synthetic concentration']['valueQuantity']['value'].as_tuple() == \
        Decimal('1.234567890123456789012345678900').as_tuple()
    assert 'coding' not in by_label['Trace analyte']['code']
    assert 'system' not in q and 'code' not in q
    assert {r['status'] for r in by_label.values()} >= {'final', 'amended', 'cancelled', 'entered-in-error'}


@pytest.mark.parametrize('mutation', ['unknown-field', 'bad-status', 'string-number'])
def test_upstream_schema_detects_real_structural_errors(schema, corpus, mutation):
    observation = copy.deepcopy(next(e['resource'] for e in corpus['entry']
                                     if e['resource']['resourceType'] == 'Observation'))
    if mutation == 'unknown-field':
        observation['madeUpClinicalField'] = True
    elif mutation == 'bad-status':
        observation['status'] = 'approved-by-archive'
    else:
        observation['valueQuantity']['value'] = '0.0500'
    assert list(schema.iter_errors(observation))


@pytest.mark.parametrize('mutation', ['missing-status', 'missing-subject', 'wrong-person',
                                     'two-values', 'value-and-absence', 'range-comparator'])
def test_schema_success_does_not_establish_profile_or_graph_validity(schema, corpus, mutation):
    observation = copy.deepcopy(next(e['resource'] for e in corpus['entry']
                                     if e['resource']['resourceType'] == 'Observation'))
    if mutation == 'missing-status':
        del observation['status']
    elif mutation == 'missing-subject':
        del observation['subject']
    elif mutation == 'wrong-person':
        observation['subject']['reference'] = 'Patient/22222222-2222-4222-8222-222222222222'
    elif mutation == 'two-values':
        observation['valueString'] = 'Conflicting second value'
    elif mutation == 'value-and-absence':
        observation['dataAbsentReason'] = {'text': 'not performed'}
    else:
        observation['referenceRange'] = [{'low': {'value': 5, 'comparator': '<'}}]
    # Deliberately demonstrate actual upstream limitations, never a fake validator.
    schema.validate(observation)


def test_upstream_invariants_remain_an_integration_obligation():
    observation = read(CORE / 'StructureDefinition-Observation.json')
    root = observation['snapshot']['element'][0]
    assert any(c['key'] == 'obs-6' for c in root['constraint'])
    status = next(e for e in observation['snapshot']['element'] if e['path'] == 'Observation.status')
    assert status['min'] == 1 and status['binding']['strength'] == 'required'
    low = next(e for e in observation['snapshot']['element']
               if e['path'] == 'Observation.referenceRange.low')
    assert low['type'][0]['profile'] == ['http://hl7.org/fhir/StructureDefinition/SimpleQuantity']


def test_fixture_reference_closure_and_direct_patient_context(corpus):
    # Qualify this hand-authored example's links, not arbitrary FHIR instances.
    resources = [e['resource'] for e in corpus['entry']]
    patient = next(r for r in resources if r['resourceType'] == 'Patient')
    identity = 'Patient/' + patient['id']
    revisions = {f"{r['resourceType']}/{r['id']}/_history/{r['meta']['versionId']}": r
                 for r in resources}
    references = []

    def collect(value):
        if isinstance(value, dict):
            if 'reference' in value:
                references.append(value['reference'])
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    for resource in resources:
        if resource['resourceType'] in {'Observation', 'DiagnosticReport', 'Specimen', 'DocumentReference'}:
            assert resource['subject'] == {'reference': identity}
        collect(resource)
    assert references and all(ref == identity or ref in revisions for ref in references)
    provenance = next(r for r in resources if r['resourceType'] == 'Provenance')
    source = provenance['entity'][0]
    assert source['role'] == 'source'
    assert revisions[source['what']['reference']]['resourceType'] == 'DocumentReference'
    assert provenance['agent'][0]['who']['identifier']['value'] == 'local-reviewer'
    assert patient['birthDate'] == '1980-02'


def test_specific_profile_constraints_are_present():
    profiles = {kind: read(PROFILES / f'StructureDefinition-helseark-{slug}.json')
                for kind, slug in NAMES.items()}
    elements = {kind: {e['path']: e for e in p['differential']['element']}
                for kind, p in profiles.items()}
    obs = elements['Observation']
    values = {t['code'] for t in obs['Observation.value[x]']['type']}
    assert {'Quantity', 'CodeableConcept', 'string', 'Range', 'Ratio'} <= values
    assert 'SampledData' not in values
    assert obs['Observation.component.value[x]']['type'] == obs['Observation.value[x]']['type']
    assert obs['Observation.component']['constraint'][0]['key'] == 'helseark-component-absence'
    attachment = elements['DocumentReference']
    for field in ('contentType', 'url', 'title'):
        assert attachment['DocumentReference.content.attachment.' + field]['min'] == 1
    assert attachment['DocumentReference.content.attachment.data']['max'] == '0'
    for kind, profile in profiles.items():
        for element in profile['differential']['element']:
            for constraint in element.get('constraint', []):
                assert constraint['source'] == profile['url']
                assert constraint['severity'] == 'error'
                assert constraint['human'] and constraint['expression']
