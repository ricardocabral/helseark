"""Optional, network-confined official validator over a derived snapshot.

Only this boundary knows Java, package extraction, CLI flags and OperationOutcome.
It never supplies clinical facts, fetches artifacts or edits accepted resources.
"""
from dataclasses import asdict, replace
from decimal import Decimal
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
import time

from .contracts import (ArchiveError, CheckCoverage, Issue, PreparedProposal,
                        ValidationReport, ValidatorConfig, Vault)
from .serialization import decode_json, encode_json, hash_bytes


def _error(code, message):
    raise ArchiveError(code, message)


def _bytes(path, limit):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        _error('VALIDATOR_MISSING_ARTIFACT', 'Required local validator artifact is missing or unsafe.')
    return path.read_bytes()


def _lock():
    from .archive import _bundled_root
    return decode_json((_bundled_root()/'definitions/validator-lock.json').read_bytes())


def _network_command(command):
    if sys.platform == 'darwin' and Path('/usr/bin/sandbox-exec').exists():
        return ['/usr/bin/sandbox-exec', '-p', '(version 1)(allow default)(deny network*)', *command]
    if sys.platform.startswith('linux') and shutil.which('unshare'):
        return [shutil.which('unshare'), '--net', '--', *command]
    _error('VALIDATOR_NETWORK_POLICY', 'OS network confinement is unavailable; full validation is blocked.')


def _artifacts(config, home):
    lock = _lock()
    if (config.version != lock['version'] or config.executableSha256 != lock['executableSha256'] or
            hash_bytes(jar_data := _bytes(config.executablePath, 256*1024*1024)) != lock['executableSha256']):
        _error('VALIDATOR_DIGEST_MISMATCH', 'Validator version or executable digest does not match the qualified pin.')
    if type(config.timeoutSeconds) is not int or not 1 <= config.timeoutSeconds <= 600 or type(config.requireTerminology) is not bool:
        _error('INVALID_INPUT', 'Validator deadline must be 1–600 seconds and terminology policy boolean.')
    if not Path(config.javaPath).is_file() or not os.access(config.javaPath, os.X_OK):
        _error('VALIDATOR_UNAVAILABLE', 'Explicit local Java executable is unavailable.')
    # A private pathname isolates manifest Class-Path resolution. An immutable
    # same-filesystem hardlink avoids another 200 MB copy; never overwrite it.
    relocated=home.parent/'validator.jar'
    try:
        os.link(config.executablePath,relocated)
    except OSError:
        if relocated.exists() or relocated.is_symlink():
            _error('VALIDATOR_MISSING_ARTIFACT','Private validator pathname already exists.')
        with relocated.open('xb') as stream:stream.write(jar_data)
    directory = Path(config.packageDirectory)
    expected = {p['filename'] for p in lock['packages']}
    if directory.is_symlink() or not directory.is_dir() or {p.name for p in directory.iterdir()} != expected:
        _error('VALIDATOR_MISSING_ARTIFACT', 'Package directory must contain exactly the pinned TGZ closure.')
    import io
    cache = home/'.fhir/packages'
    cache.mkdir(parents=True)
    for pin in lock['packages']:
        data = _bytes(directory/pin['filename'], 24*1024*1024)
        if len(data) != pin['bytes'] or hash_bytes(data) != pin['sha256']:
            _error('VALIDATOR_PACKAGE_MISMATCH', 'Validator package digest mismatch.')
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
            members = archive.getmembers()
            if len(members) > 15000 or sum(m.size for m in members) > 160*1024*1024:
                _error('VALIDATOR_PACKAGE_MISMATCH', 'Validator package exceeds extraction bounds.')
            for member in members:
                parts = PurePosixPath(member.name).parts
                if not parts or parts[0] != 'package' or '..' in parts or not (member.isfile() or member.isdir()):
                    _error('VALIDATOR_PACKAGE_MISMATCH', 'Unsafe validator package member.')
            target = cache/(pin['name']+'#'+pin['version'])
            target.mkdir()
            archive.extractall(target, filter='data')
            metadata = decode_json((target/'package/package.json').read_bytes())
            if (metadata['name'], metadata['version'], metadata['license']) != (pin['name'],pin['version'],pin['license']):
                _error('VALIDATOR_PACKAGE_MISMATCH', 'Validator package identity mismatch.')
    return lock


