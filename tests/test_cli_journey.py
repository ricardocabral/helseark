import json
import os
from pathlib import Path
import subprocess
import sys

from helseark.archive import open_vault, resolve
from helseark.contracts import ResourceRef


def run(*args, env=None):
    return subprocess.run([sys.executable, "-m", "helseark.cli", *map(str, args)], capture_output=True, env=env)


def test_init_and_explicit_person_journey(tmp_path):
    root = tmp_path / "family"
    initialized = run("init", root, "--json")
    assert initialized.returncode == 0, initialized.stderr
    assert json.loads(initialized.stdout)["vaultId"]
    assert (root / "definitions/LICENSE").read_bytes() == (Path(__file__).resolve().parents[1] / "LICENSE").read_bytes()
    created = run("--vault", root, "person", "add", "--name", "Alex Example", "--birth-date", "1990", "--json")
    assert created.returncode == 0, created.stderr
    person = json.loads(created.stdout)["personId"]
    assert resolve(open_vault(root), person, ResourceRef("Patient", person))["birthDate"] == "1990"
    assert initialized.stderr == created.stderr == b""
    other = run("person", "add", "--name", "Alex Example", "--json", env={**os.environ, "HELSEARK_VAULT": str(root)})
    assert other.returncode == 0
    assert json.loads(other.stdout)["personId"] != person


def test_errors_are_safe_and_exit_codes_distinguish_versions(tmp_path):
    absent = run("person", "add", "--name", "PRIVATE NAME", "--json", env={k:v for k,v in os.environ.items() if k != "HELSEARK_VAULT"})
    assert absent.returncode == 2
    assert absent.stdout == b""
    assert b"PRIVATE" not in absent.stderr
    root = tmp_path / "vault"
    assert run("init", root).returncode == 0
    assert run("init", root).returncode == 2
    invalid = run("--vault", root, "person", "add", "--name", "PRIVATE NAME", "--birth-date", "no", "--json")
    assert invalid.returncode == 2
    assert b"PRIVATE" not in invalid.stderr
    config = json.loads((root / "vault.json").read_text())
    config["fhirVersion"] = "5.0.0"
    (root / "vault.json").write_text(json.dumps(config))
    incompatible = run("--vault", root, "person", "add", "--name", "Alex")
    assert incompatible.returncode == 6
    assert b"UNSUPPORTED_VERSION" in incompatible.stderr


import pytest
from helseark.archive import init_vault, add_person
from helseark.contracts import PersonDraft


@pytest.mark.parametrize('filename', ['vault.json', 'change.json', 'proposal.json', 'evidence.json', 'review.json', 'validation.json', 'resource'])
@pytest.mark.parametrize('raw', [b'{"PRIVATE RECORD":', b'{"x":1,"x":2}'])
def test_corrupt_stored_json_is_exit5(tmp_path, filename, raw):
    vault = init_vault(tmp_path / 'PRIVATE ROOT')
    person = add_person(vault, PersonDraft('PRIVATE NAME'))
    directory = next((vault.root / 'people' / person / 'accepted').iterdir())
    path = vault.root / filename if filename == 'vault.json' else directory / filename
    if filename == 'resource':
        path = next((directory / 'resources').iterdir())
    path.write_bytes(raw)
    result = run('--vault', vault.root, 'person', 'add', '--name', 'PRIVATE NAME', '--json')
    assert result.returncode == 5, result.stderr
    assert result.stdout == b''
    assert b'PRIVATE' not in result.stderr
    assert json.loads(result.stderr)['details']['path'] == path.relative_to(vault.root).as_posix()


@pytest.mark.parametrize('filename,pin', [(name, 'contractVersion') for name in ('change.json', 'proposal.json', 'evidence.json', 'review.json')] + [(name, pin) for name in ('change.json', 'proposal.json') for pin in ('fhirVersion', 'profileVersion', 'serializationVersion', 'archiveFormatVersion', 'agentKitVersion', 'agentKitLockSha256', 'definitionLockSha256')])
def test_unsupported_genesis_envelope_versions_are_exit6(tmp_path, filename, pin):
    vault = init_vault(tmp_path / 'vault')
    person = add_person(vault, PersonDraft('Synthetic'))
    directory = next((vault.root / 'people' / person / 'accepted').iterdir())
    path = directory / filename
    value = json.loads(path.read_bytes())
    if pin == 'contractVersion':
        value[pin] = 'future'
    else:
        value['versions'][pin] = 'future'
    path.write_text(json.dumps(value))
    result = run('--vault', vault.root, 'person', 'add', '--name', 'PRIVATE NAME', '--json')
    assert result.returncode == 6, result.stderr
    assert result.stdout == b'' and b'PRIVATE' not in result.stderr


