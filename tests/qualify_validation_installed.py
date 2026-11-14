"""Installed Task 2 proof, synthetic only; no pytest or source-package import.

Copy outside checkout, run using the wheel environment's Python from /private/tmp:
    python qualify_validation_installed.py ABSENT_WORK_DIRECTORY CHECKOUT
The checkout supplies only fixture bytes and uv.lock. Runtime networking denied.
"""
import importlib.metadata
from decimal import Decimal
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tomllib
from uuid import uuid4

work, checkout = (Path(x).resolve() for x in sys.argv[1:])
work.mkdir()
os.chdir(work)
import helseark.archive as archive
from helseark.contracts import ArchiveError
from helseark.serialization import decode_json, hash_bytes, encode_json
from helseark.validation import DefinitionRegistry, load_definition_registry
assert '/site-packages/' in archive.__file__
assert not Path(archive.__file__).resolve().is_relative_to(checkout)
bundled = archive._bundled_root()
assert bundled == Path(sys.prefix) / 'share/helseark'
lock_versions = {p['name']:p['version'] for p in tomllib.loads((checkout/'uv.lock').read_text())['package']}
installed = {d.metadata['Name'].lower().replace('_','-'):d.version for d in importlib.metadata.distributions()}
assert all(lock_versions[name] == version for name,version in installed.items()), installed
network = []
def offline(event, args):
    if event.startswith('socket.'):
        network.append(event)
        raise RuntimeError('Runtime network forbidden')
sys.addaudithook(offline)
import socket
try:
    socket.socket()
    raise AssertionError('Network guard did not activate')
except RuntimeError:
    pass
assert network
network.clear()
guard = work/'guard';guard.mkdir()
(guard/'sitecustomize.py').write_text('''import os,sys
def guard(event,args):
 if event.startswith('socket.'):
  with open(os.environ['NETWORK_LOG'],'a') as f:f.write(event+'\\n')
  raise RuntimeError('Runtime network forbidden')
 if event=='open' and '/people/' in str(args[0]) and os.environ.get('DENY_PATIENT'):
  with open(os.environ['PATIENT_LOG'],'a') as f:f.write('patient open\\n')
  raise RuntimeError('Patient read forbidden')
sys.addaudithook(guard)
''')
netlog, patientlog = work/'network-events', work/'patient-events'
env = {k:v for k,v in os.environ.items() if k not in {'HELSEARK_VAULT','PYTHONPATH'}}
env.update(PYTHONPATH=str(guard),NETWORK_LOG=str(netlog),PATIENT_LOG=str(patientlog))
console = Path(sys.executable).parent/'helseark'
def run(args, code=0, extra_env=None):
    result = subprocess.run([str(console),*map(str,args)],env={**env,**(extra_env or {})},capture_output=True)
    assert result.returncode == code, (result.returncode,result.stderr,result.stdout)
    assert b'Traceback' not in result.stderr
    return json.loads(result.stdout or result.stderr)
# Prove the subprocess guard separately, then clear its deliberate event.
probe=subprocess.run([sys.executable,'-c','import socket; socket.socket()'],env=env,capture_output=True)
assert probe.returncode!=0 and netlog.exists()
netlog.unlink()
vault=work/'vault'
run(['init',vault,'--json'])
person=run(['--vault',vault,'person','add','--name','Synthetic Person A','--json'])['personId']
v=archive.open_vault(vault)
registry=load_definition_registry(v)
lock=decode_json((bundled/'definitions/lock.json').read_bytes())
files={entry['path']:(bundled/entry['path']).read_bytes() for a in lock['artifacts'] for entry in a['files']}
for a in lock['artifacts']:
    for entry in a['files']:
        assert hash_bytes(files[entry['path']])==entry['sha256']
        assert len(files[entry['path']])==entry['size']
        assert registry.files[entry['path']]==files[entry['path']]
installed_registry=DefinitionRegistry(files)
core=files['definitions/runtime-core/4.0.1/hl7.fhir.r4.core.tgz']
resolved={'installed':0,'initialized':0}
with tarfile.open(fileobj=io.BytesIO(core),mode='r:gz') as tgz:
    for member in tgz:
        if member.isfile() and member.name.startswith('package/StructureDefinition-') and member.name.endswith('.json'):
            expected=json.loads(tgz.extractfile(member).read(),parse_float=Decimal)
            for name,r in [('installed',installed_registry),('initialized',registry)]:
                assert r.resolve(expected['url'])==expected
                if expected.get('version'):
                    assert r.resolve(expected['url']+'|'+expected['version'])==expected
                else:
                    try:r.resolve(expected['url']+'|4.0.1')
                    except ArchiveError as error:assert error.code=='MISSING_DEFINITION'
                    else:raise AssertionError('Invented resource version')
                resolved[name]+=1
assert resolved=={'installed':655,'initialized':655}
for r in (registry,installed_registry):
    for identifier in ('https://unknown.invalid/definition','http://hl7.org/fhir/StructureDefinition/SimpleQuantity|5.0.0'):
        try:r.resolve(identifier)
        except ArchiveError as error:assert error.code=='MISSING_DEFINITION'
        else:raise AssertionError('Unknown definition resolved')
