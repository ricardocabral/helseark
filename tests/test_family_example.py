"""Execute the distributed example and compare the independently authored ledger."""
from pathlib import Path
import json
import subprocess
import sys


def test_complete_executable_family_example(tmp_path):
    example=Path(sys.prefix)/'share/helseark/examples/synthetic-family/generate.py'
    if not example.is_file():example=Path(__file__).resolve().parents[1]/'examples/synthetic-family/generate.py'
    child=subprocess.run([sys.executable,str(example),str(tmp_path/'family'),'--synthetic-review-decisions'],capture_output=True)
    assert child.returncode==0,child.stderr
    result=json.loads((tmp_path/'family/result.json').read_text())
    ledger=json.loads((example.parent/'expected-facts.json').read_text())
    for case in ledger['cases']:
        if case['id'] in ('transcription','person-removal'):
            assert {k:result[k] for k in case if k not in ('id','coverage')}=={k:v for k,v in case.items() if k not in ('id','coverage')}
    assert result['clinicalPeople']==2 and result['doctor']['checkedResources']>0
    assert result['inventories']['beforeRestore']==result['inventories']['restored']
    assert len(result['inventories']['other'])>6
    assert all(c['exit']==c['expected'] for c in result['calls'])
