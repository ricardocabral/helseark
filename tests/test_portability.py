"""Behavioral portability checks on synthetic accepted history."""
from pathlib import Path
import shutil
import pytest
from helseark.archive import init_vault, add_person, open_vault, doctor
from helseark.contracts import PersonDraft, ExportSelection, ResourceRef, ArchiveError
from helseark.portability import backup, restore, verify_export, export_person, fhir_collection
from helseark.serialization import encode_json, decode_json
from helseark.agent_context import document


def test_roundtrip_reviews_survive_work_deletion(tmp_path):
    from test_intake import supplied_candidate
    from test_review import approve
    from helseark.intake import prepare_candidate
    from helseark.archive import commit_candidate
    from helseark.query import observations
    from helseark.contracts import ObservationFilter
    v,p,source,packet,c = supplied_candidate(tmp_path)
    proposal=prepare_candidate(v,c);commit_candidate(v,proposal,approve(v,proposal))
    # Real reviewed amended result via the existing public preparation boundary.
    from test_review import rerun_candidate
    from helseark.intake import read_candidate
    c.bundle['entry'][0]['resource']['status']='amended'
    (c.path/'bundle.json').write_bytes(encode_json(c.bundle))
    c=rerun_candidate(v,c)
    mapping={}
    current=list(observations(v,p,ObservationFilter()))
    for entry in c.bundle['entry']:
        r=entry['resource']
        if r['resourceType']=='Observation':
            match=next(row for row in current if row.code['text']==r['code']['text'])
            mapping[entry['fullUrl']]=f'Observation/{match.resourceRef.id}'
    proposal=prepare_candidate(v,c,reextract=True,reconciliation=mapping)
    commit_candidate(v,proposal,approve(v,proposal))
    expected={str(x.relative_to(v.root)):x.read_bytes() for x in (v.root/'people').rglob('*') if x.is_file()}
    facts=encode_json(document(list(observations(v,p,ObservationFilter()))))
    shutil.rmtree(v.root/'work')
    receipt=backup(v,tmp_path/'backup')
    report=verify_export(receipt.path)
    assert not report.issues and report.checkedChanges==4
    assert report.checkedResources>=8 and report.checkedAssets>0
    restored=restore(receipt.path,tmp_path/'restored')
    for name in ['.runtime','derived','work']:
        shutil.rmtree(restored.root/name,ignore_errors=True)
    assert not doctor(open_vault(restored.root)).issues
    assert {str(x.relative_to(restored.root)):x.read_bytes() for x in (restored.root/'people').rglob('*') if x.is_file()}==expected
    assert encode_json(document(list(observations(restored,p,ObservationFilter()))))==facts
    assert (restored.root/source.assetPath.relative_to(v.root)).read_bytes()==source.assetPath.read_bytes()


def test_isolation_snapshot_mapping_and_exact_bytes(tmp_path):
    v=init_vault(tmp_path/'v');p=add_person(v,PersonDraft('Selected Person'))
    other=add_person(v,PersonDraft('Other Private Person'))
    receipt=export_person(v,p,tmp_path/'person',ExportSelection('full-person'))
    assert receipt.peopleCount==1
    assert not any(b'Other Private Person' in x.read_bytes() for x in receipt.path.rglob('*') if x.is_file())
    before={x:x.read_bytes() for x in (v.root/'people').rglob('*.json')}
    selected=export_person(v,p,tmp_path/'selected',ExportSelection('selected-current',(ResourceRef('Patient',p),),False))
    assert not verify_export(selected.path).issues
    assert not (selected.path/'vault/people').exists()
    manifest=decode_json((selected.path/'export.json').read_bytes())
    assert manifest['omissions']
    bundle,mapping=fhir_collection(v,p,(ResourceRef('Patient',p),))
    assert bundle['entry'][0]['fullUrl']=='urn:uuid:'+mapping[0]['versionId']
    assert all(x.read_bytes()==b for x,b in before.items())


