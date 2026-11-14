"""Installed, offline report corpus and adversarial directory qualification.

Copy outside checkout, then run with installed Python:
  script.py WORK EVIDENCE EXACT_SOURCE PRIMARY
WORK/cases.json names retained accepted synthetic corpus/adversarial vault copies.
No extraction/model run or clinical import authority is implied by these fixtures.
"""
from pathlib import Path
import os,sys,subprocess,json,csv,hashlib,shutil
from html.parser import HTMLParser
from urllib.parse import urlparse,unquote
work,out,checkout,primary=map(lambda p:Path(p).resolve(),sys.argv[1:5]);cases=json.loads((work/'cases.json').read_text());console=Path(sys.executable).parent/'helseark'
guard=work/'guard';guard.mkdir()
(guard/'sitecustomize.py').write_text('''import os,sys,signal
from pathlib import Path
roots=[Path(p) for p in os.environ['DENY_ROOTS'].split(os.pathsep)]
def audit(event,args):
 if event.startswith(('socket.','urllib.')):raise RuntimeError('DENIED_NETWORK')
 if event in ('open','os.scandir','os.listdir') and args and isinstance(args[0],(str,bytes)):
  path=Path(os.fsdecode(args[0])).resolve()
  if any(path.is_relative_to(p) for p in roots):raise RuntimeError('DENIED_READ')
 if os.environ.get('FAIL_CSV') and event=='open' and str(args[0]).endswith('observations.csv') and args[2] & os.O_WRONLY:raise OSError('INJECTED_WRITE_FAILURE')
sys.addaudithook(audit)
''')
def env(case):
 return {**os.environ,'PYTHONPATH':str(guard),'DENY_ROOTS':os.pathsep.join([str(primary),str(checkout),case['vault']+'/people/'+case['other']])}
