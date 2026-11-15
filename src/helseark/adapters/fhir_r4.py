"""Bounded FHIR R4 Bundle import to untrusted candidates, never accepted history.

Identity and provider namespace are explicit local inputs. Unknown content is
inventoried at source pointers and blocks preparation, while original bytes stay
untouched. Local revision allocation remains the production compiler's job.
"""
from copy import deepcopy
from dataclasses import dataclass
from uuid import uuid4
from urllib.parse import urlsplit

from ..contracts import ArchiveError, Candidate, SourceReceipt, Issue, uuid_string
from ..serialization import decode_json, encode_json
from ..validation import _FIELDS, _SLUGS, _walk, _profile as native_profile, load_definition_registry


@dataclass(frozen=True)
class IdentityMapping:
    patientReference: str
    localPersonId: str
    assignmentReason: str
    provider: str

    def __post_init__(self):
        uuid_string(self.localPersonId)
        if (not isinstance(self.patientReference,str) or not self.patientReference or
                not isinstance(self.assignmentReason,str) or not self.assignmentReason.strip() or
                not isinstance(self.provider,str) or urlsplit(self.provider).scheme not in ('https','http','urn')):
            raise ArchiveError('IDENTITY_MAPPING_REQUIRED','Explicit incoming Patient, local assignment and provider URI required.')


def _profile(kind):
    return {'profile':[native_profile(kind)]}


def _source_document(source, person, media):
    return {'resourceType':'DocumentReference','id':str(uuid4()),'meta':_profile('DocumentReference'),
        'status':'current','subject':{'reference':'Patient/'+person},
        'content':[{'attachment':{'contentType':media,'url':f'assets/sha256/{source.sourceSha256}/blob',
                                  'size':source.size,'title':'Retained structured source'}}]}


def _evidence(source, document, ref, pointers, locator, quote, method, *, rule=None, description=None):
    entry = {'kind':'source','target':{'reference':ref,'pointers':pointers},
        'sourceSha256':source.sourceSha256,'sourceDocument':'urn:uuid:'+document['id'],
        'locator':locator,'quote':quote,
        'extraction':{'provenanceVersion':'1','status':'known','method':method,
            'tool':'helseark.serialization','version':'helseark-json-1','model':None,'preprocessing':[]}}
    if rule:
        entry['transformation']={'rule':rule,'description':description or rule}
    return entry


