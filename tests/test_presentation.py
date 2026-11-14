"""Static projections of accepted synthetic records; no mocked query/storage."""
import csv
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from helseark import archive
from helseark.contracts import ArchiveError, ObservationFilter, PersonDraft
from helseark.query import observations
from helseark.serialization import encode_json, hash_bytes
from test_query import corpus, clinical_candidate, enrich
from test_agent_context import accept_fixture


def render(*args):
    from helseark.presentation import render_static_report
    return render_static_report(*args)


def files(root):
    return {p.relative_to(root).as_posix(): hash_bytes(p.read_bytes())
            for p in root.rglob('*') if p.is_file() and 'derived' not in p.relative_to(root).parts}


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.tags = []
        self.links = []
        self.text = ''
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.links.extend(v for k, v in attrs if k == 'href')

    def handle_data(self, text):
        self.text += text


def test_exact_rows_sources_context_and_rebuild(corpus, tmp_path):
    vault, candidate, ids, base, _ = corpus
    other = archive.add_person(vault, PersonDraft('OTHER PERSON SECRET'))
    before = files(vault.root)
    destination = vault.root/'derived/reports'/candidate.personId
    index = render(vault, candidate.personId, destination)
    page = Page(index.read_text())
    rows = list(csv.DictReader((destination/'observations.csv').open(newline='')))
    assert len(rows) == 9
    assert '<0.050 mg/L' in page.text
    assert '1.2300 mg/dL' in page.text
    assert 'mmol/L' in page.text
    for value in ('0–1', '2–4', 'hs', 'standard', 'Not performed', 'Negative',
                  'cancelled', 'entered-in-error', 'month', 'unknown', '2.50', '4.00'):
        assert value in page.text
    assert other not in page.text and 'OTHER PERSON SECRET' not in page.text
    assert base.changeSha256 in page.text
    actual = list(observations(vault, candidate.personId, ObservationFilter(includeInvalidated=True)))
    for row in actual:
        output = next(r for r in rows if row.resourceRef.id in r['resourceRef'])
        assert output['value'] == encode_json(row.value).decode().strip()
        assert output['referenceRanges'] == encode_json(row.referenceRanges).decode().strip()
        for source in row.sourceRefs:
            assert any(source.evidencePath in link and source.entryPointer in link for link in page.links)
            if source.sourceSha256:
                assert source.sourceSha256 in page.text
    first = {p.name:p.read_bytes() for p in destination.iterdir()}
    assert files(vault.root) == before
    shutil.rmtree(vault.root/'derived')
    render(vault, candidate.personId, destination)
    assert first == {p.name:p.read_bytes() for p in destination.iterdir()}
    assert files(vault.root) == before
    with pytest.raises(ArchiveError, match='DESTINATION_EXISTS'):
        render(vault, candidate.personId, destination)


@pytest.mark.parametrize('label', ['<script>alert(1)</script><img src=x onerror=alert(2)>',
                                  '=HYPERLINK("https://invalid", "x")', '\t +SUM(1,2)', '@evil', '-1+2'])
def test_hostile_labels_are_inert(clinical_candidate, tmp_path, label):
    vault, candidate = clinical_candidate
    resources = [e for e in candidate.bundle['entry'] if e['resource']['resourceType'] != 'DocumentReference']
    resources[0]['resource']['code'] = {'text':label}
    enrich(vault, candidate, resources)
    accept_fixture(vault, candidate, tmp_path)
    destination = tmp_path/'report'
    index = render(vault, candidate.personId, destination)
    page = Page(index.read_text())
    assert not {'script','img','iframe','object','link'} & set(page.tags)
    assert label in page.text
    rows = list(csv.DictReader((destination/'observations.csv').open(newline='')))
    row = next(r for r in rows if label in r['sourceLabel'])
    assert row['sourceLabel'] == ("'"+label if label.lstrip().startswith(('=','+','-','@')) else label)
    assert all(not cell.lstrip().startswith(('=','+','-','@','\t','\r','\n')) for r in rows for cell in r.values())


def test_protected_destinations_and_symlinks(corpus, tmp_path):
    vault, candidate, *_ = corpus
    before = files(vault.root)
    for target in (vault.root/'people'/candidate.personId/'accepted/report', vault.root/'definitions/report',
                   vault.root/'agent-kit/report', vault.root/'derived/../people/report'):
        with pytest.raises(ArchiveError, match='INVALID_DESTINATION'):
            render(vault, candidate.personId, target)
    (vault.root/'derived').symlink_to(vault.root/'people', target_is_directory=True)
    with pytest.raises(ArchiveError, match='INVALID_DESTINATION'):
        render(vault, candidate.personId, vault.root/'derived/report')
    (vault.root/'derived').unlink()
    assert files(vault.root) == before


def test_cli_empty_person_and_explicit_export(tmp_path):
    vault = archive.init_vault(tmp_path/'vault')
    person = archive.add_person(vault, PersonDraft('Synthetic empty'))
    output = tmp_path/'export'
    result = subprocess.run([sys.executable, '-m', 'helseark.cli', '--vault', str(vault.root),
                             'report', '--person', person, '--out', str(output), '--json'], capture_output=True)
    assert result.returncode == 0, result.stderr
    assert (output/'index.html').exists()
    assert '0 observations' in (output/'index.html').read_text()
    assert len(list(csv.DictReader((output/'observations.csv').open()))) == 0
