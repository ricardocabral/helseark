#!/usr/bin/env python3
"""Explicit maintainer-only acquisition of pinned public software; never runtime.

Downloads no records; refuses changed bytes. Keeps bundled license/NOTICE files
verbatim alongside the JAR. Supply Java 17 separately with its vendor notices.
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--linux-jre',action='store_true',help='Explicitly acquire pinned Linux x64 CI JRE too.')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    lock = json.loads((root/'definitions/validator-lock.json').read_text())
    destination = args.destination
    destination.mkdir(parents=True, exist_ok=False)
    packages = destination/'packages'; packages.mkdir()
    artifacts = [dict(url=lock['url'], sha256=lock['executableSha256'], bytes=204856882,
                      filename='validator_cli.jar'), *lock['packages']]
    if args.linux_jre: artifacts.append(lock['ciJava'])
    for pin in artifacts:
        target = destination/pin['filename'] if pin['filename'].endswith(('.jar','.tar.gz')) else packages/pin['filename']
        # Read at most exact pin + one byte, never unbounded remote content.
        with urlopen(pin['url'], timeout=120) as response:
            data = response.read(pin['bytes']+1)
        if len(data) != pin['bytes'] or hashlib.sha256(data).hexdigest() != pin['sha256']:
            raise SystemExit('Acquisition failed byte/digest pin; preserve directory for inspection.')
        target.write_bytes(data)
    retain_notices(destination/'validator_cli.jar', destination/'notices')
    if args.linux_jre:
        import tarfile
        with tarfile.open(destination/lock['ciJava']['filename']) as archive:
            members=archive.getmembers()
            if len(members)>10000 or sum(m.size for m in members)>256*1024*1024:
                raise SystemExit('JRE archive exceeds bounds')
            archive.extractall(destination/'runtime',filter='data')


def retain_notices(jar, directory):
    """Do not interpret/relicense third-party code; retain every embedded notice."""
    directory.mkdir(parents=True)
    inventory = []
    with zipfile.ZipFile(jar) as archive:
        for name in archive.namelist():
            if not name.endswith('/') and (name.upper().startswith(('LICENSE','NOTICE')) or
                name.startswith('META-INF/') and any(x in name.lower() for x in ('license','notice','dependencies')) or
                name in ('turtle/LICENSE','org/xmlresolver/notices/w3c-license.txt')):
                data = archive.read(name)
                # Flatten into digest-named files; original names retained in inventory.
                digest = hashlib.sha256(data).hexdigest()
                (directory/(digest+'.txt')).write_bytes(data)
                inventory.append({'member':name,'sha256':digest,'bytes':len(data)})
    (directory/'inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')


if __name__ == '__main__':
    main()
