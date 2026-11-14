"""Refresh local release copies and pins from bytes, offline and without cycles."""
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]

def digest(data):
    return hashlib.sha256(data).hexdigest()

def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)+'\n')

def pin():
    kit = ROOT/'agent-kit'
    manifest = json.loads((kit/'manifest.json').read_text())
    manifest['baseInstructionPaths'] = ['START-HERE.md','AGENTS.md']
    skills = dict(zip(['inspect','import','query','correct','export','verify','migrate'],
        ['inspect-archive','import-records','query-history','correct-records','export-records','verify-archive','migrate-archive']))
    routes = {'import':['extract-report','map-structured-export'],'query':['query-with-evidence'],
        'correct':['propose-correction'],'export':['prepare-export'],'verify':['verify-archive'],'migrate':['plan-migration'],'inspect':[]}
    prompts=[]
    for task in manifest['tasks']:
        task['schemaPaths']=list(dict.fromkeys([*task['schemaPaths'],'schemas/0.1.0/agent-evidence-selection.schema.json']))
        task['skillPath']=f"skills/{skills[task['id']]}/SKILL.md"
        task['promptIds']=routes[task['id']]
        task['scenarioId']=task['promptIds'][0] if task['promptIds'] else 'inspect-routing'
        task['referencePaths']=list(dict.fromkeys([*task['referencePaths'],'docs/reference/archive-format.md',
            *(['docs/how-to/query-history.md'] if task['id']=='query' else [])]))
        task['outputs']=['output/report.md'] + (['output/candidate/candidate.json','output/candidate/bundle.json','output/candidate/evidence.json'] if task['id'] in ('import','correct') else [])
        task['requiredCapabilities']={
            'inspect':['agent-discovery','agent-context','task-instructions'],
            'import':['agent-context','schema-export','baseline-validation','task-instructions','pdf-intake','structured-import','reviewed-publication'],
            'query':['agent-context','task-instructions','clinical-query'],
            'correct':['agent-context','baseline-validation','task-instructions','correction','reviewed-publication'],
            'export':['agent-context','task-instructions','person-export'],
            'verify':['agent-context','task-instructions','integrity-report'],
            'migrate':['agent-context','task-instructions','migration']}[task['id']]
        missing=[c for c in task['requiredCapabilities'] if c not in ['agent-discovery','agent-context','schema-export','baseline-validation','person-identity','raw-record-selection','task-instructions','pdf-intake','candidate-read','clinical-query','reviewed-publication']]
