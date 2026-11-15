# Read your first cited record

Learn to trace a draft and an answer to their source. You need only a text editor
or browser. All people and results in this lesson are invented.

## 1. Read the source

Open [source.csv](examples/source.csv). It contains one data row for Alex Example,
person `11111111-1111-4111-8111-111111111111`.

Find `<0,050 mg/L` in `result` and `2026-02` in `effective_date`.
The uncertainty column says the day and time are absent. The result is below the
reporting limit, not an exact concentration.

## 2. Check the draft

Open [bundle.fhir.json](examples/bundle.fhir.json) as text. Find its Patient,
Observation and DocumentReference resources. Both subject references identify Alex.
The DocumentReference points to `source.csv`.

Find these Observation fields:

```json
"effectiveDateTime": "2026-02",
"valueQuantity": {
  "value": 0.050,
  "comparator": "<",
  "unit": "mg/L"
}
```

The decimal comma became a point. The three decimal places, bound, unit and month
precision remain. Use the raw file view if a JSON viewer displays `0.05`.
The lab status `final` does not mean human approval.

## 3. Follow a citation

Open [evidence.json](examples/evidence.json). Find the source entry whose
`target.pointers` contains `/valueQuantity/value`. Its quote is `<0,050 mg/L`.
Its locator identifies data row 1, column `result`. Check the quote against the CSV.

Find the date and subject citations too. Entries labeled `generated` describe
bookkeeping. You can use readable citations instead of this optional JSON format.

## 4. Check an answer

Ask: “What C-reactive protein result is supplied for Alex in February 2026?”
The answer is one source-reported final observation: **<0.050 mg/L**, dated
**2026-02**, with day and time unknown. It is not an exact concentration.

Check this answer against `source.csv`, data row 1, columns `test`, `status`,
`result`, `effective_date` and `uncertainty`. The matching record is Observation
`22222222-2222-4222-8222-222222222222` in `bundle.fhir.json`.
See the [annotated example](examples/README.md) for its field mapping.

Leave the supplied files unchanged and unreviewed. To use your own files, follow
the [task guide](how-to.md), including its human review step.