def _context(vault, proposal):
    from .archive import _json, _read
    from .validation import validate_proposal
    from .portability import fhir_collection
    baseline = validate_proposal(vault, proposal.path)
    if baseline.checkedProposalSha256 != proposal.proposalSha256 or any(i.severity == 'error' for i in baseline.issues) or any(c.result == 'failed' for c in baseline.coverage):
        _error('VALIDATION_BLOCKED', 'Baseline proposal checks must pass before official validation.')
    value = _json(proposal.path, 'proposal.json')
    if value['personId'] != proposal.personId or value['baseChangeSha256'] != (proposal.base.changeSha256 if proposal.base else None):
        _error('PERSON_MISMATCH', 'Validator proposal person differs from selected person.')
    resources = tuple(_json(proposal.path, item['path']) for item in value['resources'])
    bundle, mapping = fhir_collection(vault, proposal.personId, at=proposal.base, proposedResources=resources)
    return baseline, bundle, mapping


def _profiles(vault, config, destination):
    from .archive import _read
    # The current vault's pins are authoritative, including historical archives.
    lock = decode_json(_read(vault.root, 'definitions/lock.json'))
    versions = ('0.1.0', '0.2.0') if vault.config.profileVersion == '0.2.0' else ('0.1.0',)
    entries = [e for a in lock['artifacts'] for e in a['files']
               if any(e['path'].startswith(f'profiles/r4/{version}/StructureDefinition-') for version in versions)]
    if len(entries) != (15 if len(versions) == 2 else 6):
        _error('VALIDATOR_PROFILE_MISMATCH', 'Complete selected-vault profile pins are required.')
    pins = []
    for entry in entries:
        name = Path(entry['path']).name
        relative = Path(entry['path']).relative_to('profiles/r4') if len(versions) == 2 else Path(name)
        data = _bytes(Path(config.profileDirectory)/relative, 1024*1024)
        if hash_bytes(data) != entry['sha256']:
            _error('VALIDATOR_PROFILE_MISMATCH', 'Profiles must match the selected vault definition lock.')
        (destination/(Path(entry['path']).parent.name+'-'+name)).write_bytes(data)
        pins.append({'path':entry['path'], 'sha256':entry['sha256']})
    return pins


