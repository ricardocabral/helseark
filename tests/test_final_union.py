"""Cross-feature integration contracts; synthetic decisions do not measure models."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

from helseark.agent_context import list_agent_tasks
from helseark.intake import prepare_candidate
from helseark.serialization import decode_json, hash_bytes


def test_all_feature_discovery_retains_implemented_export(tmp_path):
    from helseark.archive import init_vault
    vault = init_vault(tmp_path/'vault')
    kit = vault.root/'agent-kit'/vault.config.agentKitVersion
    tasks = list_agent_tasks(kit)
    assert len(tasks) == 7 and all(t.availability.status == 'available' for t in tasks)
    assert 'reviewed-source-disclosure' in next(t for t in tasks if t.id == 'export').requiredCapabilities
    from helseark.archive import add_person
    from helseark.contracts import PersonDraft, ContextRequest
    from helseark.agent_context import build_agent_context, render_task_prompt
    person = add_person(vault, PersonDraft('Synthetic export assessment'))
    context = build_agent_context(vault, person, 'export', ContextRequest(), tmp_path/'context')
    rendered = render_task_prompt(context, 'prepare-export',
        {'source_data':{'mode':'full-person','selection':[],'omissions':[]},
         'source_scope_confirmed':True,'output_directory':str(tmp_path/'output')},
        trusted_context_sha256=context.trustedContextSha256)
    import json
    header = json.JSONDecoder().raw_decode(rendered.text.split('\n',1)[1])[0]
    assert header['disposition'] == 'draft' and not header['stopReasons']
    assert header['permittedWrites'] == ['output/report.md']


def test_host_review_inputs_reject_streams_and_oversize_without_publication(tmp_path):
    from test_intake import supplied_candidate
    vault, person, source, packet, candidate = supplied_candidate(tmp_path)
    proposal = prepare_candidate(vault, candidate)
    before = {p.relative_to(vault.root):hash_bytes(p.read_bytes())
              for p in (vault.root/'people').rglob('*') if p.is_file()}
    fifo = tmp_path/'control.fifo'
    os.mkfifo(fifo)
    oversized = tmp_path/'oversize.json'
    with oversized.open('wb') as stream:
        stream.truncate(64 * 1024 * 1024 + 1)
    for verb, target, option in [('prepare', candidate.path, '--reconciliation'),
                                  ('review', proposal.path, '--decision')]:
        for control, expected in [(fifo, 'UNSAFE_PATH'), (oversized, 'SOURCE_TOO_LARGE')]:
            result = subprocess.run([sys.executable, '-m', 'helseark.cli', '--vault', str(vault.root),
                'candidate', verb, str(target), '--person', person, option, str(control), '--json'],
                capture_output=True, timeout=10)
            assert result.returncode in (2, 5)
            assert decode_json(result.stderr)['code'] == expected
    assert not (proposal.path/'review.json').exists()
    assert before == {p.relative_to(vault.root):hash_bytes(p.read_bytes())
                      for p in (vault.root/'people').rglob('*') if p.is_file()}


def test_official_profiles_cover_current_and_retained_sets(tmp_path):
    from dataclasses import replace
    from helseark.archive import init_vault
    from helseark.contracts import ArchiveError
    from helseark.fhir_validator import _profiles, _lock
    from helseark.contracts import ValidatorConfig
    vault = init_vault(tmp_path/'vault')
    config = ValidatorConfig(tmp_path/'absent.jar', _lock()['executableSha256'], '7.0.5',
        tmp_path/'packages', vault.root/'definitions/profiles/r4', 120, False, tmp_path/'java')
    destination = tmp_path/'current-profiles'; destination.mkdir()
    pins = _profiles(vault, config, destination)
    assert len(pins) == len(list(destination.glob('*.json'))) == 15
    for pin in pins:
        assert hash_bytes((vault.root/'definitions'/pin['path']).read_bytes()) == pin['sha256']
    retained = replace(vault, config=replace(vault.config, profileVersion='0.1.0'))
    old = tmp_path/'old-profiles'; old.mkdir()
    assert len(_profiles(retained, replace(config, profileDirectory=config.profileDirectory/'0.1.0'), old)) == 6
    with pytest.raises(ArchiveError, match='VALIDATOR_MISSING_ARTIFACT'):
        _profiles(vault, replace(config, profileDirectory=config.profileDirectory/'0.1.0'), tmp_path)
