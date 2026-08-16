#!/usr/bin/env python3
"""Embed font .ttf files into one or more docx (standard OOXML embedding).
   python3 embed_fonts.py <doc1.docx> [doc2.docx ...]
Edit FONTS_DIR to point at a folder of .ttf variants (e.g. the Poppins set
saved at ~/.hermes/profiles/techno/assets/poppins)."""
import zipfile, re, os, sys

FONTS_DIR = os.path.expanduser('~/.hermes/profiles/techno/assets/poppins')
TTF_REL_TYPE = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/font'


def process(path):
    with zipfile.ZipFile(path) as z:
        parts = {n: z.read(n) for n in z.namelist()}

    rid = 1
    rels_entries = []
    for ttfn in sorted(os.listdir(FONTS_DIR)):
        src = os.path.join(FONTS_DIR, ttfn)
        if not ttfn.lower().endswith('.ttf') or not os.path.isfile(src):
            continue
        target = 'fonts/' + ttfn
        with open(src, 'rb') as fh:
            parts['word/' + target] = fh.read()
        rels_entries.append(f'<Relationship Id="rId{rid}" Type="{TTF_REL_TYPE}" Target="{target}"/>')
        rid += 1

    fmt_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + ''.join(rels_entries) + '</Relationships>'
    )
    parts['word/_rels/fontTable.xml.rels'] = fmt_rels.encode('utf-8')

    ct = parts['[Content_Types].xml'].decode('utf-8')
    if 'Extension="ttf"' not in ct:
        ct = ct.replace('</Types>', '<Default Extension="ttf" ContentType="application/x-font-ttf"/></Types>')
    parts['[Content_Types].xml'] = ct.encode('utf-8')

    settings = parts['word/settings.xml'].decode('utf-8')
    if 'embedTrueTypeFonts' not in settings:
        m = re.search(r'(<w:settings[^>]*>)', settings)
        if m:
            settings = settings[:m.end()] + '<w:embedTrueTypeFonts/><w:embedSystemFonts/><w:saveSubsetFonts/>' + settings[m.end():]
    parts['word/settings.xml'] = settings.encode('utf-8')

    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for k in sorted(parts):
            z.writestr(k, parts[k])
    print(f'{path}: embedded {len(rels_entries)} fonts')


if __name__ == '__main__':
    for f in sys.argv[1:]:
        if os.path.exists(f):
            process(f)
        else:
            print('MISSING:', f)
    print('DONE')
