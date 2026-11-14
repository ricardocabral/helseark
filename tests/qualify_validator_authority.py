"""Real offline Task10 authority/reconciliation qualification; synthetic data only.

Run explicitly with an installed wheel. No conformance subprocess is faked.
Attack copies share immutable bytes with COW on macOS; reference tools stay readonly.
"""
import argparse
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig

from jsonschema import Draft6Validator
from helseark import fhir_validator as tool
from helseark.archive import open_vault,commit_candidate,doctor,head
from helseark.review import read_prepared,read_receipt,render_review,record_review
from helseark.contracts import ArchiveError,ReviewDecision,ValidatorConfig
from helseark.serialization import encode_json,decode_json,hash_bytes
from helseark.agent_context import document
from test_intake import supplied_candidate
from test_review import prepare
from qualify_official_validator import network_denial_witness


def clone(source,destination):
    destination.parent.mkdir(parents=True,exist_ok=True)
    if sys.platform=='darwin':
        subprocess.run(['/bin/cp','-cR',str(source),str(destination)],check=True)
    else:
        shutil.copytree(source,destination,symlinks=True)


def inventory(root):
    return {p.relative_to(root).as_posix():hash_bytes(p.read_bytes()) for p in root.rglob('*') if p.is_file() and not p.is_symlink()}


def decision(view):
    return ReviewDecision(True,'accept-with-acknowledged-limitations',tuple(
        {'code':i['code'],'resourceRef':i['resourceRef'],'reason':'Explicit synthetic human decision; original sources and individual limitations checked.'}
        for i in view.issues if i['severity'] in ('review','warning')),'synthetic authority qualification')


def fork_workflow(source,destination):
    clone(source,destination)
    vault=open_vault(destination/'vault')
    path=next((vault.root/'work/proposals').glob('*/proposal.json')).parent
    for control in (vault.root/'.runtime/prepared').glob('*.json'):
        value=decode_json(control.read_bytes());value['candidatePath']=str(destination/'candidate');control.write_bytes(encode_json(value))
    return vault,path


def expect_block(operation):
    try:operation()
    except ArchiveError as error:return error.code
    raise AssertionError('Unsafe public operation succeeded')


