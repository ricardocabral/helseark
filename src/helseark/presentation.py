"""Disposable, offline views of authoritative selected-person query results.

No clinical grouping, arithmetic, unit conversion, or acceptance happens here.
A report directory is published once; delete it explicitly before rebuilding.
"""
from dataclasses import fields
import csv
from html import escape
from io import StringIO
from pathlib import Path
import shutil
from tempfile import mkdtemp

from .agent_context import document
from .archive import head
from .contracts import ArchiveError, ObservationFilter, ObservationRow, PersonId, Vault
from .portability import _publish
from .query import observations, timeline
from .serialization import encode_json


def _text(value):
    """Native FHIR JSON for structured fields, with exact Decimal spelling."""
    return value if isinstance(value, str) else encode_json(value).decode('utf-8').strip()


def _csv_cell(value):
    text = _text(value)
    # Quoting alone does not prevent spreadsheet execution. Keep the apostrophe
    # visible in the CSV; HTML/native accepted JSON remain the fidelity sources.
    if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')):
        return "'" + text
    return text


def _destination(vault, destination):
    destination = Path(destination).absolute()
    root = vault.root.resolve()
    resolved = destination.resolve()
    # Within the vault only the top-level disposable derived tree is writable.
    # Do not follow any symlink, including a derived -> accepted redirect.
    if (resolved == root or (resolved.is_relative_to(root) and
            not resolved.is_relative_to(root/'derived')) or
            any(p.is_symlink() for p in (destination, *destination.parents))):
        raise ArchiveError('INVALID_DESTINATION', 'Use a fresh derived directory or explicit directory outside the vault.', {'exitCode':2})
    if destination.exists():
        raise ArchiveError('DESTINATION_EXISTS', 'Report destination already exists; delete the disposable report explicitly to rebuild.', {'exitCode':2})
    return destination


def render_static_report(vault: Vault, person: PersonId, destination: Path) -> Path:
    """Publish index.html and observations.csv at one accepted Head, offline.

    Destination is a fresh directory under vault/derived or outside the vault.
    Source links address accepted evidence entries, never remote URLs or copied
    original blobs which might disclose another person. They require the vault.
    """
    destination = _destination(vault, destination)
    base = head(vault, person)
    rows = list(observations(vault, person, ObservationFilter(includeInvalidated=True), at=base))
    events = list(timeline(vault, person, at=base))
    columns = ['sourceLabel', *[f.name for f in fields(ObservationRow)]]
    csv_output = StringIO(newline='')
    writer = csv.writer(csv_output)
    writer.writerow(columns)
    body = []

    def details(record):
        output = ['<dl>']
        for key, value in document(record).items():
            if key == 'sourceRefs':
                output.append('<dt>sourceRefs</dt><dd>')
                for binding in record.sourceRefs:
                    # Paths come from verified query evidence, not source URLs.
                    url = (vault.root/binding.evidencePath).absolute().as_uri() + '#' + binding.entryPointer
                    output.append('<p><a href="'+escape(url, quote=True)+'">'+
                                  escape(binding.evidencePath+'#'+binding.entryPointer)+'</a><br>'+
                                  escape(_text(document(binding)))+'</p>')
                output.append('</dd>')
            else:
                output.append('<dt>'+escape(key)+'</dt><dd><pre>'+escape(_text(value))+'</pre></dd>')
        output.append('</dl>')
        return ''.join(output)

    for row in rows:
        values = document(row)
        label = row.code.get('text', '')
        writer.writerow([_csv_cell(label), *[_csv_cell(encode_json(values[c]).decode().strip() if c == 'value' else values[c]) for c in columns[1:]]])
        summary = ''
        if row.valueType == 'valueQuantity':
            summary = str(row.comparator or '') + _text(row.value.get('value')) + ' ' + (row.unit or '')
        body.append('<article><h2>'+escape(label or 'Observation')+'</h2><p>'+escape(summary)+
                    '</p>'+details(row)+'</article>')
    html = ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
            '<title>Helseark static report</title><style>body{font:1rem system-ui,sans-serif;max-width:70rem;margin:2rem auto;padding:0 1rem;line-height:1.5}'
            'article{border-top:1px solid #999;padding:1rem 0}dt{font-weight:bold}dd{margin:0 0 1rem}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}a{overflow-wrap:anywhere}</style>'
            '<body><h1>Helseark static report</h1><p>Person '+escape(person)+'</p><p>Snapshot '+
            escape(_text(document(base)))+'</p><p>'+str(len(rows))+' observations; '+str(len(events))+' current graph records.</p>'
            '<p>Derived view of accepted records. Human review remains mandatory for imports. '
            'No medical interpretation, conversion, aggregation, or comparability is inferred. Equal labels may have incompatible units, methods, specimens, dates or ranges. '
            'Cancelled and entered-in-error results are shown for audit, never as valid trend points. Missing values are not zero.</p>'
            '<p><a href="observations.csv">Observation CSV</a> neutralizes formula cells with an apostrophe. '
            'Structured fields use exact JSON. Local source links identify evidence entries and source hashes; '
            'inspect their locators/quotes in the vault. No source blobs are copied. Links require the original vault location; '
            'this report is sensitive data, not a portable archive or a complete revision history.</p>'+
            ''.join(body)+'<h2>Current graph timeline</h2>'+''.join('<article>'+details(event)+'</article>' for event in events)+
            '</body></html>')
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(mkdtemp(prefix='.helseark-report-', dir=destination.parent))
    try:
        (stage/'index.html').write_text(html, encoding='utf-8')
        (stage/'observations.csv').write_text(csv_output.getvalue(), encoding='utf-8', newline='')
        _publish(stage, destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return destination/'index.html'
