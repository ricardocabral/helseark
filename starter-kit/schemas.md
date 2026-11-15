# Existing data schema references

Clinical data uses **FHIR R4 4.0.1**, with native Patient, Observation and
DocumentReference resources in the [example Bundle](examples/bundle.fhir.json).
Readable citation/review notes are supporting material, not another clinical store.

| Existing asset | Use and limits |
| --- | --- |
| [Upstream FHIR JSON Schema](../definitions/fhir-r4-json-schema/fhir.schema.json) | Draft-06 structural schema for R4 resources; contains its definitions in one file |
| [Evidence schema](../schemas/0.1.0/evidence.schema.json) | Optional Draft 2020-12 citation envelope; the complete example uses existing source and generated entry types |
| [Local profiles](../profiles/r4/0.1.0/README.md) | Optional experimental archive constraints, including profile declarations and content-addressed attachment paths; not claimed by this portable example |
| [Clinical model](../docs/reference/clinical-model.md) | Deeper reference for the optional archive runtime and its stricter graph/evidence rules |
| [Definition provenance and terms](../definitions/README.md) | Origin and licensing of reused upstream assets |

In this example `valueQuantity.value` is a JSON number with token `0.050`,
`comparator` is `<`, `unit` is source text `mg/L`, and `effectiveDateTime` is
`2026-02`. `code.text` retains the lab label without inventing LOINC or UCUM codes.
The source's uncertainty is preserved in `Observation.note`. Human acceptance is
recorded separately from the source-reported `Observation.status`.

Evidence has one explicit `personId`. Source entries identify target resource and
FHIR pointers, original source digest, DocumentReference, quote and CSV row/column.
Generated entries label assigned IDs and file bookkeeping. This uses the existing
schema unchanged. The example's source digest is supplied; prompts can instead
produce readable field citations without any hash or archive setup.

## Optional structural validation

If Python and the repository's existing `jsonschema` dependency are already
available, run the following from the repository root. Nothing is installed,
written, fetched, or initialized. This command also works with the reduced copy
scope described in the quickstart. It validates both the Bundle and each resource
explicitly, plus the evidence envelope, while reading decimal values exactly.

```sh
python3 - <<'PY'
from decimal import Decimal
import json
from pathlib import Path
from jsonschema import Draft6Validator, Draft202012Validator

def read(path):
    return json.loads(Path(path).read_text(), parse_float=Decimal)

schema = read('definitions/fhir-r4-json-schema/fhir.schema.json')
bundle = read('starter-kit/examples/bundle.fhir.json')
Draft6Validator(schema).validate(bundle)
for entry in bundle['entry']:
    resource = entry['resource']
    specific = dict(schema, **{'$ref': '#/definitions/' + resource['resourceType']})
    Draft6Validator(specific).validate(resource)
Draft202012Validator(read('schemas/0.1.0/evidence.schema.json')).validate(
    read('starter-kit/examples/evidence.json'))
value = bundle['entry'][1]['resource']['valueQuantity']['value']
assert str(value) == '0.050'
print('Bundle, 3 resources and evidence structurally valid; decimal scale retained.')
PY
```

This check does **not** validate local profile/FHIRPath invariants, terminology,
reference resolution, evidence accuracy, clinical truth, source authenticity,
or human approval. In particular, schema validation alone may accept a wrong
person, changed comparator or inaccurate citation. Compare the [source and review
checklist](examples/README.md) manually before accepting any real record. The
starter kit does not implement validators, review enforcement or archive storage.
