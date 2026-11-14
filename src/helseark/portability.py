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
import re
import shutil
import sys

from jsonschema import Draft202012Validator

from .contracts import (ArchiveError, Vault, ResourceRef, ExportSelection,
                        ExportReceipt, IntegrityReport, Issue, Head, FHIRResource, JsonValue, uuid_string)
from .serialization import encode_json, hash_bytes
from .archive import (_writer_lock, _files, _read, _json, _safe, _write,
                      _sync_tree, _sync_directory, _history, _references,
                      open_vault, open_definitions, doctor, head, _support_paths, _person_paths)
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
    # No explicit host-recorded review was supplied: retain default denial.
    for _, directory, change in _history(vault, person):
        if any(a['mediaType']=='application/pdf' for a in change['assets']):
            raise ArchiveError('SOURCE_SCOPE_REVIEW_REQUIRED',
                               'PDF disclosure requires a reviewed source-scope or derivative workflow. Use selected-current --no-sources for a clinical snapshot.')


def _manifest(stage, kind, people, heads, omissions, mapping, counts, disclosure=None):
    files = [{'path':p, 'sha256':hash_bytes(_read(stage,p)), 'size':len(_read(stage,p))}
             for p in sorted(_files(stage))]
    value = {'format':'helseark-export-1', 'exportId':str(uuid4()), 'kind':kind,
             'people':people, 'heads':heads, 'omissions':list(omissions),
             'referenceMap':mapping, 'counts':counts, 'files':files}
    if disclosure is not None:
        value.update(format='helseark-export-2', sourceDisclosure=disclosure)
    _write(stage/'export.json', encode_json(value))
    return value


def _export(vault, destination, *, person=None, selection=None, includeWork=False, review=None):
    destination = _destination(destination, vault.root)
    stage = Path(mkdtemp(prefix='.helseark-export-', dir=destination.parent))
    try:
        with _writer_lock(vault):
            open_vault(vault.root)
            _blocked(doctor(vault))
            people = [person] if person else sorted(p.name for p in (vault.root/'people').iterdir())
            disclosure = None
            if review is not None:
                from .source_disclosure import reviewed_disclosure
                disclosure = reviewed_disclosure(vault,person,selection,review)
            if person:
                uuid_string(person); head(vault,person)
                if selection.includeSources and disclosure is None:
                    _scope_sources(vault,person)
            heads = {p:asdict(head(vault,p)) if head(vault,p) else None for p in people}
            selected = selection is not None and selection.mode=='selected-current'
            omissions = ('original history chain', 'unselected resource revisions', 'original review and evidence envelopes', 'work', 'derived', '.runtime')
            mapping = []
            if selected:
                support = _support_paths(vault)
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
                if selection.includeSources and (disclosure is None or disclosure['plan']['originalDisposition']=='included-exact'):
                    for _,_,change in _history(vault,person):
                        asset_paths.update(f"people/{person}/{a['path']}" for a in change['assets'])
                    for _,directory,_ in _history(vault,person):
                        proposal = _json(directory,'proposal.json')
                        asset_paths.update(f"people/{person}/{b['path']}" for b in proposal.get('importReview',{}).get('bindings',[]))
                    _copy(vault.root,stage/'sources',asset_paths)
                else:
                    omissions += ('all source assets and review/evidence envelopes',)
                if disclosure and disclosure['plan']['derivatives']:
                    from .source_disclosure import _derivative_objects, _derivative_bytes
                    for item in _derivative_objects(disclosure['plan']['derivatives']):
                        data = _derivative_bytes(review, item)
                        path = stage/item['path']; path.parent.mkdir(parents=True,exist_ok=True); _write(path,data)
                    omissions += tuple(disclosure['plan']['limitations'])
                derivative_count = len({d['path'] for d in disclosure['plan']['derivatives']}) if disclosure else 0
                counts = {'changes':0,'resources':len(mapping),'assets':sum(p.endswith('/blob') for p in asset_paths)+derivative_count}
                kind = 'selected-current'
            else:
                paths = _support_paths(vault)
                for p in people:
                    paths.update(_person_paths(vault, p, _history(vault, p)))
                if includeWork:
                    # Work is explicitly unaccepted, opt-in material, never scope authority.
                    for work in ['work', *(f'people/{p}/work' for p in people)]:
                        paths.update(f'{work}/{f}' for f in _files(_safe(vault.root, work)))
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
            readme = (b'Helseark export. export.json inventories every other file by SHA-256 and byte size.\n'
                   b'vault/ is exact accepted authority for backup/full-person; support/ and resources/ describe a NEW selected snapshot.\n'
                   b'collection.json is derived; referenceMap maps exact revisions to urn:uuid fullUrls. Original resource bytes remain separate.\n'
                   b'No signatures or encryption. Hashes detect changes, not a malicious rewrite of the entire folder.\n')
            if disclosure:
                notice = ('\nSOURCE DISCLOSURE REVIEW: ' + disclosure['plan']['originalDisposition'] + '\n' +
                          '\n'.join(disclosure['plan']['limitations']) + '\n')
                readme += notice.encode()
            _write(stage/'README.md',readme)
            manifest = _manifest(stage,kind,people,heads,omissions,mapping,counts,disclosure)
            _blocked(verify_export(stage))
            _sync_tree(stage)
            _publish(stage,destination)
        return ExportReceipt(destination,hash_bytes(encode_json(manifest)),len(people),
                             counts['resources'],counts['assets'],tuple(omissions))
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def backup(vault: Vault, destination: Path, *, includeWork: bool = False) -> ExportReceipt:
    return _export(vault,destination,includeWork=includeWork)


