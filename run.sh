#!/usr/bin/env bash
# Lance l'application Word Template App sur le port 8091
# Usage : ./run.sh   (ou : bash run.sh)
cd "$(dirname "$0")"
exec python3 -m uvicorn app:app --host 0.0.0.0 --port "${PORT:-8091}"