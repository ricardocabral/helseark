"""Run a copied script outside the checkout with an installed wheel and old backup.

Arguments: fresh work directory, exact bdd59ca Task8 synthetic backup, checkout.
This is deterministic preservation/CLI qualification, never model evaluation.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

from helseark.serialization import decode_json, encode_json

work,original,checkout = (Path(arg).resolve() for arg in sys.argv[1:4])
work.mkdir()
legacy=work/'legacy';legacy.mkdir()
shutil.copytree(original,legacy/'snapshot')
(legacy/'legacy-test-only.json').write_bytes(encode_json({
    'format':'helseark-test-only-layout-0',
    'notice':'TEST ONLY: not a supported public release; synthetic fixtures only',
    'snapshotPath':'snapshot'}))
guard=work/'guard';guard.mkdir()
(guard/'sitecustomize.py').write_text('''
import os,sys
from pathlib import Path
def audit(event,args):
    if event.startswith(('socket.','urllib.')):
        raise RuntimeError('network forbidden')
    if event in ('open','os.scandir','os.listdir') and args and isinstance(args[0],(str,bytes)):
        p=Path(os.fsdecode(args[0])).absolute()
        if any(p.is_relative_to(Path(root)) for root in os.environ['MIGRATION_DENY'].split(os.pathsep)):
            raise RuntimeError('checkout/original/cache forbidden')
sys.addaudithook(audit)
''')
env={**os.environ,'PYTHONPATH':str(guard),'MIGRATION_DENY':os.pathsep.join([
    str(checkout),str(original),str(Path.home()/'.cache/uv')])}
console=Path(sys.executable).parent/'helseark'
commands=0
def run(*args,code=0):
    global commands
    child=subprocess.run([str(console),*map(str,args),'--json'],cwd=work,env=env,capture_output=True)
    commands+=1
    assert child.returncode==code,(args,child.returncode,child.stderr)
    return decode_json(child.stdout if child.stdout else child.stderr)
for probe in ['import socket;socket.socket()',f'open({str(checkout/"pyproject.toml")!r}).read()']:
    child=subprocess.run([sys.executable,'-c',probe],cwd=work,env=env,capture_output=True)
    assert child.returncode!=0 and b'forbidden' in child.stderr
print('guard witnesses: real network and checkout reads rejected',flush=True)

def inventory(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and '.runtime' not in p.relative_to(root).parts}
old=legacy/'snapshot/vault';before=inventory(legacy)
assert decode_json((old/'vault.json').read_bytes())['agentKitVersion']=='0.1.3'
assert not run('backup','verify',legacy/'snapshot')['issues']
unsupported=run('--vault',old,'migrate','plan','--to-fhir','5.0.0',code=6)
assert unsupported['planClass']=='fhir-release' and unsupported['blockedRecords']
plan=run('--vault',legacy,'migrate','plan','--test-only-legacy','--to-contract','0.1.0')
assert plan['expectedCounts']=={'changes':4,'resources':10,'assets':2}
assert len(plan['sourceHeads'])==2 and plan['requiredDefinitions']
assert not plan['semanticLosses'] and not plan['blockedRecords']
assert inventory(legacy)==before
planfile=work/'plan.json';planfile.write_bytes(encode_json(plan));out=work/'migrated'
wrong=run('--vault',legacy,'migrate','apply','--test-only-legacy','--plan',planfile,
    '--reviewed-plan-sha256','0'*64,'--into',out,code=3)
assert wrong['code']=='REVIEW_MISMATCH' and not out.exists()
receipt=run('--vault',legacy,'migrate','apply','--test-only-legacy','--plan',planfile,
    '--reviewed-plan-sha256',plan['planSha256'],'--into',out)
assert receipt['originalUnchanged'] and receipt['validatedCounts']==plan['expectedCounts']
assert inventory(legacy)==before
assert not run('--vault',out,'doctor')['issues']
for path,digest in inventory(old).items():
    assert hashlib.sha256((out/path).read_bytes()).hexdigest()==digest
mapping=decode_json(Path(receipt['mappingInventoryPath']).read_bytes())
assert mapping['plan']['requiredDefinitions']==plan['requiredDefinitions']
for item in mapping['byteMappings']:
    assert item['sourcePath']=='snapshot/vault/'+item['destinationPath']
    assert item['oldSha256']==item['newSha256']==before[item['sourcePath']]
rows=[]
for person in plan['sourceHeads']:
    original_rows=run('--vault',old,'observations','--person',person,'--include-invalidated')
    migrated_rows=run('--vault',out,'observations','--person',person,'--include-invalidated')
    assert encode_json(original_rows)==encode_json(migrated_rows)
    rows.extend(migrated_rows)
assert len(rows)==2 and any(row['status']=='amended' for row in rows)
assert any(isinstance(row['value'],dict) and str(row['value'].get('value'))=='0.050' and row['comparator']=='<' and row['effective']=='2026-01' for row in rows)
run('backup','restore',legacy/'snapshot','--into',work/'rollback')
assert not run('--vault',work/'rollback','doctor')['issues']
# Fresh installed pins and installed standalone references, independent of old vault.
fresh=work/'fresh';run('init',fresh)
config=decode_json((fresh/'vault.json').read_bytes());assert config['agentKitVersion']=='0.1.4'
kit=fresh/'agent-kit/0.1.4'
manifest=decode_json((kit/'manifest.json').read_bytes())
for entry in manifest['files']:
    data=(kit/entry['path']).read_bytes()
    assert hashlib.sha256(data).hexdigest()==entry['sha256'] and len(data)==entry['size']
lock=decode_json((fresh/'definitions/lock.json').read_bytes())
for artifact in lock['artifacts']:
    for entry in artifact['files']:
        data=(fresh/'definitions'/entry['path']).read_bytes()
        assert hashlib.sha256(data).hexdigest()==entry['sha256'] and len(data)==entry['size']
for path in ['docs/how-to/migrate-archive.md','docs/reference/compatibility.md','docs/explanation/evolution.md','schemas/0.1.0/migration.schema.json']:
    assert (kit/path).is_file()
assert next(task for task in manifest['tasks'] if task['id']=='migrate')['availability']['status']=='available'
import helseark.migrations as migrations
assert not Path(migrations.__file__).resolve().is_relative_to(checkout)
print(json.dumps({'status':'passed','cliCommands':commands,'people':2,'changes':4,'resources':10,'assets':2,
    'currentKit':'0.1.4','retainedKit':'0.1.3','byteMappings':len(plan['byteMappings']),
    'requiredDefinitions':len(plan['requiredDefinitions']),'network':'denied','checkout':'denied',
    'modelEvaluation':'not run; no extraction accuracy claim'},sort_keys=True),flush=True)
