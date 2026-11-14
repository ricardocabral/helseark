"""Offline installed public CLI qualification using explicitly SYNTHETIC decisions.

Run a copy outside checkout: python qualify.py WORK EXISTING_TWO_PERSON_BACKUP CHECKOUT.
No real-user approval, model run or clinical/redaction quality claim is produced.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
from helseark.serialization import decode_json, encode_json

work,source,checkout=map(lambda p:Path(p).resolve(),sys.argv[1:4])
work.mkdir()
bundle=work/'backup'; shutil.copytree(source,bundle)
original=json.loads((bundle/'export.json').read_bytes())
assert len(original['people'])==2 and original['counts']['changes']==4 and original['counts']['resources']==10
assert original['counts']['assets']==2
sha=lambda b:hashlib.sha256(b).hexdigest()
guard=work/'guard';guard.mkdir()
(guard/'sitecustomize.py').write_text('''
import os,sys
denied=[os.path.abspath(p) for p in os.environ['DISCLOSURE_DENY'].split(os.pathsep)]
def audit(event,args):
    if event.startswith(('socket.','urllib.')):raise RuntimeError('network forbidden')
    if event in ('open','os.scandir','os.listdir') and args and isinstance(args[0],(str,bytes)):
        p=os.path.abspath(os.fsdecode(args[0]))
        for root in denied:
            if p==root or p.startswith(root+os.sep):raise RuntimeError('original checkout/vault/cache forbidden')
sys.addaudithook(audit)
''')
cache=Path.home()/'.cache/uv'
env={**os.environ,'PYTHONPATH':str(guard),'DISCLOSURE_DENY':os.pathsep.join(map(str,[checkout,source,source.parent/'vault',cache]))}
console=Path(sys.executable).parent/'helseark'
commands=[]
def command(*args,expect=0):
    child=subprocess.run([str(console),*map(str,args),'--json'],cwd=work,env=env,capture_output=True)
    result=decode_json(child.stdout if child.returncode==0 else child.stderr)
    commands.append(dict(args=list(map(str,args)),exit=child.returncode,result=result))
    (work/'commands.json').write_bytes(encode_json(commands))
    print('CLI',len(commands),args[:3],'exit',child.returncode,flush=True)
    assert child.returncode==expect,(args,child.returncode,child.stderr)
    return result
for code in ['import socket;socket.socket()',f'open({str(checkout/"pyproject.toml")!r})',f'open({str(source/"export.json")!r})',f'list(__import__("pathlib").Path({str(cache)!r}).iterdir())']:
    child=subprocess.run([sys.executable,'-c',code],cwd=work,env=env,capture_output=True)
    assert child.returncode!=0 and b'forbidden' in child.stderr
print('4 active denial witnesses: network, checkout, original backup/vault, uv cache',flush=True)
command('backup','verify',bundle)
vault=work/'restored';command('backup','restore',bundle,'--into',vault)
for name in ['.runtime','derived','work']:shutil.rmtree(vault/name,ignore_errors=True)
report=command('--vault',vault,'doctor');assert not report['issues']
assert (report['checkedChanges'],report['checkedResources'],report['checkedAssets'])==(4,10,2)
facts={p:command('--vault',vault,'observations','--person',p) for p in original['people']}
person=next(p for p in facts if facts[p]);other=next(p for p in facts if p!=person)
assert len(facts[person])==2 and not facts[other]
before={p.relative_to(vault).as_posix():p.read_bytes() for p in (vault/'people'/person).rglob('*') if p.is_file()}
denied=work/'default-denied'
assert command('--vault',vault,'export','--person',person,'--out',denied,expect=3)['code']=='SOURCE_SCOPE_REVIEW_REQUIRED'
assert not denied.exists()

def plan(name,mode='full-person',derivatives=None):
    folder=work/name
    args=['--vault',vault,'export-plan','--person',person,'--mode',mode,'--out',folder]
    if derivatives:args+=['--derivatives',derivatives]
    value=command(*args)
    assert value['planSha256']==sha((folder/'plan.json').read_bytes())
    return folder,value

def review(folder,value):
    decision=dict(format='helseark-source-decision-1',planSha256=value['planSha256'],humanReviewed=True,
                  confirmedPerson=True,acknowledgedDisclosure=True,
                  reviewer={'kind':'synthetic-test','label':'SYNTHETIC installed qualification; not a real-user approval'},
                  reason='SYNTHETIC exercise of explicit disclosure and remaining copies; no clinical approval')
    path=work/(folder.name+'-decision.json');path.write_bytes(encode_json(decision))
    command('--vault',vault,'export-review','--plan',folder,'--decision',path)

folder,value=plan('exact-plan');review(folder,value)
full=work/'full-person'
command('--vault',vault,'export','--person',person,'--review',folder,'--out',full)
verified=command('backup','verify',full);assert not verified['issues'] and verified['checkedChanges']==3
manifest=decode_json((full/'export.json').read_bytes());scope=manifest['sourceDisclosure']['plan']
assert scope['originalDisposition']=='included-exact' and manifest['format']=='helseark-export-2'
for item in scope['sourceFiles']:
    data=(full/'vault'/item['path']).read_bytes()
    assert sha(data)==item['sha256'] and len(data)==item['size']
assert b'ORIGINAL SHARED SOURCES' in (full/'README.md').read_bytes()
recovered=work/'recovered-person';command('backup','restore',full,'--into',recovered)
for name in ['.runtime','derived','work']:shutil.rmtree(recovered/name,ignore_errors=True)
assert all((recovered/path).read_bytes()==data for path,data in before.items())
assert not (recovered/'people'/other).exists()
assert command('--vault',recovered,'observations','--person',person)==facts[person]
assert not command('--vault',recovered,'doctor')['issues']
# Same captured receipt never grants a changed selection or unrelated person.
for name,p,mode in [('selection',person,'selected-current'),('person',other,'full-person')]:
    target=work/('denied-'+name)
    assert command('--vault',vault,'export','--person',p,'--mode',mode,'--review',folder,'--out',target,expect=3)['code']=='REVIEW_MISMATCH'
    assert not target.exists()
# Edited receipt and edited plan, even individually well-formed, fail host pins.
for filename in ['review.json','plan.json']:
    target=folder/filename; raw=target.read_bytes();value2=decode_json(raw)
    if filename=='review.json':value2['decision']['reason']='SYNTHETIC edited receipt'
    else:value2['originalSources'][0]['size']+=1
    target.write_bytes(encode_json(value2))
    destination=work/('denied-'+filename)
    assert command('--vault',vault,'export','--person',person,'--review',folder,'--out',destination,expect=3)['code']=='REVIEW_MISMATCH'
    assert not destination.exists();target.write_bytes(raw)
# An unrecorded plan or agent/source_data pseudo-decision is insufficient.
unrecorded,unrecorded_value=plan('unrecorded-plan')
assert command('--vault',vault,'export','--person',person,'--review',unrecorded,'--out',work/'denied-unrecorded',expect=3)['code']=='REVIEW_MISMATCH'
pseudo=work/'pseudo-decision.json';pseudo.write_bytes(encode_json({'source_data':{'source_scope_confirmed':True}}))
assert command('--vault',vault,'export-review','--plan',unrecorded,'--decision',pseudo,expect=3)['code']=='REVIEW_MISMATCH'
# Reviewed derivative is deliberately synthetic pre-authored data, not generated redaction.
derivative=work/'supplied-derivative.pdf';derivative.write_bytes(b'%PDF-1.4\nSYNTHETIC supplied exchange attachment, no clinical losslessness claim\n')
pdf=next(s for s in scope['originalSources'] if s['mediaType']=='application/pdf')
supplied=work/'derivatives.json'; supplied.write_bytes(encode_json([dict(sourceSha256=pdf['sha256'],path=str(derivative),mediaType='application/pdf',
    mapping='SYNTHETIC mapping original page 1 to attachment page 1; human assertion',
    omissions='SYNTHETIC excluded content omitted; original evidence verification unsupported')]))
dfolder,dvalue=plan('derivative-plan','selected-current',supplied);review(dfolder,dvalue)
exchange=work/'derivative-exchange'
command('--vault',vault,'export','--person',person,'--mode','selected-current','--review',dfolder,'--out',exchange)
assert not command('backup','verify',exchange)['issues']
dmanifest=decode_json((exchange/'export.json').read_bytes());dscope=dmanifest['sourceDisclosure']['plan']
assert dscope['originalDisposition']=='omitted-all' and not (exchange/'sources').exists()
assert not any('/blob' in f['path'] and not f['path'].startswith('derivatives/') for f in dmanifest['files'])
assert (exchange/f'derivatives/{sha(derivative.read_bytes())}/blob').read_bytes()==derivative.read_bytes()
assert dscope['derivatives'][0]['sourceSha256']==pdf['sha256']
assert 'original evidence references' in ' '.join(dscope['limitations'])
assert command('backup','restore',exchange,'--into',work/'not-recovery',expect=2)['code']=='INVALID_INPUT'
# Public CLI resource projection stays source-safe and retains exact original JSON.
selected=work/'source-free'
command('--vault',vault,'export','--person',person,'--mode','selected-current','--no-sources','--out',selected)
assert not command('backup','verify',selected)['issues']
assert {p.name:p.read_bytes() for p in (selected/'resources').iterdir()}=={p.name:p.read_bytes() for p in (exchange/'resources').iterdir()}
# Derivative and original hash changes are checked against the actual bytes.
blob=dfolder/dscope['derivatives'][0]['path'];raw=blob.read_bytes();blob.write_bytes(b'changed synthetic derivative')
assert command('--vault',vault,'export','--person',person,'--mode','selected-current','--review',dfolder,'--out',work/'denied-derivative-hash',expect=3)['code']=='REVIEW_MISMATCH'
blob.write_bytes(raw)
source_blob=vault/pdf['path'];raw=source_blob.read_bytes();source_blob.write_bytes(b'changed original source')
failed=command('--vault',vault,'export','--person',person,'--review',folder,'--out',work/'denied-original-hash',expect=5)
assert failed['code']=='INTEGRITY';source_blob.write_bytes(raw)
# Produce a new accepted Head through the actual public prepare/review/commit flow.
# All decisions below are explicitly SYNTHETIC test acknowledgments.
packet=work/'new-packet';candidate=work/'new-candidate'
command('--vault',vault,'intake','add',source_blob,'--person',person,'--packet',packet,'--confirm-person')
kit=next((vault/'agent-kit').iterdir())
child=subprocess.run([sys.executable,str(kit/'examples/task5-example.py'),str(packet),str(candidate)],cwd=work,env=env,capture_output=True)
assert child.returncode==0,child.stderr
# Distinguish this synthetic re-extraction from prior identical-content imports
# using generated-evidence metadata only. Clinical values and source quotes stay exact.
synthetic_evidence=decode_json((candidate/'evidence.json').read_bytes())
for entry in synthetic_evidence['entries']:
    if entry['kind']=='generated':entry['rule']+='; SYNTHETIC stale-Head qualification metadata'
(candidate/'evidence.json').write_bytes(encode_json(synthetic_evidence))
candidate_bundle=decode_json((candidate/'bundle.json').read_bytes());reconciliation={}
for entry in candidate_bundle['entry']:
    r=entry['resource']
    if r['resourceType']=='Observation':
        row=next(row for row in facts[person] if row['code']['text']==r['code']['text'])
        reconciliation[entry['fullUrl']]='Observation/'+row['resourceRef']['id']
recon=work/'reconciliation.json';recon.write_bytes(encode_json(reconciliation))
prepared=command('--vault',vault,'candidate','prepare',candidate,'--person',person,'--reextract','--reconciliation',recon)
proposal=Path(prepared['path'])
view=command('--vault',vault,'candidate','review',proposal,'--person',person)
decision=dict(confirmedPerson=True,decision='accept-with-acknowledged-limitations',
              acknowledgedIssues=[{'code':i['code'],'resourceRef':i['resourceRef'],'reason':'SYNTHETIC test acknowledgment, not clinical review'} for i in view['issues'] if i['severity'] in ('review','warning')],
              reviewerLabel='SYNTHETIC installed stale-Head qualification only')
path=work/'synthetic-import-decision.json';path.write_bytes(encode_json(decision))
command('--vault',vault,'candidate','review',proposal,'--person',person,'--decision',path)
command('--vault',vault,'candidate','commit',proposal,'--person',person)
assert command('--vault',vault,'export','--person',person,'--review',folder,'--out',work/'denied-new-head',expect=3)['code']=='REVIEW_MISMATCH'
# Installed distribution assets must initialize a fresh vault, independent of historical pins.
command('init',work/'installed-assets')
result=dict(baseline=report,people=2,acceptedPersonFiles=len(before),fullPerson=verified,
            snapshotRevisions=dmanifest['counts']['resources'],derivatives=dmanifest['counts']['assets'],
            originalSources=len(scope['originalSources']),sourceFiles=len(scope['sourceFiles']),
            sourceBytes=sum(s['size'] for s in scope['sourceFiles']),observations=len(facts[person]),
            commands=len(commands),denialWitnesses=4,python=sys.version,
            runtime=__import__('helseark').__file__,syntheticDecisionsOnly=True)
(work/'result.json').write_bytes(encode_json(result));print(encode_json(result).decode(),flush=True)
