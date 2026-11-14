"""Explicitly mapped numeric CSV rows to FHIR candidates, without locale guesses.

A row coordinate is a source assertion, not a duplicate fact key. Unknown columns,
invalid values and uncertain local clocks block preparation. This module neither
executes cell contents nor accepts clinical records.
"""
import codecs
import csv
from dataclasses import dataclass
from datetime import datetime, timezone as utc_timezone
from decimal import Decimal
import io
import re
import sys
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..contracts import ArchiveError, Candidate, SourceReceipt, Issue, uuid_string
from ..serialization import decode_json
from ..validation import _walk
from .fhir_r4 import _profile, _source_document, _evidence

_ENCODINGS = {'utf-8','utf-8-sig','utf-16','utf-16-le','utf-16-be','iso8859-1','cp1252'}


@dataclass(frozen=True)
class CsvMetricMapping:
    delimiter: str
    encoding: str
    dateColumn: str
    valueColumn: str
    unitColumn: str
    codeColumn: str
    dateFormat: str
    decimalSeparator: str
    localPersonId: str
    assignmentReason: str
    timezone: str | None = None
    codeSystem: str | None = None

    def __post_init__(self):
        uuid_string(self.localPersonId)
        try:
            encoding=codecs.lookup(self.encoding).name
        except (LookupError,TypeError):
            raise ArchiveError('CSV_MAPPING_REQUIRED','Unsupported declared CSV encoding.') from None
        columns=(self.dateColumn,self.valueColumn,self.unitColumn,self.codeColumn)
        if (encoding not in _ENCODINGS or not isinstance(self.delimiter,str) or len(self.delimiter)!=1 or
                self.delimiter in '\r\n\0"' or self.decimalSeparator not in ('.',',') or
                any(not isinstance(c,str) or not c for c in columns) or len(set(columns))!=4 or
                not isinstance(self.assignmentReason,str) or not self.assignmentReason.strip() or
                not isinstance(self.dateFormat,str) or not self.dateFormat or
                self.timezone is not None and (not isinstance(self.timezone,str) or not self.timezone) or
                self.codeSystem is not None and (not isinstance(self.codeSystem,str) or not re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:',self.codeSystem))):
            raise ArchiveError('CSV_MAPPING_REQUIRED','Explicit distinct column, decimal, date, encoding and assignment configuration required.')
        directives=re.findall(r'%(.)',self.dateFormat)
        # Locale words, two-digit pivots, defaulted calendar fields and subseconds
        # whose precision would be expanded are deliberately unsupported.
        if ('Y' not in directives or any(d not in 'YmdHMSz' for d in directives) or
                'd' in directives and 'm' not in directives or
                any(d in directives for d in 'HMSz') and not all(d in directives for d in 'YmdHMS')):
            raise ArchiveError('CSV_MAPPING_REQUIRED','Use explicit numeric calendar fields with year and complete second-precision clocks.')
        object.__setattr__(self,'encoding',encoding)
        if self.timezone is not None:
            try:ZoneInfo(self.timezone)
            except (ZoneInfoNotFoundError,ValueError):
                raise ArchiveError('CSV_MAPPING_REQUIRED','Declared timezone is unavailable offline.') from None


def _time(text, mapping):
    try:parsed=datetime.strptime(text,mapping.dateFormat)
    except ValueError:
        raise ArchiveError('CSV_DATE_INVALID','Date differs from explicit declared format.') from None
    directives=re.findall(r'%(.)',mapping.dateFormat)
    if 'H' not in directives:
        return parsed.strftime('%Y' + ('-%m' if 'm' in directives else '') + ('-%d' if 'd' in directives else ''))
    zone=ZoneInfo(mapping.timezone) if mapping.timezone else None
    if parsed.tzinfo is not None:
        if zone is not None and parsed.astimezone(zone).utcoffset()!=parsed.utcoffset():
            raise ArchiveError('CSV_TIMEZONE_CONFLICT','Source offset conflicts with declared timezone.')
        return parsed.isoformat(timespec='seconds')
    if zone is None:
        raise ArchiveError('CSV_TIMEZONE_REQUIRED','Local source clock has no declared timezone; retain original and resolve before preparation.')
    valid=[]
    for fold in (0,1):
        instant=parsed.replace(tzinfo=zone,fold=fold)
        back=instant.astimezone(utc_timezone.utc).astimezone(zone).replace(tzinfo=None)
        if back==parsed:valid.append(instant)
    if not valid:
        raise ArchiveError('CSV_TIME_NONEXISTENT','Source clock falls in a timezone gap; no instant inferred.')
    if len({t.utcoffset() for t in valid})>1:
        raise ArchiveError('CSV_TIME_AMBIGUOUS','Source clock has two possible offsets; no instant inferred.')
    return valid[0].isoformat(timespec='seconds')


def _quantity(text, separator):
    match=re.fullmatch(r'\s*(<=|>=|<|>)?\s*(-?(?:0|[1-9][0-9]*)(?:'+re.escape(separator)+r'[0-9]+)?)\s*',text)
    if match is None:
        raise ArchiveError('CSV_NUMBER_INVALID','Expected a bounded exact decimal in the declared convention; grouping and formulas are unsupported.')
    value=decode_json(match[2].replace(separator,'.').encode('ascii'))
    result={'value':Decimal(value)}
    if match[1]:result['comparator']=match[1]
    return result


def import_metrics_csv(source: SourceReceipt, person: str, mapping: CsvMetricMapping) -> Candidate:
    from ..intake import _structured_source, _structured_candidate, LIMITS
    if not isinstance(mapping,CsvMetricMapping):
        raise ArchiveError('CSV_MAPPING_REQUIRED','Use a trusted explicit CsvMetricMapping.')
    if mapping.localPersonId!=person:
        raise ArchiveError('PERSON_MISMATCH','CSV mapping differs from selected person.')
    vault,data=_structured_source(source,person)
    try:
        text=data.decode(mapping.encoding,errors='strict')
        reader=csv.reader(io.StringIO(text,newline=''),delimiter=mapping.delimiter,strict=True)
        headers=next(reader)
        if not headers or len(headers)!=len(set(headers)) or any(not h for h in headers):
            raise ArchiveError('CSV_MAPPING_REQUIRED','CSV headers must be nonempty and unique.')
        rows=[]
        for row in reader:
            if len(rows)>=LIMITS.candidateResources-1:
                raise ArchiveError('RESOURCE_LIMIT','CSV exceeds candidate resource limit.')
            if len(row)!=len(headers):
                raise ArchiveError('CSV_INPUT_INVALID','CSV rows must match the explicit header width.')
            if any(len(cell.encode('utf-8'))>LIMITS.textFieldBytes for cell in row):
                raise ArchiveError('TEXT_FIELD_LIMIT','CSV cell exceeds text limit.')
            rows.append(dict(zip(headers,row)))
    except (UnicodeError,csv.Error,StopIteration):
        raise ArchiveError('CSV_INPUT_INVALID','Cannot parse CSV with the declared delimiter/encoding.') from None
    selected={mapping.dateColumn,mapping.valueColumn,mapping.unitColumn,mapping.codeColumn}
    if not selected.issubset(headers) or not rows:
        raise ArchiveError('CSV_MAPPING_REQUIRED','Every mapped column and at least one row must be present.')
    issues=[];coverage=[];resources=[];evidence=[]
    for column in headers:
        handled=column in selected
        coverage.append({'column':column,'disposition':'mapped' if handled else 'unsupported-column'})
        if not handled:issues.append(Issue('CSV_UNHANDLED_COLUMN','error',None,None,'Unhandled column retained in source; explicit supported mapping required.'))
    doc=_source_document(source,person,'text/csv');resources.append(doc)
    def entry(ref,pointers,row,column,rule):
        e=_evidence(source,doc,ref,pointers,{'kind':'csv-cell','row':row,'column':column,
            'delimiter':mapping.delimiter,'encoding':mapping.encoding},rows[row-1][column],
            'csv-cell',rule=rule,description='Explicit local mapping: '+mapping.assignmentReason)
        e['extraction'].update(tool='python.csv',version=sys.version.split()[0])
        e['extraction']['preprocessing']=[{'method':'decode','tool':'python.codecs','version':sys.version.split()[0],
            'parameters':{'encoding':mapping.encoding,'delimiter':mapping.delimiter}}]
        return e
    docref='urn:uuid:'+doc['id']
    for pointer,value in _walk(doc):
        if isinstance(value,(dict,list)) or pointer=='/resourceType':continue
        if pointer=='/id' or pointer.startswith('/meta/') or pointer.endswith('/attachment/url'):
            evidence.append({'kind':'generated','target':{'reference':docref,'pointers':[pointer]},'rule':'structured-source-document-1'})
        else:
            # An actual nonempty cell is the coordinate of the mapped source envelope.
            column=next((h for h in headers if rows[0][h]),None)
            if column is None:raise ArchiveError('CSV_INPUT_INVALID','CSV has no nonempty source anchor.')
            evidence.append(entry(docref,[pointer],1,column,'csv-source-envelope-1'))
    for n,row in enumerate(rows,1):
        coverage.append({'row':n,'disposition':'mapped-row','columns':headers})
        try:
            effective=_time(row[mapping.dateColumn],mapping)
            quantity=_quantity(row[mapping.valueColumn],mapping.decimalSeparator)
            if not row[mapping.unitColumn] or not row[mapping.codeColumn]:
                raise ArchiveError('CSV_CELL_REQUIRED','Explicit unit and code/label cells must be nonempty.')
            quantity['unit']=row[mapping.unitColumn]
            code={'text':row[mapping.codeColumn]}
            if mapping.codeSystem:code={'coding':[{'system':mapping.codeSystem,'code':row[mapping.codeColumn]}]}
            r={'resourceType':'Observation','id':str(uuid4()),'meta':_profile('Observation'),
               'status':'unknown','subject':{'reference':'Patient/'+person},'code':code,
               'effectiveDateTime':effective,'valueQuantity':quantity}
            ref='urn:uuid:'+r['id'];resources.append(r)
            evidence.append({'kind':'generated','target':{'reference':ref,'pointers':['/id','/meta/profile/0']},'rule':'allocate-local-identity-profile-1'})
            evidence.append(entry(ref,['/status','/subject/reference'],n,mapping.codeColumn,'explicit-person-csv-status-unknown-1'))
            evidence.append(entry(ref,['/code'],n,mapping.codeColumn,'explicit-source-code-1'))
            evidence.append(entry(ref,['/effectiveDateTime'],n,mapping.dateColumn,'explicit-date-format-zone-1'))
            evidence.append(entry(ref,['/valueQuantity/value']+(['/valueQuantity/comparator'] if 'comparator' in quantity else []),n,mapping.valueColumn,'explicit-decimal-separator-1'))
            evidence.append(entry(ref,['/valueQuantity/unit'],n,mapping.unitColumn,'source-unit-verbatim-1'))
        except ArchiveError as error:
            issues.append(Issue(error.code,'error',f'/rows/{n}',None,error.safeMessage))
            coverage[-1]['disposition']='blocked-row'
    return _structured_candidate(vault,source,'csv-metrics',mapping,resources,evidence,issues,coverage)