def test_candidate_prepare_human_review_commit_cli(tmp_path):
    from test_intake import supplied_candidate
    from helseark.serialization import decode_json, encode_json
    from helseark.archive import head
    vault,person,_,_,candidate=supplied_candidate(tmp_path)
    prepared=run('--vault',vault.root,'candidate','prepare',candidate.path,'--person',person,'--json')
    assert prepared.returncode==0,prepared.stderr
    path=json.loads(prepared.stdout)['path']
    accepted=vault.root/'people'/person/'accepted'
    original={p.relative_to(accepted):p.read_bytes() for p in accepted.rglob('*') if p.is_file()}
    base=head(vault,person)
    unreviewed=run('--vault',vault.root,'candidate','commit',path,'--person',person,'--json')
    assert unreviewed.returncode==3,unreviewed.stderr
    assert unreviewed.stdout==b''
    assert json.loads(unreviewed.stderr)=={
        'code':'REVIEW_REQUIRED',
        'message':'No review decision recorded. Run candidate review with --person and --decision before candidate commit.',
        'details':{}}
    assert head(vault,person)==base
    assert {p.relative_to(accepted):p.read_bytes() for p in accepted.rglob('*') if p.is_file()}==original
    view=run('--vault',vault.root,'candidate','review',path,'--person',person,'--json')
    assert view.returncode==0,view.stderr
    issues=json.loads(view.stdout)['issues']
    decision=tmp_path/'human-decision.json'
    decision.write_bytes(encode_json({'confirmedPerson':True,'decision':'accept-with-acknowledged-limitations',
        'reviewerLabel':'synthetic human','acknowledgedIssues':[{'code':i['code'],'resourceRef':i['resourceRef'],'issueId':i['issueId'],'reason':'Checked original synthetic report'} for i in issues if i['severity'] in ('review','warning')]}))
    approved=run('--vault',vault.root,'candidate','review',path,'--person',person,'--decision',decision,'--json')
    assert approved.returncode==0,approved.stderr
    from pathlib import Path
    receipt_path=Path(path)/'review.json'; original_receipt=receipt_path.read_bytes()
    receipt_path.write_bytes(original_receipt+b' ')
    altered=run('--vault',vault.root,'candidate','commit',path,'--person',person,'--json')
    assert altered.returncode==3,altered.stderr
    receipt_path.write_bytes(original_receipt)
    wrong=run('--vault',vault.root,'candidate','commit',path,'--person','00000000-0000-4000-8000-000000000001','--json')
    assert wrong.returncode==2 and head(vault,person).sequence==1
    for expected in ('committed','already-accepted'):
        committed=run('--vault',vault.root,'candidate','commit',path,'--person',person,'--json')
        assert committed.returncode==0,committed.stderr
        assert json.loads(committed.stdout)['disposition']==expected
    retry=run('--vault',vault.root,'candidate','prepare',candidate.path,'--person',person,'--json')
    assert retry.returncode==0,retry.stderr
    assert json.loads(retry.stdout)['disposition']=='already-accepted'
    import shutil
    retained=json.loads(retry.stdout)['path']
    original={p.relative_to(accepted):p.read_bytes() for p in accepted.rglob('*') if p.is_file()}
    shutil.rmtree(vault.root/'work'); shutil.rmtree(vault.root/'.runtime')
    shutil.rmtree(candidate.path)
    retry=run('--vault',vault.root,'candidate','commit',retained,'--person',person,'--json')
    assert retry.returncode==0,retry.stderr
    assert json.loads(retry.stdout)['disposition']=='already-accepted'
    assert {p.relative_to(accepted):p.read_bytes() for p in accepted.rglob('*') if p.is_file()}==original


