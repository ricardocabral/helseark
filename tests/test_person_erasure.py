"""Recoverable synthetic removal, including real files and interrupted moves."""
from dataclasses import replace
from family_oracle import check_case
import pytest
from helseark.archive import init_vault, add_person, head, _files, _read
from helseark.contracts import PersonDraft, ArchiveError
from helseark.serialization import hash_bytes


def hashes(root):
    return {p:hash_bytes(_read(root,p)) for p in _files(root)}


def test_plan_digest_head_isolation_and_restore(tmp_path):
    from helseark.portability import plan_person_erasure, apply_person_erasure, restore_person_erasure
    v=init_vault(tmp_path/'vault');p=add_person(v,PersonDraft('Synthetic A'));q=add_person(v,PersonDraft('Synthetic B'))
    other=v.root/'people'/q;before=hashes(other)
    plan=plan_person_erasure(v,p,tmp_path/'quarantine')
    assert plan.canonicalPaths and plan.limitations and plan.baseHeads[p]
    with pytest.raises(ArchiveError,match='APPROVAL_REQUIRED'):
        apply_person_erasure(v,plan,'0'*64)
    with pytest.raises(ArchiveError,match='APPROVAL_REQUIRED'):
        apply_person_erasure(v,replace(plan,personId=q),plan.digest)
    receipt=apply_person_erasure(v,plan,plan.digest)
    assert not (v.root/'people'/p).exists() and hashes(other)==before
    assert receipt.remainingKnownCopies
    restore_person_erasure(v,receipt.quarantinePath,plan.digest)
    assert head(v,p)==plan.baseHeads[p] and hashes(other)==before
    check_case('person-removal',{'otherPersonByteChanges':sum(before[k]!=hashes(other).get(k) for k in before),
        'recoverable':head(v,p)==plan.baseHeads[p],'secureDeletion':False},['plan-digest','restore'])


@pytest.mark.parametrize('mutation',['roster','person-head'])
def test_changed_roster_invalidates_approved_plan(tmp_path,mutation):
    from helseark.portability import plan_person_erasure, apply_person_erasure
    v=init_vault(tmp_path/'vault');p=add_person(v,PersonDraft('Synthetic A'))
    plan=plan_person_erasure(v,p,tmp_path/'quarantine')
    if mutation=='roster':add_person(v,PersonDraft('Synthetic B'))
    else:
        from test_archive import update_payload
        from helseark.archive import _publish_change
        payload=tmp_path/'update';base=update_payload(v,p,payload);_publish_change(v,p,payload,base)
    with pytest.raises(ArchiveError,match='STALE_BASE'):apply_person_erasure(v,plan,plan.digest)
    assert head(v,p) and not (tmp_path/'quarantine').exists()


def test_interrupted_move_is_resumable_and_restorable(tmp_path,monkeypatch):
    import helseark.portability as port
    v=init_vault(tmp_path/'vault');p=add_person(v,PersonDraft('Synthetic A'))
    work=v.root/'work'/'corrections'/'draft';work.mkdir(parents=True)
    from helseark.serialization import encode_json
    (work/'candidate.json').write_bytes(encode_json({'personId':p}))
    plan=port.plan_person_erasure(v,p,tmp_path/'quarantine');before=hashes(v.root/'people'/p)
    publish=port._erasure_move
    def fail(move):
        if move[1]=='draft':raise OSError('synthetic boundary failure')
        return publish(move)
    monkeypatch.setattr(port,'_erasure_move',fail)
    with pytest.raises(ArchiveError,match='UNSAFE_PATH'):port.apply_person_erasure(v,plan,plan.digest)
    assert (tmp_path/'quarantine'/'plan.json').exists()
    monkeypatch.setattr(port,'_erasure_move',publish)
    receipt=port.apply_person_erasure(v,plan,plan.digest)
    port.restore_person_erasure(v,receipt.quarantinePath,plan.digest)
    assert hashes(v.root/'people'/p)==before and work.exists()


def test_real_second_writer_and_changed_bytes_block(tmp_path):
    from helseark.portability import plan_person_erasure, apply_person_erasure
    from helseark.archive import _writer_lock
    from helseark.serialization import encode_json
    from test_cli_journey import run
    v=init_vault(tmp_path/'vault');p=add_person(v,PersonDraft('Synthetic A'))
    plan=plan_person_erasure(v,p,tmp_path/'quarantine')
    from helseark.agent_context import document
    path=tmp_path/'plan.json';path.write_bytes(encode_json(document(plan)))
    with _writer_lock(v):
        child=run('--vault',v.root,'erase','apply',path,'--approve',plan.digest,'--json')
        assert child.returncode==4 and b'ARCHIVE_BUSY' in child.stderr
    blob=v.root/next(iter(plan.inventory))
    blob.write_bytes(blob.read_bytes()+b' ')
    with pytest.raises(ArchiveError):apply_person_erasure(v,plan,plan.digest)
    assert (v.root/'people'/p).exists()


