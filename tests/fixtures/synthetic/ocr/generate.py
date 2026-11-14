"""Maintainer-only synthetic CC0 scan authoring. Requires local ImageMagick.

Expected facts/locations are authored separately, never produced by OCR.
"""
from pathlib import Path
import subprocess
import tempfile
import zlib

ROOT = Path(__file__).parent

def pdf(image, output):
    with image.open('rb') as stream:
        assert stream.readline() == b'P5\n'
        line = stream.readline()
        while line.startswith(b'#'):
            line = stream.readline()
        width,height = map(int,line.split())
        assert stream.readline() == b'255\n'
        pixels = stream.read()
    compressed = zlib.compress(pixels)
    content = b'q 600 0 0 800 0 0 cm /Scan Do Q'
    if output.stem == 'mixed-text-image':
        content += b' BT /F1 12 Tf 40 780 Td (Text layer: synthetic scan) Tj ET'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /XObject << /Scan 4 0 R >> /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> /Contents 5 0 R >>',
        f'<< /Type /XObject /Subtype /Image /Width {width} /Height {height} /ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode /Length {len(compressed)} >>\nstream\n'.encode()+compressed+b'\nendstream',
        f'<< /Length {len(content)} >>\nstream\n'.encode()+content+b'\nendstream']
    data=b'%PDF-1.4\n'; offsets=[0]
    for i,obj in enumerate(objects,1):
        offsets.append(len(data)); data+=f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
    start=len(data);data+=f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
    data+=b''.join(f'{offset:010} 00000 n \n'.encode() for offset in offsets[1:])
    data+=f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()
    output.write_bytes(data)

cases = {
    'scan':['Patient: Avery Synthetic','Glucose 1.20 mmol/L','CRP <0,05 mg/L'],
    'mixed-text-image':['Patient: Avery Synthetic','Glucose 1.20 mmol/L','CRP <0,05 mg/L'],
    'rotated':['Patient: Avery Synthetic','Glucose 1.20 mmol/L','CRP <0,05 mg/L'],
    'mixed':['Patient: Avery Synthetic','Glucose 1.20 mmol/L','Patient: Morgan Synthetic','Glucose 9.80 mmol/L'],
    'noisy':['Patient: Avery Synthetic','Glucose 1.20 mmol/L','CRP <0,05 mg/L'],
    'decimal-confusion':['Patient: Avery Synthetic','Glucose 1.20 mmol/L','CRP <0,05 mg/L','Calcium O.05 mg/L'],
    'missing-glyph':['Patient: Avery Synthetic','Glucose 1.20 mmol/L','CRP <0,05 mg/L'],
    'table-spill':['Patient: Avery Synthetic','TEST                 RESULT        RANGE','Glucose              1.20          3.00-6.00','CRP                  <0,05         <0,10','Albumin              40.00         35.00-50.00'],
}
with tempfile.TemporaryDirectory() as tmp:
    for name,lines in cases.items():
        path=Path(tmp)/'image.pgm'
        args=['magick','-size','1200x1600','xc:white','-font','/System/Library/Fonts/Supplemental/Courier New.ttf','-pointsize','32','-fill','black']
        for index,text in enumerate(lines):
            args += ['-draw', f"text 80,{120+index*110} '{text}'"]
        if name=='missing-glyph':
            # White occlusion erases the fractional digits; intended value cannot be recovered.
            args += ['-fill','white','-draw','rectangle 300,195 350,240']
        if name=='noisy':
            args += ['-seed','14','-attenuate','0.6','+noise','Gaussian','-blur','0x0.6']
        if name=='rotated':
            args += ['-rotate','90','-resize','1200x1600!']
        if name=='table-spill':
            args += ['-stroke','black','-strokewidth','2','-draw','line 73,280 1100,280','-draw','line 515,155 515,610']
        args += ['-colorspace','Gray','-depth','8',str(path)]
        subprocess.run(args,check=True)
        pdf(path,ROOT/(name+'.pdf'))
