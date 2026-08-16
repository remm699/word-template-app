#!/usr/bin/env python3
"""processor.py — moteur de traitement pour l'app web.
Applique un modèle .dotx à une série de .docx :
  1. reconstruction depuis le squelette du modèle (apply_model_v2)
  2. pied de page « nom du fichier » (update_footer)
  3. police forcée (set_fonts)
  4. intégration des polices .ttf (facultatif, embed_fonts)
L'arborescence relative des entrées est préservée dans le dossier de sortie.
Les originaux ne sont JAMAIS modifiés (le résultat va dans le dossier de sortie).
"""
import os
import re
import zipfile
import shutil
import importlib.util
import tempfile

# --- chargement des scripts du skill (réutilisés tels quels) -------------------
SCRIPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts')

def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPT_DIR, name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

apply_model_v2 = _load('apply_model_v2')
set_fonts_mod = _load('set_fonts')
embed_fonts_mod = _load('embed_fonts')

DEFAULT_POPPINS_DIR = os.path.expanduser('~/.hermes/profiles/techno/assets/poppins')

# ------------------------------------------------------------------------------
# Utilitaires

def escape_xml(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def update_footer(path, name):
    """Remplace la valeur en cache du champ FILENAME du pied de page
    (« Document1 ») par le nom du document (sans extension)."""
    name_esc = escape_xml(name)
    with zipfile.ZipFile(path) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    if 'word/footer1.xml' not in parts:
        return 0
    footer = parts['word/footer1.xml'].decode('utf-8')
    new_footer, n = re.subn(
        r'(<w:fldSimple\s+w:instr="[^"]*FILENAME[^"]*">.*?<w:t[^>]*>)[^<]*(</w:t>)',
        lambda m: m.group(1) + name_esc + m.group(2),
        footer, flags=re.S)
    if n == 0:  # repli : « Document1 » nu dans le pied de page
        new_footer, n = re.subn(
            r'(<w:t[^>]*>)Document1(</w:t>)',
            lambda m: m.group(1) + name_esc + m.group(2), footer)
    parts['word/footer1.xml'] = new_footer.encode('utf-8')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for k in sorted(parts):
            z.writestr(k, parts[k])
    return n


def collect_fonts(font_name, uploaded_ttfs=None, local_font_dir=None):
    """Détermine le dossier des .ttf à intégrer.
    Priorité : fichiers uploadés > dossier local serveur > Poppins par défaut.
    Retourne un chemin de dossier ou None."""
    if uploaded_ttfs:
        tmp = tempfile.mkdtemp(prefix='wordapp_fonts_')
        n = 0
        for fname, data in uploaded_ttfs:
            if fname.lower().endswith('.ttf'):
                with open(os.path.join(tmp, os.path.basename(fname)), 'wb') as fh:
                    fh.write(data)
                n += 1
        return tmp if n else None
    if local_font_dir and os.path.isdir(local_font_dir):
        return local_font_dir
    if (font_name or '').lower() == 'poppins' and os.path.isdir(DEFAULT_POPPINS_DIR):
        return DEFAULT_POPPINS_DIR
    return None


def process_docx(model_path, src_path, out_path, font_name=None, embed_fonts=False, font_dir=None):
    """Applique le modèle à un document. Retourne la liste des étapes effectuées."""
    log = []
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    # 1) reconstruction depuis le squelette du modèle
    old_model = apply_model_v2.MODEL
    apply_model_v2.MODEL = model_path
    try:
        apply_model_v2.build(src_path, out_path)
    finally:
        apply_model_v2.MODEL = old_model
    log.append('modèle')

    # 2) pied de page = nom du fichier
    name = os.path.splitext(os.path.basename(out_path))[0]
    update_footer(out_path, name)
    log.append('pied de page')

    # 3) police forcée (si demandé)
    if font_name:
        set_fonts_mod.TARGET_FONT = font_name
        set_fonts_mod.process(out_path)
        log.append('police ' + font_name)

    # 4) intégration de la police (facultatif)
    if embed_fonts and font_dir:
        embed_fonts_mod.FONTS_DIR = font_dir
        embed_fonts_mod.process(out_path)
        log.append('polices intégrées')

    return log


def process_batch(model_path, inputs, out_root, font_name=None,
                  embed=False, uploaded_ttfs=None, local_font_dir=None,
                  progress_cb=None):
    """inputs : liste de (relpath, chemin_abs_source) — l'arborescence relative
    est recréée sous out_root. Retourne une liste de résultats.essa"""
    font_dir = None
    if embed:
        font_dir = collect_fonts(font_name, uploaded_ttfs, local_font_dir)
        if font_dir is None:
            return None, 'Aucun fichier .ttf disponible pour intégrer la police. ' \
                          'Uploader la police ou donner un dossier local de polices.'
    results = []
    total = len(inputs)
    for i, (rel, src) in enumerate(inputs, 1):
        out = os.path.join(out_root, rel)
        try:
            log = process_docx(model_path, src, out, font_name, embed, font_dir)
            results.append({'rel': rel, 'ok': True, 'error': None, 'log': log})
        except Exception as e:
            results.append({'rel': rel, 'ok': False, 'error': str(e), 'log': []})
        if progress_cb:
            progress_cb(i, total, rel, results[-1]['ok'])
    return results


def find_docx_recursive(root_dir):
    """Liste (rel, abs) des .docx sous root_dir, récursivement."""
    out = []
    for dirpath, _, filenames in os.walk(root_dir):
        for fn in sorted(filenames):
            if fn.lower().endswith('.docx'):
                abs_p = os.path.join(dirpath, fn)
                out.append((os.path.relpath(abs_p, root_dir), abs_p))
    return out


def zip_dir(src_dir, zip_path):
    """Archive récursive d'un dossier."""
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for dirpath, _, filenames in os.walk(src_dir):
            for fn in sorted(filenames):
                abs_p = os.path.join(dirpath, fn)
                rel = os.path.relpath(abs_p, src_dir)
                z.write(abs_p, rel)