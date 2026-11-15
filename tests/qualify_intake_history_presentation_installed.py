"""Run outside checkout: python qualifier.py ABSENT_WORK COPIED_FIXTURES CHECKOUT.

Synthetic deterministic candidates and decisions only; no model or clinical claims.
The installed console performs intake/review/publication/query/report/recovery.
"""
from pathlib import Path
import csv
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from uuid import uuid4
from helseark.serialization import decode_json, encode_json, hash_bytes

work, fixtures, checkout = (Path(p).resolve() for p in sys.argv[1:4])
work.mkdir()
guard=work/'guard';guard.mkdir()
(guard/'sitecustomize.py').write_text('''import os,sys
def audit(event,args):
    if event.startswith(('socket.','urllib.')):raise RuntimeError('network forbidden')
    if event in ('open','os.scandir','os.listdir') and args and isinstance(args[0],(str,bytes)):
        p=os.path.abspath(os.fsdecode(args[0]))
        for root in os.environ.get('UNION_DENY','').split(os.pathsep):
            if root and (p==root or p.startswith(root+os.sep)):raise RuntimeError('scope forbidden')
sys.addaudithook(audit)
''')
env={**os.environ,'PYTHONPATH':str(guard),'UNION_DENY':str(checkout),'PYTHONDONTWRITEBYTECODE':'1'}
console=Path(sys.executable).parent/'helseark';commands=[]
def run(*args, expected=0):
    child=subprocess.run([str(console),*map(str,args),'--json'],env=env,cwd=work,capture_output=True)
    commands.append({'args':list(map(str,args)),'exit':child.returncode,'stdout':child.stdout.decode(),'stderr':child.stderr.decode()})
    (work/'commands.json').write_bytes(encode_json(commands))
    assert child.returncode==expected,(args,child.returncode,child.stderr)
    return decode_json(child.stdout if child.returncode==0 else child.stderr)
def write(name,value):
    path=work/name;path.write_bytes(encode_json(value));return path
vault=work/'vault';run('init',vault)
person=run('--vault',vault,'person','add','--name','Synthetic union patient')['personId']
other=run('--vault',vault,'person','add','--name','Synthetic union patient','--note','PRIVATE_OTHER_PERSON')['personId']
def approve(candidate, selected):
    proposal=run('--vault',vault,'candidate','prepare',candidate,'--person',selected)
    path=Path(proposal['path'])
    assert run('--vault',vault,'candidate','commit',path,'--person',selected,expected=3)['code']=='REVIEW_REQUIRED'
    view=run('--vault',vault,'candidate','review',path,'--person',selected)
    acks=[{'code':i['code'],'resourceRef':i['resourceRef'],'issueId':i['issueId'],
           'reason':'SYNTHETIC human fixture compared source and exact limitation; no clinical approval.'}
          for i in view['issues'] if i['severity'] in ('review','warning')]
    decision=write('decision.json',{'confirmedPerson':True,'decision':'accept-with-acknowledged-limitations',
                    'acknowledgedIssues':acks,'reviewerLabel':'SYNTHETIC human fixture'})
    run('--vault',vault,'candidate','review',path,'--person',selected,'--decision',decision)
    result=run('--vault',vault,'candidate','commit',path,'--person',selected)
    assert run('--vault',vault,'candidate','commit',path,'--person',selected)['disposition']=='already-accepted'
    return result
mapping=lambda p:write('identity.json',dict(patientReference='Patient/p1',localPersonId=p,
    assignmentReason='SYNTHETIC explicit person assignment',provider='https://synthetic.example/fhir'))
other_candidate=run('--vault',vault,'intake','fhir-r4',fixtures/'structured/r4.json','--person',other,'--mapping',mapping(other))
approve(other_candidate['path'],other)
other_file=next((vault/'people'/other/'accepted').rglob('Observation-*.json'))
assert other_file.read_bytes()
env['UNION_DENY']=os.pathsep.join([str(checkout),str(vault/'people'/other)])
witnesses=[]
for code in ['import socket;socket.socket()',f'open({str(checkout/"pyproject.toml")!r})',f'open({str(other_file)!r})']:
    child=subprocess.run([sys.executable,'-c',code],env=env,cwd=work,capture_output=True)
    assert child.returncode and b'forbidden' in child.stderr
    witnesses.append(code)
