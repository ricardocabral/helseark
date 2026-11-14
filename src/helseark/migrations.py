"""Closed offline layout dispatch; accepted clinical/history bytes never rewritten.

The explicitly opted-in test-only layout wraps a Task8 snapshot. It exercises a
real path transformation without inventing an old public clinical format. All
production v1 moves are identity copies under the exact retained definitions.
"""
from dataclasses import asdict, replace
from pathlib import Path

from jsonschema import Draft202012Validator

from .contracts import (ArchiveError, Vault, VersionSet, MigrationPlan, MigrationReceipt,
                        FHIRMigrationPlan, CheckCoverage)
from .serialization import encode_json, decode_json, hash_bytes
from .agent_context import document
from .archive import (_files, _read, _json, _write, _safe, _sync_tree,
                      _sync_directory, _writer_lock, _bundled_root, open_vault, doctor, head)
from .portability import backup, restore, verify_export, _blocked, _publish, _destination

CURRENT = VersionSet(1, '0.1.0', '0.1.0', '4.0.1', 'helseark-json-1')
TEST_ONLY = replace(CURRENT, archiveFormatVersion=0, serializationVersion='test-only-layout-0')
_MARKER = {'format':'helseark-test-only-layout-0',
           'notice':'TEST ONLY: not a supported public release; synthetic fixtures only',
           'snapshotPath':'snapshot'}
# Data never selects executable code, plugins, converters or import paths.
_DISPATCH = {(CURRENT, CURRENT):'v1-identity-copy',
             (TEST_ONLY, CURRENT):'test-only-layout-0-to-v1'}


def _versions(vault):
    return VersionSet(**{key:getattr(vault.config,key) for key in asdict(CURRENT)})


def open_migration_source(root: Path, *, allowTestFixture: bool = False) -> Vault:
    root = Path(root).absolute()
    if (root/'legacy-test-only.json').exists():
        if not allowTestFixture:
            raise ArchiveError('UNSUPPORTED_VERSION', 'Test-only layout requires explicit fixture opt-in.')
        if decode_json(_read(root,'legacy-test-only.json')) != _MARKER:
            raise ArchiveError('INVALID_INPUT', 'Unknown or ambiguous test-only layout.')
        _blocked(verify_export(root/'snapshot'))
        manifest = _json(root/'snapshot','export.json')
        if manifest['kind'] != 'backup':
            raise ArchiveError('INVALID_INPUT', 'Test-only layout requires a whole-vault backup.')
        expected = {'legacy-test-only.json'} | {'snapshot/'+p for p in _files(root/'snapshot')}
        if _retained_paths(root) != expected:
            raise ArchiveError('INTEGRITY', 'Test-only container has unaccounted files.')
        config = open_vault(root/'snapshot/vault').config
        return Vault(root,replace(config,archiveFormatVersion=0,serializationVersion='test-only-layout-0'))
    return open_vault(root)


def _retained_paths(root):
    # Match Task8's explicit transient omissions. Work is retained for migration.
    return {p for p in _files(root) if Path(p).parts[0] not in ('.runtime','derived')}


def _inventory(root):
    entries = []
    for path in sorted(_retained_paths(root)):
        data = _read(root,path)
        entries.append({'path':path,'sha256':hash_bytes(data),'size':len(data)})
    return tuple(entries)


def _source(vault):
    fixture = _versions(vault) == TEST_ONLY
    reopened = open_migration_source(vault.root,allowTestFixture=fixture)
    if reopened.config != vault.config:
        raise ArchiveError('STALE_BASE', 'Migration source configuration changed.')
    return open_vault(vault.root/'snapshot/vault') if fixture else reopened


def _digest(value):
    return hash_bytes(encode_json(document({key:item for key,item in value.items() if key!='planSha256'})))


def _seal(plan):
    return replace(plan,planSha256=_digest(asdict(plan)))


