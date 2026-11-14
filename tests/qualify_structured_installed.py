"""Installed-wheel qualification; copy outside checkout. No models or test publishers."""
from pathlib import Path
import os,sys,subprocess,json,shutil,re,hashlib
work,checkout,fixtures=map(lambda x:Path(x).resolve(),sys.argv[1:4]);work.mkdir()
from helseark.serialization import decode_json,encode_json,hash_bytes
import helseark.archive as archive
assert not Path(archive.__file__).resolve().is_relative_to(checkout)
console=Path(sys.executable).parent/'helseark'
vault=work/'vault'
env={**os.environ};env.pop('PYTHONPATH',None)
sandbox=[]
def run(*args,expected=0):
    result=subprocess.run([*sandbox,str(console),*map(str,args),'--json'],cwd=work,env=env,capture_output=True)
    assert result.returncode==expected,(args,result.returncode,result.stderr)
    return decode_json(result.stdout) if result.stdout else None
run('init',vault)
person=run('--vault',vault,'person','add','--name','Synthetic Ada')['personId']
other=run('--vault',vault,'person','add','--name','Synthetic Ada')['personId']
guard=work/'guard';guard.mkdir();events=work/'denials.jsonl'
(guard/'sitecustomize.py').write_text('''import os,sys,json

def audit(event,args):
    reason=None
    if event.startswith(('socket.','urllib.')):reason='network'
    if event in ('open','os.scandir','os.listdir') and isinstance(args[0],(str,bytes,os.PathLike)):
        p=os.path.abspath(os.fsdecode(args[0]))
        for name in ('STRUCTURED_CHECKOUT','STRUCTURED_OTHER'):
            if p==os.environ[name] or p.startswith(os.environ[name]+'/'):reason=name
    if reason:
        with open(os.environ['STRUCTURED_EVENTS'],'a') as f:f.write(json.dumps({'denied':reason})+'\\n')
        raise RuntimeError('qualification denied '+reason)
sys.addaudithook(audit)
''')
env.update(PYTHONPATH=str(guard),STRUCTURED_EVENTS=str(events),STRUCTURED_CHECKOUT=str(checkout),STRUCTURED_OTHER=str(vault/'people'/other))
profile=work/'deny.sb'
profile.write_text('(version 1)(allow default)(deny network*)(deny file-read* (subpath '+json.dumps(str(checkout))+'))(deny file-read* (subpath '+json.dumps(str(vault/'people'/other))+'))')
sandbox=['/usr/bin/sandbox-exec','-f',str(profile)]
for code in ['import socket;socket.socket()', 'import os;open(os.environ["STRUCTURED_CHECKOUT"]+"/pyproject.toml")','import os;os.listdir(os.environ["STRUCTURED_OTHER"])']:
    result=subprocess.run([*sandbox,sys.executable,'-c',code],cwd=work,env=env,capture_output=True);assert result.returncode!=0
assert len(events.read_text().splitlines())==3;events.unlink()
# Kernel guard also covers descriptor-relative reads that audit paths cannot resolve.
for forbidden in (checkout,vault/'people'/other):
    code='import os,sys;fd=os.open("/",os.O_RDONLY);parts=sys.argv[1].strip("/").split("/");[(None) for _ in ()]\nfor part in parts: fd=os.open(part,os.O_RDONLY,dir_fd=fd)'
    witness=subprocess.run([*sandbox,sys.executable,'-c',code,str(forbidden)],cwd=work,env=env,capture_output=True)
    assert witness.returncode!=0
# Descriptor-relative probes use only relative path audit events; OS denial is witnessed.
assert not events.exists()

