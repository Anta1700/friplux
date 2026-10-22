"""
Regroupe un dépôt dans un autre, puis supprime le premier.

    python manage.py fusionner_depots DEPOT-PRINCIPAL DEPOT_01              (simulation)
    python manage.py fusionner_depots DEPOT-PRINCIPAL DEPOT_01 --confirmer

Tout ce qui était rattaché au premier dépôt passe au second : utilisateurs, historique des
affectations, scans, ventes, stock (réceptions), transferts… Les tables concernées sont
trouvées automatiquement dans la base (toutes celles qui font référence aux dépôts).
Le dépôt gardé est rendu actif.
Tout se fait en une seule transaction : en cas de problème, rien n'est modifié.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from core.depots import synchroniser_affectation
from core.models import AuditLogs, Depots, TransfertsStock, User


def references_aux_depots():
    """[(table, colonne)] de toutes les clés étrangères vers depots(id)."""
    with connection.cursor() as c:
        c.execute("""
            SELECT c.conrelid::regclass::text, a.attname
            FROM pg_constraint c
            JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
            WHERE c.contype = 'f' AND c.confrelid = 'depots'::regclass
            ORDER BY 1, 2
        """)
        return c.fetchall()


class Command(BaseCommand):
    help = "Regroupe un dépôt dans un autre (tout son historique), puis le supprime."

    def add_arguments(self, parser):
        parser.add_argument("depot_a_supprimer", help="Code du dépôt qui disparaît, ex. DEPOT-PRINCIPAL")
        parser.add_argument("depot_a_garder", help="Code du dépôt qui reçoit tout, ex. DEPOT_01")
        parser.add_argument("--confirmer", action="store_true", help="Effectue réellement la fusion.")

    def handle(self, *args, **options):
        def trouver(code):
            d = Depots.objects.filter(code=code.strip()).first()
            if d is None:
                codes = ", ".join(Depots.objects.values_list("code", flat=True))
                raise CommandError(f"Dépôt « {code} » introuvable. Codes existants : {codes}")
            return d

        source, cible = trouver(options["depot_a_supprimer"]), trouver(options["depot_a_garder"])
        if source.pk == cible.pk:
            raise CommandError("Indiquez deux dépôts différents.")

        entre_eux = TransfertsStock.objects.filter(
            depot_depart__in=[source, cible], depot_arrivee__in=[source, cible]).exclude(statut="BROUILLON")
        if entre_eux.exists():
            raise CommandError(
                f"Refusé : {entre_eux.count()} transfert(s) entre ces deux dépôts. Après fusion, ils iraient d'un dépôt "
                "vers lui-même. Contactez-moi pour les traiter."
            )

        qn = connection.ops.quote_name
        refs = references_aux_depots()
        self.stdout.write(f"« {source.nom} » ({source.code}) sera regroupé dans « {cible.nom} » ({cible.code}) puis supprimé :")
        with connection.cursor() as c:
            for table, colonne in refs:
                c.execute(f"SELECT count(*) FROM {table} WHERE {qn(colonne)} = %s", [source.pk])
                n = c.fetchone()[0]
                if n:
                    self.stdout.write(f"  {table}.{colonne} : {n} ligne(s)")
        utilisateurs = list(User.objects.filter(depot=source).values_list("username", flat=True))
        if utilisateurs:
            self.stdout.write(f"  utilisateurs déplacés : {', '.join(utilisateurs)}")

        if not options["confirmer"]:
            self.stdout.write(self.style.WARNING("Simulation : rien n'a été modifié. Relancez avec --confirmer."))
            return

        try:
            with transaction.atomic():
                with connection.cursor() as c:
                    # Historique des affectations : si une personne a déjà une ligne pour le dépôt gardé,
                    # on garde celle-là (l'affectation active est recalculée juste après).
                    c.execute("""DELETE FROM user_depots s WHERE s.depot_id = %s
                                 AND EXISTS (SELECT 1 FROM user_depots t WHERE t.user_id = s.user_id AND t.depot_id = %s)""",
                              [source.pk, cible.pk])
                    for table, colonne in refs:
                        c.execute(f"UPDATE {table} SET {qn(colonne)} = %s WHERE {qn(colonne)} = %s", [cible.pk, source.pk])
                for u in User.objects.filter(depot=cible):
                    synchroniser_affectation(u)
                nom_source, code_source = source.nom, source.code
                Depots.objects.filter(pk=source.pk).delete()
                Depots.objects.filter(pk=cible.pk).update(actif=True)   # le dépôt gardé doit être actif
                AuditLogs.objects.create(
                    utilisateur=None, action="FUSION_DEPOTS", table_concernee="depots", objet_id=cible.pk,
                    date_action=timezone.now(),
                    ancienne_valeur={"depot_supprime": code_source, "nom": nom_source},
                    nouvelle_valeur={"depot_garde": cible.code, "utilisateurs": utilisateurs},
                )
        except IntegrityError as erreur:
            raise CommandError(f"Échec, aucune modification n'a été enregistrée.\nDétail : {erreur}") from erreur

        self.stdout.write(self.style.SUCCESS(
            f"« {nom_source} » a été regroupé dans « {cible.nom} » et supprimé. « {cible.nom} » est actif."))
