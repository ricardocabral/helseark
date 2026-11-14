"""Read-only projections of one person's accepted FHIR graph.

No index is authoritative. One call pins a Head, scans canonical files and builds
in-memory evidence/relationship indexes. Row order is stable resource identity,
never a claim of clinical chronology or comparability.
"""
from datetime import date, datetime
from calendar import monthrange
from fractions import Fraction
import re
from typing import Iterator, Sequence

from .archive import head, iter_current, resolve, _snapshot, _read, _json
from .contracts import (ArchiveError, EvidenceRef, Head, Issue, ObservationFilter,
                        ObservationRow, PersonId, ResourceRef, TimelineRow, Vault, uuid_string)
from .serialization import hash_bytes


_DATE = re.compile(r'[0-9]{4}(?:-[0-9]{2}(?:-[0-9]{2})?)?')
_TIMESTAMP = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})')


def _bounds(value, *, instant=False):
    """Exact half-open calendar interval or closed timestamp point.

    Rational seconds avoid both binary rounding and truncating source fractional
    seconds to Python datetime's microsecond resolution. Never emitted as FHIR.
    """
    if not isinstance(value, str):
        raise ValueError
    if _DATE.fullmatch(value):
        parts = [int(v) for v in value.split('-')]
        year = parts[0]
        month = parts[1] if len(parts)>1 else 1
        day = parts[2] if len(parts)>2 else 1
        start = date(year,month,day).toordinal()
        if len(parts)==1:
            end = date(year,12,31).toordinal()+1
        elif len(parts)==2:
            end = date(year,month,monthrange(year,month)[1]).toordinal()+1
        else:
            end = start+1
        return Fraction(start*86400),Fraction(end*86400),('year','month','day')[len(parts)-1]
    if not _TIMESTAMP.fullmatch(value):
        raise ValueError
    fraction = re.search(r'\.([0-9]+)',value)
    raw = re.sub(r'\.[0-9]+','',value).replace('Z','+00:00')
    moment = datetime.fromisoformat(raw)
    point = Fraction(moment.date().toordinal()*86400+moment.hour*3600+moment.minute*60+moment.second)
    if fraction:
        digits = fraction.group(1)
        point += Fraction(int(digits),10**len(digits))
    if instant:
        point -= int(moment.utcoffset().total_seconds())
    return point,point,'instant'


_MIN = Fraction(-86400)
_MAX = Fraction((date.max.toordinal()+2)*86400)


def _date_window(from_date, to_date):
    try:
        instant = any(isinstance(v,str) and 'T' in v for v in (from_date,to_date))
        if instant and any(v is not None and (not isinstance(v,str) or 'T' not in v) for v in (from_date,to_date)):
            raise ValueError
        low = _bounds(from_date,instant=instant)[0] if from_date is not None else _MIN
        high = _bounds(to_date,instant=instant)[1] if to_date is not None else _MAX
        if low > high or (low==high and not instant):
            raise ValueError
    except (ValueError,TypeError,OverflowError):
        raise ArchiveError('INVALID_FILTER', 'Use valid inclusive year/month/day bounds or offset timestamps, in ascending order; do not mix calendar and instant bounds.') from None
    return low, high, instant


# Native event time only. Recording/authorship does not imply event onset.
_HISTORY_TIMES = {'AllergyIntolerance': ('onsetDateTime', 'onsetPeriod', 'onsetAge', 'onsetRange', 'onsetString'), 'Condition': ('onsetDateTime', 'onsetPeriod', 'onsetAge', 'onsetRange', 'onsetString'), 'MedicationRequest': ('authoredOn',), 'MedicationStatement': ('effectiveDateTime', 'effectivePeriod')}

def _effective(resource):
    kind = resource.get('resourceType')
    if kind in _HISTORY_TIMES:
        for field in _HISTORY_TIMES[kind]:
            if field in resource:
                return field, resource[field]
        return None, None
    for key in ('effectiveDateTime','effectivePeriod','effectiveInstant','effectiveTiming'):
        if key in resource:
            return key, resource[key]
    # A report's issued time is not its measurement time. Non-result timeline
    # entries may expose their native documented time without inferring one.
    for key in ('date','collectedDateTime','collectedPeriod','recorded'):
        if key in resource:
            return key, resource[key]
    collection = resource.get('collection',{})
    for key in ('collectedDateTime','collectedPeriod'):
        if key in collection:
            return 'collection.'+key,collection[key]
    return None, None


