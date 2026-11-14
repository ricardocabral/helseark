"""Task5/6/7 integration: accepted facts, original receipts and scoped contexts."""
from dataclasses import asdict
from decimal import Decimal
import shutil

from helseark.archive import commit_candidate
from helseark.contracts import ContextRequest, ObservationFilter, ResourceRef
from helseark.agent_context import build_agent_context
from helseark.intake import prepare_candidate
from helseark.query import observations
from helseark.review import read_prepared, read_receipt
from helseark.serialization import decode_json, hash_bytes
from test_intake import supplied_candidate
from test_review import approve


def test_publication_query_context_share_exact_evidence_after_work_removal(tmp_path):
    vault, person, source, packet, candidate = supplied_candidate(tmp_path)
    receipts = {p: p.read_bytes() for p in source.assetPath.parent.glob('*.json')}
    prepared = prepare_candidate(vault, candidate)
    result = commit_candidate(vault, prepared, approve(vault, prepared))
    rows = list(observations(vault, person, ObservationFilter()))
    assert len(rows) == 2
    quantity = next(r for r in rows if r.comparator == '<')
    assert quantity.value['value'].as_tuple() == Decimal('0.050').as_tuple()
    assert quantity.effective == '2026-01' and quantity.timePrecision == 'month'
    assert quantity.status == 'final' and quantity.unit == 'mg/L'
    assert quantity.method == {'text': 'M1'}
    assert quantity.referenceRanges == [{'text': '0,00 - 0,10 mg/L'}]
    assert any(r.value == 'not detected' for r in rows)
    assert all(r.sourceRefs for r in rows)
    selected = build_agent_context(vault, person, 'query', ContextRequest(
        resourceRefs=(ResourceRef('Observation', quantity.resourceRef.id, quantity.resourceRef.versionId),),
        sourceHashes=(source.sourceSha256,), fromDate='2026-01-14', toDate='2026-01-14'), tmp_path/'query-context')
    assert selected.returnedCount == 1
    assert selected.evidencePaths
    for row in rows:
        for citation in row.sourceRefs:
            raw = (vault.root/citation.evidencePath).read_bytes()
            assert hash_bytes(raw) == citation.evidenceSha256
            entry = decode_json(raw)['entries'][int(citation.entryPointer.split('/')[-1])]
            ref = row.resourceRef
            assert entry['target']['reference'] == f'Observation/{ref.id}/_history/{ref.versionId}'
    accepted = next((vault.root/'people'/person/'accepted').glob(f'*{result.head.transactionId}'))
    original = {p: p.read_bytes() for p in accepted.rglob('*') if p.is_file()}
    shutil.rmtree(vault.root/'work')
    shutil.rmtree(vault.root/'.runtime')
    shutil.rmtree(candidate.path)
    shutil.rmtree(packet.path)
    retained = read_prepared(vault, accepted)
    retry = commit_candidate(vault, retained, read_receipt(vault, retained))
    assert retry.disposition == 'already-accepted' and retry.head == result.head
    assert [asdict(r) for r in observations(vault,person,ObservationFilter())] == [asdict(r) for r in rows]
    assert all(p.read_bytes() == raw for p, raw in {**original, **receipts}.items())
