"""Real installed API: requiring unavailable terminology must block publication."""
import argparse
from pathlib import Path
from dataclasses import replace
from helseark.fhir_validator import _lock,_artifacts,validate_with_official_tool
from helseark.contracts import ValidatorConfig,ArchiveError
from helseark.serialization import encode_json
from helseark.agent_context import document
from helseark.review import _blocked
from test_intake import supplied_candidate
from test_review import prepare


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--artifacts',type=Path,required=True)
    parser.add_argument('--java',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--timeout-seconds',type=int,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    vault,person,source,packet,candidate=supplied_candidate(args.output/'workflow')
    proposal=prepare(vault,candidate)
    before={p:p.read_bytes() for p in (vault.root/'people').rglob('*') if p.is_file()}
    lock=_lock()
    config=ValidatorConfig(args.artifacts/'validator_cli.jar',lock['executableSha256'],lock['version'],
        args.artifacts/'packages',vault.root/'definitions/profiles/r4',args.timeout_seconds,True,args.java)
    report=validate_with_official_tool(proposal,config,vault=vault)
    data=encode_json(document(report));(args.output/'required-terminology-report.json').write_bytes(data)
    assert b'UNSELECTED SECRET' not in data
    assert report.officialRun['counts']['errors']==0
    assert next(c.result for c in report.coverage if c.family=='full-fhir')=='passed'
    assert next(c.result for c in report.coverage if c.family=='terminology')=='failed'
    assert any(i.code=='TERMINOLOGY_UNAVAILABLE' and i.severity=='error' for i in report.issues)
    try:_blocked(report)
    except ArchiveError as error:assert error.code=='VALIDATION_BLOCKED'
    else:raise AssertionError('Unavailable required terminology passed')
    assert all(p.read_bytes()==data for p,data in before.items())
    empty=args.output/'empty-packages';empty.mkdir()
    try:_artifacts(replace(config,packageDirectory=empty),args.output/'empty-home')
    except ArchiveError as error:assert error.code=='VALIDATOR_MISSING_ARTIFACT'
    else:raise AssertionError('Real unrelated empty cache passed')
    print('real installed required-terminology API:',report.officialRun['resourceCount'],'resources;',report.officialRun['counts'],
          '; terminology failed/unavailable; publication blocked; 1 source unchanged; real empty cache blocked')


if __name__=='__main__':main()
