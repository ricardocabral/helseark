"""Standalone installed-wheel qualification; run with an isolated venv's Python.

Copy this file outside the checkout before running. No pytest dependency needed.
Arguments: fresh work directory, checkout directory (which must not be imported).
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

work = Path(sys.argv[1]).resolve()
checkout = Path(sys.argv[2]).resolve()
work.mkdir()
os.chdir(work)
import helseark.archive as archive
assert not Path(archive.__file__).resolve().is_relative_to(checkout)
assert archive._bundled_root() == Path(sys.prefix) / 'share/helseark'
console = Path(sys.executable).parent / 'helseark'
assert console.is_file()
guard = work / 'guard'
guard.mkdir()
(guard / 'sitecustomize.py').write_text('''
import os, sys
def offline(event, args):
    if event.startswith("socket."):
        with open(os.environ["NETWORK_LOG"], "a") as stream:
            stream.write(event + "\\n")
        raise RuntimeError("Runtime network forbidden")
sys.addaudithook(offline)
''')
log = work / 'network-attempts'
env = {**os.environ, 'PYTHONPATH': str(guard), 'NETWORK_LOG': str(log)}
# Prove the guard loads and rejects real socket activity, then clear its probe log.
blocked = subprocess.run([sys.executable, '-c', 'import socket; socket.socket()'], env=env, capture_output=True)
assert blocked.returncode != 0 and log.read_text().startswith('socket.')
log.unlink()
def run(*args):
    result = subprocess.run([str(console), *map(str, args)], env=env, capture_output=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)
root = work / 'vault'
run('init', root, '--json')
person = run('--vault', root, 'person', 'add', '--name', 'Synthetic installed fixture', '--json')['personId']
shutil.rmtree(root / '.runtime')
copied = work / 'copied-vault'
shutil.copytree(root, copied)
script = '''
from pathlib import Path
import sys
from helseark.archive import open_vault, resolve, _bundled_root
from helseark.contracts import ResourceRef
v = open_vault(Path(sys.argv[1]))
p = sys.argv[2]
resource = resolve(v, p, ResourceRef("Patient", p))
assert resolve(v, p, ResourceRef("Patient", p, resource["meta"]["versionId"])) == resource
assert resource["name"][0]["text"] == "Synthetic installed fixture"
assert _bundled_root() == Path(sys.prefix) / "share/helseark"
'''
resolved = subprocess.run([sys.executable, '-c', script, str(copied), person], env=env, capture_output=True)
assert resolved.returncode == 0, resolved.stderr
assert not log.exists(), 'Unexpected runtime network attempt'
print(json.dumps({'installedModule': archive.__file__, 'console': str(console), 'runtimeNetworkAttempts': 0,
                  'checks': ['console init', 'console person add', 'copied vault without runtime', 'pinned resolution', 'bundled definitions']}))