def _outcome(data, returncode, mapping=None):
    try:
        outcome = decode_json(data)
        if outcome['resourceType'] != 'OperationOutcome' or not isinstance(outcome['issue'], list) or not outcome['issue']:
            raise ValueError
        issues = []
        counts = {'errors':0, 'warnings':0, 'information':0}
        for index, item in enumerate(outcome['issue']):
            severity = item['severity']
            if severity not in ('fatal','error','warning','information') or not isinstance(item['code'], str):
                raise ValueError
            if severity in ('fatal','error'): counts['errors'] += 1
            elif severity == 'warning': counts['warnings'] += 1
            else: counts['information'] += 1
            # Diagnostics can contain private source values. Retain only bounded
            # locations as pointers when the tool actually supplies JSON Pointer.
            locations = item.get('expression', item.get('location', []))
            pointer = None
            resource_ref = None
            for location in locations:
                if isinstance(location,str):
                    location = re.sub(r'/\*[A-Za-z]+/[0-9a-f-]+\*/','',location)
                if isinstance(location, str) and re.fullmatch(r'Bundle(?:[.][A-Za-z][A-Za-z0-9]*(?:\[[0-9]+\])?)+', location):
                    pointer = re.sub(r'\[([0-9]+)\]', r'/\1', location[len('Bundle'):].replace('.', '/'))
                    break
                if isinstance(location,str) and location.startswith('/') and len(location)<1024:
                    pointer = location
                    break
            match = re.match(r'^/entry/([0-9]+)/resource(?=/|$)',pointer or '')
            if match and mapping is not None and int(match[1]) < len(mapping):
                target = mapping[int(match[1])]
                resource_ref = f"{target['resourceType']}/{target['id']}/_history/{target['versionId']}"
                pointer = pointer[match.end():]
            issues.append(Issue('OFFICIAL_FHIR_'+severity.upper()+'_'+str(index), 'error' if severity in ('fatal','error') else 'info' if severity == 'information' else 'warning',
                                pointer, resource_ref, 'Official validator reported '+severity+'; inspect the private OperationOutcome for details.'))
        if returncode not in (0,1) or (returncode == 0) != (counts['errors'] == 0):
            _error('VALIDATOR_PROCESS_FAILED', 'Validator exit status and machine outcome disagree.')
        return tuple(issues), counts
    except (KeyError, TypeError, ValueError, ArchiveError) as error:
        if isinstance(error, ArchiveError) and error.code == 'VALIDATOR_PROCESS_FAILED': raise
        _error('VALIDATOR_MALFORMED_OUTPUT', 'Validator did not produce a valid machine OperationOutcome.')


def validate_with_official_tool(proposal: PreparedProposal, config: ValidatorConfig | Path | None, *, vault: Vault) -> ValidationReport:
    """Return an enriched report bound to exact proposal + derived Bundle bytes.

    The explicit vault provides patient scope and the pinned snapshot closure.
    A config path is loaded only after revoking previous pending authority.
    Missing config blocks an explicitly requested full check. Baseline APIs never
    call Java. Terminology is deliberately unavailable in this qualified mode.
    """
    execution_id,config=_begin_execution(vault,proposal,config)
    if (proposal.path/'review.json').exists():
        _error('REVIEW_MISMATCH','Official validation must precede human review; prepare a fresh proposal.')
    from .archive import _json
    if not (vault.root/'definitions/schemas/0.1.1/review.schema.json').is_file() or 'officialValidationAuthority' not in _json(vault.root,'definitions/schemas/0.1.1/review.schema.json')['properties']:
        _error('UNSUPPORTED_VERSION','Pinned review contract cannot retain authenticated executions; preserve old pins and use a compatible workflow.')
    baseline, bundle, mapping = _context(vault, proposal)
    runtime_inputs=_runtime_inputs(config)
    issues, counts, run = _run_bundle(vault, bundle, mapping, config)
    coverage = tuple(c for c in baseline.coverage if c.family not in ('full-fhir','terminology')) + (
        CheckCoverage('full-fhir','failed' if counts['errors'] else 'passed',
                      f"{len(bundle['entry'])} resources; {counts['errors']} errors; {counts['warnings']} warnings; pinned R4 profiles/invariants only."),
        CheckCoverage('terminology','failed' if config.requireTerminology else 'not-checked',
                      'Unavailable terminology: -tx n/a; no licensed terminology completeness claim.'))
    if config.requireTerminology:
        issues += (Issue('TERMINOLOGY_UNAVAILABLE','error',None,None,'Required terminology coverage is unavailable in the qualified offline mode.'),)
    report = replace(baseline, coverage=coverage, issues=baseline.issues+issues, officialRun=run)
    from .archive import _schema
    from .agent_context import document
    _schema(vault,'validation',document(report))
    if runtime_inputs!=_runtime_inputs(config):
        _error('VALIDATOR_RUNTIME_CHANGED','Execution inputs changed while the actual validator ran.')
    _retain_execution(vault,proposal,report,runtime_inputs,baseline,execution_id)
    return report


