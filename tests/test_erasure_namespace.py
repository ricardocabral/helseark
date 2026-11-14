"""Real namespace substitutions; native no-replace renames remain in use."""
import pytest
from test_person_erasure import hashes
from helseark.archive import init_vault, add_person
from helseark.contracts import PersonDraft, ArchiveError
import helseark.portability as port


@pytest.mark.parametrize('restore',[False,True])
@pytest.mark.parametrize('mutation',['source','destination','symlink','collision'])
def test_namespace_substitution_preserves_objects(tmp_path,monkeypatch,restore,mutation):
    v=init_vault(tmp_path/'vault')
    p=add_person(v,PersonDraft('Same synthetic name'));q=add_person(v,PersonDraft('Same synthetic name'))
    selected=hashes(v.root/'people'/p);other=hashes(v.root/'people'/q)
    quarantine=tmp_path/'quarantine';plan=port.plan_person_erasure(v,p,quarantine)
    if restore:port.apply_person_erasure(v,plan,plan.digest)
    source_root=quarantine/'files' if restore else v.root
    target_root=v.root if restore else quarantine/'files'
    original=port._erasure_move
    outside=tmp_path/'outside';outside.mkdir()
    saved=tmp_path/'saved'
    def mutate(move):
        if mutation=='source':
            (source_root/'people'/p).rename(saved)
            # A real unselected tree replaces the selected name.
            (v.root/'people'/q).rename(source_root/'people'/p)
        elif mutation in ('destination','symlink'):
            (target_root/'people').rename(saved)
            if mutation=='destination':(target_root/'people').mkdir()
            else:(target_root/'people').symlink_to(outside,target_is_directory=True)
        else:
            (target_root/'people'/p).mkdir()
            (target_root/'people'/p/'unrelated').write_text('preserve me')
        return original(move)
    monkeypatch.setattr(port,'_erasure_move',mutate)
    with pytest.raises(ArchiveError):
        if restore:port.restore_person_erasure(v,quarantine,plan.digest)
        else:port.apply_person_erasure(v,plan,plan.digest)
    assert not list(outside.iterdir())
    if mutation=='source':
        assert hashes(saved)==selected
        assert hashes(source_root/'people'/p)==other
        assert not (target_root/'people'/p).exists()
    else:
        assert hashes(source_root/'people'/p)==selected
        assert hashes((saved/q) if restore and mutation in ('destination','symlink') else v.root/'people'/q)==other
        if mutation=='collision':assert (target_root/'people'/p/'unrelated').read_text()=='preserve me'
    # Retain all trees on rejection, then explicitly undo only this test's mutation.
    monkeypatch.setattr(port,'_erasure_move',original)
    if mutation=='source':
        (source_root/'people'/p).rename(v.root/'people'/q);saved.rename(source_root/'people'/p)
    elif mutation in ('destination','symlink'):
        if mutation=='symlink':(target_root/'people').unlink()
        else:(target_root/'people').rmdir()
        saved.rename(target_root/'people')
    else:
        (target_root/'people'/p).rename(tmp_path/'competing-object')
    if not restore:port.apply_person_erasure(v,plan,plan.digest)
    port.restore_person_erasure(v,quarantine,plan.digest)
    assert hashes(v.root/'people'/p)==selected and hashes(v.root/'people'/q)==other