def publish(family,source,mapping):
    cfg=work/(family+'-mapping.json');cfg.write_bytes(encode_json(mapping))
    candidate=run('--vault',vault,'intake',family,source,'--person',person,'--mapping',cfg)
    proposal=run('--vault',vault,'candidate','prepare',candidate['path'],'--person',person)
    view=run('--vault',vault,'candidate','review',proposal['path'],'--person',person)
    acks={(i['code'],i['resourceRef']):{'code':i['code'],'resourceRef':i['resourceRef'],'reason':'Explicit pre-authored synthetic fixture decision, not clinical approval.'} for i in view['issues'] if i['severity'] in ('review','warning')}
    decision=work/(family+'-decision.json');decision.write_bytes(encode_json({'confirmedPerson':True,'decision':'accept-with-acknowledged-limitations','acknowledgedIssues':list(acks.values()),'reviewerLabel':'synthetic fixture human'}))
    run('--vault',vault,'candidate','review',proposal['path'],'--person',person,'--decision',decision)
    result=run('--vault',vault,'candidate','commit',proposal['path'],'--person',person)
    assert result['disposition']=='committed'
    return candidate,result
assert fixtures.is_relative_to(checkout) is False
fhir,result=publish('fhir-r4',fixtures/'r4.json',{'patientReference':'Patient/p1','localPersonId':person,'assignmentReason':'Synthetic explicit assignment','provider':'https://provider-a.example/fhir'})
old_head=work/'old-head.json';old_head.write_bytes(encode_json(result['head']))
rows=run('--vault',vault,'observations','--person',person)
assert len(rows)==1 and str(rows[0]['value']['value'])=='1.200' and rows[0]['status']=='amended'
csv_candidate,csv_result=publish('metrics-csv',fixtures/'metrics.csv',{'delimiter':';','encoding':'utf-8-sig','dateColumn':'date','valueColumn':'value','unitColumn':'unit','codeColumn':'code','dateFormat':'%d/%m/%Y','decimalSeparator':',','localPersonId':person,'assignmentReason':'Synthetic explicit assignment'})
rows=run('--vault',vault,'observations','--person',person)
assert len(rows)==4 and [str(r['value']['value']) for r in rows].count('0.0500')==2
assert len({r['resourceRef']['id'] for r in rows})==4
assert any(r['code'].get('text')=='=HYPERLINK("https://invalid.example")' for r in rows)
assert len(run('--vault',vault,'observations','--person',person,'--at-head',old_head))==1
for family,candidate in [('fhir-r4',fhir),('metrics-csv',csv_candidate)]:
    coverage=decode_json((Path(candidate['path'])/'coverage.json').read_bytes())
    digest=hash_bytes((Path(candidate['path'])/'coverage.json').read_bytes())
    assert any(digest in i['message'] for i in candidate['unresolved'])
    for source_hash in decode_json((Path(candidate['path'])/'candidate.json').read_bytes())['sourceSha256']:
        assert hash_bytes((vault/'people'/person/'assets/sha256'/source_hash/'blob').read_bytes())==source_hash
# Host-bound adapter output cannot have blocking inventory erased by an agent.
for family in ('fhir-r4','metrics-csv'):
    bad=work/(family+'-unsupported')
    if family=='fhir-r4':
        raw=decode_json((fixtures/'r4.json').read_bytes())
        raw['entry'].append({'resource':{'resourceType':'Medication','id':'m1','status':'active'}})
        bad.write_bytes(encode_json(raw))
    else:
        bad.write_text('date;value;unit;code;unmapped\n01/02/2026;1,200;mg/L;Q;retained\n')
    untrusted=run('--vault',vault,'intake',family,bad,'--person',person,'--mapping',work/(family+'-mapping.json'))
    assert any(i['severity']=='error' for i in untrusted['unresolved'])
    metadata=Path(untrusted['path'])/'candidate.json'
    raw=decode_json(metadata.read_bytes());raw['unresolved']=[]
    for change_id in (False,True):
        if change_id:
            from uuid import uuid4
            raw['candidateId']=str(uuid4())
        metadata.write_bytes(encode_json(raw))
        rejected=subprocess.run([*sandbox,str(console),'--vault',str(vault),'candidate','prepare',untrusted['path'],'--person',person,'--source',raw['sourceSha256'][0],'--json'],cwd=work,env=env,capture_output=True)
        assert rejected.returncode==5 and decode_json(rejected.stderr)['code']=='CANDIDATE_MISMATCH', (rejected.returncode,rejected.stderr)
assert len(run('--vault',vault,'observations','--person',person))==4
# Query is still authoritative after all drafts and runtime host controls are removed.
for path in (vault/'work',vault/'.runtime',vault/'people'/person/'work'):
    if path.exists():shutil.rmtree(path)
