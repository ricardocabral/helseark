"""Offline installed public CLI integration oracle; synthetic decisions, agentRuns=0.

Copy outside checkout. Run with installed Python: SCRIPT FRESH_ROOT DENIED_CHECKOUT
NATIVE_REPORT_FIXTURE [--portability]. No private publication API or model is used.
"""
from pathlib import Path
from copy import deepcopy
from decimal import Decimal
import json
import os
import shutil
import subprocess
import sys

from helseark.serialization import decode_json as dec, encode_json as enc, hash_bytes
import helseark
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject

root, checkout, report_fixture = map(lambda s: Path(s).resolve(), sys.argv[1:4])
root.mkdir()
assert not Path(helseark.__file__).resolve().is_relative_to(checkout)
console = Path(sys.executable).parent / 'helseark'
vault = root / 'vault'
env = {**os.environ}
env.pop('PYTHONPATH', None)

def cli(*args, exit_code=0):
    result = subprocess.run([str(console), *map(str, args), '--json'],
                            cwd=root, env=env, capture_output=True)
    assert result.returncode == exit_code, (args, result.stderr)
    assert b'Traceback' not in result.stderr
    return dec(result.stdout if result.stdout else result.stderr)

cli('init', vault)
person = cli('--vault', vault, 'person', 'add', '--name', 'Avery Synthetic')['personId']
other = cli('--vault', vault, 'person', 'add', '--name', 'UNSELECTED SYNTHETIC')['personId']
kit = next((vault / 'agent-kit').iterdir())
# Real original PDF plus an explicitly labeled alternate assertion for a later
# synthetic correction. The source oracle is specified here, not inferred by a model.
writer = PdfWriter(clone_from=PdfReader(kit / 'examples/task5-complete.pdf'))
stream = DecodedStreamObject()
stream.set_data(writer.pages[0].get_contents().get_data() +
               b'\nBT /F1 10 Tf 40 40 Td (Correction: <0,0750 mg/L) Tj ET\n')
writer.pages[0][NameObject('/Contents')] = stream
source = root / 'synthetic.pdf'
writer.write(source)
# Make independent source hashes/read-denial witnesses before restricting child CLI.
other_file = next((vault / 'people' / other / 'accepted').glob('*/resources/*.json'))
other_original = other_file.read_bytes()
other_file.write_bytes(b'UNSELECTED CORRUPTION')
guard = root / 'guard'
guard.mkdir()
(guard / 'sitecustomize.py').write_text('''
import os,sys
def audit(event,args):
    blocked = event.startswith(('socket.','urllib.'))
    if event in ('open','os.scandir','os.listdir'):
        value=str(args[0])
        blocked |= any(value.startswith(os.environ[k]) for k in ('DENY_CHECKOUT','DENY_OTHER'))
    if blocked:
        with open(os.environ['DENY_EVENTS'],'a') as f:f.write(event+'\\n')
        raise RuntimeError('integration oracle denied access')
sys.addaudithook(audit)
''')
events = root / 'denials.log'
env.update(PYTHONPATH=str(guard), DENY_CHECKOUT=str(checkout),
           DENY_OTHER=str(vault / 'people' / other), DENY_EVENTS=str(events))
for code in ('import socket;socket.socket()',
             f'open({str(checkout / "pyproject.toml")!r})',
             f'open({str(other_file)!r})'):
    witness = subprocess.run([sys.executable, '-c', code], cwd=root, env=env, capture_output=True)
    assert witness.returncode != 0 and b'integration oracle denied access' in witness.stderr
assert len(events.read_text().splitlines()) == 3
events.unlink()

def command(*args, **kw):
    return cli('--vault', vault, *args, '--person', person, **kw)

