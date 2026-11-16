#!/usr/bin/env python3
"""Offline terminology candidates; never accepts mappings or changes records.

Commands: fetch explicitly acquires pinned HTTPS bytes; install retains supplied
LOINC ZIP and UCUM XML in a NEW directory; search/check have no network behavior.
Without --package, search/check use the bundled vocabulary beside the repository
skill. Aliases retrieve candidates only; they never supply clinical evidence.

check proposal JSON:
 {"loinc":"...", "ucum":"mg/dL", "context":{
   "component":"...", "property":"MCnc", "time":"Pt", "system":"Ser/Plas",
   "scale":"Qn", "method":""}, "evidence":{each of those six keys:"citation"}}
All axes require source context and evidence, including an explanation when the
source method is unspecified (empty string). A UCUM proposal also requires a
nonempty original quantity.unit, matching context.unit and nonempty evidence.unit.
Context may also contain lab,
local_test, specimen and unit; original valueQuantity.unit must agree literally
with context.unit when it is supplied. Evidence is reported, not independently
verified. No inference from a label alone establishes a mapping.

Optional rule: {"decision":"approved", "approved_by":"human", "approved_at":
"YYYY-MM-DD", "version":"1", "loinc_version":"release", "evidence":"citation",
"conditions":{"lab":"...","local_test":"...","specimen":"...","method":"",
"unit":"mg/dL"},"loinc":"...","ucum":"mg/dL"}. All five conditions must match
context literally; approval metadata is supplied by a human, never fabricated.
Eligibility only proposes reuse for another human review, never acceptance.

Output is JSON. check emits issues, native proposed additions, source codings,
unit syntax result and rule eligibility; quantities and records are never emitted
as rewritten copies. UCUM grammar support is bounded (atoms, metric prefixes,
integer exponents, products, division and parentheses). Annotations/special syntax
return not_checked. Syntax validity and example equality do not prove clinical or
dimensional compatibility. No quantity conversion is performed.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

MAX_FILE = 256 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MAX_JSON = 2 * 1024 * 1024
AXES = {'component': 'COMPONENT', 'property': 'PROPERTY', 'time': 'TIME_ASPCT',
        'system': 'SYSTEM', 'scale': 'SCALE_TYP', 'method': 'METHOD_TYP'}
NAMES = ('LONG_COMMON_NAME', 'SHORTNAME', 'RELATEDNAMES2', 'LinguisticVariantDisplayName')
NAMESPACE = 'http://unitsofmeasure.org/ucum-essence'
DEFAULT_PACKAGE = Path(__file__).resolve().parents[3] / 'vocabulary'


def safe_path(path: Path, *, exists: bool = True) -> Path:
    """Reject symlinks in every existing path component, including parents."""
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError('symlink paths are not supported')
    if exists and not path.is_file():
        raise ValueError('expected a regular input file')
    return path


def read_bytes(path: Path, limit: int = MAX_FILE) -> bytes:
    path = safe_path(path)
    with path.open('rb') as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError('input exceeds size limit')
    return content


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def read_json(path: Path) -> dict:
    # Parse exact decimals; no full Observation or quantity value is rewritten.
    value = json.loads(read_bytes(path, MAX_JSON), object_pairs_hook=unique_object,
                       parse_float=Decimal, parse_constant=lambda _: invalid_json())
    if not isinstance(value, dict):
        raise ValueError('expected a JSON object')
    return value


def invalid_json() -> None:
    raise ValueError('non-finite JSON number')


class HTTPSOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != 'https':
            raise ValueError('redirect must remain HTTPS')
        return super().redirect_request(request, response, code, message, headers, newurl)


def fetch(url: str, sha256: str, output: Path) -> dict:
    """Fetch bounded pinned bytes to a fresh file; remove temporary failures."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('a credential-free HTTPS URL is required')
    if not re.fullmatch('[0-9a-fA-F]{64}', sha256):
        raise ValueError('expected a SHA256 hexadecimal digest')
    output = safe_path(output, exists=False)
    if output.exists():
        raise ValueError('output already exists')
    fd, temporary = tempfile.mkstemp(prefix='.terminology-', dir=output.parent)
    try:
        # Install a handler locally; do not change the process-wide opener.
        opener = urllib.request.build_opener(HTTPSOnly())
        with os.fdopen(fd, 'wb') as target:
            with opener.open(url, timeout=30) as response:
                total, hasher = 0, hashlib.sha256()
                while block := response.read(65536):
                    total += len(block)
                    if total > MAX_FILE:
                        raise ValueError('download exceeds size limit')
                    target.write(block)
                    hasher.update(block)
            if hasher.hexdigest() != sha256.lower():
                raise ValueError('download SHA256 mismatch')
        # Hard-link publication is atomic and refuses an existing destination.
        os.link(temporary, output)
        return {'sha256': sha256.lower(), 'bytes': total, 'output': str(output)}
    finally:
        os.unlink(temporary)


