"""Synthetic migration behavior; predetermined candidates are not model evidence."""
from dataclasses import replace
from pathlib import Path
import os
import shutil
import subprocess
import sys
import pytest

from helseark.archive import init_vault, add_person, doctor, open_vault, commit_candidate
from helseark.contracts import ArchiveError, PersonDraft, ObservationFilter, VersionSet
from helseark.migrations import (CURRENT, open_migration_source, plan_migration,
    apply_migration, plan_fhir_migration, read_migration_plan)
from helseark.portability import backup, restore
from helseark.query import observations
from helseark.serialization import encode_json, decode_json, hash_bytes
from helseark.agent_context import document

FIXTURE = Path(__file__).parent/'fixtures/synthetic/migrations/legacy-test-only.json'


def legacy(tmp_path, vault):
    root=tmp_path/'legacy'; root.mkdir()
    shutil.copyfile(FIXTURE,root/'legacy-test-only.json')
    backup(vault,root/'snapshot',includeWork=True)
    return open_migration_source(root,allowTestFixture=True)


def small(tmp_path):
    v=init_vault(tmp_path/'source'); add_person(v,PersonDraft('Synthetic same name'))
    add_person(v,PersonDraft('Synthetic same name'))
    return v


def inventory(root):
    return {p.relative_to(root).as_posix():hash_bytes(p.read_bytes())
            for p in root.rglob('*') if p.is_file() and '.runtime' not in p.relative_to(root).parts}


def test_legacy_roundtrip_facts_reviews_history_and_exact_bytes(tmp_path):
    from test_intake import supplied_candidate
    from test_review import approve, rerun_candidate
    from helseark.intake import prepare_candidate
    v,p,source,_,c=supplied_candidate(tmp_path)
    proposal=prepare_candidate(v,c)
    with pytest.raises(ArchiveError): commit_candidate(v,proposal,None)
    commit_candidate(v,proposal,approve(v,proposal))
    before_facts=document(list(observations(v,p,ObservationFilter())))
    quantity=next(row for row in before_facts if isinstance(row['value'],dict))
    assert str(quantity['value']['value'])=='0.050'
    assert quantity['comparator']=='<' and quantity['effective']=='2026-01'
    c.bundle['entry'][0]['resource']['status']='amended'
    (c.path/'bundle.json').write_bytes(encode_json(c.bundle)); c=rerun_candidate(v,c)
    mapping={entry['fullUrl']:f"Observation/{next(row['resourceRef']['id'] for row in before_facts if row['code']['text']==entry['resource']['code']['text'])}"
             for entry in c.bundle['entry'] if entry['resource']['resourceType']=='Observation'}
    proposal=prepare_candidate(v,c,reextract=True,reconciliation=mapping)
    commit_candidate(v,proposal,approve(v,proposal))
    facts={person.name:encode_json(document(list(observations(v,person.name,ObservationFilter(includeInvalidated=True)))))
           for person in (v.root/'people').iterdir()}
    before=inventory(v.root)
    old=legacy(tmp_path,v); old_bytes=inventory(old.root)
    plan=plan_migration(old,CURRENT)
    assert plan.transformations==('test-only-layout-0-to-v1',)
    assert not plan.blockedRecords and not plan.semanticLosses
    assert inventory(old.root)==old_bytes  # planning has no writes
    assert plan.expectedCounts['changes']==4 and len(plan.sourceHeads)==2
    receipt=apply_migration(old,plan,tmp_path/'out',reviewedPlanSha256=plan.planSha256)
    assert receipt.originalUnchanged and receipt.validatedCounts==plan.expectedCounts
    out=open_vault(receipt.destination)
    assert not doctor(out).issues
    assert {person.name:encode_json(document(list(observations(out,person.name,ObservationFilter(includeInvalidated=True)))))
            for person in (out.root/'people').iterdir()}==facts
    for path,digest in before.items(): assert hash_bytes((out.root/path).read_bytes())==digest
    assert inventory(old.root)==old_bytes
    mapped=decode_json(receipt.mappingInventoryPath.read_bytes())
    assert len(mapped['byteMappings'])==len(before)
    for item in mapped['byteMappings']:
        assert item['sourcePath']=='snapshot/vault/'+item['destinationPath']
        assert item['oldSha256']==item['newSha256']==before[item['destinationPath']]
    assert plan.requiredDefinitions and any(x['path'].endswith('hl7.fhir.r4.core.tgz') for x in plan.requiredDefinitions)
    # Rollback is a real, independently verified Task8 restore drill.
    restored=restore(old.root/'snapshot',tmp_path/'recovered')
    assert all(hash_bytes((restored.root/path).read_bytes())==digest for path,digest in before.items())