def import_fhir_r4(source: SourceReceipt, person: str, mapping: IdentityMapping) -> Candidate:
    from ..intake import _structured_source, _structured_candidate, LIMITS
    if not isinstance(mapping,IdentityMapping):
        raise ArchiveError('IDENTITY_MAPPING_REQUIRED','Use a local explicit IdentityMapping.')
    if mapping.localPersonId!=person:
        raise ArchiveError('PERSON_MISMATCH','Mapping differs from explicitly selected person.')
    vault,data = _structured_source(source,person)
    incoming = decode_json(data)
    if not isinstance(incoming,dict) or incoming.get('resourceType')!='Bundle' or not isinstance(incoming.get('entry'),list):
        raise ArchiveError('INVALID_INPUT','Expected an R4 JSON Bundle with entries.')
    if len(incoming['entry'])>LIMITS.candidateResources-1:
        raise ArchiveError('RESOURCE_LIMIT','Structured export exceeds resource count limit.')
    registry=load_definition_registry(vault)
    schema=registry.resolve('definitions/fhir-r4-json-schema/fhir.schema.json')
    definitions=schema['definitions']
    def unknown_fields(value, definition, pointer):
        if '$ref' in definition:
            name=definition['$ref'].rsplit('/',1)[-1]
            # ResourceList is a union; select the actual native schema before
            # descending through entry.resource (including unsupported types).
            if name=='ResourceList' and isinstance(value,dict) and isinstance(value.get('resourceType'),str):
                name=value.get('resourceType')
            definition=definitions.get(name,{})
        if isinstance(value,dict) and 'properties' in definition:
            for k,v in value.items():
                child=pointer+'/'+k.replace('~','~0').replace('/','~1')
                if k not in definition['properties']:unsupported(child)
                else:unknown_fields(v,definition['properties'][k],child)
        elif isinstance(value,list) and 'items' in definition:
            for n,v in enumerate(value):unknown_fields(v,definition['items'],pointer+'/'+str(n))
    issues=[]; coverage=[]; aliases={}; items=[]; selected=[]; unhandled=set()
    if not registry.validate('definitions/fhir-r4-json-schema/fhir.schema.json',incoming):
        issues.append(Issue('FHIR_SOURCE_SCHEMA_INVALID','error','',None,'Incoming export violates pinned R4 schema before local remapping; original bytes retained.'))
        coverage.append({'pointer':'','disposition':'invalid-native-r4'})
    def unsupported(pointer, disposition='unsupported-content'):
        if pointer in unhandled:return
        unhandled.add(pointer)
        coverage.append({'pointer':pointer,'disposition':disposition})
        issues.append(Issue('FHIR_UNHANDLED','error',pointer,None,'Unhandled source content retained; resolve mapping/support before preparation.'))
    # Inventory the complete native tree, even subtrees of unsupported resources
    # or envelope fields. Schema validity does not establish supported semantics.
    unknown_fields(incoming,definitions['Bundle'],'')
    for pointer,node in _walk(incoming):
        if isinstance(node,dict):
            for key in node:
                if key in {'extension','modifierExtension','contained','implicitRules'} or key.startswith('_'):
                    unsupported(pointer+'/'+key.replace('~','~0').replace('/','~1'))
    # Export metadata is retained as source-native evidence, not a second graph.
    for k in incoming:
        coverage.append({'pointer':'/'+k.replace('~','~0').replace('/','~1'),'disposition':'retained-export-envelope'})
        if k not in {'resourceType','type','entry','id','meta','identifier','timestamp','total','link'}:unsupported('/'+k.replace('~','~0').replace('/','~1'))
    if not isinstance(incoming.get('type'),str) or incoming.get('type') not in {'collection','document','searchset','history'}:unsupported('/type')
    for n,entry in enumerate(incoming['entry']):
        ptr=f'/entry/{n}'; r=entry.get('resource') if isinstance(entry,dict) else None
        if not isinstance(r,dict) or not isinstance(r.get('resourceType'),str) or r.get('resourceType') not in _SLUGS:
            unsupported(ptr,'unsupported-resource');continue
        for k in entry:
            if k not in {'fullUrl','resource','search'}:unsupported(ptr+'/'+k.replace('~','~0').replace('/','~1'))
        kind=r['resourceType'];rid=r.get('id')
        if not isinstance(r.get('meta',{}),dict):
            raise ArchiveError('INVALID_INPUT','Expected native resource metadata object.')
        if not isinstance(rid,str) or not rid:
            unsupported(ptr+'/resource/id');continue
        meta=r.get('meta',{})
        if (any(k in meta and not isinstance(meta[k],str) for k in ('versionId','lastUpdated')) or
                'identifier' in r and not isinstance(r['identifier'],list)):
            raise ArchiveError('INVALID_INPUT','Invalid native identity/version shape.')
        keys={kind+'/'+rid}
        if 'fullUrl' in entry:
            if not isinstance(entry['fullUrl'],str):unsupported(ptr+'/fullUrl');continue
            keys.add(entry['fullUrl'])
        if r.get('meta',{}).get('versionId'):
            keys |= {k+'/_history/'+r['meta']['versionId'] for k in tuple(keys)}
        if any(k in aliases for k in keys):
            raise ArchiveError('AMBIGUOUS_REFERENCE','Duplicate native resource identities require separate version/provider mapping.')
        local='Patient/'+person if kind=='Patient' else 'urn:uuid:'+str(uuid4())
        aliases.update({k:local for k in keys})
        if kind=='Patient':
            if mapping.patientReference in keys:selected.append(r)
            else:unsupported(ptr,'unselected-patient')
        items.append((ptr+'/resource',r,local))
    if len(selected)!=1:
        raise ArchiveError('IDENTITY_MAPPING_REQUIRED','Mapping must select exactly one incoming Patient.')
    # All patient aliases refer to the selected patient only after other-patient blocking.
    doc=_source_document(source,person,'application/fhir+json');resources=[doc];evidence=[]
    anchor={'kind':'json-pointer','pointer':'/resourceType'}
    docref='urn:uuid:'+doc['id']
    for pointer,value in _walk(doc):
        if isinstance(value,(dict,list)) or pointer=='/resourceType':continue
        if pointer=='/id' or pointer.startswith('/meta/') or pointer.endswith('/attachment/url'):
            evidence.append({'kind':'generated','target':{'reference':docref,'pointers':[pointer]},'rule':'structured-source-document-1'})
        else:evidence.append(_evidence(source,doc,docref,[pointer],anchor,'Bundle','json-pointer',rule='source-envelope-1'))
    selected_patient_refs={k for k,v in aliases.items() if v=='Patient/'+person}
    for ptr,original,ref in items:
        kind=original['resourceType']
        coverage.append({'pointer':ptr,'disposition':'explicit-local-assignment' if kind=='Patient' else 'mapped',
                         'nativeId':original['id'],'nativeMeta':original.get('meta',{})})
        profiles=original.get('meta',{}).get('profile',[])
        if not isinstance(profiles,list):
            raise ArchiveError('INVALID_INPUT','Expected a list of source profile identifiers.')
        for profile in profiles:
            if not isinstance(profile,str) or profile not in {'http://hl7.org/fhir/StructureDefinition/'+kind,
                    'http://hl7.org/fhir/StructureDefinition/'+kind+'|4.0.1',*_profile(kind)['profile']}:
                unsupported(ptr+'/meta/profile','unhandled-source-profile')
        for k in original.get('meta',{}):
            if k not in {'versionId','lastUpdated','profile'}:unsupported(ptr+'/meta/'+k.replace('~','~0').replace('/','~1'))
        for k in original:
            if k not in set(_FIELDS[kind].split())|{'resourceType','id','meta','language','text'}:
                unsupported(ptr+'/'+k.replace('~','~0').replace('/','~1'))
        if kind=='Patient':continue
        r=deepcopy(original);r['id']=ref.removeprefix('urn:uuid:');r['meta']=_profile(kind)
        # Rewrite only Reference.reference values, never arbitrary equal clinical strings.
        from ..archive import _reference_nodes
        for pointer,node in _reference_nodes(r):
            native=node['reference']
            if not isinstance(native,str):
                raise ArchiveError('INVALID_INPUT','Expected native Reference.reference string.')
            if pointer in ('/subject', '/patient') and native not in selected_patient_refs:
                unsupported(ptr+pointer,'other-person-reference')
            if native not in aliases:unsupported(ptr+pointer,'unresolved-reference')
            else:node['reference']=aliases[native]
        if kind in {'Observation','DiagnosticReport','Specimen','DocumentReference'} and 'subject' not in r:
            unsupported(ptr+'/subject','missing-explicit-subject')
        if kind in {'Observation','DiagnosticReport','Specimen','DocumentReference'}:
            native=[{'system':mapping.provider.rstrip('/')+'/'+kind,'value':original['id']}]
            if original.get('meta',{}).get('versionId'):
                native.append({'system':mapping.provider.rstrip('/')+'/'+kind+'/_history',
                               'value':original['id']+'/_history/'+original['meta']['versionId']})
            r['identifier']=r.get('identifier',[])+native
        resources.append(r)
        generated=[]; mapped=[]
        for pointer,value in _walk(r):
            if isinstance(value,(dict,list)) or pointer=='/resourceType':continue
            if pointer=='/id' or pointer.startswith('/meta/'):generated.append(pointer)
            else:mapped.append(pointer)
        evidence.append({'kind':'generated','target':{'reference':ref,'pointers':generated},'rule':'allocate-local-identity-profile-1'})
        if mapped:
            evidence.append(_evidence(source,doc,ref,mapped,{'kind':'json-pointer','pointer':ptr},
                encode_json(original).decode().strip(),'json-pointer',rule='fhir-r4-local-map-1',
                description='Explicit provider/Patient assignment; native metadata preserved in source. '+mapping.assignmentReason))
    return _structured_candidate(vault,source,'fhir-r4',mapping,resources,evidence,issues,coverage)
