"""Human decisions over exact prepared bytes; no source text grants authority.

Receipts are local consistency records, not signatures or human identity proof.
Callers must keep review decision input under approved-user workflow control.
"""
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from .contracts import Vault

from .contracts import (ArchiveError, PreparedProposal, ReviewDecision, ReviewReceipt,
                        ReviewView, ValidationReport, CheckCoverage, Issue, Head)
from .serialization import decode_json, encode_json, hash_bytes
from .archive import _read, _json, _schema, _safe, head, resolve
from .contracts import ResourceRef
from .validation import validate_proposal, verify_baseline_reconciliation
from .agent_context import document


def _blocked(report):
    if any(i.severity=='error' for i in report.issues) or any(c.result=='failed' for c in report.coverage):
        raise ArchiveError('VALIDATION_BLOCKED','Blocking validation failures cannot be acknowledged.')


def _review_issues(report: ValidationReport) -> tuple[dict, ...]:
    """Bind each distinct displayed issue to its exact report, without positions.

    Byte-identical issues are one limitation. Different severity, pointer, message
    or resource is a different limitation. Coverage gaps are explicit limitations.
    """
    digest = hash_bytes(encode_json(document(report)))
    issues = [asdict(i) for i in report.issues]
    issues.extend(asdict(Issue('VALIDATION_NOT_CHECKED', 'review',
        '/coverage/' + c.family.replace('~', '~0').replace('/', '~1'), None,
        c.reason or 'Validation family was not checked.'))
        for c in report.coverage if c.result == 'not-checked')
    unique = {}
    for issue in issues:
        identity = hash_bytes(encode_json({'version': 'exact-issue-v1',
                                         'validationSha256': digest, 'issue': issue}))
        unique[identity] = {**issue, 'issueId': identity}
    return tuple(unique.values())


def _accepted_change(vault, directory, digest, person):
    """Only verified canonical history grants readonly accepted/legacy status."""
    from .archive import _history
    return next((change for _,path,change in _history(vault,person)
                 if path.absolute()==Path(directory).absolute() and change['preparedContentSha256']==digest),None)


def read_prepared(vault, directory, *, candidate_path=None, base=None):
    """Reload exact prepared content; live candidate path comes only from host control."""
    directory=Path(directory).absolute()
    value=_json(directory,'proposal.json'); _schema(vault,'proposal',value)
    digest=hash_bytes(_read(directory,'proposal.json'))
    report=_json(directory,'validation.json'); _schema(vault,'validation',report)
    validation=ValidationReport(report['checkedProposalSha256'],tuple(CheckCoverage(**c) for c in report['coverage']),tuple(Issue(**i) for i in report['issues']),report.get('officialRun'))
    if base is None and value['baseChangeSha256'] is not None:
        from .archive import _history
        base=next((h for h,_,_ in _history(vault,value['personId']) if h.changeSha256==value['baseChangeSha256']),None)
        if base is None: raise ArchiveError('STALE_BASE','Prepared base is not in selected-person history.')
    if candidate_path is None:
        control=_safe(vault.root,f'.runtime/prepared/{digest}.json')
        if _accepted_change(vault,directory,digest,value['personId']) is None:
            if not control.exists():
                raise ArchiveError('REVIEW_MISMATCH','Original host preparation control is missing.')
            candidate_path=Path(decode_json(_read(control.parent,control.name))['candidatePath'])
    return PreparedProposal(directory,value['personId'],value['candidateSha256'],digest,base,validation,candidate_path)


