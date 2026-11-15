"""Run a COPY outside checkout with the actual installed console script.

Arguments: fresh work directory, copied synthetic scan, denied checkout, wheel.
Launch with audit guards denying network and checkout reads. Native subprocesses
enforce OS network denial themselves (macOS rejects nested OS sandboxes). No model is run.
Native Tesseract is real; candidate is the independent hand-authored Task5 oracle.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import zipfile
from helseark.serialization import decode_json,encode_json,hash_bytes
from helseark.archive import _bundled_root
from helseark.adapters.ocr import MODEL_SHA256

work,scan,checkout,wheel=map(lambda p:Path(p).resolve(),sys.argv[1:5])
work.mkdir()
console=Path(sys.executable).parent/'helseark'
assert not Path(__import__('helseark').__file__).resolve().is_relative_to(checkout)
# Active guard witnesses; CLI children inherit the same guard. Native tools use OS network denial.
try:
    (checkout/'pyproject.toml').read_bytes()
except PermissionError:
    print('checkout read witness: denied',flush=True)
else:raise AssertionError('Checkout read was allowed')
probe=None
try:
    probe=socket.socket();probe.bind(('127.0.0.1',0))
except PermissionError:
    print('network socket witness: denied',flush=True)
else:raise AssertionError('Network bind was allowed')
finally:
    if probe is not None:probe.close()

calls=[]
def run(*args,expect=0):
    command=[str(console),*map(str,args),'--json']
    child=subprocess.run(command,cwd=work,capture_output=True,env=os.environ.copy())
    calls.append({'args':list(map(str,args)),'exit':child.returncode})
    print(json.dumps(calls[-1]),flush=True)
    assert child.returncode==expect,(args,child.returncode,child.stderr.decode())
    return decode_json(child.stdout if child.stdout else child.stderr)

# Wheel -> installed module/support closure; no checkout reads needed.
closure=[]
with zipfile.ZipFile(wheel) as archive:
    for name in archive.namelist():
        if name.startswith('helseark/') and not name.endswith('/'):
            target=Path(__import__('helseark').__file__).parent.parent/name
        elif '.data/data/' in name and not name.endswith('/'):
            target=Path(sys.prefix)/name.split('.data/data/',1)[1]
        else:continue
        data=archive.read(name)
        assert target.read_bytes()==data,(name,target)
        closure.append({'wheelPath':name,'size':len(data),'sha256':hash_bytes(data)})
assert len(closure)>150
vault=work/'vault';run('init',vault)
person=run('--vault',vault,'person','add','--name','Avery Synthetic')['personId']
other=run('--vault',vault,'person','add','--name','UNSELECTED SECRET')['personId']
config={'outputDirectory':str(work/'ocr'),'engine':'/opt/homebrew/bin/tesseract',
    'engineSha256':hash_bytes(Path('/opt/homebrew/bin/tesseract').read_bytes()),
    'renderer':'/opt/homebrew/bin/pdftoppm','rendererSha256':hash_bytes(Path('/opt/homebrew/bin/pdftoppm').read_bytes()),
    'model':'/opt/homebrew/share/tessdata/eng.traineddata','rotation':0}
assert hash_bytes(Path(config['model']).read_bytes())==MODEL_SHA256
config_path=work/'config.json';config_path.write_bytes(encode_json(config))
packet=work/'packet'
run('--vault',vault,'intake','add',scan,'--person',person,'--packet',packet,
    '--confirm-person','--ocr-config',config_path)
meta=decode_json((packet/'intake.json').read_bytes())
digest=meta['extraction']['pagesSha256'];source=meta['source']
artifact=decode_json((vault/f'people/{person}/assets/sha256/{digest}/blob').read_bytes())
assert b'UNSELECTED SECRET' not in (packet/'prompt.txt').read_bytes()
assert other.encode() not in (packet/'prompt.txt').read_bytes()
example=_bundled_root()/'agent-kit/examples'
replacements={b'11111111-1111-4111-8111-111111111111':person.encode(),
    b'SOURCE_HASH':source['sourceSha256'].encode(),b'EXTRACTION_HASH':digest.encode()}
def bound(name):
    data=(example/name).read_bytes()
    for old,new in replacements.items():data=data.replace(old,new)
    return decode_json(data)
bundle=bound('task5-bundle.json');evidence=bound('task5-evidence.json')
for entry in evidence['entries']:
    if entry['kind']=='source':entry['extraction']=artifact['extraction']
metadata={'contractVersion':'0.1.0','fhirVersion':'4.0.1','profileVersion':'0.1.0',
    'candidateId':meta['importId'],'personId':person,
    'baseChangeSha256':decode_json((packet/'context/context.json').read_bytes())['base']['changeSha256'],
    'sourceSha256':[source['sourceSha256']],'bundlePath':'bundle.json','evidencePath':'evidence.json',
    'producer':{'kind':'local-user','name':'hand-authored synthetic OCR oracle, no model'},
    'producerProvenance':evidence['producerProvenance'],'unresolved':meta['issues']}
candidate=work/'candidate';candidate.mkdir()
for name,value in [('candidate.json',metadata),('bundle.json',bundle),('evidence.json',evidence)]:
    (candidate/name).write_bytes(encode_json(value))
run('--vault',vault,'validate','candidate',candidate,'--person',person,expect=3)
prepared=run('--vault',vault,'candidate','prepare',candidate,'--person',person)
proposal=Path(prepared['path'])
view=run('--vault',vault,'candidate','review',proposal,'--person',person)
assert any(i['code']=='OCR_VISUAL_REVIEW' for i in view['issues'])
decision=work/'decision.json';decision.write_bytes(encode_json({'confirmedPerson':True,'decision':'accept',
    'acknowledgedIssues':[],'reviewerLabel':'synthetic human'}))
run('--vault',vault,'candidate','review',proposal,'--person',person,'--decision',decision,expect=3)
decision.write_bytes(encode_json({'confirmedPerson':True,'decision':'accept-with-acknowledged-limitations',
    'acknowledgedIssues':[{'code':i['code'],'resourceRef':i['resourceRef'],'reason':'Synthetic manual source inspection.'}
        for i in view['issues'] if i['severity'] in ('review','warning')],'reviewerLabel':'synthetic human'}))
run('--vault',vault,'candidate','review',proposal,'--person',person,'--decision',decision)
run('--vault',vault,'candidate','commit',proposal,'--person',person)
query=run('--vault',vault,'observations','--person',person)
assert len(query)==2 and any(isinstance(r['value'],dict) and str(r['value'].get('value'))=='0.050' for r in query)
assert run('--vault',vault,'observations','--person',other)==[]
accepted={p.relative_to(vault).as_posix():hash_bytes(p.read_bytes()) for p in (vault/'people').rglob('*') if p.is_file() and '/accepted/' in str(p)}
run('--vault',vault,'candidate','prepare',candidate,'--person',person)
# Current head is obtainable from installed record data; use proposal/accepted change hash.
change=next((vault/f'people/{person}/accepted').glob('00000002-*/change.json'))
metadata['baseChangeSha256']=hash_bytes(change.read_bytes())
(candidate/'candidate.json').write_bytes(encode_json(metadata))
next(e for e in evidence['entries'] if e['kind']=='source')['locator']['bbox']=[0,0,1,1]
(candidate/'evidence.json').write_bytes(encode_json(evidence))
assert run('--vault',vault,'candidate','prepare',candidate,'--person',person,expect=3)['code']=='REEXTRACTION_REQUIRED'
assert run('--vault',vault,'candidate','prepare',candidate,'--person',person,'--reextract',expect=3)['code']=='RECONCILIATION_REQUIRED'
for path,digest_before in accepted.items():assert hash_bytes((vault/path).read_bytes())==digest_before
shutil.rmtree(vault/'work');shutil.rmtree(vault/'.runtime')
backup=work/'backup';run('--vault',vault,'backup','create','--out',backup)
restored=work/'restored';run('backup','restore',backup,'--into',restored)
assert run('--vault',restored,'observations','--person',person)==query
report=run('--vault',restored,'doctor');assert not report['issues']
for path,digest_before in accepted.items():assert hash_bytes((restored/path).read_bytes())==digest_before
for derivative in artifact['derivatives']:
    assert hash_bytes((restored/f"people/{person}/assets/sha256/{derivative['sha256']}/blob").read_bytes())==derivative['sha256']
# Corrupt a retained derivative; ordinary accepted reading must fail closed.
bad=restored/f"people/{person}/assets/sha256/{artifact['derivatives'][0]['sha256']}/blob"
bad.write_bytes(b'corrupt')
assert run('--vault',restored,'doctor',expect=5)['issues']
run('--vault',restored,'observations','--person',person,expect=5)
result={'commands':calls,'installedFiles':len(closure),'closure':closure,'wheelSha256':hash_bytes(wheel.read_bytes()),
    'observations':len(query),'acceptedFiles':len(accepted),'derivativeEntries':len(artifact['derivatives']),
    'distinctAssets':report['checkedAssets'],'changes':report['checkedChanges'],'resources':report['checkedResources'],
    'runtimeModule':__import__('helseark').__file__}
(work/'result.json').write_bytes(encode_json(result));print(encode_json({k:v for k,v in result.items() if k not in ('closure','commands')}).decode(),flush=True)
