# Word Template App

Application web qui applique la **mise en page d'un modèle Word** (`.dotx`) à une
**série de documents Word** (`.docx`), en conservant l'intégralité du contenu
(texte, images, hyperliens, SmartArt, listes numérotées, notes de bas de page).

Interface en français, adaptée au traitement de gros dossiers (parcours récursif),
avec progression en direct et archives téléchargeables en un clic.

## ✨ Fonctionnalités

| Étape | Rôle |
|---|---|
| **1 — Modèle** | Upload d'un fichier `.dotx` (ou glisser-déposer). C'est lui qui impose : styles, en-tête/logo, pied de page, marges, format de page. |
| **2 — Documents** | Upload de fichiers `.docx` **ou d'un dossier complet** — parcours récursif, arborescence préservée. Alternative : chemin d'un dossier déjà présent sur le serveur (originaaux non modifiés). |
| **3 — Police** | Nom de la police à forcer (ex. `Poppins`) + dossier `.ttf` local **ou** upload des `.ttf`. Case **💾 Intégrer la police** pour les embarquer dans chaque document (rendu identique partout). |
| **4 — Lancer** | Bouton de traitement avec **progression en direct** et liste des résultats OK/échec **par fichier**. |
| **5 — Téléchargements** | Bouton **⬇️ Télécharger le dossier complet (zip)** + **historique** des archives (nom, taille, date) persistant après rechargement. Chaque archive a un bouton **🗑️ Supprimer**. |

## 🏷️ Nommage des archives

Les archives sont générées automatiquement à la fin d'un traitement et portent le
nom du dossier (ou du fichier) d'origine :

- Dossier `Word` → `Word_resultat.zip`
- Fichier `lettre_motivation.docx` → `lettre_motivation_resultat.zip`

En cas de collision de noms (même dossier relancé), un suffixe est ajouté :
`Word_resultat(2).zip`. Un fichier compagnon `.job` accompagne chaque archive et
permet de retrouver (et de supprimer) le traitement associé.

## 🔧 Ce que fait le traitement (par document)

1. **Reconstruction depuis le squelette du modèle** — styles, thème, en-tête/logo,
   pied de page, marges, format de page du modèle.
2. **Pied de page** — le champ `FILENAME` du modèle est résolu avec le nom du fichier.
3. **Police forcée** (facultatif) — appliquée dans tout le document.
4. **Intégration des polices `.ttf`** (facultatif, case cochée).

> ⚠️ Les originaux ne sont **jamais modifiés** : chaque résultat est écrit dans un
> dossier de sortie dédié, rassemblé ensuite dans un zip téléchargeable.

## 🚀 Installation & lancement

### Prérequis
- Python **3.11+**
- Un environnement virtuel (recommandé)

### Procédure
```bash
# 1. Récupérer le code
git clone <url-du-dépôt>
cd word-template-app

# 2. Environnement virtuel + dépendances
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Lancer le serveur
bash run.sh
#   ou directement :
python3 -m uvicorn app:app --host 0.0.0.0 --port 8091
```

### Accès
Ouvrez dans un navigateur : `http://<ip-de-la-machine>:8091/`

## 📡 API

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/` | Page web (interface) |
| `POST` | `/api/process` | Crée un job et lance le traitement (multipart : modèle, fichiers, options). Retourne `job_id`. |
| `GET` | `/api/job/{id}` | Progression / état du job (`running`, `done`, `error`). |
| `GET` | `/api/downloads` | Liste des archives générées (nom, taille, date). |
| `GET` | `/api/download/{nom}` | Téléchargement d'une archive (protégé contre les traversées de chemin). |
| `DELETE` | `/api/download/{nom}` | Supprime l'archive **et** le dossier du job associé (refus `409` si le job est encore en cours). |

La documentation OpenAPI interactive est disponible sur `/docs`.

## 🗂️ Structure

```
word-template-app/
├── app.py               # API FastAPI (jobs, upload, suivi, téléchargements)
├── processor.py         # moteur de traitement (orchestre les étapes)
├── run.sh               # script de lancement
├── requirements.txt     # dépendances
├── templates/index.html # interface web (HTML/CSS/JS)
├── static/              # ressources statiques servies
└── scripts/             # moteurs spécialisés (réutilisés du skill word-template-apply)
    ├── apply_model_v2.py  # reconstruction depuis le modèle
    ├── update_footer.py   # pied de page « nom du fichier »
    ├── set_fonts.py       # police forcée
    └── embed_fonts.py     # intégration des .ttf
```

Les dossiers `jobs/` (dossiers de travail) et `zips/` (archives) sont créés à
l'exécution et **exclus du dépôt** via `.gitignore`. Ils peuvent être supprimés
librement (anciennes sessions de traitement).

## 🔒 Sécurité

> **Ce projet a été conçu pour un usage sur un réseau local (LAN) domestique —
> **aucune authentification** n'est implémentée.** Ne l'exposez pas directement sur
> Internet. Si vous souhaitez le publier, placez-le derrière un reverse proxy avec
> authentification, ou ajoutez un écran de connexion.

## 📄 Licence

À définir selon vos besoins (aucune licence n'est encore attribuée).