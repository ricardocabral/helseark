"""Installed subprocess drill. Run a copy outside the checkout.

Arguments: fresh work directory, checked export folder, checkout to deny.
No model is invoked; this proves package/offline recovery behavior only.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
from helseark.serialization import decode_json

work,source,checkout = map(lambda p:Path(p).resolve(),sys.argv[1:4])
work.mkdir()
bundle=work/'backup';shutil.copytree(source,bundle)
manifest=json.loads((bundle/'export.json').read_text())
assert manifest['counts']['changes']>=4 and manifest['counts']['resources']>=8 and manifest['counts']['assets']>0
assert len(manifest['people'])==2
guard=work/'guard';guard.mkdir()
(guard/'sitecustomize.py').write_text("""
import os,sys
from pathlib import Path
def audit(event,args):
    if event.startswith(('socket.','urllib.')):
        raise RuntimeError('network forbidden')
    if event in ('open','os.scandir','os.listdir'):
        if args and isinstance(args[0],(str,bytes)):
            p=Path(os.fsdecode(args[0])).absolute()
            for root in os.environ['PORTABILITY_DENY'].split(os.pathsep):
                if p.is_relative_to(root):
                    raise RuntimeError('original checkout/vault/cache forbidden')
sys.addaudithook(audit)
""")
env={**os.environ,'PYTHONPATH':str(guard),
     'PORTABILITY_DENY':os.pathsep.join([str(checkout),str(source),str(source.parent/'vault'),str(Path.home()/'.cache/uv')])}
console=Path(sys.executable).parent/'helseark'
def run(*args):
    child=subprocess.run([str(console),*map(str,args),'--json'],capture_output=True,cwd=work,env=env)
    assert child.returncode==0,child.stderr
    return decode_json(child.stdout)
# Guard witnesses prove both constraints actively reject an actual attempt.
for probe in ['import socket;socket.socket()',f'open({str(checkout/"pyproject.toml")!r}).read()']:
    child=subprocess.run([sys.executable,'-c',probe],env=env,capture_output=True,cwd=work)
    assert child.returncode!=0 and b'forbidden' in child.stderr
print('network and checkout guard witnesses: rejected')
assert not (bundle/'vault/.runtime').exists()
before={p.relative_to(bundle/'vault').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (bundle/'vault/people').rglob('*') if p.is_file()}
verified=run('backup','verify',bundle)
assert not verified['issues']
restored=work/'restored'
run('backup','restore',bundle,'--into',restored)
for p in [restored/'.runtime',restored/'derived',restored/'work']:
    shutil.rmtree(p,ignore_errors=True)
report=run('--vault',restored,'doctor')
assert not report['issues']
assert report['checkedChanges']==manifest['counts']['changes']
assert report['checkedResources']==manifest['counts']['resources']
assert report['checkedAssets']==manifest['counts']['assets']
after={p.relative_to(restored).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
       for p in (restored/'people').rglob('*') if p.is_file()}
assert before==after
observations=[]
selected_person=None
for person in manifest['people']:
    original=run('--vault',bundle/'vault','observations','--person',person)
    recovered=run('--vault',restored,'observations','--person',person)
    assert original==recovered
    observations.extend(recovered)
    if recovered:selected_person=person
assert len(observations)==2 and any(r['status']=='amended' for r in observations)
assert any(str(r['value'].get('value'))=='0.05' or str(r['value'].get('value'))=='0.050' for r in observations)
assert selected_person
selected=work/'selected'
run('--vault',restored,'export','--person',selected_person,'--mode','selected-current',
    '--no-sources','--out',selected)
selected_report=run('backup','verify',selected)
assert not selected_report['issues'] and selected_report['checkedResources']>2
exchange=decode_json((selected/'export.json').read_bytes())
assert exchange['referenceMap'] and all(m['fullUrl']=='urn:uuid:'+m['versionId'] for m in exchange['referenceMap'])
blocked=subprocess.run([str(console),'--vault',str(restored),'export','--person',selected_person,
                        '--out',str(work/'blocked-pdf'),'--json'],cwd=work,env=env,capture_output=True)
assert blocked.returncode==3 and decode_json(blocked.stderr)['code']=='SOURCE_SCOPE_REVIEW_REQUIRED'
assert not (work/'blocked-pdf').exists()
# Exercise installed resource packaging rather than reusing the archived definitions.
run('init',work/'installed-definition-probe')
import helseark.archive as archive
assert not Path(archive.__file__).resolve().is_relative_to(checkout)
print(json.dumps({'report':report,'acceptedFiles':len(before),'observations':len(observations),'snapshotRevisions':selected_report['checkedResources'],
                  'runtimeModule':archive.__file__,'manifestSha256':hashlib.sha256((bundle/'export.json').read_bytes()).hexdigest()},sort_keys=True))
