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
import sys
import sysconfig
import importlib
import zipfile

from jsonschema import Draft6Validator
from helseark.archive import init_vault, add_person, head, resolve
from helseark.contracts import PersonDraft, ResourceRef, ValidatorConfig, ArchiveError
from helseark.serialization import decode_json, encode_json, hash_bytes
from helseark.fhir_validator import (_lock, _run_bundle, _artifacts,
                                     validate_with_official_tool)
from helseark.portability import fhir_collection


def record_installed_runtime(wheel: Path, output: Path) -> dict:
    """Fail on checkout/shadow imports or installed payloads unlike this wheel.

    Shared by the actual corpus, CLI and authority producers. This verifies
    correspondence, not conformance: only the real executions establish that.
    """
    import helseark
    purelib = Path(sysconfig.get_path('purelib')).resolve()
    package = purelib/'helseark'
    assert Path(helseark.__file__).resolve() == package/'__init__.py', (
        'Qualification requires the installed wheel', helseark.__file__)
    modules, payloads = {}, {}
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.startswith('helseark/') and name.endswith('.py'):
                module_name = name[:-3].replace('/', '.')
                if module_name.endswith('.__init__'):
                    module_name = module_name[:-9]
                module = importlib.import_module(module_name)
                path = purelib/name
                assert Path(module.__file__).resolve() == path, (name, module.__file__)
                assert path.read_bytes() == archive.read(name), name
                modules[name] = {'path':str(path), 'sha256':hash_bytes(path.read_bytes())}
            elif '.data/data/share/helseark/' in name:
                relative = name.split('.data/data/', 1)[1]
                path = Path(sysconfig.get_path('data'))/relative
                assert path.read_bytes() == archive.read(name), relative
                payloads[relative] = hash_bytes(path.read_bytes())
    assert modules and payloads
    value = {'wheel':str(wheel.resolve()), 'wheelSha256':hash_bytes(wheel.read_bytes()),
             'python':sys.executable, 'modules':modules, 'dataPayloads':payloads}
    (output/'installed-runtime.json').write_bytes(encode_json(value))
    return value


def network_denial_witness(output):
    """Reachable host listener first; prove the same confined request is denied."""
    import errno,json,os,socket,subprocess,sys
    from helseark.fhir_validator import _network_command
    listener=socket.socket();listener.settimeout(3)
    try:
        listener.bind(('127.0.0.1',0));listener.listen()
        address=listener.getsockname()
        code="""import json,os,socket,sys
namespace=os.readlink('/proc/self/ns/net') if os.path.exists('/proc/self/ns/net') else None
try:
 c=socket.create_connection(ADDRESS,timeout=2);c.close()
except OSError as error:
 print(json.dumps({'connected':False,'errno':error.errno,'exception':type(error).__name__,'networkNamespace':namespace}));sys.exit(17)
print(json.dumps({'connected':True,'networkNamespace':namespace}))
""".replace('ADDRESS',repr(address))
        command=[sys.executable,'-c',code]
        positive=subprocess.run(command,capture_output=True,timeout=5)
        assert positive.returncode==0,(positive.stdout,positive.stderr)
        control=json.loads(positive.stdout);assert control['connected'] is True
        connection,_=listener.accept();connection.close()
        denied=subprocess.run(_network_command(command),capture_output=True,timeout=5)
        assert denied.returncode==17,(denied.stdout,denied.stderr)
        confined=json.loads(denied.stdout)
        assert confined['connected'] is False
        if sys.platform=='darwin':
            assert confined['exception']=='PermissionError' and confined['errno'] in (errno.EPERM,errno.EACCES)
        else:
            assert control['networkNamespace'] and confined['networkNamespace']!=control['networkNamespace']
            assert confined['errno'] in (errno.ENETUNREACH,errno.EHOSTUNREACH,errno.ECONNREFUSED,errno.EPERM,errno.EACCES)
        value={'positiveControl':control,'identicalConfinedRequest':confined}
        (output/'network-witness.json').write_text(json.dumps(value,indent=2)+'\n')
        return value
    finally:
        listener.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--wheel',type=Path,required=True)
    parser.add_argument('--fixtures',type=Path,required=True,help='Explicit synthetic fixture directory')
    parser.add_argument('--artifacts',type=Path,required=True)
    parser.add_argument('--java',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--timeout-seconds',type=int,default=120)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    record_installed_runtime(args.wheel,args.output)
    pins=_lock()
    vault=init_vault(args.output/'vault')
    config=ValidatorConfig(args.artifacts/'validator_cli.jar',pins['executableSha256'],pins['version'],
                           args.artifacts/'packages',vault.root/'definitions/profiles/r4',args.timeout_seconds,False,args.java)
    network_denial_witness(args.output)
    person=add_person(vault,PersonDraft('Synthetic official corpus'))
    initial_head=head(vault,person)
    corpus=decode_json((args.fixtures/'profiles/collection.json').read_bytes())
    (args.output/'qualification-inputs.json').write_bytes(encode_json({
        'fixturePath':str((args.fixtures/'profiles/collection.json').resolve()),
        'fixtureSha256':hash_bytes((args.fixtures/'profiles/collection.json').read_bytes()),
        'definitionLockSha256':vault.config.definitionLockSha256,
        'schemaSha256':hash_bytes((vault.root/'definitions/definitions/fhir-r4-json-schema/fhir.schema.json').read_bytes()),
        'profileDirectory':str(config.profileDirectory), 'profileVersion':vault.config.profileVersion}))
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
    schema=decode_json((vault.root/'definitions/definitions/fhir-r4-json-schema/fhir.schema.json').read_bytes())
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
    config=replace(config,profileDirectory=v.root/'definitions/profiles/r4')
    proposal=prepare(v,candidate)
    source_bytes=source.assetPath.read_bytes()
    required=validate_with_official_tool(proposal,replace(config,requireTerminology=True),vault=v)
    assert next(c.result for c in required.coverage if c.family=='terminology')=='failed'
    from helseark.review import _blocked
    try: _blocked(required)
    except ArchiveError as error: assert error.code=='VALIDATION_BLOCKED'
    else: raise AssertionError('Required terminology absence did not block')
    report=validate_with_official_tool(proposal,config,vault=v)
    assert b'UNSELECTED SECRET' not in encode_json(report.officialRun)
    (args.output/'prepared-report.json').write_bytes(encode_json(document(report)))
    assert next(c.result for c in report.coverage if c.family=='full-fhir')=='passed'
    assert next(c.result for c in report.coverage if c.family=='terminology')=='not-checked'
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