def mutation(name,value,baseline):
    run=value['officialRun']
    if name=='forged-outcome':
        run['operationOutcome']={'resourceType':'OperationOutcome','issue':[{'severity':'information','code':'informational','diagnostics':'Synthetic counterfeit success'}]}
        run['outcomeSha256']=hash_bytes(encode_json(run['operationOutcome']))
        issues,run['counts']=tool._outcome(encode_json(run['operationOutcome']),0,run['mapping'])
        value['issues']=[i for i in value['issues'] if not i['code'].startswith('OFFICIAL_FHIR_')]+[document(i) for i in issues]
        run['command']=['NOT AN EXECUTED COMMAND'];run['javaSha256']='0'*64
        for coverage in value['coverage']:
            if coverage['family']=='full-fhir':coverage['reason']='Invented zero-warning guarantee'
    elif name=='command':run['command']=['UNEXECUTED']
    elif name=='java-digest':run['javaSha256']='0'*64
    elif name=='environment':run['environment']['JAVA_TOOL_OPTIONS']='forged environment'
    elif name=='policy':run['requireTerminology']=True
    elif name=='missing-extraction':value['coverage']=[c for c in value['coverage'] if c['family']!='extraction-accuracy']
    elif name=='missing-baseline':value['coverage']=[c for c in value['coverage'] if c['family'] in ('full-fhir','terminology')]
    elif name=='duplicate-baseline':value['coverage'].append(deepcopy(value['coverage'][0]))
    elif name=='duplicate-official':value['coverage'].append(deepcopy(next(c for c in value['coverage'] if c['family']=='full-fhir')))
    elif name=='medical-diagnosis':value['coverage'].append({'family':'medical-diagnosis','result':'passed','reason':'Invented clinical guarantee'})
    elif name=='reason':next(c for c in value['coverage'] if c['family']=='extraction-accuracy')['reason']='Lost human limitation'
    elif name=='result':next(c for c in value['coverage'] if c['family']=='extraction-accuracy')['result']='passed'
    elif name=='strip-official':return deepcopy(baseline)
    else:raise AssertionError(name)
    return value


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--artifacts',type=Path,required=True)
    parser.add_argument('--java',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--legacy-workflow',type=Path,required=True)
    parser.add_argument('--timeout-seconds',type=int,default=240)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    assert 'site-packages' in tool.__file__,tool.__file__
    print('installed runtime',tool.__file__,flush=True)
    witness=network_denial_witness(args.output)
    print('reachable loopback control + specific OS denial',witness,flush=True)
    # Make only COW-owned runtime/package copies for negative mutation checks.
    java_home=args.java.absolute().parent.parent
    java_root=java_home.parent.parent if java_home.name=='Home' and java_home.parent.name=='Contents' else java_home
    clone(java_root,args.output/'java-runtime')
    java_relative=args.java.absolute().relative_to(java_root)
    clone(args.artifacts/'packages',args.output/'packages')
    vault,person,source,packet,candidate=supplied_candidate(args.output/'workflow')
    proposal=prepare(vault,candidate)
    baseline=decode_json((proposal.path/'validation.json').read_bytes())
    original=inventory(vault.root/'people')
    (args.output/'original-person-inventory.json').write_bytes(encode_json(original))
    pins=tool._lock()
    config=ValidatorConfig(args.artifacts/'validator_cli.jar',pins['executableSha256'],pins['version'],
        args.output/'packages',vault.root/'definitions/profiles/r4/0.1.0',args.timeout_seconds,False,args.output/'java-runtime'/java_relative)
    def staging_space():
        available=shutil.disk_usage(args.output).free
        staging=Path(os.environ['TMPDIR'])
        active=list(staging.glob('helseark-validator-*'))
        assert not active,('Unexpected previous staging',active)
        assert available>=900*1024*1024,('Insufficient bounded staging space',available)
        print('pre-Java free bytes',available,'active staging',len(active),'limit 700 MiB',flush=True)
    before_inputs=tool._runtime_inputs(config)
    # Demonstrate read guards work before relying on the qualified API result.
    other=next(p for p in (vault.root/'people').iterdir() if p.name!=person)
    other_file=next(other.rglob('proposal.json'))
    checkout=Path(__file__).resolve().parents[1]/'src'
    code_file=checkout/'helseark/fhir_validator.py'
    assert other_file.read_bytes() and code_file.read_bytes()
    blocked=[str(other),str(checkout)]
    def audit(event,values):
        if event=='open' and isinstance(values[0],(str,bytes,os.PathLike)):
            path=os.fsdecode(values[0])
            if any(path==prefix or path.startswith(prefix+'/') for prefix in blocked):raise PermissionError('Synthetic read guard')
    sys.addaudithook(audit)
    for target in (other_file,code_file):
        try:target.read_bytes()
        except PermissionError:pass
        else:raise AssertionError('Read guard inactive')
    for name in ('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS'):
        os.environ[name]='-this-must-not-reach-java'
    os.environ['CLASSPATH']='/invalid/injected/classpath';os.environ['HTTPS_PROXY']='http://127.0.0.1:1'
    staging_space()
    report=tool.validate_with_official_tool(proposal,config,vault=vault)
    blocked.clear()
    assert tool._runtime_inputs(config)==before_inputs
    assert inventory(vault.root/'people')==original
    assert report.officialRun['counts']=={'errors':0,'warnings':7,'information':1}
    assert report.officialRun['resourceCount']==5
    assert set(report.officialRun['environment'])=={'PATH','HOME','LANG'}
    assert b'UNSELECTED SECRET' not in encode_json(document(report))
    (args.output/'positive-report.json').write_bytes(encode_json(document(report)))
    (proposal.path/'validation.json').write_bytes(encode_json(document(report)))
    prepared=read_prepared(vault,proposal.path);view=render_review(vault,prepared)
    assert sum(i['code'].startswith('OFFICIAL_FHIR_WARNING') for i in view.issues)==7
    assert next(c for c in view.validationCoverage if c['family']=='extraction-accuracy')['result']=='not-checked'
    human=decision(view)
    pending=args.output/'pending';clone(args.output/'workflow',pending)
    print('real positive',report.officialRun['resourceCount'],report.officialRun['counts'],'original person files',len(original),flush=True)
    # Each attack has its own nonempty copy, genuine host authority is never forged.
    attacks=[]
    names=('forged-outcome','command','java-digest','policy','missing-extraction','missing-baseline',
           'duplicate-baseline','duplicate-official','medical-diagnosis','reason','result','strip-official')
    # Invalid extra environment fields are a schema rejection too; other attacks stay schema-valid.
    for name in names:
        v,path=fork_workflow(pending,args.output/'attacks'/name)
        changed=mutation(name,deepcopy(document(report)),baseline)
        (path/'validation.json').write_bytes(encode_json(changed))
        p=read_prepared(v,path)
        rendered=expect_block(lambda:render_review(v,p))
        reviewed=expect_block(lambda:record_review(v,p,human))
        cli=subprocess.run([sys.executable,'-m','helseark.cli','--vault',str(v.root),'candidate','review',str(path),
            '--person',person,'--json'],capture_output=True)
        assert cli.returncode!=0,(name,cli.stdout)
        assert inventory(v.root/'people')==original
        attacks.append({'case':name,'render':rendered,'record':reviewed,'cliExit':cli.returncode,'originalFiles':len(original)})
    for name in ('missing-authority','missing-preparation','fake-accepted-path'):
        v,path=fork_workflow(pending,args.output/'attacks'/name)
        p=read_prepared(v,path)
        if name=='missing-authority':(v.root/f'.runtime/official-validation/{p.proposalSha256}.json').unlink()
        else:
            (v.root/f'.runtime/prepared/{p.proposalSha256}.json').unlink()
            if name=='fake-accepted-path':(path/'change.json').write_bytes(encode_json({}))
        attacks.append({'case':name,'render':expect_block(lambda:render_review(v,p)),
                        'record':expect_block(lambda:record_review(v,p,human)),'originalFiles':len(original)})
    # The complete Java closure, not only its launcher, is checked while pending.
    runtime_file=(args.output/'java-runtime'/java_relative).parent.parent/'lib/tzdb.dat';saved=runtime_file.read_bytes()
    try:
        runtime_file.write_bytes(saved+b'X')
        v,path=fork_workflow(pending,args.output/'attacks/runtime-file')
        p=read_prepared(v,path)
        code=expect_block(lambda:render_review(v,p));assert code=='VALIDATOR_RUNTIME_CHANGED'
        attacks.append({'case':'runtime-file','render':code,'originalFiles':len(original)})
    finally:runtime_file.write_bytes(saved)
    # A failed new required-policy request invalidates the old result at request start.
    v,path=fork_workflow(pending,args.output/'attacks/new-request-fails')
    p=read_prepared(v,path)
    failed=expect_block(lambda:tool.validate_with_official_tool(p,replace(config,requireTerminology=True,javaPath=args.output/'absent/bin/java'),vault=v))
    attacks.append({'case':'new-request-fails','request':failed,'render':expect_block(lambda:render_review(v,p)),'originalFiles':len(original)})
    # A separate explicit synthetic baseline decision advances the selected head.
    v,path=fork_workflow(pending,args.output/'attacks/advanced-head')
    from helseark.intake import prepare_candidate,read_candidate
    concurrent=prepare_candidate(v,read_candidate(v,args.output/'attacks/advanced-head/candidate'))
    concurrent_receipt=record_review(v,concurrent,decision(render_review(v,concurrent)))
    commit_candidate(v,concurrent,concurrent_receipt)
    old=read_prepared(v,path)
    code=expect_block(lambda:render_review(v,old));assert code=='STALE_BASE'
    attacks.append({'case':'advanced-head','render':code,'originalFiles':len(original)})
    # A changed source in a disposable copy cannot reuse genuine report authority.
    v,path=fork_workflow(pending,args.output/'attacks/source-bytes')
    changed_source=v.root/source.assetPath.relative_to(vault.root)
    saved=changed_source.read_bytes();changed_source.write_bytes(saved+b'\nSYNTHETIC REPLAY')
    p=read_prepared(v,path)
    attacks.append({'case':'source-bytes','render':expect_block(lambda:render_review(v,p)),'intentionallyChangedSources':1})
    # Scope replays change only mutable proposal/report, never their host controls.
    for field,replacement in (('personId',next(p.name for p in (vault.root/'people').iterdir() if p.name!=person)),
                              ('baseChangeSha256','0'*64),('evidenceSha256','0'*64)):
        v,path=fork_workflow(pending,args.output/'attacks'/('replay-'+field))
        pv=decode_json((path/'proposal.json').read_bytes());pv[field]=replacement
        (path/'proposal.json').write_bytes(encode_json(pv))
        changed=deepcopy(document(report));changed['checkedProposalSha256']=hash_bytes((path/'proposal.json').read_bytes())
        (path/'validation.json').write_bytes(encode_json(changed))
        attacks.append({'case':'replay-'+field,'publicRead':expect_block(lambda:render_review(v,read_prepared(v,path)))})
    (args.output/'attacks.json').write_bytes(encode_json(attacks))
    print('public report/coverage/runtime/policy/scope attacks blocked',len(attacks),flush=True)
    # One independent real schema-valid deeper invariant, without touching input bytes.
    _,bundle,mapping=tool._context(vault,prepared)
    before=encode_json(bundle);invalid=deepcopy(bundle)
    next(e['resource'] for e in invalid['entry'] if e['resource']['resourceType']=='Patient')['contact']=[{'gender':'unknown'}]
    data_root=Path(sysconfig.get_path('data'))/'share/helseark'
    assert Draft6Validator(decode_json((data_root/'definitions/fhir-r4-json-schema/fhir.schema.json').read_bytes())).is_valid(invalid)
    staging_space()
    _,counts,run=tool._run_bundle(vault,invalid,mapping,config)
    assert counts['errors']>=1 and any('pat-1' in str(i) for i in run['operationOutcome']['issue'] if i['severity']=='error')
    assert encode_json(bundle)==before and inventory(vault.root/'people')==original
    (args.output/'deeper-negative.json').write_bytes(encode_json(run))
    print('real schema-valid pat-1 negative',len(invalid['entry']),counts,flush=True)
    # Real required terminology on a separate pending copy has independent host authority.
    v,path=fork_workflow(pending,args.output/'required')
    p=read_prepared(v,path)
    staging_space()
    required=tool.validate_with_official_tool(p,replace(config,requireTerminology=True),vault=v)
    (args.output/'required-report.json').write_bytes(encode_json(document(required)))
    assert required.officialRun['counts']['errors']==0
    # Old genuine optional report is now stale after the actual required-policy execution.
    (path/'validation.json').write_bytes(encode_json(document(report)))
    stale=expect_block(lambda:render_review(v,read_prepared(v,path)))
    assert stale=='VALIDATOR_AUTHORITY_MISMATCH'
    (path/'validation.json').write_bytes(encode_json(document(required)))
    rejected=expect_block(lambda:record_review(v,read_prepared(v,path),human));assert rejected=='VALIDATION_BLOCKED'
    assert inventory(v.root/'people')==original
    print('real required terminology',required.officialRun['resourceCount'],required.officialRun['counts'],
          'public record_review',rejected,'old optional replay',stale,flush=True)
    # Authentic review retains the host binding; post-review report tamper blocks direct commit.
    prepared=read_prepared(vault,proposal.path)
    receipt=record_review(vault,prepared,human)
    reviewed=args.output/'reviewed';clone(args.output/'workflow',reviewed)
    for name in ('forged-outcome','missing-extraction','medical-diagnosis'):
        v,path=fork_workflow(reviewed,args.output/'commit-attacks'/name)
        p=read_prepared(v,path);r=read_receipt(v,p)
        (path/'validation.json').write_bytes(encode_json(mutation(name,deepcopy(document(report)),baseline)))
        p=read_prepared(v,path)
        code=expect_block(lambda:commit_candidate(v,p,r))
        cli=subprocess.run([sys.executable,'-m','helseark.cli','--vault',str(v.root),'candidate','commit',str(path),'--person',person,'--json'],capture_output=True)
        assert cli.returncode!=0
        attacks.append({'case':'commit-'+name,'commit':code,'cliExit':cli.returncode})
    (args.output/'attacks.json').write_bytes(encode_json(attacks))
    result=commit_candidate(vault,prepared,receipt);assert result.disposition=='committed'
    accepted=next(d for d in (vault.root/'people'/person/'accepted').iterdir() if d.name.startswith('00000002-'))
    review=decode_json((accepted/'review.json').read_bytes())
    assert review['officialValidationAuthority']['reportSha256']==hash_bytes((accepted/'validation.json').read_bytes())
    accepted_before=inventory(vault.root/'people')
    shutil.rmtree(vault.root/'work');shutil.rmtree(vault.root/'.runtime')
    reopened=open_vault(vault.root);persisted=read_prepared(reopened,accepted)
    retained_view=render_review(reopened,persisted);read_receipt(reopened,persisted)
    assert next(c['result'] for c in retained_view.validationCoverage if c['family']=='official-execution-authority')=='passed'
    integrity=doctor(reopened);assert not integrity.issues
    assert inventory(vault.root/'people')==accepted_before
    assert all((vault.root/'people'/p).is_file() and hash_bytes((vault.root/'people'/p).read_bytes())==h for p,h in original.items())
    (args.output/'doctor.json').write_bytes(encode_json(document(integrity)))
    (args.output/'accepted-inventory.json').write_bytes(encode_json(accepted_before))
    print('authenticated accepted history after work/runtime cleanup',document(integrity),'original files',len(original),'accepted files',len(accepted_before),flush=True)
    # Historical immutable reports remain readable, but acquire no new attestation.
    legacy=args.output/'legacy';clone(args.legacy_workflow,legacy)
    old=open_vault(legacy/'vault');old_before=inventory(old.root/'people')
    old_report=next(p.parent for p in (old.root/'people').glob('*/accepted/00000002-*/validation.json') if decode_json(p.read_bytes()).get('officialRun'))
    for folder in ('work','.runtime'):
        shutil.rmtree(old.root/folder,ignore_errors=True)
    old_prepared=read_prepared(old,old_report);old_view=render_review(old,old_prepared);read_receipt(old,old_prepared)
    assert all(c['result']=='not-checked' for c in old_view.validationCoverage)
    assert inventory(old.root/'people')==old_before
    print('legacy accepted receipts readable, execution unattested, immutable files',len(old_before),flush=True)
    assert tool._runtime_inputs(config)==before_inputs
    print('qualification complete; no clinical correctness or licensed terminology claim',flush=True)


if __name__=='__main__':main()