@pytest.mark.parametrize('mutation,exit_code,code',[
    ('forged',3,'REVIEW_MISMATCH'),
    ('malformed-receipt',5,'INTEGRITY'),
    ('symlink-receipt',2,'UNSAFE_PATH'),
    ('missing-receipt',5,'INTEGRITY'),
    ('missing-control',3,'REVIEW_MISMATCH'),
    ('malformed-control',5,'INTEGRITY'),
    ('changed-control',3,'REVIEW_MISMATCH'),
    ('symlink-control',2,'UNSAFE_PATH'),
    ('accepted-missing-receipt',5,'INTEGRITY'),
])
def test_candidate_commit_rejects_damaged_review_authority(tmp_path,mutation,exit_code,code):
    from helseark.archive import head
    from test_intake import supplied_candidate
    from test_review import prepare, approve
    vault,person,_,_,candidate=supplied_candidate(tmp_path)
    proposal=prepare(vault,candidate)
    receipt=approve(vault,proposal)
    control=vault.root/'.runtime/reviews'/f'{proposal.proposalSha256}.json'
    path=proposal.path
    if mutation=='accepted-missing-receipt':
        committed=run('--vault',vault.root,'candidate','commit',path,'--person',person,'--json')
        assert committed.returncode==0,committed.stderr
        result=json.loads(committed.stdout)['head']
        path=vault.root/'people'/person/'accepted'/f"{result['sequence']:08d}-{result['transactionId']}"
    accepted=vault.root/'people'/person/'accepted'
    base=head(vault,person)
    if mutation in ('missing-receipt','accepted-missing-receipt'):
        (path/'review.json').unlink()
        if mutation=='accepted-missing-receipt':
            import shutil
            shutil.rmtree(vault.root/'work'); shutil.rmtree(vault.root/'.runtime')
    elif mutation=='forged':
        # Even a schema-valid receipt cannot authorize itself without host control.
        value=json.loads(receipt.path.read_bytes())
        value['reviewer']['label']='forged synthetic reviewer'
        receipt.path.write_text(json.dumps(value))
        control.unlink()
    elif mutation=='malformed-receipt':
        receipt.path.write_bytes(b'{')
    elif mutation in ('missing-control','malformed-control','changed-control'):
        if mutation=='missing-control': control.unlink()
        else: control.write_bytes(b'{' if mutation=='malformed-control' else b'{"receiptSha256":"forged"}')
    else:
        target=receipt.path if mutation=='symlink-receipt' else control
        saved=tmp_path/'saved.json'; saved.write_bytes(target.read_bytes())
        target.unlink(); target.symlink_to(saved)
    original={p.relative_to(accepted):p.read_bytes() for p in accepted.rglob('*') if p.is_file()}
    result=run('--vault',vault.root,'candidate','commit',path,'--person',person,'--json')
    assert result.returncode==exit_code,result.stderr
    assert result.stdout==b'' and json.loads(result.stderr)['code']==code
    assert {p.relative_to(accepted):p.read_bytes() for p in accepted.rglob('*') if p.is_file()}==original
    if mutation!='accepted-missing-receipt': assert head(vault,person)==base


@pytest.mark.parametrize('verb,filename',[('prepare','candidate.json'),('review','proposal.json'),('commit','proposal.json')])
def test_candidate_commands_fail_closed_on_non_object(tmp_path,verb,filename):
    from helseark.archive import init_vault, add_person
    from helseark.contracts import PersonDraft
    vault=init_vault(tmp_path/'vault');person=add_person(vault,PersonDraft('Synthetic'))
    path=tmp_path/'invalid';path.mkdir();(path/filename).write_text('[]\n')
    result=run('--vault',vault.root,'candidate',verb,path,'--person',person,'--json')
    assert result.returncode==2,result.stderr
    assert b'Traceback' not in result.stderr and not result.stdout

from test_query import corpus
from test_validation import good as clinical_candidate


