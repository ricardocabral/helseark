"""Export Quiet Ark assets. Requires Python 3, librsvg and ImageMagick."""

import copy
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parent
NS = '{http://www.w3.org/2000/svg}'
ET.register_namespace('', NS[1:-1])
NAVY, GREEN, PAPER = '#102B49', '#66A786', '#FAF8F3'
PALETTES = {
    'color': (NAVY, GREEN),
    'reverse': ('#FFFFFF', '#82C3A3'),
    'black': ('#000000', '#000000'),
    'white': ('#FFFFFF', '#FFFFFF'),
}
LAYOUTS = {
    'horizontal': (1600, 400, [ ('symbol', 48, 77, 304), ('wordmark', 424, 97, 1150) ]),
    'stacked': (1000, 1000, [ ('symbol', 260, 150, 480), ('wordmark', 100, 680, 800) ]),
    'wordmark': (1600, 400, [ ('wordmark', 80, 71, 1440) ]),
    'icon': (512, 512, [ ('symbol', 64, 101, 384) ]),
}
WIDTHS = {
    'horizontal': [320, 640, 1280, 2560, 4096],
    'stacked': [256, 512, 1024, 2048],
    'wordmark': [320, 640, 1280, 2560, 4096],
    'icon': [16, 24, 32, 48, 64, 96, 128, 180, 192, 256, 512, 1024],
}
SOURCES = {name: ET.parse(ROOT / 'source' / f'{name}.svg').getroot()
           for name in ('symbol', 'wordmark')}


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True, stdout=subprocess.DEVNULL)


def svg_document(layout, palette, background=None):
    width, height, placements = layout
    doc = ET.Element(NS+'svg', {'viewBox': f'0 0 {width} {height}',
                               'width': str(width), 'height': str(height),
                               'role': 'img', 'aria-labelledby': 'title'})
    ET.SubElement(doc, NS+'title', {'id': 'title'}).text = 'Helseark — Quiet Ark'
    if background:
        ET.SubElement(doc, NS+'rect', {'width': '100%', 'height': '100%', 'fill': background})
    for name, x, y, target_width in placements:
        source = SOURCES[name]
        source_width = float(source.get('width'))
        group = ET.SubElement(doc, NS+'g', {'transform': f'translate({x} {y}) scale({target_width/source_width:.8f})'})
        for child in source:
            if child.tag == NS+'title':
                continue
            shape = copy.deepcopy(child)
            for element in shape.iter():
                if element.get('fill') == NAVY:
                    element.set('fill', palette[0])
                elif element.get('fill') == GREEN:
                    element.set('fill', palette[1])
            group.append(shape)
    return ET.tostring(doc, encoding='utf-8', xml_declaration=True)


def export_svg(name, data):
    path = ROOT / 'svg' / f'{name}.svg'
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(data)
    return path


def raster(svg, output, width):
    output.parent.mkdir(parents=True, exist_ok=True)
    run('rsvg-convert', '--width', width, '--output', output, svg)


