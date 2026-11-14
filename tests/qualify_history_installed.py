"""Run a copy outside checkout with installed Python; synthetic inputs only.

Args: absent work directory, copied fixture directory, checkout root to deny.
Exercises actual console commands and installed-library candidate construction.
"""
from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import sys
from uuid import uuid4

from helseark.serialization import encode_json,decode_json,hash_bytes
from helseark.archive import open_vault
from helseark.intake import add_source

work,fixtures,checkout=map(lambda p:Path(p).resolve(),sys.argv[1:4])
work.mkdir()
guard=work/'guard';guard.mkdir()
(guard/'sitecustomize.py').write_text('''import os,sys
from pathlib import Path
def audit(event,args):
    if event.startswith(('socket.','urllib.')):
        raise RuntimeError('network forbidden')
    if event in ('open','os.scandir','os.listdir') and args and isinstance(args[0],(str,bytes)):
        p=Path(os.fsdecode(args[0])).absolute()
        if p.is_relative_to(os.environ['HISTORY_DENY']):
            raise RuntimeError('checkout forbidden')
sys.addaudithook(audit)
''')
env={**os.environ,'PYTHONPATH':str(guard),'HISTORY_DENY':str(checkout)}
console=Path(sys.executable).parent/'helseark'
def run(*args,expected=0):
    child=subprocess.run([str(console),*map(str,args),'--json'],capture_output=True,cwd=work,env=env)
    assert child.returncode==expected,(args,child.returncode,child.stderr)
    return decode_json(child.stdout) if child.stdout else None
for probe in ['import socket;socket.socket()',f'open({str(checkout/"pyproject.toml")!r}).read()']:
    child=subprocess.run([sys.executable,'-c',probe],env=env,capture_output=True,cwd=work)
    assert child.returncode!=0 and b'forbidden' in child.stderr
print('Network/checkout guard witnesses rejected',flush=True)
vault_path=work/'vault';run('init',vault_path)
person=run('--vault',vault_path,'person','add','--name','Synthetic history patient')['personId']
other=run('--vault',vault_path,'person','add','--name','Synthetic history patient','--note','OTHER_SYNTHETIC_PERSON_ONLY')['personId']
# Build an explicitly pre-authored external candidate from local synthetic JSON.
vault=open_vault(vault_path)
records=[]
for p in sorted(fixtures.glob('*.json')):
    for r in decode_json(p.read_bytes().replace(b'PERSON',person.encode())):
        r['id']=str(uuid4());records.append(r)
kinds=sorted({r['resourceType'] for r in records})
assert len(kinds)==8 and len(records)==17
use=next(r for r in records if r['resourceType']=='MedicationStatement' and r['status']=='active')
order=next(r for r in records if r['resourceType']=='MedicationRequest' and r['status']=='active')
use['derivedFrom']=[{'reference':'urn:uuid:'+order['id']}]
vaccine=next(r for r in records if r['resourceType']=='Immunization' and r['status']=='completed')
vaccine['education'][0]['reference']='urn:uuid:'+vaccine['id']
vaccine['note']=[{'text':'urn:uuid:'+vaccine['id']}]
source={'assertions':records,'document':{'status':'current','mediaType':'application/json','subject':'Patient/'+person,'title':'Synthetic clinical source assertions'}}
source_path=work/'source.json';source_path.write_bytes(encode_json(source))
receipt=add_source(vault,person,source_path)
did=str(uuid4());doc={'resourceType':'DocumentReference','id':did,'meta':{'profile':['https://github.com/ricardocabral/helseark/fhir/StructureDefinition/helseark-document-reference|0.1.0']},'status':'current','subject':{'reference':'Patient/'+person},'content':[{'attachment':{'url':f'assets/sha256/{receipt.sourceSha256}/blob','contentType':'application/json','title':'Synthetic clinical source assertions'}}]}
entries=[{'fullUrl':'urn:uuid:'+r['id'],'resource':r} for r in [*records,doc]]
def leaves(value,pointer=''):
    if isinstance(value,dict):
        for k,v in value.items():yield from leaves(v,pointer+'/'+k)
    elif isinstance(value,list):
        for i,v in enumerate(value):yield from leaves(v,pointer+'/'+str(i))
    else:yield pointer,value

evidence=[]
for index,entry in enumerate(entries):
    for pointer,value in leaves(entry['resource']):
        if pointer=='/resourceType':continue
        item={'target':{'reference':entry['fullUrl'],'pointers':[pointer]}}
        if pointer=='/id' or pointer.startswith('/meta/') or pointer=='/content/0/attachment/url':
            item.update(kind='generated',rule='synthetic-history-fixture-1')
        else:
            if index<len(records):located='/assertions/'+str(index)+pointer
            else:located={'/status':'/document/status','/subject/reference':'/document/subject','/content/0/attachment/contentType':'/document/mediaType','/content/0/attachment/title':'/document/title'}[pointer]
            item.update(kind='source',sourceSha256=receipt.sourceSha256,sourceDocument='urn:uuid:'+did,quote=value if isinstance(value,str) else encode_json(value).decode().strip(),locator={'kind':'json-pointer','pointer':located})
        evidence.append(item)
