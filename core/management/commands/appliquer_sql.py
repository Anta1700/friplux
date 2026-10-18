"""
Applique un script SQL Frip'Lux sur la base configurée dans .env.

    python manage.py appliquer_sql sql/002_qualites_references.sql

Tout le script s'exécute dans une seule transaction : s'il échoue
à un endroit, aucune modification n'est conservée.
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


class Command(BaseCommand):
    help = "Applique un fichier SQL dans une transaction unique."

    def add_arguments(self, parser):
        parser.add_argument("fichier", help="Chemin du fichier .sql")

    def handle(self, *args, **options):
        chemin = Path(options["fichier"])
        if not chemin.is_file():
            raise CommandError(f"Fichier introuvable : {chemin}")

        sql = chemin.read_text(encoding="utf-8")
        base = connection.settings_dict.get("NAME")
        self.stdout.write(f"Application de {chemin.name} sur la base « {base} »…")

        try:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql)
        except Exception as erreur:
            raise CommandError(
                f"Échec, aucune modification n'a été enregistrée.\nDétail : {erreur}"
            ) from erreur

        self.stdout.write(self.style.SUCCESS(f"{chemin.name} appliqué avec succès."))
