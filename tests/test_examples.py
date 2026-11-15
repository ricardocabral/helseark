"""Checks for the fixed invented health record example, not a clinical validator."""

import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from jsonschema import Draft6Validator, Draft202012Validator, ValidationError


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
DRAFT = EXAMPLES / "drafts" / "first-import"
SOURCE = EXAMPLES / "sources" / "source.csv"
PERSON = "11111111-1111-4111-8111-111111111111"
PATIENT = f"Patient/{PERSON}"
OBSERVATION = "Observation/22222222-2222-4222-8222-222222222222"
DOCUMENT = "DocumentReference/33333333-3333-4333-8333-333333333333"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)


class HealthExampleTests(unittest.TestCase):
    def setUp(self):
        with SOURCE.open(encoding="utf-8", newline="") as source:
            self.rows = list(csv.DictReader(source))
        self.bundle = read_json(DRAFT / "bundle.fhir.json")
        self.evidence = read_json(DRAFT / "evidence.json")
        self.resources = {}
        for entry in self.bundle["entry"]:
            resource = entry["resource"]
            self.resources[resource["resourceType"] + "/" + resource["id"]] = resource

    def test_explicit_person_and_subjects_match_source(self):
        self.assertEqual(len(self.rows), 1)
        self.assertEqual(self.rows[0]["person_id"], PERSON)
        self.assertEqual(self.rows[0]["person_name"], "Alex Example")
        self.assertEqual(set(self.resources), {PATIENT, OBSERVATION, DOCUMENT})
        patient = self.resources[PATIENT]
        self.assertEqual(patient["identifier"][0]["value"], PERSON)
        self.assertEqual(patient["name"][0]["text"], self.rows[0]["person_name"])
        self.assertEqual(self.evidence["personId"], PERSON)
        for reference in (OBSERVATION, DOCUMENT):
            self.assertEqual(
                self.resources[reference]["subject"]["reference"], f"urn:uuid:{PERSON}"
            )
        for entry in self.bundle["entry"]:
            self.assertEqual(entry["fullUrl"], "urn:uuid:" + entry["resource"]["id"])

    def test_quantity_retains_source_scale_comparator_and_unit(self):
        self.assertEqual(self.rows[0]["result"], "<0,050 mg/L")
        quantity = self.resources[OBSERVATION]["valueQuantity"]
        self.assertIsInstance(quantity["value"], Decimal)
        self.assertEqual(str(quantity["value"]), "0.050")
        self.assertEqual(quantity["comparator"], "<")
        self.assertEqual(quantity["unit"], "mg/L")

    def test_source_status_month_label_and_uncertainty_are_retained(self):
        observation = self.resources[OBSERVATION]
        for column, value in (
            ("status", observation["status"]),
            ("effective_date", observation["effectiveDateTime"]),
            ("test", observation["code"]["text"]),
            ("uncertainty", observation["note"][0]["text"]),
        ):
            with self.subTest(column=column):
                self.assertEqual(value, self.rows[0][column])
        self.assertEqual(observation["effectiveDateTime"], "2026-02")
        self.assertEqual(observation["status"], "final")
        self.assertEqual(observation["code"], {"text": "C-reactive protein"})
        self.assertEqual(
            self.resources[DOCUMENT]["description"],
            "Invented report " + self.rows[0]["report_id"],
        )
        attachment = self.resources[DOCUMENT]["content"][0]["attachment"]
        self.assertEqual(attachment["contentType"], "text/csv")

    def test_citations_match_source_bytes_cells_and_target_fields(self):
        expected = {
            (PATIENT, "/identifier/0/value", "person_id"),
            (PATIENT, "/name/0/text", "person_name"),
            (OBSERVATION, "/subject/reference", "person_id"),
            (OBSERVATION, "/status", "status"),
            (OBSERVATION, "/code/text", "test"),
            (OBSERVATION, "/effectiveDateTime", "effective_date"),
            (OBSERVATION, "/valueQuantity/value", "result"),
            (OBSERVATION, "/valueQuantity/comparator", "result"),
            (OBSERVATION, "/valueQuantity/unit", "result"),
            (OBSERVATION, "/note/0/text", "uncertainty"),
            (DOCUMENT, "/subject/reference", "person_id"),
            (DOCUMENT, "/description", "report_id"),
        }
        digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        actual = []
        for entry in self.evidence["entries"]:
            target = entry["target"]
            resource = self.resources[target["reference"]]
            for pointer in target["pointers"]:
                # The example uses only plain object keys and list indices.
                value = resource
                for key in pointer.lstrip("/").split("/"):
                    value = value[int(key)] if isinstance(value, list) else value[key]
                self.assertIsNotNone(value, pointer)
            if entry["kind"] != "source":
                continue
            locator = entry["locator"]
            self.assertEqual(locator["kind"], "csv-cell")
            self.assertEqual(locator["row"], 1)
            self.assertEqual(locator["delimiter"], ",")
            self.assertEqual(entry["quote"], self.rows[0][locator["column"]])
            self.assertEqual(entry["sourceSha256"], digest)
            self.assertEqual(entry["sourceDocument"], DOCUMENT)
            actual.extend(
                (target["reference"], pointer, locator["column"])
                for pointer in target["pointers"]
            )
        self.assertCountEqual(actual, expected)

    def test_bundle_resources_and_evidence_validate_against_existing_schemas(self):
        schema = read_json(ROOT / "definitions/fhir-r4-json-schema/fhir.schema.json")
        Draft6Validator(schema).validate(self.bundle)
        for resource in self.resources.values():
            specific = dict(schema, **{"$ref": "#/definitions/" + resource["resourceType"]})
            Draft6Validator(specific).validate(resource)
        evidence_schema = read_json(ROOT / "schemas/0.1.0/evidence.schema.json")
        Draft202012Validator(evidence_schema).validate(self.evidence)

    def test_schema_rejects_observation_without_required_code(self):
        schema = read_json(ROOT / "definitions/fhir-r4-json-schema/fhir.schema.json")
        invalid = dict(self.resources[OBSERVATION])
        del invalid["code"]
        specific = dict(schema, **{"$ref": "#/definitions/Observation"})
        with self.assertRaises(ValidationError) as rejected:
            Draft6Validator(specific).validate(invalid)
        self.assertEqual(rejected.exception.validator, "required")
        self.assertIn("code", rejected.exception.message)

    def test_profile_and_source_links_survive_copy_to_records(self):
        profile = read_json(EXAMPLES / "profile.fhir.json")
        self.assertEqual(profile, self.resources[PATIENT])
        draft = DRAFT
        retained = {path.name: path.read_bytes() for path in draft.iterdir()}
        self.assertTrue({"bundle.fhir.json", "evidence.md", "review.md"} <= retained.keys())
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory).resolve()
            shutil.copytree(EXAMPLES / "sources", folder / "sources")
            for stage in ("drafts", "records"):
                # Exercise relocation only; copying is not human acceptance.
                destination = folder / stage / "first-import"
                shutil.copytree(draft, destination)
                self.assertEqual(
                    {path.name: path.read_bytes() for path in destination.iterdir()},
                    retained,
                )
                bundle = read_json(destination / "bundle.fhir.json")
                document = next(
                    entry["resource"] for entry in bundle["entry"]
                    if entry["resource"]["resourceType"] == "DocumentReference"
                )
                source = destination / document["content"][0]["attachment"]["url"]
                self.assertEqual(source.resolve(), folder / "sources" / "source.csv")
                self.assertEqual(source.read_bytes(), (EXAMPLES / "sources" / "source.csv").read_bytes())


if __name__ == "__main__":
    unittest.main()
