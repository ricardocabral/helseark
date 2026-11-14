"""Bounded real-parser parent RSS/output measurement, not a host resource cap.

Run with the PDF extra: python tests/qualify_pdf_resources.py
Each extraction parent is fresh; fixture authoring is outside its measurement.
No allocations intended to exhaust a budget. Works from an installed wheel too.
"""
import json
from pathlib import Path
import resource
import subprocess
import sys
from tempfile import TemporaryDirectory
import time


def measure(source, destination, count):
    import helseark.adapters.pdf as pdf
    from helseark.contracts import IntakeLimits
    scale = 1024 if sys.platform == 'linux' else 1
    baseline = resource.getrusage(resource.RUSAGE_SELF)
    start = time.monotonic()
    receipt = pdf.extract_pdf(Path(source), Path(destination), IntakeLimits())
    # Read peak before this harness loads a second copy for its own verification.
    usage = resource.getrusage(resource.RUSAGE_SELF)
    data = receipt.pagesPath.read_bytes()
    pages = json.loads(data)['pages']
    assert receipt.pageCount == count
    assert all(page['text'] == 'A' * 1048576 for page in pages)
    assert len(pages) == count
    result = {'pages': count, 'textBytes': count * 1048576,
              'sourceBytes': Path(source).stat().st_size,
              'artifactBytes': len(data), 'parentBaselinePeakBytes': baseline.ru_maxrss * scale,
              'parentPeakBytes': usage.ru_maxrss * scale,
              'parentPeakIncreaseBytes': (usage.ru_maxrss - baseline.ru_maxrss) * scale,
              'parentCpuSeconds': usage.ru_utime + usage.ru_stime - baseline.ru_utime - baseline.ru_stime,
              'wallSeconds': time.monotonic() - start, 'adapter': pdf.__file__}
    print(json.dumps(result), flush=True)


def main():
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject
    fixture = Path(__file__).parent / 'fixtures/synthetic/lab-text.pdf'
    with TemporaryDirectory() as root:
        root = Path(root).resolve()
        for count in (1, 4, 8):
            writer = PdfWriter()
            for _ in range(count):
                page = writer.add_page(PdfReader(fixture).pages[0])
                stream = DecodedStreamObject()
                stream.set_data(b'BT /F1 12 Tf 10 10 Td (' + b'A' * 1048576 + b') Tj ET')
                page[NameObject('/Contents')] = writer._add_object(stream.flate_encode())
            source = root / f'{count}.pdf'; writer.write(source)
            subprocess.run([sys.executable, __file__, '--measure', str(source),
                            str(root / f'out-{count}'), str(count)], check=True)


if __name__ == '__main__':
    if len(sys.argv) == 5 and sys.argv[1] == '--measure':
        measure(sys.argv[2], sys.argv[3], int(sys.argv[4]))
    else:
        main()