def _time(resource, window):
    kind, value = _effective(resource)
    precision = 'unknown'
    low, high, instant = window
    try:
        if isinstance(value, dict) and kind and (kind.endswith('Period') or kind == 'period'):
            begin, end = value.get('start'), value.get('end')
            first = _bounds(begin,instant=instant) if begin else (_MIN,_MIN,'unknown')
            last = _bounds(end,instant=instant) if end else (_MAX,_MAX,'unknown')
            precision = 'period'
            uncertain = instant and any(v and 'T' not in v for v in (begin,end))
            start, stop = first[0], last[1]
            closed = last[2]=='instant'
        elif isinstance(value,str):
            start, stop, precision = _bounds(value,instant=instant)
            uncertain = instant and 'T' not in value
            closed = precision=='instant'
        else:
            return kind,value,precision,'unknown','unknown'
        if start > stop:
            return kind,value,precision,'unknown','unknown'
        if uncertain:
            return kind,value,precision,'unknown','dated'
        if stop < low or (stop==low and not closed) or start > high or (start==high and not instant):
            return kind,value,precision,None,'dated'
        contained = low <= start and (stop < high or (stop==high and (not closed or instant)))
        relation = 'contained' if contained else 'overlap'
        return kind,value,precision,relation,'dated'
    except (ValueError,TypeError,OverflowError):
        # Retained unknown time is visible, never silently dropped or normalized.
        return kind,value,'unknown','unknown','unknown'


def matches_dates(resource, filters: ObservationFilter):
    """Shared date owner for all native context records, including pinned revisions.

    Unknown time remains in scope with explicit uncertainty, even with bounds.
    """
    return _time(resource,_date_window(filters.fromDate,filters.toDate))[3] is not None


def date_selection(resource, filters: ObservationFilter):
    """Nonclinical selection metadata, shared by bounded context packets."""
    _,_,precision,relation,bucket = _time(resource,_date_window(filters.fromDate,filters.toDate))
    return {'fromDate':filters.fromDate,'toDate':filters.toDate,'timePrecision':precision,
            'timeFilterRelation':relation,'timeBucket':bucket}


def _ref(resource):
    return ResourceRef(resource['resourceType'],resource['id'],resource['meta']['versionId'])


def parse_reference(value):
    parts = value.split('/') if isinstance(value,str) else []
    if len(parts)==2:
        return ResourceRef(*parts)
    if len(parts)==4 and parts[2]=='_history':
        return ResourceRef(parts[0],parts[1],parts[3])
    raise ArchiveError('INVALID_REFERENCE','Use Type/UUID or Type/UUID/_history/UUID.')


def _graph(vault, person, at):
    uuid_string(person)
    base = at if at is not None else head(vault,person)
    if base is None:
        raise ArchiveError('PERSON_NOT_FOUND','Selected person has no accepted identity.')
    resources = list(iter_current(vault,person,at=base))
    by_key = {(r['resourceType'],r['id']):r for r in resources}
    evidence, issues, results = {}, {}, {}
    for original,directory,change in _snapshot(vault,person,base):
        path = directory/'evidence.json'
        data = _read(directory,'evidence.json')
        envelope = _json(directory,'evidence.json',data=data)
        digest = hash_bytes(data)
        for index,item in enumerate(envelope['entries']):
            target = item.get('target',{}).get('reference',item.get('resourceRef'))
            evidence.setdefault(target,[]).append(EvidenceRef(path.relative_to(vault.root).as_posix(),digest,
                f'/entries/{index}',item.get('sourceSha256'),item.get('sourceDocument')))
        # Preserve accepted validation limitations attached to exact revisions.
        targets = {f"{entry['type']}/{entry['id']}":
                   f"{entry['type']}/{entry['id']}/_history/{entry['versionId']}"
                   for entry in change['resources']}
        for item in _json(directory,'validation.json')['issues']:
            reference = item.get('resourceRef')
            target = targets.get(reference, reference if reference and '/_history/' in reference else None)
            if target:
                issues.setdefault(target,[]).append(Issue(**{**item, 'resourceRef':target}))
    for resource in resources:
        if resource['resourceType']!='DiagnosticReport':
            continue
        parent = _ref(resource)
        children=[]
        for target in resource.get('result',[]):
            child = parse_reference(target['reference'])
            exact = _ref(resolve(vault,person,child,at=base))
            children.append(exact)
            current = by_key.get((child.resourceType,child.id))
            if current is None or _ref(current)!=exact:
                issue = Issue('REPORT_RESULT_REVISION_MISMATCH','warning','/result',_ref_text(parent),
                    'Report retains child '+_ref_text(exact)+' while the selected snapshot has another current result revision; no cascade or reconciliation was applied.')
                issues.setdefault(_ref_text(parent),[]).append(issue)
                if current:
                    issues.setdefault(_ref_text(_ref(current)),[]).append(issue)
        results[_ref_text(parent)] = tuple(children)
    return resources,evidence,issues,results