def _run_bundle(vault, bundle, mapping, config):
    """Execute a prebuilt closed context; public calls always run baseline first."""
    with TemporaryDirectory(prefix='helseark-validator-') as temporary:
        root = Path(temporary)
        home = root/'home'; home.mkdir()
        lock = _artifacts(config, home)
        profiles = root/'profiles'; profiles.mkdir()
        profile_pins = _profiles(vault, config, profiles)
        source = root/'context.json'; source.write_bytes(encode_json(bundle))
        output = root/'outcome.json'
        command = [str(Path(config.javaPath).absolute()), '-Xmx512m', '-Duser.home='+str(home),
                   '-jar', str(root/'validator.jar'), str(source), '-version','4.0.1',
                   '-ig',str(profiles), '-tx','n/a', '-txCache',str(root/'tx'),
                   '-no-http-access','-disable-default-resource-fetcher','-output',str(output)]
        environment={'PATH':'/usr/bin:/bin','HOME':str(home),'LANG':'C.UTF-8'}
        process_command=_network_command(command)
        started = time.monotonic()
        try:
            with (root/'process.log').open('wb') as log:
                result = subprocess.run(process_command, cwd=root,
                    env=environment,
                    stdout=log, stderr=subprocess.STDOUT, timeout=config.timeoutSeconds, check=False)
            if not output.is_file():
                _error('VALIDATOR_PROCESS_FAILED', 'Validator failed before producing its machine outcome (check Java and OS confinement).')
            data = _bytes(output, 8*1024*1024)
            issues, counts = _outcome(data, result.returncode, mapping)
        except subprocess.TimeoutExpired:
            _error('VALIDATOR_TIMEOUT', 'Official validator exceeded the explicit configured deadline.')
        except OSError:
            _error('VALIDATOR_UNAVAILABLE', 'Could not execute the configured offline validator.')
        run = {'version':lock['version'], 'executableSha256':lock['executableSha256'],
               'javaSha256':hash_bytes(_bytes(config.javaPath, 64*1024*1024)),
               'packages':lock['packages'], 'profiles':profile_pins,
               'elapsedSeconds':Decimal(str(round(time.monotonic()-started,3))),
               'timeoutSeconds':config.timeoutSeconds, 'exitCode':result.returncode,
               'bundleSha256':hash_bytes(source.read_bytes()), 'mapping':mapping,
               'outcomeSha256':hash_bytes(encode_json(decode_json(data))),
               'operationOutcome':decode_json(data), 'counts':counts,
               'networkPolicy':'macOS sandbox deny network*' if sys.platform == 'darwin' else 'Linux isolated network namespace',
               'command':command, 'processCommand':process_command, 'environment':environment, 'javaRelease':_bytes(Path(config.javaPath).parent.parent/'release',16384).decode('utf-8'),
               'arguments':['-version','4.0.1','-ig','<pinned-profiles>','-tx','n/a','-no-http-access','-disable-default-resource-fetcher'],
               'resourceCount':len(bundle['entry']), 'requireTerminology':config.requireTerminology}
    return issues, counts, run


