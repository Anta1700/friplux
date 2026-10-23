"""
Lancée par Render avant chaque mise en ligne (preDeployCommand).

- Base vide (toute première mise en ligne) : ne fait rien et l'indique. Les tables Frip'Lux
  viennent de votre base actuelle, à transférer avec pg_restore (voir docs/mise_en_ligne.md).
- Base remplie : applique les migrations Django (sessions, admin…) ; sans effet si rien n'a changé.
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Prépare la base avant une mise en ligne (sans effet sur une base encore vide)."

    def handle(self, *args, **options):
        tables = set(connection.introspection.table_names())
        if "users" not in tables or "lots" not in tables:
            self.stdout.write(self.style.WARNING(
                "Base Frip'Lux encore vide : transférez vos données (pg_restore), puis relancez une mise en ligne."
            ))
            return
        call_command("migrate", interactive=False, verbosity=0)   # silencieux : jamais de « makemigrations » ici
        manquants = [s for s in ("006_mot_de_passe_provisoire", "007_stock_balles_depots", "008_facture_lien_public")
                     if not self._script_applique(s, tables)]
        if manquants:
            self.stdout.write(self.style.WARNING(
                "Scripts SQL à appliquer (Render > friplux > Shell) : "
                + ", ".join(f"python manage.py appliquer_sql sql/{m}.sql" for m in manquants)
            ))
        self.stdout.write(self.style.SUCCESS("Base prête."))

    @staticmethod
    def _script_applique(nom, tables):
        colonnes = lambda t: {c.name for c in connection.introspection.get_table_description(connection.cursor(), t)}
        if nom.startswith("006"):
            return "doit_changer_mot_de_passe" in colonnes("users")
        if nom.startswith("007"):
            return "balles" in colonnes("mouvements_stock") if "mouvements_stock" in tables else False
        if nom.startswith("008"):
            return "jeton_public" in colonnes("factures") if "factures" in tables else False
        return True