def _verify_prepared(vault, proposal, *, current=True):
    from .intake import _candidate_inputs
    value=_json(proposal.path,'proposal.json')
    _schema(vault,'proposal',value)
    if (hash_bytes(_read(proposal.path,'proposal.json'))!=proposal.proposalSha256 or
        value['personId']!=proposal.personId or value['candidateSha256']!=proposal.candidateSha256 or
        value['baseChangeSha256']!=(proposal.base.changeSha256 if proposal.base else None)):
        raise ArchiveError('REVIEW_MISMATCH','Prepared identity or bytes changed.')
    if current and head(vault,proposal.personId)!=proposal.base:
        raise ArchiveError('STALE_BASE','Selected person changed after preparation.')
    for item in value['resources']:
        if hash_bytes(_read(proposal.path,item['path']))!=item['sha256']:
            raise ArchiveError('REVIEW_MISMATCH','Prepared resource changed.')
    if hash_bytes(_read(proposal.path,'evidence.json'))!=value['evidenceSha256']:
        raise ArchiveError('REVIEW_MISMATCH','Prepared evidence changed.')
    for item in value.get('inputs',[]):
        if hash_bytes(_read(proposal.path,item['path']))!=item['sha256']:
            raise ArchiveError('REVIEW_MISMATCH','Retained candidate input changed.')
    if proposal.candidatePath is None and current and 'importReview' in value:
        raise ArchiveError('REVIEW_MISMATCH','Original candidate control is required before publication.')
    if proposal.candidatePath is not None:
        _,digest=_candidate_inputs(proposal.candidatePath)
        if digest!=proposal.candidateSha256:
            raise ArchiveError('REVIEW_MISMATCH','Candidate changed after preparation.')
    for item in value.get('importReview',{}).get('bindings',[]):
        if hash_bytes(_read(vault.root,f"people/{proposal.personId}/{item['path']}"))!=item['sha256']:
            raise ArchiveError('REVIEW_MISMATCH','Retained source receipt changed.')
    raw=_read(proposal.path,'validation.json')
    if raw!=encode_json(document(proposal.validation)):
        raise ArchiveError('REVIEW_MISMATCH','Validation report changed.')
    _blocked(proposal.validation)
    if current:
        from .fhir_validator import verify_pending_execution, verify_recorded_run
        if proposal.validation.officialRun is not None:
            report=verify_recorded_run(vault,proposal)
        else:
            verify_pending_execution(vault,proposal)
            report=validate_proposal(vault,proposal.path)
        _blocked(report)
        verify_baseline_reconciliation(report,proposal.validation)
    return value


