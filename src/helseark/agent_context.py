"""Offline kit closure and bounded, explicit-person context packets.

Only manifest-listed instructions are loadable. Clinical/source content never
participates in routing. Packets are disposable read snapshots, not authority,
permission grants or agent execution. Task4 owns prompt rendering.
"""
from dataclasses import asdict, is_dataclass
import hashlib
from pathlib import Path
import re
import shutil
from uuid import uuid4

from jsonschema import Draft202012Validator

from .archive import _bundled_root, _safe, _read, _history, head, resolve
from .contracts import (ArchiveError, Vault, ResourceRef, AgentTask, ContextRequest,
    AgentTaskDescriptor, CapabilityAvailability, ContextFile, ContextContinuation,
    AgentContext, Issue, uuid_string, sha256_string)
from .serialization import decode_json, decode_canonical_json, encode_json, hash_bytes
from .validation import load_definition_registry, _pointer

_TASKS = frozenset(('inspect', 'import', 'query', 'correct', 'export', 'verify', 'migrate'))
_CAPABILITIES = frozenset(('agent-discovery', 'agent-context', 'schema-export',
    'baseline-validation', 'person-identity', 'raw-record-selection'))
_INSTRUCTION_BUDGET = 32768


def document(value):
    """JSON representation shared by disk packets and CLI (no float coercion)."""
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


def _evidence_selection(person, entry, data, original, change, resource, registry):
    """Project exact entries, retaining original indexes without a readable route.

    Whole revisions are the selection unit. Never follow sourceDocument/locator
    links: quotes are retained evidence, broader source/page reads require an
    explicit sourceHashes request. Accepted entries are copied unchanged.
    """
    if hash_bytes(data) != change['payload']['evidence.json']:
        raise ArchiveError('INTEGRITY', 'Selected evidence differs from accepted inventory.')
    evidence = decode_canonical_json(data)
    revision = f"{entry['type']}/{entry['id']}/_history/{entry['versionId']}"
    entries, pointers = [], []
    for index, item in enumerate(evidence['entries']):
        target = item.get('target', {})
        if target.get('reference', item.get('resourceRef')) != revision:
            continue
        try:
            for pointer in target.get('pointers', [item.get('pointer')]):
                _pointer(resource, pointer)
        except (ValueError, TypeError, KeyError, IndexError):
            raise ArchiveError('INTEGRITY', 'Selected evidence pointer does not resolve in its revision.') from None
        entries.append(item)
        pointers.append(f'/entries/{index}')
    if not entries:
        raise ArchiveError('INTEGRITY', 'Selected revision has no retained evidence.')
    selection = {'selectionVersion': '1', 'personId': person, 'revision': revision,
        'original': {'changeSha256': original.changeSha256,
                     'sha256': hash_bytes(data), 'entryPointers': pointers},
        'entries': entries}
    if not registry.validate('urn:helseark:schema:0.1.0:agent-context#/$defs/evidenceSelection', selection):
        raise ArchiveError('INVALID_ENVELOPE', 'Generated evidence selection violates pinned context contract.')
    return encode_json(selection)


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
    evidence_origins = {directory: (original, change) for original, directory, change in history}
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
    data_bytes, records, record_bytes = len(identity_bytes), [], []
    evidence_paths, evidence_bytes = [], []
    for directory, entry in selected[offset:]:
        if len(records) >= request.maxRecords:
            break
        source_path = directory / entry['path']
        data = _read(directory, entry['path'])
        if hash_bytes(data) != entry['sha256']:
            raise ArchiveError('INTEGRITY', 'Selected record differs from accepted inventory.')
        original, change = evidence_origins[directory]
        evidence = _evidence_selection(person, entry, _read(directory, 'evidence.json'),
            original, change, decode_canonical_json(data), registry)
        size = len(data) + len(evidence)
        if size + len(identity_bytes) > request.maxDataBytes:
            raise ArchiveError('CONTEXT_BUDGET_EXCEEDED', 'One whole record with scoped evidence plus identity exceeds data budget; increase maxDataBytes or select other records.')
        if data_bytes + size > request.maxDataBytes:
            break
        relative = f"records/{entry['type']}-{entry['id']}-{entry['versionId']}.json"
        records.append(ContextFile(relative, entry['sha256'], len(data), str(source_path)))
        record_bytes.append(data)
        evidence_relative = relative.replace('records/', 'evidence/', 1)
        evidence_paths.append(ContextFile(evidence_relative, hash_bytes(evidence), len(evidence), str(destination / evidence_relative)))
        evidence_bytes.append(evidence)
        data_bytes += size
    next_offset = offset + len(records)
    continuation = ContextContinuation(person, task, base, scope_digest, next_offset) if next_offset < len(selected) else None
    issues = (Issue('WORKFLOW_UNAVAILABLE', 'info', None, None,
        'Missing workflow capabilities: ' + ', '.join(descriptor.availability.missingCapabilities) + '.'),) if descriptor.availability.status == 'unavailable' else ()
    instructions = tuple(ContextFile('instructions/' + p, hash_bytes(files[p]), len(files[p]), str(kit / p)) for p in instruction_names)
    identity_file = ContextFile('identity.json', hash_bytes(identity_bytes), len(identity_bytes),
        str(destination / 'identity.json'))
    context = AgentContext(destination, manifest_digest, person, base, task, manifest['kitVersion'], 1,
        instructions, tuple(contracts), sources, tuple(records), len(records), continuation, issues,
        len(selected), data_bytes, instruction_bytes, identity_file, descriptor.availability, descriptor.permittedOperations,
        _reference(kit / 'manifest.json', _read(kit, 'manifest.json')), tuple(evidence_paths), descriptor.expectedChecks, descriptor.outputs)
    value = document(context)
    if not registry.validate('urn:helseark:schema:0.1.0:agent-context', value):
        raise ArchiveError('INVALID_ENVELOPE', 'Generated context violates pinned context contract.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = destination.parent / ('.helseark-context-' + str(uuid4()))
    try:
        stage.mkdir(mode=0o700)
        for file, data in [(identity_file, identity_bytes), *zip(records, record_bytes),
                           *zip(evidence_paths, evidence_bytes),
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