def verify_recorded_run(vault, proposal):
    """Rebind retained tool evidence without rerunning Java or changing elapsed time."""
    verify_pending_execution(vault,proposal)
    baseline, bundle, mapping = _context(vault, proposal)
    run = proposal.validation.officialRun
    if run['bundleSha256'] != hash_bytes(encode_json(bundle)) or run['mapping'] != mapping or run['version'] != _lock()['version'] or run['executableSha256'] != _lock()['executableSha256']:
        _error('REVIEW_MISMATCH', 'Official validation context or pins changed.')
    from .archive import _read
    definition_lock = decode_json(_read(vault.root,'definitions/lock.json'))
    versions = ('0.1.0', '0.2.0') if vault.config.profileVersion == '0.2.0' else ('0.1.0',)
    expected_profiles = [{'path':e['path'],'sha256':e['sha256']} for a in definition_lock['artifacts'] for e in a['files']
                         if any(e['path'].startswith(f'profiles/r4/{version}/StructureDefinition-') for version in versions)]
    if run['profiles'] != expected_profiles:
        _error('REVIEW_MISMATCH', 'Official validation profile pins changed.')
    if run['packages'] != _lock()['packages'] or run['resourceCount'] != len(bundle['entry']):
        _error('REVIEW_MISMATCH', 'Official validation package or resource counts changed.')
    if run['outcomeSha256'] != hash_bytes(encode_json(run['operationOutcome'])):
        _error('REVIEW_MISMATCH', 'Official validation outcome changed.')
    issues, counts = _outcome(encode_json(run['operationOutcome']), run['exitCode'], run['mapping'])
    if run['counts'] != counts:
        _error('REVIEW_MISMATCH', 'Official validation outcome counts changed.')
    official = tuple(i for i in proposal.validation.issues if i.code.startswith('OFFICIAL_FHIR_'))
    if official != issues:
        _error('REVIEW_MISMATCH', 'Official validation issues differ from the retained outcome.')
    full = [c for c in proposal.validation.coverage if c.family == 'full-fhir']
    terminology = [c for c in proposal.validation.coverage if c.family == 'terminology']
    if len(full) != 1 or full[0].result != ('failed' if counts['errors'] else 'passed') or len(terminology) != 1 or terminology[0].result != ('failed' if run['requireTerminology'] else 'not-checked'):
        _error('REVIEW_MISMATCH', 'Official validation coverage differs from its evidence.')
    return baseline


def load_validator_config(path: Path) -> ValidatorConfig:
    """Strict host configuration reader; accepts no shell fragments or extra keys."""
    try:
        value = decode_json(_bytes(path, 16384))
        expected = {'executablePath','executableSha256','version','packageDirectory',
                    'profileDirectory','timeoutSeconds','requireTerminology','javaPath'}
        if not isinstance(value,dict) or set(value) != expected:
            raise ValueError
        for name in ('executablePath','packageDirectory','profileDirectory','javaPath'):
            if not isinstance(value[name],str) or not Path(value[name]).is_absolute():
                raise ValueError
            value[name] = Path(value[name])
        if type(value['timeoutSeconds']) is not int or not 1 <= value['timeoutSeconds'] <= 600 or type(value['requireTerminology']) is not bool:
            raise ValueError
        if value['version'] != _lock()['version'] or value['executableSha256'] != _lock()['executableSha256']:
            _error('VALIDATOR_DIGEST_MISMATCH', 'Configuration differs from the qualified validator pin.')
        return ValidatorConfig(**value)
    except (ValueError, TypeError, KeyError):
        _error('INVALID_INPUT', 'Validator configuration requires exact documented fields and absolute paths.')


