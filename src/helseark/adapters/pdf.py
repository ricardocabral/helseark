"""Bounded, offline pypdf text extraction, never clinical interpretation.

Only extract_pdf is public. It creates a NEW directory containing original.pdf
and pages.json. All pages succeed or the entire output is removed. No OCR,
boxes, executable/plugin selection, password handling, or person matching.
See docs/reference/pdf-extraction.md for the artifact and platform contract.
"""
from __future__ import annotations

import errno
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from helseark.contracts import ExtractionArtifact, IntakeLimits

PIN = '7.0.0'
STREAM_BYTES = 16 * 1024 * 1024
ARTIFACT_BYTES = 64 * 1024 * 1024
MEMORY_BYTES = 512 * 1024 * 1024
WALL_SECONDS = 15
CPU_SECONDS = 10

_MESSAGES = {
    'PDF_DEPENDENCY_UNSUPPORTED': 'Install the pinned optional pdf extra locally.',
    'PDF_PLATFORM_UNSUPPORTED': 'PDF resource controls are unavailable on this platform.',
    'PDF_INVALID': 'PDF parsing failed; no partial extraction was retained.',
    'PDF_ENCRYPTED': 'Encrypted PDFs are unsupported; no password was requested.',
    'PDF_STREAM_LIMIT': 'PDF decompression or parser work exceeded its limit.',
    'PDF_RESOURCE_LIMIT': 'PDF extraction exceeded its process resource budget.',
    'TEXT_FIELD_LIMIT': 'Page text exceeds the UTF-8 field limit.',
    'SOURCE_TOO_LARGE': 'Source exceeds the byte limit.',
    'PAGE_LIMIT': 'PDF exceeds the page limit.',
    'UNSAFE_PATH': 'Expected a regular source and new destination without symlinks or traversal.',
    'DESTINATION_EXISTS': 'Extraction destination already exists.',
    'PDF_IO': 'PDF extraction could not complete local I/O.',
    'SOURCE_CHANGED': 'Source changed during retention.',
}


def _error(code):
    from helseark.contracts import ArchiveError
    details = {'exitCode': 6} if code.endswith('_UNSUPPORTED') else {}
    return ArchiveError(code, _MESSAGES[code], details)


def _directory(path: Path) -> int:
    """Walk using held descriptors: no symlink-following or ancestor swap."""
    if '..' in path.parts:
        raise _error('UNSAFE_PATH')
    path = path.absolute()
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        return fd
    except OSError:
        os.close(fd)
        raise _error('UNSAFE_PATH') from None


def _publish_directory(parent: int, stage: str, destination: str) -> None:
    """Atomic absent-destination rename; never fall back to replacing rename.

    Both names are siblings beneath the held parent. This adapter does not
    change the accepted-archive publisher or its separate durability policy.
    """
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        rename = getattr(libc, 'renameatx_np' if sys.platform == 'darwin' else 'renameat2')
    except AttributeError:
        raise _error('PDF_PLATFORM_UNSUPPORTED') from None
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    # Darwin RENAME_EXCL=4; Linux RENAME_NOREPLACE=1.
    if rename(parent, os.fsencode(stage), parent, os.fsencode(destination),
              4 if sys.platform == 'darwin' else 1) != 0:
        code = ctypes.get_errno()
        if code in (errno.EEXIST, errno.ENOTEMPTY):
            raise _error('DESTINATION_EXISTS')
        if code in (errno.ENOSYS, errno.EINVAL, errno.ENOTSUP):
            raise _error('PDF_PLATFORM_UNSUPPORTED')
        raise OSError(code, 'Directory publication failed')


