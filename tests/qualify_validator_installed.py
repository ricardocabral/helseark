"""Run from outside the checkout using the exact installed wheel interpreter."""
from pathlib import Path
import importlib.metadata
import sysconfig
import helseark.fhir_validator as tool
from helseark.contracts import ValidatorConfig
from helseark.cli import main

root=Path(sysconfig.get_path('data'))/'share/helseark'
module=Path(tool.__file__).resolve()
assert 'site-packages' in str(module),module
assert len(tool._lock()['packages'])==9
for name in ['definitions/validator-lock.json','definitions/validator-notices.json',
             'docs/how-to/run-offline-validator.md','NOTICE']:
    assert (root/name).is_file(),name
assert len(list((root/'profiles/r4/0.1.0').glob('StructureDefinition-*.json')))==6
assert main(['validate','proposal','/absent','--person','11111111-1111-4111-8111-111111111111','--require-official','--json'])==6
print('installed closure:',importlib.metadata.version('helseark'),'; 9 package pins; 6 profiles; optional adapter/config/CLI/assets present')
