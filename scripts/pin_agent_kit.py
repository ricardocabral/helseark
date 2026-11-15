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
    history_profiles = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'profiles/r4/0.2.0').glob('StructureDefinition-*.json'))]
    manifest['baseInstructionPaths'] = ['START-HERE.md','AGENTS.md']
    skills = dict(zip(['inspect','import','query','correct','export','verify','migrate'],
        ['inspect-archive','import-records','query-history','correct-records','export-records','verify-archive','migrate-archive']))
    routes = {'import':['extract-report','map-structured-export'],'query':['query-with-evidence'],
        'correct':['propose-correction'],'export':['prepare-export'],'verify':['verify-archive'],'migrate':['plan-migration'],'inspect':[]}
    prompts=[]
    for task in manifest['tasks']:
        if task['id'] in ('import', 'query'):
            task['schemaPaths'] = list(dict.fromkeys([*task['schemaPaths'], *history_profiles]))
        if task['id'] == 'query':
            task['permittedOperations'] = list(dict.fromkeys([*task['permittedOperations'], 'helseark --vault PATH history --person UUID --kind MedicationStatement --json']))
        task['schemaPaths']=list(dict.fromkeys([*task['schemaPaths'],'schemas/0.1.0/agent-evidence-selection.schema.json']))
        task['skillPath']=f"skills/{skills[task['id']]}/SKILL.md"
        task['promptIds']=routes[task['id']]
        task['scenarioId']=task['promptIds'][0] if task['promptIds'] else 'inspect-routing'
        task['referencePaths']=list(dict.fromkeys([*task['referencePaths'],'docs/reference/archive-format.md',
            *(['docs/how-to/query-history.md','docs/how-to/generate-reports.md'] if task['id']=='query' else [])]))
        if task['id']=='correct':
            task['referencePaths']=list(dict.fromkeys([*task['referencePaths'],'docs/how-to/correct-record.md','docs/how-to/manage-family.md']))
        if task['id']=='migrate':
            task['referencePaths']=list(dict.fromkeys([*task['referencePaths'],'docs/how-to/migrate-archive.md','docs/reference/compatibility.md']))
            task['schemaPaths']=list(dict.fromkeys([*task['schemaPaths'],'schemas/0.1.0/migration.schema.json']))
        if task['id']=='import':
            task['permittedOperations']=list(dict.fromkeys([*task['permittedOperations'], 'helseark --vault PATH intake fhir-r4 SOURCE --person UUID --mapping CONFIG --json', 'helseark --vault PATH intake metrics-csv SOURCE --person UUID --mapping CONFIG --json']))
            task['referencePaths']=list(dict.fromkeys([*task['referencePaths'],'docs/how-to/import-structured-data.md']))
        if task['id'] in ('export','verify'):
            task['expectedChecks']=list(dict.fromkeys([*task['expectedChecks'], 'known-material-closure', 'readable-audit-paths',
                'exact-reference-bindings' if task['id']=='export' else 'diagnostic-path-actions']))
            task['referencePaths']=list(dict.fromkeys([*task['referencePaths'],'docs/how-to/export-records.md','docs/how-to/backup-and-restore.md']))
        if task['id']=='verify':
            task['expectedChecks']=list(dict.fromkeys([*task['expectedChecks'],'original-official-execution-authority','complete-baseline-reconciliation','failed-request-revocation']))
            task['referencePaths']=list(dict.fromkeys([*task['referencePaths'],'docs/how-to/run-offline-validator.md']))
        task['outputs']=['output/report.md'] + (['output/candidate/candidate.json','output/candidate/bundle.json','output/candidate/evidence.json'] if task['id'] in ('import','correct') else [])
        task['requiredCapabilities']={
            'inspect':['agent-discovery','agent-context','task-instructions'],
            'import':['agent-context','schema-export','baseline-validation','task-instructions','pdf-intake','fhir-r4-import','csv-metrics-import','reviewed-publication'],
            'query':['agent-context','task-instructions','clinical-query'],
            'correct':['agent-context','baseline-validation','task-instructions','correction','reviewed-publication'],
            'export':['agent-context','task-instructions','person-export','reviewed-source-disclosure'],
            'verify':['agent-context','task-instructions','integrity-report'],
            'migrate':['agent-context','task-instructions','migration']}[task['id']]
        missing=[c for c in task['requiredCapabilities'] if c not in ['agent-discovery','agent-context','schema-export','baseline-validation','person-identity','raw-record-selection','task-instructions','pdf-intake','candidate-read','clinical-query','reviewed-publication','person-export','reviewed-source-disclosure','integrity-report','correction','migration','fhir-r4-import','csv-metrics-import']]
        task['availability']={'status':'unavailable' if missing else 'available','missingCapabilities':missing}
        for name in task['promptIds']:
            path=f'prompts/{name}.md'; data=(kit/path).read_bytes()
            specs={}
            for slot in sorted(set(re.findall(r'{{\s*([a-z][a-z0-9_]*)\s*}}',data.decode()))):
                typ='boolean' if slot.endswith('_confirmed') else 'object' if slot in ('source_data','scope') else 'array' if slot in ('capabilities','source_hashes') else 'string'
                spec={'type':typ,'required':slot!='request','maxBytes':8192 if slot=='request' else 262144 if slot=='source_data' else 32768}
                if slot=='request': spec['default']=''
                if slot=='base_change_sha256': spec.update(nullable=True,pattern='[0-9a-f]{64}')
                if slot in ('candidate_id','person_id'): spec['pattern']='[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
                if slot=='source_hashes': spec.update(minItems=1,uniqueItems=True)
                specs[slot]=spec
            prompts.append({'id':name,'version':'0.1.3' if name in ('extract-report','map-structured-export') else '0.1.1' if name in ('query-with-evidence','propose-correction','plan-migration') else '0.1.0','path':path,'sha256':digest(data),'taskIds':[task['id']],
                'variables':specs,'skillId':skills[task['id']],'skillVersion':'0.1.5' if task['id']=='import' else '0.1.1' if task['id'] in ('query','correct','migrate') else '0.1.0','skillSha256':digest((kit/task['skillPath']).read_bytes()),'inputContractIds':['urn:helseark:schema:0.1.0:agent-context','urn:helseark:schema:0.1.0:agent-evidence-selection','urn:helseark:schema:0.1.0:evidence'],
                'outputContractIds':['urn:helseark:schema:0.1.0:candidate','urn:helseark:schema:0.1.0:evidence'] if task['id'] in ('import','correct') else [],
                'outputArtifacts':task['outputs']})
    manifest['prompts']=prompts
    # References have one repository source; release copies make every relative link portable.
    references=['LICENSE','NOTICE','docs/index.md'] + [p.relative_to(ROOT).as_posix() for folder in ('tutorials','how-to','reference','explanation') for p in sorted((ROOT/'docs'/folder).glob('*.md'))] + ['definitions/validator-lock.json','definitions/validator-notices.json']
    schemas=sorted({m.group(1) for p in kit.rglob('*.md') for m in re.finditer(r'\]\([^)]*?(schemas/[^)#]+)',p.read_text())})
    references += [p for p in schemas if (ROOT/p).is_file()]
    references += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'schemas').glob('*/*.json'))]
    references += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'profiles/r4').glob('*/*')) if p.is_file()]
    references = list(dict.fromkeys(references))
    for name in references:
        target=kit/name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(ROOT/name,target)
    lock_path=ROOT/'definitions/lock.json'; lock=json.loads(lock_path.read_text())
    for name in references:
        if not any(f['path']==name for a in lock['artifacts'] for f in a['files']):
            version=Path(name).parent.name if name.startswith('schemas/') else '0.1.0'
            lock['artifacts'].append({'packageId':'helseark-reference-'+Path(name).stem,'version':version,'license':'MIT','origin':'repository-authored','files':[{'path':name}]})
    for artifact in lock['artifacts']:
        for entry in artifact['files']:
            data=(ROOT/entry['path']).read_bytes(); entry.update(sha256=digest(data),size=len(data))
    write(lock_path,lock)
    manifest['compatibility']['definitionLockSha256']=digest(lock_path.read_bytes())
    (kit/'definitions').mkdir(exist_ok=True)
    shutil.copyfile(lock_path,kit/'definitions/lock.json')
    manifest['files']=[{'path':p.relative_to(kit).as_posix(),'sha256':digest(p.read_bytes()),'size':p.stat().st_size} for p in sorted(kit.rglob('*')) if p.is_file() and p.name!='manifest.json']
    write(kit/'manifest.json',manifest)

if __name__=='__main__':
    pin()