@pytest.mark.parametrize('attack',['digest','missing-definition','symlink','extra'])
def test_damaged_bundle_never_publishes(tmp_path,attack):
    v=init_vault(tmp_path/'v');add_person(v,PersonDraft('Synthetic'))
    b=backup(v,tmp_path/'b').path
    if attack=='digest':next((b/'vault/people').rglob('proposal.json')).write_bytes(b'{}')
    elif attack=='missing-definition':next((b/'vault/definitions').rglob('*.schema.json')).unlink()
    elif attack=='symlink':(b/'link').symlink_to(v.root)
    else:(b/'unexpected').write_bytes(b'orphan')
    assert verify_export(b).issues
    with pytest.raises(ArchiveError):restore(b,tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_existing_destination_and_recursive_backup(tmp_path):
    v=init_vault(tmp_path/'v');add_person(v,PersonDraft('Synthetic'))
    with pytest.raises(ArchiveError):backup(v,v.root/'backup')
    b=backup(v,tmp_path/'b').path
    target=tmp_path/'existing';target.mkdir();(target/'keep').write_bytes(b'keep')
    with pytest.raises(ArchiveError,match='DESTINATION_EXISTS'):restore(b,target)
    assert (target/'keep').read_bytes()==b'keep'


def test_archives_rejected_without_extraction(tmp_path):
    import zipfile,tarfile,io
    for kind in ['zip','tar']:
        path=tmp_path/kind
        if kind=='zip':
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('../escaped',b'bad')
                link=zipfile.ZipInfo('link');link.create_system=3;link.external_attr=0o120777 << 16
                z.writestr(link,'../escaped')
        else:
            with tarfile.open(path,'w') as t:
                info=tarfile.TarInfo('../escaped');info.size=3;t.addfile(info,io.BytesIO(b'bad'))
                link=tarfile.TarInfo('link');link.type=tarfile.SYMTYPE;link.linkname='../escaped';t.addfile(link)
        with pytest.raises(ArchiveError):restore(path,tmp_path/('out-'+kind))
    assert not (tmp_path/'escaped').exists()


def test_doctor_orphans_staging_and_corruption(tmp_path):
    v=init_vault(tmp_path/'v');p=add_person(v,PersonDraft('Synthetic'))
    orphan=v.root/f'people/{p}/assets/sha256'/('a'*64)/'blob'
    orphan.parent.mkdir(parents=True);orphan.write_bytes(b'orphan')
    stage=v.root/'.runtime/staging/incomplete';stage.mkdir()
    report=doctor(v)
    assert str(orphan.relative_to(v.root)) in report.orphanPaths
    assert any(i.code=='INCOMPLETE_STAGING' and str(stage.relative_to(v.root))==i.pointer for i in report.issues)
    resource=next((v.root/'people').rglob('resources/*.json'))
    resource.write_bytes(resource.read_bytes()+b' ')
    report=doctor(v)
    assert any(i.severity=='error' for i in report.issues)
    with pytest.raises(ArchiveError):open_vault(v.root)


def test_restore_race_preserves_competing_destination(tmp_path, monkeypatch):
    import helseark.portability as portability
    v=init_vault(tmp_path/'v');add_person(v,PersonDraft('Synthetic'))
    b=backup(v,tmp_path/'b').path
    original=portability._publish
    destination=tmp_path/'raced'
    def compete(stage,target):
        target.mkdir();(target/'keep').write_bytes(b'competitor')
        original(stage,target)
    monkeypatch.setattr(portability,'_publish',compete)
    with pytest.raises(ArchiveError,match='DESTINATION_EXISTS'):restore(b,destination)
    assert (destination/'keep').read_bytes()==b'competitor'
    assert not (destination/'vault.json').exists()


def test_snapshot_holds_real_writer_lock(tmp_path, monkeypatch):
    import subprocess,sys
    import helseark.portability as portability
    v=init_vault(tmp_path/'v');add_person(v,PersonDraft('Synthetic'))
    original=portability._copy;probed=[]
    def probe(*args):
        child=subprocess.run([sys.executable,'-m','helseark.cli','--vault',str(v.root),'person','add',
                              '--name','Concurrent Synthetic','--json'],capture_output=True)
        assert child.returncode==4,child.stderr
        probed.append(True)
        return original(*args)
    monkeypatch.setattr(portability,'_copy',probe)
    backup(v,tmp_path/'backup')
    assert probed and len(list((v.root/'people').iterdir()))==1


def test_missing_predecessor_and_unresolved_revision_block_queries(tmp_path):
    from test_archive import update_payload, rebind_proposal
    from helseark.archive import _publish_change,head
    v=init_vault(tmp_path/'v');p=add_person(v,PersonDraft('Synthetic'))
    payload=tmp_path/'payload';base=update_payload(v,p,payload)
    proposal=decode_json((payload/'proposal.json').read_bytes())
    resource_path=payload/proposal['resources'][0]['path']
    resource=decode_json(resource_path.read_bytes())
    resource['managingOrganization']={'reference':'Organization/11111111-1111-4111-8111-111111111111'}
    resource_path.write_bytes(encode_json(resource))
    from helseark.serialization import hash_bytes
    proposal['resources'][0]['sha256']=hash_bytes(resource_path.read_bytes())
    rebind_proposal(payload,proposal)
    # No unresolved accepted reference may be published.
    with pytest.raises(ArchiveError):_publish_change(v,p,payload,base)
    assert head(v,p)==base
    # A real valid second change, then a missing predecessor on disk.
    shutil.rmtree(payload);base=update_payload(v,p,payload);_publish_change(v,p,payload,base)
    first=sorted((v.root/f'people/{p}/accepted').iterdir())[0]
    shutil.move(first,tmp_path/'retained-genesis')
    report=doctor(v)
    assert report.issues and any('accepted' in i.pointer for i in report.issues)
    with pytest.raises(ArchiveError):list(__import__('helseark.query',fromlist=['timeline']).timeline(v,p))


def test_pdf_person_export_requires_source_scope(tmp_path):
    from test_intake import supplied_candidate
    from test_review import approve
    from helseark.intake import prepare_candidate
    from helseark.archive import commit_candidate
    v,p,_,_,c=supplied_candidate(tmp_path)
    proposal=prepare_candidate(v,c);commit_candidate(v,proposal,approve(v,proposal))
    with pytest.raises(ArchiveError,match='SOURCE_SCOPE_REVIEW_REQUIRED'):
        export_person(v,p,tmp_path/'blocked',ExportSelection('full-person'))
    assert not (tmp_path/'blocked').exists()
    snapshot=export_person(v,p,tmp_path/'safe',ExportSelection('selected-current',(),False))
    assert not verify_export(snapshot.path).issues
    manifest=decode_json((snapshot.path/'export.json').read_bytes())
    assert manifest['referenceMap'] and all(m['references'] for m in manifest['referenceMap'] if m['resourceType']=='Observation')
    assert not (snapshot.path/'sources').exists()
    assert not any(x.name=='blob' for x in snapshot.path.rglob('*'))
    # The immutable support kit includes its public synthetic tutorial PDF; it is not a person source.


def test_manifest_traversal_rejected_before_staging(tmp_path):
    from helseark.serialization import hash_bytes
    v=init_vault(tmp_path/'v');add_person(v,PersonDraft('Synthetic'))
    b=backup(v,tmp_path/'b').path
    manifest=decode_json((b/'export.json').read_bytes())
    manifest['files'].append({'path':'../outside','size':1,'sha256':hash_bytes(b'x')})
    (b/'export.json').write_bytes(encode_json(manifest))
    with pytest.raises(ArchiveError):restore(b,tmp_path/'out')
    assert not list(tmp_path.glob('.helseark-restore-*'))


def test_pinned_definition_failure_even_with_reinventoried_bundle(tmp_path):
    from helseark.serialization import hash_bytes
    v=init_vault(tmp_path/'v');add_person(v,PersonDraft('Synthetic'))
    b=backup(v,tmp_path/'b').path
    removed=next((b/'vault/definitions').rglob('*.schema.json'));relative=removed.relative_to(b).as_posix()
    removed.unlink()
    manifest=decode_json((b/'export.json').read_bytes())
    manifest['files']=[x for x in manifest['files'] if x['path']!=relative]
    (b/'export.json').write_bytes(encode_json(manifest))
    assert verify_export(b).issues
    with pytest.raises(ArchiveError):restore(b,tmp_path/'out')


def test_restore_rechecks_nonclinical_staged_bytes(tmp_path,monkeypatch):
    import helseark.portability as portability
    v=init_vault(tmp_path/'v');add_person(v,PersonDraft('Synthetic'))
    b=backup(v,tmp_path/'b').path
    original=portability._copy
    def changed(source,target,paths):
        original(source,target,paths)
        (target/'README.md').write_bytes(b'changed while copying')
    monkeypatch.setattr(portability,'_copy',changed)
    with pytest.raises(ArchiveError):restore(b,tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_actual_mixed_person_pdf_is_blocked(tmp_path):
    from test_archive import update_payload,rebind_proposal
    from helseark.archive import _publish_change
    from helseark.serialization import hash_bytes
    v=init_vault(tmp_path/'v');p=add_person(v,PersonDraft('Synthetic scope storage fixture'))
    data=(Path(__file__).parent/'fixtures/synthetic/lab-two-people.pdf').read_bytes()
    digest=hash_bytes(data);asset=f'assets/sha256/{digest}/blob'
    path=v.root/'people'/p/asset;path.parent.mkdir(parents=True);path.write_bytes(data)
    payload=tmp_path/'payload';base=update_payload(v,p,payload)
    proposal=decode_json((payload/'proposal.json').read_bytes())
    proposal['assets']=[{'path':asset,'sha256':digest,'size':len(data),'mediaType':'application/pdf'}]
    rebind_proposal(payload,proposal);_publish_change(v,p,payload,base)
    # Storage-level synthetic accepted fixture, not a claimed clinical importer.
    with pytest.raises(ArchiveError,match='SOURCE_SCOPE_REVIEW_REQUIRED'):
        export_person(v,p,tmp_path/'blocked',ExportSelection('full-person'))
    assert not (tmp_path/'blocked').exists()


def test_malformed_derived_collection_is_a_report_not_traceback(tmp_path):
    from helseark.serialization import hash_bytes
    v=init_vault(tmp_path/'v');p=add_person(v,PersonDraft('Synthetic'))
    b=export_person(v,p,tmp_path/'b',ExportSelection('selected-current',(),False)).path
    (b/'collection.json').write_bytes(b'null\n')
    manifest=decode_json((b/'export.json').read_bytes())
    entry=next(f for f in manifest['files'] if f['path']=='collection.json')
    entry.update(sha256=hash_bytes(b'null\n'),size=5)
    (b/'export.json').write_bytes(encode_json(manifest))
    assert verify_export(b).issues
    with pytest.raises(ArchiveError):restore(b,tmp_path/'out')


def test_derived_collection_cannot_change_decimal_scale(tmp_path):
    from decimal import Decimal
    from test_archive import update_payload,rebind_proposal
    from helseark.archive import _publish_change
    from helseark.serialization import hash_bytes
    v=init_vault(tmp_path/'v');p=add_person(v,PersonDraft('Synthetic precision fixture'))
    payload=tmp_path/'payload';base=update_payload(v,p,payload)
    proposal=decode_json((payload/'proposal.json').read_bytes());entry=proposal['resources'][0]
    resource=decode_json((payload/entry['path']).read_bytes())
    resource['extension']=[{'url':'urn:synthetic:precision','valueDecimal':Decimal('1.20')}]
    (payload/entry['path']).write_bytes(encode_json(resource))
    entry['sha256']=hash_bytes((payload/entry['path']).read_bytes())
    rebind_proposal(payload,proposal);_publish_change(v,p,payload,base)
    b=export_person(v,p,tmp_path/'b',ExportSelection('selected-current',(),False)).path
    collection=decode_json((b/'collection.json').read_bytes())
    assert b'1.20' in (b/'collection.json').read_bytes()
    collection['entry'][0]['resource']['extension'][0]['valueDecimal']=Decimal('1.2')
    data=encode_json(collection);(b/'collection.json').write_bytes(data)
    manifest=decode_json((b/'export.json').read_bytes())
    file=next(f for f in manifest['files'] if f['path']=='collection.json')
    file.update(sha256=hash_bytes(data),size=len(data))
    (b/'export.json').write_bytes(encode_json(manifest))
    assert verify_export(b).issues


@pytest.mark.parametrize('location', ['root', 'person', 'definitions', 'kit'])
def test_unknown_material_reports_exact_path_and_blocks_all_exports(tmp_path, location):
    v = init_vault(tmp_path/'v')
    p = add_person(v, PersonDraft('Selected Synthetic'))
    add_person(v, PersonDraft('Excluded Synthetic'))
    relative = {
        'root': 'other-person-notes.txt',
        'person': f'people/{p}/scratch.txt',
        'definitions': 'definitions/private.txt',
        'kit': f'agent-kit/{v.config.agentKitVersion}/private.txt',
    }[location]
    private = v.root/relative
    private.write_bytes(b'Excluded Synthetic private unreviewed material')
    report = doctor(v)
    assert report.checkedChanges == 2 and report.checkedResources == 2
    assert any(i.code == 'UNKNOWN_PATH' and i.pointer == relative and 'Preserve' in i.message
               for i in report.issues)
    for mode in ['backup', 'full-person', 'selected-current']:
        out = tmp_path/mode
        with pytest.raises(ArchiveError, match='INTEGRITY'):
            if mode == 'backup':
                backup(v, out)
            else:
                export_person(v, p, out, ExportSelection(mode, (), mode == 'full-person'))
        assert not out.exists()
    assert private.read_bytes() == b'Excluded Synthetic private unreviewed material'


def test_doctor_returns_unsafe_staging_path_and_action(tmp_path):
    v = init_vault(tmp_path/'v')
    add_person(v, PersonDraft('Synthetic'))
    target = tmp_path/'outside'; target.mkdir()
    (target/'keep').write_bytes(b'preserve')
    (v.root/'.runtime/staging').rmdir()
    (v.root/'.runtime/staging').symlink_to(target, target_is_directory=True)
    report = doctor(v)
    assert report.checkedChanges == 1 and report.checkedResources == 1
    assert any(i.code == 'UNSAFE_PATH' and i.pointer == '.runtime/staging' and
               'Preserve' in i.message for i in report.issues)
    assert (target/'keep').read_bytes() == b'preserve'
    assert (v.root/'.runtime/staging').is_symlink()


@pytest.fixture(scope='module')
def binding_snapshot(tmp_path_factory):
    from test_intake import supplied_candidate
    from test_review import approve
    from helseark.intake import prepare_candidate
    from helseark.archive import commit_candidate
    root = tmp_path_factory.mktemp('binding-snapshot')
    v, p, _, _, candidate = supplied_candidate(root)
    proposal = prepare_candidate(v, candidate)
    commit_candidate(v, proposal, approve(v, proposal))
    out = export_person(v, p, root/'out', ExportSelection('selected-current', (), False)).path
    assert not verify_export(out).issues
    return out


@pytest.mark.parametrize('attack', ['missing', 'extra', 'dangling', 'contradictory'])
@pytest.mark.parametrize('exact', [True, False])
def test_reference_binding_metadata_is_verified(tmp_path, binding_snapshot, attack, exact):
    out = tmp_path/'out'
    shutil.copytree(binding_snapshot, out)
    original_bytes = {f: f.read_bytes() for f in (out/'resources').iterdir()}
    manifest = decode_json((out/'export.json').read_bytes())
    item = next(m for m in manifest['referenceMap'] if any(
        ('/_history/' in ref) == exact for ref in m['references']))
    ref = next(ref for ref in item['references'] if ('/_history/' in ref) == exact)
    if attack == 'missing':
        del item['references'][ref]
    elif attack == 'extra':
        item['references']['Patient/11111111-1111-4111-8111-111111111111'] = item['references'][ref]
    elif attack == 'dangling':
        item['references'][ref] = 'urn:uuid:11111111-1111-4111-8111-111111111111'
    else:
        item['references'][ref] = next(m['fullUrl'] for m in manifest['referenceMap']
                                     if m['fullUrl'] != item['references'][ref])
    (out/'export.json').write_bytes(encode_json(manifest))
    assert verify_export(out).issues
    assert all(f.read_bytes() == data for f, data in original_bytes.items())


@pytest.mark.parametrize('relative', ['support/definitions/private.txt', 'private.txt',
    'sources/people/11111111-1111-4111-8111-111111111111/private.txt'])
def test_selected_verifier_rejects_unlisted_support_even_with_inventory(tmp_path, relative):
    from helseark.serialization import hash_bytes
    v = init_vault(tmp_path/'v'); p = add_person(v, PersonDraft('Synthetic'))
    out = export_person(v, p, tmp_path/'out', ExportSelection('selected-current', (), False)).path
    (out/relative).parent.mkdir(parents=True, exist_ok=True)
    (out/relative).write_bytes(b'private unpinned material')
    manifest = decode_json((out/'export.json').read_bytes())
    data = (out/relative).read_bytes()
    manifest['files'].append(dict(path=relative, size=len(data), sha256=hash_bytes(data)))
    (out/'export.json').write_bytes(encode_json(manifest))
    assert verify_export(out).issues
