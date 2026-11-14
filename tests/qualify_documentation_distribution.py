"""Compare real source, sdist, wheel and optional installed bytes. No network.

Run: python tests/qualify_documentation_distribution.py SOURCE DIST [INSTALLED_SHARE]
"""
from pathlib import Path
import hashlib
import json
import sys
import tarfile
import tomllib
import zipfile

source, dist = map(lambda p: Path(p).resolve(), sys.argv[1:3])
wheel, = dist.glob('*.whl')
sdist, = dist.glob('*.tar.gz')
config = tomllib.loads((source/'pyproject.toml').read_text())
with zipfile.ZipFile(wheel) as binary, tarfile.open(sdist) as archive:
    prefix = next(n.split('/')[0] for n in archive.getnames() if n.endswith('/pyproject.toml'))
    files = {}
    for destination, patterns in config['tool']['setuptools']['data-files'].items():
        for pattern in patterns:
            matched = list(source.glob(pattern))
            assert matched, pattern
            for path in matched:
                relative = path.relative_to(source).as_posix()
                data = path.read_bytes()
                name = destination+'/'+path.name
                member, = [n for n in binary.namelist() if n.endswith('.data/data/'+name)]
                assert binary.read(member) == data, name
                assert archive.extractfile(prefix+'/'+relative).read() == data, relative
                if len(sys.argv)>3:
                    share = Path(sys.argv[3])
                    assert (share/Path(name).relative_to('share/helseark')).read_bytes() == data, name
                files[name] = len(data)
    modules = list((source/'src/helseark').rglob('*.py'))
    for path in modules:
        data=path.read_bytes(); relative=path.relative_to(source/'src').as_posix()
        assert binary.read(relative)==data
        assert archive.extractfile(prefix+'/src/'+relative).read()==data
    docs = [source/'docs/index.md', *(p for d in ('tutorials','how-to','reference','explanation') for p in (source/'docs'/d).glob('*.md'))]
    assert all('internal' not in p.parts for p in docs)
    for page in docs:
        assert page.read_bytes() == (source/'agent-kit'/page.relative_to(source)).read_bytes()
    historical = source/'tests/fixtures/synthetic/agent-workflows/historical-protocol1'
    for path in historical.rglob('*'):
        if path.is_file():
            assert archive.extractfile(prefix+'/'+path.relative_to(source).as_posix()).read()==path.read_bytes()
    for name in binary.namelist():
        assert 'docs/internal/' not in name
    for name in archive.getnames():
        assert 'docs/internal/' not in name
print(json.dumps({'dataFiles':len(files),'dataBytes':sum(files.values()), 'documentationPages':len(docs),
                  'pythonModules':len(modules),
                  'wheelSha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),
                  'sdistSha256':hashlib.sha256(sdist.read_bytes()).hexdigest()},sort_keys=True))
