"""Offline kit closure and bounded, explicit-person context packets.

Only manifest-listed instructions are loadable. Clinical/source content never
participates in routing. Packets are disposable read snapshots, not authority,
permission grants or agent execution. Task4 owns prompt rendering.
"""
from dataclasses import asdict, is_dataclass
from collections.abc import Mapping
import hashlib
from pathlib import Path
import re
import shutil
from uuid import uuid4

from jsonschema import Draft202012Validator

from .archive import _bundled_root, _safe, _read, _history, head, resolve
from .contracts import (ArchiveError, Vault, ResourceRef, AgentTask, ContextRequest,
    AgentTaskDescriptor, CapabilityAvailability, ContextFile, ContextContinuation,
    AgentContext, RenderedPrompt, JsonValue, Issue, uuid_string, sha256_string)
from .serialization import decode_json, decode_canonical_json, encode_json, hash_bytes
from .validation import load_definition_registry

_TASKS = frozenset(('inspect', 'import', 'query', 'correct', 'export', 'verify', 'migrate'))
_CAPABILITIES = frozenset(('agent-discovery', 'agent-context', 'schema-export',
    'baseline-validation', 'person-identity', 'raw-record-selection'))
_INSTRUCTION_BUDGET = 32768


def document(value):
    """JSON representation shared by disk packets and CLI (no float coercion)."""
    if isinstance(value, AgentContext):
        fields = asdict(value)
        for name in ('maxRecords','maxDataBytes'):
            if fields[name] is None:
                del fields[name]
        return document(fields)
    if is_dataclass(value):
        return document(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {k: document(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [document(v) for v in value]
    return value


def _local(root, path):
    if root.is_symlink() or not isinstance(path, str) or not re.fullmatch(
            r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*', path):
        raise ArchiveError('UNSAFE_PATH', 'Kit paths must be confined local paths.')
    return _safe(root, path)


def _load_kit(kit: Path, expected_digest=None, registry=None):
    kit = Path(kit).absolute()
    if not _local(kit, 'manifest.json').is_file():
        raise ArchiveError('MISSING_KIT', 'Required local kit manifest is missing; no fallback is permitted.')
    data = _read(kit, 'manifest.json')
    if expected_digest is not None and hash_bytes(data) != expected_digest:
        raise ArchiveError('KIT_MISMATCH', 'Pinned kit manifest digest differs.')
    value = decode_json(data)
    if registry is None:
        schema = decode_json(_read(_bundled_root(), 'schemas/0.1.0/agent-kit.schema.json'))
        valid = Draft202012Validator(schema).is_valid(value)
    else:
        valid = registry.validate('urn:helseark:schema:0.1.0:agent-kit', value)
    if not valid:
        raise ArchiveError('INVALID_KIT', 'Kit manifest violates protocol 1.')
    # Explicit paths are checked independently of schema patterns, before any read.
    paths = [f['path'] for f in value['files']]
    if len(paths) != len(set(paths)) or set(t['id'] for t in value['tasks']) != _TASKS:
        raise ArchiveError('INVALID_KIT', 'Kit must have unique assets and exactly one entry per task.')
    files = {}
    for entry in value['files']:
        path = _local(kit, entry['path'])
        if not path.is_file():
            raise ArchiveError('MISSING_KIT', 'Required manifest-listed kit asset is missing.')
        content = _read(kit, entry['path'])
        if len(content) != entry['size'] or hash_bytes(content) != entry['sha256']:
            raise ArchiveError('KIT_MISMATCH', 'Manifest-listed kit asset differs.')
        if registry is not None and entry['path'] in registry.files and content != registry.files[entry['path']]:
            raise ArchiveError('KIT_MISMATCH', 'Kit reference copy differs from retained definition bytes.')
        if entry['path']=='definitions/lock.json' and hash_bytes(content)!=value['compatibility']['definitionLockSha256']:
            raise ArchiveError('KIT_MISMATCH', 'Kit definition-lock copy differs from compatible pin.')
        files[entry['path']] = content
    prompts = {p['id']: p for p in value['prompts']}
    if len(prompts) != len(value['prompts']):
        raise ArchiveError('INVALID_KIT', 'Duplicate prompt ID.')
    selected = list(value['baseInstructionPaths']) + ['templates/vault-AGENTS.md', 'templates/vault-CLAUDE.md']
    for task in value['tasks']:
        if task['skillPath']:
            selected.append(task['skillPath'])
        for name in task['promptIds']:
            if name not in prompts or task['id'] not in prompts[name]['taskIds']:
                raise ArchiveError('INVALID_KIT', 'Task prompt route is missing or incompatible.')
        for name in task['referencePaths'] + task['schemaPaths']:
            _local(kit, name)
    for prompt in value['prompts']:
        selected.append(prompt['path'])
        if prompt['path'] not in files or hash_bytes(files[prompt['path']]) != prompt['sha256']:
            raise ArchiveError('KIT_MISMATCH', 'Prompt digest differs from asset inventory.')
    for prompt in value['prompts']:
        for task in value['tasks']:
            if task['id'] in prompt['taskIds']:
                skill = task['skillPath']
                if (not skill or skill not in files or Path(skill).parent.name != prompt.get('skillId') or
                        hash_bytes(files[skill]) != prompt.get('skillSha256')):
                    raise ArchiveError('KIT_MISMATCH', 'Prompt skill identity/digest differs from task route.')
    if any(p not in files for p in selected) or 'START-HERE.md' not in value['baseInstructionPaths']:
        raise ArchiveError('MISSING_KIT', 'Required instruction asset is absent from manifest closure.')
    return kit, value, files, hash_bytes(data)


def _descriptor(task, manifest):
    capabilities = set(_CAPABILITIES)
    # Instruction existence is necessary, never evidence that a runtime exists.
    if (task['skillPath'] and (task['id'] == 'inspect' or task['promptIds']) and
            'AGENTS.md' in manifest['baseInstructionPaths']):
        capabilities.add('task-instructions')
    missing = tuple(c for c in task['requiredCapabilities'] if c not in capabilities)
    if 'task-instructions' not in capabilities and 'task-instructions' not in missing:
        missing += ('task-instructions',)
    values = {k: tuple(v) if isinstance(v, list) else v for k, v in task.items() if k != 'availability'}
    return AgentTaskDescriptor(**values, availability=CapabilityAvailability(
        'unavailable' if missing else 'available', missing))


def list_agent_tasks(kit: Path) -> list[AgentTaskDescriptor]:
    """Discover kit routes without opening a vault or reading any person."""
    _, manifest, _, _ = _load_kit(kit)
    return [_descriptor(t, manifest) for t in manifest['tasks']]


def _vault_kit(vault, registry=None):
    version, digest = vault.config.agentKitVersion, vault.config.agentKitLockSha256
    if not isinstance(version, str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version) or digest is None:
        raise ArchiveError('MISSING_KIT', 'Vault has no pinned compatible agent kit; no fallback is permitted.')
    sha256_string(digest)
    path = _safe(vault.root, f'agent-kit/{version}')
    if not _local(path, 'manifest.json').is_file():
        raise ArchiveError('MISSING_KIT', 'Pinned local kit release is missing; no fallback is permitted.')
    raw = _read(path, 'manifest.json')
    if hash_bytes(raw) != digest:
        raise ArchiveError('KIT_MISMATCH', 'Pinned kit manifest digest differs.')
    registry = registry or load_definition_registry(vault)
    kit, manifest, files, digest = _load_kit(path, digest, registry)
    if manifest['kitVersion'] != version or any(
            getattr(vault.config, k) != v for k, v in manifest['compatibility'].items()):
        raise ArchiveError('UNSUPPORTED_VERSION', 'Pinned kit is incompatible with this vault.')
    return kit, manifest, files, digest


def install_kit(bundle: Path, vault: Vault):
    """Init-only copy of the closed release, with generated thin routing files."""
    kit, manifest, files, digest = _load_kit(bundle / 'agent-kit', vault.config.agentKitLockSha256)
    if manifest['kitVersion'] != vault.config.agentKitVersion or any(
            getattr(vault.config, k) != v for k, v in manifest['compatibility'].items()):
        raise ArchiveError('UNSUPPORTED_VERSION', 'Bundled kit is incompatible with requested vault pins.')
    target = vault.root / 'agent-kit' / manifest['kitVersion']
    target.mkdir(parents=True)
    for relative, content in {**files, 'manifest.json': _read(kit, 'manifest.json')}.items():
        path = _local(target, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    routing = files['templates/vault-AGENTS.md'].decode('utf-8').replace('{{kitVersion}}', manifest['kitVersion'])
    if '{{' in routing:
        raise ArchiveError('INVALID_KIT', 'Unresolved vault routing template variable.')
    (vault.root / 'AGENTS.md').write_text(routing, encoding='utf-8')
    (vault.root / 'CLAUDE.md').write_bytes(files['templates/vault-CLAUDE.md'])


def _reference(path, data):
    return ContextFile(str(path), hash_bytes(data), len(data), str(path))


def _source(vault, person, digest):
    path = _safe(vault.root, f'people/{person}/assets/sha256/{digest}/blob')
    if not path.is_file():
        raise ArchiveError('SOURCE_MISSING', 'Selected source is absent from selected person.')
    sha, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            sha.update(block)
            size += len(block)
    if sha.hexdigest() != digest:
        raise ArchiveError('SOURCE_HASH_MISMATCH', 'Selected source bytes differ from requested digest.')
    return ContextFile(str(path), digest, size, str(path))


def _selected_evidence(directory, entry, record_path, registry):
    """Disposable exact-revision projection; original paths are provenance only."""
    original = _read(directory, 'evidence.json')
    value = decode_canonical_json(original)
    reference = f"{entry['type']}/{entry['id']}/_history/{entry['versionId']}"
    entries = [{'originalPointer':f'/entries/{index}', 'entry':item}
        for index,item in enumerate(value['entries']) if item.get('target',{}).get('reference',item.get('resourceRef'))==reference]
    selection = {'selectionVersion':1,'personId':value['personId'],
        'resourceRef':reference,'original':{'path':str(directory/'evidence.json'),
            'sha256':hash_bytes(original),'size':len(original)},'entries':entries}
    if 'producerProvenance' in value:
        selection['producerProvenance'] = value['producerProvenance']
    # Retained protocol-1 kits predate the disposable selection envelope. Their
    # original pinned evidence schema still validates every selected entry; do
    # not substitute installed definitions or expose the full accepted file.
    if 'schemas/0.1.0/agent-evidence-selection.schema.json' in registry.files:
        valid = registry.validate('urn:helseark:schema:0.1.0:agent-evidence-selection',selection)
    else:
        subset = {**value,'entries':[e['entry'] for e in entries]}
        valid = registry.validate('urn:helseark:schema:0.1.0:evidence',subset)
    if not valid:
        raise ArchiveError('INVALID_ENVELOPE','Evidence selection violates its pinned contract.')
    data = encode_json(selection)
    relative = 'evidence/'+Path(record_path).name
    return ContextFile(relative,hash_bytes(data),len(data),str(directory/'evidence.json')),data


def build_agent_context(vault: Vault, person: str, task: AgentTask,
                        request: ContextRequest, destination: Path) -> AgentContext:
    """Build a bounded snapshot; fail closed before making destination visible.

    Date semantics belong to Task7. Continuations bind exact scope and head;
    callers may increase page budgets but cannot change person/task/selection.
    """
    uuid_string(person)
    if task not in _TASKS:
        raise ArchiveError('UNKNOWN_TASK', 'Select a manifest task ID.')
    if not isinstance(request, ContextRequest):
        raise ArchiveError('INVALID_INPUT', 'Context request must be a ContextRequest.')
    if request.fromDate is not None or request.toDate is not None:
        raise ArchiveError('CAPABILITY_UNAVAILABLE', 'Date-filtered query contexts require the Task7 query API.')
    if task == 'import' and (not request.sourceHashes or request.resourceRefs or request.continuation):
        raise ArchiveError('INVALID_INPUT', 'Import requires explicit source hashes and excludes historical record selection.')
    if request.continuation is not None and (request.continuation.personId != person or request.continuation.taskId != task):
        raise ArchiveError('INVALID_CONTINUATION', 'Continuation belongs to another person or task.')
    destination = Path(destination).absolute()
    destination = destination.parent.resolve() / destination.name
    if destination.exists() or destination.is_symlink():
        raise ArchiveError('DESTINATION_EXISTS', 'Context destination must be absent.')
    # Working packets may live only in the explicitly selected person's work
    # area, or outside the vault. Never generate routing files in canonical paths.
    vault_root = vault.root.resolve()
    work_root = vault_root / 'people' / person / 'work'
    if ((destination == vault_root or vault_root in destination.parents) and
            destination != work_root and work_root not in destination.parents):
        raise ArchiveError('UNSAFE_PATH', 'Context output must be outside the vault or in selected person work.')
    registry = load_definition_registry(vault)
    kit, manifest, files, manifest_digest = _vault_kit(vault, registry)
    descriptor = _descriptor(next(t for t in manifest['tasks'] if t['id'] == task), manifest)
    contracts = []
    contract_paths = tuple(dict.fromkeys((*descriptor.schemaPaths, *descriptor.referencePaths)))
    # The registry verifies all retained bytes and resolves contracts offline.
    for relative in contract_paths:
        if relative not in registry.files:
            raise ArchiveError('MISSING_DEFINITION', 'Task contract/reference is not in the pinned definition registry.')
        if relative.endswith('.schema.json'):
            registry.resolve(relative)
        contracts.append(_reference(_safe(vault.root / 'definitions', relative), registry.files[relative]))
    # Large definitions remain exact references. Use existing schema_packet for
    # a standalone export; context does not implement another schema exporter.
    lock_data = _read(vault.root, 'definitions/lock.json')
    contracts.append(_reference(vault.root / 'definitions/lock.json', lock_data))
    instruction_names = list(manifest['baseInstructionPaths'])
    if descriptor.skillPath:
        instruction_names.append(descriptor.skillPath)
    prompts = {p['id']: p for p in manifest['prompts']}
    instruction_names.extend(prompts[p]['path'] for p in descriptor.promptIds)
    instruction_names = list(dict.fromkeys(instruction_names))
    instruction_bytes = sum(len(files[p]) for p in instruction_names)
    if instruction_bytes > _INSTRUCTION_BUDGET:
        raise ArchiveError('CONTEXT_BUDGET_EXCEEDED', 'Base and selected instructions exceed 32 KiB; use a smaller compatible kit.')
    history = _history(vault, person)
    if not history:
        raise ArchiveError('PERSON_NOT_FOUND', 'Selected person has no accepted identity.')
    base = history[-1][0]
    patient = resolve(vault, person, ResourceRef('Patient', person), at=base)
    identity = {k: patient[k] for k in ('resourceType', 'id', 'name', 'birthDate') if k in patient}
    identity_bytes = encode_json(identity)
    if len(identity_bytes) > request.maxDataBytes:
        raise ArchiveError('CONTEXT_BUDGET_EXCEEDED', 'Person identity exceeds data budget; explicitly increase maxDataBytes.')
    sources = tuple(_source(vault, person, d) for d in dict.fromkeys(request.sourceHashes))
    current, revisions = {}, {}
    for _, directory, change in history:
        for entry in change['resources']:
            key = (entry['type'], entry['id'])
            current[key] = (directory, entry)
            revisions[(*key, entry['versionId'])] = (directory, entry)
    if task == 'import':
        selected = []
    elif request.resourceRefs:
        selected = []
        for ref in request.resourceRefs:
            found = (revisions.get((ref.resourceType, ref.id, ref.versionId)) if ref.versionId else
                     current.get((ref.resourceType, ref.id)))
            if found is None:
                raise ArchiveError('RESOURCE_NOT_FOUND', 'Requested resource is absent from selected person and snapshot.')
            if found not in selected:
                selected.append(found)
        selected.sort(key=lambda item: (item[1]['type'], item[1]['id'], item[1]['versionId']))
    elif task == 'query':
        selected = [current[k] for k in sorted(current)]
    else:
        selected = []
    scope_digest = hash_bytes(encode_json({'personId': person, 'taskId': task,
        'kitSha256': manifest_digest, 'sourceHashes': sorted(set(request.sourceHashes)),
        'resourceRefs': [document(r) for r in request.resourceRefs]}))
    offset = 0
    if request.continuation is not None:
        token = request.continuation
        if token.personId != person or token.taskId != task or token.requestSha256 != scope_digest:
            raise ArchiveError('INVALID_CONTINUATION', 'Continuation differs from selected person, task or request.')
        if token.base != base:
            raise ArchiveError('STALE_BASE', 'Continuation base differs from current accepted head; restart selection.')
        if type(token.offset) is not int or not 0 < token.offset < len(selected):
            raise ArchiveError('INVALID_CONTINUATION', 'Continuation offset is outside selected inventory.')
        offset = token.offset
    data_bytes, records, record_bytes, evidence_paths, evidence_bytes = len(identity_bytes), [], [], [], []
    for directory, entry in selected[offset:]:
        source_path = directory / entry['path']
        data = _read(directory, entry['path'])
        relative = f"records/{entry['type']}-{entry['id']}-{entry['versionId']}.json"
        evidence, evidence_data = _selected_evidence(directory, entry, relative, registry)
        cost = len(data)+len(evidence_data)
        if cost + len(identity_bytes) > request.maxDataBytes:
            raise ArchiveError('CONTEXT_BUDGET_EXCEEDED', 'One whole record, its selected evidence and identity exceed data budget; increase maxDataBytes or select other records.')
        if len(records) >= request.maxRecords or data_bytes + cost > request.maxDataBytes:
            break
        records.append(ContextFile(relative, entry['sha256'], len(data), str(source_path)))
        record_bytes.append(data)
        data_bytes += cost
        evidence_paths.append(evidence)
        evidence_bytes.append(evidence_data)
    next_offset = offset + len(records)
    continuation = ContextContinuation(person, task, base, scope_digest, next_offset) if next_offset < len(selected) else None
    issues = (Issue('WORKFLOW_UNAVAILABLE', 'info', None, None,
        'Missing workflow capabilities: ' + ', '.join(descriptor.availability.missingCapabilities) + '.'),) if descriptor.availability.status == 'unavailable' else ()
    instructions = tuple(ContextFile('instructions/' + p, hash_bytes(files[p]), len(files[p]), str(kit / p)) for p in instruction_names)
    patient_entry = current[('Patient', person)]
    identity_file = ContextFile('identity.json', hash_bytes(identity_bytes), len(identity_bytes),
        str(patient_entry[0] / patient_entry[1]['path']))
    has_limits = 'maxRecords' in registry.resolve('urn:helseark:schema:0.1.0:agent-context')['properties']
    context = AgentContext(destination, manifest_digest, person, base, task, manifest['kitVersion'], 1,
        instructions, tuple(contracts), sources, tuple(records), len(records), continuation, issues,
        len(selected), data_bytes, instruction_bytes, identity_file, descriptor.availability, descriptor.permittedOperations,
        _reference(kit / 'manifest.json', _read(kit, 'manifest.json')), tuple(evidence_paths), descriptor.expectedChecks, descriptor.outputs, request.maxRecords if has_limits else None, request.maxDataBytes if has_limits else None)
    value = document(context)
    if not registry.validate('urn:helseark:schema:0.1.0:agent-context', value):
        raise ArchiveError('INVALID_ENVELOPE', 'Generated context violates pinned context contract.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = destination.parent / ('.helseark-context-' + str(uuid4()))
    try:
        stage.mkdir(mode=0o700)
        for file, data in [(identity_file, identity_bytes), *zip(records, record_bytes), *zip(evidence_paths, evidence_bytes),
                           *((f, files[p]) for f, p in zip(instructions, instruction_names))]:
            target = _safe(stage, file.path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (stage / 'context.json').write_bytes(encode_json(value))
        # Reject an advancing base rather than emitting a silently stale handoff.
        if head(vault, person) != base:
            raise ArchiveError('STALE_BASE', 'Selected person changed while context was being built; retry.')
        if destination.exists() or destination.is_symlink():
            raise ArchiveError('DESTINATION_EXISTS', 'Context destination appeared during preparation.')
        stage.rename(destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return context


def read_agent_context(path: Path) -> AgentContext:
    """Decode a packet; rendering independently verifies its paths and bytes."""
    from .contracts import Head
    try:
        value = decode_json(_read(Path(path), 'context.json'))
        value['path'] = Path(value['path'])
        value['base'] = Head(**value['base'])
        for name in ('instructionPaths', 'contractPaths', 'selectedSources', 'selectedRecords', 'evidencePaths'):
            value[name] = tuple(ContextFile(**f) for f in value[name])
        for name in ('identity', 'kitManifest'):
            value[name] = ContextFile(**value[name])
        value['availability'] = CapabilityAvailability(value['availability']['status'], tuple(value['availability']['missingCapabilities']))
        value['issues'] = tuple(Issue(**i) for i in value['issues'])
        if value['continuation']:
            token = value['continuation']
            value['continuation'] = ContextContinuation(token['personId'], token['taskId'], Head(**token['base']), token['requestSha256'], token['offset'])
        for name in ('permittedOperations', 'expectedChecks', 'outputPaths'):
            value[name] = tuple(value[name])
        context = AgentContext(**value)
        if context.path != Path(path).absolute():
            raise ValueError
        return context
    except (KeyError, TypeError, ValueError):
        raise ArchiveError('CONTEXT_MISMATCH', 'Malformed or relocated context packet.') from None


def _verified_context(context):
    """Verify against retained authorities, never paths asserted by source data."""
    from .archive import _open_vault_metadata
    if not isinstance(context, AgentContext):
        raise ArchiveError('CONTEXT_MISMATCH', 'Expected a context packet.')
    if decode_json(_read(context.path, 'context.json')) != document(context):
        raise ArchiveError('CONTEXT_MISMATCH', 'Context metadata differs from supplied packet.')
    # This structural root is checked again against the vault-pinned manifest.
    root = Path(context.kitManifest.path).parent.parent.parent
    vault = _open_vault_metadata(root)
    registry = load_definition_registry(vault)
    kit, manifest, files, digest = _vault_kit(vault, registry)
    if (context.kitManifest != _reference(kit/'manifest.json', _read(kit, 'manifest.json')) or
            context.manifestSha256 != digest or context.kitVersion != manifest['kitVersion'] or
            not registry.validate('urn:helseark:schema:0.1.0:agent-context', document(context))):
        raise ArchiveError('CONTEXT_MISMATCH', 'Context differs from retained kit or contract.')
    if head(vault, context.personId) != context.base:
        raise ArchiveError('STALE_BASE', 'Context base differs from selected person head; rebuild.')
    descriptor = _descriptor(next(t for t in manifest['tasks'] if t['id'] == context.taskId), manifest)
    if (context.availability != descriptor.availability or context.permittedOperations != descriptor.permittedOperations or
            context.expectedChecks != descriptor.expectedChecks or context.outputPaths != descriptor.outputs):
        raise ArchiveError('CONTEXT_MISMATCH', 'Context authority differs from runtime descriptor.')
    expected_names = list(dict.fromkeys([*manifest['baseInstructionPaths'], descriptor.skillPath,
        *(p['path'] for p in manifest['prompts'] if p['id'] in descriptor.promptIds)]))
    expected_names = [p for p in expected_names if p]
    expected = tuple(ContextFile('instructions/'+p, hash_bytes(files[p]),len(files[p]),str(kit/p)) for p in expected_names)
    if context.instructionPaths != expected:
        raise ArchiveError('CONTEXT_MISMATCH', 'Instruction selection differs from task.')
    for f in context.instructionPaths:
        data = _read(context.path, f.path)
        if hash_bytes(data) != f.sha256 or len(data) != f.size:
            raise ArchiveError('CONTEXT_MISMATCH', 'Packet instruction bytes differ.')
    contracts = tuple(_reference(_safe(root/'definitions', p),registry.files[p]) for p in
        dict.fromkeys((*descriptor.schemaPaths, *descriptor.referencePaths))) + (
            _reference(root/'definitions/lock.json', _read(root,'definitions/lock.json')),)
    if context.contractPaths != contracts:
        raise ArchiveError('CONTEXT_MISMATCH', 'Contract selection differs from pinned registry.')
    history = _history(vault, context.personId)
    allowed, evidences = {}, {}
    current = {}
    for _, directory, change in history:
        for entry in change['resources']:
            current[entry['type'],entry['id']] = (directory,entry)
            name = f"records/{entry['type']}-{entry['id']}-{entry['versionId']}.json"
            allowed[name] = ContextFile(name,entry['sha256'],len(_read(directory,entry['path'])),str(directory/entry['path']))
    patient = resolve(vault, context.personId, ResourceRef('Patient',context.personId),at=context.base)
    identity = encode_json({k:patient[k] for k in ('resourceType','id','name','birthDate') if k in patient})
    directory, entry = current['Patient',context.personId]
    if context.identity != ContextFile('identity.json',hash_bytes(identity),len(identity),str(directory/entry['path'])) or _read(context.path,'identity.json') != identity:
        raise ArchiveError('CONTEXT_MISMATCH', 'Selected person identity differs.')
    for f in context.selectedRecords:
        if allowed.get(f.path) != f or hash_bytes(_read(context.path,f.path)) != f.sha256:
            raise ArchiveError('CONTEXT_MISMATCH', 'Record is outside selected person or differs from accepted bytes.')
        directory = Path(f.sourcePath).parent.parent
        resource = decode_canonical_json(_read(context.path,f.path))
        entry = {'type':resource['resourceType'],'id':resource['id'],'versionId':resource['meta']['versionId']}
        evidence, data = _selected_evidence(directory,entry,f.path,registry)
        if _read(context.path,evidence.path) != data:
            raise ArchiveError('CONTEXT_MISMATCH','Selected evidence bytes differ from accepted original.')
        evidences[evidence.path] = evidence
    if tuple(evidences.values()) != context.evidencePaths:
        raise ArchiveError('CONTEXT_MISMATCH', 'Evidence differs from selected accepted revisions.')
    for source in context.selectedSources:
        if _source(vault,context.personId,source.sha256) != source:
            raise ArchiveError('CONTEXT_MISMATCH', 'Source differs from selected person retained asset.')
    if (context.returnedCount != len(context.selectedRecords) or
            context.dataBytes != len(identity)+sum(f.size for f in (*context.selectedRecords,*context.evidencePaths)) or
            context.instructionBytes != sum(f.size for f in expected) or
            (context.maxDataBytes is not None and context.dataBytes > context.maxDataBytes) or
            (context.maxRecords is not None and context.returnedCount > context.maxRecords) or
            context.instructionBytes > _INSTRUCTION_BUDGET):
        raise ArchiveError('CONTEXT_MISMATCH', 'Packet counts or budgets differ.')
    return vault, manifest, files, descriptor


def _output_directory(value, context, vault):
    if not isinstance(value,str) or any(ord(c)<32 for c in value) or not Path(value).is_absolute() or '..' in Path(value).parts:
        raise ArchiveError('UNSAFE_PATH', 'Output directory must be an explicit absolute fresh path.')
    path = Path(value)
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise ArchiveError('UNSAFE_PATH', 'Output directory cannot traverse symlinks.')
    if path.exists():
        raise ArchiveError('DESTINATION_EXISTS', 'Output directory must be absent.')
    packet = context.path.resolve()
    work = vault.root/'people'/context.personId/'work'
    if (path == packet or packet in path.parents or path in packet.parents or
            ((path == vault.root or vault.root in path.parents) and work not in path.parents)):
        raise ArchiveError('UNSAFE_PATH', 'Output must be separate from packet and canonical vault paths.')
    return value


def render_task_prompt(context: AgentContext, promptId: str, variables: Mapping[str, JsonValue]) -> RenderedPrompt:
    """Render one declared template as data, after verifying a fresh snapshot.

    The caller is the authority for explicit human decisions and the fresh output
    directory. Neither a context nor this text grants filesystem/tool permission.
    Unavailable workflows render a blocked assessment, never executable commands.
    """
    vault, manifest, files, task = _verified_context(context)
    prompt = next((p for p in manifest['prompts'] if p['id'] == promptId),None)
    if prompt is None or promptId not in task.promptIds or context.taskId not in prompt['taskIds']:
        raise ArchiveError('INCOMPATIBLE_PROMPT', 'Prompt is not declared for selected task.')
    if context.maxRecords is None or context.maxDataBytes is None:
        raise ArchiveError('UNSUPPORTED_VERSION','Retained context contract predates typed rendering limits.')
    if not isinstance(variables,Mapping) or set(variables)-set(prompt['variables']):
        raise ArchiveError('INVALID_VARIABLE', 'Unknown prompt variable.')
    # These values come exclusively from verified context. Optional repeats must
    # agree, so caller data cannot impersonate a toolkit selection.
    refs = []
    for f in context.selectedRecords:
        r = decode_canonical_json(_read(context.path,f.path))
        refs.append(f"{r['resourceType']}/{r['id']}/_history/{r['meta']['versionId']}")
    capabilities = sorted(_CAPABILITIES | {'task-instructions'})
    trusted = {'person_id':context.personId,'base_change_sha256':context.base.changeSha256,
        'capabilities':capabilities,'scope':{'resourceRefs':refs,
            'sourceSha256':[f.sha256 for f in context.selectedSources],
            'maxRecords':context.maxRecords,'maxDataBytes':context.maxDataBytes}}
    if 'source_hashes' in prompt['variables']:
        trusted['source_hashes'] = trusted['scope']['sourceSha256']
    values = dict(variables)
    for name,value in trusted.items():
        if name in values and values[name] != value:
            raise ArchiveError('INVALID_VARIABLE', 'Selector differs from verified context.')
        values[name] = value
    serialized = {}
    for name,spec in prompt['variables'].items():
        if name not in values:
            if 'default' in spec:
                values[name] = spec['default']
            elif spec['required']:
                raise ArchiveError('INVALID_VARIABLE', 'Required prompt variable is missing.')
            elif spec.get('nullable'):
                values[name] = None
            else:
                raise ArchiveError('INVALID_VARIABLE', 'Optional variable needs an explicit default or nullability.')
        value = values[name]
        types = {'string':str,'object':dict,'array':list,'integer':int,'boolean':bool}
        valid = value is None and spec.get('nullable',False)
        if value is not None:
            valid = spec['type']=='json' or type(value) is types.get(spec['type'])
        if not valid:
            raise ArchiveError('INVALID_VARIABLE', 'Prompt variable has the wrong type or nullability.')
        try:
            encoded = encode_json(value)
        except ArchiveError:
            raise ArchiveError('INVALID_VARIABLE','Prompt value is not bounded exact JSON.') from None
        if (len(value.encode()) if isinstance(value,str) else len(encoded)) > spec.get('maxBytes',262144):
            raise ArchiveError('INVALID_VARIABLE', 'Prompt variable exceeds its byte budget.')
        if value is not None and spec.get('pattern') and not re.fullmatch(spec['pattern'],value):
            raise ArchiveError('INVALID_VARIABLE','Prompt variable violates its declared identity constraint.')
        if isinstance(value,list) and (len(value)<spec.get('minItems',0) or
                (spec.get('uniqueItems') and len({encode_json(v) for v in value})!=len(value))):
            raise ArchiveError('INVALID_VARIABLE','Prompt array violates declared bounds.')
        serialized[name] = encoded.decode().rstrip('\n').replace('&',r'\u0026').replace('<',r'\u003c').replace('>',r'\u003e')
    host_metadata = {'output_directory','candidate_id','identity_confirmed','correspondence_confirmed','source_scope_confirmed'}
    inline_data_bytes = sum(len(serialized[name].encode('utf-8')) for name in set(values)-set(trusted)-host_metadata)
    if context.dataBytes + inline_data_bytes > context.maxDataBytes:
        raise ArchiveError('CONTEXT_BUDGET_EXCEEDED',
            'Escaped inline data plus context exceed selected data budget; reduce inline data or rebuild with a larger maxDataBytes.')
    _output_directory(values['output_directory'],context,vault)
    template = files[prompt['path']].decode('utf-8')
    marker = re.compile(r'{{\s*([a-z][a-z0-9_]*)\s*}}')
    if set(marker.findall(template)) != set(prompt['variables']) or '{{' in marker.sub('',template) or '}}' in marker.sub('',template):
        raise ArchiveError('INVALID_KIT','Template has undeclared or unresolved placeholders.')
    def substitution(match):
        return serialized[match[1]]
    text = marker.sub(substitution,template)
    provenance = {'provenanceVersion':1,'status':'known','promptId':promptId,'promptVersion':prompt['version'],
        'promptSha256':prompt['sha256'],'skillSha256':hash_bytes(files[task.skillPath]),'skillId':prompt['skillId'],'skillVersion':prompt['skillVersion'],
        'kitVersion':context.kitVersion,'kitSha256':context.manifestSha256}
    blocked = list(context.availability.missingCapabilities)
    for name in ('identity_confirmed','correspondence_confirmed','source_scope_confirmed'):
        if name in values and values[name] is not True:
            blocked.append('SOURCE_SCOPE_REVIEW_REQUIRED' if name=='source_scope_confirmed' else name.upper()+'_REQUIRED')
    text = ('Verified runtime handoff (host restrictions remain required; blocked means report only and stop):\n'+
        encode_json({'personId':context.personId,'base':document(context.base),'returnedCount':context.returnedCount,
            'totalCount':context.totalCount,'continuation':document(context.continuation),
            'contextDataBytes':context.dataBytes,'inlineDataBytes':inline_data_bytes,
            'handoffDataBytes':context.dataBytes+inline_data_bytes,
            'disposition':'blocked' if blocked else 'draft','stopReasons':blocked,
            'permittedWrites':['output/report.md'] if blocked else prompt['outputArtifacts'],
            'producerProvenance':provenance}).decode()+'\n'+text)
    # Recheck immediately before handing off text. No writes or model invocation.
    if head(vault,context.personId) != context.base:
        raise ArchiveError('STALE_BASE','Accepted head advanced during rendering; rebuild.')
    return RenderedPrompt(text,promptId,prompt['version'],prompt['sha256'],provenance['skillSha256'],
        context.manifestSha256,tuple(prompt['inputContractIds']),tuple(prompt['outputContractIds']))


def _verify_producer(vault, provenance, registry):
    """Validate genuine candidate-producing instruction pins, retaining legacy absence."""
    if provenance is None or provenance.get('status') == 'external-unknown':
        return
    version = provenance.get('kitVersion')
    if not isinstance(version,str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',version):
        raise ArchiveError('PRODUCER_MISMATCH','Invalid producer kit version.')
    _, manifest, files, _ = _load_kit(_safe(vault.root,'agent-kit/'+version),provenance.get('kitSha256'),registry)
    prompt = next((p for p in manifest['prompts'] if p['id']==provenance.get('promptId')),None)
    task = next((t for t in manifest['tasks'] if t['id'] in ('import','correct') and prompt and prompt['id'] in t['promptIds']),None)
    if (manifest['kitVersion'] != version or prompt is None or task is None or
            prompt['skillId'] != provenance.get('skillId') or prompt['skillVersion'] != provenance.get('skillVersion') or
            prompt['version'] != provenance.get('promptVersion') or prompt['sha256'] != provenance.get('promptSha256') or
            hash_bytes(files[task['skillPath']]) != provenance.get('skillSha256') or
            any(getattr(vault.config,k)!=v for k,v in manifest['compatibility'].items())):
        raise ArchiveError('PRODUCER_MISMATCH','Producer instruction pins differ from a compatible retained candidate route.')
