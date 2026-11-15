"""Fresh installed public CLI journeys. Synthetic decisions are not clinical approval.

Copy this script and fixtures outside the checkout. Arguments: WORK CHECKOUT FIXTURES.
Receipts retain exact command output, source/accepted inventories and real counts.
"""
from pathlib import Path
from dataclasses import asdict
import os
import subprocess
import sys
from helseark.archive import open_vault
from helseark.intake import add_source, read_candidate
from helseark.serialization import encode_json, decode_json, hash_bytes
import helseark.intake

work, checkout, fixtures = (Path(p).resolve() for p in sys.argv[1:4])
assert not Path(helseark.intake.__file__).resolve().is_relative_to(checkout)
assert not fixtures.is_relative_to(checkout)
work.mkdir()
commands, cases, api = [], [], []
console = Path(sys.executable).parent/'helseark'
guard = work/'guard'; guard.mkdir()
(guard/'sitecustomize.py').write_text('''import sys,os
from pathlib import Path
def deny(event,args):
 if event.startswith(('socket.','urllib.')):raise RuntimeError('NETWORK_DENIED')
 if event in ('open','os.listdir','os.scandir') and args and isinstance(args[0],(str,bytes)):
  for forbidden in os.environ['QUALIFY_DENY'].split(os.pathsep):
   if Path(os.fsdecode(args[0])).absolute().is_relative_to(Path(forbidden)):raise RuntimeError('CHECKOUT_DENIED')
sys.addaudithook(deny)
''')
env = {**os.environ, 'PYTHONDONTWRITEBYTECODE':'1', 'PYTHONPATH':str(guard), 'QUALIFY_DENY':os.pathsep.join(map(str,(checkout,work.parent/'source')))}
for code in ('import socket;socket.socket()',
             'import os;open(os.environ["QUALIFY_DENY"].split(os.pathsep)[0]+"/pyproject.toml")',
             'import os;open(os.environ["QUALIFY_DENY"].split(os.pathsep)[1]+"/pyproject.toml")'):
    witness=subprocess.run([sys.executable,'-c',code],env=env,cwd=work,capture_output=True)
    assert witness.returncode != 0 and b'_DENIED' in witness.stderr


def run(*args, expect=0):
    argv=[str(console), *map(str,args), '--json']
    child=subprocess.run(argv,cwd=work,env=env,capture_output=True,timeout=90)
    number=len(commands)+1
    for name,data in [('stdout',child.stdout),('stderr',child.stderr)]:
        (work/f'{number:03d}.{name}').write_bytes(data)
    commands.append(dict(argv=argv,exit=child.returncode,stdoutSha256=hash_bytes(child.stdout),stderrSha256=hash_bytes(child.stderr)))
    (work/'commands.json').write_bytes(encode_json(commands))
    assert child.returncode==expect,(argv,child.returncode,child.stderr)
    return decode_json(child.stdout if child.returncode==0 else child.stderr)


def inventory(root):
    return {str(f.relative_to(root)):dict(sha256=hash_bytes(f.read_bytes()),size=f.stat().st_size)
            for f in root.rglob('*') if f.is_file()}


def publish(v,p,cpath,folder,label):
    proposal=run('--vault',v,'candidate','prepare',cpath,'--person',p)
    view=run('--vault',v,'candidate','review',proposal['path'],'--person',p)
    assert not [i for i in view['issues'] if i['severity']=='error']
    acks={i['issueId']:dict(issueId=i['issueId'],code=i['code'],resourceRef=i['resourceRef'],
                          reason='SYNTHETIC exact displayed limitation; not clinical approval')
          for i in view['issues'] if i['severity'] in ('review','warning')}
    d=folder/(label+'-decision.json')
    d.write_bytes(encode_json(dict(confirmedPerson=True,decision='accept-with-acknowledged-limitations',
                                  acknowledgedIssues=list(acks.values()),reviewerLabel='SYNTHETIC host qualification')))
    run('--vault',v,'candidate','review',proposal['path'],'--person',p,'--decision',d)
    return run('--vault',v,'candidate','commit',proposal['path'],'--person',p)