packet = root / 'packet'
packet_result = command('intake', 'add', source, '--packet', packet, '--confirm-person')
intake = dec((packet/'intake.json').read_bytes())
context = dec((packet / 'context/context.json').read_bytes())
assert hash_bytes((packet / 'context/context.json').read_bytes()) == packet_result['trustedContextSha256']
extraction = intake['extraction']
assert hash_bytes(source.read_bytes()) == intake['source']['sourceSha256']
prompt = (packet / 'prompt.txt').read_text()
header = json.JSONDecoder().raw_decode(prompt.split('\n', 1)[1])[0]
source_data = dec(prompt.split('<SOURCE_DATA_JSON>\n')[1].split('\n</SOURCE_DATA_JSON>')[0].encode())
readable = [f for f in header['readableFiles'] if f['path'] == source_data['extractionPath']]
assert len(readable) == 1
raw = Path(readable[0]['path']).read_bytes()
assert hash_bytes(raw) == readable[0]['sha256'] == extraction['pagesSha256']
assert len(raw) == readable[0]['size']
assert context['dataBytes'] == context['identity']['size'] + len(raw)
assert header['handoffDataBytes'] == header['contextDataBytes'] + header['inlineDataBytes'] <= header['maxDataBytes']
assert other not in prompt and 'UNSELECTED' not in prompt

candidate = root / 'candidate'
candidate.mkdir()
replacements = {'11111111-1111-4111-8111-111111111111': person,
                'SOURCE_HASH': intake['source']['sourceSha256'], 'EXTRACTION_HASH': extraction['pagesSha256']}
for filename in ('bundle.json', 'evidence.json'):
    data = (kit / 'examples' / ('task5-' + filename)).read_bytes()
    for old, new in replacements.items():
        data = data.replace(old.encode(), new.encode())
    (candidate / filename).write_bytes(data)
bundle = dec((candidate / 'bundle.json').read_bytes())
evidence = dec((candidate / 'evidence.json').read_bytes())
report = dec(report_fixture.read_bytes().replace(b'PERSON', person.encode()))
report_ref = 'urn:uuid:' + report['id']
bundle['entry'].append({'fullUrl': report_ref, 'resource': report})
for pointer, quote in [('/status','Status: final'),('/code/text','Report: Synthetic laboratory report'),
    ('/subject/reference','Patient: Avery Synthetic'),('/effectiveDateTime','Collected: 2026-01'),
    ('/result/0/reference','Analyte Q: <0,050 mg/L'),('/result/1/reference','Qualitative: not detected')]:
    entry = deepcopy(next(e for e in evidence['entries'] if e['kind'] == 'source'))
    entry.update(target={'reference':report_ref,'pointers':[pointer]}, quote=quote)
    evidence['entries'].append(entry)
evidence['entries'].append({'target':{'reference':report_ref,'pointers':['/id','/meta/profile/0']},
                            'kind':'generated','rule':'synthetic-native-report-1'})
metadata = dict(contractVersion='0.1.0', fhirVersion='4.0.1', profileVersion='0.1.0',
    candidateId=intake['importId'], personId=person, baseChangeSha256=context['base']['changeSha256'],
    sourceSha256=[intake['source']['sourceSha256']], bundlePath='bundle.json', evidencePath='evidence.json',
    producer={'kind':'local-user','name':'explicit synthetic integration oracle; agentRuns=0'},
    producerProvenance=evidence['producerProvenance'], unresolved=intake['issues'])

def save_candidate():
    for name, data in [('candidate',metadata),('bundle',bundle),('evidence',evidence)]:
        (candidate / (name + '.json')).write_bytes(enc(data))

def publish(path):
    view = command('candidate', 'review', path)
    issues = [i for i in view['issues'] if i['severity'] in ('review','warning')]
    assert issues and len({i['issueId'] for i in issues}) == len(issues)
    decision = root / (Path(path).name + '-synthetic-decision.json')
    decision.write_bytes(enc(dict(confirmedPerson=True, decision='accept-with-acknowledged-limitations',
        reviewerLabel='synthetic CLI oracle; no clinical approval', acknowledgedIssues=[dict(
            code=i['code'], resourceRef=i['resourceRef'], issueId=i['issueId'],
            reason='Individually inspected synthetic limitation ' + i['issueId']) for i in issues])))
    command('candidate','review',path,'--decision',decision)
    assert dec((Path(path) / 'review.json').read_bytes())['contractVersion'] == '0.1.1'
    return command('candidate','commit',path), view, len(issues)

