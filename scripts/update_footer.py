#!/usr/bin/env python3
"""Update cached FILENAME field text in footer1.xml of each rebuilt docx.
   python3 update_footer.py
Edit the mapping list below: (file, name_without_extension)."""
import zipfile, re, os

mapping = [
    ('doc.docx', 'doc'),
]

def update(path, name):
    with zipfile.ZipFile(path) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    footer = parts['word/footer1.xml'].decode('utf-8')
    new_footer, n = re.subn(
        r'(<w:fldSimple\s+w:instr="[^"]*FILENAME[^"]*">.*?<w:t>)[^<]*(</w:t>)',
        lambda m: m.group(1) + name + m.group(2),
        footer, flags=re.S)
    parts['word/footer1.xml'] = new_footer.encode('utf-8')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for k in sorted(parts):
            z.writestr(k, parts[k])
    print(f'{path}: footer replacement count={n}')

for f, name in mapping:
    if os.path.exists(f):
        update(f, name)
    else:
        print(f'MISSING: {f}')
print('DONE')
