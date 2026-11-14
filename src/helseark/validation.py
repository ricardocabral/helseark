"""Bounded offline admissibility of FHIR R4 graphs and retained source evidence.

The registry hides byte pins, schema dialect dispatch and local resolution. The
four public operations never fetch URLs or execute FHIRPath, terminology or a
full validator. A clean report still requires review of the final proposal.
"""
from __future__ import annotations

import base64
import csv
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import tarfile
from typing import Sequence
from urllib.parse import urldefrag
from uuid import uuid4

from jsonschema import Draft6Validator, Draft202012Validator
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource, Unresolvable
from referencing.jsonschema import DRAFT6, DRAFT202012
from jsonschema.exceptions import SchemaError

from .contracts import (ArchiveError, Candidate, CheckCoverage, Issue,
                        JsonValue, ResourceRef, ValidationReport, Vault, uuid_string)
from .serialization import decode_json, encode_json, hash_bytes
from .archive import _read, _safe, head, resolve, _versions, _json, _verify_inputs

_CORE = 'http://hl7.org/fhir/StructureDefinition/'
_BASE = 'https://github.com/ricardocabral/helseark/fhir/StructureDefinition/helseark-'
_SLUGS = {'Patient': 'patient', 'Observation': 'observation', 'DiagnosticReport': 'diagnostic-report',
          'Specimen': 'specimen', 'DocumentReference': 'document-reference', 'Provenance': 'provenance'}
# Added resource profiles are versioned independently of the frozen original six.
_HISTORY = {'AllergyIntolerance': 'allergy-intolerance', 'Condition': 'condition', 'MedicationRequest': 'medication-request', 'MedicationStatement': 'medication-statement'}
_SLUGS['MedicationStatement'] = 'medication-statement'
_SLUGS['MedicationRequest'] = 'medication-request'
_SLUGS['Condition'] = 'condition'
_SLUGS['AllergyIntolerance'] = 'allergy-intolerance'
_PATIENT_FIELDS = {'Observation':'subject','DiagnosticReport':'subject','Specimen':'subject','DocumentReference':'subject'}

_PATIENT_FIELDS['MedicationStatement'] = 'subject'

_PATIENT_FIELDS['MedicationRequest'] = 'subject'

_PATIENT_FIELDS['Condition'] = 'subject'

_PATIENT_FIELDS['AllergyIntolerance'] = 'patient'

def _profile(kind):
    return _BASE + _SLUGS[kind] + ('|0.2.0' if kind in _HISTORY else '|0.1.0')

_SCHEMA = 'definitions/fhir-r4-json-schema/fhir.schema.json'
_DIALECTS = {'http://json-schema.org/draft-06/schema#': (Draft6Validator, DRAFT6),
             'https://json-schema.org/draft/2020-12/schema': (Draft202012Validator, DRAFT202012)}
# Deliberately bounded structured surface; unsupported data stays in the source.
_FIELDS = {
    'Patient': 'identifier active name telecom gender birthDate deceasedBoolean deceasedDateTime address maritalStatus multipleBirthBoolean multipleBirthInteger',
    'Observation': 'identifier status category code subject effectiveDateTime effectivePeriod effectiveInstant issued performer valueQuantity valueCodeableConcept valueString valueBoolean valueInteger valueRange valueRatio valueTime valueDateTime valuePeriod dataAbsentReason interpretation note bodySite method specimen referenceRange hasMember derivedFrom component',
    'DiagnosticReport': 'identifier status category code subject effectiveDateTime effectivePeriod issued performer resultsInterpreter specimen result conclusion conclusionCode presentedForm',
    'Specimen': 'identifier accessionIdentifier status type subject receivedTime parent collection processing container condition note',
    'DocumentReference': 'masterIdentifier identifier status docStatus type category subject date author authenticator custodian relatesTo description securityLabel content context',
    'Provenance': 'target occurredPeriod occurredDateTime recorded policy location reason activity agent entity',
    'MedicationStatement': 'identifier status statusReason category medicationCodeableConcept subject context effectiveDateTime effectivePeriod dateAsserted informationSource derivedFrom reasonCode reasonReference note dosage',
    'MedicationRequest': 'identifier status statusReason intent category priority doNotPerform reportedBoolean medicationCodeableConcept subject encounter supportingInformation authoredOn requester reasonCode reasonReference instantiatesCanonical instantiatesUri basedOn groupIdentifier courseOfTherapyType insurance note dosageInstruction dispenseRequest substitution priorPrescription detectedIssue eventHistory',
    'Condition': 'identifier clinicalStatus verificationStatus category severity code bodySite subject encounter onsetDateTime onsetAge onsetPeriod onsetRange onsetString abatementDateTime abatementAge abatementPeriod abatementRange abatementString recordedDate recorder asserter stage evidence note',
    'AllergyIntolerance': 'identifier clinicalStatus verificationStatus type category criticality code patient encounter onsetDateTime onsetAge onsetPeriod onsetRange onsetString recordedDate recorder asserter lastOccurrence note reaction',
    'Bundle': 'type entry',
}
_STATUSES = {
    ('MedicationRequest', 'status'): 'active on-hold cancelled completed entered-in-error stopped draft unknown',
    ('MedicationStatement', 'status'): 'active completed entered-in-error intended stopped on-hold unknown not-taken',
    ('Observation', 'status'): 'registered preliminary final amended corrected cancelled entered-in-error unknown',
    ('DiagnosticReport', 'status'): 'registered partial preliminary final amended corrected appended cancelled entered-in-error unknown',
    ('Specimen', 'status'): 'available unavailable unsatisfactory entered-in-error',
    ('DocumentReference', 'status'): 'current superseded entered-in-error',
    ('DocumentReference', 'docStatus'): 'preliminary final amended entered-in-error',
}
_PRIMITIVES = {'base64Binary','boolean','canonical','code','date','dateTime','decimal','id','instant',
               'integer','markdown','oid','positiveInt','string','time','unsignedInt','uri','url','uuid','xhtml'}


def _pointer(value, pointer: str):
    if pointer == '':
        return value
    if not isinstance(pointer, str) or not pointer.startswith('/'):
        raise ValueError
    for token in pointer[1:].split('/'):
        if re.search(r'~(?![01])', token):
            raise ValueError
        token = token.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', token):
                raise ValueError
            value = value[int(token)]
        elif isinstance(value, dict):
            value = value[token]
        else:
            raise ValueError
    return value


def _walk(value, pointer=''):
    yield pointer, value
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk(item, pointer + '/' + key.replace('~', '~0').replace('/', '~1'))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from _walk(item, pointer + '/' + str(i))


def _offline_missing(uri):
    raise NoSuchResource(ref=uri)


