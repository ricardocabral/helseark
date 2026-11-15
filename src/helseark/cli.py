"""Small CLI; all archive behavior is shared with the library."""
import argparse
from dataclasses import asdict, replace
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from .archive import init_vault, open_vault, open_definitions, add_person, head, _read, _json, _open_vault_metadata, _bundled_root
from .contracts import ArchiveError, PersonDraft, uuid_string, ResourceRef, ContextRequest, ContextContinuation, Head
from .query import observations, timeline, history, parse_reference
from .presentation import render_static_report
from .archive import resolve
from .contracts import ObservationFilter
from .intake import add_source, build_packet, read_candidate, prepare_candidate, start_correction, _regular
from .review import read_prepared, render_review, record_review, read_receipt
from .contracts import ReviewDecision
from .archive import commit_candidate, doctor
from .portability import (backup, verify_export, restore, export_person, plan_person_erasure,
                          apply_person_erasure, restore_person_erasure, read_erasure_plan)
from .migrations import (CURRENT, open_migration_source, plan_migration, plan_fhir_migration,
                         apply_migration, read_migration_plan)
from dataclasses import replace
from .source_disclosure import prepare_disclosure, record_disclosure, DISCLOSURE_BYTES
from .contracts import ExportSelection
from .serialization import encode_json, decode_json
from .agent_context import list_agent_tasks, build_agent_context, _vault_kit, document, read_agent_context, render_task_prompt
from .validation import schema_packet, validate_candidate, validate_proposal

_EXIT = {
    "CORRECTION_STATUS": 2, "APPROVAL_REQUIRED": 3, "ERASURE_SCOPE_UNKNOWN": 3,
    "INVALID_MIGRATION_PLAN": 2, "MIGRATION_BLOCKED": 6, "MIGRATION_STAGING_EXISTS": 4,
    "VALIDATOR_AUTHORITY_REQUIRED": 3, "VALIDATOR_AUTHORITY_MISMATCH": 3, "VALIDATOR_RUNTIME_CHANGED": 5,
    "VALIDATOR_UNAVAILABLE": 6, "VALIDATOR_MISSING_ARTIFACT": 6,
    "VALIDATOR_NETWORK_POLICY": 6, "VALIDATOR_DIGEST_MISMATCH": 5,
    "VALIDATOR_PACKAGE_MISMATCH": 5, "VALIDATOR_PROFILE_MISMATCH": 5,
    "VALIDATOR_TIMEOUT": 2, "VALIDATOR_PROCESS_FAILED": 2, "VALIDATOR_MALFORMED_OUTPUT": 2,
    "SOURCE_SCOPE_REVIEW_REQUIRED": 3, "INVALID_FILTER": 2, "UNKNOWN_HEAD": 2, "CONTEXT_AUTHORITY_REQUIRED": 2,
    "INVALID_VARIABLE": 2, "INCOMPATIBLE_PROMPT": 2, "CONTEXT_MISMATCH": 5,
    "CONTEXT_BUDGET_EXCEEDED": 2, "UNKNOWN_TASK": 2, "INVALID_CONTINUATION": 2,
    "CAPABILITY_UNAVAILABLE": 6, "MISSING_KIT": 6, "INVALID_KIT": 6, "KIT_MISMATCH": 5,
    "PERSON_NOT_FOUND": 2, "RESOURCE_NOT_FOUND": 2, "SOURCE_MISSING": 2,
    "ARCHIVE_BUSY": 4, "STALE_BASE": 4,
    "UNSUPPORTED_VERSION": 6, "UNSUPPORTED_PROFILE": 6, "DEFINITION_MISMATCH": 5,
    "NUMERIC_LIMIT": 2, "DUPLICATE_KEY": 2, "DEPTH_LIMIT": 2,
    "INVALID_JSON": 2, "INVALID_INPUT": 2, "INVALID_PERSON": 2,
    "DESTINATION_EXISTS": 2, "INVALID_ID": 2, "INVALID_REFERENCE": 2,
    "SOURCE_AUTHORITY_REQUIRED": 3, "SOURCE_SCOPE_MISMATCH": 2, "IDENTITY_UNCONFIRMED": 3, "REEXTRACTION_REQUIRED": 3, "RECONCILIATION_REQUIRED": 3, "CANDIDATE_MISMATCH": 5, "VALIDATION_BLOCKED": 2, "REVIEW_MISMATCH": 3,
    "UNSAFE_PATH": 2, "SOURCE_TOO_LARGE": 2, "PAGE_LIMIT": 2,
    "TEXT_FIELD_LIMIT": 2, "RESOURCE_LIMIT": 2, "INTAKE_ISSUES_MISSING": 2,
    "CSV_MAPPING_REQUIRED": 2, "CSV_INPUT_INVALID": 2,
    "INVALID_FILTER": 2, "UNKNOWN_HEAD": 2,
    "IDENTITY_MAPPING_REQUIRED": 2, "AMBIGUOUS_REFERENCE": 2,
    "INVALID_ENVELOPE": 2, "PERSON_MISMATCH": 2, "UNSUPPORTED_RESOURCE": 6,
    "MISSING_DEFINITION": 6, "UNSUPPORTED_DIALECT": 6, "REVIEW_REQUIRED": 3,
}


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ArchiveError("INVALID_INPUT", "Invalid command arguments; use --help.")


