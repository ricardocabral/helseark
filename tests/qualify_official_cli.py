"""Installed-wheel real CLI + review drill; synthetic fixtures only."""
import argparse
from dataclasses import replace
from pathlib import Path
import subprocess
import sys

from helseark import fhir_validator as tool
from helseark.contracts import ValidatorConfig
from helseark.serialization import encode_json,decode_json,hash_bytes
from helseark.review import read_prepared
from helseark.archive import commit_candidate,open_vault,doctor
from test_intake import supplied_candidate
from test_review import prepare,approve
from qualify_official_validator import record_installed_runtime


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--wheel',type=Path,required=True)
    parser.add_argument('--artifacts',type=Path,required=True)
    parser.add_argument('--java',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--timeout-seconds',type=int,default=120)
    parser.add_argument('--reuse-workflow',type=Path)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    record_installed_runtime(args.wheel,args.output)
    if args.reuse_workflow:
        vault=open_vault(args.reuse_workflow/'vault')
        proposal_path=next((vault.root/'work/proposals').glob('*/proposal.json')).parent
        proposal=read_prepared(vault,proposal_path)
        person=proposal.personId
    else:
        vault,person,source,packet,candidate=supplied_candidate(args.output/'workflow')
        proposal=prepare(vault,candidate)
    before={p:p.read_bytes() for p in (vault.root/'people').rglob('*') if p.is_file()}
    lock=tool._lock()
    config=ValidatorConfig(args.artifacts/'validator_cli.jar',lock['executableSha256'],lock['version'],
                           args.artifacts/'packages',vault.root/'definitions/profiles/r4',args.timeout_seconds,False,args.java)
    from helseark.agent_context import document
    path=args.output/'config.json';path.write_bytes(encode_json(document(config)))
    command=[sys.executable,'-m','helseark.cli','--vault',str(vault.root),'validate','proposal',str(proposal.path),
             '--person',person,'--require-official','--official-config',str(path),'--json']
    result=subprocess.run(command,capture_output=True)
    (args.output/'cli-stdout.json').write_bytes(result.stdout)
    (args.output/'cli-stderr.txt').write_bytes(result.stderr)
    assert result.returncode in (0,3),(result.returncode,result.stderr)
    assert b'UNSELECTED SECRET' not in result.stdout
    report=decode_json(result.stdout)
    assert next(c['result'] for c in report['coverage'] if c['family']=='full-fhir')=='passed'
    assert next(c['result'] for c in report['coverage'] if c['family']=='terminology')=='not-checked'
    assert all(p.read_bytes()==data for p,data in before.items())
    prepared=read_prepared(vault,proposal.path)
    # Exercise the real public CLI failure after genuine success. It must revoke
    # pending authority; a later real execution is required before acceptance.
    empty=args.output/'empty-packages';empty.mkdir()
    missing=replace(config,packageDirectory=empty)
    missing_path=args.output/'missing-config.json'
    missing_path.write_bytes(encode_json(document(missing)))
    negative_command=command.copy()
    negative_command[negative_command.index(str(path))]=str(missing_path)
    negative=subprocess.run(negative_command,capture_output=True)
    (args.output/'missing-artifact-stdout.txt').write_bytes(negative.stdout)
    (args.output/'missing-artifact-stderr.txt').write_bytes(negative.stderr)
    assert negative.returncode==5,(negative.returncode,negative.stderr)
    assert decode_json(negative.stderr)['code']=='VALIDATOR_RUNTIME_CHANGED'
    # The original stale six-profile root must still fail for current vaults.
    missing_path.write_bytes(encode_json(document(replace(config,
        profileDirectory=vault.root/'definitions/profiles/r4/0.1.0'))))
    missing_profile=subprocess.run(negative_command,capture_output=True)
    (args.output/'missing-profile-stdout.txt').write_bytes(missing_profile.stdout)
    (args.output/'missing-profile-stderr.txt').write_bytes(missing_profile.stderr)
    assert missing_profile.returncode==6,(missing_profile.returncode,missing_profile.stderr)
    assert decode_json(missing_profile.stderr)['code']=='VALIDATOR_MISSING_ARTIFACT'
    assert all(p.read_bytes()==data for p,data in before.items())
    recovery=subprocess.run(command,capture_output=True)
    (args.output/'recovery-stdout.json').write_bytes(recovery.stdout)
    (args.output/'recovery-stderr.txt').write_bytes(recovery.stderr)
    assert recovery.returncode in (0,3),(recovery.returncode,recovery.stderr)
    recovered=decode_json(recovery.stdout)
    assert recovered['officialRun']['counts']==report['officialRun']['counts']
    prepared=read_prepared(vault,proposal.path)
    receipt=approve(vault,prepared)
    committed=commit_candidate(vault,prepared,receipt)
    assert committed.disposition=='committed'
    assert not doctor(open_vault(vault.root)).issues
    assert all(p.read_bytes()==data for p,data in before.items())
    print('installed actual CLI:',report['officialRun']['resourceCount'],'resources;',report['officialRun']['counts'],
          '; source/accepted bytes unchanged; review/commit/reopen passed; module',tool.__file__)


if __name__=='__main__': main()
