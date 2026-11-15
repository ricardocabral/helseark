"""Coverage reconciliation is independent of trusting a complete tool report.

These datatype checks assert reconciliation, never fake tool conformance.
Real Java/public workflow and mutation probes run in qualify_validator_authority.py.
"""
from dataclasses import replace
import pytest
from helseark.contracts import ArchiveError,CheckCoverage,ValidationReport
from helseark import validation


def baseline():
    return ValidationReport('a'*64,tuple(CheckCoverage(f,'not-checked' if f in ('full-fhir','terminology','extraction-accuracy') else 'passed',
        'Human source review required.' if f=='extraction-accuracy' else None) for f in (
        'local-envelopes','upstream-json-schema','supported-profile-rules','patient-reference-scope',
        'evidence','source-hashes','time-precision','terminology','full-fhir','extraction-accuracy')),())


def recorded():
    fresh=baseline()
    return replace(fresh,coverage=tuple(c for c in fresh.coverage if c.family not in ('full-fhir','terminology'))+
        (CheckCoverage('full-fhir','passed','Tool result'),CheckCoverage('terminology','not-checked','Disabled')),
        officialRun={'requireTerminology':False})


@pytest.mark.parametrize('mutation',['missing-extraction','missing-all-baseline','duplicate-baseline','duplicate-official','extra-medical','reason','result'])
def test_complete_baseline_coverage_rejected(mutation):
    report=recorded();coverage=list(report.coverage)
    if mutation=='missing-extraction':coverage=[c for c in coverage if c.family!='extraction-accuracy']
    elif mutation=='missing-all-baseline':coverage=[c for c in coverage if c.family in ('full-fhir','terminology')]
    elif mutation=='duplicate-baseline':coverage.append(coverage[0])
    elif mutation=='duplicate-official':coverage.append(coverage[-1])
    elif mutation=='extra-medical':coverage.append(CheckCoverage('medical-diagnosis','passed','Invented claim'))
    elif mutation in ('reason','result'):
        coverage=[replace(c,**({'reason':'Different limitation'} if mutation=='reason' else {'result':'passed'})) if c.family=='extraction-accuracy' else c for c in coverage]
    with pytest.raises(ArchiveError,match='REVIEW_MISMATCH'):
        validation.verify_baseline_reconciliation(baseline(),replace(report,coverage=tuple(coverage)))


def test_supported_substitutions_keep_every_baseline_limitation():
    validation.verify_baseline_reconciliation(baseline(),recorded())


def test_baseline_only_report_still_matches_exact_coverage():
    validation.verify_baseline_reconciliation(baseline(),baseline())
    with pytest.raises(ArchiveError,match='REVIEW_MISMATCH'):
        validation.verify_baseline_reconciliation(baseline(),replace(baseline(),coverage=baseline().coverage[:-1]))


@pytest.mark.parametrize('fake_change',[False,True])
def test_legacy_pending_state_cannot_acquire_trust_from_report_or_path(tmp_path,fake_change):
    from test_intake import supplied_candidate
    from test_review import prepare
    from helseark.review import read_prepared,render_review
    from helseark.serialization import encode_json
    vault,person,_,_,candidate=supplied_candidate(tmp_path)
    prepared=prepare(vault,candidate)
    control=vault.root/f'.runtime/prepared/{prepared.proposalSha256}.json'
    control.write_bytes(encode_json({'candidatePath':str(candidate.path)}))
    if fake_change:(prepared.path/'change.json').write_bytes(encode_json({}))
    with pytest.raises(ArchiveError,match='VALIDATOR_AUTHORITY_REQUIRED'):
        render_review(vault,read_prepared(vault,prepared.path))


@pytest.mark.parametrize('mutation', ['omitted', 'altered', 'duplicated'])
def test_nonempty_baseline_issues_reconcile_exactly(mutation):
    from helseark.contracts import Issue
    issue = Issue('SYNTHETIC_LIMITATION', 'warning', '/valueQuantity/value',
                  'Observation/11111111-1111-4111-8111-111111111111', 'Retain the source limitation.')
    fresh = replace(baseline(), issues=(issue,))
    original = replace(recorded(), issues=(issue,))
    validation.verify_baseline_reconciliation(fresh, original)
    changed = () if mutation == 'omitted' else (replace(issue, message='Altered limitation'),) if mutation == 'altered' else (issue, issue)
    with pytest.raises(ArchiveError, match='REVIEW_MISMATCH'):
        validation.verify_baseline_reconciliation(fresh, replace(original, issues=changed))


