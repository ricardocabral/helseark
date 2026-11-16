"""Check the shipped bilingual vocabulary against its public coverage contract."""
import csv
import hashlib
import io
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
VOCABULARY = ROOT / 'vocabulary'


class ShippedVocabularyTest(unittest.TestCase):
    def test_manifest_pins_every_shipped_definition_and_notice(self):
        self.assertTrue((VOCABULARY / 'manifest.json').is_file(), 'fresh checkout needs a usable vocabulary')
        manifest = json.loads((VOCABULARY / 'manifest.json').read_text())
        self.assertEqual(manifest['format'], 2)
        self.assertEqual(set(manifest['languages']), {'en', 'pt-BR'})
        for name, expected in manifest['artifacts'].items():
            self.assertEqual(hashlib.sha256((VOCABULARY / name).read_bytes()).hexdigest(), expected, name)
        self.assertTrue({'loinc.csv', 'pt-BR.csv', 'ucum.xml', 'aliases.json', 'mappings.json'}.issubset(manifest['artifacts']))
        self.assertTrue({'LICENSES/LOINC.txt', 'LICENSES/UCUM.txt', 'LICENSES/Janusmed.txt'}.issubset(manifest['artifacts']))

    def test_authorized_janusmed_aliases_cover_both_languages_without_clinical_approval(self):
        self.assertTrue((VOCABULARY / 'aliases.json').is_file(), 'Janusmed bilingual seed is missing')
        aliases = json.loads((VOCABULARY / 'aliases.json').read_text())['aliases']
        catalog = {row['LOINC_NUM'] for row in csv.DictReader(io.StringIO((VOCABULARY / 'loinc.csv').read_text()))}
        by_family = {}
        for alias in aliases:
            self.assertEqual(alias['review_status'], 'retrieval_only')
            self.assertTrue(alias['candidates'])
            self.assertTrue(set(alias['candidates']).issubset(catalog))
            if alias['source']['name'] == 'Janusmed':
                self.assertIsInstance(alias['source']['synonym_id'], int)
                by_family.setdefault(alias['source']['metric'], set()).add(alias['language'])
        for family in ['LDL', 'HDL', 'TOTAL_CHOLESTEROL', 'TRIGLYCERIDES', 'HB1AC', 'TSH', 'CREATININE', 'HEMOGLOBIN', 'CRP', 'WBC', 'NEUTROPHILS', 'NEUTROPHILS_ABS']:
            self.assertTrue({'en', 'pt-BR'}.issubset(by_family[family]), family)
        self.assertEqual(json.loads((VOCABULARY / 'mappings.json').read_text())['rules'], [])
        by_term = {a['term'].casefold(): a for a in aliases}
        self.assertIn('mau colesterol', by_term)
        self.assertIn('hemoglobina glicada', by_term)
        self.assertGreater(len(by_term['ldl']['candidates']), 1)
        definitions = {row['LOINC_NUM']: row for row in csv.DictReader(io.StringIO((VOCABULARY / 'loinc.csv').read_text()))}
        for alias in aliases:
            metric = alias['source']['metric']
            if metric in ('NEUTROPHILS', 'NEUTROPHILS_ABS'):
                expected = 'NFr' if metric == 'NEUTROPHILS' else 'NCnc'
                self.assertEqual({definitions[code]['PROPERTY'] for code in alias['candidates']}, {expected}, alias['id'])

    def test_official_definitions_retain_distinct_methods_and_count_properties(self):
        self.assertTrue((VOCABULARY / 'loinc.csv').is_file(), 'official starter definitions are missing')
        rows = {row['LOINC_NUM']: row for row in csv.DictReader(io.StringIO((VOCABULARY / 'loinc.csv').read_text()))}
        self.assertEqual(rows['13457-7']['METHOD_TYP'], 'Calculated')
        self.assertEqual(rows['18262-6']['METHOD_TYP'], 'Direct assay')
        self.assertEqual(rows['770-8']['PROPERTY'], 'NFr')
        self.assertEqual(rows['751-8']['PROPERTY'], 'NCnc')
        self.assertEqual(rows['4548-4']['PROPERTY'], 'MFr')
        self.assertEqual(rows['59261-8']['PROPERTY'], 'SFr')
        self.assertTrue(all(row['STATUS'] == 'ACTIVE' for row in rows.values()))
        translated = {row['LOINC_NUM']: row for row in csv.DictReader(io.StringIO((VOCABULARY / 'pt-BR.csv').read_text()))}
        self.assertTrue(set(translated).issubset(rows))
        self.assertIn('1988-5', translated)
        self.assertEqual(translated['1988-5']['COMPONENT'], 'Proteína C Reativa')


if __name__ == '__main__':
    unittest.main()