records=decode_json((fixtures/'clinical-history/oracle/candidate-resources.json').read_bytes().replace(b'PERSON',b'p1'))
for r in records:r['id']=r['resourceType'].lower()
next(r for r in records if r['resourceType']=='Immunization')['education']=[{'reference':'urn:uuid:immunization'}]
next(r for r in records if r['resourceType']=='MedicationStatement')['derivedFrom']=[{'reference':'MedicationRequest/medicationrequest'}]
source=write('native.json',{'resourceType':'Bundle','type':'collection','entry':[
    {'resource':{'resourceType':'Patient','id':'p1','name':[{'text':'Synthetic union patient'}]}},*[{'resource':r} for r in records]]})
candidate=run('--vault',vault,'intake','fhir-r4',source,'--person',person,'--mapping',mapping(person))
approve(candidate['path'],person)
kinds=[r['resourceType'] for r in records];kind_args=[s for k in kinds for s in ('--kind',k)]
def facts(resources):
    oracle=decode_json((fixtures/'expected/clinical-history-facts.json').read_bytes())['families']
    def at(r,p):
        for part in p.strip('/').split('/'):r=r[int(part)] if isinstance(r,list) else r[part]
        return r
    for kind,expected in oracle.items():
        r=next(r for r in resources if r['resourceType']==kind)
        for pointer,value in expected['facts'].items():assert encode_json(at(r,pointer))==encode_json(value),(kind,pointer)
        for pointer in expected['absent']:
            try:at(r,pointer)
            except (KeyError,IndexError):pass
            else:raise AssertionError((kind,pointer))
    assert next(r for r in resources if r['resourceType']=='Immunization')['education'][0]['reference']=='urn:uuid:immunization'
    assert '/_history/' in next(r for r in resources if r['resourceType']=='MedicationStatement')['derivedFrom'][0]['reference']
accepted=run('--vault',vault,'history','--person',person,*kind_args);facts(accepted)
map_csv=write('csv.json',dict(delimiter=';',encoding='utf-8-sig',dateColumn='date',valueColumn='value',unitColumn='unit',codeColumn='code',dateFormat='%d/%m/%Y',decimalSeparator=',',localPersonId=person,assignmentReason='SYNTHETIC explicit assignment'))
candidate=run('--vault',vault,'intake','metrics-csv',fixtures/'structured/metrics.csv','--person',person,'--mapping',map_csv)
approve(candidate['path'],person)
# Actual optional native OCR, with exact local pins and a pre-authored candidate.
engine=Path('/opt/homebrew/bin/tesseract');renderer=Path('/opt/homebrew/bin/pdftoppm');model=Path('/opt/homebrew/share/tessdata/eng.traineddata')
assert sys.platform=='darwin' and all(p.is_file() for p in (engine,renderer,model)), 'qualified optional native tools required for this drill'
conf=write('ocr.json',dict(outputDirectory=str(work/'ocr'),engine=str(engine),engineSha256=hash_bytes(engine.read_bytes()),renderer=str(renderer),rendererSha256=hash_bytes(renderer.read_bytes()),model=str(model),rotation=0))
packet=work/'packet'
run('--vault',vault,'intake','add',fixtures/'ocr/complete-scan.pdf','--person',person,'--packet',packet,'--confirm-person','--ocr-config',conf)
meta=decode_json((packet/'intake.json').read_bytes());context=decode_json((packet/'context/context.json').read_bytes())
extraction=meta['extraction']['pagesSha256'];assert context['selectedExtractions'][0]['sha256']==extraction
artifact=decode_json((vault/'people'/person/'assets/sha256'/extraction/'blob').read_bytes())
assert artifact['pages'][0]['unresolvedRegions'] and artifact['extraction']['method']=='ocr'
example=Path(sys.prefix)/'share/helseark/agent-kit/examples'
def bound(name):
    data=(example/name).read_bytes()
    for key,value in {b'11111111-1111-4111-8111-111111111111':person.encode(),b'SOURCE_HASH':meta['source']['sourceSha256'].encode(),b'EXTRACTION_HASH':extraction.encode()}.items():data=data.replace(key,value)
    return decode_json(data)
