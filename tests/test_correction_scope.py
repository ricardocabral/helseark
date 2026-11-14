"""The public correction route admits only selected accepted history."""
from pathlib import Path
import os
import subprocess
import sys
from test_intake import supplied_candidate
from test_review import approve
from helseark.archive import add_person,commit_candidate,iter_current
from helseark.contracts import PersonDraft
from helseark.intake import add_source,build_packet,read_candidate,prepare_candidate


def test_correct_ignores_denied_and_corrupt_other_nonempty_history(tmp_path):
    v,p,source,packet,c=supplied_candidate(tmp_path)
    proposal=prepare_candidate(v,c);commit_candidate(v,proposal,approve(v,proposal))
    q=add_person(v,PersonDraft('Avery Synthetic'))
    second=build_packet(v,add_source(v,q,source.assetPath),tmp_path/'packet-q',identityConfirmed=True)
    script=Path(__file__).resolve().parents[1]/'agent-kit/examples/task5-example.py'
    subprocess.run([sys.executable,str(script),str(second.path),str(tmp_path/'candidate-q')],check=True,capture_output=True)
    proposal=prepare_candidate(v,read_candidate(v,tmp_path/'candidate-q'));commit_candidate(v,proposal,approve(v,proposal))
    assert len([r for r in iter_current(v,q) if r['resourceType']=='Observation'])==2
    target=next(r for r in iter_current(v,p) if r['resourceType']=='Observation')
    witness=next((v.root/'people'/q).rglob('change.json'))
    harness=tmp_path/'guard.py'
    harness.write_text('''import os,sys
from pathlib import Path
other=Path(sys.argv.pop(1));witness=Path(sys.argv.pop(1))
def deny(event,args):
 if event in ('open','os.listdir','os.scandir') and args and isinstance(args[0],(str,bytes)):
  if Path(os.fsdecode(args[0])).absolute().is_relative_to(other):raise PermissionError('OTHER_PERSON_DENIED')
sys.addaudithook(deny)
try:witness.read_bytes()
except PermissionError:print('ACTIVE_OTHER_PERSON_WITNESS',file=sys.stderr)
else:raise AssertionError('denial inactive')
from helseark.cli import main
sys.exit(main())
''')
    args=['--vault',str(v.root),'correct','--person',p,'--resource','Observation/'+target['id'],'--reason','transcription: synthetic source checked','--json']
    child=subprocess.run([sys.executable,str(harness),str(v.root/'people'/q),str(witness),*args],capture_output=True)
    assert b'ACTIVE_OTHER_PERSON_WITNESS' in child.stderr
    assert child.returncode==0,child.stderr
    witness.write_bytes(b'{corrupt unrelated accepted history')
    child=subprocess.run([sys.executable,'-m','helseark.cli',*args],capture_output=True)
    assert child.returncode==0,child.stderr
    # Erasure remains explicitly global and rejects that same corruption.
    child=subprocess.run([sys.executable,'-m','helseark.cli','--vault',str(v.root),'erase','plan','--person',p,
                          '--quarantine',str(tmp_path/'quarantine'),'--out',str(tmp_path/'plan.json'),'--json'],capture_output=True)
    assert child.returncode==5,child.stderr