def _runtime_inputs(config: ValidatorConfig) -> dict:
    """Read-only identity of configured inputs, including the complete JRE."""
    from .agent_context import document
    import hashlib
    files, total = [], 0
    def retain(artifact, root, relative):
        nonlocal total
        path = root/relative
        if path.is_symlink():
            if not path.resolve().is_relative_to(root.resolve()):
                _error('VALIDATOR_RUNTIME_CHANGED','Runtime symlink leaves the selected runtime.')
            files.append({'artifact':artifact,'path':relative,'kind':'symlink','target':os.readlink(path)})
            return
        if not path.is_file() or path.stat().st_size > 256*1024*1024:
            _error('VALIDATOR_RUNTIME_CHANGED','Configured runtime input is missing or unsafe.')
        digest = hashlib.sha256(); size = 0
        with path.open('rb') as stream:
            while block := stream.read(1024*1024):
                size += len(block); total += len(block)
                if size > 256*1024*1024 or total > 1024*1024*1024:
                    _error('VALIDATOR_RUNTIME_CHANGED','Runtime input inventory exceeds supported bounds.')
                digest.update(block)
        files.append({'artifact':artifact,'path':relative,'kind':'file','sha256':digest.hexdigest(),'size':size})
    jar=Path(config.executablePath).absolute()
    retain('validator',jar.parent,jar.name)
    packages=Path(config.packageDirectory)
    if packages.is_symlink() or not packages.is_dir() or {p.name for p in packages.iterdir()} != {p['filename'] for p in _lock()['packages']}:
        _error('VALIDATOR_RUNTIME_CHANGED','Configured package directory no longer has the exact artifact closure.')
    for pin in _lock()['packages']:
        retain('package',packages,pin['filename'])
    profiles=Path(config.profileDirectory)
    for path in sorted(profiles.rglob('StructureDefinition-*.json')):
        retain('profile',profiles,path.relative_to(profiles).as_posix())
    home=Path(config.javaPath).absolute().parent.parent
    if not (home/'release').is_file():
        _error('VALIDATOR_RUNTIME_CHANGED','Selected Java home has no release metadata.')
    if not os.access(config.javaPath,os.X_OK):
        _error('VALIDATOR_RUNTIME_CHANGED','Configured Java executable is unavailable.')
    runtime_root=home.parent.parent if home.name=='Home' and home.parent.name=='Contents' else home
    count=0
    def unreadable(error):
        _error('VALIDATOR_RUNTIME_CHANGED','Java runtime inventory cannot be read completely.')
    for directory, dirs, names in os.walk(runtime_root,followlinks=False,onerror=unreadable):
        count+=len(dirs)+len(names)
        if count>10000:
            _error('VALIDATOR_RUNTIME_CHANGED','Java runtime inventory exceeds supported bounds.')
        for name in sorted([*dirs,*names]):
            path=Path(directory)/name
            if path.is_symlink() or path.is_file():
                retain('java-runtime',runtime_root,path.relative_to(runtime_root).as_posix())
    return {'configuration':document(config),'files':sorted(files,key=lambda f:(f['artifact'],f['path']))}


def _preparation_control(vault, proposal):
    from .archive import _safe,_json
    path=_safe(vault.root,f'.runtime/prepared/{proposal.proposalSha256}.json')
    if not path.is_file():
        _error('VALIDATOR_AUTHORITY_REQUIRED','Original host preparation authority is missing; prepare and review again.')
    value=_json(path.parent,path.name)
    expected = {'candidatePath','validationAuthorityVersion','baselineValidationSha256','officialExecutionId','officialRequestSha256'}
    if (value.get('validationAuthorityVersion')!=1 or set(value) not in (expected, expected | {'personId'}) or
            ('personId' in value and value['personId'] != proposal.personId)):
        _error('VALIDATOR_AUTHORITY_REQUIRED','Legacy or ambiguous pending workflow requires fresh preparation; no execution was attested.')
    return path,value


def _execution_scope(vault, proposal_value):
    selected={k:proposal_value.get(k) for k in ('resources','assets','inputs','evidenceSha256','importReview')}
    return {'vaultId':vault.config.vaultId,'personId':proposal_value['personId'],
            'proposalSha256':hash_bytes(encode_json(proposal_value)),
            'candidateSha256':proposal_value['candidateSha256'],
            'baseChangeSha256':proposal_value['baseChangeSha256'],
            'definitionLockSha256':vault.config.definitionLockSha256,
            'sourceInventorySha256':hash_bytes(encode_json(selected))}


