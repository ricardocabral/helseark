# First archive: review, publish, query and restore

For toolkit 0.1.2, kit 0.1.16, archive format 1, contract 0.1.0 / profile-set 0.2.0
and independently versioned exact-issue review receipts 0.1.1.
Use Python 3.12+ and an installed local Helseark wheel with its pinned `pdf` extra.
Setup may require acquiring dependencies in advance; the lesson itself is offline.
Run in an empty disposable directory. Only synthetic data is used. No model runs.
This branch is under development and is not production-qualified.

Save the following as `first-intake.py` and run `python first-intake.py`.
The code creates real IDs through the CLI and binds the supplied deterministic
candidate to the actual intake packet. When prompted, inspect the displayed
prepared resources, source quotes, coverage and limitations alongside the supplied
PDF. Confirm Avery Synthetic, both rows, `<0,050 mg/L`, month `2026-01`, final status,
method M1, printed range and qualitative “not detected”. Type `SYNTHETIC` only after
that inspection. This records an explicit synthetic test review; the local reviewer
label does not authenticate a human. It is not a recipe for approving real reports.

```python
from pathlib import Path
from decimal import Decimal
import json
import subprocess
import sys
import hashlib
import shutil

root = Path.cwd().resolve()
vault = root / 'lesson-vault'
packet = root / 'lesson-packet'
candidate = root / 'lesson-candidate'

def cli(*args, expected=0):
    result = subprocess.run([sys.executable, '-m', 'helseark.cli', *map(str,args)],
                            capture_output=True, text=True)
    if result.returncode != expected:
        raise RuntimeError(result.stderr or result.stdout)
    from helseark.serialization import decode_json
    return decode_json(result.stdout.encode())

cli('init', vault, '--json')
person = cli('--vault', vault, 'person', 'add', '--name', 'Avery Synthetic', '--json')['personId']
config = json.loads((vault / 'vault.json').read_text())
kit = vault / 'agent-kit' / config['agentKitVersion']
source = kit / 'examples/task5-complete.pdf'
intake = cli('--vault', vault, 'intake', 'add', source, '--person', person,
             '--packet', packet, '--agent-output', root / 'lesson-agent-output',
             '--confirm-person', '--json')
assert (packet / 'ENTRY.md').is_file()
assert (packet / 'prompt.txt').is_file()
subprocess.run([sys.executable, str(kit / 'examples/task5-example.py'),
                str(packet), str(candidate)], check=True)
report = cli('--vault', vault, 'validate', 'candidate', candidate,
             '--person', person, '--json', expected=3)
assert not [i for i in report['issues'] if i['severity'] == 'error']
bundle = json.loads((candidate / 'bundle.json').read_text(), parse_float=Decimal)
quantity = bundle['entry'][0]['resource']['valueQuantity']
assert str(quantity['value']) == '0.050'
assert quantity['comparator'] == '<' and quantity['unit'] == 'mg/L'
retained = Path(intake['source']['assetPath'])
assert retained.read_bytes() == source.read_bytes()

prepared = cli('--vault', vault, 'candidate', 'prepare', candidate, '--person', person, '--json')
proposal = Path(prepared['path'])
view = cli('--vault', vault, 'candidate', 'review', proposal, '--person', person, '--json')
from helseark.serialization import encode_json
print(encode_json(view).decode())
# Inspect this display AND examples/task5-complete.pdf before answering.
# Tests explicitly supply this synthetic decision; no authenticated human is asserted.
if input('Inspected synthetic identity, both results, source quotes and limitations? Type SYNTHETIC: ') != 'SYNTHETIC':
    raise SystemExit('No decision recorded; inspect and rerun in a new empty directory.')
issues = view['issues']
assert not any(i['severity'] == 'error' for i in issues)
reasons = {
    'PDF_TEXT_REVIEW': 'Inspected supplied synthetic PDF and page text; both rows match this fixture.',
    'SOURCE_IDENTITY_REVIEW': 'Inspected Avery Synthetic cue and explicitly assigned this synthetic fixture.',
    'VALIDATION_NOT_CHECKED': 'Inspected this fixture coverage gap; baseline checks do not prove full FHIR conformance, terminology or extraction accuracy.',
}
# Only explicitly inspected fixture limitations may be acknowledged. Unexpected issues stop.
acks = []
seen = set()
for issue in issues:
    if issue['severity'] in ('review', 'warning'):
        assert issue['code'] in reasons, issue
        assert issue['issueId'] not in seen
        acks.append({'code': issue['code'], 'resourceRef': issue['resourceRef'],
                     'issueId': issue['issueId'], 'reason': reasons[issue['code']]})
        seen.add(issue['issueId'])
decision = root / 'lesson-decision.json'
decision.write_text(json.dumps({'confirmedPerson': True,
    'decision': 'accept-with-acknowledged-limitations' if acks else 'accept',
    'acknowledgedIssues': acks, 'reviewerLabel': 'explicit synthetic test review; unauthenticated'}))
receipt = cli('--vault', vault, 'candidate', 'review', proposal, '--person', person,
              '--decision', decision, '--json')
assert receipt['proposalSha256'] == prepared['proposalSha256']
committed = cli('--vault', vault, 'candidate', 'commit', proposal, '--person', person, '--json')
assert committed['disposition'] == 'committed'
retry = cli('--vault', vault, 'candidate', 'commit', proposal, '--person', person, '--json')
assert retry['disposition'] == 'already-accepted' and retry['head'] == committed['head']
rows = cli('--vault', vault, 'observations', '--person', person, '--json')
assert len(rows) == 2
# Reparse numeric tokens with Decimal: ordinary json.loads would erase scale.
from helseark.serialization import decode_json
raw = subprocess.run([sys.executable, '-m', 'helseark.cli', '--vault', str(vault),
    'observations', '--person', person, '--json'], capture_output=True, check=True).stdout
exact = decode_json(raw)
q = next(r for r in exact if r['code']['text'] == 'Analyte Q')
n = next(r for r in exact if r['code']['text'] == 'Qualitative')
assert str(q['value']['value']) == '0.050'
assert q['value']['comparator'] == '<' and q['value']['unit'] == 'mg/L'
assert q['status'] == n['status'] == 'final'
assert q['effective'] == n['effective'] == '2026-01'
assert q['method'] == {'text': 'M1'}
assert q['referenceRanges'] == [{'text': '0,00 - 0,10 mg/L'}]
assert n['value'] == 'not detected'
assert all(r['sourceRefs'] for r in exact)

def inventory(folder):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob('*') if p.is_file() and
            ('accepted' in p.parts or 'assets' in p.parts)}

before = inventory(vault / 'people')
# Accepted review, evidence, exact revisions and source/extraction receipts are retained.
assert before and len(list((vault / 'people' / person / 'accepted').iterdir())) == 2
for disposable in ('work', 'derived', '.runtime'):
    shutil.rmtree(vault / disposable, ignore_errors=True)
for folder in (vault / 'people').glob('*/work'):
    shutil.rmtree(folder)
health = cli('--vault', vault, 'doctor', '--json')
assert not health['issues'] and health['checkedChanges'] == 2 and health['checkedAssets'] > 0
backup = root / 'lesson-backup'
restored = root / 'lesson-restored'
cli('--vault', vault, 'backup', 'create', '--out', backup, '--json')
verified = cli('backup', 'verify', backup, '--json')
assert not verified['issues'] and verified['checkedResources'] > 2
cli('backup', 'restore', backup, '--into', restored, '--json')
assert inventory(restored / 'people') == before
recovered = cli('--vault', restored, 'observations', '--person', person, '--json')
assert recovered == rows
assert hashlib.sha256(retained.read_bytes()).hexdigest() == intake['source']['sourceSha256']
print('Accepted 2 synthetic observations; exact 0.050, <, mg/L, month, M1, range, final and not detected; identical restored histories and assets.')
```

The final message requires two accepted observations and byte-identical accepted
histories, evidence, source blobs and extraction receipts after a fresh restore.
The second commit must return `already-accepted` with the same Head. Validation's
exit 3 before review is expected; no fatal error is waived. An unexpected limitation
stops the lesson rather than creating a blanket acknowledgment. The script prints
the review view; it never executes source text or calls an internal publisher.

If you stop at the prompt, preserve the vault and inspect it. For a repeat of the
whole lesson choose another empty directory: existing destinations intentionally
fail rather than overwrite. See [backup recovery](../how-to/backup-and-restore.md)
and [CLI errors](../reference/cli.md#errors-and-recovery) for operational failures.

For a genuine external agent, follow [import a report](../how-to/import-report.md).
Its host authorization and output restrictions remain separate from this fixture.
Read [evaluation limits](../explanation/evaluation-and-limits.md) before interpreting
this deterministic roundtrip as evidence about extraction accuracy.