def test_restore_after_interrupted_removal_and_refuse_collision(tmp_path,monkeypatch):
    import helseark.portability as port
    from helseark.serialization import encode_json
    v=init_vault(tmp_path/'vault');p=add_person(v,PersonDraft('Synthetic A'))
    work=v.root/'work'/'corrections'/'draft';work.mkdir(parents=True)
    (work/'candidate.json').write_bytes(encode_json({'personId':p}))
    plan=port.plan_person_erasure(v,p,tmp_path/'quarantine')
    original=port._erasure_move
    def fail(move):
        if move[1]==work.name:raise OSError('synthetic interruption')
        return original(move)
    monkeypatch.setattr(port,'_erasure_move',fail)
    with pytest.raises(ArchiveError,match='UNSAFE_PATH'):port.apply_person_erasure(v,plan,plan.digest)
    monkeypatch.setattr(port,'_erasure_move',original)
    port.restore_person_erasure(v,tmp_path/'quarantine',plan.digest)
    assert head(v,p)==plan.baseHeads[p] and work.exists()


def test_known_backup_and_external_packet_are_listed(tmp_path):
    from helseark.portability import backup, plan_person_erasure
    from helseark.serialization import encode_json
    v=init_vault(tmp_path/'vault');p=add_person(v,PersonDraft('Synthetic A'))
    backup(v,tmp_path/'backup')
    controls=v.root/'.runtime/intake';controls.mkdir(exist_ok=True)
    (controls/'synthetic.json').write_bytes(encode_json({'personId':p,'packetPath':str(tmp_path/'packet')}))
    plan=plan_person_erasure(v,p,tmp_path/'quarantine')
    assert str(tmp_path/'backup') in plan.knownExternalCopies
    assert str(tmp_path/'packet') in plan.knownExternalCopies


@pytest.mark.parametrize('recovery',['resume','restore'])
def test_process_death_after_first_move(tmp_path,recovery):
    import os
    from helseark.portability import plan_person_erasure,apply_person_erasure,restore_person_erasure
    from helseark.agent_context import document
    from helseark.serialization import encode_json
    from test_cli_journey import run
    v=init_vault(tmp_path/'vault');p=add_person(v,PersonDraft('Synthetic A'));q=add_person(v,PersonDraft('Synthetic B'))
    before=hashes(v.root/'people'/q)
    plan=plan_person_erasure(v,p,tmp_path/'quarantine');path=tmp_path/'plan.json'
    path.write_bytes(encode_json(document(plan)))
    child=run('--vault',v.root,'erase','apply',path,'--approve',plan.digest,'--json',env={**os.environ,'_HELSEARK_TEST_CRASH_AT':'erasure-after-move'})
    assert child.returncode==91 and not (v.root/'people'/p).exists()
    if recovery=='resume':apply_person_erasure(v,plan,plan.digest)
    restore_person_erasure(v,tmp_path/'quarantine',plan.digest)
    assert head(v,p)==plan.baseHeads[p] and hashes(v.root/'people'/q)==before


def test_source_writer_cannot_recreate_removed_person(tmp_path,monkeypatch):
    import helseark.intake as intake
    from helseark.portability import plan_person_erasure,apply_person_erasure
    v=init_vault(tmp_path/'vault');p=add_person(v,PersonDraft('Synthetic A'))
    plan=plan_person_erasure(v,p,tmp_path/'quarantine')
    source=tmp_path/'synthetic.txt';source.write_text('Invented source only')
    original=intake._regular
    def read_then_remove(path,maximum):
        data=original(path,maximum)
        if path==source:apply_person_erasure(v,plan,plan.digest)
        return data
    monkeypatch.setattr(intake,'_regular',read_then_remove)
    with pytest.raises(ArchiveError,match='PERSON_NOT_FOUND'):intake.add_source(v,p,source)
    assert not (v.root/'people'/p).exists()


