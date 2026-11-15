"""Disposable, offline views of authoritative selected-person query results.

No clinical grouping, arithmetic, unit conversion, or acceptance happens here.
A report directory is published once; delete it explicitly before rebuilding.
"""
from dataclasses import fields
import csv
import textwrap
from html import escape
from io import StringIO
from pathlib import Path
from unicodedata import category

from .agent_context import document
from .archive import head
from .contracts import ObservationFilter, ObservationRow, PersonId, Vault
from .report_publication import ReportPublication
from .query import observations, timeline
from .serialization import encode_json


def _text(value):
    """Native FHIR JSON for structured fields, with exact Decimal spelling."""
    return value if isinstance(value, str) else encode_json(value).decode('utf-8').strip()


def _csv_cell(value):
    text = _text(value)
    # Quoting alone does not prevent spreadsheet execution. Keep the apostrophe
    # visible in the CSV; HTML/native accepted JSON remain the fidelity sources.
    prefix = 0
    while prefix < len(text) and (text[prefix].isspace() or category(text[prefix]) in ('Cc', 'Cf')):
        prefix += 1
    if text[prefix:].startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')):
        return "'" + text
    return text


def render_static_report(vault: Vault, person: PersonId, destination: Path) -> Path:
    """Publish index.html and observations.csv at one accepted Head, offline.

    Destination is a fresh directory under vault/derived or outside the vault.
    Source links address accepted evidence entries, never remote URLs or copied
    original blobs which might disclose another person. They require the vault.
    """
    with ReportPublication(vault, destination) as publication:
        return _render(vault, person, publication)


def _render(vault, person, publication):
    destination = publication.destination
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
            '<p><a href="report.svg">Source-cited factual SVG</a>. <a href="observations.csv">Observation CSV</a> neutralizes formula cells with an apostrophe. '
            'Structured fields use exact JSON. Local source links identify evidence entries and source hashes; '
            'inspect their locators/quotes in the vault. No source blobs are copied. Links require the original vault location; '
            'this report is sensitive data, not a portable archive or a complete revision history.</p>'+
            ''.join(body)+'<h2>Current graph timeline</h2>'+''.join('<article>'+details(event)+'</article>' for event in events)+
            '</body></html>')
    # A textual SVG preserves native assertions without inventing comparable axes.
    svg_lines = []
    y = 28
    def line(text, link=None):
        nonlocal y
        for part in textwrap.wrap(text, width=110, replace_whitespace=False, drop_whitespace=False) or ['']:
            node = '<text x="16" y="'+str(y)+'">'+escape(part)+'</text>'
            svg_lines.append('<a href="'+escape(link, quote=True)+'">'+node+'</a>' if link else node)
            y += 20
    line('Helseark factual snapshot: ' + person)
    line('Head: ' + _text(document(base)))
    line('Native assertions; unknowns retained. No conversion, trends or clinical interpretation.')
    for event in events:
        line(_text(document(event.resourceRef)))
        line(_text(event.resource))
        line('Time precision: ' + event.timePrecision + '; status: ' + _text(event.status))
        for binding in event.sourceRefs:
            link = (vault.root/binding.evidencePath).absolute().as_uri() + '#' + binding.entryPointer
            line('Evidence: ' + binding.evidencePath + '#' + binding.entryPointer +
                 '; source SHA-256: ' + (binding.sourceSha256 or 'unknown'), link)
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="'+str(y+16)+
           '" viewBox="0 0 1100 '+str(y+16)+'" role="img" aria-label="Source-cited native clinical assertions">'
           '<title>Helseark factual snapshot</title><g font-family="monospace" font-size="14">'+
           ''.join(svg_lines)+'</g></svg>')
    publication.publish(html, csv_output.getvalue(), svg)
    return destination/'index.html'
