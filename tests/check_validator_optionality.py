"""Base-only runtime drill: explicitly absent Java never blocks baseline use."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from helseark.archive import init_vault, add_person, resolve
from helseark.contracts import PersonDraft, ResourceRef, ArchiveError
from helseark.fhir_validator import validate_with_official_tool

os.environ['PATH']='/nonexistent'
with TemporaryDirectory() as temporary:
    vault=init_vault(Path(temporary)/'vault')
    person=add_person(vault,PersonDraft('Synthetic base-only person'))
    patient=resolve(vault,person,ResourceRef('Patient',person))
    assert patient['resourceType']=='Patient'
    try: validate_with_official_tool(None,None,vault=vault)
    except ArchiveError as error: assert error.code=='INVALID_INPUT'
    else: raise AssertionError('Invalid explicit request did not block')
print('base without Java: 1 Patient resolved; invalid explicit request blocked')
