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
