"""Migration receipts are household metadata, retained only in whole backups."""
from helseark.archive import doctor, open_vault
from helseark.contracts import ExportSelection
from helseark.migrations import CURRENT, plan_migration, apply_migration
from helseark.portability import backup, restore, export_person, verify_export
from helseark.serialization import decode_json, encode_json
from test_migrations import small, inventory


def test_receipts_survive_successive_migration_backup_but_not_person_export(tmp_path):
    source=small(tmp_path)
    before=inventory(source.root)
    plan=plan_migration(source,CURRENT)
    receipt=apply_migration(source,plan,tmp_path/'first',reviewedPlanSha256=plan.planSha256)
    migrated=open_vault(receipt.destination)
    assert not doctor(migrated).issues
    assert inventory(source.root)==before
    second=plan_migration(migrated,CURRENT)
    again=apply_migration(migrated,second,tmp_path/'second',reviewedPlanSha256=second.planSha256)
    assert receipt.mappingInventoryPath.read_bytes()==(again.destination/'migrations'/receipt.mappingInventoryPath.name).read_bytes()
    saved=backup(open_vault(again.destination),tmp_path/'backup')
    restored=restore(saved.path,tmp_path/'restored')
    assert inventory(restored.root)==inventory(again.destination)
    person=next((restored.root/'people').iterdir()).name
    selected=export_person(restored,person,tmp_path/'selected',ExportSelection('selected-current',(),False))
    assert not verify_export(selected.path).issues
    assert not any('migrations' in p.parts for p in selected.path.rglob('*'))
    full=export_person(restored,person,tmp_path/'person',ExportSelection('full-person',(),True))
    assert not verify_export(full.path).issues
    assert not (full.path/'vault/migrations').exists()
    receipt_path=restored.root/'migrations'/receipt.mappingInventoryPath.name
    original=receipt_path.read_bytes()
    for field,value in [('reviewedPlanSha256','0'*64), ('byteMappings',[]),
                        ('validatedCounts',{'changes':0,'resources':0,'assets':0}),
                        ('originalUnchanged',False), ('meaning','unreviewed text')]:
        changed=decode_json(original);changed[field]=value
        receipt_path.write_bytes(encode_json(changed))
        rejected=doctor(restored)
        assert rejected.issues and rejected.checkedChanges==2
        receipt_path.write_bytes(original)
    assert not doctor(restored).issues
    # A known directory name alone never grants unknown bytes authority.
    bad=restored.root/'migrations/private.json';bad.write_bytes(b'{"private":"other person"}')
    report=doctor(restored)
    assert report.issues and report.checkedChanges==2
    assert any(i.pointer=='migrations/private.json' for i in report.issues)