class DefinitionRegistry:
    """Verified local definitions. IDs are identifiers, never fetch instructions."""

    def __init__(self, files: dict[str, bytes]):
        self.files = files
        self._definitions = {}
        core_definitions = {}
        core_path = 'definitions/runtime-core/4.0.1/hl7.fhir.r4.core.tgz'
        if core_path not in files:
            raise ArchiveError('MISSING_DEFINITION', 'Complete pinned core package is missing.')
        with tarfile.open(fileobj=io.BytesIO(files[core_path]), mode='r:gz') as archive:
            members = archive.getmembers()
            if len(members) > 10000 or sum(m.size for m in members) > 64 * 1024 * 1024:
                raise ArchiveError('INVALID_DEFINITION', 'Core package exceeds supported bounds.')
            for member in members:
                match = re.fullmatch(r'package/StructureDefinition-([A-Za-z0-9.-]+)\.json', member.name)
                if match and member.isfile():
                    if member.size > 8 * 1024 * 1024:
                        raise ArchiveError('INVALID_DEFINITION', 'Core member exceeds supported bounds.')
                    try:
                        value = json.loads(archive.extractfile(member).read().decode('utf-8-sig'), parse_float=Decimal)
                        canonical = value['url']
                        version = value.get('version')
                        if not isinstance(canonical, str) or not canonical or '|' in canonical or (
                                version is not None and (not isinstance(version, str) or not version)):
                            raise ValueError
                    except (ValueError, KeyError, UnicodeError, TypeError):
                        raise ArchiveError('INVALID_DEFINITION', 'Core canonical identity is invalid.') from None
                    identifiers = [canonical] + ([canonical + '|' + version] if version else [])
                    for identifier in identifiers:
                        if identifier in core_definitions:
                            raise ArchiveError('DEFINITION_IDENTITY_CONFLICT', 'Duplicate core canonical identity.')
                        core_definitions[identifier] = value
        resources = []
        for path, data in files.items():
            if not path.endswith('.json') or not (path.startswith('schemas/') or
                    '/StructureDefinition-' in path or path == _SCHEMA):
                continue
            try:
                value = json.loads(data.decode('utf-8-sig'), parse_float=Decimal)
            except (ValueError, UnicodeError):
                raise ArchiveError('INVALID_DEFINITION', 'Pinned definition is not valid JSON.') from None
            identifiers = [path]
            canonical = value.get('url') or value.get('$id') or value.get('id')
            if canonical:
                identifiers.append(canonical)
                if value.get('version'):
                    identifiers.append(canonical + '|' + value['version'])
            for identifier in identifiers:
                if identifier in self._definitions:
                    previous = self._definitions[identifier]
                    if identifier != canonical or not previous.get('version') or not value.get('version') or previous['version'] == value['version']:
                        raise ArchiveError('INVALID_DEFINITION', 'Duplicate definition identifier.')
                    if tuple(map(int, previous['version'].split('.'))) > tuple(map(int, value['version'].split('.'))):
                        continue
                self._definitions[identifier] = value
            if '$schema' in value:
                dialect = _DIALECTS.get(value['$schema'])
                if dialect is None:
                    raise ArchiveError('UNSUPPORTED_DIALECT', 'Pinned schema dialect is unsupported.')
                resource = Resource.from_contents(value, default_specification=dialect[1])
                resources.extend((identifier, resource) for identifier in identifiers)
        for identifier, value in core_definitions.items():
            if identifier in self._definitions and self._definitions[identifier] != value:
                raise ArchiveError('DEFINITION_IDENTITY_CONFLICT', 'Pinned canonical definitions conflict.')
            self._definitions[identifier] = value
        self._registry = Registry(retrieve=_offline_missing).with_resources(resources)
        # Fail explicitly before accepting graphs that need missing core profiles.
        for name in [*_SLUGS, 'Bundle', 'SimpleQuantity']:
            self.resolve(_CORE + name)
        for kind in _SLUGS:
            if kind not in _HISTORY:
                self.resolve(_profile(kind))
        self.resolve(_SCHEMA)

    def resolve(self, identifier: str) -> JsonValue:
        base, fragment = urldefrag(identifier)
        try:
            value = self._definitions[base]
            return _pointer(value, '/' + fragment.lstrip('/')) if fragment else value
        except (KeyError, ValueError, IndexError):
            raise ArchiveError('MISSING_DEFINITION', 'Definition is not in the pinned local registry.') from None

    def validate(self, schema: str | dict, value: JsonValue) -> bool:
        schema = self.resolve(schema) if isinstance(schema, str) else schema
        dialect = _DIALECTS.get(schema.get('$schema'))
        if dialect is None:
            raise ArchiveError('UNSUPPORTED_DIALECT', 'Schema must declare a supported dialect.')
        # Preflight all references, even in branches not reached by this instance.
        def check_refs(current, document):
            for _, node in _walk(current):
                if isinstance(node, dict) and '$ref' in node:
                    ref = node['$ref']
                    base, fragment = urldefrag(ref)
                    try:
                        target = self.resolve(base) if base else document
                        if fragment:
                            _pointer(target, '/' + fragment.lstrip('/'))
                    except (ValueError, KeyError, IndexError):
                        raise ArchiveError('MISSING_DEFINITION', 'Schema reference is not local.') from None
        check_refs(schema, schema)
        try:
            return dialect[0](schema, registry=self._registry).is_valid(value)
        except (Unresolvable, SchemaError, ValueError) as error:
            raise ArchiveError('MISSING_DEFINITION', 'Schema cannot resolve from local definitions.') from error


def load_definition_registry(vault: Vault) -> DefinitionRegistry:
    data = _read(vault.root, 'definitions/lock.json')
    if hash_bytes(data) != vault.config.definitionLockSha256:
        raise ArchiveError('DEFINITION_MISMATCH', 'Definition lock checksum mismatch.')
    lock = decode_json(data)
    files = {}
    for artifact in lock['artifacts']:
        for entry in artifact['files']:
            path = entry['path']
            if path in files:
                raise ArchiveError('INVALID_DEFINITION', 'Duplicate definition path.')
            try:
                content = _read(vault.root / 'definitions', path)
            except (ArchiveError, OSError) as error:
                raise ArchiveError('MISSING_DEFINITION', 'Pinned definition file is missing or unsafe.') from error
            if hash_bytes(content) != entry['sha256'] or len(content) != entry['size']:
                raise ArchiveError('DEFINITION_MISMATCH', 'Pinned definition bytes differ.')
            files[path] = content
    return DefinitionRegistry(files)


