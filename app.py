#!/usr/bin/env python3
"""word-template-app — Application web pour appliquer un modèle .dotx
à une série de documents .docx (fichiers ou dossiers, récursif).

Lancement :  python3 -m uvicorn app:app --host 0.0.0.0 --port 8080
"""
import os
import json
import uuid
import threading
import shutil
import tempfile
import time
import re

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi import Request

import processor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOBS_DIR = os.path.join(BASE_DIR, 'jobs')          # dossiers de travail par job
ZIPS_DIR = os.path.join(BASE_DIR, 'zips')           # archives prêtes à télécharger
MAX_PART_SIZE = 512 * 1024 * 1024                   # 512 Mo par upload

os.makedirs(JOBS_DIR, exist_ok=True)
os.makedirs(ZIPS_DIR, exist_ok=True)

app = FastAPI(title="Word Template App")

# ---------------------------------------------------------------------------
# État des jobs (en mémoire + dossiers sur disque)
JOBS = {}          # job_id -> dict état
JOBS_LOCK = threading.Lock()


def new_job():
    job_id = uuid.uuid4().hex[:12]
    job_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    state = {
        'id': job_id,
        'dir': job_dir,
        'status': 'pending',          # pending | running | done | error
        'error': None,
        'done': 0,
        'total': 0,
        'current': None,
        'results': [],
        'out_dir': os.path.join(job_dir, 'sortie'),
        'created': time.time(),
        'started': None,
        'finished': None,
    }
    with JOBS_LOCK:
        JOBS[job_id] = state
    return state


# ---------------------------------------------------------------------------
# Nommage des archives : <nom_dossier_ou_fichier>_resultat.zip

def sanitize_base(name):
    """Nettoie un nom pour en faire un nom de fichier sûr."""
    name = re.sub(r'[\\/:*?"<>|]+', '_', name).strip(' ._')
    return name[:80] or 'documents'


def archive_base_name(local_dir, inputs):
    """Détermine le nom de base de l'archive :
    - dossier local serveur  -> nom du dossier
    - upload avec relpaths   -> nom du dossier racine commun (ou 1er fichier)
    - sinon, fichier seul    -> nom du premier fichier sans extension"""
    base = 'documents'
    if local_dir.strip():
        base = os.path.basename(local_dir.strip().rstrip('/'))
    elif inputs:
        # inputs = [(relpath, abs)] — le relpath peut contenir des sous-dossiers
        rels = [r for r, _ in inputs]
        roots = {r.split('/')[0] for r in rels if '/' in r}
        if len(roots) == 1:
            base = roots.pop()                      # dossier racine commun
        else:
            first = os.path.basename(rels[0])
            base = os.path.splitext(first)[0]       # premier fichier
    return sanitize_base(base)


def make_zip_name(job_id, base):
    """Nom d'archive unique : <base>_resultat.zip, suffixe (2), (3)… si conflit."""
    cand = f'{base}_resultat.zip'
    n = 2
    while os.path.exists(os.path.join(ZIPS_DIR, cand)) or \
            os.path.exists(os.path.join(ZIPS_DIR, cand + '.job')):
        cand = f'{base}_resultat({n}).zip'
        n += 1
    # fichier compagnon : mémorise le job associé (pour la suppression)
    with open(os.path.join(ZIPS_DIR, cand + '.job'), 'w') as fh:
        fh.write(job_id)
    return cand


def job_id_from_zip(zip_name):
    """Retrouve le job associé à une archive (via le fichier .job,
    ou l'ancien format <job_id>_resultats.zip)."""
    job_file = os.path.join(ZIPS_DIR, zip_name + '.job')
    if os.path.isfile(job_file):
        with open(job_file) as fh:
            return fh.read().strip()
    m = re.match(r'^([0-9a-f]{12})_resultats\.zip$', zip_name)
    if m:
        return m.group(1)
    return None


