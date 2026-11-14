"""Historical genuine reports stay readable without invented execution authority."""
from pathlib import Path
import subprocess
import sys
import pytest

from helseark.contracts import ArchiveError

from helseark.archive import init_vault, open_vault, _schema
from helseark.review import read_prepared, read_receipt, render_review
from helseark.serialization import decode_json, hash_bytes


def test_immutable_legacy_report_and_current_schema_dispatch(tmp_path):
    setup = Path(__file__).with_name('setup_validator_legacy.py')
    subprocess.run([sys.executable, str(setup), str(tmp_path/'legacy')], check=True)
    root = tmp_path/'legacy/vault'
    original = {p.relative_to(root): hash_bytes(p.read_bytes())
                for p in root.rglob('*') if p.is_file()}
    assert len(original) > 200
    legacy = open_vault(root)
    accepted = next(p.parent for p in (root/'people').glob('*/accepted/00000002-*/validation.json')
                    if decode_json(p.read_bytes()).get('officialRun'))
    prepared = read_prepared(legacy, accepted)
    view = render_review(legacy, prepared)
    read_receipt(legacy, prepared)
    assert prepared.validation.officialRun['resourceCount'] == 5
    assert all(c['result'] == 'not-checked' for c in view.validationCoverage)
    assert 'officialValidationAuthority' not in decode_json((accepted/'review.json').read_bytes())
    assert original == {p.relative_to(root): hash_bytes(p.read_bytes())
                        for p in root.rglob('*') if p.is_file()}
    # The current schema requires the actual command/environment fields absent
    # from the historical report. Reading old pins cannot invent these fields.
    current = init_vault(tmp_path/'current')
    with pytest.raises(ArchiveError, match='INVALID_ENVELOPE'):
        _schema(current, 'validation', decode_json((accepted/'validation.json').read_bytes()))


def test_invalid_review_authority_returns_typed_contract_error(tmp_path):
    from test_intake import supplied_candidate
    from test_review import prepare, approve
    vault, _, _, _, candidate = supplied_candidate(tmp_path)
    prepared = prepare(vault, candidate)
    receipt = approve(vault, prepared)
    malformed = decode_json(receipt.path.read_bytes())
    malformed['officialValidationAuthority'] = None
    # Resolve the real local authority contract and reject the invalid value.
    # This exercises schema failure handling, not validator conformance.
    with pytest.raises(ArchiveError, match='INVALID_ENVELOPE'):
        _schema(vault, 'review', malformed)
