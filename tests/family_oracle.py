"""Independent expected-facts ledger compared with measured behavior, not importer output."""
import json
import os
from pathlib import Path

LEDGER=Path(__file__).resolve().parents[1]/'examples/synthetic-family/expected-facts.json'


def check_case(identifier, actual, checked):
    ledger=json.loads(LEDGER.read_text())
    case=next(c for c in ledger['cases'] if c['id']==identifier)
    expected={k:v for k,v in case.items() if k not in ('id','coverage')}
    assert actual==expected, (identifier,actual,expected)
    assert set(checked)<=set(case['coverage'])
    # Optional retained evidence; ordinary pytest needs no writable source tree.
    if destination:=os.environ.get('HELSEARK_FAMILY_LEDGER_RESULTS'):
        path=Path(destination)
        results=json.loads(path.read_text()) if path.exists() else {
            'synthetic':True,'modelRuns':0,'cases':{c['id']:{'result':'not-checked',
                'coverage':{label:'not-checked' for label in c['coverage']}} for c in ledger['cases']},
            'notChecked':ledger['notChecked']}
        results['cases'][identifier]={'result':'checked','actual':actual,
            'coverage':{label:'checked' if label in checked else 'not-checked' for label in case['coverage']}}
        path.write_text(json.dumps(results,indent=2)+'\n')
