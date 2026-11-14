"""Real CLI/filesystem races; injected at runtime audit boundaries, not fake I/O."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from helseark import archive
from helseark.contracts import PersonDraft


GUARD = '''
import os, sys
from pathlib import Path
armed = True
def audit(event, args):
    global armed
    action = os.environ['RACE_ACTION']
    trigger = (event == 'ctypes.dlsym' and args[1] in ('renameatx_np', 'renameat2')) if action.endswith('_late') else (event == 'os.mkdir' and str(args[0]).startswith('.helseark-report-'))
    if armed and trigger:
        armed = False
        parent = Path(os.environ['RACE_PARENT'])
        protected = Path(os.environ['RACE_PROTECTED'])
        action = action.removesuffix('_late')
        if action.startswith('compete'):
            target = parent / 'report'
            target.mkdir()
            (target / 'sentinel').write_bytes(b'competitor')
        else:
            parent.rename(protected / 'relocated' if action == 'relocate' else parent.with_name('original'))
            if action == 'replace':
                parent.mkdir()
            else:
                parent.symlink_to(protected, target_is_directory=True)
        print('ACTUAL_PARENT_MUTATION:' + action, file=sys.stderr)
sys.addaudithook(audit)
'''


def inventory(root):
    return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.fixture(scope='module')
def empty_vault(tmp_path_factory):
    root = tmp_path_factory.mktemp('report-authority')
    vault = archive.init_vault(root/'vault')
    person = archive.add_person(vault, PersonDraft('Synthetic authority'))
    return vault, person


@pytest.mark.parametrize('action', ['redirect', 'replace', 'relocate', 'compete', 'redirect_late', 'replace_late', 'relocate_late', 'compete_late'])
def test_installed_style_cli_parent_races(empty_vault, tmp_path, action):
    original_vault, person = empty_vault
    shutil.copytree(original_vault.root, tmp_path/'vault')
    vault = archive.open_vault(tmp_path/'vault')
    parent = tmp_path/'parent'
    parent.mkdir()
    protected = vault.root/'people'/person/'accepted'
    before = inventory(protected)
    guard = tmp_path/'guard'
    guard.mkdir()
    (guard/'sitecustomize.py').write_text(GUARD)
    env = {**os.environ, 'PYTHONPATH':os.pathsep.join([str(guard), str(Path(__file__).resolve().parents[1]/'src')]),
           'RACE_PARENT':str(parent), 'RACE_PROTECTED':str(protected), 'RACE_ACTION':action}
    result = subprocess.run([sys.executable, '-m', 'helseark.cli', '--vault', str(vault.root),
                             'report', '--person', person, '--out', str(parent/'report'), '--json'],
                            cwd=tmp_path, env=env, capture_output=True)
    assert b'ACTUAL_PARENT_MUTATION:' in result.stderr
    # Relocation itself moves an empty user directory into accepted; the CLI
    # must add no files there, including during error cleanup.
    assert inventory(protected) == before
    assert result.returncode == 2, (result.stdout, result.stderr)
    error = result.stderr
    assert (b'DESTINATION_EXISTS' if action.startswith('compete') else b'INVALID_DESTINATION') in error
    if action.startswith('compete'):
        assert inventory(parent/'report') == {'sentinel':b'competitor'}
    elif action == 'replace':
        assert list(parent.iterdir()) == []
    original = tmp_path/'original'
    if original.exists():
        assert list(original.iterdir()) == []


@pytest.mark.parametrize('nested', ['nested/deeper/report', 'report'])
def test_valid_external_and_derived_directories(empty_vault, tmp_path, nested):
    from helseark.presentation import render_static_report
    vault, person = empty_vault
    before = inventory(vault.root/'people')
    for destination in (tmp_path/nested, vault.root/'derived'/tmp_path.name/nested):
        index = render_static_report(vault, person, destination)
        assert index.is_file()
        assert set(p.name for p in destination.iterdir()) == {'index.html', 'observations.csv'}
        assert '0 observations' in index.read_text()
    assert inventory(vault.root/'people') == before


@pytest.mark.parametrize('kind', ['direct', 'ancestor', 'dangling'])
def test_symlinks_are_not_directory_authority(empty_vault, tmp_path, kind):
    from helseark.presentation import render_static_report
    from helseark.contracts import ArchiveError
    vault, person = empty_vault
    before = inventory(vault.root/'people')
    link = tmp_path/'link'
    link.symlink_to(vault.root/'people'/person/'accepted' if kind != 'dangling' else tmp_path/'absent', target_is_directory=True)
    with pytest.raises(ArchiveError):
        render_static_report(vault, person, link if kind == 'direct' else link/'nested/report')
    assert inventory(vault.root/'people') == before


def test_partial_write_has_no_public_visibility_and_cleans_stage(empty_vault, tmp_path):
    vault, person = empty_vault
    guard = tmp_path/'guard'
    guard.mkdir()
    output = tmp_path/'report'
    (guard/'sitecustomize.py').write_text('''import os, sys
from pathlib import Path
def audit(event, args):
    if event == 'open' and str(args[0]).endswith('observations.csv') and args[2] & os.O_WRONLY:
        assert not Path(os.environ['REPORT_TARGET']).exists(), 'PARTIAL_PUBLICATION'
        print('PARTIAL_WRITE_WITNESS', file=sys.stderr)
        raise OSError('synthetic disk failure')
sys.addaudithook(audit)
''')
    before = inventory(vault.root/'people')
    env = {**os.environ, 'TMPDIR':str(tmp_path), 'REPORT_TARGET':str(output),
           'PYTHONPATH':os.pathsep.join([str(guard), str(Path(__file__).resolve().parents[1]/'src')])}
    result = subprocess.run([sys.executable, '-m', 'helseark.cli', '--vault', str(vault.root),
                             'report', '--person', person, '--out', str(output), '--json'],
                            cwd=tmp_path, env=env, capture_output=True)
    assert result.returncode == 5 and b'IO_ERROR' in result.stderr
    assert b'PARTIAL_WRITE_WITNESS' in result.stderr
    assert not output.exists() and not list(tmp_path.glob('.helseark-report-*'))
    assert inventory(vault.root/'people') == before


def test_temporary_root_cannot_authorize_canonical_staging(empty_vault, tmp_path):
    vault, person = empty_vault
    protected = vault.root/'people'/person/'accepted'
    before = inventory(protected)
    result = subprocess.run([sys.executable, '-m', 'helseark.cli', '--vault', str(vault.root),
                             'report', '--person', person, '--out', str(tmp_path/'report'), '--json'],
                            env={**os.environ, 'TMPDIR':str(protected),
                                 'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}, capture_output=True)
    assert result.returncode == 2 and b'INVALID_DESTINATION' in result.stderr
    assert inventory(protected) == before
    assert not (tmp_path/'report').exists()
