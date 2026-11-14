"""Executable invented family lesson, Apache-2.0; generated fixture data CC0.

python generate.py ABSENT_OUTPUT_DIRECTORY --synthetic-review-decisions
Requires installed helseark[pdf]. Uses only the installed supplied candidate.
The flag records illustrative fixture decisions, never authenticated medical approval.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import subprocess
import sys
from helseark.serialization import decode_json, encode_json


def inventory(root):
    return {p.relative_to(root).as_posix():{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
            'size':p.stat().st_size} for p in sorted(root.rglob('*')) if p.is_file()}


def generate(output, *, synthetic_review_decisions=False):
    if not synthetic_review_decisions:
        raise ValueError('Explicit --synthetic-review-decisions is required for invented fixtures only.')
    output=Path(output).absolute();output.mkdir()
    kit=Path(sys.prefix)/'share/helseark/agent-kit'
    # A source checkout invocation may use its own distributed kit; installed
    # qualification always uses sys.prefix and does not need checkout reads.
    if not kit.is_dir():
        kit=Path(__file__).resolve().parents[2]/'agent-kit'
    calls=[]
    def run(*args, expected=0):
        child=subprocess.run([sys.executable,'-m','helseark.cli',*map(str,args),'--json'],
                             cwd=output,capture_output=True)
        calls.append({'args':list(map(str,args)),'exit':child.returncode,'expected':expected})
        if child.returncode!=expected:
            raise RuntimeError((args,child.returncode,child.stderr.decode()))
        return decode_json(child.stdout if expected==0 else child.stderr)
    vault=output/'vault';run('init',vault)
    def cli(*args,**kwargs):return run('--vault',vault,*args,**kwargs)
    people=[cli('person','add','--name','Avery Synthetic')['personId'] for _ in range(2)]
    def accept(person,candidate):
        proposal=cli('candidate','prepare',candidate,'--person',person)
        view=cli('candidate','review',proposal['path'],'--person',person)
        decision={'confirmedPerson':True,'decision':'accept-with-acknowledged-limitations',
          'reviewerLabel':'SYNTHETIC illustrative decision; not authenticated medical approval',
          'acknowledgedIssues':[{'code':i['code'],'resourceRef':i['resourceRef'],
             'reason':'Synthetic fixture decision: retain this disclosed limitation.'}
             for i in view['issues'] if i['severity'] in ('warning','review')]}
        decision_path=output/('decision-'+str(len(calls))+'.json')
        decision_path.write_bytes(encode_json(decision))
        (output/('review-'+str(len(calls))+'.json')).write_bytes(encode_json(view))
        cli('candidate','commit',proposal['path'],'--person',person,expected=3)
        cli('candidate','review',proposal['path'],'--person',person,'--decision',decision_path)
        return cli('candidate','commit',proposal['path'],'--person',person)
    for person in people:
        packet=output/('packet-'+person);candidate=output/('candidate-'+person)
        cli('intake','add',kit/'examples/task5-complete.pdf','--person',person,'--packet',packet,'--confirm-person')
        subprocess.run([sys.executable,str(kit/'examples/task5-example.py'),str(packet),str(candidate)],
                       cwd=output,check=True,capture_output=True)
        if person==people[0]:
            bundle=decode_json((candidate/'bundle.json').read_bytes())
            bundle['entry'][0]['resource']['method']['text']='M? invented transcription error'
            (candidate/'bundle.json').write_bytes(encode_json(bundle))
        accept(person,candidate)
        rows=cli('observations','--person',person)
        assert len(rows)==2
        quantity=next(r for r in rows if r['valueType']=='valueQuantity')
        assert str(quantity['value']['value'])=='0.050' and quantity['comparator']=='<'
        assert quantity['unit']=='mg/L' and quantity['timePrecision']=='month'
    selected,other=people
    initial=inventory(vault/'people'/selected);other_before=inventory(vault/'people'/other)
    rows=cli('observations','--person',selected)
    row=next(r for r in rows if r['valueType']=='valueQuantity')
    ref='Observation/'+row['resourceRef']['id'];oldref=ref+'/_history/'+row['resourceRef']['versionId']
    old=cli('record','--person',selected,'--resource',oldref)
    draft=cli('correct','--person',selected,'--resource',ref,'--reason','transcription: synthetic source says M1')
    path=Path(draft['path']);bundle=decode_json((path/'bundle.json').read_bytes())
    next(e['resource'] for e in bundle['entry'] if e['resource']['resourceType']=='Observation')['method']['text']='M1'
    (path/'bundle.json').write_bytes(encode_json(bundle));committed=accept(selected,path)
    current=cli('record','--person',selected,'--resource',ref)
    assert current['method']['text']=='M1' and current['status']=='final'
    assert str(current['valueQuantity']['value'])=='0.050'
    assert cli('record','--person',selected,'--resource',oldref)==old
    after=inventory(vault/'people'/selected)
    assert all(after[k]==v for k,v in initial.items())
    provenance=next(r for r in committed['logicalResources'] if r['resourceType']=='Provenance')
    native=cli('record','--person',selected,'--resource','Provenance/'+provenance['id'])
    assert any(e['role']=='revision' and e['what']['reference']==oldref for e in native['entity'])
    backup=output/'backup';cli('backup','create','--out',backup)
    assert run('backup','verify',backup)['issues']==[]
    before=inventory(vault/'people');planfile=output/'erasure-plan.json'
    plan=cli('erase','plan','--person',selected,'--quarantine',output/'quarantine','--out',planfile)
    cli('erase','apply',planfile,'--approve','0'*64,expected=3)
    cli('erase','apply',planfile,'--approve',plan['digest'])
    assert not (vault/'people'/selected).exists() and inventory(vault/'people'/other)==other_before
    cli('erase','restore',output/'quarantine','--approve',plan['digest'])
    assert inventory(vault/'people')==before
    run('backup','restore',backup,'--into',output/'restored')
    assert inventory(output/'restored/people')==before
    restored_rows=run('--vault',output/'restored','observations','--person',selected)
    assert encode_json(restored_rows)==encode_json(cli('observations','--person',selected))
    report=cli('doctor');assert not report['issues'] and report['checkedResources']>0
    result={'synthetic':True,'review':'illustrative fixture decisions; not authenticated medical approval',
       'readAt':datetime.now(timezone.utc).isoformat(),'people':people,'clinicalPeople':2,
       'selectedResource':ref,'oldResource':oldref,'valueLexeme':str(current['valueQuantity']['value']),
       'clinicalStatus':current['status'],'history':'retained','otherPersonByteChanges':0,
       'recoverable':True,'secureDeletion':False,'modelRuns':0,'doctor':report,
       'inventories':{'initialSelected':initial,'other':other_before,'beforeRestore':before,
                      'restored':inventory(output/'restored/people')},'calls':calls,
       'cases':[{'id':'transcription','result':'checked'}, {'id':'person-removal','result':'checked'},
                {'id':'laboratory-amendment','result':'not-checked'},
                {'id':'entered-in-error','result':'not-checked'},{'id':'cancelled-report','result':'not-checked'}]}
    (output/'result.json').write_bytes(encode_json(result))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--synthetic-review-decisions',action='store_true')
    args=parser.parse_args()
    result=generate(args.output,synthetic_review_decisions=args.synthetic_review_decisions)
    print(json.dumps({k:result[k] for k in ('clinicalPeople','valueLexeme','modelRuns','cases')}))