@pytest.mark.parametrize('entry', ['adapter', 'api', 'cli', 'invalid-cli'])
def test_failed_request_revokes_even_without_valid_configuration(tmp_path, entry):
    from test_intake import supplied_candidate
    from test_review import prepare
    from helseark import fhir_validator as tool
    from helseark.cli import main
    from helseark.review import render_review
    from helseark.serialization import decode_json, encode_json
    vault, person, _, _, candidate = supplied_candidate(tmp_path)
    prepared = prepare(vault, candidate)
    control = vault.root/f'.runtime/prepared/{prepared.proposalSha256}.json'
    before = control.read_bytes()
    if entry in ('cli', 'invalid-cli'):
        args = ['--vault', str(vault.root), 'validate', 'proposal', str(prepared.path),
                '--person', person, '--require-official', '--json']
        if entry == 'invalid-cli':
            from test_fhir_validator import config
            from helseark.agent_context import document
            bad = tmp_path/'config.json'
            bad.write_bytes(encode_json(document(replace(config(tmp_path), executableSha256='0'*64, requireTerminology=True))))
            args += ['--official-config', str(bad)]
        assert main(args) == (5 if entry == 'invalid-cli' else 6)
    else:
        with pytest.raises(ArchiveError, match='VALIDATOR_UNAVAILABLE'):
            if entry == 'adapter':
                tool.validate_with_official_tool(prepared, None, vault=vault)
            else:
                validation.validate_proposal(vault, prepared.path, requireOfficial=True)
    assert control.read_bytes() != before
    state = decode_json(control.read_bytes())
    assert state['officialExecutionId'] is not None
    assert state['officialRequestSha256'] is None
    with pytest.raises(ArchiveError, match='VALIDATOR_AUTHORITY_'):
        render_review(vault, prepared)


@pytest.mark.parametrize('mutation', ['copy', 'person', 'digest', 'candidate', 'symlink'])
def test_unauthorized_request_cannot_revoke_original(tmp_path, mutation):
    import shutil
    from test_intake import supplied_candidate
    from test_review import prepare
    from helseark import fhir_validator as tool
    from helseark.review import render_review
    vault, person, _, _, candidate = supplied_candidate(tmp_path)
    prepared = prepare(vault, candidate)
    control = vault.root/f'.runtime/prepared/{prepared.proposalSha256}.json'
    before = control.read_bytes()
    changed = prepared
    if mutation == 'copy':
        copy = tmp_path/'untrusted-copy'
        shutil.copytree(prepared.path, copy)
        changed = replace(prepared, path=copy)
    elif mutation == 'symlink':
        link = tmp_path/'untrusted-link'
        link.symlink_to(prepared.path, target_is_directory=True)
        changed = replace(prepared, path=link)
    elif mutation == 'person':
        changed = replace(prepared, personId='11111111-1111-4111-8111-111111111111')
    elif mutation == 'digest':
        changed = replace(prepared, proposalSha256='0'*64)
    else:
        changed = replace(prepared, candidatePath=tmp_path/'unrelated')
    with pytest.raises(ArchiveError):
        tool.validate_with_official_tool(changed, None, vault=vault)
    assert control.read_bytes() == before
    render_review(vault, prepared)


def test_request_does_not_revoke_unrelated_proposal_or_accepted_history(tmp_path):
    from test_intake import supplied_candidate
    from test_review import prepare, approve
    from helseark import fhir_validator as tool
    from helseark.intake import prepare_candidate
    from helseark.archive import commit_candidate
    from helseark.review import render_review, read_prepared
    from helseark.serialization import hash_bytes
    vault, _, _, _, candidate = supplied_candidate(tmp_path)
    first = prepare(vault, candidate)
    second = prepare_candidate(vault, candidate)
    def inventory():
        return {str(p.relative_to(vault.root)): hash_bytes(p.read_bytes()) for p in (vault.root/'people').rglob('*') if p.is_file()}
    before = inventory()
    with pytest.raises(ArchiveError, match='VALIDATOR_UNAVAILABLE'):
        tool.validate_with_official_tool(first, None, vault=vault)
    assert inventory() == before
    render_review(vault, second)
    receipt = approve(vault, second)
    result = commit_candidate(vault, second, receipt)
    accepted = vault.root/f'people/{second.personId}/accepted/{result.head.sequence:08d}-{result.head.transactionId}'
    history = inventory()
    controls = {p: p.read_bytes() for p in (vault.root/'.runtime/prepared').glob('*.json')}
    with pytest.raises(ArchiveError, match='REVIEW_MISMATCH'):
        tool.validate_with_official_tool(read_prepared(vault, accepted), None, vault=vault)
    assert inventory() == history
    assert all(p.read_bytes() == data for p, data in controls.items())
    render_review(vault, read_prepared(vault, accepted))


def test_baseline_failure_also_revokes_request_first(tmp_path):
    from test_intake import supplied_candidate
    from test_review import prepare
    from test_fhir_validator import config
    from helseark import fhir_validator as tool
    vault, _, _, _, candidate = supplied_candidate(tmp_path)
    prepared = prepare(vault, candidate)
    control = vault.root/f'.runtime/prepared/{prepared.proposalSha256}.json'
    before = control.read_bytes()
    resource = next((prepared.path/'resources').iterdir())
    resource.write_bytes(resource.read_bytes()+b' ')
    with pytest.raises(ArchiveError, match='VALIDATION_BLOCKED'):
        tool.validate_with_official_tool(prepared, config(tmp_path), vault=vault)
    assert control.read_bytes() != before
