"""Exercise the actual synthetic terminology draft, not clinical correctness."""

import csv
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

from jsonschema import Draft6Validator, Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/terminology"
DRAFT = EXAMPLE / "drafts/bilingual-ldl"
PERSON = "44444444-4444-4444-8444-444444444444"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)


class TerminologyExampleTests(unittest.TestCase):
    def setUp(self):
        self.source = EXAMPLE / "sources/laboratory.csv"
        with self.source.open(encoding="utf-8", newline="") as source:
            self.rows = list(csv.DictReader(source))
        self.bundle = read_json(DRAFT / "bundle.fhir.json")
        self.resources = {entry["resource"]["resourceType"] + "/" + entry["resource"]["id"]:
                          entry["resource"] for entry in self.bundle["entry"]}
        self.observations = [r for r in self.resources.values() if r["resourceType"] == "Observation"]
        self.evidence = read_json(DRAFT / "evidence.json")

    def test_actual_bundle_and_each_resource_validate(self):
        schema = read_json(ROOT / "definitions/fhir-r4-json-schema/fhir.schema.json")
        Draft6Validator(schema).validate(self.bundle)
        for resource in self.resources.values():
            Draft6Validator(dict(schema, **{"$ref": "#/definitions/" + resource["resourceType"]})).validate(resource)

    def test_source_evidence_validates_against_existing_contract(self):
        schema = read_json(ROOT / "schemas/0.1.0/evidence.schema.json")
        Draft202012Validator(schema).validate(self.evidence)

    def test_identity_precision_and_raw_context_are_preserved(self):
        self.assertEqual(len(self.rows), 3)
        profile = read_json(EXAMPLE / "profile.fhir.json")
        self.assertEqual(profile, self.resources["Patient/" + PERSON])
        for row, observation in zip(self.rows, self.observations, strict=True):
            self.assertEqual(row["person_id"], PERSON)
            self.assertEqual(row["person_name"], profile["name"][0]["text"])
            self.assertEqual(observation["subject"]["reference"], "urn:uuid:" + PERSON)
            self.assertEqual(observation["code"]["text"], row["test"])
            self.assertEqual(observation["effectiveDateTime"], row["date"])
            self.assertEqual(observation["status"], row["status"])
            quantity = observation["valueQuantity"]
            self.assertIsInstance(quantity["value"], Decimal)
            self.assertEqual(str(quantity["value"]), row["result"].replace(",", "."))
            self.assertEqual(quantity["unit"], row["unit"])
            if row["method"]:
                self.assertEqual(observation["method"], {"text": row["method"]})
                self.assertEqual(observation["specimen"]["display"], row["specimen"])
            else:
                self.assertNotIn("method", observation)
                self.assertNotIn("specimen", observation)
        for resource in self.resources.values():
            if "subject" in resource:
                self.assertEqual(resource["subject"]["reference"], "urn:uuid:" + PERSON)

    def test_bilingual_native_coding_and_uncoded_abstention(self):
        expected = {"system": "http://loinc.org", "version": "2.83", "code": "13457-7",
                    "display": "Cholesterol in LDL [Mass/volume] in Serum or Plasma by calculation"}
        for observation in self.observations[:2]:
            self.assertEqual(observation["code"]["coding"], [expected])
            self.assertEqual(observation["valueQuantity"]["system"], "http://unitsofmeasure.org")
            self.assertEqual(observation["valueQuantity"]["code"], "mg/dL")
        unresolved = self.observations[2]
        self.assertEqual(unresolved["code"], {"text": "LDL"})
        # A coded-only selection must exclude the ambiguous row. No chart is built.
        selected = [o for o in self.observations if any(
            c.get("system") == "http://loinc.org" and c.get("code") == "13457-7"
            for c in o["code"].get("coding", []))]
        self.assertEqual(selected, self.observations[:2])

    def test_source_citations_resolve_exact_cells_and_targets(self):
        self.assertEqual(self.evidence["personId"], PERSON)
        digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        cited = set()
        for entry in self.evidence["entries"]:
            for pointer in entry["target"]["pointers"]:
                value = self.resources[entry["target"]["reference"]]
                for key in pointer.strip("/").split("/"):
                    value = value[int(key)] if isinstance(value, list) else value[key]
                self.assertIsNotNone(value)
            if entry["kind"] != "source":
                self.assertEqual(entry["kind"], "generated")
                continue
            locator = entry["locator"]
            self.assertEqual(entry["sourceSha256"], digest)
            self.assertEqual(entry["quote"], self.rows[locator["row"] - 1][locator["column"]])
            self.assertEqual(locator["kind"], "csv-cell")
            self.assertEqual(locator["delimiter"], ",")
            self.assertIn(entry["sourceDocument"], self.resources)
            expected_pointers = {
                "person_id": {"/identifier/0/value", "/subject/reference"},
                "person_name": {"/name/0/text"}, "test": {"/code/text"},
                "status": {"/status"}, "date": {"/effectiveDateTime"},
                "result": {"/valueQuantity/value"}, "unit": {"/valueQuantity/unit"},
                "method": {"/method/text"}, "specimen": {"/specimen/display"},
            }
            for pointer in entry["target"]["pointers"]:
                self.assertIn(pointer, expected_pointers[locator["column"]])
            if entry["target"]["reference"].startswith("Observation/"):
                self.assertEqual(entry["target"]["reference"], "Observation/" +
                                 self.observations[locator["row"] - 1]["id"])
            cited.add((locator["row"], locator["column"]))
        for number, row in enumerate(self.rows, 1):
            required = {"person_id", "person_name", "test", "date", "result", "unit", "status"}
            if row["method"]:
                required |= {"method", "specimen"}
            self.assertTrue({(number, column) for column in required} <= cited)

    def test_agent_coding_evidence_is_distinct_from_source(self):
        mapping = read_json(DRAFT / "mapping-evidence.json")
        self.assertEqual(mapping["reviewStatus"], "unreviewed")
        self.assertEqual(mapping["catalog"]["version"], "2.83")
        self.assertEqual(mapping["catalog"]["reference"], "https://loinc.org/13457-7/")
        self.assertEqual(len(mapping["decisions"]), 3)
        for row, decision in zip(self.rows, mapping["decisions"], strict=True):
            self.assertEqual(decision["sourceCoding"], [])
            self.assertEqual(decision["sourceLabel"], row["test"])
            if decision["agentAssignedCoding"]:
                self.assertEqual(decision["agentAssignedCoding"][0]["code"], "13457-7")
                self.assertTrue(decision["rationale"])
                self.assertEqual(set(decision["axisEvidence"]), {"component", "property", "time", "system", "scale", "method"})
                for citation in decision["axisEvidence"].values():
                    self.assertEqual(citation["quote"], row[citation["column"]])
            else:
                self.assertEqual(decision["outcome"], "unresolved")

    def test_retained_source_survives_relocation_without_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            shutil.copytree(EXAMPLE / "sources", root / "sources")
            for stage in ("drafts", "records"):
                destination = root / stage / "bilingual-ldl"
                shutil.copytree(DRAFT, destination)
                bundle = read_json(destination / "bundle.fhir.json")
                document = next(e["resource"] for e in bundle["entry"]
                                if e["resource"]["resourceType"] == "DocumentReference")
                source = destination / document["content"][0]["attachment"]["url"]
                self.assertEqual(source.resolve(), root / "sources/laboratory.csv")
                self.assertEqual(source.read_bytes(), self.source.read_bytes())
                self.assertEqual((destination / "bundle.fhir.json").read_bytes(),
                                 (DRAFT / "bundle.fhir.json").read_bytes())

    def test_local_helper_checks_proposals_and_rejects_conflicting_axes(self):
        spec = importlib.util.spec_from_file_location(
            "example_terminology", ROOT / "skills/helseark/scripts/terminology.py")
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        retained = (DRAFT / "bundle.fhir.json").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory).resolve()
            archive = folder / "synthetic.zip"
            with zipfile.ZipFile(archive, "w") as target:
                for source in sorted((EXAMPLE / "mini-catalog").rglob("*.csv")):
                    target.write(source, source.relative_to(EXAMPLE / "mini-catalog"))
            package = folder / "package"
            helper.install(archive, "2.83", EXAMPLE / "mini-catalog/ucum-essence.xml", package)
            for number, observation in enumerate(self.observations[:2], 1):
                observation_path = folder / "observation.json"
                # The retained source supplied no codes; remove only the explicitly
                # agent-assigned additions to exercise the proposal boundary.
                original = json.loads(json.dumps(observation, default=str))
                original["code"].pop("coding")
                original["valueQuantity"].pop("system")
                original["valueQuantity"].pop("code")
                # Restore the JSON number token exactly; JSON's default encoder
                # does not support Decimal and binary float is not appropriate.
                token = str(observation["valueQuantity"]["value"])
                observation_path.write_text(json.dumps(original).replace(
                    '"value": ' + json.dumps(token), '"value": ' + token))
                self.assertIsInstance(read_json(observation_path)["valueQuantity"]["value"], Decimal)
                proposal_path = DRAFT / f"mapping-proposal-{number}.json"
                result = helper.check(package, observation_path, proposal_path)
                self.assertEqual(result["issues"], [])
                self.assertEqual(result["source_codings"], [])
                self.assertEqual(result["decision"], "human_review_required")
                self.assertEqual(result["rule_reuse"], "not_requested")
                self.assertEqual(result["proposed_additions"]["code.coding"], observation["code"]["coding"][0])
                self.assertEqual(result["unit"]["status"], "valid_syntax")
                for axis, conflict in (("component", "Cholesterol.in VLDL"),
                                       ("property", "MRto"),
                                       ("system", "Urine"), ("method", "Direct")):
                    with self.subTest(row=number, axis=axis):
                        proposal = read_json(proposal_path)
                        proposal["context"][axis] = conflict
                        negative = folder / "negative.json"
                        negative.write_text(json.dumps(proposal))
                        rejected = helper.check(package, observation_path, negative)
                        self.assertIn("incompatible: " + axis + " contradicts LOINC axis", rejected["issues"])
                unresolved = folder / "unresolved.json"
                proposal = read_json(proposal_path)
                for axis in ("system", "method"):
                    proposal["context"].pop(axis)
                    proposal["evidence"].pop(axis)
                unresolved.write_text(json.dumps(proposal))
                result = helper.check(package, observation_path, unresolved)
                self.assertIn("unresolved: missing system context", result["issues"])
                self.assertIn("unresolved: missing method context", result["issues"])
            ambiguous_path = folder / "ambiguous-observation.json"
            ambiguous_path.write_text(json.dumps(self.observations[2], default=str).replace(
                '"value": "105.0"', '"value": 105.0'))
            result = helper.check(package, ambiguous_path, unresolved)
            self.assertEqual(result["source_codings"], [])
            self.assertIn("unresolved: missing system context", result["issues"])
            self.assertIn("unresolved: missing method context", result["issues"])
        self.assertEqual((DRAFT / "bundle.fhir.json").read_bytes(), retained)


if __name__ == "__main__":
    unittest.main()
