"""Offline folder snapshots, exact inventories and staged no-replace recovery.

The FHIR collection boundary owns revision closure and reversible fullUrl mapping;
official-validator callers can consume it without implementing another mapper.
Accepted resource bytes are copied independently of the derived collection.
"""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from tempfile import mkdtemp
from uuid import uuid4
import ctypes
import errno
import os
import shutil
import sys

from jsonschema import Draft202012Validator

from .contracts import (ArchiveError, Vault, ResourceRef, ExportSelection,
                        ExportReceipt, IntegrityReport, Issue, Head, FHIRResource, JsonValue, uuid_string)
from .serialization import encode_json, hash_bytes
from .archive import (_writer_lock, _files, _read, _json, _safe, _write,
                      _sync_tree, _sync_directory, _history, _references,
                      open_vault, open_definitions, doctor, head)
from .query import parse_reference


def _publish(stage: Path, destination: Path):
    """Atomic absent-destination rename on qualified POSIX systems."""
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == 'darwin':
        function = libc.renamex_np
        result = function(os.fsencode(stage), os.fsencode(destination), 4)  # RENAME_EXCL
    elif sys.platform.startswith('linux') and hasattr(libc, 'renameat2'):
        result = libc.renameat2(-100, os.fsencode(stage), -100, os.fsencode(destination), 1)
    else:
        raise ArchiveError('UNSUPPORTED_VERSION', 'Atomic no-replace directory publication is unavailable on this platform.')
    if result:
        code = ctypes.get_errno()
        if code in (errno.EEXIST, errno.ENOTEMPTY):
            raise ArchiveError('DESTINATION_EXISTS', 'Destination must not exist.')
        raise ArchiveError('IO_ERROR', 'Atomic directory publication failed.')
    _sync_directory(destination.parent)