def test_v1_identity_plan_and_explicit_review(tmp_path):
    v=small(tmp_path); before=inventory(v.root); plan=plan_migration(v,CURRENT)
    assert plan.transformations==('v1-identity-copy',)
    assert inventory(v.root)==before
    with pytest.raises(ArchiveError,match='REVIEW_REQUIRED'): apply_migration(v,plan,tmp_path/'out')
    with pytest.raises(ArchiveError,match='REVIEW_MISMATCH'):
        apply_migration(v,plan,tmp_path/'out',reviewedPlanSha256='0'*64)
    receipt=apply_migration(v,plan,tmp_path/'out',reviewedPlanSha256=plan.planSha256)
    assert receipt.originalUnchanged and len(plan.sourceHeads)==2
    assert all(hash_bytes((receipt.destination/p).read_bytes())==h for p,h in before.items())


@pytest.mark.parametrize('attack',['unknown-source','missing-definition','changed-file','changed-head','nonempty','empty','lossy','ambiguous','tamper','extra-field','unknown-target','symlink'])
def test_fail_closed(tmp_path,attack):
    v=small(tmp_path); plan=plan_migration(v,CURRENT); dest=tmp_path/'out'
    if attack=='unknown-source':
        config=decode_json((v.root/'vault.json').read_bytes()); config['archiveFormatVersion']=987
        (v.root/'vault.json').write_bytes(encode_json(config))
    elif attack=='missing-definition': next((v.root/'definitions').rglob('*.schema.json')).unlink()
    elif attack=='changed-file': (v.root/'README.md').write_bytes(b'changed')
    elif attack=='changed-head': add_person(v,PersonDraft('New synthetic'))
    elif attack in ('nonempty','empty'):
        dest.mkdir()
        if attack=='nonempty': (dest/'keep').write_bytes(b'keep')
    elif attack in ('lossy','ambiguous'):
        plan=(replace(plan,semanticLosses=({'reason':'drop values'},)) if attack=='lossy' else
              replace(plan,blockedRecords=({'code':'AMBIGUOUS_MAPPING','reason':'two possible targets'},)))
        raw=document(plan);raw.pop('planSha256')
        plan=replace(plan,planSha256=hash_bytes(encode_json(raw)))
    elif attack=='tamper': plan=replace(plan,expectedCounts={'changes':0,'resources':0,'assets':0})
    elif attack=='extra-field':
        raw=document(plan);raw['arbitraryCode']='bad';file=tmp_path/'plan.json';file.write_bytes(encode_json(raw))
        with pytest.raises(ArchiveError):read_migration_plan(file)
        return
    elif attack=='unknown-target': plan=plan_migration(v,replace(CURRENT,contractVersion='0.2.0'))
    elif attack=='symlink': (v.root/'foreign').symlink_to(tmp_path/'elsewhere')
    with pytest.raises(ArchiveError): apply_migration(v,plan,dest,reviewedPlanSha256=plan.planSha256)
    assert not dest.exists() or attack in ('nonempty','empty')
    if attack=='nonempty': assert (dest/'keep').read_bytes()==b'keep'


def test_legacy_requires_opt_in_and_strict_unambiguous_marker(tmp_path):
    v=small(tmp_path); old=legacy(tmp_path,v)
    with pytest.raises(ArchiveError): open_migration_source(old.root)
    raw=decode_json((old.root/'legacy-test-only.json').read_bytes());raw['snapshotPath']='../source'
    (old.root/'legacy-test-only.json').write_bytes(encode_json(raw))
    with pytest.raises(ArchiveError):open_migration_source(old.root,allowTestFixture=True)


def test_fhir_release_plan_is_separate_and_never_applies(tmp_path):
    v=small(tmp_path); plan=plan_fhir_migration(v,'5.0.0')
    assert plan.planClass=='fhir-release' and plan.blockedRecords and plan.semanticLosses
    with pytest.raises(ArchiveError):apply_migration(v,plan,tmp_path/'out',reviewedPlanSha256=plan.planSha256)
    assert not (tmp_path/'out').exists()