def schema_packet(vault: Vault, resourceTypes: Sequence[str], destination: Path) -> Path:
    registry = load_definition_registry(vault)
    types = tuple(dict.fromkeys(resourceTypes))
    if not types or any(t not in _SLUGS and t != 'Bundle' for t in types):
        raise ArchiveError('UNSUPPORTED_RESOURCE', 'Requested schema resource type is unsupported.')
    if vault.config.profileVersion != '0.2.0' and any(t in _HISTORY for t in types):
        raise ArchiveError('UNSUPPORTED_PROFILE', 'History requires profile set 0.2.0; retain old vault pins.')
    for kind in types:
        if kind != 'Bundle':
            registry.resolve(_profile(kind))
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ArchiveError('DESTINATION_EXISTS', 'Schema packet destination must not exist.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = destination.parent / ('.helseark-schema-' + str(uuid4()))
    try:
        stage.mkdir(mode=0o700)
        for path, data in registry.files.items():
            target = _safe(stage, path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (stage / 'definitions/lock.json').write_bytes(_read(vault.root, 'definitions/lock.json'))
        (stage / 'packet.json').write_bytes(encode_json({'contractVersion': '0.1.0', 'fhirVersion': '4.0.1',
            'profileVersion': vault.config.profileVersion, 'resourceTypes': list(types),
            'definitionLockSha256': vault.config.definitionLockSha256,
            'coverage': 'Baseline archive rules only; terminology and full FHIR conformance not checked.'}))
        (stage / 'README.md').write_text('Offline Helseark 0.1.0 schema packet.\n'
            'FHIR JSON Schema is draft-06; local envelopes are 2020-12.\n'
            'StructureDefinitions are profile metadata, not JSON Schemas.\n'
            'Includes the complete pinned core package; specification archive is separate.\n'
            'Never fetch missing IDs. Every clinical import requires human review.\n', encoding='utf-8')
        stage.rename(destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return destination


class _Checks:
    def __init__(self, vault, registry, person, base, prepared=False):
        self.vault, self.registry, self.person, self.base = vault, registry, person, base
        self.prepared = prepared
        self.issues = []
        self.failed = set()
        self.checked = set()
        self.resources = {}
        self.aliases = {}
        self.reference_types = {}
        self.typed_resources = set()
        self.assets = {}
        self.family = 'local-envelopes'

    def issue(self, code, pointer=None, ref=None, message=None, severity='error'):
        self.issues.append(Issue(code, severity, pointer, ref, message or code.replace('_', ' ').capitalize() + '.'))
        if severity == 'error':
            self.failed.add(self.family)

    def source_issues(self, issues):
        blocking = {'MULTIPLE_PERSON_CUES','PERSON_MISMATCH','IDENTITY_UNRESOLVED','SOURCE_IDENTITY_UNRESOLVED','SOURCE_IDENTITY_MISMATCH'}
        for issue in issues:
            if issue.code in blocking:
                issue = Issue(issue.code, 'error', issue.pointer, issue.resourceRef, issue.message)
            self.issues.append(issue)
            if issue.severity == 'error':
                self.failed.add('evidence')

    def report(self, digest=None):
        families = ('local-envelopes', 'upstream-json-schema', 'supported-profile-rules',
                    'patient-reference-scope', 'evidence', 'source-hashes', 'time-precision')
        coverage = [CheckCoverage(f, 'failed' if f in self.failed else 'passed' if f in self.checked else 'not-checked',
                                  'Earlier structural failure prevented this check.' if f not in self.checked and f not in self.failed else None) for f in families]
        coverage.extend([CheckCoverage('terminology', 'not-checked', 'No terminology service or licensed expansions executed.'),
                         CheckCoverage('full-fhir', 'not-checked', 'No qualified official validator or general FHIRPath execution.'),
                         CheckCoverage('extraction-accuracy', 'not-checked', 'Quote consistency cannot establish source-row correctness; human review mandatory.')])
        return ValidationReport(digest, tuple(coverage), tuple(self.issues))

    def asset(self, digest):
        if digest in self.assets:
            return self.assets[digest]
        self.family = 'source-hashes'
        self.checked.add(self.family)
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            self.issue('SOURCE_HASH_MISMATCH')
            return None
        try:
            relative = f'people/{self.person}/assets/sha256/{digest}/blob'
            if _safe(self.vault.root, relative).stat().st_size > 100 * 1024 * 1024:
                self.issue('SOURCE_LIMIT')
                return None
            data = _read(self.vault.root, relative)
        except (ArchiveError, OSError):
            self.issue('SOURCE_MISSING')
            return None
        if hash_bytes(data) != digest:
            self.issue('SOURCE_HASH_MISMATCH')
            return None
        self.assets[digest] = data
        return data

    def graph(self, bundle):
        self.family = 'upstream-json-schema'
        if not self.registry.validate(_SCHEMA, bundle):
            self.issue('FHIR_SCHEMA_INVALID')
        self.checked.add('upstream-json-schema')
        self.family = 'supported-profile-rules'
        if not isinstance(bundle, dict) or bundle.get('resourceType') != 'Bundle' or bundle.get('type') != 'collection':
            self.issue('BUNDLE_REQUIRED')
            return
        if set(bundle) - {'resourceType','type','entry','id','meta'}:
            self.issue('UNSUPPORTED_ELEMENT', '/')
        # The collection transport carries only id and optional revision timestamps.
        # Clinical security/source/profile semantics on a transport are unsupported.
        meta = bundle.get('meta', {})
        if isinstance(meta, dict) and set(meta) - {'versionId', 'lastUpdated'}:
            self.issue('UNSUPPORTED_ELEMENT', '/meta')
        bookkeeping = {k: v for k, v in bundle.items() if k != 'entry'}
        for pointer, value in _walk(bookkeeping):
            if isinstance(value, dict) and ('extension' in value or 'modifierExtension' in value or
                    any(k.startswith('_') for k in value)):
                self.issue('UNSUPPORTED_CONTENT', pointer)
        entries = bundle.get('entry', [])
        if not isinstance(entries, list) or not 1 <= len(entries) <= 10000:
            self.issue('RESOURCE_LIMIT')
            return
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) - {'fullUrl','resource'}:
                self.issue('UNSUPPORTED_ELEMENT', '/entry')
                continue
            r = entry.get('resource')
            if not isinstance(r, dict):
                self.issue('FHIR_RESOURCE_REQUIRED')
                continue
            kind, rid = r.get('resourceType'), r.get('id')
            try:
                uuid_string(rid)
            except ArchiveError:
                self.issue('INVALID_ID')
                continue
            if kind not in _SLUGS:
                self.issue('UNSUPPORTED_RESOURCE')
                continue
            key = f'{kind}/{rid}'
            if key in self.resources or entry.get('fullUrl') in self.aliases:
                self.issue('DUPLICATE_RESOURCE', ref=key)
                continue
            self.resources[key] = r
            urn = 'urn:uuid:' + (r.get('meta', {}).get('versionId', '') if self.prepared else rid)
            if entry.get('fullUrl') != urn:
                self.issue('INVALID_FULL_URL', ref=key)
            self.aliases[entry.get('fullUrl', '')] = key
            version = r.get('meta', {}).get('versionId')
            if version:
                self.aliases[key + '/_history/' + version] = key
        if len({r['id'] for r in self.resources.values()}) != len(self.resources):
            self.issue('DUPLICATE_RESOURCE')
        for key, r in self.resources.items():
            self.resource(r, key)
        self.checked.update({'supported-profile-rules','time-precision'})
        self.family = 'patient-reference-scope'
        for key, r in list(self.resources.items()):
            self.references(r, key)
        self.checked.add('patient-reference-scope')

    def resource(self, r, key):
        self.family = 'supported-profile-rules'
        kind = r['resourceType']
        profile = _profile(kind)
        if kind == 'Provenance' and r.get('meta', {}).get('profile') == [_BASE + 'provenance|0.2.0'] and self.vault.config.profileVersion == '0.2.0':
            profile = _BASE + 'provenance|0.2.0'
        if kind in _HISTORY and self.vault.config.profileVersion != '0.2.0':
            self.issue('UNSUPPORTED_PROFILE', '/meta/profile', key)
            return
        if r.get('meta', {}).get('profile') != [profile]:
            self.issue('UNSUPPORTED_PROFILE', '/meta/profile', key)
        meta = r.get('meta', {})
        allowed_meta = {'profile', 'versionId', 'lastUpdated'} if self.prepared else {'profile'}
        if set(meta) - allowed_meta:
            self.issue('UNSUPPORTED_ELEMENT', '/meta', key)
        if self.prepared:
            try:
                uuid_string(meta.get('versionId'))
            except ArchiveError:
                self.issue('REVISION_REQUIRED', '/meta/versionId', key)
            if 'lastUpdated' not in meta:
                self.issue('FHIR_REQUIRED', '/meta/lastUpdated', key)
        elif 'versionId' in meta or 'lastUpdated' in meta:
            self.issue('ARCHIVE_METADATA_FORBIDDEN', '/meta', key)
        allowed = set(_FIELDS[kind].split()) | {'resourceType','id','meta','language','text'}
        for field in r:
            if field not in allowed and field not in {'implicitRules','modifierExtension','contained','extension'}:
                self.issue('UNSUPPORTED_ELEMENT', '/' + field, key)
        for pointer, value in _walk(r):
            if isinstance(value, dict):
                if 'implicitRules' in value or 'modifierExtension' in value:
                    self.issue('UNSUPPORTED_MODIFIER', pointer, key)
                if 'contained' in value or 'extension' in value or any(k.startswith('_') for k in value):
                    self.issue('UNSUPPORTED_CONTENT', pointer, key)
                if not value or set(value) == {'id'}:
                    self.issue('FHIR_EMPTY', pointer, key)
                if 'coding' in value:
                    self.issue('CODING_UNVERIFIED', pointer + '/coding', key,
                               'Source coding retained; terminology meaning not checked.', 'review')
                if 'reference' in value and 'type' in value:
                    typ = value['type']
                    if not isinstance(typ, str) or ('hl7.org/fhir/' in typ and not typ.startswith(_CORE)):
                        self.issue('FHIR_VERSION_MISMATCH', pointer + '/type', key)
            if value is None or value == '' or value == []:
                self.issue('FHIR_EMPTY', pointer, key)
            if isinstance(value, str) and len(value) > 1048576:
                self.issue('TEXT_LIMIT', pointer, key)
        definition = self.registry.resolve(_CORE + kind)
        differential = self.registry.resolve(profile)['differential']['element']
        self.elements(r, definition['snapshot']['element'], kind, '', key, differential)
        self.typed_resources.add((kind, r['id'], r.get('meta', {}).get('versionId')))
        for (resource_type, field), statuses in _STATUSES.items():
            if kind == resource_type and field in r and r[field] not in statuses.split():
                self.issue('FHIR_STATUS_INVALID', '/' + field, key)
        if kind == 'Patient' and r['id'] != self.person:
            self.family = 'patient-reference-scope'
            self.issue('PERSON_MISMATCH', '/id', key)
        if kind in _PATIENT_FIELDS:
            patient_field = _PATIENT_FIELDS[kind]
            self.family = 'patient-reference-scope'
            subject = r.get(patient_field, {}).get('reference') if isinstance(r.get(patient_field, {}), dict) else None
            if subject is None:
                self.issue('SUBJECT_REQUIRED', '/' + patient_field, key)
            elif subject != 'Patient/' + self.person and not (subject == 'urn:uuid:' + self.person and 'Patient/' + self.person in self.resources):
                self.issue('PERSON_MISMATCH', '/' + patient_field + '/reference', key)
        self.family = 'supported-profile-rules'
        if kind == 'MedicationRequest' and r.get('intent') not in 'proposal plan order original-order reflex-order filler-order instance-order option'.split():
            self.issue('FHIR_STATUS_INVALID', '/intent', key)
        if kind == 'Condition':
            verification = {c.get('code') for c in r.get('verificationStatus', {}).get('coding', [])}
            clinical = {c.get('code') for c in r.get('clinicalStatus', {}).get('coding', [])}
            problem_list = any(c.get('code') == 'problem-list-item' for category in r.get('category', []) for c in category.get('coding', []))
            if ('entered-in-error' in verification and 'clinicalStatus' in r or
                    'entered-in-error' not in verification and problem_list and not clinical or
                    any(k.startswith('abatement') for k in r) and not clinical.intersection({'inactive','resolved','remission'})):
                self.issue('CONDITION_STATUS_CONFLICT', '/clinicalStatus', key)
            for field, choices in (('stage', ('summary','assessment')), ('evidence', ('code','detail'))):
                for index, value in enumerate(r.get(field, [])):
                    if not any(value.get(choice) for choice in choices):
                        self.issue('FHIR_REQUIRED', '/' + field + '/' + str(index), key)
        if kind == 'Condition':
            for field, system, allowed_codes in (
                    ('verificationStatus','condition-ver-status','unconfirmed provisional differential confirmed refuted entered-in-error'),
                    ('clinicalStatus','condition-clinical','active recurrence relapse inactive remission resolved')):
                if field not in r:
                    continue
                codings = r[field].get('coding', [])
                if not codings or any(c.get('system') != 'http://terminology.hl7.org/CodeSystem/' + system or c.get('code') not in allowed_codes.split() for c in codings):
                    self.issue('FHIR_STATUS_INVALID', '/' + field, key)
        if kind == 'AllergyIntolerance':
            verification = {c.get('code') for c in r.get('verificationStatus', {}).get('coding', [])}
            if ('entered-in-error' in verification) == ('clinicalStatus' in r):
                self.issue('ALLERGY_STATUS_CONFLICT', '/clinicalStatus', key)
        if kind == 'AllergyIntolerance':
            for field, system, allowed_codes in (
                    ('verificationStatus','allergyintolerance-verification','unconfirmed confirmed refuted entered-in-error'),
                    ('clinicalStatus','allergyintolerance-clinical','active inactive resolved')):
                if field not in r:
                    continue
                codings = r[field].get('coding', [])
                if not codings or any(c.get('system') != 'http://terminology.hl7.org/CodeSystem/' + system or c.get('code') not in allowed_codes.split() for c in codings):
                    self.issue('FHIR_STATUS_INVALID', '/' + field, key)
        if kind == 'Observation':
            self.observation(r, '', key)
            for i, component in enumerate(r.get('component', [])):
                if isinstance(component, dict):
                    self.observation(component, f'/component/{i}', key)
                    root_codes = {(c.get('system'), c.get('code')) for c in r.get('code', {}).get('coding', [])}
                    component_codes = {(c.get('system'), c.get('code')) for c in component.get('code', {}).get('coding', [])}
                    if (component.get('code') == r.get('code') or root_codes & component_codes) and any(k.startswith('value') for k in r):
                        self.issue('OBS_7_CONFLICT', f'/component/{i}/code', key)
        if kind == 'DiagnosticReport' and r.get('status') in {'cancelled','entered-in-error'} and r.get('result'):
            self.issue('RESULT_DISPOSITION_REVIEW', '/result', key,
                       'Source report is cancelled or entered in error; review each linked result disposition.', 'review')
        if kind == 'Provenance':
            if not any(e.get('role') == 'source' for e in r.get('entity', []) if isinstance(e, dict)):
                self.issue('PROVENANCE_SOURCE_REQUIRED', '/entity', key)
            for i, agent in enumerate(r.get('agent', [])):
                who = agent.get('who', {})
                if not (who.get('reference') or who.get('identifier', {}).get('value')):
                    self.issue('PROVENANCE_ACTOR_REQUIRED', f'/agent/{i}/who', key)
        for pointer, node in _walk(r):
            if not isinstance(node, dict):
                continue
            if ('low' in node or 'high' in node) and pointer.endswith(('Range','/age')):
                low, high = node.get('low', {}), node.get('high', {})
                if 'value' in low and 'value' in high:
                    if low.get('unit') != high.get('unit') or low.get('system') != high.get('system') or low.get('code') != high.get('code'):
                        self.issue('RANGE_UNIT_MISMATCH', pointer, key)
                    elif low['value'] > high['value']:
                        self.issue('RANGE_ORDER_INVALID', pointer, key)
            if 'numerator' in node and node.get('denominator', {}).get('value') == 0:
                self.issue('RATIO_ZERO_DENOMINATOR', pointer, key)

    def observation(self, node, pointer, key):
        if 'dataAbsentReason' in node and any(k.startswith('value') for k in node):
            self.issue('FHIR_CHOICE_CONFLICT', pointer, key)
        for i, bounds in enumerate(node.get('referenceRange', [])):
            if not any(k in bounds for k in ('low','high','text')):
                self.issue('OBS_3_RANGE_REQUIRED', pointer + f'/referenceRange/{i}', key)

    def elements(self, obj, elements, path, pointer, key, differential=()):
        if not isinstance(obj, dict):
            return  # upstream schema reports the type failure
        children = [e for e in elements if e['path'].rsplit('.', 1)[0] == path and e['path'] != path]
        for original in children:
            element = dict(original)
            for override in differential:
                if override['path'] == original['path']:
                    element.update(override)
            field = element['path'].rsplit('.', 1)[-1]
            choices = field.endswith('[x]')
            prefix = field[:-3] if choices else field
            types = element.get('type', [])
            options = {prefix + t['code'][0].upper() + t['code'][1:]: t for t in types} if choices else {field: types[0] if types else {}}
            present = [f for f in options if f in obj]
            count = sum(len(obj[f]) if isinstance(obj[f], list) else 1 for f in present)
            if count < element.get('min', 0):
                self.issue('FHIR_REQUIRED', pointer + '/' + prefix, key)
            if element.get('max') != '*' and count > int(element.get('max', '1')):
                self.issue('FHIR_CHOICE_CONFLICT' if choices else 'FHIR_CARDINALITY', pointer + '/' + prefix, key)
            if choices:
                # Differential may exclude a choice that the upstream schema permits.
                if any(f.startswith(prefix) and len(f) > len(prefix) and f[len(prefix)].isupper() and f not in options for f in obj):
                    self.issue('UNSUPPORTED_ELEMENT', pointer + '/' + prefix, key)
            for f in present:
                typ = options[f]
                code = typ.get('code', '')
                values = obj[f] if isinstance(obj[f], list) else [obj[f]]
                for i, value in enumerate(values):
                    loc = pointer + '/' + f + ('/' + str(i) if isinstance(obj[f], list) else '')
                    if code in ('date','dateTime','instant','time'):
                        self.time(value, code, loc, key)
                    if code == 'Reference':
                        allowed = set()
                        for canonical in typ.get('targetProfile', [_CORE + 'Resource']):
                            target_type = self.registry.resolve(canonical).get('type')
                            allowed.update(_SLUGS if target_type in {'Resource','DomainResource'} else [target_type])
                        self.reference_types[(key, loc)] = allowed
                    if code == 'BackboneElement' or 'contentReference' in element:
                        nextpath = element.get('contentReference', '#' + element['path']).removeprefix('#')
                        self.elements(value, elements, nextpath, loc, key, differential)
                    elif code and code not in _PRIMITIVES and not code.startswith('http'):
                        definition_id = next(iter(typ.get('profile', [])), _CORE + code)
                        definition = self.registry.resolve(definition_id)
                        if definition.get('type') == 'Quantity' and definition.get('id') == 'SimpleQuantity' and isinstance(value, dict) and 'comparator' in value:
                            self.issue('SIMPLE_QUANTITY_COMPARATOR', loc + '/comparator', key)
                        self.elements(value, definition['snapshot']['element'], definition.get('type', code), loc, key)
                        # Local differential paths can descend into datatype children.
                        self.differential_children(value, original['path'], loc, key, differential)
                    if code == 'Quantity' and isinstance(value, dict):
                        if 'value' in value and (type(value['value']) not in (int, Decimal)):
                            self.issue('QUANTITY_NUMBER_REQUIRED', loc + '/value', key)
                        if 'code' in value and 'system' not in value:
                            self.issue('QUANTITY_SYSTEM_REQUIRED', loc, key)
                        if 'comparator' in value and value['comparator'] not in ('<','<=','>=','>'):
                            self.issue('QUANTITY_COMPARATOR_INVALID', loc, key)

    def differential_children(self, obj, path, pointer, key, differential):
        if not isinstance(obj, dict):
            return
        for e in differential:
            if e['path'].rsplit('.', 1)[0] != path:
                continue
            field = e['path'].rsplit('.', 1)[-1]
            if e.get('min', 0) and field not in obj:
                self.issue('FHIR_REQUIRED', pointer + '/' + field, key)
            if e.get('max') == '0' and field in obj:
                self.issue('UNSUPPORTED_ELEMENT', pointer + '/' + field, key)

    def time(self, value, code, pointer, key):
        self.family = 'time-precision'
        valid = isinstance(value, str)
        if valid:
            try:
                if code == 'time':
                    valid = bool(re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]:(?:[0-5][0-9]|60)(?:\.[0-9]+)?', value))
                elif re.fullmatch(r'[0-9]{4}(?:-[0-9]{2})?(?:-[0-9]{2})?', value) and code != 'instant':
                    pieces = value.split('-')
                    date(int(pieces[0]), int(pieces[1]) if len(pieces)>1 else 1, int(pieces[2]) if len(pieces)>2 else 1)
                else:
                    valid = code != 'date' and bool(re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|[+-](?:0[0-9]|1[0-4]):[0-5][0-9])', value))
                    if valid:
                        parsed = datetime.fromisoformat(value.replace('Z','+00:00'))
                        valid = abs(parsed.utcoffset().total_seconds()) <= 14*3600
                    elif 'T' in value and not re.search(r'(?:Z|[+-][0-9]{2}:[0-9]{2})$', value):
                        self.issue('DATE_TIMEZONE_UNKNOWN', pointer, key, 'Retain local clock as source text; reduce precision only with review.', 'review')
            except ValueError:
                valid = False
        if not valid:
            self.issue('FHIR_TIME_INVALID', pointer, key)
        self.family = 'supported-profile-rules'

    def lookup(self, reference, pointer=None, origin=None):
        self.family = 'patient-reference-scope'
        if not isinstance(reference, str):
            self.issue('INVALID_REFERENCE', pointer, origin)
            return None
        if self.prepared and reference.startswith('urn:uuid:'):
            self.issue('REVISION_REQUIRED', pointer, origin)
            return None
        if reference in self.aliases:
            return self.resources[self.aliases[reference]]
        if reference.startswith('urn:uuid:'):
            self.issue('REFERENCE_NOT_FOUND', pointer, origin)
            return None
        match = re.fullmatch(r'([A-Z][A-Za-z]+)/([0-9a-f-]{36})(?:/_history/([0-9a-f-]{36}))?', reference)
        if not match:
            self.issue('INVALID_REFERENCE', pointer, origin)
            return None
        kind, rid, version = match.groups()
        if kind not in _SLUGS:
            self.issue('UNSUPPORTED_RESOURCE', pointer, origin)
            return None
        if kind == 'Patient' and rid != self.person:
            self.issue('PERSON_MISMATCH', pointer, origin)
            return None
        if not version and kind != 'Patient':
            self.issue('REVISION_REQUIRED', pointer, origin)
            return None
        if version is None and kind == 'Patient' and pointer and pointer.startswith('/target/') and (origin or '').startswith('Provenance/'):
            self.issue('REVISION_REQUIRED', pointer, origin)
            return None
        try:
            return resolve(self.vault, self.person, ResourceRef(kind, rid, version), at=self.base)
        except ArchiveError as error:
            self.issue(error.code if error.code in {'INTEGRITY','DEFINITION_MISMATCH','STALE_BASE'} else 'REFERENCE_NOT_FOUND', pointer, origin)
            return None

    def references(self, resource, key, visited=None):
        visited = set() if visited is None else visited
        identity = (resource.get('resourceType'), resource.get('id'), resource.get('meta', {}).get('versionId'))
        if identity in visited:
            return
        visited.add(identity)
        kind = resource.get('resourceType')
        if kind not in _SLUGS:
            self.issue('UNSUPPORTED_RESOURCE', ref=key)
            return
        if kind in _HISTORY and self.vault.config.profileVersion != '0.2.0':
            self.issue('UNSUPPORTED_PROFILE', '/meta/profile', key)
            return
        if kind == 'Patient' and resource.get('id') != self.person:
            self.issue('PERSON_MISMATCH', ref=key)
        if kind in _PATIENT_FIELDS:
            patient_field = _PATIENT_FIELDS[kind]
            subject = resource.get(patient_field, {}).get('reference') if isinstance(resource.get(patient_field, {}), dict) else None
            if subject is None:
                self.issue('SUBJECT_REQUIRED', '/' + patient_field, key)
            elif subject != 'Patient/' + self.person and not (subject == 'urn:uuid:' + self.person and not self.prepared):
                self.issue('PERSON_MISMATCH', '/' + patient_field + '/reference', key)
        if identity not in self.typed_resources:
            definition = self.registry.resolve(_CORE + kind)
            differential = [] if kind == 'Patient' else self.registry.resolve(resource.get('meta', {}).get('profile', [_profile(kind)])[0])['differential']['element']
            self.elements(resource, definition['snapshot']['element'], kind, '', key, differential)
            self.typed_resources.add(identity)
            self.family = 'patient-reference-scope'
        profiles = resource.get('meta', {}).get('profile', [])
        if any('|5.' in p or '|3.' in p for p in profiles):
            self.issue('FHIR_VERSION_MISMATCH', '/meta/profile', key)
        for pointer, value in _walk(resource):
            if not isinstance(value, dict) or 'reference' not in value:
                continue
            target = self.lookup(value['reference'], pointer + '/reference', key)
            if target is None:
                continue
            target_kind = target.get('resourceType')
            # Check the constrained target sets, not merely existence of a UUID.
            field = next((p for p in reversed(pointer.split('/')) if p and not p.isdigit()), '')
            inherited_allowed = self.reference_types.get((key, pointer))
            if inherited_allowed is not None and target_kind not in inherited_allowed:
                self.issue('REFERENCE_TYPE_MISMATCH', pointer, key)
            allowed = {'subject': {'Patient'}, 'patient': {'Patient'}, 'specimen': {'Specimen'}, 'result': {'Observation'},
                       'hasMember': {'Observation'}, 'derivedFrom': {'Observation','DocumentReference'},
                       'parent': {'Specimen'}}.get(field)
            if kind == 'Provenance' and re.fullmatch(r'/entity/[0-9]+/what', pointer):
                entity = resource['entity'][int(pointer.split('/')[2])]
                if entity.get('role') == 'source':
                    allowed = {'DocumentReference'}
            if allowed is not None and target_kind not in allowed:
                self.issue('REFERENCE_TYPE_MISMATCH', pointer, key)
            declared = value.get('type')
            if declared and declared not in (target_kind, _CORE + target_kind):
                self.issue('REFERENCE_TYPE_MISMATCH', pointer + '/type', key)
            self.references(target, f'{target_kind}/{target.get("id")}', visited)
        for pointer, node in _walk(resource):
            if not isinstance(node, dict) or not pointer.endswith('/attachment') and not (kind == 'DiagnosticReport' and pointer.startswith('/presentedForm/') and pointer.count('/') == 2):
                continue
            if 'url' not in node or 'data' in node:
                self.issue('ATTACHMENT_LOCAL_REQUIRED', pointer, key)
                continue
            match = re.fullmatch(r'assets/sha256/([0-9a-f]{64})/blob', node['url']) if isinstance(node['url'], str) else None
            if not match:
                self.issue('ATTACHMENT_LOCAL_REQUIRED', pointer + '/url', key)
                continue
            data = self.asset(match[1])
            if data is not None:
                if 'size' in node and node['size'] != len(data):
                    self.issue('SOURCE_SIZE_MISMATCH', pointer + '/size', key)
                if 'hash' in node:
                    if node['hash'] != base64.b64encode(hashlib.sha1(data).digest()).decode('ascii'):
                        self.issue('ATTACHMENT_HASH_INVALID', pointer + '/hash', key)
            self.family = 'patient-reference-scope'

    def evidence(self, evidence, sources):
        self.family = 'evidence'
        if not self.registry.validate('urn:helseark:schema:0.1.0:evidence', evidence):
            self.issue('INVALID_ENVELOPE')
        if not isinstance(evidence, dict) or evidence.get('personId') != self.person:
            self.issue('PERSON_MISMATCH')
            return
        from .agent_context import _verify_producer
        try:
            _verify_producer(self.vault,evidence.get('producerProvenance'),self.registry)
        except (ArchiveError, TypeError, AttributeError):
            self.issue('PRODUCER_MISMATCH')
        covered = set()
        entries = evidence.get('entries', [])
        if not isinstance(entries, list):
            return
        for entry in entries:
            self.family = 'evidence'
            if not isinstance(entry, dict):
                continue
            target = entry.get('target', {})
            ref = target.get('reference', entry.get('resourceRef'))
            # Prepared evidence binds the actual produced immutable revision.
            if self.prepared and (not isinstance(ref, str) or '/_history/' not in ref):
                self.issue('EVIDENCE_TARGET_INVALID', ref=ref)
                continue
            # Evidence can describe only resources actually produced by this graph.
            resource_key = self.aliases.get(ref, ref if ref in self.resources else None)
            if resource_key not in self.resources:
                self.issue('EVIDENCE_TARGET_INVALID', ref=ref)
                continue
            resource = self.resources[resource_key]
            pointers = target.get('pointers', [entry.get('pointer')])
            if not isinstance(pointers, list):
                continue
            for pointer in pointers:
                try:
                    target_value = _pointer(resource, pointer)
                except (ValueError, TypeError, KeyError, IndexError):
                    self.issue('EVIDENCE_POINTER_INVALID', pointer, ref)
                    continue
                for suffix, leaf in _walk(target_value):
                    if isinstance(leaf, (dict,list)):
                        continue
                    full = pointer + suffix
                    generated = (self.prepared and resource['resourceType'] == 'Provenance' and entry.get('rule') == 'prepare-provenance-1' and bool(re.fullmatch(r'/(?:recorded|target/[0-9]+/reference|agent/[0-9]+/who/identifier/(?:system|value)|entity/[0-9]+/(?:role|what/reference))', full))) or full in {'/id','/resourceType'} or full.startswith('/meta/') or bool(re.fullmatch(r'/content/[0-9]+/attachment/url', full))
                    if entry.get('kind') == 'generated' and not generated:
                        self.issue('GENERATED_CLINICAL_EVIDENCE', full, ref)
                    elif entry.get('kind') == 'user-entry' and not (self.prepared and resource['resourceType'] == 'Patient'):
                        self.issue('USER_ENTRY_EVIDENCE_FORBIDDEN', full, ref)
                    else:
                        covered.add((resource_key, full))
            if entry.get('kind') != 'source':
                continue
            digest = entry.get('sourceSha256')
            if digest not in sources:
                self.issue('SOURCE_NOT_DECLARED', ref=ref)
            data = self.asset(digest)
            self.family = 'evidence'
            source_document = self.lookup(entry.get('sourceDocument'), origin=ref)
            self.family = 'evidence'
            if source_document is None or source_document.get('resourceType') != 'DocumentReference' or not any(
                    item.get('attachment', {}).get('url') == f'assets/sha256/{digest}/blob'
                    for item in source_document.get('content', [])):
                self.issue('SOURCE_DOCUMENT_MISMATCH', ref=ref)
            locator = entry.get('locator', {})
            if not isinstance(locator, dict):
                continue
            bbox = locator.get('bbox')
            if bbox is not None and (not isinstance(bbox, list) or len(bbox) != 4 or
                    any(type(x) not in (int, Decimal) or not 0 <= x <= 1 for x in bbox) or
                    not (bbox[0] < bbox[2] and bbox[1] < bbox[3])):
                self.issue('INVALID_BBOX', ref=ref)
            if data is not None:
                try:
                    quote = entry['quote']
                    kind = locator['kind']
                    if kind == 'json-pointer':
                        located = _pointer(decode_json(data), locator['pointer'])
                        text = located if isinstance(located, str) else encode_json(located).decode().strip()
                    elif kind == 'csv-cell':
                        reader = csv.DictReader(io.StringIO(data.decode('utf-8')), delimiter=locator['delimiter'])
                        rows = list(reader)
                        text = rows[locator['row']-1][locator['column']]
                    elif kind in {'text-span','pdf-page'}:
                        provenance = entry.get('extraction', {})
                        if provenance.get('status') != 'known':
                            self.issue('EXTRACTION_PROVENANCE_UNKNOWN', ref=ref, severity='review',
                                       message='Extraction provenance is unknown; human review required.')
                        extraction = self.asset(locator['extractionSha256'])
                        self.family = 'evidence'
                        if extraction is None:
                            continue
                        if kind == 'text-span':
                            text = extraction.decode('utf-8')
                            start, end = locator['start'], locator['end']
                            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
                                raise ValueError
                            text = text[start:end]
                        else:
                            pages = decode_json(extraction)
                            if pages['sourceSha256'] != digest:
                                raise ValueError
                            page = pages['pages'][locator['page']-1]
                            if page['page'] != locator['page'] or page['rotation'] != locator['pageRotationApplied']:
                                raise ValueError
                            text = page['text']
                    else:
                        raise ValueError
                    if isinstance(quote, str) and re.search(r'[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}', quote) and not re.search(r'(?:Z|[+-][0-9]{2}:[0-9]{2})', quote):
                        self.issue('DATE_TIMEZONE_UNKNOWN', ref=ref, severity='review',
                                   message='Source clock has no offset; retain its text and review any reduced precision.')
                    if not isinstance(quote, str) or not quote or quote not in text:
                        self.issue('EVIDENCE_QUOTE_MISMATCH', ref=ref)
                    self.source_token(entry, resource, ref)
                except (KeyError, TypeError, ValueError, IndexError, UnicodeError, csv.Error, ArchiveError):
                    self.issue('EVIDENCE_LOCATOR_INVALID', ref=ref)
        self.family = 'evidence'
        for key, resource in self.resources.items():
            for pointer, value in _walk(resource):
                if isinstance(value, (dict,list)) or pointer == '/resourceType':
                    continue
                if (key, pointer) not in covered:
                    self.issue('EVIDENCE_MISSING', pointer, key)
        self.checked.add('evidence')

    def source_token(self, entry, resource, ref):
        transformation = entry.get('transformation')
        if not transformation:
            return
        if transformation.get('rule') == 'decimal-comma-v1':
            match = re.search(r'(?P<comparator><=|>=|<|>)?\s*(?P<number>-?[0-9]+(?:,[0-9]+)?)', entry['quote'])
            if match is None:
                self.issue('SOURCE_TOKEN_MISMATCH', ref=ref)
                return
            number = Decimal(match['number'].replace(',','.'))
            for pointer in entry['target']['pointers']:
                target = _pointer(resource, pointer)
                for suffix, value in _walk(target):
                    leaf = pointer + suffix
                    if leaf.endswith('/value') and (type(value) not in (int, Decimal) or value != number or
                            min(0, Decimal(value).as_tuple().exponent) != number.as_tuple().exponent):
                        self.issue('SOURCE_TOKEN_MISMATCH', leaf, ref)
                    if leaf.endswith('/comparator') and value != match['comparator']:
                        self.issue('SOURCE_TOKEN_MISMATCH', leaf, ref)
                    if leaf.endswith('/unit') and value != entry['quote'][match.end():].strip():
                        self.issue('SOURCE_TOKEN_MISMATCH', leaf, ref)
        else:
            self.issue('TRANSFORMATION_UNVERIFIED', ref=ref,
                       message='Source transformation is not machine checked; human review required.', severity='review')


def validate_candidate(vault: Vault, candidate: Candidate) -> ValidationReport:
    """Validate candidate bytes and its selected-person graph; never publish."""
    # Local import avoids the intake/validator construction dependency. All disk
    # rereads use intake's no-follow, allocation and JSON field/depth boundary.
    from .intake import _bounded_json, LIMITS
    registry = load_definition_registry(vault)
    checks = _Checks(vault, registry, candidate.personId, candidate.base)
    try:
        if candidate.path.is_symlink():
            raise ArchiveError('UNSAFE_PATH', 'Candidate root cannot be a symlink.')
        uuid_string(candidate.personId)
        uuid_string(candidate.candidateId)
        metadata = _bounded_json(candidate.path / 'candidate.json', LIMITS)
        if not isinstance(metadata, dict):
            raise ArchiveError('INVALID_ENVELOPE', 'Candidate metadata must be an object.')
        if metadata.get('fhirVersion') != vault.config.fhirVersion:
            checks.issue('FHIR_VERSION_MISMATCH')
        if any(k in metadata and metadata[k] != v for k, v in {
                'contractVersion':vault.config.contractVersion,'profileVersion':vault.config.profileVersion,
                'fhirVersion':vault.config.fhirVersion}.items()):
            raise ArchiveError('UNSUPPORTED_VERSION', 'Candidate version pins are unsupported.')
        checks.checked.add('local-envelopes')
        if not registry.validate('urn:helseark:schema:0.1.0:candidate', metadata):
            checks.issue('INVALID_ENVELOPE')
            return checks.report()
        expected = {'candidateId': candidate.candidateId, 'personId': candidate.personId,
                    'baseChangeSha256': candidate.base.changeSha256 if candidate.base else None,
                    'unresolved': [asdict(i) for i in candidate.unresolved]}
        if any(metadata.get(k) != v for k, v in expected.items()):
            checks.issue('CANDIDATE_MISMATCH')
        if head(vault, candidate.personId) != candidate.base:
            checks.issue('STALE_BASE')
        for field, value in (('bundlePath', candidate.bundle), ('evidencePath', candidate.evidence)):
            disk = _bounded_json(_safe(candidate.path, metadata[field]), LIMITS)
            if encode_json(disk) != encode_json(value):
                checks.issue('CANDIDATE_MISMATCH')
        if metadata.get('producerProvenance') != candidate.evidence.get('producerProvenance'):
            checks.issue('PRODUCER_MISMATCH')
        checks.graph(candidate.bundle)
        sources = metadata.get('sourceSha256', [])
        for source in sources:
            checks.asset(source)
        checks.evidence(candidate.evidence, sources)
        checks.source_issues(candidate.unresolved)
        if any(i.severity == 'error' for i in candidate.unresolved):
            checks.failed.add('evidence')
    except (ArchiveError, OSError) as error:
        checks.family = 'local-envelopes'
        checks.issue(error.code if isinstance(error, ArchiveError) else 'IO_ERROR')
    except (TypeError, KeyError, ValueError, IndexError, AttributeError):
        checks.family = 'local-envelopes'
        checks.issue('INVALID_ENVELOPE')
    return checks.report()


def validate_proposal(vault: Vault, proposalDirectory: Path) -> ValidationReport:
    """Check a prepared inventory and exact resource/evidence/assets before review.

    This operation does not read or authorize a review receipt. Its digest binds
    the report to the exact retained proposal bytes, with no circular hashes.
    """
    registry = load_definition_registry(vault)
    checks = _Checks(vault, registry, None, None, prepared=True)
    digest = None
    try:
        if Path(proposalDirectory).is_symlink():
            raise ArchiveError('UNSAFE_PATH', 'Proposal root cannot be a symlink.')
        raw = _read(proposalDirectory, 'proposal.json')
        digest = hash_bytes(raw)
        proposal = _json(proposalDirectory, 'proposal.json', data=raw)
        checks.person = proposal.get('personId') if isinstance(proposal, dict) else None
        if isinstance(proposal, dict):
            pins = proposal.get('versions')
            if ('contractVersion' in proposal and proposal['contractVersion'] != vault.config.contractVersion or
                    isinstance(pins, dict) and any(k in pins and pins[k] != v for k,v in _versions(vault).items())):
                raise ArchiveError('UNSUPPORTED_VERSION', 'Proposal version pins are unsupported.')
        checks.checked.add('local-envelopes')
        if not registry.validate('urn:helseark:schema:0.1.0:proposal', proposal):
            checks.issue('INVALID_ENVELOPE')
            return checks.report(digest)
        _verify_inputs(proposalDirectory,proposal)
        for item in proposal.get('inputs', []):
            if not re.fullmatch(r'inputs/[a-z-]+[.]json',item['path']) or hash_bytes(_read(proposalDirectory,item['path']))!=item['sha256']:
                checks.issue('CANDIDATE_MISMATCH')
        checks.base = head(vault, checks.person)
        if proposal['baseChangeSha256'] != (checks.base.changeSha256 if checks.base else None):
            checks.issue('STALE_BASE')
        if proposal['versions'] != _versions(vault):
            checks.issue('FHIR_VERSION_MISMATCH' if proposal['versions']['fhirVersion'] != vault.config.fhirVersion else 'UNSUPPORTED_VERSION')
        entries = []
        seen = set()
        for item in proposal['resources']:
            identity = (item['type'], item['id'])
            if identity in seen:
                checks.issue('DUPLICATE_RESOURCE')
            seen.add(identity)
            if item['path'] != f"resources/{item['type']}-{item['id']}.json":
                checks.issue('UNSAFE_PATH')
            content = _read(proposalDirectory, item['path'])
            resource = _json(proposalDirectory, item['path'], data=content)
            if hash_bytes(content) != item['sha256']:
                checks.issue('RESOURCE_HASH_MISMATCH')
            if not isinstance(resource, dict) or (resource.get('id'), resource.get('resourceType'), resource.get('meta', {}).get('versionId')) != (item['id'],item['type'],item['versionId']):
                checks.issue('RESOURCE_INVENTORY_MISMATCH')
            entries.append({'fullUrl': 'urn:uuid:' + item['versionId'], 'resource': resource})
        checks.graph({'resourceType':'Bundle','type':'collection','entry':entries})
        sources = []
        media_types = {}
        checks.checked.add('source-hashes')
        for item in proposal['assets']:
            if item['sha256'] in media_types:
                checks.issue('DUPLICATE_ASSET')
            media_types[item['sha256']] = item['mediaType']
            sources.append(item['sha256'])
            if item['path'] != f'assets/sha256/{item["sha256"]}/blob':
                checks.issue('UNSAFE_PATH')
            data = checks.asset(item['sha256'])
            if data is not None and len(data) != item['size']:
                checks.issue('SOURCE_SIZE_MISMATCH')
        evidence_bytes = _read(proposalDirectory, 'evidence.json')
        if hash_bytes(evidence_bytes) != proposal['evidenceSha256']:
            checks.issue('EVIDENCE_HASH_MISMATCH')
        checks.evidence(_json(proposalDirectory, 'evidence.json', data=evidence_bytes), sources)
        if any(item['type'] != 'Patient' for item in proposal['resources']) and 'unresolved' not in proposal:
            checks.issue('SOURCE_ISSUES_REQUIRED')
        checks.source_issues(tuple(Issue(**i) for i in proposal.get('unresolved', [])))
        checks.family = 'source-hashes'
        if set(checks.assets) - set(sources):
            checks.issue('SOURCE_NOT_DECLARED')
        for _, node in _walk({'resources': list(checks.resources.values())}):
            if isinstance(node, dict) and isinstance(node.get('url'), str):
                match = re.fullmatch(r'assets/sha256/([0-9a-f]{64})/blob', node['url'])
                if match and node.get('contentType') != media_types.get(match[1]):
                    checks.issue('SOURCE_MEDIA_TYPE_MISMATCH')
    except (ArchiveError, OSError) as error:
        checks.issue(error.code if isinstance(error, ArchiveError) else 'IO_ERROR')
    except (TypeError, KeyError, ValueError, IndexError, AttributeError):
        checks.issue('INVALID_ENVELOPE')
    return checks.report(digest)