bundle=bound('task5-bundle.json');evidence=bound('task5-evidence.json')
for e in evidence['entries']:
    if e['kind']=='source':e['extraction']=artifact['extraction']
candidate=work/'ocr-candidate';candidate.mkdir()
metadata=dict(contractVersion='0.1.0',fhirVersion='4.0.1',profileVersion='0.2.0',candidateId=meta['importId'],personId=person,baseChangeSha256=context['base']['changeSha256'],sourceSha256=[meta['source']['sourceSha256']],bundlePath='bundle.json',evidencePath='evidence.json',producer={'kind':'local-user','name':'SYNTHETIC pre-authored OCR oracle; no model'},producerProvenance=evidence['producerProvenance'],unresolved=meta['issues'])
for name,value in [('candidate',metadata),('bundle',bundle),('evidence',evidence)]: (candidate/(name+'.json')).write_bytes(encode_json(value))
approve(candidate,person)
rows=run('--vault',vault,'observations','--person',person);assert len(rows)==5
q=next(r for r in rows if r['code'].get('text')=='Analyte Q')
assert str(q['value']['value'])=='0.050' and q['comparator']=='<' and q['unit']=='mg/L' and q['effective']=='2026-01'
assert sum(str(r['value'].get('value'))=='0.0500' for r in rows if isinstance(r['value'],dict))==2
selected=run('--vault',vault,'history','--person',person,*kind_args);facts(selected)
def inventory():
    return {str(p.relative_to(vault)):{'sha256':hash_bytes(p.read_bytes()),'size':p.stat().st_size}
            for p in (vault/'people'/person).rglob('*') if p.is_file() and '/work/' not in str(p)}
before=inventory();write('before.json',before)
report=work/'report';run('--vault',vault,'report','--person',person,'--out',report)
svg=ET.fromstring((report/'report.svg').read_bytes());text=''.join(svg.itertext())
assert all(x in text for x in ('1.250','2.500','0.500','45.00','cancelled','unconfirmed'))
assert 'PRIVATE_OTHER_PERSON' not in text and not svg.findall('.//{http://www.w3.org/2000/svg}script')
assert len(list(csv.DictReader((report/'observations.csv').open())))==5
first={p.name:p.read_bytes() for p in report.iterdir()};shutil.rmtree(report)
run('--vault',vault,'report','--person',person,'--out',report);assert first=={p.name:p.read_bytes() for p in report.iterdir()}
assert run('--vault',vault,'report','--person',person,'--out',report,expected=2)['code']=='DESTINATION_EXISTS'
assert inventory()==before
# Household operations explicitly read both people.
env['UNION_DENY']=str(checkout)
assert not run('--vault',vault,'doctor')['issues']
backup=work/'backup';run('--vault',vault,'backup','create','--out',backup)
assert not run('backup','verify',backup)['issues']
recovered=work/'restored';run('backup','restore',backup,'--into',recovered)
facts(run('--vault',recovered,'history','--person',person,*kind_args))
assert run('--vault',recovered,'observations','--person',person)==rows
assert len(run('--vault',recovered,'observations','--person',other))==1
assert all(hash_bytes((recovered/path).read_bytes())==v['sha256'] for path,v in before.items())
assert not run('--vault',recovered,'doctor')['issues']
write('result.json',dict(people=2,families=8,independentFacts=43,absences=12,observations=5,otherObservations=1,denialWitnesses=witnesses,commands=len(commands),protectedFiles=len(before),nativePins=decode_json(conf.read_bytes()),history=selected,rows=rows))
print('PASS: installed two-person FHIR/history/CSV/actual-OCR/report/recovery union',flush=True)
