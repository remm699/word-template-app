#!/usr/bin/env python3
"""apply_model_v2.py — rebuild a .docx from modele.dotx skeleton, preserving body
content: text, images, hyperlinks (incl. in-drawing hlinkClick), SmartArt
diagrams, numbering (lists), notes. Handles document2.xml main parts too.
Usage: python3 apply_model_v2.py <source.docx> <output.docx>
Set MODEL to the .dotx path (env MODEL overrides).
"""
import zipfile, re, sys, os

MODEL = os.environ.get('MODEL', 'modele.dotx')


def read_zip(path):
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}


def write_zip(path, parts):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in sorted(parts):
            z.writestr(name, parts[name])


def parse_rels(xml):
    out = {}
    if not xml:
        return out
    for m in re.finditer(
            r'<Relationship\s+Id="([^"]+)"\s+Type="([^"]+)"\s+Target="([^"]+)"(?:\s+TargetMode="([^"]+)")?',
            xml):
        out[m.group(1)] = (m.group(2), m.group(3), m.group(4) or '')
    return out


def build(source_path, out_path):
    model = read_zip(MODEL)
    src = read_zip(source_path)

    # locate main document part (normal, or document2.xml)
    src_doc_name = 'word/document.xml'
    if src_doc_name not in src:
        for cand in ('word/document2.xml', 'word/document1.xml'):
            if cand in src:
                src_doc_name = cand
                break
    src_rels_name = 'word/_rels/' + os.path.basename(src_doc_name) + '.rels'

    model_doc = model['word/document.xml'].decode('utf-8')
    m = re.search(r'<w:sectPr\b.*?</w:sectPr>', model_doc, re.S)
    if not m:
        raise RuntimeError('model has no sectPr')
    model_sectpr = m.group(0)

    src_doc = src[src_doc_name].decode('utf-8')
    bs = src_doc.index('<w:body>') + len('<w:body>')
    be = src_doc.index('</w:body>')
    body = src_doc[bs:be]
    body = re.sub(r'<w:sectPr\b.*?</w:sectPr>', '', body, flags=re.S)

    srels = parse_rels(src.get(src_rels_name, b'').decode('utf-8', 'replace'))

    rels_path = 'word/_rels/document.xml.rels'
    mrels_xml = model[rels_path].decode('utf-8')
    m_targets = set(re.findall(r'Target="([^"]+)"', mrels_xml))

    counter = 200
    add_rel = []
    used_map = {}
    new_parts = dict(model)

    def new_rid():
        nonlocal counter
        counter += 1
        return f'rId{counter}'

    def name_taken(cand):
        return cand in new_parts or cand in m_targets

    def rewrite(body, rid, nr):
        # rewrite every relation reference to this rid (any prefix: r:embed, r:id, r:link, r:dm...)
        return re.sub(rf'((?:embed|id|link|dm|lo|qs|cs)="){rid}(")', rf'\g<1>{nr}\g<2>', body)

    # ---- collect every relation ref in body ----
    all_rids = set(re.findall(r'(?:embed|id|link|dm|lo|qs|cs)="(rId\d+)"', body))

    for rid in sorted(all_rids, key=lambda x: int(x[3:])):
        if rid not in srels or rid in used_map:
            continue
        rtype, target, tmode = srels[rid]
        rshort = rtype.split('/')[-1]

        # --- image ---
        if 'image' in rtype:
            media = target if target.startswith('word/') else 'word/' + target
            raw = src.get(media) or src.get(target)
            if raw is None:
                continue
            base = os.path.basename(target)
            stem, ext = os.path.splitext(base)
            cand = 'word/media/' + base
            if name_taken(cand):
                cand = f'word/media/{stem}_{counter}{ext}'
            new_parts[cand] = raw
            m_targets.add(cand)
            nr = new_rid()
            add_rel.append(f'<Relationship Id="{nr}" Type="{rtype}" Target="{cand[len("word/"):]}"/>')
            used_map[rid] = nr
            body = rewrite(body, rid, nr)

        # --- diagram parts (SmartArt etc.) ---
        elif 'diagram' in rshort or 'diagram' in rtype:
            for n in list(src):
                if n.startswith('word/diagrams/') and n not in new_parts:
                    new_parts[n] = src[n]
                if '_rels' in n and 'diagrams' in n and n not in new_parts:
                    new_parts[n] = src[n]
            nr = new_rid()
            add_rel.append(f'<Relationship Id="{nr}" Type="{rtype}" Target="{target}"/>')
            used_map[rid] = nr
            body = rewrite(body, rid, nr)

        # --- hyperlink (incl. a:hlinkClick / picAttrSrcUrl) ---
        elif 'hyperlink' in rtype:
            nr = new_rid()
            extm = ' TargetMode="External"' if tmode else ''
            add_rel.append(f'<Relationship Id="{nr}" Type="{rtype}" Target="{target}"{extm}/>')
            used_map[rid] = nr
            body = rewrite(body, rid, nr)

        # --- anything else referenced from body (footnote refs, ole, etc.) ---
        else:
            part = target if target.startswith('word/') else 'word/' + target
            if part in src and part not in new_parts:
                new_parts[part] = src[part]
            nr = new_rid()
            add_rel.append(f'<Relationship Id="{nr}" Type="{rtype}" Target="{target}"/>')
            used_map[rid] = nr
            body = rewrite(body, rid, nr)

    # ---------- numbering (lists) ----------
    if 'word/numbering.xml' in src and 'word/numbering.xml' not in new_parts:
        new_parts['word/numbering.xml'] = src['word/numbering.xml']
        nr = new_rid()
        add_rel.append('<Relationship Id="%s" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>' % nr)
        num_rels = src.get('word/_rels/numbering.xml.rels', b'').decode('utf-8', 'replace')
        for n in src:
            if n.startswith('word/_rels/numbering') and n.endswith('.rels') and n not in new_parts:
                new_parts[n] = src[n]
            if n.startswith('word/media/') and n not in new_parts:
                base_n = os.path.basename(n)
                if num_rels and ('media/' + base_n) in num_rels:
                    new_parts[n] = src[n]
        ct = new_parts['[Content_Types].xml'].decode('utf-8')
        if 'numbering+xml' not in ct:
            ct = ct.replace('</Types>', '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/></Types>')
        new_parts['[Content_Types].xml'] = ct.encode('utf-8')

    # ---------- footnotes/endnotes: keep source's if it has real notes ----------
    for part in ('word/footnotes.xml', 'word/endnotes.xml'):
        if part in src and src[part].count(b'<w:footnote') > 3:
            new_parts[part] = src[part]
        elif part in src and part not in new_parts:
            new_parts[part] = src[part]

    # ---------- assemble ----------
    head = model_doc[:model_doc.index('<w:body>') + len('<w:body>')]
    tail = model_doc[model_doc.index('</w:body>'):]
    new_parts['word/document.xml'] = (head + body + model_sectpr + tail).encode('utf-8')

    if add_rel:
        mrels_xml = mrels_xml.replace('</Relationships>', ''.join(add_rel) + '</Relationships>')
    new_parts[rels_path] = mrels_xml.encode('utf-8')

    # content types: switch template.main+xml -> document.main+xml (model is a .dotx)
    ct = new_parts['[Content_Types].xml'].decode('utf-8')
    ct = ct.replace(
        'application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml')
    ext_map = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'gif': 'image/gif',
               'bmp': 'image/bmp', 'wmf': 'image/x-wmf', 'emf': 'image/x-emf', 'tif': 'image/tiff',
               'tiff': 'image/tiff', 'svg': 'image/svg+xml', 'webp': 'image/webp'}
    for k in new_parts:
        if k.startswith('word/media/'):
            e = k.rsplit('.', 1)[-1].lower()
            if f'Extension="{e}"' not in ct and f'Extension="{e.upper()}"' not in ct:
                ct = ct.replace('</Types>', f'<Default Extension="{e}" ContentType="{ext_map.get(e, "application/octet-stream")}"/></Types>')
    new_parts['[Content_Types].xml'] = ct.encode('utf-8')

    write_zip(out_path, new_parts)
    print(f'built {out_path}')


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('usage: apply_model_v2.py <source.docx> <output.docx>')
        sys.exit(1)
    build(sys.argv[1], sys.argv[2])