@pytest.mark.parametrize('boundary',['snapshot-ready','restore-copy','restored'])
def test_real_process_death_staging_and_explicit_resume(tmp_path,boundary):
    v=small(tmp_path); plan=plan_migration(v,CURRENT); before=inventory(v.root)
    planfile=tmp_path/'plan.json';planfile.write_bytes(encode_json(document(plan))); dest=tmp_path/'out'
    script='''
import os,sys
from pathlib import Path
from helseark import migrations as m
m._checkpoint=lambda point: os._exit(79) if point==sys.argv[4] else None
if sys.argv[4]=='restore-copy':
    from helseark import portability as port
    original=port._copy
    def die_mid_copy(source,target,paths):
        if target.name.startswith('.helseark-restore-'):
            original(source,target,[sorted(paths)[0]])
            os._exit(79)
        return original(source,target,paths)
    port._copy=die_mid_copy
v=m.open_migration_source(Path(sys.argv[1]));p=m.read_migration_plan(Path(sys.argv[2]))
m.apply_migration(v,p,Path(sys.argv[3]),reviewedPlanSha256=p.planSha256)
'''
    child=subprocess.run([sys.executable,'-c',script,str(v.root),str(planfile),str(dest),boundary],capture_output=True)
    assert child.returncode==79,child.stderr
    assert not dest.exists() and inventory(v.root)==before and not doctor(open_vault(v.root)).issues
    stages=list(tmp_path.glob('.helseark-migrate-*')); assert len(stages)==1
    assert (stages[0]/'owner.json').is_file()
    if boundary=='restore-copy':
        assert list(stages[0].glob('.helseark-restore-*'))
    with pytest.raises(ArchiveError,match='MIGRATION_STAGING_EXISTS'):
        apply_migration(v,plan,dest,reviewedPlanSha256=plan.planSha256)
    receipt=apply_migration(v,plan,dest,reviewedPlanSha256=plan.planSha256,resume=True)
    assert receipt.originalUnchanged and not doctor(open_vault(dest)).issues
    assert inventory(v.root)==before


def test_cli_plan_apply_and_blocked_fhir(tmp_path):
    console=Path(sys.executable).parent/'helseark'
    def run(*args):
        return subprocess.run([str(console),*map(str,args),'--json'],capture_output=True)
    root=tmp_path/'v'
    assert run('init',root).returncode==0
    assert run('--vault',root,'person','add','--name','Synthetic CLI').returncode==0
    child=run('--vault',root,'migrate','plan','--to-contract','0.1.0')
    assert child.returncode==0,child.stderr
    plan=decode_json(child.stdout);file=tmp_path/'plan.json';file.write_bytes(child.stdout)
    blocked=run('--vault',root,'migrate','plan','--to-fhir','5.0.0')
    assert blocked.returncode==6 and decode_json(blocked.stdout)['planClass']=='fhir-release'
    out=tmp_path/'out'
    bad=run('--vault',root,'migrate','apply','--plan',file,'--reviewed-plan-sha256','0'*64,'--into',out)
    assert bad.returncode==3 and not out.exists()
    child=run('--vault',root,'migrate','apply','--plan',file,'--reviewed-plan-sha256',plan['planSha256'],'--into',out)
    assert child.returncode==0,child.stderr
    assert decode_json(child.stdout)['originalUnchanged'] and not doctor(open_vault(out)).issues


def test_source_changed_during_staging_is_not_published(tmp_path,monkeypatch):
    from helseark import migrations
    v=small(tmp_path);plan=plan_migration(v,CURRENT)
    clinical={p.relative_to(v.root).as_posix():p.read_bytes() for p in (v.root/'people').rglob('*') if p.is_file()}
    def edit(point):
        if point=='restored':
            (v.root/'README.md').write_bytes(b'Concurrent unrelated source edit')
    monkeypatch.setattr(migrations,'_checkpoint',edit)
    with pytest.raises(ArchiveError,match='STALE_BASE'):
        apply_migration(v,plan,tmp_path/'out',reviewedPlanSha256=plan.planSha256)
    assert not (tmp_path/'out').exists() and not doctor(open_vault(v.root)).issues
    assert all((v.root/p).read_bytes()==data for p,data in clinical.items())
    # Unpublished staging must not claim the source was unchanged before the
    # final comparison has actually succeeded.
    for stage in tmp_path.glob('.helseark-migrate-*'):
        assert not list((stage/'vault/migrations').glob('*.json'))