save_candidate()
validation = command('validate','candidate',candidate,exit_code=3)
assert not any(i['severity']=='error' for i in validation['issues'])
assert any(i['severity'] in ('review','warning') for i in validation['issues'])
prepared = command('candidate','prepare',candidate)
first, first_view, acknowledgments = publish(prepared['path'])
assert first['head']['sequence'] == 2
head_file = root / 'old-head.json'
head_file.write_bytes(enc(first['head']))
accepted = vault / 'people' / person / 'accepted'
originals = {str(p.relative_to(vault)): hash_bytes(p.read_bytes()) for p in accepted.rglob('*') if p.is_file()}
receipts = {str(p.relative_to(vault)): hash_bytes(p.read_bytes()) for p in (vault/'people'/person/'assets').rglob('*.json')}
rows = command('observations')
assert len(rows) == 2
quantity = next(r for r in rows if r['comparator'] == '<')
assert str(quantity['value']['value']) == '0.050' and quantity['value']['value'].as_tuple().exponent == -3
assert quantity['effective'] == '2026-01' and quantity['timePrecision'] == 'month'
assert quantity['status'] == 'final' and quantity['unit'] == 'mg/L'
assert quantity['method'] == {'text':'M1'} and quantity['referenceRanges'] == [{'text':'0,00 - 0,10 mg/L'}]
assert next(r for r in rows if r['comparator'] is None)['value'] == 'not detected'
assert all(r['sourceRefs'] for r in rows)
for row in rows:
    for binding in row['sourceRefs']:
        payload = (vault / binding['evidencePath']).read_bytes()
        assert hash_bytes(payload) == binding['evidenceSha256']
        entry = dec(payload)['entries'][int(binding['entryPointer'].split('/')[-1])]
        ref = row['resourceRef']
        assert entry['target']['reference'] == f"Observation/{ref['id']}/_history/{ref['versionId']}"
        if binding['sourceSha256']:
            assert entry['quote'] and entry['locator']
            assert hash_bytes((vault/'people'/person/'assets/sha256'/binding['sourceSha256']/'blob').read_bytes()) == binding['sourceSha256']
# Same retained source, explicit human re-extraction corrects one assertion. Omitted
# report/qualitative assertion remain accepted, and report must keep its old child.
qurn = bundle['entry'][0]['fullUrl']
bundle['entry'] = [bundle['entry'][0], bundle['entry'][2]]
bundle['entry'][0]['resource']['valueQuantity']['value'] = Decimal('0.0750')
evidence['entries'] = [e for e in evidence['entries'] if e['target']['reference'] in {qurn,bundle['entry'][1]['fullUrl']}]
for e in evidence['entries']:
    if e.get('quote') == '<0,050 mg/L':
        e['quote'] = '<0,0750 mg/L'
metadata['baseChangeSha256'] = first['head']['changeSha256']
save_candidate()
assert command('candidate','prepare',candidate,exit_code=3)['code'] == 'REEXTRACTION_REQUIRED'
mapping = root/'mapping.json'
mapping.write_bytes(enc({qurn:'Observation/'+quantity['resourceRef']['id']}))
second_p = command('candidate','prepare',candidate,'--reextract','--reconciliation',mapping)
second, second_view, second_acks = publish(second_p['path'])
assert second['head']['sequence'] == 3
assert len(second_view['omittedResources']) == 2
assert all(x['previousEvidence'] for x in second_view['revisionsChanged'])
current = command('observations')
assert len(current) == 2
assert str(next(r for r in current if r['comparator']=='<')['value']['value']) == '0.0750'
old_rows = command('observations','--at-head',head_file)
assert str(next(r for r in old_rows if r['comparator']=='<')['value']['value']) == '0.050'
timeline = command('timeline')
old_report = next(r for r in timeline if r['resourceRef']['resourceType']=='DiagnosticReport')
assert 'REPORT_RESULT_REVISION_MISMATCH' in {i['code'] for i in old_report['issues']}
child = old_report['resultRefs'][0]
exact = f"Observation/{child['id']}/_history/{child['versionId']}"
assert str(command('record','--resource',exact)['valueQuantity']['value']) == '0.050'
filtered = command('observations','--from-date','2026-01-14','--to-date','2026-01-14')
assert len(filtered) == 2 and all(r['timeFilterRelation']=='overlap' for r in filtered)
assert command('observations','--from-date','2026-01-14T00:00:00+00:60',exit_code=2)['code']=='INVALID_FILTER'
# All original accepted/history/source/extraction receipts remain exact bytes.
for name, digest in {**originals, **receipts}.items():
    assert hash_bytes((vault/name).read_bytes()) == digest