candidate=work/'candidate';candidate.mkdir()
producer={'provenanceVersion':1,'status':'external-unknown','reason':'Pre-authored synthetic installed qualification, no model run.'}
from helseark.archive import head
base=head(vault,person)
metadata={'contractVersion':'0.1.0','profileVersion':vault.config.profileVersion,'fhirVersion':'4.0.1','candidateId':str(uuid4()),'personId':person,'baseChangeSha256':base.changeSha256,'sourceSha256':[receipt.sourceSha256],'bundlePath':'bundle.json','evidencePath':'evidence.json','unresolved':[],'producer':{'kind':'external-agent','name':'synthetic installed qualification'},'producerProvenance':producer}
for name,value in [('candidate',metadata),('bundle',{'resourceType':'Bundle','type':'collection','entry':entries}),('evidence',{'contractVersion':'0.1.0','personId':person,'producerProvenance':producer,'entries':evidence})]:
    (candidate/(name+'.json')).write_bytes(encode_json(value))
proposal=run('--vault',vault_path,'candidate','prepare',candidate,'--person',person,'--source',receipt.sourceSha256)
proposal_path=Path(proposal['path'])
run('--vault',vault_path,'candidate','commit',proposal_path,'--person',person,expected=5)
view=run('--vault',vault_path,'candidate','review',proposal_path,'--person',person)
acks={}
for issue in view['issues']:
    if issue['severity'] in ('review','warning'):
        acks[(issue['code'],issue['resourceRef'])]={'code':issue['code'],'resourceRef':issue['resourceRef'],'reason':'Synthetic human compared original source and retained qualifier.'}
decision=work/'decision.json';decision.write_bytes(encode_json({'confirmedPerson':True,'decision':'accept-with-acknowledged-limitations','reviewerLabel':'synthetic human','acknowledgedIssues':list(acks.values())}))
run('--vault',vault_path,'candidate','review',proposal_path,'--person',person,'--decision',decision)
run('--vault',vault_path,'candidate','commit',proposal_path,'--person',person)
print('Reviewed 17 assertions across 8 families',flush=True)
args=[x for k in kinds for x in ('--kind',k)]
before=run('--vault',vault_path,'history','--person',person,*args)
assert len([r for r in before if r['resourceType'] in kinds])==17
accepted_vaccine=next(r for r in before if r['resourceType']=='Immunization' and r['status']=='completed')
assert accepted_vaccine['education'][0]['reference']==vaccine['education'][0]['reference']
assert accepted_vaccine['note']==vaccine['note']
accepted_use=next(r for r in before if r['resourceType']=='MedicationStatement' and r['status']=='active')
accepted_order=next(r for r in before if r['resourceType']=='MedicationRequest' and r['status']=='active')
assert accepted_use['derivedFrom'][0]['reference']==f"MedicationRequest/{accepted_order['id']}/_history/{accepted_order['meta']['versionId']}"
assert any(r['resourceType']=='Provenance' for r in before)
initial_head=work/'initial-head.json'
initial_head.write_bytes(encode_json({'sequence':base.sequence,'transactionId':base.transactionId,'changeSha256':base.changeSha256}))
assert not run('--vault',vault_path,'history','--person',person,*args,'--at-head',initial_head)
assert encode_json(accepted_vaccine)==encode_json(run('--vault',vault_path,'record','--person',person,'--resource','Immunization/'+accepted_vaccine['id']))
assert not run('--vault',vault_path,'history','--person',other,*args)
rows=run('--vault',vault_path,'timeline','--person',person)
assert len([r for r in rows if r['resourceRef']['resourceType'] in kinds])==17
assert all(r['sourceRefs'] for r in rows if r['resourceRef']['resourceType'] in kinds)
run('--vault',vault_path,'schema','export',*[x for k in kinds for x in ('--resource',k)],'--out',work/'schemas')
raw_before={p.relative_to(vault_path).as_posix():p.read_bytes() for p in (vault_path/'people').rglob('*') if p.is_file()}
run('--vault',vault_path,'backup','create','--out',work/'backup')
run('backup','verify',work/'backup')
restored=work/'restored';run('backup','restore',work/'backup','--into',restored)
for disposable in ('.runtime','work','derived'):shutil.rmtree(restored/disposable,ignore_errors=True)
assert raw_before=={p.relative_to(restored).as_posix():p.read_bytes() for p in (restored/'people').rglob('*') if p.is_file()}
assert encode_json(before)==encode_json(run('--vault',restored,'history','--person',person,*args))
assert encode_json(rows)==encode_json(run('--vault',restored,'timeline','--person',person))
report=run('--vault',restored,'doctor');assert not report['issues']
run('--vault',restored,'export','--person',person,'--out',work/'selected','--mode','selected-current','--no-sources')
run('backup','verify',work/'selected')
run('--vault',restored,'export','--person',person,'--out',work/'full-person')
run('backup','verify',work/'full-person')
assert all(b'OTHER_SYNTHETIC_PERSON_ONLY' not in p.read_bytes() for p in (work/'full-person').rglob('*') if p.is_file())
assert (work/'full-person/vault/people'/person/'assets/sha256'/receipt.sourceSha256/'blob').read_bytes()==source_path.read_bytes()
print(encode_json({'families':len(kinds),'assertions':17,'people':2,'peopleTreeFiles':len(raw_before),'exactBytes':True,'doctor':report}).decode(),flush=True)
