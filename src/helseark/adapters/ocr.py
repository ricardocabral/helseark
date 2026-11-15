"""Optional local PDF OCR; pinned native tools, immutable artifacts, no publisher.

Only extract_ocr is public. Caller selects retained source and fresh output.
Raster/TSV derivatives are retained; every page is unresolved until human review.
No identity inference, numeric normalization, automatic orientation or downloads.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
import io
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from uuid import uuid4

from helseark.contracts import ArchiveError, ExtractionArtifact, IntakeLimits, Issue, SourceReceipt, sha256_string, uuid_string
from helseark.serialization import encode_json, decode_json, hash_bytes
from .pdf import extract_pdf, _directory, _publish_directory, _resident_reader

ENGINE_VERSION = '5.5.4'
RENDER_VERSION = '26.11.0'
MODEL_SHA256 = '7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2'
MAX_PIXELS = 20_000_000
MAX_OUTPUT = 64 * 1024 * 1024


@dataclass(frozen=True)
class OcrConfig:
    outputDirectory: Path
    engine: Path
    engineSha256: str
    renderer: Path
    rendererSha256: str
    model: Path
    # Explicit clockwise correction in displayed-page space, never guessed.
    rotation: int = 0

    def __post_init__(self):
        sha256_string(self.engineSha256)
        sha256_string(self.rendererSha256)
        if type(self.rotation) is not int or self.rotation not in (0, 90, 180, 270):
            raise ArchiveError('INVALID_INPUT', 'OCR rotation must be 0, 90, 180 or 270.')
        if any(not Path(p).is_absolute() for p in (self.outputDirectory, self.engine, self.renderer, self.model)):
            raise ArchiveError('INVALID_INPUT', 'OCR paths must be absolute.')


def _fail(code='OCR_INVALID'):
    return ArchiveError(code, 'Local OCR failed; original source is retained. Inspect pinned tools and limits.',
                        {'exitCode': 6} if code == 'OCR_UNSUPPORTED' else {})


def _run(args, cwd, *, seconds=30):
    """Network-denied fixed local command with bounded output, memory and time."""
    if sys.platform != 'darwin' or not Path('/usr/bin/sandbox-exec').is_file():
        raise _fail('OCR_UNSUPPORTED')
    import resource
    def controls():
        resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT, MAX_OUTPUT))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    command = ['/usr/bin/sandbox-exec', '-p', '(version 1)(allow default)(deny network*)', *map(str, args)]
    resident = _resident_reader()
    with (cwd / '.stdout').open('wb') as out, (cwd / '.stderr').open('wb') as err:
        with subprocess.Popen(command, cwd=cwd, env={'OMP_THREAD_LIMIT':'1','LC_ALL':'C'},
                              stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                              start_new_session=True, preexec_fn=controls) as process:
            end = time.monotonic() + seconds
            try:
                while process.poll() is None:
                    if time.monotonic() > end:
                        raise _fail('OCR_RESOURCE_LIMIT')
                    try:
                        if resident(process.pid) > 512 * 1024 * 1024:
                            raise _fail('OCR_RESOURCE_LIMIT')
                    except OSError:
                        if process.poll() is None:
                            raise _fail('OCR_RESOURCE_LIMIT') from None
                    time.sleep(.02)
                if process.returncode:
                    raise _fail()
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    return (cwd / '.stdout').read_bytes() + (cwd / '.stderr').read_bytes()


def _pgm(data, rotation):
    # Poppler's fixed raw P5 output; no arbitrary image decoder/plugin.
    stream = io.BytesIO(data)
    if stream.readline() != b'P5\n':
        raise _fail()
    line = stream.readline()
    while line.startswith(b'#'):
        line = stream.readline()
    width, height = map(int, line.split())
    if stream.readline() != b'255\n' or not (width > 0 and height > 0 and width * height <= MAX_PIXELS):
        raise _fail('OCR_RESOURCE_LIMIT')
    pixels = stream.read()
    if len(pixels) != width * height:
        raise _fail()
    if rotation == 90:
        pixels = b''.join(pixels[x::width][::-1] for x in range(width))
        width, height = height, width
    elif rotation == 180:
        pixels = pixels[::-1]
    elif rotation == 270:
        pixels = b''.join(pixels[x::width] for x in range(width-1, -1, -1))
        width, height = height, width
    return f'P5\n{width} {height}\n255\n'.encode() + pixels, width, height


def _words(data, width, height, rotation):
    # Geometry must not depend on a caller changing the clinical Decimal context.
    with localcontext(Context(prec=28)):
        words, text, previous = [], '', None
        for row in csv.DictReader(io.StringIO(data.decode('utf-8')), delimiter='\t', quoting=csv.QUOTE_NONE):
            if row['level'] != '5' or not row['text'].strip():
                continue
            left, top, w, h = (int(row[k]) for k in ('left','top','width','height'))
            if not (0 <= left < left+w <= width and 0 <= top < top+h <= height):
                raise _fail()
            box = [Decimal(left)/width, Decimal(top)/height, Decimal(left+w)/width, Decimal(top+h)/height]
            # Inverse correction maps recognized coordinates to original displayed CropBox.
            l,t,r,b = box
            box = {0:box, 90:[t,1-r,b,1-l], 180:[1-r,1-b,1-l,1-t], 270:[1-b,l,1-t,r]}[rotation]
            line = tuple(row[k] for k in ('block_num','par_num','line_num'))
            if text:
                text += '\n' if line != previous else ' '
            start = len(text)
            text += row['text']
            words.append({'text':row['text'], 'start':start, 'end':len(text), 'bbox':box,
                          'confidence':Decimal(row['conf'])})
            previous = line
        return text, words


def _validate_artifact(value):
    """Version-1 reader boundary; invalid retained metadata never broadens scope."""
    try:
        if not (set(value) == {'artifactVersion','sourceSha256','personId','extraction','pages','derivatives'}): raise ValueError
        provenance = value['extraction']
        if not (set(provenance) == {'provenanceVersion','status','method','tool','version','model','preprocessing'}): raise ValueError
        if not (provenance['provenanceVersion'] == '1' and provenance['status'] == 'known'): raise ValueError
        if not (provenance['method'] == 'ocr' and provenance['tool'] == 'tesseract' and provenance['version'] == ENGINE_VERSION): raise ValueError
        if not (provenance['model'] == {'name':'tessdata_fast/eng','version':MODEL_SHA256}): raise ValueError
        if not (len(provenance['preprocessing']) == 1): raise ValueError
        step = provenance['preprocessing'][0]
        if not (set(step) == {'method','tool','version','parameters'}): raise ValueError
        if not (step['method'] == 'cropbox-grayscale-render-and-clockwise-rotation'): raise ValueError
        if not (step['tool'] == 'pdftoppm+helseark-pgm' and step['version'] == RENDER_VERSION+'+1'): raise ValueError
        parameters = step['parameters']
        if not (parameters['rotation'] in (0,90,180,270) and parameters['dpi'] == 150 and parameters['scaleTo'] == 4000): raise ValueError
        if not (parameters['oem'] == 1 and parameters['psm'] == 6): raise ValueError
        sha256_string(parameters['engineSha256']); sha256_string(parameters['rendererSha256'])
        if not (type(value['pages']) is list and 0 < len(value['pages']) <= 20): raise ValueError
        if not (type(value['derivatives']) is list and len(value['derivatives']) == 3*len(value['pages'])): raise ValueError
        inventory = {}
        for derivative in value['derivatives']:
            if not (set(derivative) == {'path','sha256','size'}): raise ValueError
            sha256_string(derivative['sha256'])
            if not (type(derivative['size']) is int and 0 < derivative['size'] <= MAX_OUTPUT): raise ValueError
            if not (derivative['path'] not in inventory): raise ValueError
            inventory[derivative['path']] = derivative['sha256']
        if not (sum(d['size'] for d in value['derivatives']) <= 128*1024*1024): raise ValueError
        for n,page in enumerate(value['pages'],1):
            if not (set(page) == {'page','rotation','text','words','width','height','derivatives','coordinateSpace','unresolvedRegions'}): raise ValueError
            if not (type(page['page']) is int and page['page'] == n and page['rotation'] in (0,90,180,270)): raise ValueError
            if not (page['coordinateSpace'] == 'displayed-cropbox-top-left-normalized'): raise ValueError
            if not (type(page['width']) is int and type(page['height']) is int): raise ValueError
            if not (page['width'] > 0 and page['height'] > 0 and page['width']*page['height'] <= MAX_PIXELS): raise ValueError
            if not (isinstance(page['text'],str) and len(page['text'].encode()) <= IntakeLimits().textFieldBytes): raise ValueError
            if not (set(page['derivatives']) == {'render','image','tsv'}): raise ValueError
            if page['unresolvedRegions'] != [{'bbox':[0,0,1,1],'code':'OCR_VISUAL_REVIEW',
                'reason':'Review all pixels, omitted glyphs, decimals, identity and table row attribution.'}]: raise ValueError
            for kind,digest in page['derivatives'].items():
                if not (inventory[f'{n}-{kind}.blob'] == digest): raise ValueError
            if not (isinstance(page['words'],list)): raise ValueError
            for word in page['words']:
                if not (set(word) == {'text','start','end','bbox','confidence'}): raise ValueError
                if not (type(word['start']) is int and type(word['end']) is int): raise ValueError
                if not (0 <= word['start'] < word['end'] <= len(page['text'])): raise ValueError
                if not (page['text'][word['start']:word['end']] == word['text']): raise ValueError
                if not (len(word['bbox']) == 4): raise ValueError
                l,t,r,b = word['bbox']
                if not (all(type(x) in (int,Decimal) for x in (l,t,r,b)) and 0 <= l < r <= 1 and 0 <= t < b <= 1): raise ValueError
                if not (type(word['confidence']) in (int,Decimal) and -1 <= word['confidence'] <= 100): raise ValueError
    except (TypeError, KeyError, IndexError, ValueError, UnicodeError, ArchiveError):
        raise ArchiveError('INTEGRITY','Unsupported or inconsistent retained OCR artifact.') from None


def extract_ocr(source: SourceReceipt, config: OcrConfig) -> ExtractionArtifact:
    """Produce a new version from exact retained PDF bytes; never mutate source/history.

    Qualified on macOS only. Native binaries are operator-installed; their exact
    hashes and qualified versions are checked before they see any source bytes.
    """
    from helseark.intake import _regular
    uuid_string(source.personId)
    destination = Path(config.outputDirectory)
    parent = _directory(destination.parent)
    stage = destination.parent / ('.ocr-' + uuid4().hex)
    try:
        for path, digest in ((config.engine,config.engineSha256), (config.renderer,config.rendererSha256), (config.model,MODEL_SHA256)):
            # Tool symlinks (e.g. Homebrew) are explicit operator selections.
            try:
                actual = hash_bytes(_regular(Path(path).resolve(), MAX_OUTPUT))
            except ArchiveError:
                raise _fail('OCR_UNSUPPORTED') from None
            if actual != digest:
                raise _fail('OCR_UNSUPPORTED')
        stage.mkdir(mode=0o700)
        if not _run([config.engine,'--version'],stage).startswith(f'tesseract {ENGINE_VERSION}\n'.encode()):
            raise _fail('OCR_UNSUPPORTED')
        if not _run([config.renderer,'-v'],stage).startswith(f'pdftoppm version {RENDER_VERSION}\n'.encode()):
            raise _fail('OCR_UNSUPPORTED')
        original = _regular(source.assetPath, IntakeLimits().sourceBytes)
        if source.mediaType != 'application/pdf' or len(original) != source.size or hash_bytes(original) != source.sourceSha256:
            raise ArchiveError('SOURCE_RECEIPT_MISMATCH', 'OCR source differs from its receipt.')
        # Existing parser supplies bounded page count and rejects encrypted/corrupt PDFs.
        (stage/'original.pdf').write_bytes(original)
        pdf = extract_pdf(stage/'original.pdf', stage/'pdf', IntakeLimits(pdfPages=20))
        original_pages = decode_json(pdf.pagesPath.read_bytes())['pages']
        model = _regular(Path(config.model).resolve(), MAX_OUTPUT)
        if hash_bytes(model) != MODEL_SHA256:
            raise _fail('OCR_UNSUPPORTED')
        (stage/'eng.traineddata').write_bytes(model)
        derivatives, pages = [], []
        derivative_bytes = 0
        for number, page in enumerate(original_pages, 1):
            prefix = stage/f'render-{number}'
            _run([config.renderer,'-f',number,'-l',number,'-singlefile','-cropbox','-r','150',
                  '-scale-to','4000','-gray',stage/'original.pdf',prefix], stage)
            rendered = _regular(prefix.with_suffix('.pgm'), MAX_OUTPUT)
            image, width, height = _pgm(rendered, config.rotation)
            image_path = stage/f'page-{number}.pgm'
            image_path.write_bytes(image)
            _run([config.engine,image_path,stage/f'page-{number}','--tessdata-dir',stage,
                  '-l','eng','--oem','1','--psm','6','-c','tessedit_create_tsv=1'], stage)
            tsv = _regular(stage/f'page-{number}.tsv', MAX_OUTPUT)
            text, words = _words(tsv,width,height,config.rotation)
            if len(text.encode()) > IntakeLimits().textFieldBytes:
                raise _fail('OCR_RESOURCE_LIMIT')
            # Retain rendered and corrected images even when they coincide.
            refs = {}
            for kind, data in (('render',rendered),('image',image),('tsv',tsv)):
                name = f'{number}-{kind}.blob'
                derivative_bytes += len(data)
                if derivative_bytes > 128 * 1024 * 1024:
                    raise _fail('OCR_RESOURCE_LIMIT')
                (stage/name).write_bytes(data)
                derivatives.append({'path':name,'sha256':hash_bytes(data),'size':len(data)})
                refs[kind] = hash_bytes(data)
            pages.append({'page':number,'rotation':page['rotation'],'text':text,'words':words,
                'width':width,'height':height,'derivatives':refs,
                'coordinateSpace':'displayed-cropbox-top-left-normalized',
                'unresolvedRegions':[{'bbox':[0,0,1,1], 'code':'OCR_VISUAL_REVIEW',
                    'reason':'Review all pixels, omitted glyphs, decimals, identity and table row attribution.'}]})
        provenance = {'provenanceVersion':'1','status':'known','method':'ocr','tool':'tesseract',
            'version':ENGINE_VERSION,'model':{'name':'tessdata_fast/eng','version':MODEL_SHA256},
            'preprocessing':[{'method':'cropbox-grayscale-render-and-clockwise-rotation',
                'tool':'pdftoppm+helseark-pgm','version':RENDER_VERSION+'+1',
                'parameters':{'rendererSha256':config.rendererSha256,'engineSha256':config.engineSha256,
                    'dpi':150,'scaleTo':4000,'rotation':config.rotation,'oem':1,'psm':6,
                    'transform':'inverse normalized rotation; no deskew or crop beyond PDF CropBox'}}]}
        payload = {'artifactVersion':'helseark-ocr-pages-1','sourceSha256':source.sourceSha256,
            'personId':source.personId,'extraction':provenance,'pages':pages,'derivatives':derivatives}
        _validate_artifact(payload)
        data = encode_json(payload)
        if len(data) > MAX_OUTPUT:
            raise _fail('OCR_RESOURCE_LIMIT')
        (stage/'pages.json').write_bytes(data)
        keep = {'original.pdf','pages.json',*(d['path'] for d in derivatives)}
        for path in stage.iterdir():
            if path.name not in keep:
                shutil.rmtree(path) if path.is_dir() else path.unlink()
        _publish_directory(parent,stage.name,destination.name)
        issues = (Issue('OCR_VISUAL_REVIEW','review',None,None,
            'Every OCR page remains unresolved: verify original pixels, identity, missing glyphs, decimals and table rows.'),)
        return ExtractionArtifact('ocr',ENGINE_VERSION,destination/'pages.json',hash_bytes(data),len(pages),issues)
    except ArchiveError:
        raise
    except (OSError, ValueError, KeyError, UnicodeError, csv.Error):
        raise _fail() from None
    finally:
        if stage.exists():
            shutil.rmtree(stage)
        os.close(parent)