def plan_migration(vault: Vault, target: VersionSet) -> MigrationPlan:
    """Read every retained revision and definition; no source writes or downloads."""
    before = _inventory(vault.root)
    source = _source(vault)
    report = doctor(source)
    _blocked(report)
    people = sorted(path.name for path in (source.root/'people').iterdir())
    heads = {p:asdict(head(source,p)) if head(source,p) else None for p in people}
    versions = _versions(vault)
    operation = _DISPATCH.get((versions,target))
    blocked = () if operation else ({'code':'UNSUPPORTED_VERSION',
        'reason':'No evaluated closed-dispatch archive transformation for these exact versions.'},)
    if target.fhirVersion != versions.fhirVersion:
        blocked = ({'code':'FHIR_RELEASE_PLAN_REQUIRED',
                    'reason':'Use the separate unsupported FHIR release plan class.'},)
    prefix = 'snapshot/vault/' if versions==TEST_ONLY else ''
    mappings = tuple({'sourcePath':entry['path'], 'destinationPath':entry['path'][len(prefix):],
                      'oldSha256':entry['sha256'], 'newSha256':entry['sha256'], 'size':entry['size']}
                     for entry in before if not prefix or entry['path'].startswith(prefix)) if operation else ()
    definitions = tuple(entry for entry in before if entry['path'].startswith(
        (prefix+'definitions/',prefix+'agent-kit/')))
    if _inventory(vault.root) != before:
        raise ArchiveError('STALE_BASE','Migration source changed during planning.')
    return _seal(MigrationPlan('',heads,versions,target,(operation,) if operation else (),
        {'changes':report.checkedChanges,'resources':report.checkedResources,'assets':report.checkedAssets},
        (),blocked,definitions,before,mappings))


def plan_fhir_migration(vault: Vault, target: str) -> FHIRMigrationPlan:
    # Verify source even for a blocked conversion report; never infer coverage.
    _blocked(doctor(_source(vault)))
    return _seal(FHIRMigrationPlan('',_versions(vault),target,
        ({'reason':'Semantic losses are unevaluated; no converter is installed or supported.'},),
        ({'code':'UNSUPPORTED_FHIR_CONVERSION','reason':'All FHIR release conversions are unsupported.'},)))


def read_migration_plan(path: Path) -> MigrationPlan:
    raw = decode_json(Path(path).read_bytes())
    schema = _json(_bundled_root(),'schemas/0.1.0/migration.schema.json')
    if not Draft202012Validator(schema).is_valid(raw) or raw['planSha256'] != _digest(raw):
        raise ArchiveError('INVALID_MIGRATION_PLAN','Migration plan contract or digest mismatch.')
    raw = dict(raw)
    raw['sourceVersionSet'] = VersionSet(**raw['sourceVersionSet'])
    raw['targetVersionSet'] = VersionSet(**raw['targetVersionSet'])
    for key in ('transformations','semanticLosses','blockedRecords','requiredDefinitions','sourceInventory','byteMappings'):
        raw[key] = tuple(raw[key])
    return MigrationPlan(**raw)


def _checkpoint(point):
    """Internal subprocess-test seam. No environment-controlled runtime fault hook."""


def _matches(vault, plan):
    # Recompute the complete plan, never execute a caller-supplied transformation.
    current = plan_migration(vault,plan.targetVersionSet)
    if asdict(current) != asdict(plan):
        raise ArchiveError('STALE_BASE', 'Source bytes, heads or migration plan changed; make and review a new plan.')


def _validate_destination(root, plan):
    expected = {item['destinationPath']:item for item in plan.byteMappings}
    provenance = 'migrations/'+plan.planSha256+'.json'
    paths = _retained_paths(root)
    if paths - {provenance} != set(expected):
        raise ArchiveError('INTEGRITY','Migrated inventory has missing or extra retained bytes.')
    for path,item in expected.items():
        data = _read(root,path)
        if hash_bytes(data)!=item['newSha256'] or len(data)!=item['size']:
            raise ArchiveError('INTEGRITY','Migrated byte mapping mismatch.')
    report = doctor(open_vault(root)); _blocked(report)
    counts = {'changes':report.checkedChanges,'resources':report.checkedResources,'assets':report.checkedAssets}
    if counts != plan.expectedCounts:
        raise ArchiveError('INTEGRITY','Migrated graph counts differ from the plan.')
    return counts


