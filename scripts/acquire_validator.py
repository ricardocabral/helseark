#!/usr/bin/env python3
"""Explicit maintainer-only acquisition of pinned public software; never runtime.

Downloads no records; refuses changed bytes. Keeps bundled license/NOTICE files
verbatim alongside the JAR. Supply Java 17 separately with its vendor notices.
Retains acquisition.jsonl even when the corpus cannot start; transfer failures
and changed bytes remain failures. See scripts/README.md for diagnostic limits.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from http.client import HTTPException, IncompleteRead
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen
import zipfile


def public_url(url):
    """Never retain signed redirect queries, credentials or fragments."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc.rsplit('@', 1)[-1], parts.path, '', ''))


def acquire(pin, target, report):
    """Publish only an exact pin; retain bounded transfer facts even on failure.

    Diagnostics contain no response bodies, arbitrary headers or exception text.
    A failed transfer's digest describes only the bytes actually read, never an
    asserted replacement pin. The failed temporary binary is not an evidence file.
    """
    record = dict(artifact=pin['filename'], url=public_url(pin['url']),
                  startedAt=datetime.now(timezone.utc).isoformat(),
                  expectedBytes=pin['bytes'], expectedSha256=pin['sha256'],
                  readLimitBytes=pin['bytes']+1, status=None, finalUrl=None,
                  contentLength=None, result='transfer-error', digestScope='partial-body')
    digest = hashlib.sha256()
    observed = 0
    partial = target.with_name(target.name+'.part')
    owns_partial = False
    try:
        if target.exists():
            raise FileExistsError(target)
        output = partial.open('xb')
        owns_partial = True
        with output, urlopen(pin['url'], timeout=120) as response:
            record['status'] = response.status
            record['finalUrl'] = public_url(response.geturl())
            length = response.headers.get('Content-Length', '')
            if length.isascii() and length.isdecimal() and len(length) <= 20:
                record['contentLength'] = int(length)
            while observed < record['readLimitBytes']:
                try:
                    chunk = response.read(min(1024*1024, record['readLimitBytes']-observed))
                except IncompleteRead as error:
                    # Chunked HTTP may deliver bytes inside its failure exception.
                    observed += len(error.partial)
                    digest.update(error.partial)
                    raise
                if not chunk:
                    record['digestScope'] = 'complete-body'
                    break
                observed += len(chunk)
                digest.update(chunk)
                output.write(chunk)
            else:
                record['digestScope'] = 'bounded-prefix'
        if observed != pin['bytes'] or digest.hexdigest() != pin['sha256']:
            record['result'] = 'pin-mismatch'
        else:
            partial.rename(target)
            record['result'] = 'verified'
    except (OSError, URLError, HTTPException) as error:
        record['errorType'] = type(error).__name__
        if isinstance(error, URLError) and isinstance(error.reason, OSError):
            record['causeType'] = type(error.reason).__name__
            record['errno'] = error.reason.errno
        if isinstance(error, HTTPError):
            record['status'] = error.code
            record['finalUrl'] = public_url(error.geturl())
            error.close()
    finally:
        record['observedBytes'] = observed
        record['observedSha256'] = digest.hexdigest()
        record['finishedAt'] = datetime.now(timezone.utc).isoformat()
        # A small journal survives when a later artifact or the corpus fails.
        with report.open('a') as evidence:
            evidence.write(json.dumps(record, sort_keys=True)+'\n')
        print(json.dumps(record, sort_keys=True), flush=True)
        if owns_partial:
            partial.unlink(missing_ok=True)
    if record['result'] != 'verified':
        raise SystemExit(f"Acquisition failed for {pin['filename']}: {record['result']}; see {report.name}.")


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
        acquire(pin, target, destination/'acquisition.jsonl')
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
