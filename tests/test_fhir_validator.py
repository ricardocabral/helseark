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


def test_validation_api_required_policy_blocks_without_java():
    from helseark.validation import validate_proposal
    with pytest.raises(ArchiveError,match='VALIDATOR_UNAVAILABLE'):
        validate_proposal(None,Path('/absent'),requireOfficial=True)


def test_cli_required_policy_has_missing_tool_exit6(capsys):
    from helseark.cli import main
    assert main(['validate','proposal','/absent','--person','11111111-1111-4111-8111-111111111111','--require-official'])==6


def test_shared_mapping_preserves_historical_child_and_clinical_bytes(tmp_path):
    from copy import deepcopy
    from uuid import uuid4
    from helseark.archive import init_vault,add_person,head,resolve
    from helseark.contracts import PersonDraft,ResourceRef
    from helseark.portability import fhir_collection
    from helseark.validation import _walk
    vault=init_vault(tmp_path/'vault');person=add_person(vault,PersonDraft('Synthetic mapping person'))
    base=head(vault,person)
    patient=resolve(vault,person,ResourceRef('Patient',person))
    logical,old,new,parent=[str(uuid4()) for _ in range(4)]
    profile='https://github.com/ricardocabral/helseark/fhir/StructureDefinition/helseark-'
    child={'resourceType':'Observation','id':logical,'meta':{'versionId':old,'profile':[profile+'observation|0.1.0']},
           'status':'final','code':{'text':'Synthetic'},'subject':{'reference':'Patient/'+person},'valueString':'old exact value'}
    revised=deepcopy(child);revised['meta']['versionId']=new;revised['valueString']='new exact value'
    report={'resourceType':'DiagnosticReport','id':parent,'meta':{'versionId':str(uuid4()),'profile':[profile+'diagnostic-report|0.1.0']},
            'status':'final','code':{'text':'Synthetic parent'},'subject':{'reference':'Patient/'+person},
            'result':[{'reference':f'Observation/{logical}/_history/{old}'}]}
    originals=(child,revised,report)
    before=encode_json(list(originals))
    bundle,mapping=fhir_collection(vault,person,at=base,proposedResources=originals)
    assert len(bundle['entry'])==4
    assert {item['versionId'] for item in mapping if item['id']==logical}=={old,new}
    parent_entry=next(e['resource'] for e in bundle['entry'] if e['resource']['id']==parent)
    assert parent_entry['result'][0]['reference']=='urn:uuid:'+old
    assert parent_entry['subject']['reference']=='urn:uuid:'+patient['meta']['versionId']
    for entry,item in zip(bundle['entry'],mapping):
        resource=deepcopy(entry['resource']);reverse={v:k for k,v in item['references'].items()}
        for _,node in _walk(resource):
            if isinstance(node,dict) and 'reference' in node:node['reference']=reverse[node['reference']]
        original=patient if item['resourceType']=='Patient' else next(r for r in originals if r['meta']['versionId']==item['versionId'])
        assert encode_json(resource)==encode_json(original)
    assert encode_json(list(originals))==before
    assert head(vault,person)==base


def test_new_genesis_declares_profile_without_altering_old_history(tmp_path):
    from helseark.archive import init_vault,add_person,resolve
    from helseark.contracts import PersonDraft,ResourceRef
    vault=init_vault(tmp_path/'vault');person=add_person(vault,PersonDraft('Synthetic profile genesis'))
    patient=resolve(vault,person,ResourceRef('Patient',person))
    assert patient['meta']['profile']==['https://github.com/ricardocabral/helseark/fhir/StructureDefinition/helseark-patient|0.1.0']


def test_machine_locations_map_to_original_revision_and_json_pointer():
    mapping=[{'resourceType':'Observation','id':'11111111-1111-4111-8111-111111111111','versionId':'22222222-2222-4222-8222-222222222222'}]
    raw=encode_json({'resourceType':'OperationOutcome','issue':[{'severity':'error','code':'invariant',
        'expression':['Bundle.entry[0].resource/*Observation/11111111-1111-4111-8111-111111111111*/.valueQuantity.value']}]})
    issues,counts=tool._outcome(raw,1,mapping)
    assert issues[0].pointer=='/valueQuantity/value'
    assert issues[0].resourceRef=='Observation/11111111-1111-4111-8111-111111111111/_history/22222222-2222-4222-8222-222222222222'


def test_old_reports_preserve_their_original_serialized_shape():
    from helseark.contracts import ValidationReport,CheckCoverage
    from helseark.agent_context import document
    report=ValidationReport(None,(CheckCoverage('full-fhir','not-checked','No tool executed.'),),())
    assert document(report)=={'checkedProposalSha256':None,'coverage':[{'family':'full-fhir','result':'not-checked','reason':'No tool executed.'}],'issues':[]}


def test_process_exit_without_machine_outcome_blocks(tmp_path,monkeypatch):
    monkeypatch.setattr(tool,'_artifacts',lambda *a:tool._lock())
    monkeypatch.setattr(tool,'_profiles',lambda *a:[])
    monkeypatch.setattr(tool.subprocess,'run',lambda *a,**k:subprocess.CompletedProcess(a[0],7))
    with pytest.raises(ArchiveError,match='VALIDATOR_PROCESS_FAILED'):
        tool._run_bundle(None,{'resourceType':'Bundle','entry':[]},[],config(tmp_path))


@pytest.fixture(autouse=True)
def prohibit_python_network(monkeypatch):
    import socket
    import ssl  # initialize SSLSocket before replacing its socket base class
    def denied(*args,**kwargs):raise AssertionError('Runtime Python network attempt')
    monkeypatch.setattr(socket,'socket',denied)
    monkeypatch.setattr(socket,'create_connection',denied)