def apply_migration(vault: Vault, plan: MigrationPlan, destination: Path, *,
                    reviewedPlanSha256: str | None = None, resume: bool = False) -> MigrationReceipt:
    """Stage via Task8, verify original hashes again, then publish without replacement.

    Explicit human review binds the exact host-generated plan digest. This is not
    identity authentication and does not approve a new clinical import.
    On interruption nothing is deleted; --resume revalidates retained staging.
    """
    if not isinstance(plan,MigrationPlan) or plan.planClass!='archive-contract':
        raise ArchiveError('UNSUPPORTED_VERSION','FHIR conversion plans cannot use archive apply.')
    if _digest(asdict(plan)) != plan.planSha256:
        raise ArchiveError('INVALID_MIGRATION_PLAN','Migration plan digest mismatch.')
    if plan.semanticLosses or plan.blockedRecords or not _DISPATCH.get((plan.sourceVersionSet,plan.targetVersionSet)):
        raise ArchiveError('MIGRATION_BLOCKED','Lossy, ambiguous or unsupported migration cannot apply.')
    if reviewedPlanSha256 is None:
        raise ArchiveError('REVIEW_REQUIRED','Explicit human review of this plan digest is required.')
    if reviewedPlanSha256 != plan.planSha256:
        raise ArchiveError('REVIEW_MISMATCH','Human review must bind this exact plan digest.')
    _matches(vault,plan)
    destination = Path(destination).absolute()
    # Do not permit a destination enclosing the source, including through aliases.
    if vault.root.resolve().is_relative_to(destination.resolve()):
        raise ArchiveError('INVALID_INPUT','Destination cannot enclose the source.')
    destination = _destination(destination,vault.root)
    token = hash_bytes(encode_json({'plan':plan.planSha256,'destination':str(destination.resolve())}))
    stage = destination.parent/('.helseark-migrate-'+token)
    owner = {'format':'helseark-migration-staging-1','planSha256':plan.planSha256,
             'source':str(vault.root.resolve()),'destination':str(destination.resolve())}
    if stage.exists() or stage.is_symlink():
        if not resume:
            raise ArchiveError('MIGRATION_STAGING_EXISTS','Preserve incomplete migration staging; explicitly resume the reviewed plan.',{'staging':str(stage)})
        if stage.is_symlink() or _json(stage,'owner.json')!=owner:
            raise ArchiveError('INTEGRITY','Staging ownership differs from this migration.')
        _files(stage)  # reject unsafe debris too; never follow it or delete it
    else:
        stage.mkdir(mode=0o700)
        _write(stage/'owner.json',encode_json(owner)); _sync_directory(stage)
    # Separate migration lock permits deterministic resume without sharing a
    # writer with another attempt. The source writer lock remains Task8-owned.
    stage_vault = Vault(stage,vault.config)
    with _writer_lock(stage_vault):
        snapshot = stage/'snapshot'
        if snapshot.exists():
            _blocked(verify_export(snapshot))
        elif plan.sourceVersionSet==TEST_ONLY:
            # Restore the verified fixture through Task8, then snapshot it through
            # that same boundary; no second copy/restore implementation.
            recovered = stage/'legacy-recovered'
            if not recovered.exists():
                restore(vault.root/'snapshot',recovered)
            _validate_destination(recovered,plan)
            backup(open_vault(recovered),snapshot,includeWork=True)
        else:
            backup(vault,snapshot,includeWork=True)
        _checkpoint('snapshot-ready')
        result = stage/'vault'
        if not result.exists():
            restore(snapshot,result)
        _checkpoint('restored')
        counts = _validate_destination(result,plan)
        # Lock the actual retained source (fixture wrapper or ordinary vault) for
        # the final comparison, provenance and publication. No staged success
        # assertion exists until both original bytes and heads have been checked.
        with _writer_lock(vault):
            _matches(vault,plan)
            original_unchanged = _inventory(vault.root)==plan.sourceInventory
            if not original_unchanged:
                raise ArchiveError('STALE_BASE','Source changed before destination publication.')
            provenance = 'migrations/'+plan.planSha256+'.json'
            mapping = {'format':'helseark-migration-receipt-1','plan':asdict(plan),
                       'reviewedPlanSha256':reviewedPlanSha256,'byteMappings':list(plan.byteMappings),
                       'validatedCounts':counts,'originalUnchanged':original_unchanged,
                       'meaning':'Layout migration only; accepted review and correction history is unchanged.'}
            path = _safe(result,provenance)
            if path.exists():
                if _read(result,provenance)!=encode_json(document(mapping)):
                    raise ArchiveError('INTEGRITY','Staged provenance differs from reviewed migration.')
            else:
                path.parent.mkdir(exist_ok=True); _write(path,encode_json(document(mapping)))
            _validate_destination(result,plan)
            _sync_tree(result)
            _publish(result,destination)
        coverage = (CheckCoverage('retained-byte-mappings','passed'),
                    CheckCoverage('accepted-history-reference-evidence-review-closure','passed'),
                    CheckCoverage('source-unchanged','passed'),
                    CheckCoverage('terminology','not-checked','No terminology service is invoked.'),
                    CheckCoverage('extraction-accuracy','not-checked','Preservation is not extraction accuracy.'))
        return MigrationReceipt(destination,destination/provenance,counts,coverage,original_unchanged)
