"""Real filesystem candidate rereads. All people and decisions are synthetic."""
import json
import subprocess
import sys

import pytest

from helseark.archive import head
from helseark.serialization import encode_json, decode_json
from test_intake import supplied_candidate


# Runs in a child so the irreversible audit hook never affects another test.
# Removing either authoritative-person forwarding makes these actual reads fail.
REREAD = r'''
import json, os, sys
from pathlib import Path
from helseark.archive import _open_vault_metadata
from helseark.intake import read_candidate, prepare_candidate
from helseark.cli import main
from helseark.contracts import ArchiveError
vpath, path, person, other, mode, log = sys.argv[1:]
v = _open_vault_metadata(Path(vpath))
p = Path(path) / 'candidate.json'
data = json.loads(p.read_bytes()); data['personId'] = other
replacement = json.dumps(data).encode()
if mode == 'library':
    candidate = read_candidate(v, Path(path), person=person)
    p.write_bytes(replacement)
fd = os.open(p, os.O_WRONLY)
events = {'opens': 0, 'mutations': int(mode == 'library'), 'forbidden': [], 'witnesses': 0}
def audit(event, args):
    if event == 'open':
        target = str(args[0])
        if target in (str(p), 'candidate.json'):
            events['opens'] += 1
            if mode != 'library' and events['opens'] == 2:
                os.lseek(fd, 0, 0); os.write(fd, replacement)
                os.ftruncate(fd, len(replacement)); os.fsync(fd)
                events['mutations'] += 1
        if other in target.split('/'):
            events['forbidden'].append(target)
            raise PermissionError('active other-person denial')
sys.addaudithook(audit)
try:
    # Positive witness: prove the active guard can deny the genuine other history.
    target = next((Path(vpath)/'people'/other/'accepted').glob('*/change.json'))
    try: target.read_bytes()
    except PermissionError: events['witnesses'] += 1
    assert len(events['forbidden']) == 1
    events['forbidden'].clear()
    if mode == 'library':
        try: prepare_candidate(v, candidate)
        except ArchiveError as error: events['error'] = error.code
        else: raise AssertionError('changed candidate prepared')
    else:
        verbs = ['validate', 'candidate'] if mode == 'validate' else ['candidate', 'prepare']
        events['exit'] = main(['--vault', vpath, *verbs, path, '--person', person, '--json'])
finally:
    os.close(fd)
    Path(log).write_text(json.dumps(events))
'''


@pytest.mark.parametrize('mode', ['prepare', 'library', 'validate'])
def test_changed_person_reread_never_opens_other_history(tmp_path, mode):
    vault, person, source, packet, candidate = supplied_candidate(tmp_path)
    other = next(p.name for p in (vault.root/'people').iterdir() if p.name != person)
    # Both persons have genuine accepted Patient histories; snapshot every byte.
    before = {p: p.read_bytes() for p in vault.root.rglob('*') if p.is_file()}
    log = tmp_path/'events.json'
    child = subprocess.run([sys.executable, '-c', REREAD, str(vault.root),
        str(candidate.path), person, other, mode, str(log)], capture_output=True)
    assert child.returncode == 0, child.stderr.decode()
    events = json.loads(log.read_text())
    print(json.dumps({'mode': mode, **events}))
    assert events['witnesses'] == events['mutations'] == 1
    assert events['forbidden'] == [], events
    assert b'Traceback' not in child.stderr
    if mode == 'library':
        assert events['error'] == 'PERSON_MISMATCH'
    else:
        assert events['exit'] == 2
        assert b'PERSON_MISMATCH' in child.stderr or b'CANDIDATE_MISMATCH' in child.stdout
    assert all(p.read_bytes() == raw for p, raw in before.items())
    assert source.assetPath.read_bytes()
    assert head(vault, person) == candidate.base


@pytest.mark.parametrize('route', [('candidate', 'prepare'), ('validate', 'candidate')])
@pytest.mark.parametrize('boundary', ['oversize', 'root-symlink', 'ancestor-symlink'])
def test_cli_admits_only_bounded_nofollow_candidates(tmp_path, route, boundary):
    vault, person, source, packet, candidate = supplied_candidate(tmp_path)
    before = {p: p.read_bytes() for p in vault.root.rglob('*') if p.is_file()}
    path = tmp_path/'untrusted'
    path.mkdir()
    # Invalid JSON deliberately distinguishes rejection before parsing.
    (path/'candidate.json').write_bytes(b'not JSON')
    if boundary == 'oversize':
        with (path/'candidate.json').open('wb') as stream:
            stream.seek(64 * 1024 * 1024); stream.write(b' ')
        assert (path/'candidate.json').stat().st_size == 67108865
        code = 'SOURCE_TOO_LARGE'
    else:
        # Valid other-person metadata would reveal an unsafe preliminary parse.
        (path/'candidate.json').write_bytes(encode_json({'personId': '00000000-0000-4000-8000-000000000000'}))
        link = tmp_path/'link'
        link.symlink_to(path if boundary == 'root-symlink' else tmp_path, target_is_directory=True)
        path = link if boundary == 'root-symlink' else link/'untrusted'
        code = 'UNSAFE_PATH'
    child = subprocess.run([sys.executable, '-m', 'helseark.cli', '--vault', str(vault.root),
        *route, str(path), '--person', person, '--json'], capture_output=True)
    assert b'Traceback' not in child.stderr
    assert child.returncode == 2, child.stderr.decode()
    assert decode_json(child.stderr)['code'] == code
    assert all(p.read_bytes() == raw for p, raw in before.items())
