"""Manifest failures are byte/provenance checks, not medical/PHI detection."""
import importlib.util
from pathlib import Path
import shutil
import pytest

spec=importlib.util.spec_from_file_location('fixture_checker',Path(__file__).resolve().parents[1]/'scripts/check_fixture_manifest.py')
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)


def test_declared_fixture_inventory_and_tampered_byte(tmp_path):
    assert checker.check()['files']>0
    root=Path(__file__).resolve().parents[1]
    for directory in checker.ROOTS:
        shutil.copytree(root/directory,tmp_path/directory,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copyfile(root/'tests/fixture-manifest.json',tmp_path/'tests/fixture-manifest.json')
    target=tmp_path/'examples/synthetic-family/expected-facts.json'
    target.write_bytes(target.read_bytes()+b' ')
    with pytest.raises(AssertionError):checker.check(tmp_path)
