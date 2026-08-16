# Installation Docker — guide pas à pas

Ce guide couvre l'installation de l'application avec Docker, sur une machine
classique puis sur le **NAS ZimaOS** (le cas réellement déployé).

L'image contient tout le nécessaire : Python 3.11-slim, FastAPI, uvicorn,
python-multipart. Les documents traités **ne quittent jamais vos dossiers**
(lecture seule) et les résultats sont téléchargeables via l'interface.

---

## 1. Machine classique (Linux, Docker + Compose installés)

### Prérequis
- Docker Engine ≥ 24 et Docker Compose v2
- Internet au moment du premier build (téléchargement de `python:3.11-slim`)

### Installation
```bash
# 1. Récupérer le code
git clone https://github.com/remm699/word-template-app.git
cd word-template-app

# 2. Build + démarrage
docker compose up -d --build
```

### Accès
Ouvrez `http://<ip-de-la-machine>:8092/`

*Si le port 8092 est occupé : modifiez la ligne `"8092:8091"` dans
`docker-compose.yml` (par exemple `"8100:8091"`).*

---

## 2. NAS ZimaOS / CasaOS (déploiement réellement validé)

ZimaOS est un OS à système racine en **lecture seule** : deux particularités
à connaître :
- **pas d'`apt`** → tout passe par Docker ;
- `docker build` échoue avec *`mkdir /root/.docker: read-only file system`*
  si `DOCKER_CONFIG` n'est pas redirigé (voir étape 4).

### Étape 1 — copier le projet sur le NAS
```bash
# Depuis une machine du réseau local (les fichiers sont root-owned sur /DATA)
scp -r word-template-app/* <utilisateur>@<ip-du-nas>:/tmp/wta/
ssh <utilisateur>@<ip-du-nas> "echo '<mot-de-passe>' | sudo -S mkdir -p /DATA/AppData/word-template-app && \
  sudo mv /tmp/wta/* /DATA/AppData/word-template-app/"
```
> **Alternative si `scp` vers `/tmp` est plus simple :** uploader via SFTP
> n'importe où dans `/tmp`, puis `sudo mv` vers `/DATA/AppData/word-template-app/`.

### Étape 2 — configuration des volumes (`docker-compose.yml`)
Le fichier fourni monte automatiquement :
| Hôte (NAS) | Conteneur | Mode | Rôle |
|---|---|---|---|
| `/DATA/Documents` | `/documents` | **`ro`** | vos documents (lecture seule, jamais modifiés) |
| `wta_jobs` (volume nommé) | `/app/jobs` | rw | dossiers de travail des traitements |
| `wta_zips` (volume nommé) | `/app/zips` | rw | archives générées |

Modifiez le chemin source si vos documents sont ailleurs (ex. `/DATA/partage`).

### Étape 3 — build + démarrage
```bash
cd /DATA/AppData/word-template-app
sudo DOCKER_CONFIG=/tmp/docker-config docker compose -f docker-compose.yml up -d --build
```

> 🔑 **`DOCKER_CONFIG=/tmp/docker-config` est indispensable sur ZimaOS** — le
> système racine étant en lecture seule, Docker ne peut pas créer
> `/root/.docker`. La variable doit être placée **après** `sudo` (sudo efface
> l'environnement sinon) : `sudo VAR=val command`.

### Étape 4 — accès et premier traitement
- Interface : **http://<ip-du-nas>:8092/** (adaptez l'IP)
- Champ « dossier déjà présent sur le serveur » :
  `/documents/partage/Word` (le point de montage est `/documents`, la source
  NAS `/DATA/Documents`, puis votre arborescence) — traitement récursif.
- Ou uploader fichiers/dossier directement via l'interface (upload HTTP).

---

## 3. Mise à jour de l'application

```bash
# Sur une machine classique :
git pull && docker compose up -d --build --force-recreate

# Sur le NAS ZimaOS (après avoir copié les nouveaux fichiers) :
sudo DOCKER_CONFIG=/tmp/docker-config docker compose -f docker-compose.yml \
  up -d --build --force-recreate
```

Les volumes nommés (`wta_jobs`, `wta_zips`) ne sont **pas** recréés : vos
traitements et archives sont conservés.

---

## 4. Sauvegarde / restauration

Les seules données à sauvegarder sont les volumes nommés :

```bash
sudo docker run --rm -v word-template-app_wta_jobs:/jobs -v word-template-app_wta_zips:/zips \
  -v $(pwd):/backup alpine tar czf /backup/wta-volumes-$(date +%F).tar.gz /jobs /zips
```

---

## 5. Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `mkdir /root/.docker: read-only file system` | système racine RO (ZimaOS) | `sudo DOCKER_CONFIG=/tmp/docker-config docker …` |
| `Address already in use` | port 8092 pris | changer le mapping dans `docker-compose.yml` |
| `curl: connection refused` | conteneur pas démarré | `docker logs word-template-app` |
| Form data requires python-multipart | dépendance manquante dans une vieille image | rebuild (l'image actuelle l'inclut) |
| L'archive téléchargée contient des noms `doc_N.docx` | relpaths absents de l'upload | utiliser des fichiers `.docx` avec leur nom d'origine |

---

## 6. Référence — variables et chemins

| Élément | Valeur |
|---|---|
| Image | `word-template-app:latest` |
| Port interne | `8091` (uvicorn) |
| Port externe (par défaut) | `8092` |
| Point de montage documents | `/docs` (ro) |
| Dossiers de travail | `/app/jobs`, `/app/zips` (volumes nommés) |
| Redémarrage auto | `restart: unless-stopped` |