def verify_retained_execution(vault, proposal_value, validation, authority, *, allow_legacy=False):
    """Check immutable receipt binding without work, current tools or Java.

    Only verified accepted history may permit a readonly legacy report whose
    original pinned schema predates execution authority. No attestation is made.
    """
    from .archive import _json,_schema
    run=validation.get('officialRun')
    if run is None:
        if authority is not None:
            _error('VALIDATOR_AUTHORITY_MISMATCH','Execution authority cannot be detached from its original report.')
        return False
    if authority is None:
        schema=_json(vault.root,'definitions/schemas/0.1.0/review.schema.json')
        if allow_legacy and 'officialValidationAuthority' not in schema['properties']:
            return False
        _error('VALIDATOR_AUTHORITY_REQUIRED','Original official execution authority is missing.')
    _schema(vault,'official-validation-authority',authority)
    expected={**_execution_scope(vault,proposal_value),
              'requestSha256':hash_bytes(encode_json(authority['runtimeInputs']['configuration'])),
              'reportSha256':hash_bytes(encode_json(validation)),
              'officialRunSha256':hash_bytes(encode_json(run)),
              'outcomeSha256':hash_bytes(encode_json(run['operationOutcome'])),
              'bundleSha256':run['bundleSha256'],'requireTerminology':run['requireTerminology']}
    if any(authority.get(k)!=v for k,v in expected.items()) or authority['runtimeInputsSha256'] != hash_bytes(encode_json(authority['runtimeInputs'])):
        _error('VALIDATOR_AUTHORITY_MISMATCH','Report, execution inputs, policy or proposal scope differ from original host authority.')
    config=authority['runtimeInputs']['configuration']
    if (config['requireTerminology']!=run['requireTerminology'] or config['timeoutSeconds']!=run['timeoutSeconds'] or
            config['executableSha256']!=run['executableSha256'] or config['version']!=run['version']):
        _error('VALIDATOR_AUTHORITY_MISMATCH','Required execution policy or runtime identity changed.')
    return True


def verify_pending_execution(vault, proposal):
    """Authenticate pending reports against independently host-held state."""
    from .archive import _safe,_json
    from .agent_context import document
    _,control=_preparation_control(vault,proposal)
    path=_safe(vault.root,f'.runtime/official-validation/{proposal.proposalSha256}.json')
    if control['officialExecutionId'] is None and control['officialRequestSha256'] is None and not path.exists():
        if proposal.validation.officialRun is not None:
            _error('VALIDATOR_AUTHORITY_REQUIRED','An old report cannot supply original execution authority; rerun the actual tool.')
        if hash_bytes(encode_json(document(proposal.validation)))!=control['baselineValidationSha256']:
            _error('VALIDATOR_AUTHORITY_MISMATCH','Baseline report differs from original host preparation.')
        return None
    if not path.is_file():
        _error('VALIDATOR_AUTHORITY_REQUIRED','Original host official execution authority is missing.')
    authority=_json(path.parent,path.name)
    if authority.get('executionId')!=control['officialExecutionId'] or authority.get('requestSha256')!=control['officialRequestSha256']:
        _error('VALIDATOR_AUTHORITY_MISMATCH','Host execution generation changed or was only partially retained.')
    verify_retained_execution(vault,_json(proposal.path,'proposal.json'),document(proposal.validation),authority)
    config=dict(authority['runtimeInputs']['configuration'])
    for field in ('executablePath','packageDirectory','profileDirectory','javaPath'):
        config[field]=Path(config[field])
    try:
        inputs=_runtime_inputs(ValidatorConfig(**config))
    except (OSError,ArchiveError):
        _error('VALIDATOR_RUNTIME_CHANGED','Original pending execution inputs are unavailable or changed.')
    if inputs!=authority['runtimeInputs']:
        _error('VALIDATOR_RUNTIME_CHANGED','Configured tool, complete Java runtime, packages, profiles or policy changed after execution.')
    if (proposal.path/'review.json').exists():
        review=_json(proposal.path,'review.json')
        if review.get('officialValidationAuthority')!=authority:
            _error('VALIDATOR_AUTHORITY_MISMATCH','Execution changed after the human decision; prepare and review again.')
    return authority


