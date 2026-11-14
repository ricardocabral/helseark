"""Execute the documented Task5 learning path from a clean directory."""
import os
from pathlib import Path
import subprocess
import sys


def test_first_archive_tutorial_from_clean_directory(tmp_path):
    root = Path(__file__).resolve().parents[1]
    page = (root/'docs/tutorials/first-archive.md').read_text()
    code = page.split('```python\n',1)[1].split('```',1)[0]
    result = subprocess.run([sys.executable,'-c',code],cwd=tmp_path,
        env={**os.environ,'PYTHONPATH':str(root/'src')},capture_output=True,text=True)
    assert result.returncode == 0, result.stderr + result.stdout
    assert 'validated untrusted draft: <0.050 mg/L' in result.stdout
    assert len(list((tmp_path/'lesson-vault/people').glob('*/accepted/*/change.json'))) == 1