def render_review(vault: Vault, proposal: PreparedProposal) -> ReviewView:
    accepted=_accepted_change(vault,proposal.path,proposal.proposalSha256,proposal.personId) is not None
    value=_verify_prepared(vault,proposal,current=not accepted)
    resources=[_json(proposal.path,i['path']) for i in value['resources']]
    info=value.get('importReview',{})
    evidence=_json(proposal.path,'evidence.json')['entries']
    def source_evidence(entries, resource):
        logical=f"{resource['resourceType']}/{resource['id']}"
        exact=f"{logical}/_history/{resource['meta']['versionId']}"
        return tuple(e for e in entries if e['kind']=='source' and
                     e.get('target',{}).get('reference',e.get('resourceRef')) in (logical,exact))
    needed=set(info.get('omissions',[])) | set(info.get('duplicateCandidates',[]))
    needed.update(f"{i['type']}/{i['id']}" for i in value['resources'] if i['supersedesVersionId'])
    previous={}
    if needed and proposal.base:
        from .archive import _history
        for h,directory,change in _history(vault,proposal.personId):
            if h.sequence>proposal.base.sequence: break
            old_evidence=_json(directory,'evidence.json')['entries']
            for item in change['resources']:
                logical=f"{item['type']}/{item['id']}"
                if logical in needed:
                    resource=_json(directory,item['path'])
                    previous[logical]={'resource':resource,'evidence':source_evidence(old_evidence,resource)}
    revisions=[]
    for r,i in zip(resources,value['resources']):
        if i['supersedesVersionId']:
            old=previous[f"{i['type']}/{i['id']}"]
            revisions.append({'resource':r,'supersedesVersionId':i['supersedesVersionId'],
                              'previousResource':old['resource'],'previousEvidence':old['evidence'],
                              'evidence':source_evidence(evidence,r)})
    comparisons=[]
    for ref in info.get('duplicateCandidates',[]):
        old=previous[ref]
        for resource in resources:
            if (resource['resourceType']==old['resource']['resourceType']=='Observation' and
                resource['id']!=old['resource']['id'] and
                resource.get('code')==old['resource'].get('code') and
                resource.get('effectiveDateTime')==old['resource'].get('effectiveDateTime')):
                comparisons.append({'resource':resource,'evidence':source_evidence(evidence,resource),
                                    'previousResource':old['resource'],'previousEvidence':old['evidence']})
    omitted=tuple(previous[ref] for ref in info.get('omissions',[]))
    sources=[e for e in evidence if e['kind']=='source']
    sources.extend(e for old in previous.values() for e in old['evidence'])
    legacy=accepted and _json(proposal.path,'review.json')['contractVersion']=='0.1.0'
    patient=resolve(vault,proposal.personId,ResourceRef('Patient',proposal.personId),at=proposal.base)
    coverage=list(proposal.validation.coverage)
    if accepted and proposal.validation.officialRun is not None:
        authority=_json(proposal.path,'review.json').get('officialValidationAuthority')
        if authority is None:
            coverage=[CheckCoverage(c.family,'not-checked',
                f'Unattested legacy accepted report (stored {c.result}); original execution authority unavailable. '+(c.reason or '')) for c in coverage]
        coverage.append(CheckCoverage('official-execution-authority','passed' if authority is not None else 'not-checked',
            'Original host execution binding retained by human review.' if authority is not None else
            'Legacy history remains readable; no execution attestation was invented.'))
    return ReviewView({'personId':proposal.personId,'patient':patient,'base':asdict(proposal.base) if proposal.base else None,
                       'acceptanceStatus':'accepted' if accepted else 'prepared-unaccepted',
                       'acknowledgmentBinding':'legacy-code-resourceRef' if legacy else 'exact-issue-v1',
                       'reviewQualification':('Legacy decision bytes are retained; individual acknowledgment of colliding issues and unchecked coverage is not established.' if legacy else None)},
        tuple(r for r,i in zip(resources,value['resources']) if i['supersedesVersionId'] is None),
        tuple(revisions),
        tuple(info.get('omissions',[])),tuple(info.get('duplicateCandidates',[])),
        tuple({encode_json(e):e for e in sources}.values()),
        _review_issues(proposal.validation),tuple(asdict(c) for c in coverage),
        tuple(comparisons),omitted)


def _decision(report, decision):
    """Validate human selections and return exact acknowledgments for retention.

    Original three-field decisions remain usable only for unambiguous selectors.
    No selection, reason or confirmation is inferred for a missing limitation.
    """
    _blocked(report)
    if (not isinstance(decision,ReviewDecision) or decision.confirmedPerson is not True or
        not isinstance(decision.reviewerLabel,str) or not decision.reviewerLabel.strip() or
        not isinstance(decision.acknowledgedIssues,(tuple,list))):
        raise ArchiveError('REVIEW_REQUIRED','Explicit human identity confirmation and reviewer label required.')
    # Unknown identity is not an acknowledgeable extraction limitation.
    if any(i.code in {'IDENTITY_UNCONFIRMED','IDENTITY_MISMATCH','MULTIPLE_PERSON_CUES','PERSON_MISMATCH','IDENTITY_UNRESOLVED','SOURCE_IDENTITY_UNRESOLVED','SOURCE_IDENTITY_MISMATCH'} for i in report.issues):
        raise ArchiveError('VALIDATION_BLOCKED','Unresolved identity cannot be acknowledged.')
    required={i['issueId']:i for i in _review_issues(report) if i['severity'] in ('review','warning')}
    supplied=set()
    normalized=[]
    for ack in decision.acknowledgedIssues:
        if (not isinstance(ack,dict) or set(ack) not in ({'code','resourceRef','reason'}, {'code','resourceRef','reason','issueId'}) or
            not isinstance(ack['code'],str) or not (ack['resourceRef'] is None or isinstance(ack['resourceRef'],str)) or
            not isinstance(ack['reason'],str) or not ack['reason'].strip()):
            raise ArchiveError('REVIEW_REQUIRED','Each limitation needs an explicit reason.')
        matches=[identity for identity,i in required.items() if (i['code'],i['resourceRef'])==(ack['code'],ack['resourceRef'])]
        if 'issueId' in ack:
            key=ack['issueId']
            if not isinstance(key,str) or key not in matches:
                raise ArchiveError('REVIEW_REQUIRED','Unknown or mismatched exact issue selection.')
        elif len(matches)==1:
            key=matches[0]
        else:
            raise ArchiveError('REVIEW_REQUIRED','Legacy selection must identify exactly one displayed issue; use issueId.')
        if key in supplied: raise ArchiveError('REVIEW_REQUIRED','Duplicate acknowledgment.')
        supplied.add(key)
        normalized.append({**ack,'issueId':key})
    if supplied!=set(required) or decision.decision not in ('accept','accept-with-acknowledged-limitations') or required and decision.decision!='accept-with-acknowledged-limitations':
        raise ArchiveError('REVIEW_REQUIRED','Acknowledge exactly the displayed limitations individually.')
    return normalized


