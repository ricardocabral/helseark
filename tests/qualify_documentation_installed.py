"""Run a copy outside the checkout with a final installed wheel's Python.

Usage: python qualify_documentation_installed.py NEW_WORK CHECKOUT
Records bounded Python read-method telemetry; never claims complete process I/O.
"""
from pathlib import Path
import builtins
import io
import json
import os
import re
import shutil
import subprocess
import sys
from urllib.parse import unquote


def check_links(root):
    """Check real local targets and GitHub-style heading fragments, offline."""
    count = 0
    for page in ([root] if root.is_file() else sorted(root.rglob('*.md'))):
        if 'internal' in page.relative_to(root.parent if root.is_file() else root).parts:
            continue
        for target in re.findall(r'\]\(([^)]+)\)', page.read_text()):
            if '://' in target or target.startswith(('mailto:', '#')):
                if not target.startswith('#'):
                    continue
            path, _, fragment = unquote(target).partition('#')
            linked = (page.parent/path).resolve() if path else page
            assert linked.exists(), (page, target)
            if fragment and linked.is_file() and linked.suffix == '.md':
                seen = {}
                anchors = []
                for heading in re.findall(r'^#{1,6}\s+(.+)$', linked.read_text(), re.M):
                    slug = re.sub(r'[^\w\- ]', '', heading.replace('`', '').lower()).replace(' ', '-')
                    n = seen.get(slug, 0); seen[slug] = n+1
                    anchors.append(slug if n == 0 else f'{slug}-{n}')
                assert fragment in anchors, (page, target, anchors)
            count += 1
    return count