def run_job(job_id):
    state = JOBS[job_id]
    try:
        with JOBS_LOCK:
            state['status'] = 'running'
            state['started'] = time.time()

        inputs = state['inputs']
        total = len(inputs)
        with JOBS_LOCK:
            state['total'] = total

        def progress_cb(i, total, rel, ok):
            with JOBS_LOCK:
                state['done'] = i
                state['current'] = rel

        results = processor.process_batch(
            model_path=state['model_path'],
            inputs=inputs,
            out_root=state['out_dir'],
            font_name=state['font_name'],
            embed=state['embed'],
            uploaded_ttfs=state.get('uploaded_ttfs'),
            local_font_dir=state.get('local_font_dir'),
            progress_cb=progress_cb,
        )
        if results is None:
            # pas de police disponible pour l'intégration
            with JOBS_LOCK:
                state['status'] = 'error'
                state['error'] = 'Aucun fichier .ttf disponible pour intégrer la police.'
            return

        # copier le modèle et les sources dans le job (trace + débogage)
        with JOBS_LOCK:
            state['results'] = results
            state['status'] = 'done'
            state['finished'] = time.time()

        # générer l'archive zip des résultats (téléchargements persistants)
        try:
            zip_name = make_zip_name(state['id'], state.get('archive_base', 'documents'))
            zip_path = os.path.join(ZIPS_DIR, zip_name)
            processor.zip_dir(state['out_dir'], zip_path)
            state['zip_name'] = zip_name
            print(f'archive générée : {zip_name}')
        except Exception as e:
            print(f'zip generation failed: {e}')
    except Exception as e:
        import traceback
        traceback.print_exc()
        with JOBS_LOCK:
            state['status'] = 'error'
            state['error'] = str(e)
            state['finished'] = time.time()


# ---------------------------------------------------------------------------
# Page principale

@app.get('/', response_class=HTMLResponse)
async def index():
    with open(os.path.join(BASE_DIR, 'templates', 'index.html'), encoding='utf-8') as fh:
        content = fh.read()
    resp = HTMLResponse(content=content)
    resp.headers['Cache-Control'] = 'no-store'
    return resp


# ---------------------------------------------------------------------------
# Création d'un job (upload du modèle, des documents, de la police)

@app.post('/api/process')
async def api_process(
    model: UploadFile = File(...),
    files: list[UploadFile] = File(default=[]),
    relpaths: str = Form('[]'),
    local_dir: str = Form(''),
    font_name: str = Form(''),
    embed: str = Form('false'),
    font_files: list[UploadFile] = File(default=[]),
    local_font_dir: str = Form(''),
):
    # 1) vérifier le modèle
    if not model.filename.lower().endswith('.dotx'):
        raise HTTPException(400, 'Le modèle doit être un fichier .dotx')

    job = new_job()

    # 2) modèle -> disque
    model_path = os.path.join(job['dir'], 'modele.dotx')
    with open(model_path, 'wb') as fh:
        while chunk := await model.read(1 << 20):
            fh.write(chunk)

    # 3) documents uploadés (structure préservée via relpaths)
    inputs = []
    try:
        rel_list = json.loads(relpaths) if relpaths else []
    except json.JSONDecodeError:
        rel_list = []
    if len(rel_list) != len(files):
        rel_list = [f.filename or f'f{i}.docx' for i, f in enumerate(files)]

    src_root = os.path.join(job['dir'], 'sources')
    for i, (up, rel) in enumerate(zip(files, rel_list)):
        if not up.filename:
            continue
        if not rel or rel.startswith('/') or '..' in rel.split('/'):
            rel = os.path.basename(up.filename)
        dest = os.path.join(src_root, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, 'wb') as fh:
            while chunk := await up.read(1 << 20):
                fh.write(chunk)
        if rel.lower().endswith('.docx'):
            inputs.append((rel, dest))

    # 4) dossier local serveur (récursif)
    if local_dir.strip():
        if not os.path.isdir(local_dir.strip()):
            with JOBS_LOCK:
                JOBS[job['id']]['status'] = 'error'
                JOBS[job['id']]['error'] = f'Dossier local introuvable : {local_dir}'
            return JSONResponse({'job_id': job['id']})
        for rel, abs_p in processor.find_docx_recursive(local_dir.strip()):
            inputs.append((rel, abs_p))

    if not inputs:
        with JOBS_LOCK:
            JOBS[job['id']]['status'] = 'error'
            JOBS[job['id']]['error'] = 'Aucun document .docx trouvé (upload ou dossier local).'
        return JSONResponse({'job_id': job['id']})

    # 5) polices uploadées
    uploaded_ttfs = []
    for ff in font_files:
        if ff.filename:
            data = await ff.read()
            uploaded_ttfs.append((ff.filename, data))

    with JOBS_LOCK:
        JOBS[job['id']].update({
            'inputs': inputs,
            'model_path': model_path,
            'font_name': font_name.strip(),
            'embed': embed.lower() in ('true', '1', 'on'),
            'uploaded_ttfs': uploaded_ttfs,
            'local_font_dir': local_font_dir.strip() or None,
            'archive_base': archive_base_name(local_dir, inputs),
        })

    # 6) lancer le traitement dans un thread
    t = threading.Thread(target=run_job, args=(job['id'],), daemon=True)
    t.start()

    return JSONResponse({'job_id': job['id']})