assert len(run('--vault',vault,'observations','--person',person))==4
from helseark.validation import _pointer
for row in rows:
    ref=row['resourceRef']; reference=f"{ref['resourceType']}/{ref['id']}/_history/{ref['versionId']}"
    resource=run('--vault',vault,'record','--person',person,'--resource',reference)
    for binding in row['sourceRefs']:
        raw=(vault/binding['evidencePath']).read_bytes();assert hash_bytes(raw)==binding['evidenceSha256']
        e=_pointer(decode_json(raw),binding['entryPointer'])
        assert e['target']['reference']==reference
        for pointer in e['target']['pointers']:_pointer(resource,pointer)
        if e['kind']=='source':
            mapping=decode_json(e['transformation']['description'].split('Trusted local mapping JSON: ',1)[1].encode())
            assert mapping['localPersonId']==person and mapping['assignmentReason']=='Synthetic explicit assignment'
            doc=run('--vault',vault,'record','--person',person,'--resource',e['sourceDocument'])
            assert any(a['attachment']['url']==f"assets/sha256/{e['sourceSha256']}/blob" for a in doc['content'])
kit=vault/'agent-kit'/archive._open_vault_metadata(vault).config.agentKitVersion
for name in ('skills/import-records/SKILL.md','prompts/map-structured-export.md','docs/how-to/import-structured-data.md'):
    path=kit/name;assert path.is_file()
    for link in re.findall(r'\]\(([^)]+)\)',path.read_text()):
        target=link.split('#',1)[0]
        if target and '://' not in target:assert (path.parent/target).resolve().is_file(),(path,target)
manifest=decode_json((kit/'manifest.json').read_bytes())
assert manifest['kitVersion']=='0.1.4'
for item in manifest['files']:
    data=(kit/item['path']).read_bytes();assert hash_bytes(data)==item['sha256'] and len(data)==item['size']
# Check every lock asset and installed runtime module against release bytes.
root=archive._bundled_root();lock=decode_json((root/'definitions/lock.json').read_bytes())
for artifact in lock['artifacts']:
    for item in artifact['files']:
        data=(root/item['path']).read_bytes();assert hash_bytes(data)==item['sha256'] and len(data)==item['size']
import importlib
modules={}
for name in ('archive','contracts','serialization','validation','intake','review','query','cli','agent_context','adapters.fhir_r4','adapters.csv_metrics','adapters.pdf'):
    path=Path(importlib.import_module('helseark.'+name).__file__)
    assert not path.resolve().is_relative_to(checkout);modules[name]=hash_bytes(path.read_bytes())
assert not events.exists()
historical=None
if len(sys.argv)>4:
    old_vault=Path(sys.argv[4]).resolve()
    selected=sys.argv[5]
    before={str(p.relative_to(old_vault)):hash_bytes(p.read_bytes()) for p in old_vault.rglob('*') if p.is_file()}
    prior_config=decode_json((old_vault/'vault.json').read_bytes())
    prior_rows=run('--vault',old_vault,'observations','--person',selected)
    assert len(prior_rows)==1 and str(prior_rows[0]['value']['value'])=='1.200'
    assert prior_config['agentKitVersion']=='0.1.3'
    assert before=={str(p.relative_to(old_vault)):hash_bytes(p.read_bytes()) for p in old_vault.rglob('*') if p.is_file()}
    historical={'kitVersion':prior_config['agentKitVersion'],'rows':len(prior_rows),'unchangedFiles':len(before),'autoRepinned':False}
assert not events.exists()
print(encode_json({'fhirRows':1,'csvRows':3,'acceptedRows':4,'historicalHeadRows':1,'denialWitnesses':5,'networkAttempts':0,'checkoutReads':0,'otherPersonReads':0,'kernelSandbox':True,'errorWaiverAttemptsBlocked':4,'modelRuns':0,'kitVersion':manifest['kitVersion'],'definitionLockSha256':hash_bytes((root/'definitions/lock.json').read_bytes()),'kitSha256':hash_bytes((kit/'manifest.json').read_bytes()),'modules':modules,'assetClosure':True,'historicalPins':historical}).decode())
