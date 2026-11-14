"""Bind ONLY the supplied synthetic candidate to a real Task5 packet. No extraction.

Run: python task5-example.py PACKET NEW_CANDIDATE_DIRECTORY
The manually authored oracle is maintained independently under tests/fixtures.
"""
from pathlib import Path
import sys
from helseark.serialization import decode_json, encode_json, hash_bytes
from helseark.intake import _new_directory, _regular, CANDIDATE_FILE_BYTES

packet, destination = map(Path, sys.argv[1:])
meta = decode_json(_regular(packet/'intake.json', CANDIDATE_FILE_BYTES))
source = meta['source']
example = Path(__file__).parent
if source['sourceSha256'] != hash_bytes((example/'task5-complete.pdf').read_bytes()):
    raise SystemExit('This supplied candidate is only for task5-complete.pdf.')
if not meta['identityConfirmed']:
    raise SystemExit('Explicit synthetic person assignment is required.')
context = decode_json(_regular(packet/'context/context.json', CANDIDATE_FILE_BYTES))
replacements = {'11111111-1111-4111-8111-111111111111': meta['personId'],
                'SOURCE_HASH': source['sourceSha256'], 'EXTRACTION_HASH': meta['extraction']['pagesSha256']}
def bound(name):
    data = (example/name).read_bytes()
    for key,value in replacements.items(): data=data.replace(key.encode(),value.encode())
    return decode_json(data)
bundle = bound('task5-bundle.json')
evidence = bound('task5-evidence.json')
manifest_bytes = _regular(Path(context['kitManifest']['path']), CANDIDATE_FILE_BYTES)
if hash_bytes(manifest_bytes) != context['kitManifest']['sha256']:
    raise SystemExit('Pinned synthetic example kit manifest differs.')
pins = decode_json(manifest_bytes)['compatibility']
candidate = {'contractVersion':pins['contractVersion'],'fhirVersion':pins['fhirVersion'],'profileVersion':pins['profileVersion'],
    'candidateId':meta['importId'],'personId':meta['personId'],
    'baseChangeSha256':context['base']['changeSha256'], 'sourceSha256':[source['sourceSha256']],
    'bundlePath':'bundle.json','evidencePath':'evidence.json',
    'producer':{'kind':'local-user','name':'pre-authored synthetic example'},
    'producerProvenance':evidence['producerProvenance'], 'unresolved':meta['issues']}
_new_directory(destination.absolute())
for name,value in [('candidate.json',candidate),('bundle.json',bundle),('evidence.json',evidence)]:
    with (destination/name).open('xb') as output: output.write(encode_json(value))
print(destination)
