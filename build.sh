#!/usr/bin/env bash
# Exécuté par Render à chaque mise en ligne : installe les dépendances et prépare les fichiers statiques.
set -o errexit
pip install --upgrade pip
pip install -r requirements.txt
python manage.py collectstatic --noinput