def _destination(destination: Path, source: Path | None = None):
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ArchiveError('DESTINATION_EXISTS', 'Destination must not exist.')
    if source is not None and destination.resolve().is_relative_to(source.resolve()):
        raise ArchiveError('INVALID_INPUT', 'Backup/export destination must be outside the vault.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def _copy(source, target, paths):
    for relative in sorted(paths):
        data = _read(source, relative)
        path = _safe(target, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        _write(path, data)


def _blocked(report):
    if report.issues:
        raise ArchiveError('INTEGRITY', 'Snapshot contains corruption or unaccounted material; run doctor and preserve all reported paths.',
                           {'issues': [asdict(i) for i in report.issues]})


def fhir_collection(vault: Vault, person: str, resourceRefs: tuple[ResourceRef, ...] = (), *,
                    at: Head | None = None) -> tuple[FHIRResource, list[dict[str, JsonValue]]]:
    """Return (derived collection, explicit revision/fullUrl map) at one Head.

    Empty selection means all current resources. Exact historical references
    remain exact; versionless references resolve at the same captured Head.
    No network, inference, accepted-byte rewrite or cross-person resolution.
    """
    uuid_string(person)
    at = at or head(vault, person)
    if at is None:
        raise ArchiveError('PERSON_NOT_FOUND', 'Selected person has no accepted history.')
    from .archive import _snapshot
    revisions, current = {}, {}
    for _, directory, change in _snapshot(vault,person,at):
        for entry in change['resources']:
            resource = _json(directory,entry['path'])
            key = (entry['type'],entry['id'],entry['versionId'])
            revisions[key] = resource
            current[key[:2]] = resource
    def resolved(ref):
        resource = (revisions.get((ref.resourceType,ref.id,ref.versionId)) if ref.versionId
                    else current.get((ref.resourceType,ref.id)))
        if resource is None:
            raise ArchiveError('UNRESOLVED_REVISION','Snapshot reference closure is incomplete.')
        return resource
    pending = list(resourceRefs) or [ResourceRef(r['resourceType'], r['id'], r['meta']['versionId'])
                                    for r in current.values()]
    resources = {}
    while pending:
        resource = resolved(pending.pop())
        key = (resource['resourceType'], resource['id'], resource['meta']['versionId'])
        if key in resources:
            continue
        resources[key] = resource
        pending.extend(parse_reference(ref) for ref in _references(resource))
    mapping = [dict(personId=person, resourceType=k[0], id=k[1], versionId=k[2],
                    fullUrl='urn:uuid:'+k[2], references={ref:'urn:uuid:'+resolved(parse_reference(ref))['meta']['versionId'] for ref in _references(resources[k])}) for k in sorted(resources)]
    def rewrite(value):
        if isinstance(value, dict):
            if 'reference' in value:
                target = resolved(parse_reference(value['reference']))
                value['reference'] = 'urn:uuid:'+target['meta']['versionId']
            for item in value.values():
                rewrite(item)
        elif isinstance(value, list):
            for item in value:
                rewrite(item)
    entries = []
    for item in mapping:
        resource = deepcopy(resources[(item['resourceType'],item['id'],item['versionId'])])
        rewrite(resource)
        entries.append({'fullUrl':item['fullUrl'], 'resource':resource})
    return {'resourceType':'Bundle', 'type':'collection', 'entry':entries}, mapping


def _scope_sources(vault, person):
    # Person assignment authorizes intake, not disclosure of every page of a PDF.
    # There is no reviewed derivative/scope receipt in format 1 yet: fail closed.
    for _, directory, change in _history(vault, person):
        if any(a['mediaType']=='application/pdf' for a in change['assets']):
            raise ArchiveError('SOURCE_SCOPE_REVIEW_REQUIRED',
                               'PDF disclosure requires a reviewed source-scope or derivative workflow. Use selected-current --no-sources for a clinical snapshot.')


def _manifest(stage, kind, people, heads, omissions, mapping, counts):
    files = [{'path':p, 'sha256':hash_bytes(_read(stage,p)), 'size':len(_read(stage,p))}
             for p in sorted(_files(stage))]
    value = {'format':'helseark-export-1', 'exportId':str(uuid4()), 'kind':kind,
             'people':people, 'heads':heads, 'omissions':list(omissions),
             'referenceMap':mapping, 'counts':counts, 'files':files}
    _write(stage/'export.json', encode_json(value))
    return value


def _export(vault, destination, *, person=None, selection=None, includeWork=False):
    destination = _destination(destination, vault.root)
    stage = Path(mkdtemp(prefix='.helseark-export-', dir=destination.parent))
    try:
        with _writer_lock(vault):
            open_vault(vault.root)
            _blocked(doctor(vault))
            people = [person] if person else sorted(p.name for p in (vault.root/'people').iterdir())
            if person:
                uuid_string(person); head(vault,person)
                if selection.includeSources:
                    _scope_sources(vault,person)
            heads = {p:asdict(head(vault,p)) if head(vault,p) else None for p in people}
            selected = selection is not None and selection.mode=='selected-current'
            omissions = ('original history chain', 'unselected resource revisions', 'original review and evidence envelopes', 'work', 'derived', '.runtime')
            mapping = []
            if selected:
                support = {p for p in _files(vault.root) if p.startswith(('definitions/','agent-kit/')) or p in ('vault.json','README.md','AGENTS.md','CLAUDE.md')}
                _copy(vault.root,stage/'support',support)
                bundle,mapping = fhir_collection(vault,person,selection.resourceRefs)
                _write(stage/'collection.json',encode_json(bundle))
                included = {(m['resourceType'],m['id'],m['versionId']) for m in mapping}
                # Copy original bytes separately; never serialize them from derived resources.
                (stage/'resources').mkdir(exist_ok=True)
                for _,directory,change in _history(vault,person):
                    for entry in change['resources']:
                        if (entry['type'],entry['id'],entry['versionId']) in included:
                            _write(stage/f"resources/{entry['versionId']}.json",_read(directory,entry['path']))
                asset_paths = set()
                if selection.includeSources:
                    for _,_,change in _history(vault,person):
                        asset_paths.update(f"people/{person}/{a['path']}" for a in change['assets'])
                    for _,directory,_ in _history(vault,person):
                        proposal = _json(directory,'proposal.json')
                        asset_paths.update(f"people/{person}/{b['path']}" for b in proposal.get('importReview',{}).get('bindings',[]))
                    _copy(vault.root,stage/'sources',asset_paths)
                else:
                    omissions += ('all source assets and review/evidence envelopes',)
                counts = {'changes':0,'resources':len(mapping),'assets':sum(p.endswith('/blob') for p in asset_paths)}
                kind = 'selected-current'
            else:
                paths = set()
                for relative in _files(vault.root):
                    parts = Path(relative).parts
                    if parts[0] in ('.runtime','derived') or ('work' in parts and not includeWork):
                        continue
                    if parts[0]=='people' and parts[1] not in people:
                        continue
                    paths.add(relative)
                _copy(vault.root,stage/'vault',paths)
                (stage/'vault/people').mkdir(exist_ok=True)
                # Empty accepted directories are significant after an interrupted genesis.
                for p in people:
                    (stage/f'vault/people/{p}/accepted').mkdir(parents=True,exist_ok=True)
                report = doctor(open_vault(stage/'vault'))
                _blocked(report)
                counts = {'changes':report.checkedChanges,'resources':report.checkedResources,'assets':report.checkedAssets}
                omissions = ('derived','.runtime') + (() if includeWork else ('work',))
                kind = 'full-person' if person else 'backup'
            _write(stage/'README.md',b'Helseark export format 1. export.json inventories every other file by SHA-256 and byte size.\n'
                   b'vault/ is exact accepted authority for backup/full-person; support/ and resources/ describe a NEW selected snapshot.\n'
                   b'collection.json is derived; referenceMap maps exact revisions to urn:uuid fullUrls. Original resource bytes remain separate.\n'
                   b'No signatures or encryption. Hashes detect changes, not a malicious rewrite of the entire folder.\n')
            manifest = _manifest(stage,kind,people,heads,omissions,mapping,counts)
            _blocked(verify_export(stage))
            _sync_tree(stage)
            _publish(stage,destination)
            _remember_external(vault,people,destination)
        return ExportReceipt(destination,hash_bytes(encode_json(manifest)),len(people),
                             counts['resources'],counts['assets'],tuple(omissions))
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def backup(vault: Vault, destination: Path, *, includeWork: bool = False) -> ExportReceipt:
    return _export(vault,destination,includeWork=includeWork)


def export_person(vault: Vault, person: str, destination: Path, selection: ExportSelection) -> ExportReceipt:
    return _export(vault,destination,person=person,selection=selection)


def _verify(bundle):
    if not bundle.is_dir() or bundle.is_symlink():
        raise ArchiveError('UNSAFE_PATH','Only regular export folders are accepted. ZIP/tar extraction is not supported.')
    actual = _files(bundle)
    manifest = _json(bundle,'export.json')
    # The installed schema is only a format parser, not authority for archived clinical pins.
    from .archive import _bundled_root
    schema = _json(_bundled_root(),'schemas/0.1.0/export.schema.json')
    if not Draft202012Validator(schema).is_valid(manifest):
        raise ArchiveError('INVALID_ENVELOPE','Invalid export manifest.')
    expected = {f['path'] for f in manifest['files']}
    if len(expected)!=len(manifest['files']) or actual != expected | {'export.json'}:
        raise ArchiveError('INTEGRITY','Export inventory has missing, duplicate or extra files.')
    for item in manifest['files']:
        data = _read(bundle,item['path'])
        if len(data)!=item['size'] or hash_bytes(data)!=item['sha256']:
            raise ArchiveError('INTEGRITY','Export digest mismatch.',{'path':item['path']})
    if manifest['kind']=='full-person' and len(manifest['people'])!=1:
        raise ArchiveError('INTEGRITY','Full-person export must contain exactly one person.')
    if manifest['kind'] in ('backup','full-person'):
        v = open_vault(bundle/'vault')
        report = doctor(v)
        if sorted(p.name for p in (v.root/'people').iterdir()) != sorted(manifest['people']):
            raise ArchiveError('INTEGRITY','Export person inventory mismatch.')
        heads = {p:asdict(head(v,p)) if head(v,p) else None for p in manifest['people']}
        if heads != manifest['heads']:
            raise ArchiveError('INTEGRITY','Export heads mismatch.')
        counts = dict(changes=report.checkedChanges,resources=report.checkedResources,assets=report.checkedAssets)
        if counts != manifest['counts']:
            raise ArchiveError('INTEGRITY','Export integrity counts mismatch.')
        return report
    if len(manifest['people'])!=1 or set(manifest['heads'])!=set(manifest['people']):
        raise ArchiveError('INTEGRITY','Selected snapshot must bind exactly one person and Head.')
    if manifest['counts']['changes']!=0 or manifest['counts']['assets']!=sum(p.startswith('sources/') and p.endswith('/blob') for p in actual):
        raise ArchiveError('INTEGRITY','Selected snapshot counts differ from its inventory.')
    open_definitions(bundle/'support')
    from .agent_context import _vault_kit
    _vault_kit(open_definitions(bundle/'support'))
    collection = _json(bundle,'collection.json')
    mapping = manifest['referenceMap']
    if not isinstance(collection,dict) or collection.get('resourceType')!='Bundle' or collection.get('type')!='collection':
        raise ArchiveError('INTEGRITY','Expected derived FHIR collection.')
    if len(mapping)!=manifest['counts']['resources'] or len(mapping)!=len(collection['entry']):
        raise ArchiveError('INTEGRITY','Snapshot mapping count mismatch.')
    urls = {m['fullUrl'] for m in mapping}
    if len(urls)!=len(mapping):
        raise ArchiveError('INTEGRITY','Duplicate snapshot mapping.')
    if {e['fullUrl'] for e in collection['entry']} != urls:
        raise ArchiveError('INTEGRITY','Collection entries differ from mapping.')
    if {p for p in actual if p.startswith('resources/')} != {f"resources/{m['versionId']}.json" for m in mapping}:
        raise ArchiveError('INTEGRITY','Snapshot resource inventory differs from mapping.')
    originals = {}
    for item in mapping:
        uuid_string(item['id']);uuid_string(item['versionId'])
        if item['personId'] not in manifest['people'] or item['fullUrl']!='urn:uuid:'+item['versionId']:
            raise ArchiveError('INTEGRITY','Snapshot mapping identity mismatch.')
        resource = _json(bundle,f"resources/{item['versionId']}.json")
        if (resource['resourceType'],resource['id'],resource['meta']['versionId'])!=(item['resourceType'],item['id'],item['versionId']):
            raise ArchiveError('INTEGRITY','Original revision differs from mapping.')
        originals[item['fullUrl']] = resource
    for entry in collection['entry']:
        if entry['fullUrl'] not in originals or any(ref not in urls for ref in _references(entry['resource'])):
            raise ArchiveError('INTEGRITY','Snapshot has unresolved references.')
        original = deepcopy(originals[entry['fullUrl']])
        # Check derived values while resolving each original Reference through the declared map.
        def rewrite(value):
            if isinstance(value,dict):
                if 'reference' in value:
                    ref = parse_reference(value['reference'])
                    matches = [m for m in mapping if m['resourceType']==ref.resourceType and m['id']==ref.id and
                               (ref.versionId is None or m['versionId']==ref.versionId)]
                    if ref.versionId is None:
                        matches = [m for m in matches if m['fullUrl']==next(x for x in mapping if x['fullUrl']==entry['fullUrl'])['references'].get(value['reference'])]
                    if len(matches)!=1:
                        raise ArchiveError('INTEGRITY','Ambiguous or missing original reference mapping.')
                    value['reference']=matches[0]['fullUrl']
                for x in value.values():rewrite(x)
            elif isinstance(value,list):
                for x in value:rewrite(x)
        rewrite(original)
        if encode_json(original)!=encode_json(entry['resource']):
            raise ArchiveError('INTEGRITY','Derived collection differs from original revision.')
    return IntegrityReport((),0,len(mapping),manifest['counts']['assets'],())


def verify_export(bundle: Path) -> IntegrityReport:
    try:
        return _verify(Path(bundle))
    except (ArchiveError, KeyError, TypeError, ValueError, OSError) as error:
        code = error.code if isinstance(error,ArchiveError) else 'INTEGRITY'
        path = error.details.get('path','export.json') if isinstance(error,ArchiveError) else 'export.json'
        return IntegrityReport((Issue(code,'error',path,None,'Preserve this bundle; recover the affected file from a verified copy before restore.'),),0,0,0,())


def restore(bundle: Path, destination: Path) -> Vault:
    bundle = Path(bundle).absolute()
    destination = _destination(destination)
    # Capture the manifest once; later copies must match this verified inventory.
    manifest_bytes = _read(bundle,'export.json') if bundle.is_dir() and not bundle.is_symlink() else None
    _blocked(verify_export(bundle))
    if manifest_bytes != _read(bundle,'export.json'):
        raise ArchiveError('INTEGRITY','Export manifest changed during verification.')
    from .serialization import decode_canonical_json
    manifest = decode_canonical_json(manifest_bytes)
    if manifest['kind']=='selected-current':
        raise ArchiveError('INVALID_INPUT','A selected snapshot is an exchange artifact, not an accepted vault history.')
    stage = Path(mkdtemp(prefix='.helseark-restore-',dir=destination.parent))
    try:
        _copy(bundle/'vault',stage,_files(bundle/'vault'))
        (stage/'people').mkdir(exist_ok=True)
        for p in manifest['people']:
            (stage/f'people/{p}/accepted').mkdir(parents=True,exist_ok=True)
        inventory = {item['path'][6:]:item for item in manifest['files'] if item['path'].startswith('vault/')}
        if _files(stage) != set(inventory):
            raise ArchiveError('INTEGRITY','Staged restore inventory differs from verified export.')
        for relative,item in inventory.items():
            data = _read(stage,relative)
            if hash_bytes(data)!=item['sha256'] or len(data)!=item['size']:
                raise ArchiveError('INTEGRITY','Export changed while copying restore staging.',{'path':relative})
        _blocked(doctor(open_vault(stage)))
        _sync_tree(stage)
        _publish(stage,destination)
        return open_vault(destination)
    finally:
        if stage.exists():shutil.rmtree(stage)


_ERASURE_LIMITS = (
    'Quarantine is a recoverable copy, not secure deletion.',
    'Unknown external copies, agent packets, shared exports, snapshots, SSD remnants and backups may remain.',
    'No automated purge; OS permissions and cooperating single-writer locking are required.',
)


def _erasure_scope(vault, person):
    """Select complete person-owned work trees; never delete a shared cache."""
    from .serialization import decode_json
    canonical = (f'people/{person}',) if (vault.root/f'people/{person}').exists() else ()
    work, derived = set(), set()
    files = _files(vault.root)
    for path in sorted(files):
        if not path.startswith(('work/', 'derived/', '.runtime/')) or path.startswith('.runtime/erasures/'):
            continue
        if not path.endswith('.json'):
            continue
        try:
            value = decode_json(_read(vault.root,path))
        except ArchiveError:
            # Unknown disposable content must be inspected, never silently erased.
            if person.encode() in _read(vault.root,path):
                raise ArchiveError('ERASURE_SCOPE_UNKNOWN','Person-linked malformed disposable file needs manual isolation.',{'path':path})
            continue
        if not isinstance(value,dict):
            continue
        if value.get('personId') == person:
            parts = path.split('/')
            # Work metadata owns its draft directory; runtime records own only themselves.
            root = '/'.join(parts[:-1]) if (path.startswith('work/') and len(parts)>2) or path.startswith('.runtime/staging/') else path
            (derived if path.startswith('derived/') else work).add(root)
        elif path.startswith('.runtime/prepared/') and isinstance(value.get('candidatePath'),str):
            candidate = Path(value['candidatePath'])/'candidate.json'
            if candidate.exists():
                from .intake import _bounded_json, LIMITS
                meta = _bounded_json(candidate,LIMITS)
                if isinstance(meta,dict) and meta.get('personId')==person:
                    work.add(path)
    for path in tuple(work):
        if path.startswith('.runtime/prepared/'):
            review = path.replace('.runtime/prepared/','.runtime/reviews/')
            if review in files:work.add(review)
    for prefix, selected in [('derived',derived),('work',work)]:
        owned = f'{prefix}/{person}'
        if (vault.root/owned).exists(): selected.add(owned)
    # Refuse ambiguous copies rather than claim their removal or touch another person.
    for path in sorted(files):
        if path.startswith(('work/','derived/','.runtime/staging/')) and person.encode() in _read(vault.root,path):
            if not any(path==r or path.startswith(r+'/') for r in (*work,*derived)):
                raise ArchiveError('ERASURE_SCOPE_UNKNOWN','Unclassified person-linked work/derived data needs manual isolation.',{'path':path})
    other_people = [p.name.encode() for p in (vault.root/'people').iterdir() if p.name != person]
    for path in sorted(files):
        if any(path==r or path.startswith(r+'/') for r in (*work,*derived)) and path.startswith(('work/','derived/','.runtime/staging/')):
            if any(other in _read(vault.root,path) for other in other_people):
                raise ArchiveError('ERASURE_SCOPE_UNKNOWN','Selected disposable tree also identifies another person; isolate it manually.',{'path':path})
    def minimal(paths):
        return tuple(p for p in sorted(paths) if not any(p.startswith(q+'/') for q in paths if p!=q))
    return canonical, minimal(work), minimal(derived)


def _erasure_value(plan):
    from .agent_context import document
    value = document(plan)
    value.pop('digest')
    return value


def read_erasure_plan(path: Path):
    """Strict local plan reload; approval is a separately supplied digest."""
    from .contracts import ErasurePlan
    from .serialization import decode_json
    try:
        raw = decode_json(_read(Path(path).parent,Path(path).name))
        raw['baseHeads'] = {p:Head(**h) if h else None for p,h in raw['baseHeads'].items()}
        for key in ('canonicalPaths','workPaths','derivedPaths','knownExternalCopies','limitations'):
            raw[key] = tuple(raw[key])
        raw['quarantineDestination'] = Path(raw['quarantineDestination'])
        return ErasurePlan(**raw)
    except (KeyError,TypeError,ValueError,AttributeError):
        raise ArchiveError('INVALID_INPUT','Expected a complete erasure plan.') from None


def _heads(vault):
    return {p.name:head(vault,p.name) for p in sorted((vault.root/'people').iterdir())}


def plan_person_erasure(vault: Vault, person: str, quarantineDestination: Path):
    """Capture heads and every selected byte under lock; does not remove data."""
    from dataclasses import replace
    from .contracts import ErasurePlan
    uuid_string(person)
    destination = Path(quarantineDestination).absolute()
    if destination.exists() or destination.is_symlink() or destination.resolve().is_relative_to(vault.root.resolve()):
        raise ArchiveError('INVALID_INPUT','Quarantine must be an absent destination outside the active vault.')
    from .intake import _directory
    fd = _directory(destination.parent); os.close(fd)
    if destination.parent.stat().st_dev != vault.root.stat().st_dev:
        raise ArchiveError('INVALID_INPUT','Recoverable atomic removal requires quarantine on the same filesystem.')
    with _writer_lock(vault):
        if head(vault,person) is None:
            raise ArchiveError('PERSON_NOT_FOUND','Selected person has no accepted history.')
        canonical, work, derived = _erasure_scope(vault,person)
        roots = (*canonical,*work,*derived)
        inventory = {p:hash_bytes(_read(vault.root,p)) for p in sorted(_files(vault.root))
                     if any(p==r or p.startswith(r+'/') for r in roots)}
        external = []
        for path in sorted(_files(vault.root)):
            if path.startswith('.runtime/external-copies/'):
                record = _json(vault.root,path)
                if record.get('personId')==person:
                    external.extend(record['destinations'])
        for path in work:
            if path.startswith('.runtime/') and path in inventory:
                record = _json(vault.root,path)
                external.extend(record[k] for k in ('packetPath','outputDirectory','candidatePath') if isinstance(record.get(k),str) and not Path(record[k]).is_relative_to(vault.root))
        plan = ErasurePlan('',person,_heads(vault),canonical,work,derived,destination,
            tuple(sorted(set(external))),_ERASURE_LIMITS,vault.config.vaultId,inventory)
        return replace(plan,digest=hash_bytes(encode_json(_erasure_value(plan))))


def _erasure_check(vault, plan, approvedDigest, *, resuming=False):
    if approvedDigest != plan.digest or hash_bytes(encode_json(_erasure_value(plan))) != approvedDigest or plan.vaultId!=vault.config.vaultId:
        raise ArchiveError('APPROVAL_REQUIRED','Explicit approval must match the exact plan digest and vault.')
    uuid_string(plan.personId)
    current = _heads(vault)
    expected = dict(plan.baseHeads)
    if resuming and plan.personId not in current:
        expected.pop(plan.personId,None)
    if current != expected:
        raise ArchiveError('STALE_BASE','Vault heads or roster changed after removal planning.')
    roots = (*plan.canonicalPaths,*plan.workPaths,*plan.derivedPaths)
    if plan.canonicalPaths != (f'people/{plan.personId}',):
        raise ArchiveError('INVALID_INPUT','Plan canonical scope is invalid.')
    for root in roots:
        _safe(vault.root,root)
        if not root.startswith((f'people/{plan.personId}', 'work/', 'derived/', '.runtime/')):
            raise ArchiveError('INVALID_INPUT','Plan path outside supported removal scope.')
    return roots


def _erasure_inventory(vault, plan, quarantine):
    """Every captured byte must occur exactly once, active or quarantined."""
    roots = (*plan.canonicalPaths,*plan.workPaths,*plan.derivedPaths)
    found = {}
    for location in (vault.root,quarantine/'files'):
        if not location.exists(): continue
        paths = _files(location)
        selected = {p for p in paths if location!=vault.root or any(p==r or p.startswith(r+'/') for r in roots)}
        for path in selected:
            if path in found or path not in plan.inventory or hash_bytes(_read(location,path))!=plan.inventory[path]:
                raise ArchiveError('INTEGRITY','Removal inventory changed; preserve active and quarantine trees.',{'path':path})
            found[path] = True
    if set(found)!=set(plan.inventory):
        raise ArchiveError('INTEGRITY','Removal inventory is incomplete; preserve both trees.')


def apply_person_erasure(vault: Vault, plan, approvedDigest: str):
    """Move only approved paths. An interrupted operation can resume or restore.

    plan.json is written and synced before the first rename. No copy/delete
    fallback across devices and no automatic quarantine purge are permitted.
    """
    from .contracts import ErasureReceipt
    from .agent_context import document
    quarantine = plan.quarantineDestination
    with _writer_lock(vault):
        resuming = quarantine.exists()
        roots = _erasure_check(vault,plan,approvedDigest,resuming=resuming)
        if resuming:
            if read_erasure_plan(quarantine/'plan.json') != plan:
                raise ArchiveError('INTEGRITY','Quarantine belongs to a different plan.')
        else:
            # Re-evaluate ownership, including newly created work after planning.
            if _erasure_scope(vault,plan.personId) != (plan.canonicalPaths,plan.workPaths,plan.derivedPaths):
                raise ArchiveError('STALE_BASE','Disposable person scope changed after planning.')
            from .intake import _new_directory
            _destination(quarantine,vault.root)
            _new_directory(quarantine)
            _write(quarantine/'plan.json',encode_json(document(plan)))
            _sync_tree(quarantine)
        active_scope = _erasure_scope(vault,plan.personId)
        if any(r not in roots for group in active_scope for r in group):
            raise ArchiveError('STALE_BASE','New person-owned work appeared during interrupted removal.')
        _erasure_inventory(vault,plan,quarantine)
        _sync_directory(quarantine.parent)
        for relative in roots:
            source = _safe(vault.root,relative)
            if not source.exists(): continue
            target = _safe(quarantine/'files',relative)
            target.parent.mkdir(parents=True,exist_ok=True)
            source_parent = source.parent
            _publish(source,target)
            _sync_directory(source_parent)
            from .archive import _publication_boundary
            _publication_boundary('erasure-after-move')
        _erasure_inventory(vault,plan,quarantine)
        receipt = ErasureReceipt(quarantine,roots,(str(quarantine),*plan.knownExternalCopies,*plan.limitations))
        receipt_path = quarantine/'receipt.json'
        if not receipt_path.exists(): _write(receipt_path,encode_json(document(receipt)))
        _sync_tree(quarantine)
        return receipt


def restore_person_erasure(vault: Vault, quarantine: Path, approvedDigest: str):
    """Restore exact quarantined paths to their original absent active locations.

    Also recovers interrupted removal/restore; refuses changed selected-person
    heads and any collision rather than overwriting active work.
    """
    quarantine = Path(quarantine).absolute()
    plan = read_erasure_plan(quarantine/'plan.json')
    if quarantine != plan.quarantineDestination:
        raise ArchiveError('INVALID_INPUT','Quarantine location differs from its plan.')
    with _writer_lock(vault):
        roots = _erasure_check(vault,plan,approvedDigest,resuming=True)
        _erasure_inventory(vault,plan,quarantine)
        for relative in reversed(roots):
            source = _safe(quarantine/'files',relative)
            if not source.exists(): continue
            target = _safe(vault.root,relative)
            target.parent.mkdir(parents=True,exist_ok=True)
            source_parent = source.parent
            _publish(source,target)
            _sync_directory(source_parent)
        _erasure_inventory(vault,plan,quarantine)
        return head(vault,plan.personId)


def _remember_external(vault, people, destination):
    """Retain known successful copy destinations under the export writer lock."""
    for person in people:
        directory = _safe(vault.root,'.runtime/external-copies')
        directory.mkdir(exist_ok=True)
        _write(directory/(str(uuid4())+'.json'),encode_json({'personId':person,'destinations':[str(destination)]}))
