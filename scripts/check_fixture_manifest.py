"""Check declared synthetic provenance and exact fixture/example byte inventory.

This is an auditable declaration gate, not a PHI detector or accuracy evaluation.
"""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
ROOTS = ('tests/fixtures', 'agent-kit/examples', 'examples/synthetic-family')


def check(root=ROOT):
    manifest = json.loads((root/'tests/fixture-manifest.json').read_text())
    assert manifest['syntheticOnly'] is True
    assert manifest['accuracyClaim'] == 'none; predetermined candidates are not model evaluations'
    actual = {p.relative_to(root).as_posix() for directory in ROOTS for p in (root/directory).rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    entries = manifest['files']
    assert len(entries)==len({e['path'] for e in entries}), 'Duplicate fixture path'
    assert actual == {e['path'] for e in entries}, 'Missing or unaccounted fixture/example'
    for entry in entries:
        path = root/entry['path']
        assert not path.is_symlink(), entry['path']
        data = path.read_bytes()
        assert entry['synthetic'] is True and entry['license'] in ('CC0-1.0','Apache-2.0','MIT')
        assert entry['provenance'] and entry['sha256']==hashlib.sha256(data).hexdigest() and entry['size']==len(data), entry['path']
    cases=json.loads((root/'examples/synthetic-family/expected-facts.json').read_text())
    assert cases['synthetic'] is True and all(c['coverage'] for c in cases['cases'])
    return {'files':len(entries),'cases':len(cases['cases']),'syntheticDeclarationChecked':True,'modelRuns':0}


if __name__=='__main__':
    try:
        print(json.dumps(check(),sort_keys=True))
    except (AssertionError,KeyError,ValueError,OSError) as error:
        print(f'Fixture provenance check failed: {error}',file=sys.stderr)
        raise SystemExit(1)
