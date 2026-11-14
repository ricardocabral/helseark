"""Small CLI; all archive behavior is shared with the library."""
import argparse
from dataclasses import asdict
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from .archive import init_vault, open_vault, add_person, head, _read
from .contracts import ArchiveError, PersonDraft, Candidate, Issue, uuid_string
from .serialization import encode_json, decode_json
from .validation import load_definition_registry, schema_packet, validate_candidate, validate_proposal

_EXIT = {
    "ARCHIVE_BUSY": 4, "STALE_BASE": 4,
    "UNSUPPORTED_VERSION": 6, "DEFINITION_MISMATCH": 5,
    "INVALID_JSON": 2, "INVALID_INPUT": 2, "INVALID_PERSON": 2,
    "DESTINATION_EXISTS": 2, "INVALID_ID": 2, "INVALID_REFERENCE": 2,
    "VALIDATION_BLOCKED": 2, "REVIEW_MISMATCH": 3,
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
    try:
        args = parser.parse_args(argv)
        exit_code = 0
        if args.command == "init":
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
            vault = open_vault(Path(path))
            if args.command == "schema":
                output = {"path": str(schema_packet(vault, args.resource, args.out))}
            elif args.command == "validate":
                uuid_string(args.person)
                if args.validation_command == "candidate":
                    metadata = decode_json(_read(args.path, "candidate.json"))
                    registry = load_definition_registry(vault)
                    if not registry.validate("urn:helseark:schema:0.1.0:candidate", metadata):
                        raise ArchiveError("INVALID_ENVELOPE", "Candidate metadata violates its pinned contract.")
                    if metadata["personId"] != args.person:
                        raise ArchiveError("PERSON_MISMATCH", "Candidate differs from explicitly selected person.")
                    base = head(vault, args.person)
                    if metadata["baseChangeSha256"] != (base.changeSha256 if base else None):
                        raise ArchiveError("STALE_BASE", "Candidate base differs from accepted history.")
                    candidate = Candidate(args.path, metadata["candidateId"], args.person, base,
                        decode_json(_read(args.path, metadata["bundlePath"])),
                        decode_json(_read(args.path, metadata["evidencePath"])),
                        tuple(Issue(**issue) for issue in metadata["unresolved"]))
                    report = validate_candidate(vault, candidate)
                else:
                    metadata = decode_json(_read(args.path, "proposal.json"))
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
            if args.command == "validate":
                print("Baseline archive checks blocked." if exit_code in {2, 4, 5, 6} else
                      "Baseline archive checks completed; review required; terminology not checked." if exit_code == 3 else
                      "Baseline archive checks passed; terminology not checked. Human review remains mandatory.")
            else:
                print(output.get("personId", output.get("path")))
        return exit_code
    except ArchiveError as error:
        sys.stderr.buffer.write(encode_json({"code": error.code, "message": error.safeMessage, "details": error.details}))
        return _EXIT.get(error.code, 5)
    except OSError:
        sys.stderr.buffer.write(encode_json({"code": "IO_ERROR", "message": "Archive I/O failed; reopen to determine committed state."}))
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
