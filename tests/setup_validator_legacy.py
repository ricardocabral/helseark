"""Materialize exact immutable synthetic historical bytes; never repin a vault."""
import hashlib
import json
from pathlib import Path
import sys
import tarfile


def main():
    fixture = Path(__file__).parent/'fixtures/synthetic/validator-legacy'
    inventory = json.loads((fixture/'inventory.json').read_bytes())
    archive = fixture/'accepted-workflow.tar.gz'
    assert archive.stat().st_size == inventory['archiveBytes']
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == inventory['archiveSha256']
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=False)
    expected = {row['path']: row for row in inventory['files']}
    assert expected
    with tarfile.open(archive) as stream:
        members = stream.getmembers()
        assert len(members) == len(expected)
        assert {m.name for m in members} == set(expected)
        for member in members:
            assert member.isfile() and not Path(member.name).is_absolute()
            assert '..' not in Path(member.name).parts
            data = stream.extractfile(member).read()
            row = expected[member.name]
            assert len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256']
            target = output/member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    print('Immutable synthetic legacy files:', len(expected), flush=True)


if __name__ == '__main__':
    main()