shutil.rmtree(vault/'work')
shutil.rmtree(vault/'.runtime')
shutil.rmtree(candidate)
shutil.rmtree(packet)
path = next(p for p in accepted.iterdir() if p.name.endswith(second['head']['transactionId']))
assert command('candidate','commit',path)['disposition']=='already-accepted'
assert len(list(accepted.iterdir())) == 3 and len(command('observations')) == 2
assert command('candidate','review',path)['omittedResources']
assert not events.exists(), events.read_text() if events.exists() else ''
print(json.dumps(dict(agentRuns=0, publicCli=True, observedRows=2, transactions=3,
    oldValue='0.050', currentValue='0.0750', pinnedReportChild='0.050',
    acknowledgedLimitations=[acknowledgments,second_acks], originalAcceptedFiles=len(originals),
    originalReceipts=len(receipts), denialWitnesses=3, forbiddenAttempts=0,
    extractionReceipt=True, exactCitations=True, idempotentAfterRemoval=True)), flush=True)

if sys.argv[4:] == ['--portability']:
    # Household audit needs both people. Restore only this oracle's deliberate
    # corruption and remove its other-person denial after scoped checks passed.
    other_file.write_bytes(other_original)
    env['DENY_OTHER'] = str(root/'never-read-other-witness')
    before = {str(p.relative_to(vault)):hash_bytes(p.read_bytes())
              for p in (vault/'people').rglob('*') if p.is_file()}
    backup = root/'backup'
    cli('--vault',vault,'backup','create','--out',backup)
    verified = cli('backup','verify',backup)
    assert not verified['issues']
    assert (verified['checkedChanges'],verified['checkedResources'],verified['checkedAssets']) == (4,10,2)
    restored = root/'restored'
    cli('backup','restore',backup,'--into',restored)
    for name in ('work','derived','.runtime'):
        shutil.rmtree(restored/name,ignore_errors=True)
    report = cli('--vault',restored,'doctor')
    assert report == verified
    after = {str(p.relative_to(restored)):hash_bytes(p.read_bytes())
             for p in (restored/'people').rglob('*') if p.is_file()}
    assert before == after
    assert cli('--vault',restored,'observations','--person',person) == current
    assert cli('--vault',restored,'observations','--person',person,'--at-head',head_file) == old_rows
    assert cli('--vault',restored,'record','--person',person,'--resource',exact)['valueQuantity']['value'] == Decimal('0.050')
    for name,digest in {**originals,**receipts}.items():
        assert hash_bytes((restored/name).read_bytes()) == digest
    selected = root/'selected'
    cli('--vault',restored,'export','--person',person,'--mode','selected-current','--no-sources','--out',selected)
    selected_report = cli('backup','verify',selected)
    assert not selected_report['issues'] and selected_report['checkedResources'] == 9
    assert not (selected/'sources').exists()
    assert all(other.encode() not in p.read_bytes() and b'UNSELECTED SYNTHETIC' not in p.read_bytes()
               for p in selected.rglob('*') if p.is_file())
    cli('--vault',restored,'export','--person',person,'--out',root/'blocked-pdf',exit_code=3)
    assert not (root/'blocked-pdf').exists()
    assert not events.exists()
    print(json.dumps(dict(portability=True, people=2, changes=4, revisions=10, blobs=2,
        equalPersonFiles=len(before), observations=2, selectedRevisions=9,
        otherPersonLeaks=0, forbiddenAttempts=0, oldPinsPreserved=True)),flush=True)