def main(argv=None):
    parser = _Parser(prog="helseark", description="Offline immutable local health archive and bounded FHIR validation.")
    parser.add_argument("--vault", type=Path, help="Explicit vault; defaults only to HELSEARK_VAULT.")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create a new vault at an absent path.")
    init.add_argument("path", type=Path)
    init.add_argument("--json", action="store_true")
    person = commands.add_parser("person")
    people = person.add_subparsers(dest="person_command", required=True)
    add = people.add_parser("add", help="Explicitly create one self-reported Patient identity.")
    add.add_argument("--name", required=True)
    add.add_argument("--birth-date")
    add.add_argument("--note", help="Self-reported identity note, retained in evidence.")
    add.add_argument("--json", action="store_true")
    intake = commands.add_parser('intake', help='Retain a source and render a local external-agent packet.')
    intakes = intake.add_subparsers(dest='intake_command', required=True)
    ingest = intakes.add_parser('add')
    ingest.add_argument('source', type=Path)
    ingest.add_argument('--person', required=True)
    ingest.add_argument('--packet', required=True, type=Path)
    ingest.add_argument('--agent-output', type=Path, help='Fresh permitted external-agent output root.')
    ingest.add_argument('--confirm-person', action='store_true', help='Explicit human assignment; source text cannot supply this.')
    ingest.add_argument('--json', action='store_true')
    ingest.add_argument('--ocr-config', type=Path, help='Explicit pinned local OCR configuration JSON; no downloads.')
    structured = intakes.add_parser('fhir-r4', help='Map a retained R4 export using explicit local Patient/provider configuration.')
    structured.add_argument('source', type=Path)
    structured.add_argument('--person', required=True)
    structured.add_argument('--mapping', type=Path, required=True, help='Trusted local IdentityMapping JSON, never export prose.')
    structured.add_argument('--json', action='store_true')
    metrics = intakes.add_parser('metrics-csv', help='Map CSV rows using explicit trusted column/date/decimal configuration.')
    metrics.add_argument('source', type=Path)
    metrics.add_argument('--person', required=True)
    metrics.add_argument('--mapping', type=Path, required=True, help='Trusted local CsvMetricMapping JSON, never source prose.')
    metrics.add_argument('--json', action='store_true')
    schema = commands.add_parser("schema", help="Export pinned offline contracts and definitions.")
    schemas = schema.add_subparsers(dest="schema_command", required=True)
    export = schemas.add_parser("export")
    export.add_argument("--resource", action="append", required=True)
    export.add_argument("--out", type=Path, required=True)
    export.add_argument("--json", action="store_true")
    validate = commands.add_parser("validate", help="Check untrusted candidates or final proposals without publishing.")
    validations = validate.add_subparsers(dest="validation_command", required=True)
    for kind in ("candidate", "proposal"):
        command = validations.add_parser(kind)
        command.add_argument("path", type=Path)
        command.add_argument("--person", required=True)
        command.add_argument("--json", action="store_true")
        if kind == 'proposal':
            command.add_argument('--official-config',type=Path,help='Host-controlled optional offline validator configuration; writes a new pre-review report.')
            command.add_argument('--require-official',action='store_true',help='Block if explicit official validator configuration is absent.')

    report = commands.add_parser('report', help='Render an offline derived HTML/CSV snapshot; no accepted writes.')
    report.add_argument('--person', required=True)
    report.add_argument('--out', type=Path, help='Fresh directory; default vault/derived/reports/PERSON.')
    report.add_argument('--json', action='store_true')
    candidate = commands.add_parser('candidate', help='Prepare, inspect, review and publish exact bytes; human control only.')
    candidates = candidate.add_subparsers(dest='candidate_command', required=True)
    for verb in ('prepare','review','commit'):
        action=candidates.add_parser(verb)
        action.add_argument('path',type=Path)
        action.add_argument('--person',required=True)
        action.add_argument('--json',action='store_true')
        if verb=='prepare':
            action.add_argument('--amendment-target',help='Explicit Type/UUID matched to a laboratory-issued amendment from a new source.')
            action.add_argument('--amendment-reason')
            action.add_argument('--source',action='append',help='Explicit user-authorized source hash for legacy/unbound candidates; repeat for each source.')
            action.add_argument('--reextract',action='store_true',help='Explicit user workflow intent for an existing source.')
            action.add_argument('--reconciliation',type=Path,help='User-controlled JSON map: candidate urn to Type/UUID or null (new fact).')
        if verb=='review':
            action.add_argument('--decision',type=Path,help='User-controlled ReviewDecision JSON; omit to inspect only.')
    for name in ('observations','timeline','history','record'):
        query = commands.add_parser(name, help='Read one person at a current or exact historical Head.')
        query.add_argument('--person',required=True)
        query.add_argument('--at-head',type=Path,help='Path to a JSON file containing the exact Head object.')
        query.add_argument('--json',action='store_true')
        if name == 'observations':
            query.add_argument('--label')
            query.add_argument('--code-system')
            query.add_argument('--code')
            query.add_argument('--from-date')
            query.add_argument('--to-date')
            query.add_argument('--include-invalidated',action='store_true')
        if name == 'history':
            query.add_argument('--kind', action='append', required=True)
        if name == 'record':
            query.add_argument('--resource',required=True,help='Type/UUID or Type/UUID/_history/UUID.')
    correction = commands.add_parser('correct', help='Start an editable local correction; explicit review is still required.')
    correction.add_argument('--person',required=True)
    correction.add_argument('--resource',required=True)
    correction.add_argument('--reason',required=True,help='transcription:, entered-in-error: or cancellation: and explanation.')
    correction.add_argument('--json',action='store_true')
    erasures = commands.add_parser('erase',help='Digest-approved recoverable removal; never purges.').add_subparsers(dest='erase_command',required=True)
    action = erasures.add_parser('plan')
    action.add_argument('--person',required=True)
    action.add_argument('--quarantine',type=Path,required=True)
    action.add_argument('--out',type=Path,required=True)
    action.add_argument('--json',action='store_true')
    action = erasures.add_parser('apply')
    action.add_argument('plan',type=Path)
    action.add_argument('--approve',required=True,help='Exact digest from the inspected plan.')
    action.add_argument('--json',action='store_true')
    action = erasures.add_parser('restore')
    action.add_argument('quarantine',type=Path)
    action.add_argument('--approve',required=True)
    action.add_argument('--json',action='store_true')
    migrations = commands.add_parser('migrate', help='Plan offline; explicitly review before writing a separate vault.').add_subparsers(dest='migration_command', required=True)
    for verb in ('plan','apply'):
        action = migrations.add_parser(verb)
        action.add_argument('--test-only-legacy', action='store_true', help='Allow the labeled synthetic test-only layout; never a public legacy release.')
        action.add_argument('--json', action='store_true')
        if verb == 'plan':
            targets = action.add_mutually_exclusive_group(required=True)
            targets.add_argument('--to-contract')
            targets.add_argument('--to-fhir', help='Separate unsupported FHIR conversion report.')
        else:
            action.add_argument('--plan', type=Path, required=True, help='Exact host-generated plan JSON file.')
            action.add_argument('--reviewed-plan-sha256', required=True, help='Digest explicitly approved by the human reviewer.')
            action.add_argument('--into', type=Path, required=True)
            action.add_argument('--resume', action='store_true', help='Explicitly revalidate and resume this task-owned staging.')
    diagnose = commands.add_parser('doctor', help='Audit accepted history and report recovery paths without deleting anything.')
    diagnose.add_argument('--json', action='store_true')
    backups = commands.add_parser('backup').add_subparsers(dest='backup_command', required=True)
    create = backups.add_parser('create')
    create.add_argument('--out', type=Path, required=True)
    create.add_argument('--include-work', action='store_true')
    create.add_argument('--json', action='store_true')
    for verb in ('verify','restore'):
        action = backups.add_parser(verb)
        action.add_argument('bundle', type=Path)
        action.add_argument('--json', action='store_true')
        if verb == 'restore':
            action.add_argument('--into', type=Path, required=True)
    exchange = commands.add_parser('export')
    exchange.add_argument('--person', required=True)
    exchange.add_argument('--out', type=Path, required=True)
    exchange.add_argument('--mode', choices=('full-person','selected-current'), default='full-person')
    exchange.add_argument('--resource', action='append', default=[])
    exchange.add_argument('--no-sources', action='store_true')
    exchange.add_argument('--json', action='store_true')
    exchange.add_argument('--review', type=Path, help='Host-recorded disclosure plan directory; use export-plan then export-review.')
    plan = commands.add_parser('export-plan', help='Capture exact source inclusion or supplied derivative scope for human review.')
    plan.add_argument('--person', required=True)
    plan.add_argument('--out', type=Path, required=True)
    plan.add_argument('--mode', choices=('full-person','selected-current'), default='full-person')
    plan.add_argument('--resource', action='append', default=[])
    plan.add_argument('--derivatives', type=Path, help='JSON list of individually supplied derivative files and human mappings/omissions.')
    plan.add_argument('--json', action='store_true')
    review = commands.add_parser('export-review', help='Record an explicit human decision over the displayed plan digest; local labels are unauthenticated.')
    review.add_argument('--plan', type=Path, required=True)
    review.add_argument('--decision', type=Path, required=True)
    review.add_argument('--json', action='store_true')
    agent = commands.add_parser("agent", help="Discover tasks and prepare bounded local context; no model execution.")
    agents = agent.add_subparsers(dest="agent_command", required=True)
    tasks = agents.add_parser("tasks", help="List kit routes without clinical reads.")
    tasks.add_argument("--json", action="store_true")
    context = agents.add_parser("context", help="Build an explicit-person bounded packet.")
    context.add_argument("--task", required=True)
    context.add_argument("--person", required=True)
    context.add_argument("--out", type=Path, required=True)
    context.add_argument("--source", action="append", default=[])
    context.add_argument("--resource", action="append", default=[])
    context.add_argument("--from-date")
    context.add_argument("--to-date")
    context.add_argument("--max-records", type=int, default=100)
    context.add_argument("--max-data-bytes", type=int, default=262144)
    context.add_argument("--continuation", type=Path, help="Prior context.json; repeats the same selection at its bound head.")
    context.add_argument("--json", action="store_true")
    render = agents.add_parser('render', help='Verify a packet and render declared JSON slots; no agent execution.')
    render.add_argument('--context', type=Path, required=True)
    render.add_argument('--trusted-context-sha256', required=True,
        help='Original builder digest retained from agent context / intake add stdout, outside editable packet files.')
    render.add_argument('--person', required=True)
    render.add_argument('--prompt', required=True)
    render.add_argument('--variables', type=Path, required=True)
    render.add_argument('--json', action='store_true')
    try:
        args = parser.parse_args(argv)
        exit_code = 0
        if args.command == "agent":
            path = args.vault or os.environ.get("HELSEARK_VAULT")
            if args.agent_command == "tasks":
                kit_path = _vault_kit(_open_vault_metadata(Path(path)))[0] if path else _bundled_root() / 'agent-kit'
                output = [document(t) for t in list_agent_tasks(kit_path)]
            elif args.agent_command == 'render':
                if not path:
                    raise ArchiveError('INVALID_INPUT', 'Provide --vault PATH or HELSEARK_VAULT.')
                packet = read_agent_context(args.context)
                expected = Path(path).resolve() / 'agent-kit' / packet.kitVersion / 'manifest.json'
                if packet.personId != args.person or Path(packet.kitManifest.path) != expected:
                    raise ArchiveError('CONTEXT_MISMATCH', 'Packet differs from selected vault/person.')
                output = document(render_task_prompt(packet, args.prompt, decode_json(args.variables.read_bytes()),
                    trusted_context_sha256=args.trusted_context_sha256))
            else:
                if not path:
                    raise ArchiveError('INVALID_INPUT', 'Provide --vault PATH or HELSEARK_VAULT.')
                vault = _open_vault_metadata(Path(path))
                refs = []
                for value in args.resource:
                    parts = value.split('/')
                    if len(parts) == 2:
                        refs.append(ResourceRef(*parts))
                    elif len(parts) == 4 and parts[2] == '_history':
                        refs.append(ResourceRef(parts[0], parts[1], parts[3]))
                    else:
                        raise ArchiveError('INVALID_REFERENCE', 'Use Type/UUID or Type/UUID/_history/UUID.')
                token = None
                if args.continuation:
                    prior = decode_json(args.continuation.read_bytes())
                    try:
                        raw = prior['continuation']
                        token = ContextContinuation(raw['personId'], raw['taskId'], Head(**raw['base']), raw['requestSha256'], raw['offset'])
                    except (KeyError, TypeError):
                        raise ArchiveError('INVALID_CONTINUATION', 'Prior context must contain a continuation.') from None
                built = build_agent_context(vault, args.person, args.task,
                    ContextRequest(tuple(args.source), tuple(refs), args.from_date, args.to_date,
                        args.max_records, args.max_data_bytes, token), args.out)
                output = {**document(built), 'trustedContextSha256': built.trustedContextSha256}
        elif args.command == 'backup' and args.backup_command in ('verify','restore'):
            if args.backup_command == 'verify':
                report = verify_export(args.bundle)
                output = document(report)
                exit_code = 5 if report.issues else 0
            else:
                restored = restore(args.bundle, args.into)
                output = {'path': str(restored.root), 'vaultId': restored.config.vaultId}
        elif args.command == "init":
            vault = init_vault(args.path)
            output = {"vaultId": vault.config.vaultId, "path": str(vault.root)}
        elif args.command == "schema" and not args.vault and not os.environ.get("HELSEARK_VAULT"):
            with TemporaryDirectory(prefix="helseark-schema-") as temporary:
                vault = init_vault(Path(temporary) / "vault")
                output = {"path": str(schema_packet(vault, args.resource, args.out))}
        else:
            path = args.vault or os.environ.get("HELSEARK_VAULT")
            if not path:
                raise ArchiveError("INVALID_INPUT", "Provide --vault PATH or HELSEARK_VAULT.")
            if args.command == 'migrate':
                vault = open_migration_source(Path(path), allowTestFixture=args.test_only_legacy)
            elif args.command == 'doctor':
                from .contracts import Vault, VaultConfig
                try:
                    vault = Vault(Path(path).absolute(), VaultConfig(**_json(Path(path), 'vault.json')))
                except TypeError:
                    raise ArchiveError('INVALID_ENVELOPE','Invalid vault configuration.') from None
            elif args.command == 'schema':
                vault = open_definitions(Path(path))
            elif args.command in ('intake','candidate','observations','timeline','history','record','report','correct') or (args.command == 'validate' and args.validation_command == 'candidate'):
                vault = _open_vault_metadata(Path(path))
            else:
                vault = open_vault(Path(path))
            if args.command == 'correct':
                output = document(start_correction(vault,args.person,parse_reference(args.resource),args.reason))
            elif args.command == 'erase':
                if args.erase_command == 'plan':
                    plan = plan_person_erasure(vault,args.person,args.quarantine)
                    from .archive import _write
                    _write(args.out,encode_json(document(plan)))
                    output = document(plan)
                elif args.erase_command == 'apply':
                    output = document(apply_person_erasure(vault,read_erasure_plan(args.plan),args.approve))
                else:
                    output = document(restore_person_erasure(vault,args.quarantine,args.approve))
            elif args.command == 'migrate':
                if args.migration_command == 'plan':
                    plan = (plan_fhir_migration(vault,args.to_fhir) if args.to_fhir else
                            plan_migration(vault,replace(CURRENT,contractVersion=args.to_contract)))
                    output = document(plan)
                    exit_code = 6 if plan.blockedRecords else 0
                else:
                    output = document(apply_migration(vault,read_migration_plan(args.plan),args.into,
                        reviewedPlanSha256=args.reviewed_plan_sha256,resume=args.resume))
            elif args.command == 'doctor':
                report = doctor(vault)
                output = document(report)
                exit_code = 5 if any(i.severity=='error' for i in report.issues) else 3 if report.issues else 0
            elif args.command == 'backup':
                output = document(backup(vault,args.out,includeWork=args.include_work))
            elif args.command == 'export-plan':
                selection = ExportSelection(args.mode,tuple(parse_reference(r) for r in args.resource))
                path = prepare_disclosure(vault,args.person,selection,args.out,
                    derivatives=decode_json(_regular(args.derivatives, DISCLOSURE_BYTES)) if args.derivatives else ())
                from .serialization import hash_bytes
                output = {'path':str(path),'planSha256':hash_bytes((path/'plan.json').read_bytes()),'plan':_json(path,'plan.json')}
            elif args.command == 'export-review':
                path = record_disclosure(vault,args.plan,decode_json(_regular(args.decision, DISCLOSURE_BYTES)))
                output = {'path':str(path)}
            elif args.command == 'report':
                destination = args.out if args.out is not None else vault.root/'derived/reports'/args.person
                output = {'path': str(render_static_report(vault, args.person, destination))}
            elif args.command == 'export':
                output = document(export_person(vault,args.person,args.out,
                    ExportSelection(args.mode,tuple(parse_reference(r) for r in args.resource),not args.no_sources),review=args.review))
            elif args.command in ('observations','timeline','history','record'):
                at = None
                if args.at_head:
                    raw = decode_json(args.at_head.read_bytes())
                    if (not isinstance(raw,dict) or set(raw) != {'sequence','transactionId','changeSha256'} or
                            type(raw['sequence']) is not int or raw['sequence'] < 1):
                        raise ArchiveError('INVALID_INPUT','Expected an exact Head JSON object.')
                    from .contracts import sha256_string
                    uuid_string(raw['transactionId']); sha256_string(raw['changeSha256'])
                    at = Head(**raw)
                if args.command == 'observations':
                    output = document(list(observations(vault,args.person,ObservationFilter(
                        args.code_system,args.code,args.label,args.from_date,args.to_date,args.include_invalidated),at=at)))
                elif args.command == 'history':
                    output = list(history(vault,args.person,args.kind,at=at))
                elif args.command == 'timeline':
                    output = document(list(timeline(vault,args.person,at=at)))
                else:
                    output = resolve(vault,args.person,parse_reference(args.resource),at=at)
            elif args.command == 'intake':
                ocr_config = None
                if getattr(args, 'ocr_config', None):
                    from .adapters.ocr import OcrConfig
                    raw_config = decode_json(_regular(args.ocr_config, 65536))
                    try:
                        ocr_config = OcrConfig(**{k: Path(v) if k in ('outputDirectory','engine','renderer','model') else v for k,v in raw_config.items()})
                    except (TypeError, ValueError, AttributeError):
                        raise ArchiveError('INVALID_INPUT','Invalid OCR configuration.') from None
                source = add_source(vault, args.person, args.source)
                if args.intake_command == 'fhir-r4':
                    from .adapters.fhir_r4 import import_fhir_r4, IdentityMapping
                    raw = decode_json(_regular(args.mapping, 65536))
                    if not isinstance(raw,dict) or set(raw) != {'patientReference','localPersonId','assignmentReason','provider'}:
                        raise ArchiveError('IDENTITY_MAPPING_REQUIRED','Expected trusted local IdentityMapping JSON.')
                    output = document(import_fhir_r4(source,args.person,IdentityMapping(**raw)))
                elif args.intake_command == 'metrics-csv':
                    from .adapters.csv_metrics import import_metrics_csv, CsvMetricMapping
                    raw = decode_json(_regular(args.mapping, 65536))
                    required = {'delimiter','encoding','dateColumn','valueColumn','unitColumn','codeColumn',
                                'dateFormat','decimalSeparator','localPersonId','assignmentReason'}
                    if not isinstance(raw,dict) or not required.issubset(raw) or set(raw)-required-{'timezone','codeSystem'}:
                        raise ArchiveError('CSV_MAPPING_REQUIRED','Expected trusted local CsvMetricMapping JSON.')
                    output = document(import_metrics_csv(source,args.person,CsvMetricMapping(**raw)))
                else:
                    built = build_packet(vault, source, args.packet,
                        identityConfirmed=args.confirm_person, outputDirectory=args.agent_output, ocrConfig=ocr_config)
                    output = {**document(built), 'trustedContextSha256': built.trustedContextSha256}
            elif args.command == 'candidate':
                if args.candidate_command=='prepare':
                    candidate=read_candidate(vault,args.path,person=args.person)
                    reconciliation=decode_json(args.reconciliation.read_bytes()) if args.reconciliation else None
                    if reconciliation is not None and (not isinstance(reconciliation,dict) or any(v is not None and not isinstance(v,str) for v in reconciliation.values())):
                        raise ArchiveError('INVALID_INPUT','Reconciliation must map references to strings or null.')
                    proposal=prepare_candidate(vault,candidate,reextract=args.reextract,reconciliation=reconciliation,authorized_sources=tuple(args.source) if args.source else None,
                        amendment_target=parse_reference(args.amendment_target) if args.amendment_target else None,amendment_reason=args.amendment_reason)
                    output={**document(proposal),'disposition':'already-accepted' if (proposal.path/'change.json').exists() else 'prepared'}
                else:
                    envelope=_json(args.path,'proposal.json')
                    if not isinstance(envelope,dict) or envelope.get('personId')!=args.person:
                        raise ArchiveError('PERSON_MISMATCH','Proposal differs from explicit person.')
                    proposal=read_prepared(vault,args.path)
                    if proposal.personId!=args.person:
                        raise ArchiveError('PERSON_MISMATCH','Proposal differs from explicit person.')
                    if args.candidate_command=='review':
                        if args.decision:
                            raw=decode_json(args.decision.read_bytes())
                            if not isinstance(raw,dict) or set(raw)!={'confirmedPerson','decision','acknowledgedIssues','reviewerLabel'} or not isinstance(raw['acknowledgedIssues'],list) or not isinstance(raw['reviewerLabel'],str):
                                raise ArchiveError('INVALID_INPUT','Expected explicit human ReviewDecision object.')
                            decision=ReviewDecision(raw['confirmedPerson'],raw['decision'],tuple(raw['acknowledgedIssues']),raw['reviewerLabel'])
                            output=document(record_review(vault,proposal,decision))
                        else: output=document(render_review(vault,proposal))
                    else:
                        receipt=read_receipt(vault,proposal)
                        output=document(commit_candidate(vault,proposal,receipt))
            elif args.command == "schema":
                output = {"path": str(schema_packet(vault, args.resource, args.out))}
            elif args.command == "validate":
                uuid_string(args.person)
                if args.validation_command == "candidate":
                    candidate = read_candidate(vault, args.path, person=args.person)
                    report = validate_candidate(vault, candidate)
                else:
                    metadata = _json(args.path, "proposal.json")
                    if not isinstance(metadata, dict) or metadata.get("personId") != args.person:
                        raise ArchiveError("PERSON_MISMATCH", "Proposal differs from explicitly selected person.")
                    if args.official_config or args.require_official:
                        from .fhir_validator import validate_with_official_tool, verify_recorded_run
                        prepared = read_prepared(vault,args.path)
                        report = validate_with_official_tool(prepared,args.official_config,vault=vault)
                        verify_recorded_run(vault,replace(prepared,validation=report))
                        # Atomic replacement of the unreviewed report, never a clinical file.
                        from tempfile import NamedTemporaryFile
                        with NamedTemporaryFile(dir=args.path,delete=False) as stream:
                            temporary_report = Path(stream.name)
                            stream.write(encode_json(document(report))); stream.flush(); os.fsync(stream.fileno())
                        os.replace(temporary_report,args.path/'validation.json')
                    else:
                        report = validate_proposal(vault, args.path)
                output = {"checkedProposalSha256": report.checkedProposalSha256,
                          "coverage": [asdict(c) for c in report.coverage],
                          "issues": [asdict(i) for i in report.issues]}
                if report.officialRun is not None:
                    output['officialRun'] = report.officialRun
                errors = {i.code for i in report.issues if i.severity == "error"}
                if "STALE_BASE" in errors:
                    exit_code = 4
                elif errors & {"INTEGRITY", "DEFINITION_MISMATCH", "IO_ERROR", "SOURCE_HASH_MISMATCH", "RESOURCE_HASH_MISMATCH", "EVIDENCE_HASH_MISMATCH"}:
                    exit_code = 5
                elif errors & {"MISSING_DEFINITION", "UNSUPPORTED_VERSION", "UNSUPPORTED_DIALECT"}:
                    exit_code = 6
                else:
                    exit_code = 2 if errors else 3 if any(i.severity == "review" for i in report.issues) else 0
            else:
                person_id = add_person(vault, PersonDraft(args.name, args.birth_date, args.note))
                output = {"personId": person_id}
        if args.json or args.command in ('doctor','backup','export','export-plan','export-review','migrate'):
            sys.stdout.buffer.write(encode_json(output))
        else:
            if args.command in ('observations','timeline','history','record'):
                sys.stdout.buffer.write(encode_json(output))
            elif args.command == "validate":
                if report.officialRun is not None:
                    run=report.officialRun
                    print(f"Official R4/profile checks: {run['resourceCount']} resources, {run['counts']['errors']} errors, {run['counts']['warnings']} warnings; terminology not checked; human review mandatory.")
                print("Baseline archive checks blocked." if exit_code in {2, 4, 5, 6} else
                      "Baseline archive checks completed; review required; terminology not checked." if exit_code == 3 else
                      "Baseline archive checks passed; terminology not checked. Human review remains mandatory.")
            elif args.command == 'candidate':
                print(encode_json(output).decode(),end='')
            elif args.command == 'intake':
                print(output['path'])
                if 'trustedContextSha256' in output:
                    print('Host-retained context SHA-256: '+output['trustedContextSha256'])
            elif args.command == 'agent' and args.agent_command == 'tasks':
                for task in output:
                    print(task['id'] + ': ' + task['availability']['status'])
            elif args.command == 'agent' and args.agent_command == 'render':
                print(output['text'])
            else:
                print(output.get("personId", output.get("path")))
                if args.command == 'agent' and args.agent_command == 'context':
                    print('Host-retained context SHA-256: '+output['trustedContextSha256'])
        return exit_code
    except ArchiveError as error:
        sys.stderr.buffer.write(encode_json({"code": error.code, "message": error.safeMessage, "details": error.details}))
        return _EXIT.get(error.code, error.details.get('exitCode', 5))
    except OSError:
        sys.stderr.buffer.write(encode_json({"code": "IO_ERROR", "message": "Archive I/O failed; reopen to determine committed state."}))
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
