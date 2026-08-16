# Word Template App — image de production
FROM python:3.11-slim

WORKDIR /app

# Dépendances d'abord (cache de build efficace)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code de l'application
COPY app.py processor.py run.sh ./
COPY templates ./templates
COPY static ./static
COPY scripts ./scripts

# Dossiers de travail (souvent montés en volumes en production)
RUN mkdir -p jobs zips

EXPOSE 8091

# Lancement via python3 -m uvicorn (le pattern fiable — voir skill ssh-nas-zimaos)
CMD ["python3", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8091"]