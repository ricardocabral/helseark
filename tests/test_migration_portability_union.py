"""Migration receipts are household metadata, retained only in whole backups."""
from helseark.archive import doctor, open_vault
from helseark.contracts import ExportSelection
from helseark.migrations import CURRENT, plan_migration, apply_migration
from helseark.portability import backup, restore, export_person, verify_export
from helseark.serialization import decode_json, encode_json
from test_migrations import small, inventory
import pytest


@pytest.mark.parametrize('wrapper', [False, True], ids=['identity', 'wrapper'])
def test_resealed_impossible_receipts_are_rejected(tmp_path, wrapper):
    from helseark.migrations import _digest
    from test_migrations import legacy
    source = small(tmp_path)
    if wrapper:
        source = legacy(tmp_path, source)
    plan = plan_migration(source, CURRENT)
    receipt = apply_migration(source, plan, tmp_path/'migrated', reviewedPlanSha256=plan.planSha256)
    vault = open_vault(receipt.destination)
    path = receipt.mappingInventoryPath
    original = path.read_bytes()
    attacks = {
        'oldhash': lambda p: p['byteMappings'][0].update(oldSha256='0'*64),
        'duplicate': lambda p: p['byteMappings'].append(p['byteMappings'][0].copy()),
        'transform': lambda p: p.update(transformations=['unknown-private-transform']),
        'versions': lambda p: p['sourceVersionSet'].update(contractVersion='9.9.9'),
        'missing': lambda p: p['byteMappings'].pop(),
        'destination': lambda p: p['byteMappings'][0].update(destinationPath='../escape'),
        'collision': lambda p: p['byteMappings'][0].update(destinationPath=p['byteMappings'][1]['destinationPath']),
        'newhash': lambda p: p['byteMappings'][0].update(newSha256='0'*64),
        'size': lambda p: p['byteMappings'][0].update(size=999),
        'definitions': lambda p: p['requiredDefinitions'].pop(),
        'inventory-duplicate': lambda p: p['sourceInventory'].append(p['sourceInventory'][0].copy()),
        'unsafe-source': lambda p: p['sourceInventory'][0].update(path='a/../escape'),
        'missing-inventory': lambda p: p['sourceInventory'].pop(),
        'extra-definition': lambda p: p['requiredDefinitions'].append(p['sourceInventory'][0].copy()),
        'wrong-operation': lambda p: p.update(transformations=['v1-identity-copy' if wrapper else 'test-only-layout-0-to-v1']),
        'source-collision': lambda p: p['byteMappings'][0].update(sourcePath=p['byteMappings'][1]['sourcePath']),
        'absolute-source': lambda p: p['sourceInventory'][0].update(path='/escape'),
        'source-backslash': lambda p: p['sourceInventory'][0].update(path='a\\escape'),
        'source-dot': lambda p: p['sourceInventory'][0].update(path='.'),
        'source-noncanonical': lambda p: p['sourceInventory'][0].update(path='a//escape'),
    }
    failures = []
    for name, mutate in attacks.items():
        value = decode_json(original)
        mutate(value['plan'])
        value['plan']['planSha256'] = _digest(value['plan'])
        value['reviewedPlanSha256'] = value['plan']['planSha256']
        value['byteMappings'] = value['plan']['byteMappings']
        changed = path.with_name(value['plan']['planSha256']+'.json')
        path.rename(tmp_path/'held.json')
        changed.write_bytes(encode_json(value))
        try:
            report = doctor(vault)
            if not report.issues:
                failures.append(name)
            else:
                assert report.checkedChanges == 2
                assert any(i.code == 'INTEGRITY' for i in report.issues)
        finally:
            changed.rename(tmp_path/(name+'.json'))
            (tmp_path/'held.json').rename(path)
    assert not failures, failures
    assert path.read_bytes() == original and not doctor(vault).issues


def test_migrated_removal_discloses_approved_local_residue_and_restores(tmp_path):
    from helseark.portability import (plan_person_erasure, apply_person_erasure,
                                     restore_person_erasure, read_erasure_plan)
    from helseark.serialization import hash_bytes
    from helseark.agent_context import document
    source = small(tmp_path)
    plan = plan_migration(source, CURRENT)
    receipt = apply_migration(source, plan, tmp_path/'migrated', reviewedPlanSha256=plan.planSha256)
    vault = open_vault(receipt.destination)
    person, other = sorted(p.name for p in (vault.root/'people').iterdir())
    original = receipt.mappingInventoryPath.read_bytes()
    selected, other_before = inventory(vault.root/'people'/person), inventory(vault.root/'people'/other)
    removal = plan_person_erasure(vault, person, tmp_path/'quarantine')
    expected = ({'path': 'migrations/'+receipt.mappingInventoryPath.name,
                 'sha256': hash_bytes(original), 'size': len(original), 'personId': person,
                 'sourceHead': decode_json(original)['plan']['sourceHeads'][person]},)
    assert removal.retainedLocalMetadata == expected
    file = tmp_path/'removal.json'; file.write_bytes(encode_json(document(removal)))
    assert read_erasure_plan(file) == removal
    from dataclasses import replace
    from helseark.contracts import ArchiveError
    with pytest.raises(ArchiveError, match='APPROVAL_REQUIRED'):
        apply_person_erasure(vault, replace(removal, retainedLocalMetadata=()), removal.digest)
    # Same sealed receipt, different file bytes: disclosure must be approved again.
    receipt.mappingInventoryPath.write_bytes(original+b'\n')
    with pytest.raises(ArchiveError, match='STALE_BASE'):
        apply_person_erasure(vault, removal, removal.digest)
    assert not removal.quarantineDestination.exists()
    receipt.mappingInventoryPath.write_bytes(original)
    result = apply_person_erasure(vault, removal, removal.digest)
    assert result.retainedLocalMetadata == expected
    assert str(receipt.mappingInventoryPath) in result.remainingKnownCopies
    assert receipt.mappingInventoryPath.read_bytes() == original
    assert not (vault.root/'people'/person).exists()
    assert inventory(vault.root/'people'/other) == other_before
    assert not doctor(vault).issues
    restore_person_erasure(vault, removal.quarantineDestination, removal.digest)
    assert inventory(vault.root/'people'/person) == selected
    assert inventory(vault.root/'people'/other) == other_before


def test_old_removal_journal_digest_still_restores_without_new_field(tmp_path):
    from helseark.portability import (plan_person_erasure, apply_person_erasure,
                                     restore_person_erasure, read_erasure_plan)
    from helseark.agent_context import document
    source = small(tmp_path)
    person = next((source.root/'people').iterdir()).name
    before = inventory(source.root/'people'/person)
    plan = plan_person_erasure(source, person, tmp_path/'quarantine')
    apply_person_erasure(source, plan, plan.digest)
    journal = plan.quarantineDestination/'plan.json'
    raw = document(plan); raw.pop('retainedLocalMetadata')
    journal.write_bytes(encode_json(raw))
    assert read_erasure_plan(journal) == plan
    restore_person_erasure(source, plan.quarantineDestination, plan.digest)
    assert inventory(source.root/'people'/person) == before


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
