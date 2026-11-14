# First archive: retain a PDF and validate a draft

This Task5 lesson creates a synthetic identity, retains a synthetic PDF, builds the
actual import handoff and validates the supplied candidate. It needs Python 3.12+,
an installed Helseark distribution with the pinned `pdf` extra, and an empty working
directory. No model account, repository discovery or network is needed after setup.
The supplied candidate is manually authored, not a model result. Nothing clinical
is accepted in this lesson; mandatory human review/publication belongs Task6.

Save the following as `first-intake.py` in an empty directory and run
`python first-intake.py` with the interpreter where Helseark is installed:

```python
from pathlib import Path
from decimal import Decimal
import json
import subprocess
import sys

root = Path.cwd().resolve()
vault = root / 'lesson-vault'
packet = root / 'lesson-packet'
candidate = root / 'lesson-candidate'

def cli(*args, expected=0):
    result = subprocess.run([sys.executable, '-m', 'helseark.cli', *map(str,args)],
                            capture_output=True, text=True)
    if result.returncode != expected:
        raise RuntimeError(result.stderr or result.stdout)
    return json.loads(result.stdout)

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
print('Retained synthetic PDF; validated untrusted draft: <0.050 mg/L. Review required.')
```

You will see the supplied candidate directory and the final message. Validation
returns exit 3 because PDF text and identity uncertainty require human review. The
source and extracted page bytes are retained separately by hash; the existing
identity is still the only accepted change. Open `lesson-packet/ENTRY.md` to see
the real external-agent route. The deterministic candidate binder uses that
packet's actual IDs/receipts and only accepts this one synthetic source.

The draft also preserves the original range text, method M1, month precision and
qualitative result, without inventing a standardized code. These are examples of
fields to inspect beside the original source, not medical interpretation.

This lesson stops at Task5. Candidate preparation, a review view, a bound human
receipt and accepted clinical records depend on Task6 publication. After reviewed
acceptance, use [query accepted history](../how-to/query-history.md); query
commands never read the draft. Backup/restore lessons remain separate.
Never copy candidate files into accepted history. Use [import a report](../how-to/import-report.md)
for a separately run external agent and the [intake reference](../reference/intake.md)
for exact limits. Toolkit tests and supplied examples do not measure model accuracy.

On this lesson's vault, an accepted-only query has no observations:

```sh
helseark --vault lesson-vault observations --person UUID_FROM_LESSON --json
helseark --vault lesson-vault timeline --person UUID_FROM_LESSON --json
```

Expect `[]` from observations and one Patient timeline row in the unknown-time
bucket. This is absence of accepted records, not a negative clinical result.
After Task6 review/acceptance, repeat these commands and follow each row's exact
revision and evidence bindings. Never copy draft files into accepted history.
