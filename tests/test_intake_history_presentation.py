"""Issued native history and mapped CSV on the current clinical foundation."""
import csv
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

import pytest
from helseark.archive import init_vault, add_person, commit_candidate, doctor, head
from helseark.contracts import PersonDraft, ArchiveError, ObservationFilter
from helseark.adapters.fhir_r4 import import_fhir_r4, IdentityMapping
from helseark.adapters.csv_metrics import import_metrics_csv
from helseark.intake import add_source, prepare_candidate, read_candidate
from helseark.query import history, observations
from helseark.presentation import render_static_report
from helseark.portability import backup, restore, verify_export
from helseark.serialization import decode_json, encode_json, hash_bytes
from test_adapters import decision, csv_mapping
from test_clinical_history_oracle import assert_facts

FIXTURES = Path(__file__).parent/'fixtures/synthetic'


def test_issued_eight_family_csv_history_report_and_restore(tmp_path):
    vault = init_vault(tmp_path/'vault')
    person = add_person(vault, PersonDraft('Synthetic union patient'))
    other = add_person(vault, PersonDraft('Synthetic union patient', note='PRIVATE_OTHER_PERSON'))
    raw = (FIXTURES/'clinical-history/oracle/candidate-resources.json').read_bytes().replace(b'PERSON', b'p1')
    records = decode_json(raw)
    for r in records:
        r['id'] = r['resourceType'].lower()
    # Native URI named reference must remain literal; order/use is a real Reference.
    vaccine = next(r for r in records if r['resourceType']=='Immunization')
    vaccine['education'] = [{'reference':'urn:uuid:immunization'}]
    use = next(r for r in records if r['resourceType']=='MedicationStatement')
    use['derivedFrom'] = [{'reference':'MedicationRequest/medicationrequest'}]
    incoming = {'resourceType':'Bundle','type':'collection','entry':[
        {'resource':{'resourceType':'Patient','id':'p1','name':[{'text':'Synthetic union patient'}]}},
        *[{'resource':r} for r in records]]}
    source = tmp_path/'native.json'; source.write_bytes(encode_json(incoming))
    receipt = add_source(vault,person,source)
    candidate = import_fhir_r4(receipt,person,IdentityMapping('Patient/p1',person,'Explicit synthetic assignment','https://synthetic.example/fhir'))
    assert_facts([e['resource'] for e in candidate.bundle['entry']])
    proposal = prepare_candidate(vault,candidate)
    with pytest.raises(ArchiveError, match='REVIEW_REQUIRED'):
        commit_candidate(vault,proposal,None)
    committed = commit_candidate(vault,proposal,decision(vault,proposal))
    assert commit_candidate(vault,proposal,decision_receipt(vault,proposal)).disposition=='already-accepted'
    kinds = [r['resourceType'] for r in records]
    accepted = list(history(vault,person,kinds))
    assert_facts(accepted)
    assert next(r for r in accepted if r['resourceType']=='Immunization')['education'][0]['reference']=='urn:uuid:immunization'
    assert '/_history/' in next(r for r in accepted if r['resourceType']=='MedicationStatement')['derivedFrom'][0]['reference']
    earlier = head(vault,person)
    metrics = add_source(vault,person,FIXTURES/'structured/metrics.csv')
    mapped = import_metrics_csv(metrics,person,csv_mapping(person))
    p = prepare_candidate(vault,mapped); commit_candidate(vault,p,decision(vault,p))
    assert list(observations(vault,person,ObservationFilter(),at=earlier))==[]
    rows = list(observations(vault,person,ObservationFilter()))
    assert len(rows)==3 and sum(str(r.value.get('value'))=='0.0500' for r in rows)==2
    assert not list(history(vault,other,kinds))
    # Canonical source issuance is retained in backup closure, never unknown debris.
    assert not doctor(vault).issues
    saved = {str(p.relative_to(vault.root)):hash_bytes(p.read_bytes())
             for p in (vault.root/'people').rglob('*') if p.is_file() and '/work/' not in str(p)}
    dest=tmp_path/'report';render_static_report(vault,person,dest)
    svg=ET.fromstring((dest/'report.svg').read_bytes())
    text=''.join(svg.itertext())
    for value in ('1.250','2.500','0.500','45.00','false','Possibly childhood','cancelled','unconfirmed'):
        assert value in text
    assert 'PRIVATE_OTHER_PERSON' not in text
    links=svg.findall('.//{http://www.w3.org/2000/svg}a')
    assert links and all('/accepted/' in a.attrib['href'] and '#/entries/' in a.attrib['href'] for a in links)
    assert not svg.findall('.//{http://www.w3.org/2000/svg}script')
    assert len(list(csv.DictReader((dest/'observations.csv').open())))==3
    before={p.name:p.read_bytes() for p in dest.iterdir()}
    shutil.rmtree(dest);render_static_report(vault,person,dest)
    assert before=={p.name:p.read_bytes() for p in dest.iterdir()}
    for path,digest in saved.items():assert hash_bytes((vault.root/path).read_bytes())==digest
    copied=tmp_path/'backup';backup(vault,copied)
    assert not verify_export(copied).issues
    recovered=restore(copied,tmp_path/'restored')
    assert_facts(list(history(recovered,person,kinds)))
    assert not doctor(recovered).issues
    for path,digest in saved.items():assert hash_bytes((recovered.root/path).read_bytes())==digest
    # Resumable issuance is optional after acceptance, never reconstructed.
    issuance_files=list((recovered.root/'people'/person/'assets').glob('sha256/*/structured/*.json'))
    assert len(issuance_files)==2
    for path in issuance_files:path.unlink()
    assert_facts(list(history(recovered,person,kinds)))
    assert not doctor(recovered).issues


def decision_receipt(vault, proposal):
    from helseark.review import read_receipt
    return read_receipt(vault,proposal)