for kind in ('DocumentReference','DiagnosticReport','csv'):
    folder=work/kind;folder.mkdir();v=folder/'vault';run('init',v)
    assert open_vault(v).config.agentKitVersion=='0.1.19'
    assert open_vault(v).config.profileVersion=='0.2.0'
    p=run('--vault',v,'person','add','--name','Person A')['personId']
    other=run('--vault',v,'person','add','--name','Person B')['personId']
    if kind=='csv':
        source=fixtures/'structured/metrics.csv';family='metrics-csv'
        mapping=dict(delimiter=';',encoding='utf-8-sig',dateColumn='date',valueColumn='value',unitColumn='unit',
                     codeColumn='code',dateFormat='%d/%m/%Y',decimalSeparator=',',localPersonId=p,assignmentReason='SYNTHETIC explicit assignment')
    else:
        retained=add_source(open_vault(v),p,fixtures/'agent-workflows/shared-report.txt')
        api.append(dict(operation='add_source',receipt={**asdict(retained),'assetPath':str(retained.assetPath)}))
        assert retained.sourceSha256=='dc35fde75226b81cdc86b58b7a0aca24822d9a979447ae9b79074aac5c7e4f96'
        assert retained.mediaType=='application/octet-stream'
        a=dict(url=f'assets/sha256/{retained.sourceSha256}/blob',contentType=retained.mediaType,
               size=retained.size,title='Unchanged synthetic shared original')
        r=dict(resourceType=kind,id='d1',status='current' if kind=='DocumentReference' else 'final',subject={'reference':'Patient/p1'})
        o=dict(resourceType='Observation',id='o1',status='unknown',subject={'reference':'Patient/p1'},
               code={'text':'Synthetic result'},valueString='synthetic result A')
        if kind=='DocumentReference':r['content']=[{'attachment':a}];o['derivedFrom']=[{'reference':'DocumentReference/d1'}]
        else:r.update(code={'text':'Synthetic report'},presentedForm=[a],result=[{'reference':'Observation/o1'}])
        source=folder/'native.json';source.write_bytes(encode_json(dict(resourceType='Bundle',type='collection',entry=[
            {'resource':{'resourceType':'Patient','id':'p1'}},{'resource':r},{'resource':o}])))
        family='fhir-r4';mapping=dict(patientReference='Patient/p1',localPersonId=p,assignmentReason='SYNTHETIC explicit assignment; no disclosure',provider='https://synthetic.example')
    cfg=folder/'mapping.json';cfg.write_bytes(encode_json(mapping))
    c=run('--vault',v,'intake',family,source,'--person',p,'--mapping',cfg)
    publish(v,p,c['path'],folder,'import')
    issued=inventory(Path(c['path']));assets=inventory(v/'people'/p/'assets');prior=inventory(v/'people'/p/'accepted')
    if kind!='csv':
        reused=add_source(open_vault(v),p,fixtures/'agent-workflows/shared-report.txt')
        assert reused.assetPath==retained.assetPath and reused.sourceSha256==retained.sourceSha256
        assert inventory(v/'people'/p/'assets')==assets
        api.append(dict(operation='add_source same-person reuse',receipt={**asdict(reused),'assetPath':str(reused.assetPath)}))
    assert read_candidate(open_vault(v),Path(c['path'])).candidateId==c['candidateId']
    api.append(dict(operation='read_candidate',personId=p,candidateId=c['candidateId'],unchanged=True))
    rows=run('--vault',v,'observations','--person',p);old=rows[0]['resourceRef']
    target=f"{old['resourceType']}/{old['id']}/_history/{old['versionId']}"
    old_resource=run('--vault',v,'record','--person',p,'--resource',target)
    draft=run('--vault',v,'correct','--person',p,'--resource',target,'--reason','entered-in-error: SYNTHETIC explicitly invalid local assertion')
    path=Path(draft['path']);bundle=decode_json((path/'bundle.json').read_bytes())
    next(e['resource'] for e in bundle['entry'] if e['resource']['resourceType']=='Observation')['status']='entered-in-error'
    (path/'bundle.json').write_bytes(encode_json(bundle));publish(v,p,path,folder,'correction')
    assert run('--vault',v,'record','--person',p,'--resource',target)==old_resource
    corrected=run('--vault',v,'record','--person',p,'--resource',f"Observation/{old['id']}")
    assert corrected['status']=='entered-in-error'
    assert all(corrected[k]==value for k,value in old_resource.items() if k not in ('status','meta'))
    from helseark.archive import iter_current
    assert any(e['role']=='revision' and e['what']['reference']==target
               for r in iter_current(open_vault(v),p) if r['resourceType']=='Provenance' for e in r['entity'])
    current=run('--vault',v,'observations','--person',p)
    assert not any(r['resourceRef']['id']==old['id'] for r in current)
    assert all(inventory(v/'people'/p/'accepted')[name]==data for name,data in prior.items())
    assert inventory(v/'people'/p/'assets')==assets and inventory(Path(c['path']))==issued
    report=run('--vault',v,'doctor');assert not report['issues'] and report['checkedResources']>0 and report['checkedAssets']>0
    row=dict(oldResource=old_resource,correctedResource=corrected,kind=kind,personId=p,otherPersonId=other,target=target,doctor=report,
             priorAccepted=prior,finalAccepted=inventory(v/'people'/p/'accepted'),sourceInventory=assets,issuedInventory=issued)
    if kind!='csv':
        args=['--vault',v,'export','--person',p,'--mode','selected-current']
        assert run(*args,'--out',folder/'denied',expect=3)['code']=='SOURCE_SCOPE_REVIEW_REQUIRED'
        run(*args,'--no-sources','--out',folder/'source-free')
        assert not run('backup','verify',folder/'source-free')['issues']
        def review(plan):
            raw=(plan/'plan.json').read_bytes();d=folder/(plan.name+'-decision.json')
            d.write_bytes(encode_json(dict(format='helseark-source-decision-1',planSha256=hash_bytes(raw),humanReviewed=True,
                confirmedPerson=True,acknowledgedDisclosure=True,reviewer={'kind':'synthetic-test','label':'SYNTHETIC fixture human'},
                reason='SYNTHETIC full displayed source inventory and remaining disclosure reviewed')))
            run('--vault',v,'export-review','--plan',plan,'--decision',d)
        plan=folder/'original-plan';run('--vault',v,'export-plan','--person',p,'--mode','selected-current','--out',plan);review(plan)
        run(*args,'--out',folder/'original-export','--review',plan)
        assert not run('backup','verify',folder/'original-export')['issues']
        assert (folder/f'original-export/sources/people/{p}/assets/sha256/{retained.sourceSha256}/blob').read_bytes()==retained.assetPath.read_bytes()
        derivative=folder/'supplied.txt';derivative.write_bytes(b'Person A: synthetic result A\n')
        dlist=folder/'derivatives.json';dlist.write_bytes(encode_json([dict(sourceSha256=retained.sourceSha256,path=str(derivative),
            mediaType='text/plain',mapping='SYNTHETIC Person A line',omissions='Human omitted Person B line')]))
        dplan=folder/'derivative-plan';run('--vault',v,'export-plan','--person',p,'--mode','selected-current','--out',dplan,'--derivatives',dlist);review(dplan)
        run(*args,'--out',folder/'derivative-export','--review',dplan)
        assert not run('backup','verify',folder/'derivative-export')['issues']
        assert not (folder/'derivative-export/sources').exists()
        assert (folder/f'derivative-export/derivatives/{hash_bytes(derivative.read_bytes())}/blob').read_bytes()==derivative.read_bytes()
        row['disclosureOriginalSources']=decode_json((plan/'plan.json').read_bytes())['originalSources']
    cases.append(row)
    (work/'result.json').write_bytes(encode_json(dict(actualModelRuns=0,cliCommands=len(commands),apiReceipts=api,cases=cases)))
print('Installed public qualification:',len(commands),'CLI receipts,',len(cases),'cases',flush=True)
