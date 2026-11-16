"""Synthetic bundled packages and copied-checkout offline resolver behavior."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from test_terminology import AXES, HEADERS, ROWS, SCRIPT, XML, table


class BundledTerminologyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.checkout = self.root / 'copied-checkout'
        self.script = self.checkout / 'skills/helseark/scripts/terminology.py'
        self.script.parent.mkdir(parents=True)
        shutil.copyfile(SCRIPT, self.script)
        self.package = self.checkout / 'vocabulary'
        self.package.mkdir()
        self.aliases = [self.alias('ldl-br', 'gordura ruim', 'pt-BR', ['1234-5', '3456-7']),
                        self.alias('ldl-en', 'bad fat', 'en', ['1234-5']),
                        self.alias('neutral', 'LDLX', 'und', ['1234-5']),
                        self.alias('percent', 'cells %', 'en', ['2345-6']),
                        self.alias('absolute', 'cells absolute', 'en', ['1234-5'])]
        self.write_bundle()

    def alias(self, identifier, term, language, candidates):
        return {'id': identifier, 'term': term, 'language': language,
                'source': {'name': 'Janusmed synthetic', 'metric': 'synthetic-family', 'synonym_id': identifier},
                'candidates': candidates, 'review_status': 'retrieval_only'}

    def write_bundle(self, *, aliases=None, rules=None):
        files = {'loinc.csv': table(HEADERS, ROWS).encode(),
                 'pt-BR.csv': table(['LOINC_NUM', 'COMPONENT'], [['1234-5', 'Colesterol LDL']]).encode(),
                 'ucum.xml': XML,
                 'aliases.json': json.dumps({'format': 1, 'aliases': self.aliases if aliases is None else aliases}).encode(),
                 'mappings.json': json.dumps({'format': 1, 'rules': [] if rules is None else rules}).encode(),
                 'LICENSES/synthetic.txt': b'Synthetic terms fixture'}
        for name, content in files.items():
            path = self.package / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(content)
        manifest = {'format': 2, 'kind': 'bundled', 'vocabulary_version': '0.1.0',
                    'loinc_version': 'synthetic', 'ucum_version': 'test-1', 'languages': ['en', 'pt-BR'],
                    'artifacts': {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}}
        (self.package / 'manifest.json').write_text(json.dumps(manifest))

    def run_cli(self, *args, success=True):
        wrapper = "import runpy,socket,sys,urllib.request; socket.socket=lambda *a,**k: (_ for _ in ()).throw(AssertionError('network forbidden')); sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name='__main__')"
        result = subprocess.run([sys.executable, '-c', wrapper, str(self.script), *map(str, args)],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0 if success else 2, result.stderr)
        return json.loads(result.stdout) if success else result.stderr

    def search(self, text, *args):
        return self.run_cli('search', '--text', text, *args)

    def full_package(self, version='synthetic', rows=None):
        package = self.root / 'full'
        package.mkdir(exist_ok=True)
        with zipfile.ZipFile(package / 'loinc.zip', 'w') as archive:
            archive.writestr('LoincTable/Loinc.csv', table(HEADERS, ROWS if rows is None else rows))
        (package / 'ucum.xml').write_bytes(XML)
        manifest = {'format': 1, 'loinc_version': version, 'ucum_version': 'test-1',
                    'artifacts': {name: hashlib.sha256((package / name).read_bytes()).hexdigest()
                                  for name in ('loinc.zip', 'ucum.xml')}}
        (package / 'manifest.json').write_text(json.dumps(manifest))
        return package

    def test_default_copied_checkout_search_is_offline_from_another_cwd(self):
        result = self.search('gordura ruim')
        self.assertEqual([item['code'] for item in result['candidates']], ['1234-5', '3456-7'])
        self.assertTrue(result['human_review_required'])
        self.assertEqual(result['catalog']['vocabulary_version'], '0.1.0')
        match = result['candidates'][0]['alias_matches'][0]
        self.assertEqual(match['id'], 'ldl-br')
        self.assertEqual(match['source']['synonym_id'], 'ldl-br')
        self.assertEqual(match['review_status'], 'retrieval_only')
        self.assertEqual(match['catalog']['loinc_version'], 'synthetic')
        self.assertEqual(result['candidates'][0]['provenance']['loinc_sha256'],
                         hashlib.sha256((self.package / 'loinc.csv').read_bytes()).hexdigest())

    def test_aliases_are_individual_bilingual_neutral_and_preserve_percent(self):
        for term, codes in [('BAD FAT', ['1234-5']), ('LDLX', ['1234-5']),
                            ('cells %', ['2345-6']), ('cells absolute', ['1234-5']),
                            ('gordura fat', []), ('cells % absolute', [])]:
            with self.subTest(term=term):
                self.assertEqual([item['code'] for item in self.search(term)['candidates']], codes)
        filtered = self.search('gordura ruim', '--system', 'Urine')
        self.assertEqual([item['code'] for item in filtered['candidates']], ['3456-7'])
        self.assertEqual(self.search('uncovered synthetic analyte')['candidates'], [])

    def test_alias_union_has_one_candidate_per_code_with_all_matches(self):
        self.aliases.append(self.alias('duplicate-term', 'bad fat', 'en', ['1234-5', '2345-6']))
        self.write_bundle()
        result = self.search('bad fat')
        self.assertEqual([item['code'] for item in result['candidates']], ['1234-5', '2345-6'])
        self.assertEqual({item['id'] for item in result['candidates'][0]['alias_matches']}, {'ldl-en', 'duplicate-term'})

    def test_source_synonym_ids_preserve_numeric_type_without_invented_ids(self):
        self.aliases[0]['source'] = {'name': 'Janusmed', 'metric': 'LDL', 'synonym_id': 1541}
        self.aliases[1]['source'] = {'name': 'Helseark', 'metric': 'LDL'}
        self.write_bundle()
        self.assertEqual(self.search('gordura ruim')['candidates'][0]['alias_matches'][0]['source']['synonym_id'], 1541)
        self.assertNotIn('synonym_id', self.search('bad fat')['candidates'][0]['alias_matches'][0]['source'])
        for invalid in (True, -1, [], ''):
            self.aliases[0]['source']['synonym_id'] = invalid
            self.write_bundle()
            self.assertIn('alias', self.run_cli('search', '--text', 'gordura ruim', success=False))
        del self.aliases[0]['source']['synonym_id']
        self.write_bundle()
        self.assertIn('alias', self.run_cli('search', '--text', 'gordura ruim', success=False))

    def test_check_default_abstains_without_axes_and_keeps_exact_source_bytes(self):
        observation = self.root / 'observation.json'
        observation.write_text('{"resourceType":"Observation","code":{"text":"gordura ruim"},"valueQuantity":{"value":100.00,"unit":"mg/dL"}}')
        proposal = self.root / 'proposal.json'
        proposal.write_text(json.dumps({'loinc': '1234-5', 'context': {}, 'evidence': {}}))
        before = observation.read_bytes(), proposal.read_bytes()
        result = self.run_cli('check', '--observation', observation, '--proposal', proposal)
        self.assertEqual(result['decision'], 'human_review_required')
        self.assertEqual(result['proposed_additions'], {})
        self.assertTrue(result['issues'])
        self.assertEqual(before, (observation.read_bytes(), proposal.read_bytes()))
        proposed = {'loinc': '1234-5', 'context': dict(AXES), 'evidence': {key: 'invented line 1' for key in AXES}}
        proposal.write_text(json.dumps(proposed))
        result = self.run_cli('check', '--observation', observation, '--proposal', proposal)
        self.assertEqual(result['issues'], [])
        self.assertEqual(result['proposed_additions']['code.coding']['version'], 'synthetic')
        self.assertEqual(observation.read_bytes(), before[0])

    def test_explicit_bundled_package_and_official_translation_work(self):
        result = self.search('Colesterol LDL', '--package', self.package)
        self.assertEqual([item['code'] for item in result['candidates']], ['1234-5'])

    def test_every_declared_artifact_including_notices_is_verified(self):
        for name in ('loinc.csv', 'pt-BR.csv', 'ucum.xml', 'aliases.json', 'mappings.json', 'LICENSES/synthetic.txt'):
            with self.subTest(name=name):
                self.write_bundle()
                path = self.package / name
                path.write_bytes(path.read_bytes() + b' ')
                error = self.run_cli('search', '--package', self.package, '--text', 'LDL', success=False)
                self.assertIn('SHA256 mismatch', error)

    def test_alias_metadata_and_references_fail_closed(self):
        for field, value in [('language', 'xx'), ('review_status', 'approved'),
                             ('candidates', ['9999-9']), ('term', ''), ('source', {}), ('id', '')]:
            with self.subTest(field=field):
                aliases = json.loads(json.dumps(self.aliases))
                aliases[0][field] = value
                self.write_bundle(aliases=aliases)
                self.assertIn('alias', self.run_cli('search', '--package', self.package, '--text', 'LDL', success=False))
        self.write_bundle(aliases=[self.aliases[0], self.aliases[0]])
        self.assertIn('alias', self.run_cli('search', '--package', self.package, '--text', 'LDL', success=False))

    def test_unsafe_paths_missing_pins_and_invalid_rules_fail_closed(self):
        for name in ('../outside', '/absolute', 'LICENSES/../escape', 'LICENSES\\escape'):
            self.write_bundle()
            path = self.package / 'manifest.json'
            manifest = json.loads(path.read_text())
            manifest['artifacts'][name] = '0' * 64
            path.write_text(json.dumps(manifest))
            self.assertIn('unsafe', self.run_cli('search', '--package', self.package, '--text', 'LDL', success=False))
        for rule in ({'loinc': '9999-9'}, {'loinc': '1234-5', 'loinc_version': 'another'}):
            self.write_bundle(rules=[rule])
            self.assertIn('rule', self.run_cli('search', '--package', self.package, '--text', 'LDL', success=False))
        self.write_bundle()
        path = self.package / 'manifest.json'
        manifest = json.loads(path.read_text())
        del manifest['artifacts']['aliases.json']
        path.write_text(json.dumps(manifest))
        self.assertIn('manifest', self.run_cli('search', '--package', self.package, '--text', 'LDL', success=False))

    def test_bundle_symlinks_unknown_status_and_unknown_translation_fail_closed(self):
        path = self.package / 'aliases.json'
        target = self.root / 'aliases.json'
        shutil.copyfile(path, target)
        path.unlink()
        path.symlink_to(target)
        self.assertIn('symlink', self.run_cli('search', '--package', self.package, '--text', 'LDL', success=False))
        path.unlink()
        self.write_bundle()
        for name, content in [('loinc.csv', table(HEADERS, [ROWS[0][:7] + ['UNKNOWN'] + ROWS[0][8:]]).encode()),
                              ('pt-BR.csv', table(['LOINC_NUM', 'COMPONENT'], [['9999-9', 'Invented']]).encode())]:
            self.write_bundle()
            (self.package / name).write_bytes(content)
            manifest_path = self.package / 'manifest.json'
            manifest = json.loads(manifest_path.read_text())
            manifest['artifacts'][name] = hashlib.sha256(content).hexdigest()
            manifest_path.write_text(json.dumps(manifest))
            self.run_cli('search', '--package', self.package, '--text', 'LDL', success=False)

    def test_flat_artifact_and_aggregate_budgets_are_enforced(self):
        spec = importlib.util.spec_from_file_location('bundled_terminology', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for limits in ({'MAX_FILE': 10}, {'MAX_TOTAL': 10}, {'MAX_JSON': 10}):
            with self.subTest(limits=limits), patch.multiple(module, **limits):
                with self.assertRaisesRegex(ValueError, 'size limit'):
                    module.load_package(self.package)

    def test_full_package_preserves_compatible_aliases_and_uses_its_own_pins(self):
        package = self.full_package()
        result = self.search('gordura ruim', '--package', package)
        self.assertEqual([item['code'] for item in result['candidates']], ['1234-5', '3456-7'])
        self.assertEqual(result['catalog']['loinc_version'], 'synthetic')
        self.assertEqual(result['catalog']['diagnostics'], [])
        self.assertEqual(result['candidates'][0]['provenance']['loinc_sha256'],
                         hashlib.sha256((package / 'loinc.zip').read_bytes()).hexdigest())

    def test_full_release_revalidates_aliases_and_records_both_pins(self):
        result = self.search('gordura ruim', '--package', self.full_package(version='synthetic-new'))
        self.assertEqual([item['code'] for item in result['candidates']], ['1234-5', '3456-7'])
        match = result['candidates'][0]['alias_matches'][0]
        self.assertTrue(match['revalidated'])
        self.assertEqual(match['catalog']['loinc_version'], 'synthetic')
        self.assertEqual(match['selected_loinc_version'], 'synthetic-new')
        self.assertEqual(result['catalog']['loinc_version'], 'synthetic-new')
        self.assertEqual(self.search('LDL', '--package', self.root / 'full')['candidates'][0]['provenance']['loinc_version'], 'synthetic-new')

    def test_full_conflicting_axes_status_or_missing_codes_have_diagnostics(self):
        rows = json.loads(json.dumps(ROWS))
        rows[0][2] = 'SCnc'
        rows[2][7] = 'DEPRECATED'
        rows = [row for row in rows if row[0] != '2345-6']
        result = self.search('gordura ruim', '--package', self.full_package(version='synthetic-new', rows=rows))
        self.assertEqual(result['candidates'], [])
        self.assertIn('catalog', result)
        reasons = {(item['code'], item['reason']) for item in result['catalog']['diagnostics']}
        self.assertIn(('1234-5', 'axes_mismatch'), reasons)
        self.assertIn(('3456-7', 'status_mismatch'), reasons)
        self.assertIn(('2345-6', 'code_absent'), reasons)


if __name__ == '__main__':
    unittest.main()