def test_observations_timeline_record_cli_explicit_scope(corpus,tmp_path):
    from dataclasses import asdict
    from helseark.serialization import decode_json, encode_json
    v,c,ids,base,_=corpus
    result=run('--vault',v.root,'observations','--person',c.personId,'--label','Proteína C reativa — ultrassensível','--json')
    assert result.returncode==0,result.stderr
    rows=decode_json(result.stdout)
    assert len(rows)==7
    month=next(r for r in rows if r['resourceRef']['id']==ids['month'])
    assert b'0.050' in result.stdout and month['comparator']=='<' and month['timePrecision']=='month'
    assert month['sourceRefs']
    for command in ('observations','timeline','record'):
        missing=run('--vault',v.root,command,'--json')
        assert missing.returncode==2 and decode_json(missing.stderr)['code']=='INVALID_INPUT'
    timeline=run('--vault',v.root,'timeline','--person',c.personId,'--json')
    assert timeline.returncode==0,timeline.stderr
    assert any(r['status']=='entered-in-error' for r in decode_json(timeline.stdout))
    pin=tmp_path/'head.json';pin.write_bytes(encode_json(asdict(base)))
    ref=month['resourceRef'];reference=f"Observation/{ref['id']}/_history/{ref['versionId']}"
    record=run('--vault',v.root,'record','--person',c.personId,'--resource',reference,'--at-head',pin,'--json')
    assert record.returncode==0,record.stderr
    assert decode_json(record.stdout)['valueQuantity']['value'].as_tuple()==month['value']['value'].as_tuple()
    invalid=run('--vault',v.root,'observations','--person',c.personId,'--from-date','2026-02-30','--json')
    assert invalid.returncode==2 and decode_json(invalid.stderr)['code']=='INVALID_FILTER'



def test_query_cli_rejects_offset_normalization(corpus):
    from helseark.serialization import decode_json
    v, c, _, _, _ = corpus
    for offset in ('+00:60', '+01:99', '+02:60', '-00:60', '-02:60', '+14:01', '-14:01'):
        result = run('--vault', v.root, 'observations', '--person', c.personId,
                     '--from-date', '2024-02-29T00:00:00.00000001'+offset, '--json')
        assert result.returncode == 2
        assert decode_json(result.stderr)['code'] == 'INVALID_FILTER'
        assert not result.stdout

def test_correction_removal_restore_public_journey(tmp_path):
    from test_corrections import accepted
    from helseark.serialization import decode_json, encode_json
    from helseark.archive import head, _files, _read
    from helseark.serialization import hash_bytes
    from pathlib import Path
    v,p,old=accepted(tmp_path)
    other=next(path.name for path in (v.root/'people').iterdir() if path.name!=p)
    other_root=v.root/'people'/other
    unchanged={path:hash_bytes(_read(other_root,path)) for path in _files(other_root)}
    def cli(*args):
        result=run('--vault',v.root,*args,'--json')
        assert result.returncode==0,result.stderr
        return decode_json(result.stdout)
    draft=cli('correct','--person',p,'--resource',f"Observation/{old['id']}",'--reason','transcription: human checked source')
    path=Path(draft['path'])
    prepared=cli('candidate','prepare',path,'--person',p)
    view=cli('candidate','review',prepared['path'],'--person',p)
    decision=tmp_path/'decision.json'
    decision.write_bytes(encode_json({'confirmedPerson':True,'decision':'accept-with-acknowledged-limitations','reviewerLabel':'Synthetic human',
        'acknowledgedIssues':[{'code':i['code'],'resourceRef':i['resourceRef'],'issueId':i['issueId'],'reason':'Checked original synthetic source'} for i in view['issues'] if i['severity'] in ('review','warning')]}))
    cli('candidate','review',prepared['path'],'--person',p,'--decision',decision)
    cli('candidate','commit',prepared['path'],'--person',p)
    cli('observations','--person',p)
    backup=cli('backup','create','--out',tmp_path/'backup')
    assert backup['peopleCount']==2 and backup['resourceCount']>2
    plan=cli('erase','plan','--person',p,'--quarantine',tmp_path/'quarantine','--out',tmp_path/'plan.json')
    cli('erase','apply',tmp_path/'plan.json','--approve',plan['digest'])
    assert not (v.root/'people'/p).exists()
    cli('erase','restore',tmp_path/'quarantine','--approve',plan['digest'])
    assert head(v,p).changeSha256==plan['baseHeads'][p]['changeSha256']
    assert {path:hash_bytes(_read(other_root,path)) for path in _files(other_root)}==unchanged
    assert cli('doctor')['issues']==[]
