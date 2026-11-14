"""Process fakes cover failures only. Real conformance is a separate offline drill."""
from dataclasses import replace
from pathlib import Path
import json
import subprocess

import pytest
from helseark.contracts import ArchiveError, ValidatorConfig
from helseark.serialization import encode_json
from helseark import fhir_validator as tool

ROOT = Path(__file__).resolve().parents[1]


def config(tmp_path):
    return ValidatorConfig(tmp_path/'missing.jar', tool._lock()['executableSha256'], '7.0.5',
                           tmp_path/'packages', ROOT/'profiles/r4/0.1.0',120,False,tmp_path/'java')


def test_explicit_required_tool_absent_blocks():
    with pytest.raises(ArchiveError, match='VALIDATOR_UNAVAILABLE'):
        tool.validate_with_official_tool(None, None, vault=None)


def test_wrong_digest_blocks_before_execution(tmp_path):
    jar=tmp_path/'wrong.jar';jar.write_bytes(b'not official')
    with pytest.raises(ArchiveError,match='VALIDATOR_DIGEST_MISMATCH'):
        tool._artifacts(replace(config(tmp_path),executablePath=jar),tmp_path/'home')


def test_unrelated_empty_cache_is_not_a_package_closure(tmp_path,monkeypatch):
    jar=tmp_path/'jar';jar.write_bytes(b'process failure fixture')
    pin=tool._lock();pin['executableSha256']=tool.hash_bytes(jar.read_bytes())
    monkeypatch.setattr(tool,'_lock',lambda:pin)
    java=tmp_path/'java';java.write_text('#!/bin/sh\nexit 1\n');java.chmod(0o700)
    packages=tmp_path/'packages';packages.mkdir()
    with pytest.raises(ArchiveError,match='VALIDATOR_MISSING_ARTIFACT'):
        tool._artifacts(replace(config(tmp_path),executablePath=jar,executableSha256=pin['executableSha256']),tmp_path/'home')


@pytest.mark.parametrize('data,code,expected',[
    (b'not JSON',1,'VALIDATOR_MALFORMED_OUTPUT'),
    (encode_json({'resourceType':'Patient'}),0,'VALIDATOR_MALFORMED_OUTPUT'),
    (encode_json({'resourceType':'OperationOutcome','issue':[]}),0,'VALIDATOR_MALFORMED_OUTPUT'),
    (encode_json({'resourceType':'OperationOutcome','issue':[{'severity':'alien','code':'invalid'}]}),0,'VALIDATOR_MALFORMED_OUTPUT'),
    (encode_json({'resourceType':'OperationOutcome','issue':[{'severity':'warning','code':'invalid'}]}),7,'VALIDATOR_PROCESS_FAILED'),
    (encode_json({'resourceType':'OperationOutcome','issue':[{'severity':'error','code':'invalid'}]}),0,'VALIDATOR_PROCESS_FAILED'),
])
def test_process_output_failures_are_typed(data,code,expected):
    with pytest.raises(ArchiveError,match=expected): tool._outcome(data,code)


def test_process_timeout_is_typed_without_diagnostics(tmp_path,monkeypatch):
    monkeypatch.setattr(tool,'_artifacts',lambda *a:tool._lock())
    monkeypatch.setattr(tool,'_profiles',lambda *a:[])
    def timeout(*a,**k): raise subprocess.TimeoutExpired('private',120,output='private patient text')
    monkeypatch.setattr(tool.subprocess,'run',timeout)
    with pytest.raises(ArchiveError,match='VALIDATOR_TIMEOUT') as error:
        tool._run_bundle(None,{'resourceType':'Bundle','entry':[]},[],config(tmp_path))
    assert 'private' not in str(error.value)


def test_launch_error_is_typed(tmp_path,monkeypatch):
    monkeypatch.setattr(tool,'_artifacts',lambda *a:tool._lock())
    monkeypatch.setattr(tool,'_profiles',lambda *a:[])
    def fail(*a,**k): raise OSError('private path')
    monkeypatch.setattr(tool.subprocess,'run',fail)
    with pytest.raises(ArchiveError,match='VALIDATOR_UNAVAILABLE'):
        tool._run_bundle(None,{'resourceType':'Bundle','entry':[]},[],config(tmp_path))


def test_safe_issues_and_explicit_counts():
    issues,counts=tool._outcome(encode_json({'resourceType':'OperationOutcome','issue':[
        {'severity':'error','code':'invariant','diagnostics':'private clinical text','expression':['Patient.contact[0]']},
        {'severity':'warning','code':'informational'}]}),1)
    assert counts=={'errors':1,'warnings':1,'information':0}
    assert issues[0].pointer is None and 'private clinical text' not in issues[0].message


def test_baseline_without_java_and_remote_reference_block(tmp_path):
    from test_intake import supplied_candidate
    from test_review import prepare
    from helseark.validation import validate_proposal
    from helseark.intake import read_candidate
    vault,person,source,packet,candidate=supplied_candidate(tmp_path)
    prepared=prepare(vault,candidate)
    report=validate_proposal(vault,prepared.path)
    assert not any(i.severity=='error' for i in report.issues)
    assert next(c for c in report.coverage if c.family=='full-fhir').result=='not-checked'
    candidate.bundle['entry'][0]['resource']['subject']={'reference':'https://unreachable.invalid/Patient/private'}
    (candidate.path/'bundle.json').write_bytes(encode_json(candidate.bundle))
    with pytest.raises(ArchiveError): prepare(vault,read_candidate(vault,candidate.path))


@pytest.mark.parametrize('change',[
    {'timeoutSeconds':True},{'timeoutSeconds':0},{'timeoutSeconds':601},
    {'executablePath':'relative.jar'},{'requireTerminology':'false'}, {'unexpected':True}])
def test_host_configuration_is_strict(tmp_path,change):
    from dataclasses import asdict
    value={k:str(v) if isinstance(v,Path) else v for k,v in asdict(config(tmp_path)).items()}
    value.update(change)
    path=tmp_path/'config.json';path.write_bytes(encode_json(value))
    with pytest.raises(ArchiveError,match='INVALID_INPUT'): tool.load_validator_config(path)
