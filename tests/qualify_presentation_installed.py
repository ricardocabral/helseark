"""Exercise the installed console script, outside checkout and without networking.

Run a copied script with: INSTALLED_PYTHON script.py WORK CHECKOUT PRIMARY.
WORK contains accepted synthetic vaults named corpus and hostile, and case.json.
"""
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

work, checkout, primary = [Path(p).resolve() for p in sys.argv[1:4]]
case = json.loads((work/'case.json').read_text())
guard = work/'guard'
guard.mkdir()
(guard/'sitecustomize.py').write_text('''
import os, sys
from pathlib import Path
def audit(event, args):
    if event.startswith(('socket.', 'urllib.')):
        raise RuntimeError('network forbidden')
    if event in ('open', 'os.scandir', 'os.listdir') and args and isinstance(args[0], (str, bytes)):
        p = Path(os.fsdecode(args[0])).absolute()
        if any(p.is_relative_to(root) for root in os.environ['REPORT_DENY'].split(os.pathsep)):
            raise RuntimeError('checkout forbidden')
sys.addaudithook(audit)
''')
env = {**os.environ, 'PYTHONPATH':str(guard), 'REPORT_DENY':os.pathsep.join(map(str,[checkout,primary]))}
console = Path(sys.executable).parent/'helseark'
for probe in ['import socket; socket.socket()', f'open({str(checkout/"pyproject.toml")!r})']:
    result = subprocess.run([sys.executable,'-c',probe],cwd=work,env=env,capture_output=True)
    assert result.returncode and b'forbidden' in result.stderr
print('2 denial witnesses rejected', flush=True)

def run(*args):
    child = subprocess.run([str(console), *map(str,args), '--json'],cwd=work,env=env,capture_output=True)
    assert child.returncode == 0, child.stderr
    return json.loads(child.stdout)


def inventory(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and 'derived' not in p.relative_to(root).parts}

run('init',work/'installed-init')
counts = []
for name in ('corpus','hostile'):
    vault = work/name
    person = case[name]
    before = inventory(vault)
    output = run('--vault',vault,'report','--person',person)
    index = Path(output['path'])
    html = index.read_text()
    rows = list(csv.DictReader((index.parent/'observations.csv').open(newline='')))
    if name == 'corpus':
        assert len(rows) == 9
        assert '&lt;0.050 mg/L' in html and '1.2300 mg/dL' in html
        assert all(s in html for s in ('mmol/L','cancelled','entered-in-error','Not performed','2–4','0–1','month','unknown'))
    else:
        assert len(rows) == 1
        assert '<script>' not in html and '&lt;script&gt;' in html
        assert rows[0]['sourceLabel'].startswith("'=HYPERLINK")
    assert 'file://' in html and '/entries/' in html and 'sourceSha256' in html
    assert 'OTHER PERSON SECRET' not in html
    snapshot = {p.name:p.read_bytes() for p in index.parent.iterdir()}
    shutil.rmtree(vault/'derived')
    run('--vault',vault,'report','--person',person)
    assert snapshot == {p.name:p.read_bytes() for p in index.parent.iterdir()}
    external = work/(name+'-export')
    run('--vault',vault,'report','--person',person,'--out',external)
    assert (external/'index.html').read_bytes() == index.read_bytes()
    forbidden = vault/'people'/person/'accepted/report'
    rejected = subprocess.run([str(console),'--vault',str(vault),'report','--person',person,'--out',str(forbidden),'--json'],cwd=work,env=env,capture_output=True)
    assert rejected.returncode == 2 and json.loads(rejected.stderr)['code'] == 'INVALID_DESTINATION'
    assert not forbidden.exists() and inventory(vault) == before
    counts.append({'case':name,'observations':len(rows),'unchangedVaultFiles':len(before),
                   'htmlSha256':hashlib.sha256(index.read_bytes()).hexdigest()})
import helseark.presentation as presentation
assert not Path(presentation.__file__).resolve().is_relative_to(checkout)
print(json.dumps({'cases':counts,'module':presentation.__file__,'console':str(console)}, sort_keys=True))
