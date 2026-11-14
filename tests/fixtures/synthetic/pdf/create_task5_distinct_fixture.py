"""Author ONLY supplementary explicit-result fixture; never replace old trials.

CC0 invented text. Run with pinned pypdf 7.0.0; no model or OCR is used.
"""
from pathlib import Path
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

lines = [
    'SYNTHETIC SUPPLEMENTARY DISTINCT RESULTS - NOT HEALTH DATA',
    'Patient: Avery Synthetic', 'Report: Synthetic laboratory report',
    'Document status: current', 'Format: application/pdf',
    'Result 1 - independent quantitative observation:',
    'Signal Z: >2,700 mg/L', 'Reference: 0,00 - 0,10 mg/L',
    'Method: M1', 'Status: final', 'Collected: 2026-01',
    'Result 2 - independent qualitative observation, unrelated to Result 1:',
    'Screening assay: reactive', 'Status: final', 'Collected: 2026-01',
    'No terminology codes supplied. Preserve each printed local label.'
]
writer=PdfWriter()
page=writer.add_blank_page(width=600,height=800)
font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
stream=DecodedStreamObject()
stream.set_data(('BT /F1 10 Tf 40 760 Td 20 TL\n'+'\n'.join('('+s+') Tj T*' for s in lines)+'\nET\n').encode('ascii'))
page[NameObject('/Contents')]=writer._add_object(stream)
with (Path(__file__).resolve().parents[1]/'task5-distinct-results.pdf').open('xb') as out:
    writer.write(out)