fixtures=checkout/'tests/fixtures/synthetic/validation'
source=(fixtures/'source.json').read_bytes();source_value=decode_json(source);digest=hash_bytes(source)
asset=vault/'people'/person/'assets/sha256'/digest/'blob';asset.parent.mkdir(parents=True);asset.write_bytes(source)
bundle=decode_json((fixtures/'candidate-bundle.json').read_bytes().replace(
    b'11111111-1111-4111-8111-111111111111',person.encode()))
document=bundle['entry'][1]
document['resource']['content'][0]['attachment']['url']=f'assets/sha256/{digest}/blob'
entries=[]
def leaves(value,pointer=''):
    if isinstance(value,dict):
        for key,item in value.items():yield from leaves(item,pointer+'/'+key)
    elif isinstance(value,list):
        for i,item in enumerate(value):yield from leaves(item,pointer+'/'+str(i))
    else:yield pointer,value
for e in bundle['entry']:
    resource=e['resource']
    for pointer,value in leaves(resource):
        if pointer=='/resourceType':continue
        item={'target':{'reference':e['fullUrl'],'pointers':[pointer]}}
        if pointer=='/id' or pointer.startswith('/meta/') or pointer.endswith('/attachment/url'):
            item.update(kind='generated',rule='synthetic-installed-proof-v1')
        else:
            mapping={'/status':'/docStatus' if resource['resourceType']=='DocumentReference' else '/status',
                '/code/text':'/reportLabel' if resource['resourceType']=='DiagnosticReport' else '/label',
                '/subject/reference':'/person','/effectiveDateTime':'/date',
                '/valueQuantity/value':'/result','/valueQuantity/comparator':'/result','/valueQuantity/unit':'/result',
                '/content/0/attachment/contentType':'/mediaType','/content/0/attachment/title':'/title',
                '/result/0/reference':'/label'}
            field=mapping[pointer]
            item.update(kind='source',sourceSha256=digest,sourceDocument=document['fullUrl'],
                quote=source_value[field[1:]],locator={'kind':'json-pointer','pointer':field})
        entries.append(item)
evidence={'contractVersion':'0.1.0','personId':person,'entries':entries}
candidate=work/'candidate';candidate.mkdir()
metadata={'contractVersion':'0.1.0','candidateId':str(uuid4()),'personId':person,
    'baseChangeSha256':archive.head(v,person).changeSha256,'fhirVersion':'4.0.1','profileVersion':'0.1.0',
    'sourceSha256':[digest],'bundlePath':'bundle.json','evidencePath':'evidence.json',
    'producer':{'kind':'external-agent','name':'synthetic-installed-proof'},'unresolved':[]}
for name,value in [('candidate',metadata),('bundle',bundle),('evidence',evidence)]:
    (candidate/(name+'.json')).write_bytes(encode_json(value))
args=['--vault',vault,'validate','candidate',candidate,'--person',person,'--json']
good=run(args)
assert not [i for i in good['issues'] if i['severity']=='error']
o=bundle['entry'][0]['resource']
assert str(o['valueQuantity']['value'])=='0.050'
assert o['valueQuantity']['comparator']=='<' and o['valueQuantity']['unit']=='mg/L'
assert o['effectiveDateTime']=='2026-11'
o['subject']['reference']='Patient/'+str(uuid4());(candidate/'bundle.json').write_bytes(encode_json(bundle))
bad=run(args,2)
assert 'PERSON_MISMATCH' in {i['code'] for i in bad['issues']}
# Corrupt an unrelated second person. Definition export must not access either.
other=run(['--vault',vault,'person','add','--name','Unrelated synthetic person','--json'])['personId']
patient=next((vault/'people'/other/'accepted').glob('*/resources/Patient-*.json'))
blocked=subprocess.run([sys.executable,'-c','import sys;open(sys.argv[1])',str(patient)],
    env={**env,'DENY_PATIENT':'1'},capture_output=True)
assert blocked.returncode!=0 and patientlog.exists()
patientlog.unlink()
patient.write_bytes(b'{corrupt synthetic patient')
exports={}
for mode in ['explicit','env','standalone']:
    packet=work/('packet-'+mode)
    prefix=['--vault',vault] if mode=='explicit' else []
    extra={'DENY_PATIENT':'1',**({'HELSEARK_VAULT':str(vault)} if mode=='env' else {})}
    run([*prefix,'schema','export','--resource','Observation','--out',packet,'--json'],extra_env=extra)
    for a in lock['artifacts']:
        for entry in a['files']:assert hash_bytes((packet/entry['path']).read_bytes())==entry['sha256']
    exports[mode]={'exit':0,'patientOpens':0,'verifiedFiles':len(files)}
assert not patientlog.exists()
assert run(args,5)['code']=='INTEGRITY'
assert not network and not netlog.exists()
result={'installedModule':archive.__file__,'python':sys.version,'dependencies':installed,
    'definitionLockSha256':hash_bytes((bundled/'definitions/lock.json').read_bytes()),
    'coreSha256':hash_bytes(core),'inventoryFiles':len(files),'registryResolved':resolved,
    'goodCandidateExit':0,'wrongPersonExit':2,'unrelatedPatientIntegrityExit':5,
    'exports':exports,'runtimeNetworkAttempts':0,'goodCoverage':good['coverage']}
(work/'result.json').write_bytes(encode_json(result))
print(encode_json(result).decode())