def export_person(vault: Vault, person: str, destination: Path, selection: ExportSelection, *, review: Path | None = None) -> ExportReceipt:
    return _export(vault,destination,person=person,selection=selection,review=review)


def _verify(bundle):
    if not bundle.is_dir() or bundle.is_symlink():
        raise ArchiveError('UNSAFE_PATH','Only regular export folders are accepted. ZIP/tar extraction is not supported.')
    actual = _files(bundle)
    manifest = _json(bundle,'export.json')
    # The installed schema is only a format parser, not authority for archived clinical pins.
    from .archive import _bundled_root
    version = manifest.get('format') if isinstance(manifest,dict) else None
    schemas = {'helseark-export-1':'export.schema.json','helseark-export-2':'export-2.schema.json'}
    if version not in schemas:
        raise ArchiveError('UNSUPPORTED_VERSION','Unsupported export format; use a compatible reader.')
    schema = _json(_bundled_root(),'schemas/0.1.0/'+schemas[version])
    if not Draft202012Validator(schema).is_valid(manifest):
        raise ArchiveError('INVALID_ENVELOPE','Invalid export manifest.')
    expected = {f['path'] for f in manifest['files']}
    if len(expected)!=len(manifest['files']) or actual != expected | {'export.json'}:
        raise ArchiveError('INTEGRITY','Export inventory has missing, duplicate or extra files.')
    for item in manifest['files']:
        data = _read(bundle,item['path'])
        if len(data)!=item['size'] or hash_bytes(data)!=item['sha256']:
            raise ArchiveError('INTEGRITY','Export digest mismatch.',{'path':item['path']})
    if version=='helseark-export-2':
        from .source_disclosure import verify_disclosure
        verify_disclosure(bundle,manifest)
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
    if manifest['counts']['changes']!=0 or manifest['counts']['assets']!=sum(p.startswith(('sources/','derivatives/')) and p.endswith('/blob') for p in actual):
        raise ArchiveError('INTEGRITY','Selected snapshot counts differ from its inventory.')
    support_vault = open_definitions(bundle/'support')
    from .agent_context import _vault_kit
    _vault_kit(support_vault)
    if {p[8:] for p in actual if p.startswith('support/')} != _support_paths(support_vault):
        raise ArchiveError('INTEGRITY', 'Snapshot support differs from its pinned closure.')
    sources = {p for p in actual if p.startswith('sources/')}
    source_prefix = f"sources/people/{manifest['people'][0]}/assets/sha256/"
    if any(not p.startswith(source_prefix) or not re.fullmatch(
            r'[0-9a-f]{64}/(?:blob|source[.]json|extraction[.]json)', p[len(source_prefix):]) for p in sources):
        raise ArchiveError('INTEGRITY', 'Snapshot source path is outside the selected person asset scope.')
    allowed = {'export.json', 'README.md', 'collection.json'} | sources
    if version == 'helseark-export-2':
        # verify_disclosure already checked these exact objects and every mapping.
        allowed.update(item['path'] for item in manifest['sourceDisclosure']['plan']['derivatives'])
    allowed.update('support/' + p for p in _support_paths(support_vault))
    allowed.update(f"resources/{m['versionId']}.json" for m in manifest['referenceMap'])
    if actual != allowed:
        raise ArchiveError('INTEGRITY', 'Snapshot contains files outside its declared closure.')
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
        bindings = next(m for m in mapping if m['fullUrl'] == entry['fullUrl'])['references']
        if set(bindings) != set(_references(original)):
            raise ArchiveError('INTEGRITY', 'Original reference binding inventory mismatch.')
        # Check derived values while resolving each original Reference through the declared map.
        def rewrite(value):
            if isinstance(value,dict):
                if 'reference' in value:
                    ref = parse_reference(value['reference'])
                    matches = [m for m in mapping if m['resourceType']==ref.resourceType and m['id']==ref.id and
                               (ref.versionId is None or m['versionId']==ref.versionId)]
                    matches = [m for m in matches if m['fullUrl'] == bindings[value['reference']]]
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
