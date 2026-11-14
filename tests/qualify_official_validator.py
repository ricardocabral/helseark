"""Real pinned binary qualification; all inputs synthetic, no subprocess fakes.

Run explicitly (not ordinary pytest) with acquired artifacts and Java. Each run
has the adapter's OS deny-network policy; the whole script can also be confined.
"""
import argparse
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import shutil
import socket

from jsonschema import Draft6Validator
from helseark.archive import init_vault, add_person, head, resolve
from helseark.contracts import PersonDraft, ResourceRef, ValidatorConfig, ArchiveError
from helseark.serialization import decode_json, encode_json, hash_bytes
from helseark.fhir_validator import (_lock, _run_bundle, _artifacts,
                                     validate_with_official_tool)
from helseark.portability import fhir_collection


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--artifacts',type=Path,required=True)
    parser.add_argument('--java',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--timeout-seconds',type=int,default=120)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parents[1]
    pins=_lock()
    config=ValidatorConfig(args.artifacts/'validator_cli.jar',pins['executableSha256'],pins['version'],
                           args.artifacts/'packages',root/'profiles/r4/0.1.0',args.timeout_seconds,False,args.java)
    # Witness the enclosing OS confinement, not just Python socket monkeypatches.
    from helseark.fhir_validator import _network_command
    import subprocess,sys
    witness=subprocess.run(_network_command([sys.executable,'-c',
        "import socket; socket.create_connection(('1.1.1.1',443),timeout=2)"]),capture_output=True)
    assert witness.returncode != 0, 'OS network denial witness unexpectedly connected'
    (args.output/'network-witness.txt').write_bytes(witness.stderr)
    vault=init_vault(args.output/'vault')
    person=add_person(vault,PersonDraft('Synthetic official corpus'))
    initial_head=head(vault,person)
    corpus=decode_json((root/'tests/fixtures/synthetic/profiles/collection.json').read_bytes())
    original_person=next(e['resource']['id'] for e in corpus['entry'] if e['resource']['resourceType']=='Patient')
    # Fixture parameterization of identity precedes the public mapper; no Bundle converter here.
    raw=encode_json(corpus).replace(original_person.encode(),person.encode())
    corpus=decode_json(raw)
    from decimal import Decimal
    amendment=deepcopy(next(e['resource'] for e in corpus['entry'] if 'valueQuantity' in e['resource']))
    old_version=amendment['meta']['versionId']
    amendment['meta']['versionId']='00000010-8888-4888-8888-888888888888'
    amendment['status']='amended'; amendment['valueQuantity']['value']=Decimal('0.0600')
    resources=tuple(e['resource'] for e in corpus['entry'])+(amendment,)
    original_bytes=encode_json(resources_as_list:=list(resources))
    bundle,mapping=fhir_collection(vault,person,at=initial_head,proposedResources=resources)
    assert len(mapping)==len(resources) and len(mapping)>6
    assert {m['versionId'] for m in mapping if m['id']==amendment['id']}=={old_version,amendment['meta']['versionId']}
    report_resource=next(e['resource'] for e in bundle['entry'] if e['resource']['resourceType']=='DiagnosticReport')
    assert report_resource['result'][0]['reference']=='urn:uuid:'+old_version
    # Reverse only documented Reference rewrites and compare every clinical byte,
    # including exact Decimal scale and array ordering.
    from helseark.validation import _walk
    for entry,item in zip(bundle['entry'],mapping):
        resource=deepcopy(entry['resource'])
        reverse={v:k for k,v in item['references'].items()}
        for _,node in _walk(resource):
            if isinstance(node,dict) and 'reference' in node:
                node['reference']=reverse[node['reference']]
        before=next(r for r in resources if r['resourceType']==item['resourceType'] and r['id']==item['id'] and r['meta']['versionId']==item['versionId'])
        assert encode_json(resource)==encode_json(before)
    issues,counts,run=_run_bundle(vault,bundle,mapping,config)
    (args.output/'supported-corpus.json').write_bytes(encode_json(run))
    print('supported corpus:',len(bundle['entry']),'resources;',counts,flush=True)
    assert counts['errors']==0, 'See supported-corpus.json actual OperationOutcome'
    assert {e['resource']['resourceType'] for e in bundle['entry']}=={'Patient','Observation','DiagnosticReport','Specimen','DocumentReference','Provenance'}
    # Genuine deeper invariant counterexample. Same R4-schema-valid resource,
    # with declared supported Observation profile, both value + dataAbsentReason.
    invalid=deepcopy(bundle)
    obs=next(e['resource'] for e in invalid['entry'] if 'valueQuantity' in e['resource'])
    obs['dataAbsentReason']={'text':'Synthetic conflicting absence'}
    schema=decode_json((root/'definitions/fhir-r4-json-schema/fhir.schema.json').read_bytes())
    assert Draft6Validator(schema).is_valid(invalid)
    _,bad_counts,bad_run=_run_bundle(vault,invalid,mapping,config)
    (args.output/'invariant-negative.json').write_bytes(encode_json(bad_run))
    assert bad_counts['errors']>=1
    assert any('obs-6' in str(i) for i in bad_run['operationOutcome']['issue'] if i['severity'] in ('error','fatal'))
    print('schema-valid invariant negative:',len(invalid['entry']),'resources;',bad_counts,flush=True)
    assert encode_json(resources_as_list)==original_bytes
    # Real full API source/person checks and retained report/review publication.
    from test_intake import supplied_candidate
    from test_review import prepare,approve
    from helseark.agent_context import document
    from helseark.review import read_prepared
    from helseark.archive import commit_candidate,open_vault
    v,p,source,packet,candidate=supplied_candidate(args.output/'workflow')
    proposal=prepare(v,candidate)
    source_bytes=source.assetPath.read_bytes()
    report=validate_with_official_tool(proposal,config,vault=v)
    assert b'UNSELECTED SECRET' not in encode_json(report.officialRun)
    (args.output/'prepared-report.json').write_bytes(encode_json(document(report)))
    assert next(c.result for c in report.coverage if c.family=='full-fhir')=='passed'
    assert next(c.result for c in report.coverage if c.family=='terminology')=='not-checked'
    required=validate_with_official_tool(proposal,replace(config,requireTerminology=True),vault=v)
    assert next(c.result for c in required.coverage if c.family=='terminology')=='failed'
    from helseark.review import _blocked
    try: _blocked(required)
    except ArchiveError as error: assert error.code=='VALIDATION_BLOCKED'
    else: raise AssertionError('Required terminology absence did not block')
    (proposal.path/'validation.json').write_bytes(encode_json(document(report)))
    prepared=read_prepared(v,proposal.path)
    receipt=approve(v,prepared)
    result=commit_candidate(v,prepared,receipt)
    assert result.disposition=='committed'
    assert source.assetPath.read_bytes()==source_bytes
    open_vault(v.root)
    assert report.officialRun['counts']['errors']==0
    # Complete package closure vs isolated unrelated empty cache (actual adapter).
    empty=args.output/'empty-packages';empty.mkdir()
    try: _artifacts(replace(config,packageDirectory=empty),args.output/'empty-home')
    except ArchiveError as error: assert error.code=='VALIDATOR_MISSING_ARTIFACT'
    else: raise AssertionError('Unrelated empty cache passed')
    print('full API:',report.officialRun['resourceCount'],'resources;',report.officialRun['counts'],
          '; 1 source unchanged; review/commit/reopen passed; empty cache blocked',flush=True)


if __name__=='__main__': main()