@pytest.mark.parametrize('restore',[False,True])
@pytest.mark.parametrize('ancestor',['source','destination'])
def test_native_rename_stays_on_held_ancestor(tmp_path,monkeypatch,restore,ancestor):
    """Mutation at the syscall seam still calls the REAL native rename.

    A later path inventory error is a partial move, never a safe no-op.
    Recovery bytes remain at the held directory (here renamed to saved).
    """
    v=init_vault(tmp_path/'vault');p=add_person(v,PersonDraft('Same synthetic name'));q=add_person(v,PersonDraft('Same synthetic name'))
    selected=hashes(v.root/'people'/p);other=hashes(v.root/'people'/q)
    quarantine=tmp_path/'quarantine';plan=port.plan_person_erasure(v,p,quarantine)
    if restore:port.apply_person_erasure(v,plan,plan.digest)
    source_root=quarantine/'files' if restore else v.root
    target_root=v.root if restore else quarantine/'files'
    saved=tmp_path/'saved';outside=tmp_path/'outside';outside.mkdir()
    native=port._rename_noreplace
    def mutate(sfd,source,dfd,destination):
        root=source_root if ancestor=='source' else target_root
        (root/'people').rename(saved)
        (root/'people').symlink_to(outside,target_is_directory=True)
        return native(sfd,source,dfd,destination)
    monkeypatch.setattr(port,'_rename_noreplace',mutate)
    with pytest.raises(ArchiveError):
        if restore:port.restore_person_erasure(v,quarantine,plan.digest)
        else:port.apply_person_erasure(v,plan,plan.digest)
    assert not list(outside.iterdir())
    recovery=(saved/p) if ancestor=='destination' else target_root/'people'/p
    assert hashes(recovery)==selected
    other_location=(saved/q) if (restore and ancestor=='destination') or (not restore and ancestor=='source') else v.root/'people'/q
    assert hashes(other_location)==other
    root=source_root if ancestor=='source' else target_root
    (root/'people').unlink();saved.rename(root/'people')
    monkeypatch.setattr(port,'_rename_noreplace',native)
    port.restore_person_erasure(v,quarantine,plan.digest)
    assert hashes(v.root/'people'/p)==selected and hashes(v.root/'people'/q)==other


def test_process_death_during_restore_preserves_exact_recovery(tmp_path):
    import os
    from test_cli_journey import run
    from helseark.serialization import encode_json
    v=init_vault(tmp_path/'vault');p=add_person(v,PersonDraft('Synthetic'));q=add_person(v,PersonDraft('Synthetic'))
    work=v.root/'work/corrections/owned';work.mkdir(parents=True)
    (work/'candidate.json').write_bytes(encode_json({'personId':p,'synthetic':True}))
    before=hashes(v.root/'people');work_before=hashes(work)
    quarantine=tmp_path/'quarantine';plan=port.plan_person_erasure(v,p,quarantine)
    port.apply_person_erasure(v,plan,plan.digest)
    child=run('--vault',v.root,'erase','restore',quarantine,'--approve',plan.digest,'--json',
              env={**os.environ,'_HELSEARK_TEST_CRASH_AT':'erasure-after-move'})
    # The existing production test seam uses this deliberately private variable.
    assert child.returncode==91,child.stderr
    assert hashes(work)==work_before and hashes(quarantine/'files/people'/p)=={k[len(p)+1:]:h for k,h in before.items() if k.startswith(p+'/')}
    assert hashes(v.root/'people'/q)=={k[len(q)+1:]:h for k,h in before.items() if k.startswith(q+'/')}
    port.restore_person_erasure(v,quarantine,plan.digest)
    assert hashes(v.root/'people')==before and hashes(work)==work_before


@pytest.mark.parametrize('operation',['resume','restore'])
def test_existing_quarantine_symlink_preserves_recovery(tmp_path,operation):
    v=init_vault(tmp_path/'vault');p=add_person(v,PersonDraft('Synthetic'));q=add_person(v,PersonDraft('Synthetic'))
    selected=hashes(v.root/'people'/p);other=hashes(v.root/'people'/q)
    quarantine=tmp_path/'quarantine';plan=port.plan_person_erasure(v,p,quarantine)
    port.apply_person_erasure(v,plan,plan.digest)
    saved=tmp_path/'saved';(quarantine/'files/people').rename(saved)
    (quarantine/'files/people').symlink_to(v.root/'people',target_is_directory=True)
    with pytest.raises(ArchiveError):
        if operation=='resume':port.apply_person_erasure(v,plan,plan.digest)
        else:port.restore_person_erasure(v,quarantine,plan.digest)
    assert hashes(saved/p)==selected and hashes(v.root/'people'/q)==other
    assert not (v.root/'people'/p).exists()
    (quarantine/'files/people').unlink();saved.rename(quarantine/'files/people')
    port.restore_person_erasure(v,quarantine,plan.digest)
    assert hashes(v.root/'people'/p)==selected
