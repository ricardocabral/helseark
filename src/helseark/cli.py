"""Small CLI; all archive behavior is shared with the library."""
import argparse
import os
from pathlib import Path
import sys

from .archive import init_vault, open_vault, add_person
from .contracts import ArchiveError, PersonDraft
from .serialization import encode_json

_EXIT = {
    "ARCHIVE_BUSY": 4, "STALE_BASE": 4,
    "UNSUPPORTED_VERSION": 6, "DEFINITION_MISMATCH": 5,
    "INVALID_JSON": 2, "INVALID_INPUT": 2, "INVALID_PERSON": 2,
    "DESTINATION_EXISTS": 2, "INVALID_ID": 2, "INVALID_REFERENCE": 2,
    "VALIDATION_BLOCKED": 2, "REVIEW_MISMATCH": 3,
}


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ArchiveError("INVALID_INPUT", "Invalid command arguments; use --help.")


def main(argv=None):
    parser = _Parser(prog="helseark", description="Offline immutable local health archive (Task 1 storage).")
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
    try:
        args = parser.parse_args(argv)
        if args.command == "init":
            vault = init_vault(args.path)
            output = {"vaultId": vault.config.vaultId, "path": str(vault.root)}
        else:
            path = args.vault or os.environ.get("HELSEARK_VAULT")
            if not path:
                raise ArchiveError("INVALID_INPUT", "Provide --vault PATH or HELSEARK_VAULT.")
            vault = open_vault(Path(path))
            person_id = add_person(vault, PersonDraft(args.name, args.birth_date, args.note))
            output = {"personId": person_id}
        if args.json:
            sys.stdout.buffer.write(encode_json(output))
        else:
            print(output.get("personId", output.get("path")))
        return 0
    except ArchiveError as error:
        sys.stderr.buffer.write(encode_json({"code": error.code, "message": error.safeMessage, "details": error.details}))
        return _EXIT.get(error.code, 5)
    except OSError:
        sys.stderr.buffer.write(encode_json({"code": "IO_ERROR", "message": "Archive I/O failed; reopen to determine committed state."}))
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
