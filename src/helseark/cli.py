"""Small CLI; all archive behavior is shared with the library."""
import argparse
from dataclasses import asdict
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from .archive import init_vault, open_vault, open_definitions, add_person, _json, _open_vault_metadata, _bundled_root
from .contracts import ArchiveError, PersonDraft, uuid_string, ResourceRef, ContextRequest, ContextContinuation, Head
from .query import observations, timeline, parse_reference
from .archive import resolve
from .contracts import ObservationFilter
from .intake import add_source, build_packet, read_candidate
from .serialization import encode_json, decode_json
from .agent_context import list_agent_tasks, build_agent_context, _vault_kit, document, read_agent_context, render_task_prompt
from .validation import schema_packet, validate_candidate, validate_proposal

_EXIT = {
    "INVALID_FILTER": 2, "UNKNOWN_HEAD": 2, "CONTEXT_AUTHORITY_REQUIRED": 2,
    "INVALID_VARIABLE": 2, "INCOMPATIBLE_PROMPT": 2, "CONTEXT_MISMATCH": 5,
    "CONTEXT_BUDGET_EXCEEDED": 2, "UNKNOWN_TASK": 2, "INVALID_CONTINUATION": 2,
    "CAPABILITY_UNAVAILABLE": 6, "MISSING_KIT": 6, "INVALID_KIT": 6, "KIT_MISMATCH": 5,
    "PERSON_NOT_FOUND": 2, "RESOURCE_NOT_FOUND": 2, "SOURCE_MISSING": 2,
    "ARCHIVE_BUSY": 4, "STALE_BASE": 4,
    "UNSUPPORTED_VERSION": 6, "DEFINITION_MISMATCH": 5,
    "NUMERIC_LIMIT": 2, "DUPLICATE_KEY": 2, "DEPTH_LIMIT": 2,
    "INVALID_JSON": 2, "INVALID_INPUT": 2, "INVALID_PERSON": 2,
    "DESTINATION_EXISTS": 2, "INVALID_ID": 2, "INVALID_REFERENCE": 2,
    "VALIDATION_BLOCKED": 2, "REVIEW_MISMATCH": 3,
    "UNSAFE_PATH": 2, "SOURCE_TOO_LARGE": 2, "PAGE_LIMIT": 2,
    "TEXT_FIELD_LIMIT": 2, "RESOURCE_LIMIT": 2, "INTAKE_ISSUES_MISSING": 2,
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
    for name in ('observations','timeline','record'):
        query = commands.add_parser(name, help='Read one person at a current or exact historical Head.')
        query.add_argument('--person',required=True)
        query.add_argument('--at-head',type=Path,help='JSON object with sequence, transactionId and changeSha256.')
        query.add_argument('--json',action='store_true')
        if name == 'observations':
            query.add_argument('--label')
            query.add_argument('--code-system')
            query.add_argument('--code')
            query.add_argument('--from-date')
            query.add_argument('--to-date')
            query.add_argument('--include-invalidated',action='store_true')
        if name == 'record':
            query.add_argument('--resource',required=True,help='Type/UUID or Type/UUID/_history/UUID.')
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
            if args.command == 'schema':
                vault = open_definitions(Path(path))
            elif args.command in ('intake','observations','timeline','record') or (args.command == 'validate' and args.validation_command == 'candidate'):
                vault = _open_vault_metadata(Path(path))
            else:
                vault = open_vault(Path(path))
            if args.command in ('observations','timeline','record'):
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
                elif args.command == 'timeline':
                    output = document(list(timeline(vault,args.person,at=at)))
                else:
                    output = resolve(vault,args.person,parse_reference(args.resource),at=at)
            elif args.command == 'intake':
                source = add_source(vault, args.person, args.source)
                built = build_packet(vault, source, args.packet,
                    identityConfirmed=args.confirm_person, outputDirectory=args.agent_output)
                output = {**document(built), 'trustedContextSha256': built.trustedContextSha256}
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
                    report = validate_proposal(vault, args.path)
                output = {"checkedProposalSha256": report.checkedProposalSha256,
                          "coverage": [asdict(c) for c in report.coverage],
                          "issues": [asdict(i) for i in report.issues]}
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
        if args.json:
            sys.stdout.buffer.write(encode_json(output))
        else:
            if args.command in ('observations','timeline','record'):
                sys.stdout.buffer.write(encode_json(output))
            elif args.command == "validate":
                print("Baseline archive checks blocked." if exit_code in {2, 4, 5, 6} else
                      "Baseline archive checks completed; review required; terminology not checked." if exit_code == 3 else
                      "Baseline archive checks passed; terminology not checked. Human review remains mandatory.")
            elif args.command == 'intake':
                print(output['path'])
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
