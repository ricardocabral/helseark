"""Installed-wheel real CLI + review drill; synthetic fixtures only."""
import argparse
from dataclasses import asdict
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


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--artifacts',type=Path,required=True)
    parser.add_argument('--java',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--timeout-seconds',type=int,default=120)
    parser.add_argument('--reuse-workflow',type=Path)
    args=parser.parse_args()
    assert 'site-packages' in str(Path(tool.__file__).resolve()),tool.__file__
    args.output.mkdir(parents=True,exist_ok=False)
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
                           args.artifacts/'packages',vault.root/'definitions/profiles/r4/0.1.0',args.timeout_seconds,False,args.java)
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
    receipt=approve(vault,prepared)
    committed=commit_candidate(vault,prepared,receipt)
    assert committed.disposition=='committed'
    assert not doctor(open_vault(vault.root)).issues
    assert all(p.read_bytes()==data for p,data in before.items())
    print('installed actual CLI:',report['officialRun']['resourceCount'],'resources;',report['officialRun']['counts'],
          '; source/accepted bytes unchanged; review/commit/reopen passed; module',tool.__file__)


if __name__=='__main__': main()