# ---------------------------------------------------------------------------
# Suivi d'un job

@app.get('/api/job/{job_id}')
async def api_job(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, 'Job inconnu')
    return JSONResponse({
        'id': job['id'],
        'status': job['status'],
        'error': job['error'],
        'done': job['done'],
        'total': job['total'],
        'current': job['current'],
        'results': job['results'] if job['status'] in ('done', 'error') else [],
    })


# ---------------------------------------------------------------------------
# Téléchargement des résultats (zip)

@app.get('/api/job/{job_id}/download')
async def api_download(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, 'Job inconnu')
    if job['status'] != 'done':
        raise HTTPException(400, 'Le job n’est pas terminé')

    zip_name = job.get('zip_name')
    if not zip_name:
        zip_name = f'{job_id}_resultats.zip'  # ancien format
    zip_path = os.path.join(ZIPS_DIR, zip_name)
    if not os.path.exists(zip_path):
        processor.zip_dir(job['out_dir'], zip_path)
    return FileResponse(zip_path, filename=zip_name, media_type='application/zip')


# ---------------------------------------------------------------------------
# Liste des archives .zip déjà générées (téléchargements persistants)

@app.get('/api/downloads')
async def api_downloads():
    """Liste les zips générés par le serveur (les plus récents d'abord)."""
    items = []
    for fname in os.listdir(ZIPS_DIR):
        if not fname.lower().endswith('.zip'):
            continue
        path = os.path.join(ZIPS_DIR, fname)
        st = os.stat(path)
        items.append({
            'name': fname,
            'size': st.st_size,
            'mtime': st.st_mtime,
        })
    items.sort(key=lambda d: d['mtime'], reverse=True)
    return JSONResponse(items)


@app.get('/api/download/{fname}')
async def api_download_named(fname: str):
    """Télécharge une archive existante par son nom (anti-traversée de chemin)."""
    import posixpath
    safe = posixpath.basename(fname)
    if not safe.lower().endswith('.zip'):
        raise HTTPException(400, 'Nom invalide')
    path = os.path.join(ZIPS_DIR, safe)
    if not os.path.isfile(path):
        raise HTTPException(404, 'Archive introuvable')
    return FileResponse(path, filename=safe, media_type='application/zip')


@app.delete('/api/download/{fname}')
async def api_delete_download(fname: str):
    """Supprime une archive .zip et, si le job correspondant est encore en
    mémoire, son dossier complet (modèle + sources uploadées + résultats)."""
    import posixpath
    safe = posixpath.basename(fname)
    if not safe.lower().endswith('.zip'):
        raise HTTPException(400, 'Nom invalide')
    path = os.path.join(ZIPS_DIR, safe)
    if not os.path.isfile(path):
        raise HTTPException(404, 'Archive introuvable')

    # remonter au job via le fichier compagnon .job (ou l'ancien format de nom)
    job_id = job_id_from_zip(safe)

    job_dir = None
    job_present = False
    with JOBS_LOCK:
        job = JOBS.get(job_id) if job_id else None
        if job and job['status'] in ('pending', 'running'):
            raise HTTPException(409, 'Le job associé est encore en cours de traitement — suppression refusée.')
        if job:
            job_dir = job['dir']
            job_present = True
            JOBS.pop(job_id, None)
        elif job_id:
            # job plus en mémoire mais dossier possiblement resté sur disque
            job_dir = os.path.join(JOBS_DIR, job_id)

    # suppression de l'archive (+ son fichier compagnon .job)
    os.remove(path)
    job_file = path + '.job'
    if os.path.isfile(job_file):
        os.remove(job_file)

    # suppression du dossier du job (sources uploadées + sortie résultats + modèle)
    deleted = {'job_dir': False, 'sources': False, 'sortie': False}
    if job_dir and os.path.isdir(job_dir):
        deleted['sources'] = os.path.isdir(os.path.join(job_dir, 'sources'))
        deleted['sortie'] = os.path.isdir(os.path.join(job_dir, 'sortie'))
        shutil.rmtree(job_dir, ignore_errors=True)
        deleted['job'] = True

    return JSONResponse({
        'deleted': safe,
        'job_in_memory': job_present,
        **deleted,
    })


@app.get('/api/health')
async def health():
    return {'ok': True}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8080)