def inventory(root):
 return {str(p.relative_to(root)):{'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in root.rglob('*') if p.is_file() and 'derived' not in p.relative_to(root).parts}
def call(c,*args,expected=0,extra=None):
 p=subprocess.run([str(console),'--vault',c['vault'],*map(str,args),'--json'],cwd=work,env={**env(c),**(extra or {})},capture_output=True)
 assert p.returncode==expected,(args,p.returncode,p.stdout,p.stderr)
 return json.loads(p.stdout if expected==0 else p.stderr)
class Page(HTMLParser):
 def __init__(self,text):super().__init__();self.tags=[];self.links=[];self.metas=[];self.text='';self.feed(text)
 def handle_starttag(self,tag,attrs):
  self.tags.append(tag);self.links.extend(v for k,v in attrs if k=='href')
  if tag=='meta':self.metas.append(dict(attrs))
  assert not any(k.startswith('on') for k,v in attrs)
 def handle_data(self,text):self.text+=text
initialized=subprocess.run([str(console),'init',str(work/'installed-init'),'--json'],cwd=work,env=env(cases['corpus']),capture_output=True)
assert initialized.returncode==0,initialized.stderr
results=[]
for name,c in cases.items():
 root=Path(c['vault']);before=inventory(root)
 excluded_file=next((root/'people'/c['other']/'accepted').rglob('Observation-*.json'))
 assert excluded_file.is_file()
 probes=['import socket; socket.socket()',f'open({str(excluded_file)!r})',f'open({str(primary/"pyproject.toml")!r})',f'open({str(checkout/"pyproject.toml")!r})']
 for probe in probes:
  p=subprocess.run([sys.executable,'-c',probe],env=env(c),cwd=work,capture_output=True);assert p.returncode and b'DENIED_' in p.stderr,(probe,p.stderr)
 index=Path(call(c,'report','--person',c['person'])['path']);html=index.read_text();page=Page(html)
 rows=list(csv.DictReader((index.parent/'observations.csv').open(newline='')));byid={json.loads(r['resourceRef'])['id']:r for r in rows}
 assert c['other'] not in html and 'PRIVATE OTHER PERSON' not in html and 'OTHER PERSON SECRET' not in html
 assert not {'script','img','iframe','object','link','form','base'}&set(page.tags)
 csp=next(m['content'] for m in page.metas if m.get('http-equiv')=='Content-Security-Policy');assert "default-src 'none'" in csp and "base-uri 'none'" in csp and "form-action 'none'" in csp
 assert all(l in ('observations.csv','report.svg') or l.startswith('file://') for l in page.links)
 for l in page.links:
  if l.startswith('file://'):
   u=urlparse(l);p=Path(unquote(u.path));assert p.is_file() and p.name=='evidence.json' and p.is_relative_to(root/'people'/c['person']);assert u.fragment.startswith('/entries/')
   evidence=json.loads(p.read_text());entry=evidence['entries'][int(u.fragment.split('/')[-1])];assert entry
 if name=='corpus':
  assert len(rows)==9;ids=c['ids']
  r=byid[ids['month']];assert r['comparator']=='<' and '0.050' in r['value'] and r['timePrecision']=='month' and r['effective']=='2026-11'
  r=byid[ids['day']];assert '1.2300' in r['value'] and r['unit']=='mg/dL' and r['referenceRanges']=='[\n  {\n    "text": "2–4"\n  }\n]'
  assert byid[ids['month']]['specimenRef']!=r['specimenRef'] and byid[ids['month']]['method']!=r['method']
  assert byid[ids['cancelled']]['value']=='null' and 'Not performed' in byid[ids['cancelled']]['dataAbsentReason']
  assert byid[ids['offset']]['value']=='false' and byid[ids['unknown']]['timePrecision']=='unknown' and 'Negative' in byid[ids['unknown']]['value']
  assert byid[ids['error']]['status']=='entered-in-error' and byid[ids['cancelled']]['status']=='cancelled'
  assert '2.50' in byid[ids['period']]['value'] and '4.00' in byid[ids['period']]['value']
 else:
  assert len(rows)==14
  for rid,f in c['facts'].items():
   r=byid[rid];label=f['label'];expected="'"+label if label.lstrip('\x00\ufeff\u200b \t\r\n').startswith(('=','+','-','@')) or label.startswith(('\t','\r','\n')) else label
   assert r['sourceLabel']==expected
   assert r['valueType']==next((k for k in f if k.startswith('value')),'null')
   if 'valueBoolean' in f:assert r['value']=='false'
   if 'valueInteger' in f:assert r['value']=="'-7"
   if 'dataAbsentReason' in f:assert r['value']=='null'
   if 'valueQuantity' in f:assert '0.000' in r['value']
   if 'valueString' in f:assert json.loads(r['value'])==f['valueString']
  assert '&lt;img' in html and '&lt;script&gt;' in html
 original={p.name:p.read_bytes() for p in index.parent.iterdir()};shutil.rmtree(root/'derived');call(c,'report','--person',c['person']);assert original=={p.name:p.read_bytes() for p in index.parent.iterdir()}
 assert call(c,'report','--person',c['person'],expected=2)['code']=='DESTINATION_EXISTS'
 ext=work/(name+'-external')/'nested/report';call(c,'report','--person',c['person'],'--out',ext);assert original=={p.name:p.read_bytes() for p in ext.iterdir()}
 rejects=[]
 for i,target in enumerate([root/'people'/c['person']/'accepted/new-report',root/'definitions/new-report',root/'agent-kit/new-report',root/'derived/../people/new-report']):
  assert call(c,'report','--person',c['person'],'--out',target,expected=2)['code']=='INVALID_DESTINATION';assert not target.exists();rejects.append(str(target))
 for label,dest in [('protected',root/'people'/c['person']/'accepted'),('external',work/'redirect-external'),('dangling',work/'no-such-dir')]:
  link=work/(name+'-link-'+label);link.symlink_to(dest,target_is_directory=True)
  assert call(c,'report','--person',c['person'],'--out',link/'new-report',expected=2)['code']=='INVALID_DESTINATION';assert not (dest/'new-report').exists();rejects.append(str(link))
 failed=work/(name+'-partial');assert call(c,'report','--person',c['person'],'--out',failed,expected=5,extra={'FAIL_CSV':'1'})['code']=='IO_ERROR';assert not failed.exists();assert not list(work.glob('.helseark-report-*'))
 assert before==inventory(root)
 (out/(name+'-before.json')).write_text(json.dumps(before,indent=2));(out/(name+'-after.json')).write_text(json.dumps(inventory(root),indent=2))
 results.append({'case':name,'rows':len(rows),'unchangedFiles':len(before),'unchangedBytes':sum(e['size'] for e in before.values()),'denialWitnesses':len(probes),'redirectAndProtectedRefusals':len(rejects),'sourceLinks':sum(l.startswith('file://') for l in page.links),'htmlSha256':hashlib.sha256(original['index.html']).hexdigest(),'csvSha256':hashlib.sha256(original['observations.csv']).hexdigest(),'controlPrefixes':[{ 'label':repr(f['label']),'csvPrefix':repr(byid[rid]['sourceLabel'][:5])} for rid,f in c.get('facts',{}).items()]})
 print(json.dumps(results[-1]),flush=True)
(out/'installed-results.json').write_text(json.dumps(results,indent=2)+'\n')

# Mutate actual checked parents at real mkdir/native-symbol lookup boundaries.
# The ordinary corpus above already proved native facts and isolation; these
# copies prove that errors and competing writers do not alter canonical files.
race_guard = work/'race-guard'
race_guard.mkdir()
(race_guard/'sitecustomize.py').write_text((guard/'sitecustomize.py').read_text() + r'''
armed = True
def mutate(event,args):
 global armed
 action=os.environ['RACE_ACTION']
 late=action.endswith('_late')
 trigger=(event=='ctypes.dlsym' and args[1] in ('renameatx_np','renameat2')) if late else (event=='os.mkdir' and str(args[0]).startswith('.helseark-report-'))
 if armed and trigger:
  armed=False
  action=action.removesuffix('_late')
  parent=Path(os.environ['RACE_PARENT']);protected=Path(os.environ['RACE_PROTECTED'])
  if action.startswith('compete'):
   dest=parent/'report';dest.mkdir()
   if action=='compete':(dest/'sentinel').write_bytes(b'competing writer')
   print('COMPETITOR_INODE:'+str(dest.stat().st_ino),file=sys.stderr)
  else:
   parent.rename(protected/'relocated' if action=='relocate' else parent.with_name('original'))
   if action=='replace':parent.mkdir()
   else:parent.symlink_to(protected,target_is_directory=True)
  print('ACTUAL_MUTATION:'+action,file=sys.stderr)
sys.addaudithook(mutate)
''')
races=[]
for phase in ('','_late'):
 for action in ('redirect','replace','relocate','compete','compete_empty'):
  name=action+phase
  area=work/('race-'+name);area.mkdir()
  c=dict(cases['corpus']);root=area/'vault'
  shutil.copytree(c['vault'],root,ignore=shutil.ignore_patterns('derived'))
  c['vault']=str(root)
  parent=area/'parent';parent.mkdir()
  protected=root/'people'/c['person']/'accepted'
  before=inventory(root)
  extra={'PYTHONPATH':str(race_guard),'RACE_PARENT':str(parent),'RACE_PROTECTED':str(protected),'RACE_ACTION':name}
  child=subprocess.run([str(console),'--vault',str(root),'report','--person',c['person'],'--out',str(parent/'report'),'--json'],cwd=work,env={**env(c),**extra},capture_output=True)
  stderr=child.stderr.decode()
  assert 'ACTUAL_MUTATION:' in stderr,(name,stderr)
  assert child.returncode==2,(name,child.returncode,stderr)
  error=json.loads(stderr[stderr.index('{'):])
  assert error['code']==('DESTINATION_EXISTS' if action.startswith('compete') else 'INVALID_DESTINATION')
  assert inventory(root)==before,(name,'canonical file additions or mutations')
  if action.startswith('compete'):
   expected={'sentinel':b'competing writer'} if action=='compete' else {}
   assert {p.name:p.read_bytes() for p in (parent/'report').iterdir()}==expected
   inode=int(stderr.split('COMPETITOR_INODE:')[1].splitlines()[0]);assert (parent/'report').stat().st_ino==inode
  elif action=='replace':assert not list(parent.iterdir())
  if (area/'original').exists():assert not list((area/'original').iterdir())
  races.append({'action':name,'exit':child.returncode,'code':error['code'],'unchangedCanonicalFiles':len(before),'witness':stderr[:stderr.index('{')].strip()})
  print(json.dumps(races[-1]),flush=True)
(out/'destination-results.json').write_text(json.dumps(races,indent=2)+'\n')

import helseark.presentation as presentation
import helseark.report_publication as publication
assert not Path(presentation.__file__).resolve().is_relative_to(checkout)
assert not Path(publication.__file__).resolve().is_relative_to(checkout)
print(json.dumps({'installedPresentation':presentation.__file__,'installedPublication':publication.__file__,
                  'console':str(console),'corpusRows':sum(r['rows'] for r in results),
                  'denialWitnesses':sum(r['denialWitnesses'] for r in results),'destinationRaces':len(races)}))
