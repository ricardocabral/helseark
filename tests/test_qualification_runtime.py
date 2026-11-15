"""Qualification must refuse a checkout even when wheel bytes are supplied."""
from pathlib import Path
import os
import subprocess
import sys


def test_official_qualification_rejects_checkout_runtime(tmp_path):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, '-c',
         'from qualify_official_validator import record_installed_runtime; '
         'from pathlib import Path; '
         'record_installed_runtime(Path("not-installed.whl"), Path("unused"))'],
        cwd=tmp_path,
        env={**os.environ, 'PYTHONPATH': os.pathsep.join((str(root/'src'), str(root/'tests')))},
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert 'Qualification requires the installed wheel' in result.stderr, result.stderr
