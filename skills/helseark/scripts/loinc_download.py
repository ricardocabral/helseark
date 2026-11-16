#!/usr/bin/env python3
"""Explicit, authenticated LOINC acquisition; never installs or changes records.

Run this script in a local terminal with --version and --destination NEW_DIRECTORY.
Both account fields use hidden prompts. download() is the noninteractive boundary:
credentials stay in memory, HTTPS requests cannot redirect or leave the official
origin, and original ZIP bytes must match the requested release's official MD5.
The private destination is created only after verification; each file is published
without replacement, with receipt.json last as the completion marker. Directory
creation and the two file publications are not one filesystem transaction.

Protocol: https://loinc.org/kb/api/download/ and https://loinc.org/kb/api/auth/
"""
import argparse
import base64
from datetime import datetime, timezone
import getpass
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import BinaryIO
import urllib.error
import urllib.parse
import urllib.request
import warnings


API = 'https://loinc.regenstrief.org/api/v1/Loinc'
MAX_METADATA_BYTES = 1024 * 1024
MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 30


class DownloadError(Exception):
    """An acquisition failed; messages contain no remote content or credentials."""


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's usual error includes unknown arguments, potentially secrets.
        raise DownloadError('Invalid acquisition arguments.')


def _new_destination(destination: Path) -> Path:
    destination = Path(os.path.abspath(destination))
    if any(part.is_symlink() for part in (destination, *destination.parents)):
        raise DownloadError('Symlink paths are not supported.')
    if destination.exists() or not destination.parent.is_dir():
        raise DownloadError('Use a new directory in an existing parent directory.')
    return destination


def _official_url(url: object) -> str:
    if not isinstance(url, str) or not url or any(char.isspace() or ord(char) < 32 for char in url):
        raise DownloadError('Invalid download metadata.')
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname != 'loinc.regenstrief.org'
            or parsed.port not in (None, 443) or parsed.username is not None
            or parsed.password is not None or parsed.fragment):
        raise DownloadError('Invalid download metadata.')
    return url


def _receive(opener: urllib.request.OpenerDirector, url: str, authorization: str,
             target: BinaryIO, limit: int) -> tuple[int, str, str]:
    """Stream bounded bytes, reject status/length failures, and hash original bytes."""
    request = urllib.request.Request(url, headers={
        'Authorization': authorization, 'Accept-Encoding': 'identity',
        'User-Agent': 'Helseark-LOINC-acquisition/1',
    })
    try:
        response = opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS)
    except urllib.error.HTTPError as error:
        error.close()
        raise DownloadError('The LOINC request failed.') from None
    with response:
        if response.status != 200:
            raise DownloadError('The LOINC request failed.')
        length = response.headers.get('Content-Length')
        expected = None
        if length is not None:
            if not re.fullmatch(r'[0-9]+', length) or len(length) > 20:
                raise DownloadError('Invalid response length.')
            expected = int(length)
            if expected > limit:
                raise DownloadError('The response exceeds the download limit.')
        md5 = hashlib.md5(usedforsecurity=False)
        sha256 = hashlib.sha256()
        size = 0
        while True:
            chunk = response.read(min(64 * 1024, limit - size + 1))
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise DownloadError('The response exceeds the download limit.')
            target.write(chunk)
            md5.update(chunk)
            sha256.update(chunk)
        if not size or (expected is not None and expected != size):
            raise DownloadError('The response is empty or incomplete.')
    return size, md5.hexdigest(), sha256.hexdigest()


def _publish(staging: Path, destination: Path) -> None:
    """Reserve exclusively; commit receipt last; clean up only our own entries."""
    destination = _new_destination(destination)
    destination.mkdir(mode=0o700)
    identity = destination.stat()
    publications: list[tuple[Path, os.stat_result]] = []
    try:
        for name in ('loinc.zip', 'receipt.json'):
            source = staging / name
            publications.append((destination / name, source.stat()))
            os.link(source, destination / name)
    except BaseException:
        # Never recursively delete a destination: another session may add files.
        try:
            current = destination.lstat()
            if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
                for path, original in reversed(publications):
                    try:
                        current_file = path.lstat()
                    except FileNotFoundError:
                        continue
                    if (current_file.st_dev, current_file.st_ino) == (original.st_dev, original.st_ino):
                        path.unlink()
                destination.rmdir()
        except OSError:
            pass
        raise


