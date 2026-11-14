"""Failed-request matrix over genuine retained actual execution authority.

This probe never creates execution evidence or simulates validator conformance.
Run against an installed runtime and an owned copy of a real pending workflow.
"""
from dataclasses import replace
from pathlib import Path
import shutil
import subprocess
import sys

from helseark import fhir_validator as tool
from helseark.agent_context import document
from helseark.archive import commit_candidate
from helseark.contracts import ArchiveError
from helseark.review import read_prepared, render_review, record_review
from helseark.serialization import encode_json, decode_json, hash_bytes
from helseark.validation import validate_proposal
from qualify_validator_authority import fork_workflow, inventory, decision


def failed_request_matrix(pending, output, config, *, vulnerable=False):
    results = []
    for name in ('missing-config-adapter', 'missing-config-api', 'missing-config-cli', 'invalid-config-cli'):
        vault, path = fork_workflow(pending, output/name)
        prepared = read_prepared(vault, path)
        assert prepared.validation.officialRun['resourceCount'] > 0
        # Positive control: genuine report + host authority works before request.
        view = render_review(vault, prepared)
        human = decision(view)
        receipt = record_review(vault, prepared, human)
        review_bytes = receipt.path.read_bytes()
        receipt.path.unlink()  # retain legitimate old receipt for later replay
        review_control = vault.root/f'.runtime/reviews/{prepared.proposalSha256}.json'
        review_control_bytes = review_control.read_bytes()
        review_control.unlink()
        control = vault.root/f'.runtime/prepared/{prepared.proposalSha256}.json'
        before_control = control.read_bytes()
        before_people = inventory(vault.root/'people')
        before_proposal = inventory(path)
        expected = 'VALIDATOR_DIGEST_MISMATCH' if name == 'invalid-config-cli' else 'VALIDATOR_UNAVAILABLE'
        exit_code = None
        if name.endswith('cli'):
            args = [sys.executable, '-m', 'helseark.cli', '--vault', str(vault.root),
                    'validate', 'proposal', str(path), '--person', prepared.personId, '--require-official', '--json']
            if name == 'invalid-config-cli':
                value = document(replace(config, requireTerminology=True, executableSha256='0'*64))
                config_path = output/name/'invalid-config.json'
                config_path.write_bytes(encode_json(value))
                args += ['--official-config', str(config_path)]
            process = subprocess.run(args, capture_output=True)
            exit_code = process.returncode
            assert exit_code == (5 if name == 'invalid-config-cli' else 6), process.stderr
            assert expected.encode() in process.stderr, process.stderr
        else:
            try:
                if name.endswith('adapter'):
                    tool.validate_with_official_tool(prepared, None, vault=vault)
                else:
                    validate_proposal(vault, path, requireOfficial=True)
            except ArchiveError as error:
                assert error.code == expected, error
            else:
                raise AssertionError('Request unexpectedly succeeded')
        after_control = control.read_bytes()
        assert inventory(path) == before_proposal
        observations = {}
        for label, operation in (
            ('render', lambda: render_review(vault, prepared)),
            ('review', lambda: record_review(vault, prepared, human)),
        ):
            try:
                operation()
                observations[label] = 'SUCCEEDED'
            except ArchiveError as error:
                observations[label] = error.code
        # Replay the exact prior human receipt, without generating new authority.
        receipt.path.write_bytes(review_bytes)
        review_control.write_bytes(review_control_bytes)
        try:
            observations['commit'] = commit_candidate(vault, prepared, receipt).disposition
        except ArchiveError as error:
            observations['commit'] = error.code
        if vulnerable:
            assert before_control == after_control
            assert observations == {'render': 'SUCCEEDED', 'review': 'SUCCEEDED', 'commit': 'committed'}
        else:
            assert before_control != after_control
            assert all(value.startswith('VALIDATOR_AUTHORITY_') for value in observations.values()), observations
            assert inventory(vault.root/'people') == before_people
        results.append({'case': name, 'request': expected, 'exit': exit_code,
                        'controlChanged': before_control != after_control,
                        'beforeControl': decode_json(before_control), 'afterControl': decode_json(after_control),
                        'peopleFiles': len(before_people), 'proposalFiles': len(before_proposal),
                        'proposalBytesUnchanged': inventory(path) == {**before_proposal, 'review.json': hash_bytes(review_bytes)},
                        'peopleBytesUnchanged': inventory(vault.root/'people') == before_people,
                        'reportSha256': before_proposal['validation.json'], **observations})
        shutil.rmtree(vault.root.parent)
    return results


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pending', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--vulnerable', action='store_true')
    args = parser.parse_args()
    config = tool.load_validator_config(args.config)
    result = failed_request_matrix(args.pending, args.output, config, vulnerable=args.vulnerable)
    (args.output/'results.json').write_bytes(encode_json(result))
    print(encode_json(result).decode(), flush=True)