def reader(work, vault, person, other, checkout):
    from helseark.archive import open_definitions
    from helseark.agent_context import build_agent_context, render_task_prompt, document
    from helseark.contracts import ContextRequest, ResourceRef, ArchiveError
    from helseark.serialization import decode_json, hash_bytes
    reads, denied, opened_paths = [], [], []
    phase = 'bootstrap'
    roots = [checkout, vault/'people'/other]
    original_open, original_io = builtins.open, io.open

    def audit(event, args):
        if event.startswith(('socket.', 'urllib.')):
            denied.append(event)
            raise RuntimeError('denied network')
        if event in ('open', 'os.listdir', 'os.scandir') and args and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).absolute()
            if any(path.is_relative_to(root) for root in roots):
                denied.append(str(path))
                raise RuntimeError('denied checkout/other person')
            if event == 'open': opened_paths.append(str(path))
    sys.addaudithook(audit)

    class Traced:
        def __init__(self, handle, path): self.handle, self.path = handle, path
        def __getattr__(self, key): return getattr(self.handle, key)
        def __enter__(self): self.handle.__enter__(); return self
        def __exit__(self, *args): return self.handle.__exit__(*args)
        def record(self, data, start):
            size = len(data.encode('utf-8') if isinstance(data, str) else data)
            if size: reads.append({'path': self.path, 'offset':start, 'bytes': size, 'phase':phase})
            return data
        def read(self, *args):
            start = self.handle.tell()
            return self.record(self.handle.read(*args), start)
        def readline(self, *args):
            start = self.handle.tell()
            return self.record(self.handle.readline(*args), start)
        def readinto(self, buffer):
            start = self.handle.tell()
            size = self.handle.readinto(buffer)
            if size: reads.append({'path': self.path, 'offset':start, 'bytes': size, 'phase':phase})
            return size
        def __iter__(self): return self
        def __next__(self):
            data = self.readline()
            if not data: raise StopIteration
            return data
    def opener(fn):
        def opened(path, *args, **kwargs):
            handle = fn(path, *args, **kwargs)
            mode = args[0] if args else kwargs.get('mode', 'r')
            if isinstance(path, (str, bytes, Path)) and ('r' in mode or '+' in mode):
                return Traced(handle, str(Path(os.fsdecode(path)).absolute()))
            return handle
        return opened
    builtins.open, io.open = opener(original_open), opener(original_io)
    # Actual attempted operations are witnesses, excluded from successful read totals.
    import socket
    for action in [lambda: socket.socket(), lambda: (checkout/'pyproject.toml').read_bytes(),
                   lambda: (vault/'people'/other/'accepted').iterdir().__next__()]:
        try: action()
        except RuntimeError as error: assert 'denied' in str(error)
        else: raise AssertionError('guard did not deny witness')
    assert len(denied) == 3, denied
    entry = (vault/'AGENTS.md').read_text()
    config = decode_json((vault/'vault.json').read_bytes())
    kit = vault/'agent-kit'/config['agentKitVersion']
    assert f"agent-kit/{config['agentKitVersion']}/START-HERE.md" in entry
    assert hash_bytes((kit/'manifest.json').read_bytes()) == config['agentKitLockSha256']
    (kit/'START-HERE.md').read_text()
    (kit/'docs/index.md').read_text()
    phase = 'documentation-closure'
    assert check_links(kit/'docs') > 40
    assert check_links(vault/'definitions/docs') > 40
    manifest = decode_json((kit/'manifest.json').read_bytes())
    # Follow selected task routes; contributor instructions are never discovered.
    for task in ('import', 'query'):
        descriptor = next(t for t in manifest['tasks'] if t['id']==task)
        (kit/descriptor['skillPath']).read_text()
    phase = 'selected-contexts-and-rendering'
    v = open_definitions(vault)
    expected = decode_json((work/'expected.json').read_bytes())
    source = expected['source']
    ref = ResourceRef(**next(r for r in expected['rows'] if r['code']['text']=='Analyte Q')['resourceRef'])
    selected_refs = tuple(ResourceRef(**r['resourceRef']) for r in expected['rows'])
    packets = []
    for task, request, prompt, values in [
        ('import', ContextRequest(sourceHashes=(source,)), 'extract-report',
         {'source_data': {'text': 'Synthetic retained source only.'}, 'candidate_id': '99999999-9999-4999-8999-999999999999', 'identity_confirmed': True}),
        ('query', ContextRequest(resourceRefs=selected_refs, sourceHashes=(source,)), 'query-with-evidence', {'source_data': {'request': 'Read selected exact result with evidence.'}}),
    ]:
        context = build_agent_context(v, person, task, request, work/(task+'-context'))
        values['output_directory'] = str(work/(task+'-output'))
        rendered = render_task_prompt(context, prompt, values,
                                       trusted_context_sha256=context.trustedContextSha256)
        assert rendered.text and other not in rendered.text
        assert context.instructionBytes <= 32768 and context.dataBytes <= context.maxDataBytes
        assert context.continuation is None
        assert context.returnedCount == (0 if task=='import' else 2)
        for selected in (*context.selectedRecords, *context.evidencePaths):
            data = (context.path/selected.path).read_bytes()
            assert hash_bytes(data)==selected.sha256
        if task=='query':
            records = [decode_json((context.path/f.path).read_bytes()) for f in context.selectedRecords]
            assert {r['meta']['versionId'] for r in records} == {r.versionId for r in selected_refs}
            record = next(r for r in records if r['code']['text']=='Analyte Q')
            qualitative = next(r for r in records if r['code']['text']=='Qualitative')
            assert qualitative['valueString']=='not detected' and qualitative['status']=='final'
            assert qualitative['effectiveDateTime']=='2026-01'
            assert record['meta']['versionId'] == ref.versionId
            assert str(record['valueQuantity']['value'])=='0.050'
            assert record['valueQuantity']['comparator']=='<' and record['effectiveDateTime']=='2026-01'
            assert record['method']=={'text':'M1'} and record['status']=='final'
            assert record['referenceRange']==[{'text':'0,00 - 0,10 mg/L'}]
            projection = b''.join((context.path/e.path).read_bytes() for e in context.evidencePaths)
            assert source.encode() in projection and b'0,050' in projection and b'not detected' in projection
        else:
            assert len(context.selectedSources)==1 and context.selectedSources[0].sha256==source
        packets.append({'task':task, 'returnedCount':context.returnedCount, 'totalCount':context.totalCount,
                        'instructionBytes':context.instructionBytes, 'dataBytes':context.dataBytes,
                        'maxDataBytes':context.maxDataBytes, 'head':document(context.base)})
    # Remove/restore only this disposable archive's kit for explicit fail-closed probes.
    phase = 'kit-failure-probes'
    manifest_path=kit/'manifest.json'; saved=manifest_path.read_bytes()
    manifest_path.rename(kit/'manifest.unavailable')
    try:
        try: build_agent_context(v,person,'query',ContextRequest(),work/'missing')
        except ArchiveError as error: assert error.code == 'MISSING_KIT'
        else: raise AssertionError('missing kit accepted')
    finally: (kit/'manifest.unavailable').rename(manifest_path)
    manifest_path.write_bytes(saved+b' ')
    try:
        try: build_agent_context(v,person,'query',ContextRequest(),work/'mismatched')
        except ArchiveError as error: assert error.code == 'KIT_MISMATCH'
        else: raise AssertionError('mismatched kit accepted')
    finally: manifest_path.write_bytes(saved)
    from dataclasses import replace
    from helseark.contracts import Vault
    incompatible = Vault(v.root, replace(v.config, fhirVersion='5.0.0'))
    try: build_agent_context(incompatible,person,'query',ContextRequest(),work/'incompatible')
    except ArchiveError as error: assert error.code == 'UNSUPPORTED_VERSION'
    else: raise AssertionError('incompatible kit accepted')
    assert len(denied)==3, denied
    unique = {}
    for event in reads:
        unique.setdefault(event['path'], []).append((event['offset'], event['offset']+event['bytes']))
    unique_bytes = 0
    for intervals in unique.values():
        end = 0
        for start, stop in sorted(intervals):
            unique_bytes += max(0, stop-max(start,end))
            end = max(end,stop)
    assert not any(Path(e['path']).is_relative_to(vault/'people'/other) for e in reads)
    result = {'packets':packets, 'guardWitnesses':denied, 'orderedReadEvents':reads,
              'orderedOpenEvents':opened_paths, 'otherPersonSuccessfulReads':0,
              'readEvents':len(reads), 'uniquePaths':len(unique),
              'phases':{p:{'readEvents':sum(e['phase']==p for e in reads), 'totalReadBytes':sum(e['bytes'] for e in reads if e['phase']==p)} for p in sorted({e['phase'] for e in reads})},
              'totalReadBytes':sum(e['bytes'] for e in reads),
              'uniqueFileByteRangesRead':unique_bytes,
              'limits':'Python read/readline/readinto byte intervals after imports only (UTF-8 text for this corpus); not complete OS or implicit-agent I/O telemetry',
              'missingKit':'MISSING_KIT', 'modifiedKit':'KIT_MISMATCH','incompatibleKit':'UNSUPPORTED_VERSION'}
    builtins.open, io.open = original_open, original_io
    (work/'onboarding-evidence.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('orderedReadEvents','orderedOpenEvents')}))


def main():
    work, checkout = map(lambda p:Path(p).resolve(), sys.argv[1:3])
    if len(sys.argv)>3:
        reader(work, Path(sys.argv[3]), sys.argv[4], sys.argv[5], checkout)
        return
    work.mkdir(); os.chdir(work)
    import helseark.archive as archive
    from helseark.serialization import decode_json, encode_json, hash_bytes
    assert not Path(archive.__file__).resolve().is_relative_to(checkout)
    bundled = Path(sys.prefix)/'share/helseark'
    # Deny checkout/network for every child, including the documented CLI lesson.
    guard=work/'guard'; guard.mkdir()
    (guard/'sitecustomize.py').write_text('''import sys, os
from pathlib import Path
def guard(event,args):
    if event.startswith(('socket.','urllib.')): raise RuntimeError('denied network')
    if event in ('open','os.listdir','os.scandir') and args and isinstance(args[0],(str,bytes)):
        if Path(os.fsdecode(args[0])).absolute().is_relative_to(os.environ['DOCS_DENY']): raise RuntimeError('denied checkout')
sys.addaudithook(guard)
''')
    env={**os.environ,'PYTHONPATH':str(guard),'DOCS_DENY':str(checkout)}
    assert check_links(bundled/'README.md') >= 5
    assert check_links(bundled/'docs') > 40
    assert check_links(bundled/'agent-kit') > 40
    page=(bundled/'docs/tutorials/first-archive.md').read_text()
    code=page.split('```python\n',1)[1].split('```',1)[0]
    result=subprocess.run([sys.executable,'-c',code],input='SYNTHETIC\n',capture_output=True,text=True,env=env)
    (work/'tutorial.stdout').write_text(result.stdout)
    assert result.returncode==0, result.stderr
    assert 'Accepted 2 synthetic observations' in result.stdout
    def cli(*args):
        child=subprocess.run([sys.executable,'-m','helseark.cli',*map(str,args),'--json'],capture_output=True,env=env)
        assert child.returncode==0,child.stderr
        return decode_json(child.stdout)
    vault=work/'lesson-restored'
    person=next((vault/'people').iterdir()).name
    rows=cli('--vault',vault,'observations','--person',person)
    assert len(rows)==2
    other=cli('--vault',vault,'person','add','--name','Avery Synthetic')['personId']
    assert cli('--vault',vault,'observations','--person',other)==[]
    source=decode_json((work/'lesson-packet/intake.json').read_bytes())['source']['sourceSha256']
    # Retain only one additional full snapshot for the two-person drill.
    backup=work/'two-person-backup'; restored=work/'two-person-restored'
    before={str(p.relative_to(vault)):hash_bytes(p.read_bytes()) for p in (vault/'people').rglob('*') if p.is_file()}
    cli('--vault',vault,'backup','create','--out',backup)
    manifest=decode_json((backup/'export.json').read_bytes())
    assert len(manifest['people'])==2 and manifest['counts']['changes']==3 and manifest['counts']['assets']>0
    assert not cli('backup','verify',backup)['issues']
    cli('backup','restore',backup,'--into',restored)
    after={str(p.relative_to(restored)):hash_bytes(p.read_bytes()) for p in (restored/'people').rglob('*') if p.is_file()}
    assert before==after
    assert cli('--vault',restored,'observations','--person',person)==rows
    assert not cli('--vault',restored,'doctor')['issues']
    (work/'expected.json').write_bytes(encode_json({'rows':rows,'source':source}))
    child=subprocess.run([sys.executable,__file__,str(work),str(checkout),str(restored),person,other],
                          env={**env, 'PYTHONPATH':''},capture_output=True,text=True)
    assert child.returncode==0,child.stderr
    (work/'reader.stdout').write_text(child.stdout)
    # Verify reader failure probes restored all immutable authority and pins.
    assert after=={str(p.relative_to(restored)):hash_bytes(p.read_bytes()) for p in (restored/'people').rglob('*') if p.is_file()}
    assert not cli('--vault',restored,'doctor')['issues']
    print(json.dumps({'module':archive.__file__, 'people':2,'observations':2,
                      'counts':manifest['counts'],'acceptedSourceFiles':len(before),
                      'onboarding':json.loads((work/'onboarding-evidence.json').read_text())['packets']}))


if __name__=='__main__': main()
