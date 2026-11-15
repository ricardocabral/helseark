"""Inspect real built wheel/sdist licensing; run after uv build in branch CI."""
from email.parser import BytesParser
from pathlib import Path
import re
import sys
import tarfile
import zipfile

root = Path(__file__).resolve().parents[1]
dist = Path(sys.argv[1])
wheels = list(dist.glob('*.whl'))
sdists = list(dist.glob('*.tar.gz'))
assert len(wheels) == len(sdists) == 1, 'Expected one fresh wheel and sdist'
license_bytes = (root / 'LICENSE').read_bytes()

with zipfile.ZipFile(wheels[0]) as wheel:
    metadata_path = next(n for n in wheel.namelist() if n.endswith('.dist-info/METADATA'))
    info = metadata_path.rsplit('/', 1)[0]
    metadata = BytesParser().parsebytes(wheel.read(metadata_path))
    assert metadata['License-Expression'] == 'MIT'
    assert metadata.get_all('License-File') == ['LICENSE'], 'Unrelated project license metadata'
    for markdown, html in re.findall(r'\]\(([^)]+)\)|(?:src|srcset)="([^"]+)"', metadata.get_payload()):
        target = markdown or html
        if not target.startswith(('https://', '#')):
            # Reader routes must exist in the actual wheel, without a checkout.
            from pathlib import PurePosixPath
            relative = PurePosixPath(target.split('#', 1)[0])
            assert not relative.is_absolute() and '..' not in relative.parts, target
            assert any(name.endswith('/data/share/helseark/'+str(relative))
                       for name in wheel.namelist()), ('README target absent from wheel', target)
    assert wheel.read(info + '/licenses/LICENSE') == license_bytes
    runtime_license = next(n for n in wheel.namelist() if n.endswith('.data/data/share/helseark/LICENSE'))
    assert wheel.read(runtime_license) == license_bytes
    assert not any(n.endswith('/licenses/Apache-2.0.txt') for n in wheel.namelist())

with tarfile.open(sdists[0]) as sdist:
    metadata_path = next(n for n in sdist.getnames() if n.count('/') == 1 and n.endswith('/PKG-INFO'))
    prefix = metadata_path.rsplit('/', 1)[0]
    metadata = BytesParser().parsebytes(sdist.extractfile(metadata_path).read())
    assert metadata['License-Expression'] == 'MIT'
    assert metadata.get_all('License-File') == ['LICENSE']
    assert sdist.extractfile(prefix + '/LICENSE').read() == license_bytes
    assert prefix + '/licenses/Apache-2.0.txt' not in sdist.getnames()

print('Wheel/sdist MIT metadata, license bytes and runtime license verified; no unrelated Apache notice')