def csv_rows(content: bytes, required: set[str]) -> list[dict]:
    text = content.decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text, newline=''), strict=True)
    headers = reader.fieldnames
    if not headers or len(headers) != len(set(headers)) or not required.issubset(headers):
        raise ValueError('missing or duplicate CSV headers')
    rows, codes = [], set()
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError('malformed CSV row')
        code = row['LOINC_NUM']
        if not re.fullmatch(r'[0-9]{1,8}-[0-9]', code) or code in codes:
            raise ValueError('malformed or duplicate LOINC row')
        codes.add(code)
        rows.append(row)
    if not rows:
        raise ValueError('empty terminology CSV')
    return rows


def load_loinc(data: bytes) -> tuple[dict, dict]:
    """Read exact distribution members without extracting archive paths."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members, total = {}, 0
        for item in archive.infolist():
            path = PurePosixPath(item.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in item.filename
                    or stat.S_ISLNK(item.external_attr >> 16) or item.filename in members):
                raise ValueError('unsafe or duplicate ZIP member')
            if len(members) >= 10000:
                raise ValueError('ZIP exceeds size limit')
            members[item.filename] = item

        def read_member(name: str) -> bytes:
            nonlocal total
            limit = min(MAX_FILE, MAX_TOTAL - total)
            if members[name].file_size > limit:
                raise ValueError('ZIP exceeds size limit')
            with archive.open(name) as stream:
                content = stream.read(limit + 1)
            total += len(content)
            if len(content) > limit:
                raise ValueError('ZIP exceeds size limit')
            return content

        # Some distributions wrap the official layout in a release directory.
        names = [name for name in members if name == 'LoincTable/Loinc.csv'
                 or re.fullmatch(r'Loinc_[^/]+/LoincTable/Loinc.csv', name)]
        if len(names) != 1:
            raise ValueError('expected exactly one official LoincTable/Loinc.csv')
        core_name = names[0]
        prefix = core_name[:-len('LoincTable/Loinc.csv')]
        rows = csv_rows(read_member(core_name), set(AXES.values()) | {'LOINC_NUM', 'STATUS', 'LONG_COMMON_NAME'})
        catalog = {row['LOINC_NUM']: row for row in rows}
        for row in rows:
            if row['STATUS'] not in ('ACTIVE', 'TRIAL', 'DISCOURAGED', 'DEPRECATED'):
                raise ValueError('unknown LOINC status')
        translations = {}
        pattern = re.compile(re.escape(prefix) + r'AccessoryFiles/LinguisticVariants/([a-z]{2})([A-Z]{2})[0-9]+LinguisticVariant\.csv')
        for name in members:
            match = pattern.fullmatch(name)
            if not match:
                continue
            language = '-'.join(match.groups())
            if language in translations:
                raise ValueError('duplicate linguistic variant')
            translated = csv_rows(read_member(name), {'LOINC_NUM'})
            if any(row['LOINC_NUM'] not in catalog for row in translated):
                raise ValueError('linguistic variant references unknown LOINC')
            translations[language] = {'member': name, 'rows': {row['LOINC_NUM']: row for row in translated}}
    return catalog, translations


def load_ucum(data: bytes) -> tuple[str, dict, set]:
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('XML entities and document types are not supported')
    root = ET.fromstring(data)
    if root.tag != '{' + NAMESPACE + '}root' or not root.get('version'):
        raise ValueError('expected versioned UCUM essence XML')
    atoms, prefixes = {}, set()
    for item in root:
        kind = item.tag.removeprefix('{' + NAMESPACE + '}')
        if kind not in ('prefix', 'base-unit', 'unit'):
            continue
        code = item.get('Code')
        if not code or len(code) > 100:
            raise ValueError('malformed UCUM code')
        if kind == 'prefix':
            if code in prefixes:
                raise ValueError('duplicate UCUM prefix')
            prefixes.add(code)
        else:
            if code in atoms or item.get('isMetric', 'no') not in ('yes', 'no'):
                raise ValueError('duplicate or malformed UCUM atom')
            atoms[code] = kind == 'base-unit' or item.get('isMetric') == 'yes'
    if not atoms:
        raise ValueError('UCUM contains no atoms')
    return root.attrib['version'], atoms, prefixes


def install(loinc_zip: Path, loinc_version: str, ucum_xml: Path, destination: Path) -> dict:
    """Validate catalogs and publish immutable originals plus an integrity receipt."""
    if not loinc_version.strip() or len(loinc_version) > 100:
        raise ValueError('a LOINC release identifier is required')
    destination = safe_path(destination, exists=False)
    if destination.exists():
        raise ValueError('destination already exists')
    loinc, ucum = read_bytes(loinc_zip), read_bytes(ucum_xml)
    catalog, translations = load_loinc(loinc)
    version, _, _ = load_ucum(ucum)
    manifest = {'format': 1, 'loinc_version': loinc_version, 'ucum_version': version,
                'artifacts': {'loinc.zip': digest(loinc), 'ucum.xml': digest(ucum)},
                'sources': {'loinc': 'https://loinc.org/downloads', 'ucum': 'https://ucum.org/docs/artifacts'}}
    temporary = Path(tempfile.mkdtemp(prefix='.terminology-', dir=destination.parent))
    try:
        (temporary / 'loinc.zip').write_bytes(loinc)
        (temporary / 'ucum.xml').write_bytes(ucum)
        (temporary / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        # mkdir reserves a fresh destination without replacing an existing directory.
        destination.mkdir()
        try:
            for member in temporary.iterdir():
                os.rename(member, destination / member.name)
        except OSError:
            shutil.rmtree(destination)
            raise
    finally:
        shutil.rmtree(temporary)
    return {'loinc_version': loinc_version, 'ucum_version': version,
            'codes': len(catalog), 'languages': sorted(translations)}


def catalog_pins(manifest: dict) -> dict:
    """Identify the selected immutable catalog without exposing loader state."""
    result = {key: manifest[key] for key in ('loinc_version', 'ucum_version', 'artifacts', 'manifest_sha256')}
    if 'vocabulary_version' in manifest:
        result['vocabulary_version'] = manifest['vocabulary_version']
    return result


def load_bundled_metadata(content: dict, manifest: dict, catalog: dict) -> list[dict]:
    """Validate retrieval-only aliases and release-pinned human reuse rules."""
    documents = {}
    for name in ('aliases.json', 'mappings.json'):
        documents[name] = json.loads(content[name], object_pairs_hook=unique_object,
                                     parse_float=Decimal, parse_constant=lambda _: invalid_json())
        if not isinstance(documents[name], dict) or documents[name].get('format') != 1:
            raise ValueError('unsupported alias or rule document')
    aliases, rules = documents['aliases.json'].get('aliases'), documents['mappings.json'].get('rules')
    if not isinstance(aliases, list) or not isinstance(rules, list):
        raise ValueError('expected alias and rule lists')
    identifiers = set()
    for alias in aliases:
        if not isinstance(alias, dict):
            raise ValueError('malformed retrieval alias')
        source, codes = alias.get('source'), alias.get('candidates')
        synonym_id = source.get('synonym_id') if isinstance(source, dict) else None
        if (any(not isinstance(alias.get(key), str) or not alias[key].strip() or len(alias[key]) > 1000
                for key in ('id', 'term'))
                or alias['id'] in identifiers or not tokens(alias['term'])
                or alias.get('language') not in ('en', 'pt-BR', 'und')
                or alias.get('review_status') != 'retrieval_only'
                or not isinstance(source, dict)
                or any(not isinstance(source.get(key), str) or not source[key].strip()
                       for key in ('name', 'metric'))
                or (isinstance(source, dict) and ('synonym_id' in source or source.get('name') == 'Janusmed')
                    and not ((isinstance(synonym_id, str) and synonym_id.strip())
                             or (type(synonym_id) is int and synonym_id >= 0)))
                or not isinstance(codes, list) or not codes
                or any(not isinstance(code, str) or code not in catalog for code in codes)
                or len(codes) != len(set(codes))):
            raise ValueError('malformed or unresolved retrieval alias')
        identifiers.add(alias['id'])
    for rule in rules:
        if (not isinstance(rule, dict) or not isinstance(rule.get('loinc'), str)
                or rule['loinc'] not in catalog
                or catalog[rule['loinc']]['STATUS'] != 'ACTIVE'
                or rule_reuse(rule, rule, rule.get('conditions', {}), manifest) != 'eligible_for_human_review'):
            raise ValueError('malformed or unresolved release-pinned rule')
    return aliases


def _load_package(package: Path) -> tuple[dict, dict, dict, dict, set]:
    package = safe_path(package, exists=False)
    if not package.is_dir():
        raise ValueError('expected a package directory')
    manifest_bytes = read_bytes(package / 'manifest.json', MAX_JSON)
    manifest = json.loads(manifest_bytes, object_pairs_hook=unique_object,
                          parse_float=Decimal, parse_constant=lambda _: invalid_json())
    if not isinstance(manifest, dict):
        raise ValueError('expected a package manifest object')
    bundled = manifest.get('format') == 2
    artifacts = manifest.get('artifacts')
    required = {'loinc.csv', 'pt-BR.csv', 'ucum.xml', 'aliases.json', 'mappings.json'} if bundled else {'loinc.zip', 'ucum.xml'}
    if (not isinstance(artifacts, dict) or len(artifacts) > 1000
            or (bundled and (manifest.get('kind') != 'bundled'
                            or not isinstance(manifest.get('vocabulary_version'), str)
                            or not manifest['vocabulary_version'].strip()
                            or manifest.get('languages') != ['en', 'pt-BR']))
            or (not bundled and manifest.get('format') != 1)):
        raise ValueError('unsupported package manifest')
    for name in artifacts:
        path = PurePosixPath(name)
        if (not name or path.is_absolute() or '..' in path.parts or '\\' in name
                or str(path) != name):
            raise ValueError('unsafe artifact name')
    if (not required.issubset(artifacts)
            or (not bundled and set(artifacts) != required)
            or (bundled and (not any(name.startswith('LICENSES/') for name in artifacts)
                             or any(name not in required and not name.startswith('LICENSES/') for name in artifacts)))):
        raise ValueError('unsupported package manifest artifacts')
    content = {}
    total = 0
    for name, expected in artifacts.items():
        if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
            raise ValueError('invalid artifact SHA256 digest')
        limit = min(MAX_JSON if name.endswith('.json') else MAX_FILE, MAX_TOTAL - total)
        data = read_bytes(package / name, limit)
        total += len(data)
        if digest(data) != expected:
            raise ValueError('installed artifact SHA256 mismatch')
        content[name] = data
    if bundled:
        rows = csv_rows(content['loinc.csv'], set(AXES.values()) | {'LOINC_NUM', 'STATUS', 'LONG_COMMON_NAME'})
        catalog = {row['LOINC_NUM']: row for row in rows}
        if any(row['STATUS'] not in ('ACTIVE', 'TRIAL', 'DISCOURAGED', 'DEPRECATED') for row in rows):
            raise ValueError('unknown LOINC status')
        translated = csv_rows(content['pt-BR.csv'], {'LOINC_NUM'})
        if any(row['LOINC_NUM'] not in catalog for row in translated):
            raise ValueError('linguistic variant references unknown LOINC')
        translations = {'pt-BR': {'member': 'pt-BR.csv', 'rows': {row['LOINC_NUM']: row for row in translated}}}
    else:
        catalog, translations = load_loinc(content['loinc.zip'])
    version, atoms, prefixes = load_ucum(content['ucum.xml'])
    if (version != manifest.get('ucum_version') or not isinstance(manifest.get('loinc_version'), str)
            or not manifest['loinc_version'].strip()):
        raise ValueError('catalog version differs from manifest')
    manifest['manifest_sha256'] = digest(manifest_bytes)
    manifest['_aliases'] = load_bundled_metadata(content, manifest, catalog) if bundled else []
    manifest['_diagnostics'] = []
    manifest['_alias_catalog'] = catalog_pins(manifest)
    return manifest, catalog, translations, atoms, prefixes


def load_package(package: Path | None = None) -> tuple[dict, dict, dict, dict, set]:
    """Load local catalogs; reconcile bundled discovery aliases with an explicit ZIP.

    One selected catalog controls every candidate and proposal. Only retrieval
    aliases can complement another release, after code, axes and status agree;
    bundled human mapping rules are never transferred.
    """
    manifest, catalog, translations, atoms, prefixes = _load_package(DEFAULT_PACKAGE if package is None else package)
    if manifest['format'] == 1 and DEFAULT_PACKAGE.exists():
        bundled, baseline, _, _, _ = _load_package(DEFAULT_PACKAGE)
        if bundled['format'] != 2:
            raise ValueError('expected a bundled default vocabulary')
        compatible = set()
        for code in sorted({code for alias in bundled['_aliases'] for code in alias['candidates']}):
            row = catalog.get(code)
            if row is None:
                reason = 'code_absent'
            elif row['STATUS'] != 'ACTIVE' or row['STATUS'] != baseline[code]['STATUS']:
                reason = 'status_mismatch'
            elif any(row[column] != baseline[code][column] for column in AXES.values()):
                reason = 'axes_mismatch'
            else:
                compatible.add(code)
                continue
            manifest['_diagnostics'].append({'code': code, 'reason': reason,
                                             'source_loinc_version': bundled['loinc_version'],
                                             'selected_loinc_version': manifest['loinc_version']})
        manifest['_aliases'] = [dict(alias, candidates=[code for code in alias['candidates'] if code in compatible])
                                for alias in bundled['_aliases']]
        manifest['_alias_catalog'] = catalog_pins(bundled)
    return manifest, catalog, translations, atoms, prefixes


def tokens(text: str) -> set[str]:
    plain = ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))
    return set(re.findall(r'[^\W_]+|[%#+/<>=]', plain))


def candidate(row: dict, translations: dict, manifest: dict) -> dict:
    code = row['LOINC_NUM']
    translated = {language: item['rows'][code] for language, item in translations.items() if code in item['rows']}
    return {'code': code, 'display': row['LONG_COMMON_NAME'], 'status': row['STATUS'],
            'axes': {axis: row[column] for axis, column in AXES.items()},
            'translations': translated,
            'example_units': row.get('EXAMPLE_UNITS', ''),
            'example_ucum_units': [unit for unit in row.get('EXAMPLE_UCUM_UNITS', '').split(';') if unit],
            'provenance': {'loinc_version': manifest['loinc_version'],
                           'loinc_sha256': manifest['artifacts']['loinc.csv' if manifest['format'] == 2 else 'loinc.zip'],
                           'translation_members': {lang: translations[lang]['member'] for lang in translated}}}


def search(package: Path | None = None, text: str = '', limit: int = 20, **filters: str) -> dict:
    """Find active candidates, ordering exact alias matches before broad names.

    Stable code order within each group is retrieval order, never clinical rank.
    Counts describe all matching active, axis-filtered candidates before limit.
    """
    if not 1 <= limit <= 100 or not text.strip() or len(text) > 1000:
        raise ValueError('search requires text and a limit from 1 to 100')
    manifest, catalog, translations, _, _ = load_package(package)
    wanted, found = tokens(text), []
    if not wanted:
        raise ValueError('search requires at least one word')
    matches = {}
    for alias in manifest['_aliases']:
        if wanted == tokens(alias['term']):
            match = {key: alias[key] for key in ('id', 'term', 'language', 'source', 'review_status')}
            match.update(catalog=manifest['_alias_catalog'], selected_loinc_version=manifest['loinc_version'],
                         revalidated=manifest['format'] == 1)
            for code in alias['candidates']:
                matches.setdefault(code, []).append(match)
    for row in catalog.values():
        if row['STATUS'] != 'ACTIVE' or any(row[AXES[key]] != value for key, value in filters.items() if value is not None):
            continue
        result = candidate(row, translations, manifest)
        names = [row.get(name, '') for name in (*NAMES, 'COMPONENT', 'DisplayName')]
        for translated in result['translations'].values():
            names.extend(translated.get(name, '') for name in (*NAMES, 'COMPONENT'))
        alias_matches = matches.get(row['LOINC_NUM'], [])
        if alias_matches or wanted.issubset(tokens(' '.join(names))):
            result['alias_matches'] = alias_matches
            found.append(result)
    return {'candidates': sorted(found, key=lambda row: (not row['alias_matches'], row['code']))[:limit],
            'total_candidates': len(found), 'truncated': len(found) > limit,
            'catalog': dict(catalog_pins(manifest), diagnostics=manifest['_diagnostics']),
            'examples_are_whitelist': False, 'human_review_required': True}


def unit_syntax(code: str, atoms: dict, prefixes: set) -> dict:
    """Validate the documented subset without conversion or dimensional claims."""
    result = {'status': 'invalid', 'dimensional_compatibility_checked': False}
    if not isinstance(code, str) or not code or len(code) > 256 or not code.isascii() or any(c.isspace() for c in code):
        return result
    if any(c in code for c in '{}='):
        result['status'] = 'not_checked'
        return result
    position = 0

    def simple(symbol: str) -> bool:
        if symbol in atoms:
            return True
        return any(symbol.startswith(prefix) and atoms.get(symbol[len(prefix):], False)
                   for prefix in sorted(prefixes, key=len, reverse=True))

    def term(depth: int = 0) -> bool:
        nonlocal position
        if depth > 12:
            return False
        if depth == 0 and position < len(code) and code[position] == '/':
            position += 1
        if not component(depth):
            return False
        while position < len(code) and code[position] in './':
            position += 1
            if not component(depth):
                return False
        return True

    def component(depth: int) -> bool:
        nonlocal position
        if position >= len(code):
            return False
        if code[position] == '(':
            position += 1
            if not term(depth + 1) or position >= len(code) or code[position] != ')':
                return False
            position += 1
            return True
        start, bracket = position, False
        while position < len(code):
            char = code[position]
            if char == '[':
                if bracket:
                    return False
                bracket = True
            elif char == ']':
                if not bracket:
                    return False
                bracket = False
            elif char in './()' and not bracket:
                break
            position += 1
        symbol = code[start:position]
        if bracket or not symbol:
            return False
        if simple(symbol) or re.fullmatch('[0-9]+', symbol):
            return True
        # Try an exponent suffix; signs cannot occur inside atom symbols.
        match = re.fullmatch(r'(.+?)([+-]?[0-9]+)', symbol)
        return bool(match and len(match[2].lstrip('+-')) <= 6 and simple(match[1]))

    if term() and position == len(code):
        result['status'] = 'valid_syntax'
    return result


def rule_reuse(rule: object, proposal: dict, context: dict, manifest: dict) -> str:
    if rule is None:
        return 'not_requested'
    if not isinstance(rule, dict):
        return 'ineligible'
    conditions = rule.get('conditions')
    keys = {'lab', 'local_test', 'specimen', 'method', 'unit'}
    metadata = ('approved_by', 'approved_at', 'version', 'evidence')
    if (rule.get('decision') != 'approved' or not all(isinstance(rule.get(key), str) and rule[key].strip() for key in metadata)
            or not isinstance(conditions, dict) or set(conditions) != keys
            or any(not isinstance(conditions[key], str) or (not conditions[key] and key != 'method') for key in keys)
            or any(context.get(key) != conditions[key] for key in keys)
            or rule.get('loinc_version') != manifest['loinc_version']
            or rule.get('loinc') != proposal.get('loinc') or rule.get('ucum') != proposal.get('ucum')):
        return 'ineligible'
    try:
        date.fromisoformat(rule['approved_at'])
    except ValueError:
        return 'ineligible'
    return 'eligible_for_human_review'


def check(package: Path | None, observation: Path, proposal: Path) -> dict:
    """Report proposed native codings and unresolved evidence for human review."""
    manifest, catalog, translations, atoms, prefixes = load_package(package)
    source, proposed = read_json(observation), read_json(proposal)
    if source.get('resourceType') != 'Observation' or not isinstance(source.get('code'), dict):
        raise ValueError('expected a native FHIR Observation with code')
    context, evidence = proposed.get('context', {}), proposed.get('evidence', {})
    if not isinstance(context, dict) or not isinstance(evidence, dict) or not isinstance(proposed.get('loinc'), str):
        raise ValueError('proposal requires loinc and context/evidence objects')
    codings = source['code'].get('coding', [])
    quantity = source.get('valueQuantity', {})
    if (not isinstance(codings, list) or any(not isinstance(coding, dict) for coding in codings)
            or not isinstance(quantity, dict)):
        raise ValueError('malformed native coding or quantity')
    issues, additions = [], {}
    row = catalog.get(proposed['loinc'])
    if row is None:
        issues.append('unresolved: LOINC code absent from pinned catalog')
    else:
        if row['STATUS'] != 'ACTIVE':
            issues.append('incompatible: LOINC status is ' + row['STATUS'])
        for axis, column in AXES.items():
            value, citation = context.get(axis), evidence.get(axis)
            if not isinstance(value, str) or (not value and axis != 'method'):
                issues.append('unresolved: missing ' + axis + ' context')
            elif value != row[column]:
                issues.append('incompatible: ' + axis + ' contradicts LOINC axis')
            if not isinstance(citation, str) or not citation.strip():
                issues.append('unresolved: missing ' + axis + ' evidence')
        for coding in codings:
            if coding.get('system') == 'http://loinc.org':
                if coding.get('code') != proposed['loinc']:
                    issues.append('incompatible: existing source LOINC coding differs')
                if coding.get('version') not in (None, manifest['loinc_version']):
                    issues.append('unresolved: source LOINC version differs')
        additions['code.coding'] = {'system': 'http://loinc.org', 'version': manifest['loinc_version'],
                                    'code': proposed['loinc'], 'display': row['LONG_COMMON_NAME']}
    if 'unit' in context and context['unit'] != quantity.get('unit'):
        issues.append('incompatible: context unit differs from original quantity unit')
    unit = {'status': 'not_requested', 'dimensional_compatibility_checked': False}
    if 'ucum' in proposed:
        if not isinstance(quantity.get('unit'), str) or not quantity['unit'].strip():
            issues.append('unresolved: UCUM proposal requires original quantity unit')
        if not isinstance(context.get('unit'), str) or not context['unit'].strip():
            issues.append('unresolved: missing unit context')
        if not isinstance(evidence.get('unit'), str) or not evidence['unit'].strip():
            issues.append('unresolved: missing unit assignment evidence')
        unit = unit_syntax(proposed['ucum'], atoms, prefixes)
        unit['example_match'] = bool(row and proposed['ucum'] in row.get('EXAMPLE_UCUM_UNITS', '').split(';'))
        unit['example_match_proves_compatibility'] = False
        if unit['status'] != 'valid_syntax':
            issues.append('unresolved: UCUM syntax ' + unit['status'])
        if (('system' in quantity or 'code' in quantity)
                and (quantity.get('system') != 'http://unitsofmeasure.org'
                     or quantity.get('code') != proposed['ucum'])):
            issues.append('incompatible: existing source UCUM or other quantity coding differs')
        additions['valueQuantity'] = {'system': 'http://unitsofmeasure.org', 'code': proposed['ucum']}
    reuse = rule_reuse(proposed.get('rule'), proposed, context, manifest)
    if issues and reuse == 'eligible_for_human_review':
        reuse = 'ineligible'
    return {'decision': 'human_review_required', 'issues': issues, 'proposed_additions': additions if not issues else {},
            'source_codings': codings,
            'source_quantity_coding': {key: quantity[key] for key in ('system', 'code') if key in quantity},
            'unit': unit, 'rule_reuse': reuse,
            'evidence': evidence, 'context': context,
            'catalog': dict(catalog_pins(manifest), diagnostics=manifest['_diagnostics'])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    acquire = commands.add_parser('fetch', help='explicit pinned HTTPS acquisition')
    for flag in ('url', 'sha256', 'output'):
        acquire.add_argument('--' + flag, required=True)
    setup = commands.add_parser('install', help='retain and validate local official artifacts')
    for flag in ('loinc-zip', 'loinc-version', 'ucum-xml', 'destination'):
        setup.add_argument('--' + flag, required=True)
    find = commands.add_parser('search', help='offline multilingual candidate search')
    find.add_argument('--package', type=Path)
    find.add_argument('--text', required=True)
    find.add_argument('--limit', type=int, default=20)
    for axis in AXES:
        find.add_argument('--' + axis)
    review = commands.add_parser('check', help='review-only native FHIR coding proposals')
    review.add_argument('--package', type=Path)
    for flag in ('observation', 'proposal'):
        review.add_argument('--' + flag, required=True, type=Path)
    args = vars(parser.parse_args())
    command = args.pop('command')
    try:
        if command == 'fetch':
            args['output'] = Path(args['output'])
            result = fetch(**args)
        elif command == 'install':
            for key in ('loinc_zip', 'ucum_xml', 'destination'):
                args[key] = Path(args[key])
            result = install(**args)
        elif command == 'search':
            result = search(**args)
        else:
            result = check(**args)
    except UnicodeError:
        print('terminology: unsupported input encoding', file=sys.stderr)
        return 2
    except ValueError as error:
        # Our policy errors contain no clinical content; JSON errors report positions.
        print('terminology: ' + str(error), file=sys.stderr)
        return 2
    except (OSError, KeyError, TypeError, RecursionError, csv.Error, zipfile.BadZipFile, ET.ParseError, urllib.error.URLError):
        # Do not echo untrusted content, paths, or remote response bodies.
        print('terminology: malformed input or unavailable acquisition', file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