def download(version: str, destination: Path, username: str, password: str) -> dict:
    """Acquire and verify an exact official release in a fresh private directory.

    Requires an existing, nonsymlink parent. Returns the saved receipt including
    official MD5 and retained-byte SHA256. Raises sanitized DownloadError on input,
    HTTP, integrity or filesystem failure; interruptions propagate after cleanup.
    The receipt marks completion. No account field or raw metadata is persisted.
    """
    try:
        if not isinstance(version, str) or not re.fullmatch(r'[0-9]{1,8}\.[0-9]{1,8}', version):
            raise DownloadError('Specify an exact numeric LOINC version.')
        if (not isinstance(username, str) or not isinstance(password, str)
                or not username or not password or ':' in username
                or len(username) > 1024 or len(password) > 4096
                or any(ord(char) < 32 or ord(char) == 127 for char in username + password)):
            raise DownloadError('Invalid account credentials.')
        destination = _new_destination(destination)
        authorization = 'Basic ' + base64.b64encode(f'{username}:{password}'.encode('utf-8')).decode('ascii')
        # No proxy environment or automatic authentication/redirect forwarding.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirects())
        metadata_url = API + '?' + urllib.parse.urlencode({'version': version})
        with tempfile.TemporaryDirectory(prefix='.loinc-acquisition-', dir=destination.parent) as temporary:
            staging = Path(temporary)
            # Metadata stays in bounded memory; raw metadata is never saved.
            metadata_bytes = io.BytesIO()
            _receive(opener, metadata_url, authorization, metadata_bytes, MAX_METADATA_BYTES)
            metadata = json.loads(metadata_bytes.getvalue())
            if not isinstance(metadata, dict) or metadata.get('version') != version:
                raise DownloadError('The metadata release does not match the requested version.')
            official_md5 = metadata.get('downloadMD5Hash')
            if not isinstance(official_md5, str) or not re.fullmatch(r'[a-fA-F0-9]{32}', official_md5):
                raise DownloadError('Invalid download metadata.')
            download_url = _official_url(metadata.get('downloadUrl'))
            archive = staging / 'loinc.zip'
            with archive.open('xb') as target:
                os.chmod(archive, stat.S_IRUSR | stat.S_IWUSR)
                size, md5, sha256 = _receive(opener, download_url, authorization, target, MAX_ARCHIVE_BYTES)
                target.flush()
                os.fsync(target.fileno())
            if md5 != official_md5.lower():
                raise DownloadError('The release checksum does not match.')
            receipt = {'format': 1, 'loinc_version': version, 'source': metadata_url,
                       'md5': md5, 'sha256': sha256, 'bytes': size,
                       'acquired_at': datetime.now(timezone.utc).isoformat()}
            receipt_path = staging / 'receipt.json'
            with receipt_path.open('x', encoding='utf-8') as target:
                os.chmod(receipt_path, stat.S_IRUSR | stat.S_IWUSR)
                json.dump(receipt, target, ensure_ascii=True, indent=2)
                target.write('\n')
                target.flush()
                os.fsync(target.fileno())
            _publish(staging, destination)
        return receipt
    except DownloadError:
        raise
    except (OSError, ValueError, TypeError, RecursionError, http.client.HTTPException):
        raise DownloadError('LOINC acquisition failed.') from None


def main(argv: list[str] | None = None) -> int:
    """Read credentials only from hidden native terminal prompts; return exit code."""
    try:
        parser = _Parser(description=__doc__)
        parser.add_argument('--version', required=True, help='Exact LOINC release, for example 2.83')
        parser.add_argument('--destination', required=True, type=Path, help='New private download directory')
        args = parser.parse_args(argv)
        _new_destination(args.destination)
        if not sys.stdin.isatty() or not sys.stderr.isatty():
            raise DownloadError('A local terminal is required for hidden account entry.')
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            username = getpass.getpass('LOINC username (hidden): ')
            password = getpass.getpass('LOINC password (hidden): ')
        receipt = download(args.version, args.destination, username, password)
        print(json.dumps(receipt, ensure_ascii=True))
        return 0
    except KeyboardInterrupt:
        print('LOINC acquisition interrupted.', file=sys.stderr)
        return 130
    except (DownloadError, getpass.GetPassWarning, EOFError, OSError):
        print('LOINC acquisition failed. Use a local terminal, valid account and a new directory.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
