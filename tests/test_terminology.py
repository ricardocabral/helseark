"""Offline terminology contracts exercised with invented catalogs and FHIR."""
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/helseark/scripts/terminology.py'
AXES = {'component': 'Cholesterol in LDL', 'system': 'Ser/Plas', 'property': 'MCnc', 'time': 'Pt', 'scale': 'Qn', 'method': ''}
HEADERS = ['LOINC_NUM', 'COMPONENT', 'PROPERTY', 'TIME_ASPCT', 'SYSTEM', 'SCALE_TYP', 'METHOD_TYP', 'STATUS', 'LONG_COMMON_NAME', 'SHORTNAME', 'RELATEDNAMES2', 'EXAMPLE_UCUM_UNITS']
ROWS = [
 ['1234-5', 'Cholesterol in LDL', 'MCnc', 'Pt', 'Ser/Plas', 'Qn', '', 'ACTIVE', 'LDL cholesterol mass', 'LDL', '', 'mg/dL'],
 ['2345-6', 'Cholesterol in VLDL', 'MCnc', 'Pt', 'Ser/Plas', 'Qn', '', 'ACTIVE', 'VLDL cholesterol mass', 'VLDL', '', 'mg/dL'],
 ['3456-7', 'Cholesterol in LDL', 'MCnc', 'Pt', 'Urine', 'Qn', 'Calculated', 'ACTIVE', 'LDL urine calculated', 'LDL urine', '', 'mg/dL'],
 ['4567-8', 'Cholesterol in LDL', 'MCnc', 'Pt', 'Ser/Plas', 'Qn', '', 'DEPRECATED', 'LDL old', 'LDL old', '', 'mg/dL'],
]
XML = b'''<root xmlns="http://unitsofmeasure.org/ucum-essence" version="test-1"><prefix Code="m"/><prefix Code="d"/><base-unit Code="g"/><unit Code="L" isMetric="yes"/><unit Code="%" isMetric="no"/><unit Code="[IU]" isMetric="yes"/></root>'''


def table(headers, rows):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows(rows)
    return stream.getvalue()


class TerminologyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.archive = self.root / 'official.zip'
        self.xml = self.root / 'ucum.xml'
        self.xml.write_bytes(XML)
        self.make_archive()
        self.package = self.root / 'package'

    def make_archive(self, rows=None, extra=None):
        with zipfile.ZipFile(self.archive, 'w') as archive:
            archive.writestr('LoincTable/Loinc.csv', table(HEADERS, ROWS if rows is None else rows))
            archive.writestr('AccessoryFiles/LinguisticVariants/ptBR11LinguisticVariant.csv', table(['LOINC_NUM', 'LONG_COMMON_NAME', 'SHORTNAME', 'LinguisticVariantDisplayName'], [['1234-5', 'Colesterol LDL massa', 'LDL', 'Colesterol LDL']]))
            archive.writestr('LoincLicense.txt', 'Synthetic license fixture')
            archive.writestr('AccessoryFiles/PanelsAndForms/Loinc.csv', 'unrelated')
            if extra:
                archive.writestr(*extra)

    def run_cli(self, *args, success=True):
        result = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0 if success else 2, result.stderr)
        return json.loads(result.stdout) if success else result.stderr

    def install(self):
        return self.run_cli('install', '--loinc-zip', self.archive, '--loinc-version', 'synthetic', '--ucum-xml', self.xml, '--destination', self.package)

    def files(self):
        observation = {'resourceType': 'Observation', 'id': 'invented', 'subject': {'reference': 'Patient/invented'}, 'code': {'text': 'Colesterol LDL', 'coding': [{'system': 'urn:lab:invented', 'code': 'LDL1'}]}, 'valueQuantity': {'value': 100, 'unit': 'mg/dL'}}
        # Retain the exact lexical decimal in the real input bytes.
        obs_path = self.root / 'observation.json'
        obs_path.write_text(json.dumps(observation).replace('100,', '100.00,'))
        proposal = {'loinc': '1234-5', 'ucum': 'mg/dL', 'context': dict(AXES, unit='mg/dL'), 'evidence': {key: 'Synthetic report line 1' for key in (*AXES, 'unit')}}
        prop_path = self.root / 'proposal.json'
        prop_path.write_text(json.dumps(proposal))
        return obs_path, prop_path, proposal

    def check(self, proposal=None):
        obs, prop, original = self.files()
        if proposal:
            original.update(proposal)
            prop.write_text(json.dumps(original))
        before = obs.read_bytes(), prop.read_bytes()
        result = self.run_cli('check', '--package', self.package, '--observation', obs, '--proposal', prop)
        self.assertEqual(before, (obs.read_bytes(), prop.read_bytes()))
        return result

    def test_search_is_bilingual_token_aware_active_and_axis_filtered(self):
        self.install()
        found = self.run_cli('search', '--package', self.package, '--text', 'colesterol LDL', '--system', 'Ser/Plas')
        self.assertEqual([row['code'] for row in found['candidates']], ['1234-5'])
        row = found['candidates'][0]
        self.assertEqual(row['axes']['system'], 'Ser/Plas')
        self.assertEqual(row['translations']['pt-BR']['LONG_COMMON_NAME'], 'Colesterol LDL massa')
        self.assertEqual(row['example_ucum_units'], ['mg/dL'])
        self.assertFalse(found['examples_are_whitelist'])
        self.assertEqual(len(self.run_cli('search', '--package', self.package, '--text', 'LDL')['candidates']), 2)

    def test_install_retains_originals_hashes_versions_and_refuses_overwrite(self):
        self.install()
        manifest = json.loads((self.package / 'manifest.json').read_text())
        self.assertEqual(manifest['ucum_version'], 'test-1')
        self.assertEqual(manifest['loinc_version'], 'synthetic')
        self.assertEqual((self.package / 'loinc.zip').read_bytes(), self.archive.read_bytes())
        self.run_cli('install', '--loinc-zip', self.archive, '--loinc-version', 'synthetic', '--ucum-xml', self.xml, '--destination', self.package, success=False)

    def test_corruption_and_symlinks_fail_closed(self):
        self.install()
        (self.package / 'ucum.xml').write_bytes(XML + b' ')
        self.run_cli('search', '--package', self.package, '--text', 'LDL', success=False)
        (self.package / 'ucum.xml').unlink()
        (self.package / 'ucum.xml').symlink_to(self.xml)
        self.run_cli('search', '--package', self.package, '--text', 'LDL', success=False)

    def test_duplicate_rows_and_unsafe_archive_fail_without_destination(self):
        for rows, extra in [(ROWS + [ROWS[0]], None), (ROWS, ('../escape', 'bad'))]:
            self.make_archive(rows, extra)
            self.run_cli('install', '--loinc-zip', self.archive, '--loinc-version', 'synthetic', '--ucum-xml', self.xml, '--destination', self.package, success=False)
            self.assertFalse(self.package.exists())
        self.assertFalse((self.root / 'escape').exists())
        self.make_archive(ROWS + [ROWS[0]])
        error = self.run_cli('install', '--loinc-zip', self.archive, '--loinc-version', 'synthetic', '--ucum-xml', self.xml, '--destination', self.package, success=False)
        self.assertIn('duplicate LOINC row', error)

    def test_check_emits_native_additions_without_changing_decimal_or_sources(self):
        self.install()
        result = self.check()
        self.assertEqual(result['decision'], 'human_review_required')
        self.assertEqual(result['issues'], [])
        self.assertEqual(result['proposed_additions']['code.coding']['system'], 'http://loinc.org')
        self.assertEqual(result['proposed_additions']['valueQuantity']['code'], 'mg/dL')
        self.assertFalse(result['unit']['dimensional_compatibility_checked'])
        self.assertEqual(result['catalog']['artifacts']['loinc.zip'], hashlib.sha256(self.archive.read_bytes()).hexdigest())
        self.assertEqual(len(result['catalog']['manifest_sha256']), 64)
        self.assertIn('100.00', (self.root / 'observation.json').read_text())
        self.assertEqual(result['source_codings'][0]['code'], 'LDL1')

    def test_missing_context_evidence_and_contradictory_axes_are_unresolved(self):
        self.install()
        missing = self.check({'context': {}, 'evidence': {}})
        self.assertTrue(missing['issues'])
        self.assertEqual(missing['proposed_additions'], {})
        wrong = self.check({'loinc': '3456-7'})
        self.assertTrue(any('system' in issue and 'incompatible' in issue for issue in wrong['issues']))
        self.assertTrue(any('method' in issue and 'incompatible' in issue for issue in wrong['issues']))
        self.assertEqual(wrong['proposed_additions'], {})
        self.assertTrue(self.check({'loinc': '4567-8'})['issues'])
        self.assertTrue(self.check({'loinc': '9999-9'})['issues'])

    def test_ucum_case_and_bounded_supported_grammar(self):
        self.install()
        for unit in ('mg/dL', 'mg.dL-1', '[IU]/L', '%', '1'):
            self.assertEqual(self.check({'ucum': unit})['unit']['status'], 'valid_syntax')
        self.assertEqual(self.check({'ucum': 'MG/DL'})['unit']['status'], 'invalid')
        self.assertEqual(self.check({'ucum': 'mg{label}/dL'})['unit']['status'], 'not_checked')
        self.assertEqual(self.check({'ucum': 'mg//'})['unit']['status'], 'invalid')

    def test_conditional_reuse_never_uses_label_only_or_autoaccepts(self):
        self.install()
        context = dict(AXES, lab='invented-lab', local_test='LDL1', specimen='Ser/Plas', unit='mg/dL')
        rule = {'decision': 'approved', 'version': '1', 'loinc_version': 'synthetic', 'evidence': 'Synthetic reviewed mapping', 'approved_by': 'Invented human', 'approved_at': '2026-11-16', 'conditions': {key: context[key] for key in ('lab', 'local_test', 'specimen', 'method', 'unit')}, 'loinc': '1234-5', 'ucum': 'mg/dL'}
        self.assertEqual(self.check({'context': context, 'rule': rule})['rule_reuse'], 'eligible_for_human_review')
        rule['conditions']['specimen'] = 'Urine'
        self.assertEqual(self.check({'context': context, 'rule': rule})['rule_reuse'], 'ineligible')
        rule['conditions'] = {'label': 'LDL'}
        self.assertEqual(self.check({'context': context, 'rule': rule})['rule_reuse'], 'ineligible')

    def test_offline_commands_do_not_open_sockets(self):
        self.install()
        obs, prop, _ = self.files()
        wrapper = "import runpy,socket,sys,urllib.request; socket.socket=lambda *a,**k: (_ for _ in ()).throw(AssertionError('network forbidden')); sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name='__main__')"
        for args in [('search', '--package', self.package, '--text', 'LDL'), ('check', '--package', self.package, '--observation', obs, '--proposal', prop)]:
            result = subprocess.run([sys.executable, '-c', wrapper, str(SCRIPT), *map(str, args)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_conflicting_source_codes_units_and_rule_release_are_reported(self):
        self.install()
        obs, prop, proposal = self.files()
        observation = json.loads(obs.read_text())
        observation['code']['coding'].append({'system': 'http://loinc.org', 'code': '2345-6'})
        observation['valueQuantity'].update(system='http://unitsofmeasure.org', code='g/L')
        obs.write_text(json.dumps(observation))
        proposal['context']['unit'] = 'g/L'
        prop.write_text(json.dumps(proposal))
        result = self.run_cli('check', '--package', self.package, '--observation', obs, '--proposal', prop)
        self.assertTrue(any('source LOINC' in issue for issue in result['issues']))
        self.assertTrue(any('source UCUM' in issue for issue in result['issues']))
        self.assertTrue(any('original quantity unit' in issue for issue in result['issues']))

    def test_malformed_json_and_csv_fail_cleanly(self):
        self.install()
        obs, prop, _ = self.files()
        prop.write_text('{"loinc":"1234-5","loinc":"2345-6"}')
        self.run_cli('check', '--package', self.package, '--observation', obs, '--proposal', prop, success=False)
        manifest_path = self.package / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['artifacts'] = []
        manifest_path.write_text(json.dumps(manifest))
        self.run_cli('search', '--package', self.package, '--text', 'LDL', success=False)
        self.make_archive([ROWS[0][:-1]])
        self.run_cli('install', '--loinc-zip', self.archive, '--loinc-version', 'synthetic', '--ucum-xml', self.xml, '--destination', self.root / 'bad-package', success=False)

    def test_existing_quantity_coding_is_retained_and_conflicts_abstain(self):
        self.install()
        for coding in ({'system': 'urn:lab:units', 'code': 'MGDL'},
                       {'system': 'urn:lab:units'}, {'code': 'MGDL'},
                       {'system': 'http://unitsofmeasure.org', 'code': 'mg/dL'}):
            obs, prop, _ = self.files()
            source = json.loads(obs.read_text())
            source['valueQuantity'].update(coding)
            obs.write_text(json.dumps(source))
            result = self.run_cli('check', '--package', self.package, '--observation', obs, '--proposal', prop)
            self.assertEqual(result['source_quantity_coding'], coding)
            if coding == {'system': 'http://unitsofmeasure.org', 'code': 'mg/dL'}:
                self.assertEqual(result['issues'], [])
                self.assertIn('valueQuantity', result['proposed_additions'])
            else:
                self.assertTrue(result['issues'])
                self.assertEqual(result['proposed_additions'], {})

    def test_ucum_unary_division_is_only_valid_at_top_level(self):
        self.install()
        for unit in ('(/mg)', 'mg/(/dL)'):
            self.assertEqual(self.check({'ucum': unit})['unit']['status'], 'invalid')
        for unit in ('/mg', 'mg/dL', '[IU]/L'):
            self.assertEqual(self.check({'ucum': unit})['unit']['status'], 'valid_syntax')

    def test_ucum_requires_source_unit_and_assignment_evidence(self):
        self.install()
        for change in ({'context': dict(AXES)}, {'evidence': {key: 'source' for key in AXES}}):
            result = self.check(change)
            self.assertTrue(result['issues'])
            self.assertEqual(result['proposed_additions'], {})
        obs, prop, _ = self.files()
        source = json.loads(obs.read_text())
        del source['valueQuantity']['unit']
        obs.write_text(json.dumps(source))
        result = self.run_cli('check', '--package', self.package, '--observation', obs, '--proposal', prop)
        self.assertTrue(result['issues'])
        self.assertEqual(result['proposed_additions'], {})

    def test_empty_installed_release_is_rejected(self):
        self.install()
        path = self.package / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['loinc_version'] = ''
        path.write_text(json.dumps(manifest))
        self.run_cli('search', '--package', self.package, '--text', 'LDL', success=False)

    def test_fetch_publishes_only_verified_bytes_without_overwrite(self):
        spec = importlib.util.spec_from_file_location('terminology', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        target = self.root / 'download'
        data = b'invented pinned bytes'
        with patch.object(module.urllib.request.OpenerDirector, 'open', return_value=io.BytesIO(data)):
            module.fetch('https://example.invalid/catalog', hashlib.sha256(data).hexdigest(), target)
        self.assertEqual(target.read_bytes(), data)
        with self.assertRaises(ValueError):
            module.fetch('https://example.invalid/catalog', '0' * 64, target)
        self.assertEqual(target.read_bytes(), data)

    def test_fetch_stream_failure_and_limit_leave_no_artifacts(self):
        spec = importlib.util.spec_from_file_location('terminology', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        target = self.root / 'download'
        class BrokenStream(io.BytesIO):
            def read(self, size):
                raise OSError('synthetic interrupted transport')
        with patch.object(module.urllib.request.OpenerDirector, 'open', return_value=BrokenStream(b'x')):
            with self.assertRaises(OSError):
                module.fetch('https://example.invalid/catalog', '0' * 64, target)
        with patch.object(module, 'MAX_FILE', 2), patch.object(module.urllib.request.OpenerDirector, 'open', return_value=io.BytesIO(b'three')):
            with self.assertRaises(ValueError):
                module.fetch('https://example.invalid/catalog', '0' * 64, target)
        self.assertFalse(target.exists())
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['official.zip', 'ucum.xml'])

    def test_fetch_wrong_digest_cleans_up_and_http_is_refused(self):
        spec = importlib.util.spec_from_file_location('terminology', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        target = self.root / 'download'
        with patch.object(module.urllib.request.OpenerDirector, 'open', return_value=io.BytesIO(b'invented')):
            with self.assertRaises(ValueError):
                module.fetch('https://example.invalid/catalog', '0' * 64, target)
        self.assertFalse(target.exists())
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['official.zip', 'ucum.xml'])
        self.run_cli('fetch', '--url', 'http://example.invalid', '--sha256', '0' * 64, '--output', target, success=False)


if __name__ == '__main__':
    unittest.main()