def _ref_text(ref):
    return f'{ref.resourceType}/{ref.id}/_history/{ref.versionId}'


def observations(vault: Vault, person: PersonId, filters: ObservationFilter, *, at: Head | None = None) -> Iterator[ObservationRow]:
    if not isinstance(filters,ObservationFilter):
        raise ArchiveError('INVALID_FILTER','Expected an ObservationFilter.')
    resources,evidence,issues,_ = _graph(vault,person,at)
    window = _date_window(filters.fromDate,filters.toDate)
    for r in resources:
        if r['resourceType']!='Observation':
            continue
        if not filters.includeInvalidated and r.get('status') in ('cancelled','entered-in-error'):
            continue
        code = r.get('code',{})
        if filters.exactSourceLabel is not None and code.get('text')!=filters.exactSourceLabel:
            continue
        if filters.code is not None or filters.codeSystem is not None:
            if not any((filters.code is None or c.get('code')==filters.code) and
                       (filters.codeSystem is None or c.get('system')==filters.codeSystem) for c in code.get('coding',[])):
                continue
        kind,effective,precision,relation,bucket = _time(r,window)
        if relation is None:
            continue
        ref = _ref(r); target = _ref_text(ref)
        value_type = next((k for k in r if k.startswith('value') and not k.startswith('_')),None)
        value = r.get(value_type) if value_type else None
        quantity = value if value_type=='valueQuantity' else {}
        yield ObservationRow(ref,effective,precision,relation,code,value,quantity.get('unit'),quantity.get('comparator'),
            r.get('referenceRange',[]),r.get('method'),r.get('specimen'),r.get('status'),tuple(evidence.get(target,())),
            tuple(issues.get(target,())),value_type,kind,bucket,r.get('component',[]),r.get('dataAbsentReason'),
            r.get('note',[]),r.get('interpretation',[]),r.get('hasMember',[]),r.get('derivedFrom',[]))


def timeline(vault: Vault, person: PersonId, *, at: Head | None = None) -> Iterator[TimelineRow]:
    resources,evidence,issues,results = _graph(vault,person,at)
    for r in resources:
        ref = _ref(r); target = _ref_text(ref)
        kind,effective,precision,_,bucket = _time(r,_date_window(None,None))
        yield TimelineRow(ref,r.get('status'),effective,precision,bucket,kind,results.get(target,()),
            tuple(evidence.get(target,())),tuple(issues.get(target,())),r)


def history(vault: Vault, person: PersonId, kinds: Sequence[str], at: Head | None = None) -> Iterator[dict]:
    """Native assertions plus their native Provenance at one verified Head.

    Evidence locators remain in the accepted evidence envelope (also exposed by
    timeline); no synthetic fields are added to these FHIR resources.
    """
    if isinstance(kinds, (str, bytes)) or not kinds or any(k not in _HISTORY_TIMES for k in kinds):
        raise ArchiveError('INVALID_FILTER', 'Select supported clinical history resource kinds.')
    resources, _, _, _ = _graph(vault, person, at)
    selected = [r for r in resources if r['resourceType'] in kinds]
    targets = {_ref_text(_ref(r)) for r in selected}
    logical = {r['resourceType']+'/'+r['id'] for r in selected}
    for r in resources:
        if r in selected or (r['resourceType']=='Provenance' and any(
                t.get('reference') in targets | logical for t in r.get('target', []))):
            yield r
