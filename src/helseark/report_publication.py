"""Directory authority for disposable reports (macOS/Linux local filesystems).

Paths select authority once; subsequent mutations use directory descriptors.
No-follow traversal and exclusive rename prevent replacement-path redirection
and destination clobbering. Link identity checks detect relocated authorities.
This is not a sandbox against a principal moving an opened directory inode
between the last identity check and a mutating syscall, or tampering with private
staging. Such principals must be excluded by host directory permissions.
"""
from contextlib import ExitStack
import stat
import ctypes
import errno
import os
from pathlib import Path
import sys
from uuid import uuid4

from .contracts import ArchiveError


_FLAGS = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0)


def _invalid():
    return ArchiveError('INVALID_DESTINATION', 'Report directory authority changed or contains a symlink.', {'exitCode': 2})


class ReportPublication:
    """Bind a fresh destination, then publish two complete files without replace.

    Keep the context open across query/render work. Missing parent directories
    are created only at publication, relative to the verified existing handles.
    Staging is private and normally outside destination ancestry; cross-device
    exports use private staging on the selected destination filesystem.
    """

    def __init__(self, vault, destination):
        if not (sys.platform == 'darwin' or sys.platform.startswith('linux')):
            raise ArchiveError('UNSUPPORTED_VERSION', 'Handle-relative report publication requires macOS or Linux.')
        self.destination = Path(os.path.abspath(destination))
        root = self.vault_root = vault.root.resolve()
        if self.destination == root or (self.destination.is_relative_to(root) and
                not self.destination.is_relative_to(root/'derived')):
            raise _invalid()
        self.stack = ExitStack()
        self.chain = []
        self.missing = []

    def _open(self, name, parent=None):
        fd = os.open(name, _FLAGS, dir_fd=parent)
        self.stack.callback(os.close, fd)
        return fd

    def __enter__(self):
        try:
            self.chain.append((None, '/', self._open('/')))
            parts = self.destination.parent.parts[1:]
            for i, part in enumerate(parts):
                parent = self.chain[-1][2]
                try:
                    fd = self._open(part, parent)
                except FileNotFoundError:
                    self.missing = list(parts[i:])
                    break
                self.chain.append((parent, part, fd))
            self._verify()
            if not self.missing:
                self._absent()
            return self
        except OSError:
            self.stack.close()
            raise _invalid() from None
        except BaseException:
            self.stack.close()
            raise

    def __exit__(self, *error):
        self.stack.close()

    def _verify(self):
        # Compare each named directory to its still-open authority, including
        # every ancestor. Do not resolve a fresh pathname as write authority.
        try:
            for parent, name, fd in self.chain:
                named = os.stat(name, dir_fd=parent, follow_symlinks=False)
                opened = os.fstat(fd)
                if (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino):
                    raise _invalid()
        except OSError:
            raise _invalid() from None

    def _absent(self):
        try:
            entry = os.stat(self.destination.name, dir_fd=self.chain[-1][2], follow_symlinks=False)
            if stat.S_ISLNK(entry.st_mode):
                raise _invalid()
        except FileNotFoundError:
            return
        raise ArchiveError('DESTINATION_EXISTS', 'Report destination must not exist.', {'exitCode': 2})

    def publish(self, html, csv, svg):
        self._verify()
        parent = self.chain[-1][2]
        for name in self.missing:
            self._verify()
            try:
                os.mkdir(name, mode=0o700, dir_fd=parent)
            except FileExistsError:
                # A competing creator is not authority to adopt a new path.
                raise _invalid() from None
            fd = self._open(name, parent)
            self.chain.append((parent, name, fd))
            parent = fd
        self._verify()
        self._absent()
        # Open the temporary root component-by-component too: TMPDIR is not
        # permission to stage inside canonical data or follow a redirected path.
        temporary_root = Path(os.environ.get('TMPDIR') or ('/private/tmp' if sys.platform == 'darwin' else '/tmp')).resolve()
        if temporary_root.is_relative_to(self.vault_root) and not temporary_root.is_relative_to(self.vault_root/'derived'):
            raise _invalid()
        temp_parent = self.chain[0][2]
        try:
            for name in temporary_root.parts[1:]:
                fd = self._open(name, temp_parent)
                self.chain.append((temp_parent, name, fd))
                temp_parent = fd
        except OSError:
            raise _invalid() from None
        if os.fstat(temp_parent).st_dev != os.fstat(parent).st_dev:
            # Same-filesystem staging preserves valid external mounted exports.
            # This private sibling requires the same host permission boundary
            # as the opened destination authority.
            temp_parent = parent
        stage_name = '.helseark-report-' + uuid4().hex
        self._verify()
        os.mkdir(stage_name, mode=0o700, dir_fd=temp_parent)
        stage = self._open(stage_name, temp_parent)
        published = False
        try:
            for name, content in (('index.html', html), ('observations.csv', csv), ('report.svg', svg)):
                self._verify()
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=stage)
                with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
            os.fsync(stage)
            libc = ctypes.CDLL(None, use_errno=True)
            if sys.platform == 'darwin':
                rename = libc.renameatx_np
                flag = 4  # RENAME_EXCL
            elif sys.platform.startswith('linux') and hasattr(libc, 'renameat2'):
                rename = libc.renameat2
                flag = 1  # RENAME_NOREPLACE
            else:
                raise ArchiveError('UNSUPPORTED_VERSION', 'Handle-relative no-replace publication is unavailable.')
            rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            rename.restype = ctypes.c_int
            self._verify()
            if rename(temp_parent, os.fsencode(stage_name), parent, os.fsencode(self.destination.name), flag):
                code = ctypes.get_errno()
                if code in (errno.EEXIST, errno.ENOTEMPTY):
                    raise ArchiveError('DESTINATION_EXISTS', 'Report destination must not exist.', {'exitCode': 2})
                raise ArchiveError('IO_ERROR', 'Atomic report publication failed.')
            published = True
            # A pathname can change even inside the native rename call. The
            # handles still bind publication to the original directory; do not
            # report a now-redirected pathname as a successful result.
            self._verify()
            os.fsync(parent)
        finally:
            if not published:
                # Clean only our private stage through its handles. A moved
                # same-filesystem stage authority is retained for inspection;
                # never repair or clean up through a redirected output path.
                if temp_parent == parent:
                    self._verify()
                for name in ('index.html', 'observations.csv', 'report.svg'):
                    try:
                        os.unlink(name, dir_fd=stage)
                    except FileNotFoundError:
                        pass
                os.rmdir(stage_name, dir_fd=temp_parent)
