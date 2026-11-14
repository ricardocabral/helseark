"""Execute reader material against public boundaries; synthetic data only."""
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote

import pytest

from helseark.serialization import decode_json, hash_bytes

ROOT = Path(__file__).resolve().parents[1]


def python_block(path):
    return path.read_text().split('```python\n', 1)[1].split('```', 1)[0]


def cli(*args, expected=0):
    result = subprocess.run([sys.executable, '-m', 'helseark.cli', *map(str, args), '--json'],
                            capture_output=True)
    assert result.returncode == expected, result.stderr + result.stdout
    return decode_json(result.stdout if result.stdout else result.stderr)


@pytest.fixture(scope='module')
def lesson(tmp_path_factory):
    work = tmp_path_factory.mktemp('documented-lesson')
    result = subprocess.run([sys.executable, '-c', python_block(ROOT/'docs/tutorials/first-archive.md')],
        cwd=work, env={**os.environ, 'PYTHONPATH': str(ROOT/'src')},
        capture_output=True, text=True, input='SYNTHETIC\n')
    assert result.returncode == 0, result.stderr + result.stdout[-1500:]
    assert 'Accepted 2 synthetic observations' in result.stdout
    return work


def test_first_archive_tutorial_from_clean_directory(lesson):
    assert len(list((lesson/'lesson-vault/people').glob('*/accepted/*/change.json'))) == 2
    assert check_links(lesson/'lesson-restored/definitions/docs') > 40
    config = decode_json((lesson/'lesson-restored/vault.json').read_bytes())
    assert check_links(lesson/'lesson-restored/agent-kit'/config['agentKitVersion']) > 40
    vault = lesson/'lesson-restored'
    person = next((vault/'people').iterdir()).name
    rows = cli('--vault', vault, 'observations', '--person', person)
    assert len(rows) == 2
    assert str(next(r for r in rows if r['code']['text']=='Analyte Q')['value']['value']) == '0.050'
    assert all(r['sourceRefs'] and r['resourceRef']['versionId'] for r in rows)


def test_documented_family_export_errors_and_recovery(lesson):
    vault = lesson/'lesson-restored'
    person = next((vault/'people').iterdir()).name
    before = {p.relative_to(vault): hash_bytes(p.read_bytes()) for p in (vault/'people'/person).rglob('*') if p.is_file()}
    other = cli('--vault', vault, 'person', 'add', '--name', 'Avery Synthetic')['personId']
    assert person != other
    assert cli('--vault', vault, 'observations', '--person', other) == []
    row = cli('--vault', vault, 'observations', '--person', person)[0]
    ref = row['resourceRef']
    code = cli('--vault', vault, 'record', '--person', other,
               '--resource', ref['resourceType']+'/'+ref['id'], expected=2)['code']
    assert code == 'RESOURCE_NOT_FOUND'
    blocked = lesson/'pdf-person-export'
    assert cli('--vault', vault, 'export', '--person', person, '--out', blocked, expected=3)['code'] == 'SOURCE_SCOPE_REVIEW_REQUIRED'
    assert not blocked.exists()
    selected = lesson/'selected-clinical'
    cli('--vault', vault, 'export', '--person', person, '--out', selected,
        '--mode', 'selected-current', '--no-sources')
    assert not cli('backup', 'verify', selected)['issues']
    assert cli('backup', 'restore', lesson/'lesson-backup', '--into', vault, expected=2)['code'] == 'DESTINATION_EXISTS'
    assert cli('--vault', vault, 'agent', 'context', '--task', 'query', '--person', person,
               '--out', lesson/'over-budget', '--max-data-bytes', '1', expected=2)['code'] == 'CONTEXT_BUDGET_EXCEEDED'
    assert cli('--vault', vault, 'observations', '--person', 'not-a-uuid', expected=2)['code'] == 'INVALID_ID'
    assert before == {p.relative_to(vault): hash_bytes(p.read_bytes()) for p in (vault/'people'/person).rglob('*') if p.is_file()}
    # Both histories survive household recovery; same display name never chooses scope.
    backup = lesson/'two-person-backup'
    cli('--vault', vault, 'backup', 'create', '--out', backup)
    assert len(decode_json((backup/'export.json').read_bytes())['people']) == 2


def test_python_reference_example(tmp_path):
    result = subprocess.run([sys.executable, '-c', python_block(ROOT/'docs/reference/python-api.md')],
        cwd=tmp_path, env={**os.environ, 'PYTHONPATH': str(ROOT/'src')}, capture_output=True)
    assert result.returncode == 0, result.stderr


def check_links(root):
    """Check real local targets and GitHub-style heading fragments, offline."""
    count = 0
    for page in ([root] if root.is_file() else sorted(root.rglob('*.md'))):
        if 'internal' in page.relative_to(root.parent if root.is_file() else root).parts:
            continue
        for target in re.findall(r'\]\(([^)]+)\)', page.read_text()):
            if '://' in target or target.startswith(('mailto:', '#')):
                if not target.startswith('#'):
                    continue
            path, _, fragment = unquote(target).partition('#')
            linked = (page.parent/path).resolve() if path else page
            assert linked.exists(), (page, target)
            if fragment and linked.is_file() and linked.suffix == '.md':
                seen = {}
                anchors = []
                for heading in re.findall(r'^#{1,6}\s+(.+)$', linked.read_text(), re.M):
                    slug = re.sub(r'[^\w\- ]', '', heading.replace('`', '').lower()).replace(' ', '-')
                    n = seen.get(slug, 0); seen[slug] = n+1
                    anchors.append(slug if n == 0 else f'{slug}-{n}')
                assert fragment in anchors, (page, target, anchors)
            count += 1
    return count


def test_source_and_pinned_kit_links_and_complete_copies():
    assert check_links(ROOT/'README.md') >= 5
    assert check_links(ROOT/'docs') > 40
    assert check_links(ROOT/'agent-kit') > 40
    for page in [ROOT/'docs/index.md', *(p for d in ('tutorials','how-to','reference','explanation') for p in (ROOT/'docs'/d).glob('*.md'))]:
        assert page.read_bytes() == (ROOT/'agent-kit'/page.relative_to(ROOT)).read_bytes()
    manifest = decode_json((ROOT/'agent-kit/manifest.json').read_bytes())
    for entry in manifest['files']:
        data = (ROOT/'agent-kit'/entry['path']).read_bytes()
        assert hash_bytes(data) == entry['sha256'] and len(data) == entry['size']


def test_shipped_native_candidate_and_contract_examples(lesson):
    # Binding/validation runs the supplied complete Bundle and evidence, not copied prompt output.
    vault = lesson/'lesson-vault'
    person = decode_json((lesson/'lesson-packet/intake.json').read_bytes())['personId']
    from helseark.archive import open_vault
    from helseark.validation import load_definition_registry
    registry = load_definition_registry(open_vault(vault))
    for path, name in [('lesson-candidate/candidate.json', 'candidate'),
                       ('lesson-candidate/evidence.json', 'evidence')]:
        value = decode_json((lesson/path).read_bytes())
        assert registry.validate('urn:helseark:schema:0.1.0:'+name, value)
    assert len(cli('--vault', vault, 'observations', '--person', person)) == 2