def test_shared_work_tree_never_moves_other_person_bytes(tmp_path):
    from helseark.portability import plan_person_erasure
    from helseark.serialization import encode_json
    v=init_vault(tmp_path/'vault');p=add_person(v,PersonDraft('Synthetic A'));q=add_person(v,PersonDraft('Synthetic B'))
    shared=v.root/'work'/'mixed';shared.mkdir(parents=True)
    (shared/'candidate.json').write_bytes(encode_json({'personId':p}))
    (shared/'other.json').write_bytes(encode_json({'personId':q,'synthetic':'other person working data'}))
    before=hashes(shared)
    with pytest.raises(ArchiveError,match='ERASURE_SCOPE_UNKNOWN'):plan_person_erasure(v,p,tmp_path/'quarantine')
    assert hashes(shared)==before


def test_legacy_external_candidate_control_is_inventoried(tmp_path):
    from helseark.portability import plan_person_erasure
    from helseark.serialization import encode_json
    v=init_vault(tmp_path/'vault');p=add_person(v,PersonDraft('Synthetic A'))
    external=tmp_path/'old-candidate';external.mkdir();(external/'candidate.json').write_bytes(encode_json({'personId':p}))
    control=v.root/'.runtime/prepared';control.mkdir(exist_ok=True)
    (control/'legacy.json').write_bytes(encode_json({'candidatePath':str(external)}))
    plan=plan_person_erasure(v,p,tmp_path/'quarantine')
    assert '.runtime/prepared/legacy.json' in plan.workPaths and str(external) in plan.knownExternalCopies


def test_prepare_cannot_write_while_removal_writer_lock_is_held(tmp_path):
    from test_intake import supplied_candidate
    from test_cli_journey import run
    from helseark.archive import _writer_lock
    v,p,_,_,c=supplied_candidate(tmp_path)
    with _writer_lock(v):
        result=run('--vault',v.root,'candidate','prepare',c.path,'--person',p,'--json')
    assert result.returncode==4 and b'ARCHIVE_BUSY' in result.stderr


def test_incomplete_selected_publication_staging_is_quarantined(tmp_path):
    from helseark.portability import plan_person_erasure,apply_person_erasure,restore_person_erasure
    from helseark.serialization import encode_json
    v=init_vault(tmp_path/'vault');p=add_person(v,PersonDraft('Synthetic A'))
    staged=v.root/'.runtime/staging/interrupted';staged.mkdir()
    (staged/'proposal.json').write_bytes(encode_json({'personId':p}))
    (staged/'synthetic.txt').write_text('Synthetic staged private copy')
    plan=plan_person_erasure(v,p,tmp_path/'quarantine')
    assert '.runtime/staging/interrupted' in plan.workPaths
    receipt=apply_person_erasure(v,plan,plan.digest)
    assert not staged.exists()
    restore_person_erasure(v,receipt.quarantinePath,plan.digest)
    assert (staged/'synthetic.txt').read_text()=='Synthetic staged private copy'


def test_review_cannot_recreate_control_while_removal_lock_is_held(tmp_path):
    from test_intake import supplied_candidate
    from test_cli_journey import run
    from helseark.archive import _writer_lock
    from helseark.intake import prepare_candidate
    from helseark.review import render_review
    from helseark.serialization import encode_json, decode_json
    v,p,_,_,candidate=supplied_candidate(tmp_path)
    proposal=prepare_candidate(v,candidate)
    view=render_review(v,proposal)
    decision=tmp_path/'decision.json'
    decision.write_bytes(encode_json({'confirmedPerson':True,
        'decision':'accept-with-acknowledged-limitations','reviewerLabel':'synthetic lock regression',
        'acknowledgedIssues':[{'code':i['code'],'resourceRef':i['resourceRef'],
            'issueId':i['issueId'],'reason':'Synthetic fixture limitation inspected.'}
            for i in view.issues if i['severity'] in ('warning','review')]}))
    with _writer_lock(v):
        child=run('--vault',v.root,'candidate','review',proposal.path,'--person',p,
                  '--decision',decision,'--json')
    assert child.returncode==4 and b'ARCHIVE_BUSY' in child.stderr
    assert not (proposal.path/'review.json').exists()
    assert not (v.root/'.runtime/reviews'/f'{proposal.proposalSha256}.json').exists()
    child=run('--vault',v.root,'candidate','review',proposal.path,'--person',p,
              '--decision',decision,'--json')
    assert child.returncode==0,child.stderr
    control=decode_json((v.root/'.runtime/reviews'/f'{proposal.proposalSha256}.json').read_bytes())
    assert control['personId']==p