def _retain_execution(vault, proposal, report, runtime_inputs, baseline, execution_id):
    """Host-only post-execution checkpoint; never adopts an existing report."""
    from .archive import _safe,_json,_schema,_writer_lock
    from .agent_context import document
    from .validation import verify_baseline_reconciliation
    with _writer_lock(vault):
        _,control=_preparation_control(vault,proposal)
        request_sha=hash_bytes(encode_json(runtime_inputs['configuration']))
        if control['officialExecutionId']!=execution_id or control['officialRequestSha256']!=request_sha:
            _error('VALIDATOR_AUTHORITY_MISMATCH','A newer execution request superseded this result.')
        fresh,bundle,_=_context(vault,proposal)
        verify_baseline_reconciliation(fresh,report)
        if hash_bytes(encode_json(bundle))!=report.officialRun['bundleSha256'] or fresh!=baseline:
            _error('VALIDATOR_AUTHORITY_MISMATCH','Inputs or baseline changed during actual validation.')
        authority={'authorityVersion':1,'executionId':execution_id,'requestSha256':request_sha,
                   **_execution_scope(vault,_json(proposal.path,'proposal.json')),
                   'reportSha256':hash_bytes(encode_json(document(report))),
                   'officialRunSha256':hash_bytes(encode_json(report.officialRun)),
                   'outcomeSha256':report.officialRun['outcomeSha256'],
                   'bundleSha256':report.officialRun['bundleSha256'],
                   'baselineSha256':hash_bytes(encode_json(document(baseline))),
                   'requireTerminology':report.officialRun['requireTerminology'],
                   'runtimeInputs':runtime_inputs,'runtimeInputsSha256':hash_bytes(encode_json(runtime_inputs))}
        _schema(vault,'official-validation-authority',authority)
        path=_safe(vault.root,f'.runtime/official-validation/{proposal.proposalSha256}.json')
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        _replace_host_control(path,authority)


def _replace_host_control(target, value):
    """Atomic durable host checkpoints; interrupted multi-file state fails closed."""
    from tempfile import NamedTemporaryFile
    from .archive import _sync_directory
    temporary=None
    try:
        with NamedTemporaryFile(dir=target.parent,delete=False) as stream:
            temporary=Path(stream.name);stream.write(encode_json(value));stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,target);_sync_directory(target.parent)
    except OSError:
        _error('IO_ERROR','Original execution authority could not be retained; no result was authorized.')
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)


def _begin_execution(vault, proposal, config):
    """Resolve pending scope, revoke, then resolve the requested configuration.

    A generation with a null request digest is an unresolved/failed request,
    never successful execution authority. Only the actual runner can retain it.
    """
    from uuid import uuid4
    from .archive import _writer_lock,_safe,_json,_read,_schema
    from .agent_context import document
    if proposal is None or vault is None:
        _error('INVALID_INPUT','An explicit vault and prepared proposal are required.')
    execution_id=str(uuid4())
    with _writer_lock(vault):
        # Identity/path authorization precedes mutation; baseline/resource/runtime
        # checks follow it. Editable copies cannot revoke the original proposal.
        value=_json(proposal.path,'proposal.json');_schema(vault,'proposal',value)
        expected=_safe(vault.root,f"work/proposals/{value['transactionId']}")
        if (Path(proposal.path).absolute()!=expected.absolute() or
                hash_bytes(_read(proposal.path,'proposal.json'))!=proposal.proposalSha256 or
                value['personId']!=proposal.personId or value['candidateSha256']!=proposal.candidateSha256 or
                value['baseChangeSha256']!=(proposal.base.changeSha256 if proposal.base else None)):
            _error('REVIEW_MISMATCH','Request does not identify the original pending proposal.')
        path,control=_preparation_control(vault,proposal)
        if proposal.candidatePath is None or str(proposal.candidatePath)!=control['candidatePath']:
            _error('REVIEW_MISMATCH','Request differs from original host preparation scope.')
        control['officialExecutionId']=execution_id
        control['officialRequestSha256']=None
        _replace_host_control(path,control)
        if isinstance(config,Path):
            config=load_validator_config(config)
        if config is None:
            _error('VALIDATOR_UNAVAILABLE','Required full check has no explicit validator configuration.')
        control['officialRequestSha256']=hash_bytes(encode_json(document(config)))
        _replace_host_control(path,control)
    return execution_id,config
