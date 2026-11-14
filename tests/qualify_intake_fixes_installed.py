"""Offline installed Task5 corrections proof, synthetic only.

Copy this file outside checkout before running with the installed wheel Python:
python qualify_intake_fixes_installed.py ABSENT_WORK_DIRECTORY CHECKOUT
Checkout is used only to copy the synthetic PDF before activating the guard.
"""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

work, checkout = (Path(p).resolve() for p in sys.argv[1:])
work.mkdir()
shutil.copyfile(checkout / 'tests/fixtures/synthetic/task5-complete.pdf', work / 'source.pdf')
os.chdir(work)
import helseark
from helseark.archive import init_vault, add_person, open_vault
from helseark.contracts import ArchiveError, PersonDraft
from helseark.intake import read_candidate, CANDIDATE_FILE_BYTES
from helseark.serialization import decode_json, encode_json, hash_bytes
from helseark.validation import validate_candidate
assert '/site-packages/' in helseark.__file__
guard = work / 'guard'
guard.mkdir()
# All subprocesses inherit the same active guard. Include relative descriptor
# opens by UUID, not just absolute paths. Witness each denial separately.
(guard / 'sitecustomize.py').write_text("""
import os, sys
def deny(event, args):
    if event.startswith('socket.'):
        raise PermissionError('OFFLINE')
    if event in ('open', 'os.listdir', 'os.scandir') and args:
        p = str(args[0])
        other = os.environ.get('DENY_PERSON')
        if p.startswith(os.environ['DENY_CHECKOUT']) or (other and (other in p.split('/'))):
            raise PermissionError('SCOPE')
sys.addaudithook(deny)
""")
env = {k:v for k,v in os.environ.items() if k not in ('PYTHONPATH', 'HELSEARK_VAULT')}
denied_root = Path(str(checkout).split('/.worktrees/')[0])
env.update(PYTHONPATH=str(guard), DENY_CHECKOUT=str(denied_root), PYTHONDONTWRITEBYTECODE='1')
os.environ['DENY_CHECKOUT'] = str(denied_root)
exec((guard / 'sitecustomize.py').read_text(), {})
def denied(action):
    try:
        action()
    except PermissionError:
        return
    raise AssertionError('Denial witness failed')
denied(lambda: (checkout / 'AGENTS.md').read_bytes())
denied(lambda: socket.socket())
def cli(*args, code=0):
    r = subprocess.run([str(Path(sys.executable).parent / 'helseark'), *map(str,args)],
        env=env, capture_output=True)
    assert r.returncode == code, (r.returncode, r.stdout, r.stderr)
    return decode_json(r.stdout or r.stderr)
v = init_vault(work / 'vault')
person = add_person(v, PersonDraft('Avery Synthetic'))
other = add_person(v, PersonDraft('Unrelated Synthetic'))
other_change = next((v.root / 'people' / other / 'accepted').glob('*/change.json'))
other_bytes = other_change.read_bytes()
before = {str(p.relative_to(v.root)):hash_bytes(p.read_bytes())
    for p in (v.root / 'people').rglob('*') if p.is_file()}
env['DENY_PERSON'] = other
os.environ['DENY_PERSON'] = other
denied(lambda: other_change.read_bytes())
packet = cli('--vault', v.root, 'intake', 'add', work / 'source.pdf', '--person', person,
    '--packet', work / 'packet', '--confirm-person', '--json')
kit = v.root / 'agent-kit' / v.config.agentKitVersion
r = subprocess.run([sys.executable, str(kit / 'examples/task5-example.py'),
    str(work / 'packet'), str(work / 'candidate')], env=env, capture_output=True)
assert r.returncode == 0, r.stderr
args = ['--vault', v.root, 'validate', 'candidate', work / 'candidate', '--person', person, '--json']
normal = cli(*args, code=3)
assert not [i for i in normal['issues'] if i['severity'] == 'error']
c = read_candidate(v, work / 'candidate', person=person)
assert str(c.bundle['entry'][0]['resource']['valueQuantity']['value']) == '0.050'
assert c.bundle['entry'][0]['resource']['valueQuantity']['value'].as_tuple().exponent == -3
# Metadata cannot select the denied person even when it names their real UUID.
meta_path = c.path / 'candidate.json'
saved_meta = meta_path.read_bytes()
meta = decode_json(saved_meta)
meta['personId'] = other
meta_path.write_bytes(encode_json(meta))
assert cli(*args, code=2)['code'] == 'PERSON_MISMATCH'
meta_path.write_bytes(saved_meta)
# All three paths reject the same sparse whitespace file before parsing.
for name in ('candidate.json', 'bundle.json', 'evidence.json'):
    p = c.path / name
    saved = p.read_bytes()
    with p.open('wb') as f:
        f.seek(CANDIDATE_FILE_BYTES)
        f.write(b' ')
    assert cli(*args, code=2)['code'] == 'SOURCE_TOO_LARGE'
    # Task2 has already received a valid Candidate; its fresh read is still bounded.
    assert 'SOURCE_TOO_LARGE' in {i.code for i in validate_candidate(v, c).issues}
    p.unlink()
    p.symlink_to(work / 'source.pdf')
    assert 'UNSAFE_PATH' in {i.code for i in validate_candidate(v, c).issues}
    p.unlink()
    p.write_bytes(saved)
# Compare exactly the same selected candidate with only unrelated history corrupt.
os.environ.pop('DENY_PERSON')
env.pop('DENY_PERSON')
other_change.write_bytes(b'corrupt unrelated synthetic history')
assert cli(*args, code=3) == normal
try:
    open_vault(v.root)
    raise AssertionError('Global integrity accepted corruption')
except ArchiveError as error:
    assert error.code == 'INTEGRITY'
other_change.write_bytes(other_bytes)
assert before == {str(p.relative_to(v.root)):hash_bytes(p.read_bytes())
    for p in (v.root / 'people').rglob('*') if p.is_file() and '/accepted/' in str(p)}
# Fresh installed tutorial exercises the public route too.
lesson = work / 'lesson'
lesson.mkdir()
text = (Path(sys.prefix) / 'share/helseark/docs/tutorials/first-archive.md').read_text()
code = text.split('```python\n',1)[1].split('```',1)[0]
r = subprocess.run([sys.executable, '-c', code], cwd=lesson, env=env, capture_output=True, input=b"SYNTHETIC\n")
assert r.returncode == 0, (r.stdout, r.stderr)
print('PASS installed:', helseark.__file__)
print('PASS checkout/network/other-person denial witnesses; selected CLI review=3; mismatch=2')
print('PASS unrelated-corruption comparison=3; global integrity=INTEGRITY; restored history unchanged')
print('PASS 3 sparse CLI preparse caps; 3 bounded Task2 rereads; 3 no-follow rereads; Decimal scale')
print('PASS installed tutorial:', r.stdout.decode().strip())