def build():
    for layout, geometry in LAYOUTS.items():
        for variant, palette in PALETTES.items():
            name = f'helseark-{layout}-{variant}'
            svg = export_svg(name, svg_document(geometry, palette))
            for width in WIDTHS[layout]:
                raster(svg, ROOT/'png'/f'{name}-{width}.png', width)
            for fmt in ('pdf', 'eps'):
                folder = ROOT/fmt
                folder.mkdir(exist_ok=True)
                # EPS is opaque; a dark backing keeps reversed/white art visible.
                background = NAVY if variant in ('white', 'reverse') else PAPER
                args = ['rsvg-convert', '--format', fmt, '--output', folder/f'{name}.{fmt}']
                if fmt == 'eps':
                    args += ['--background-color', background]
                run(*args, svg)
                if fmt == 'eps':
                    eps = folder/f'{name}.{fmt}'
                    eps.write_bytes(b'\n'.join(line.rstrip(b' \t') for line in eps.read_bytes().split(b'\n')))
            png = ROOT/'png'/f'{name}-{WIDTHS[layout][-1]}.png'
            for fmt in ('webp', 'jpg', 'tiff'):
                folder = ROOT/fmt
                folder.mkdir(exist_ok=True)
                args = ['magick', png]
                if fmt in ('jpg', 'tiff'):
                    args += ['-background', NAVY if variant in ('reverse', 'white') else PAPER,
                             '-alpha', 'remove', '-alpha', 'off']
                else:
                    args += ['-define', 'webp:lossless=true']
                if fmt == 'tiff':
                    args += ['-units', 'PixelsPerInch', '-density', '300', '-compress', 'LZW']
                run(*args, '-quality', '95', folder/f'{name}.{fmt}')

    for name, width, height, layout in [
        ('social', 1200, 630, (160, 205, 880)),
        ('repository', 1280, 640, (160, 210, 960)),
        ('banner', 2560, 640, (520, 130, 1520)),
        ('portrait', 1080, 1350, (120, 255, 840)),
    ]:
        for theme, background, variant in [('light', PAPER, 'color'), ('dark', NAVY, 'reverse')]:
            x, y, target_width = layout
            form = 'stacked' if name == 'portrait' else 'horizontal'
            nested = svg_document(LAYOUTS[form], PALETTES[variant])
            doc = ET.Element(NS+'svg', {'viewBox': f'0 0 {width} {height}', 'width':str(width), 'height':str(height)})
            ET.SubElement(doc, NS+'title').text = 'Helseark — Quiet Ark'
            ET.SubElement(doc, NS+'rect', {'width':'100%', 'height':'100%', 'fill':background})
            group = ET.SubElement(doc, NS+'g', {'transform':f'translate({x} {y}) scale({target_width/LAYOUTS[form][0]})'})
            for child in ET.fromstring(nested):
                if child.tag != NS+'title':
                    group.append(child)
            svg = export_svg(f'helseark-{name}-{theme}', ET.tostring(doc, encoding='utf-8', xml_declaration=True))
            output = ROOT/'banners'/f'helseark-{name}-{theme}.png'
            raster(svg, output, width)
            run('magick', output, '-quality', '95', output.with_suffix('.jpg'))
            run('magick', output, '-define', 'webp:lossless=true', output.with_suffix('.webp'))

    favicons = ROOT/'favicon'
    favicons.mkdir(exist_ok=True)
    for size in (16, 32, 48, 180, 192, 512):
        raster(ROOT/'svg/helseark-icon-color.svg', favicons/f'favicon-{size}.png', size)
    adaptive = ET.parse(ROOT/'svg/helseark-icon-color.svg').getroot()
    ET.SubElement(adaptive, NS+'style').text = '@media (prefers-color-scheme: dark) { [fill="#102B49"] { fill: #FFFFFF; } [fill="#66A786"] { fill: #82C3A3; } }'
    (favicons/'favicon.svg').write_bytes(ET.tostring(adaptive, encoding='utf-8', xml_declaration=True))
    (favicons/'safari-pinned-tab.svg').write_bytes((ROOT/'svg/helseark-icon-black.svg').read_bytes())
    (favicons/'apple-touch-icon.png').write_bytes((favicons/'favicon-180.png').read_bytes())
    # An opaque Apple icon and generous maskable safe zone survive platform crops.
    run('magick', favicons/'apple-touch-icon.png', '-background', PAPER, '-alpha', 'remove', '-alpha', 'off', favicons/'apple-touch-icon.png')
    maskable = export_svg('helseark-icon-maskable', svg_document((512,512,[('symbol',128,153,256)]), PALETTES['color'], PAPER))
    raster(maskable, favicons/'maskable-512.png', 512)
    run('magick', ROOT/'png/helseark-icon-color-256.png', '-define', 'icon:auto-resize=256,128,64,48,32,16', favicons/'favicon.ico')
    (favicons/'site.webmanifest').write_text(json.dumps({
        'name':'Helseark', 'short_name':'Helseark',
        'icons':[
            {'src':f'favicon-{s}.png','sizes':f'{s}x{s}','type':'image/png','purpose':'any'} for s in (192,512)
        ] + [{'src':'maskable-512.png','sizes':'512x512','type':'image/png','purpose':'maskable'}],
        'theme_color':NAVY, 'background_color':PAPER, 'display':'standalone'
    }, indent=2)+'\n')

    files = sorted(p for folder in ('svg','png','webp','jpg','tiff','pdf','eps','favicon','banners') for p in (ROOT/folder).iterdir())
    manifest = []
    for path in files:
        record = {'file':str(path.relative_to(ROOT)), 'bytes':path.stat().st_size,
                  'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        if path.suffix in ('.png','.webp','.jpg','.tiff'):
            dimensions = subprocess.check_output(['magick', 'identify', '-format', '%w %h', str(path)], text=True)
            record['width'], record['height'] = map(int, dimensions.split())
        manifest.append(record)
    (ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'Exported {len(files)} assets to {ROOT}')


if __name__ == '__main__':
    build()
