"""Standalone installed query qualification with checkout/network/other person denied.

Arguments: fresh workdir, denied checkout, synthetic source vault, selected person,
old Head JSON, forbidden person. Copy this script outside the checkout first.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys

work,checkout,source=map(lambda x:Path(x).resolve(),sys.argv[1:4])
person,old_head,other=sys.argv[4:7]
work.mkdir()
root=work/'vault';shutil.copytree(source,root)
for path in (root/'.runtime',root/'derived',root/'people'/person/'work'):
    if path.exists():shutil.rmtree(path)
# Real unrelated corruption must never be inspected by selected-person reads.
unrelated=next((root/'people'/other/'accepted').glob('*/resources/*.json'))
unrelated.write_bytes(b'UNRELATED SYNTHETIC CORRUPTION')
head=work/'head.json';shutil.copyfile(old_head,head)
import helseark.archive as archive
from helseark.serialization import decode_json,hash_bytes
assert not Path(archive.__file__).resolve().is_relative_to(checkout)
console=Path(sys.executable).parent/'helseark'
guard=work/'guard';guard.mkdir()
events=work/'events'
(guard/'sitecustomize.py').write_text('''
import os,sys
def audit(event,args):
    if event.startswith(('socket.','urllib.')):
        with open(os.environ['QUERY_EVENTS'],'a') as f:f.write(event+'\\n')
        raise RuntimeError('network forbidden')
    if event in ('open','os.scandir','os.listdir'):
        for name in ('QUERY_CHECKOUT','QUERY_OTHER'):
            if str(args[0]).startswith(os.environ[name]):raise RuntimeError('out-of-scope read')
sys.addaudithook(audit)
''')
env={**os.environ,'PYTHONPATH':str(guard),'QUERY_EVENTS':str(events),
     'QUERY_CHECKOUT':str(checkout),'QUERY_OTHER':str(root/'people'/other)}
probe=subprocess.run([sys.executable,'-c','import socket;socket.socket()'],env=env,capture_output=True,cwd=work)
assert probe.returncode!=0 and events.read_text().startswith('socket.')
events.unlink()
def run(command,*args):
    result=subprocess.run([str(console),'--vault',str(root),command,'--person',person,*map(str,args),'--json'],
        cwd=work,env=env,capture_output=True)
    assert result.returncode==0,result.stderr
    return decode_json(result.stdout)
rows=run('observations')
assert len(rows)==7
month=next(r for r in rows if r['timePrecision']=='month')
assert str(month['value']['value'])=='0.0750' and month['comparator']=='<'
assert month['unit']=='mg/L' and month['referenceRanges']==[{'text':'0–1'}]
assert any(r['timeBucket']=='unknown' and r['value']=={'text':'Negative'} for r in rows)
assert any(r['unit']=='mg/dL' and str(r['value']['value'])=='1.2300' for r in rows)
all_rows=run('observations','--include-invalidated')
assert len(all_rows)==9 and any(r['status']=='cancelled' for r in all_rows)
selected=run('observations','--from-date','2026-11-14','--to-date','2026-11-14')
assert len(selected)==5
assert next(r for r in selected if r['timePrecision']=='month')['timeFilterRelation']=='overlap'
events_now=run('timeline')
report=next(r for r in events_now if r['resourceRef']['resourceType']=='DiagnosticReport')
assert 'REPORT_RESULT_REVISION_MISMATCH' in {i['code'] for i in report['issues']}
child=report['resultRefs'][0]
reference=f"{child['resourceType']}/{child['id']}/_history/{child['versionId']}"
assert str(run('record','--resource',reference)['valueQuantity']['value'])=='0.050'
assert str(next(r for r in run('observations','--at-head',head) if r['timePrecision']=='month')['value']['value'])=='0.050'
# Verify source binding meaning, not only the presence of a projection field.
for row in rows:
    for binding in row['sourceRefs']:
        data=(root/binding['evidencePath']).read_bytes()
        assert hash_bytes(data)==binding['evidenceSha256']
        evidence=decode_json(data)['entries'][int(binding['entryPointer'].split('/')[-1])]
        assert evidence.get('target',{}).get('reference')==f"Observation/{row['resourceRef']['id']}/_history/{row['resourceRef']['versionId']}"
        if binding['sourceSha256']:
            assert (root/'people'/person/'assets/sha256'/binding['sourceSha256']/'blob').is_file()
            assert evidence['locator'] and evidence['quote']
# Installed docs and the query kit's direct relative links form an asset closure.
kit=root/'agent-kit'/archive._open_vault_metadata(root).config.agentKitVersion
for path in (kit/'skills/query-history/SKILL.md',kit/'prompts/query-with-evidence.md',kit/'docs/how-to/query-history.md'):
    assert path.is_file()
    for link in re.findall(r'\]\(([^)]+)\)',path.read_text()):
        link=link.split('#',1)[0]
        if link and '://' not in link:
            assert (path.parent/link).resolve().is_file(),(path,link)
assert not events.exists()
print('{"installedQueryRows":7,"historyRows":9,"calendarRows":5,"modelRuns":0,"networkAttempts":0,"otherPersonReads":0,"historicalReportChild":"0.050","currentValue":"0.0750","assetClosure":true}')