def _resident_reader():
    if sys.platform == 'darwin':
        # ABI from Apple's sys/resource.h: rusage_info_v0, RUSAGE_INFO_V0=0.
        import ctypes
        class Usage(ctypes.Structure):
            _fields_ = [('uuid', ctypes.c_uint8 * 16)] + [
                (name, ctypes.c_uint64) for name in (
                    'user', 'system', 'idle', 'interrupts', 'pageins', 'wired',
                    'resident', 'footprint', 'start', 'exit')]
        lib = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
        query = lib.proc_pid_rusage
        query.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.POINTER(Usage)]
        query.restype = ctypes.c_int
        def resident(pid):
            usage = Usage()
            if query(pid, 0, usage) != 0:
                raise OSError('Memory accounting unavailable')
            return usage.resident
        return resident
    if sys.platform == 'linux':
        def resident(pid):
            return int(Path(f'/proc/{pid}/statm').read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE')
        return resident
    raise _error('PDF_PLATFORM_UNSUPPORTED')


def _run_worker(source_fd, result_fd, limits):
    try:
        resident = _resident_reader()
        resident(os.getpid())  # fail closed before parsing if accounting is unavailable
    except (OSError, AttributeError, ImportError, ValueError):
        raise _error('PDF_PLATFORM_UNSUPPORTED') from None
    command = [sys.executable, '-I', str(Path(__file__).resolve()), '--worker',
               str(source_fd), str(result_fd), str(limits.pdfPages), str(limits.textFieldBytes)]
    with subprocess.Popen(command, pass_fds=(source_fd, result_fd), stdin=subprocess.DEVNULL,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          cwd='/', env={}) as process:
        deadline = time.monotonic() + WALL_SECONDS
        try:
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    raise _error('PDF_RESOURCE_LIMIT')
                try:
                    memory = resident(process.pid)
                except OSError:
                    if process.poll() is not None:
                        break
                    raise _error('PDF_PLATFORM_UNSUPPORTED') from None
                if memory > MEMORY_BYTES:
                    raise _error('PDF_RESOURCE_LIMIT')
                time.sleep(0.02)
            if process.returncode != 0:
                raise _error('PDF_RESOURCE_LIMIT')
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()


def extract_pdf(source: Path, outputDirectory: Path, limits: 'IntakeLimits') -> 'ExtractionArtifact':
    """Retain original bytes and complete page text in a new local directory.

    ArchiveError carries safe fixed messages; unsupported dependency/platform
    errors have details.exitCode=6 for the later intake/CLI caller.
    """
    from helseark.contracts import ExtractionArtifact, Issue
    try:
        if importlib.metadata.version('pypdf') != PIN:
            raise _error('PDF_DEPENDENCY_UNSUPPORTED')
    except importlib.metadata.PackageNotFoundError:
        raise _error('PDF_DEPENDENCY_UNSUPPORTED') from None
    source, outputDirectory = Path(source), Path(outputDirectory)
    if '..' in source.parts or '..' in outputDirectory.parts or not outputDirectory.name:
        raise _error('UNSAFE_PATH')
    if sys.platform not in ('darwin', 'linux'):
        raise _error('PDF_PLATFORM_UNSUPPORTED')
    parent = _directory(outputDirectory.parent)
    output = None
    stage = None
    try:
        src_parent = _directory(source.parent)
        try:
            try:
                src_fd = os.open(source.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=src_parent)
            except OSError as error:
                if error.errno in (errno.ELOOP, errno.ENOTDIR):
                    raise _error('UNSAFE_PATH') from None
                raise
        finally:
            os.close(src_parent)
        with os.fdopen(src_fd, 'rb') as incoming:
            before = os.fstat(incoming.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise _error('UNSAFE_PATH')
            if before.st_size > limits.sourceBytes:
                raise _error('SOURCE_TOO_LARGE')
            # Reserve a private sibling without ever occupying the final name.
            name = '.pdf-' + uuid.uuid4().hex
            os.mkdir(name, mode=0o700, dir_fd=parent)
            stage = name
            output = os.open(stage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            original_fd = os.open('original.pdf', os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=output)
            digest = hashlib.sha256()
            size = 0
            with os.fdopen(original_fd, 'wb') as retained:
                while block := incoming.read(65536):
                    size += len(block)
                    if size > limits.sourceBytes:
                        raise _error('SOURCE_TOO_LARGE')
                    digest.update(block)
                    retained.write(block)
            after = os.fstat(incoming.fileno())
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                    after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise _error('SOURCE_CHANGED')
        read_fd = os.open('original.pdf', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=output)
        try:
            result_fd = os.open('.result', os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=output)
        except OSError:
            os.close(read_fd)
            raise
        try:
            _run_worker(read_fd, result_fd, limits)
            os.lseek(result_fd, 0, os.SEEK_SET)
            with os.fdopen(os.dup(result_fd), 'rb') as result:
                if os.fstat(result_fd).st_size > ARTIFACT_BYTES:
                    raise _error('PDF_RESOURCE_LIMIT')
                payload = json.load(result)
        except (ValueError, UnicodeError):
            raise _error('PDF_INVALID') from None
        finally:
            os.close(read_fd)
            os.close(result_fd)
        if not isinstance(payload, dict):
            raise _error('PDF_INVALID')
        if 'error' in payload:
            code = payload['error']
            raise _error(code if code in _MESSAGES else 'PDF_INVALID')
        pages = payload.get('pages')
        if (payload.get('version') != PIN or not isinstance(pages, list) or
                not 0 < len(pages) <= limits.pdfPages):
            raise _error('PDF_INVALID')
        issues = [Issue('PDF_TEXT_REVIEW', 'review', None, None,
                        'Page text is not proof of visual completeness or clinical row attribution.')]
        for number, page in enumerate(pages, 1):
            if (not isinstance(page, dict) or set(page) != {'page', 'rotation', 'text'} or
                    type(page['page']) is not int or page['page'] != number or
                    type(page['rotation']) is not int or page['rotation'] not in (0, 90, 180, 270) or
                    not isinstance(page['text'], str)):
                raise _error('PDF_INVALID')
            if len(page['text'].encode('utf-8')) > limits.textFieldBytes:
                raise _error('TEXT_FIELD_LIMIT')
            if not page['text'].strip():
                issues.append(Issue('OCR_REQUIRED', 'review', f'/pages/{number-1}', None,
                                    'No usable text on this page; inspect original and obtain OCR separately.'))
        artifact = {'artifactVersion': 'helseark-pdf-pages-1', 'sourceSha256': digest.hexdigest(),
                    'extraction': {'provenanceVersion': '1', 'status': 'known', 'method': 'pdf-text',
                                   'tool': 'pypdf', 'version': PIN, 'model': None, 'preprocessing': []},
                    'pages': pages}
        data = (json.dumps(artifact, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
        if len(data) > ARTIFACT_BYTES:
            raise _error('PDF_RESOURCE_LIMIT')
        fd = os.open('pages.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=output)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        receipt = ExtractionArtifact('pdf-text', PIN, outputDirectory.absolute() / 'pages.json',
                                     hashlib.sha256(data).hexdigest(), len(pages), tuple(issues))
        os.unlink('.result', dir_fd=output)
        _publish_directory(parent, stage, outputDirectory.name)
        stage = None
        return receipt
    except OSError:
        raise _error('PDF_IO') from None
    finally:
        try:
            if output is not None:
                try:
                    if stage is not None:
                        for name in ('original.pdf', '.result', 'pages.json'):
                            try:
                                os.unlink(name, dir_fd=output)
                            except FileNotFoundError:
                                pass
                finally:
                    os.close(output)
            if stage is not None:
                os.rmdir(stage, dir_fd=parent)
        except OSError:
            raise _error('PDF_IO') from None
        finally:
            os.close(parent)


def _worker(source_fd, result_fd, page_limit, text_limit):
    """Private fixed child entry: resource controls precede parser import."""
    import logging
    import resource
    import warnings

    class Rejected(BaseException):
        def __init__(self, code):
            self.code = code

    class RejectWarnings(logging.Handler):
        def emit(self, record):
            raise Rejected('PDF_INVALID')

    def audit(event, args):
        if event in {'subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn'} or event.startswith('socket.'):
            raise Rejected('PDF_INVALID')

    try:
        resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
        resource.setrlimit(resource.RLIMIT_FSIZE, (ARTIFACT_BYTES, ARTIFACT_BYTES))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        if sys.platform == 'linux':
            resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    except (OSError, ValueError):
        payload = {'error': 'PDF_PLATFORM_UNSUPPORTED'}
    else:
        try:
            sys.addaudithook(audit)
            import pypdf
            from pypdf.errors import LimitReachedError
            if pypdf.__version__ != PIN:
                raise Rejected('PDF_DEPENDENCY_UNSUPPORTED')
            logging.getLogger('pypdf').addHandler(RejectWarnings(logging.WARNING))
            warnings.simplefilter('error')
            # Public configuration API in the qualified pin. All other upstream
            # security defaults remain enabled; no unbounded decompression.
            pypdf.overwrite_configuration(
                maximum_declared_stream_length=STREAM_BYTES,
                array_based_stream_maximum_output_length=STREAM_BYTES,
                zlib_maximum_output_length=STREAM_BYTES,
                lzw_maximum_output_length=STREAM_BYTES,
                run_length_maximum_output_length=STREAM_BYTES,
                stream_decoding_work_maximum_length=4 * STREAM_BYTES,
                jbig2dec_binary=None)
            with os.fdopen(source_fd, 'rb') as source:
                reader = pypdf.PdfReader(source, strict=True)
                if reader.is_encrypted:
                    raise Rejected('PDF_ENCRYPTED')
                count = len(reader.pages)
                if count > page_limit:
                    raise Rejected('PAGE_LIMIT')
                if not count:
                    raise Rejected('PDF_INVALID')
                pages = []
                for number, page in enumerate(reader.pages, 1):
                    rotation = page.rotation
                    if rotation not in (0, 90, 180, 270):
                        raise Rejected('PDF_INVALID')
                    content = page.get_contents()
                    if content is not None and len(content.get_data()) > STREAM_BYTES:
                        raise Rejected('PDF_STREAM_LIMIT')
                    text = page.extract_text(extraction_mode='plain')
                    if len(text.encode('utf-8')) > text_limit:
                        raise Rejected('TEXT_FIELD_LIMIT')
                    pages.append({'page': number, 'rotation': rotation, 'text': text})
                payload = {'version': pypdf.__version__, 'pages': pages}
            peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if peak * (1024 if sys.platform == 'linux' else 1) > MEMORY_BYTES:
                raise Rejected('PDF_RESOURCE_LIMIT')
        except Rejected as error:
            payload = {'error': error.code}
        except MemoryError:
            payload = {'error': 'PDF_RESOURCE_LIMIT'}
        except ImportError:
            payload = {'error': 'PDF_DEPENDENCY_UNSUPPORTED'}
        except LimitReachedError:
            payload = {'error': 'PDF_STREAM_LIMIT'}
        except Exception:
            payload = {'error': 'PDF_INVALID'}
    with os.fdopen(result_fd, 'w', encoding='utf-8') as result:
        json.dump(payload, result, ensure_ascii=False, separators=(',', ':'))


if __name__ == '__main__':
    if len(sys.argv) != 6 or sys.argv[1] != '--worker':
        raise SystemExit(2)
    _worker(*(int(value) for value in sys.argv[2:]))
