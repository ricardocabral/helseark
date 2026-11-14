"""Failed reads cannot certify the vault's unknown-material closure."""
import errno
import os
from pathlib import Path

import pytest

from helseark.archive import init_vault, add_person, doctor, head, _publish_change
from helseark.contracts import PersonDraft, ExportSelection, ArchiveError
from helseark.portability import backup, export_person
from helseark.serialization import decode_json, hash_bytes


def output_results(vault, person, root):
    results = {}
    for mode in ('backup', 'full-person', 'selected-current'):
        destination = root/mode
        try:
            if mode == 'backup':
                backup(vault, destination)
            else:
                export_person(vault, person, destination,
                              ExportSelection(mode, (), mode == 'full-person'))
            results[mode] = 'published'
        except ArchiveError as error:
            results[mode] = error.code
    return results


def test_real_unreadable_subtree_preserves_history_sources_and_blocks_outputs(tmp_path):
    from test_archive import update_payload, rebind_proposal
    assert os.geteuid() != 0, 'Real denial qualification must run as a nonroot user'
    vault = init_vault(tmp_path/'v')
    person = add_person(vault, PersonDraft('Enumeration Synthetic'))
    # Storage-protocol fixture: retain an exact source blob in a verified change.
    # This is not a clinical-import or medical-review qualification.
    payload = tmp_path/'prepared'
    base = update_payload(vault, person, payload)
    source_bytes = b'{"value":0.050,"unit":"mg/L","original":"synthetic"}\n'
    digest = hash_bytes(source_bytes)
    source = vault.root/f'people/{person}/assets/sha256/{digest}/blob'
    source.parent.mkdir(parents=True); source.write_bytes(source_bytes)
    proposal = decode_json((payload/'proposal.json').read_bytes())
    proposal['assets'] = [dict(sha256=digest, size=len(source_bytes),
                              mediaType='text/plain', path=f'assets/sha256/{digest}/blob')]
    rebind_proposal(payload, proposal)
    _publish_change(vault, person, payload, base)
    baseline = doctor(vault)
    assert not baseline.issues and baseline.checkedChanges == 2
    assert baseline.checkedResources == 2 and baseline.checkedAssets == 1
    original_head = head(vault, person)
    original_files = {p.relative_to(vault.root):p.read_bytes()
                      for p in (vault.root/'people').rglob('*') if p.is_file()}
    directory = vault.root/'unknown-private'; directory.mkdir()
    private = directory/'private.txt'; private_bytes = b'Unaccepted private source, preserve exactly\n'
    private.write_bytes(private_bytes)
    directory.chmod(0)
    try:
        with pytest.raises(PermissionError):
            list(directory.iterdir())  # Active witness; chmod alone is not proof.
        report = doctor(vault)
        results = output_results(vault, person, tmp_path)
    finally:
        directory.chmod(0o700)  # Restore the test's access, never remove the material.
    assert head(vault, person) == original_head
    assert source.read_bytes() == source_bytes and private.read_bytes() == private_bytes
    assert all((vault.root/p).read_bytes() == data for p, data in original_files.items())
    assert (report.checkedChanges, report.checkedResources, report.checkedAssets) == (2, 2, 1)
    assert any(i.code == 'IO_ERROR' and i.pointer == 'unknown-private' and
               'Preserve' in i.message for i in report.issues)
    assert results == dict.fromkeys(('backup', 'full-person', 'selected-current'), 'INTEGRITY')
    assert all(not (tmp_path/mode).exists() for mode in results)


@pytest.mark.parametrize('operation,number', [('classify-directory', errno.EIO), ('enumerate', errno.EIO),
    ('enumerate-no-filename', errno.EIO), ('enumerate-external-filename', errno.EIO),
    ('stat-file', errno.EACCES), ('stat-directory', errno.EIO)])
def test_audit_read_failures_have_relative_paths_and_block_outputs(tmp_path, monkeypatch, operation, number):
    vault = init_vault(tmp_path/'v')
    person = add_person(vault, PersonDraft('Enumeration Synthetic'))
    original_head = head(vault, person)
    relative = f'people/{person}/unknown-private'
    target = vault.root/relative
    if operation == 'stat-file':
        target.write_bytes(b'preserve file')
    else:
        target.mkdir(); (target/'private.txt').write_bytes(b'preserve subtree')
    hits = []
    with monkeypatch.context() as patch:
        if operation == 'classify-directory':
            original = os.scandir
            class Entry:
                def __init__(self, entry):
                    self.entry = entry
                def __getattr__(self, name):
                    return getattr(self.entry, name)
                def is_dir(self, *args, **kwargs):
                    hits.append(True)
                    raise OSError(number, 'injected entry classification failure', str(target))
            class Entries:
                def __init__(self, path):
                    self.stream = original(path)
                def __enter__(self):
                    self.stream.__enter__()
                    return self
                def __exit__(self, *args):
                    return self.stream.__exit__(*args)
                def __iter__(self):
                    return self
                def __next__(self):
                    entry = next(self.stream)
                    return Entry(entry) if Path(entry.path) == target else entry
            def denied(path):
                if isinstance(path, (str, os.PathLike)) and Path(path) == target.parent:
                    return Entries(path)
                return original(path)
            patch.setattr(os, 'scandir', denied)
        elif operation.startswith('enumerate'):
            original = os.scandir
            def denied(path):
                if isinstance(path, (str, os.PathLike)) and Path(path) == target:
                    hits.append(True)
                    filename = (None if operation == 'enumerate-no-filename' else
                                str(tmp_path/'outside-private') if operation == 'enumerate-external-filename' else str(target))
                    raise OSError(number, 'injected enumeration failure', filename)
                return original(path)
            patch.setattr(os, 'scandir', denied)
        else:
            original = Path.stat
            def denied(path, *args, **kwargs):
                if path == target:
                    hits.append(True)
                    raise OSError(number, 'injected stat failure', str(target))
                return original(path, *args, **kwargs)
            patch.setattr(Path, 'stat', denied)
        report = doctor(vault)
        results = output_results(vault, person, tmp_path)
    assert hits and head(vault, person) == original_head
    assert (target if operation == 'stat-file' else target/'private.txt').read_bytes().startswith(b'preserve')
    assert (report.checkedChanges, report.checkedResources) == (1, 1)
    expected = '.' if operation in ('enumerate-no-filename', 'enumerate-external-filename') else relative
    assert any(i.code == 'IO_ERROR' and i.pointer == expected and 'Preserve' in i.message
               for i in report.issues)
    assert all('outside-private' not in (i.pointer or '') for i in report.issues)
    assert results == dict.fromkeys(('backup', 'full-person', 'selected-current'), 'INTEGRITY')
    assert all(not (tmp_path/mode).exists() for mode in results)