def record_review(vault: Vault, proposal: PreparedProposal, decision: ReviewDecision, *, clock: Callable[[], datetime] | None = None) -> ReviewReceipt:
    from .archive import _write
    _verify_prepared(vault,proposal)
    acknowledgments=_decision(proposal.validation,decision)
    instant=(clock or (lambda:datetime.now(timezone.utc)))()
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ArchiveError('INVALID_INPUT','Review clock requires timezone.')
    validation_digest=hash_bytes(_read(proposal.path,'validation.json'))
    value={'contractVersion':'0.1.1','personId':proposal.personId,'proposalSha256':proposal.proposalSha256,
        'validationSha256':validation_digest,'baseChangeSha256':proposal.base.changeSha256 if proposal.base else None,
        'decision':decision.decision,'reviewer':{'kind':'local-user','label':decision.reviewerLabel},
        'reviewedAt':instant.astimezone(timezone.utc).isoformat().replace('+00:00','Z'),
        'confirmedPerson':decision.confirmedPerson,'acknowledgedIssues':acknowledgments}
    from .fhir_validator import verify_pending_execution
    authority=verify_pending_execution(vault,proposal)
    if authority is not None:
        value['officialValidationAuthority']=authority
    _schema(vault,'review',value)
    path=proposal.path/'review.json'; data=encode_json(value)
    _write(path,data)
    from .intake import _mkdir
    control=_safe(vault.root,f'.runtime/reviews/{proposal.proposalSha256}.json')
    _mkdir(control.parent)
    _write(control,encode_json({'receiptSha256':hash_bytes(data)}))
    return ReviewReceipt(path,proposal.proposalSha256,validation_digest,proposal.base,hash_bytes(data))


def read_receipt(vault: Vault, proposal: PreparedProposal) -> ReviewReceipt:
    """Reload the recorded human decision using original host/accepted authority."""
    from .archive import _history
    accepted=next((change for _,_,change in _history(vault,proposal.personId)
                   if change['preparedContentSha256']==proposal.proposalSha256),None)
    if accepted is not None:
        digest=accepted['payload']['review.json']
    else:
        control=_safe(vault.root,f'.runtime/reviews/{proposal.proposalSha256}.json')
        receipt=_safe(proposal.path,'review.json')
        # Only an unaccepted proposal with neither decision artifact is unreviewed.
        # Missing retained history or a partially lost decision remains corruption.
        if not receipt.exists() and not control.exists():
            raise ArchiveError('REVIEW_REQUIRED','No review decision recorded. Run candidate review with --person and --decision before candidate commit.')
    value=_json(proposal.path,'review.json'); _schema(vault,'review',value)
    if accepted is None:
        if not control.exists():
            raise ArchiveError('REVIEW_MISMATCH','Original host review digest is missing.')
        digest=_json(control.parent,control.name).get('receiptSha256')
    if hash_bytes(_read(proposal.path,'review.json'))!=digest:
        raise ArchiveError('REVIEW_MISMATCH','Receipt bytes differ from the recorded human decision.')
    return ReviewReceipt(proposal.path/'review.json',value['proposalSha256'],value['validationSha256'],proposal.base,digest)
