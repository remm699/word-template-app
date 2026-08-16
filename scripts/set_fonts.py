#!/usr/bin/env python3
"""Force all fonts in a docx to a target font (default Poppins).
   python3 set_fonts.py <doc1.docx> [doc2.docx ...]
Rewrites rFonts in document.xml + headers/footers, sets the theme Latin
typeface, and updates docDefaults in styles.xml. Edit TARGET_FONT below."""
import zipfile, re, os, sys

TARGET_FONT = 'Poppins'


def set_fonts_xml(xml):
    def repl(m):
        tag = m.group(0)
        for attr in ['ascii', 'hAnsi', 'cs', 'eastAsia', 'asciiTheme', 'hAnsiTheme', 'eastAsiaTheme', 'cstheme']:
            tag = re.sub(rf'\s+w:{attr}="[^"]*"', '', tag)
        tag = tag.replace('/>', f' w:ascii="{TARGET_FONT}" w:hAnsi="{TARGET_FONT}" w:cs="{TARGET_FONT}"/>')
        return tag
    return re.sub(r'<w:rFonts[^>]*/>', repl, xml)


def process(path):
    with zipfile.ZipFile(path) as z:
        parts = {n: z.read(n) for n in z.namelist()}

    theme = parts.get('word/theme/theme1.xml')
    if theme:
        tx = theme.decode('utf-8')
        tx2 = re.sub(r'<a:latin[^>]*/>',
                     lambda m: re.sub(r'typeface="[^"]*"', f'typeface="{TARGET_FONT}"', m.group(0)), tx)
        if tx2 != tx:
            parts['word/theme/theme1.xml'] = tx2.encode('utf-8')

    styles = parts.get('word/styles.xml')
    if styles:
        sx = styles.decode('utf-8')
        if 'docDefaults' in sx:
            sx2 = re.sub(
                r'(<w:rPrDefault><w:rPr>)(.*?)(</w:rPr></w:rPrDefault>)',
                lambda m: m.group(1) + re.sub(
                    r'<w:rFonts[^>]*/>',
                    f'<w:rFonts w:ascii="{TARGET_FONT}" w:hAnsi="{TARGET_FONT}" w:cs="{TARGET_FONT}" w:eastAsia="{TARGET_FONT}"/>',
                    m.group(2)) + m.group(3),
                sx, count=1, flags=re.S)
            if sx2 != sx:
                parts['word/styles.xml'] = sx2.encode('utf-8')

    targets = ['word/document.xml']
    for name in list(parts):
        if name.startswith('word/header') or name.startswith('word/footer'):
            targets.append(name)
    for part in targets:
        if part not in parts:
            continue
        xml = parts[part].decode('utf-8')
        new = set_fonts_xml(xml)
        if new != xml:
            parts[part] = new.encode('utf-8')

    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for k in sorted(parts):
            z.writestr(k, parts[k])

    from collections import Counter
    with zipfile.ZipFile(path) as z:
        doc = z.read('word/document.xml').decode('utf-8')
    fonts = re.findall(r'w:(?:ascii|hAnsi)="([^"]+)"', doc)
    cnt = Counter(f for f in fonts if f != TARGET_FONT)
    print(f'{path}: non-{TARGET_FONT}_runs={dict(cnt) if cnt else "OK-ALL-" + TARGET_FONT}')


if __name__ == '__main__':
    for f in sys.argv[1:]:
        if os.path.exists(f):
            process(f)
        else:
            print('MISSING:', f)
    print('DONE')
