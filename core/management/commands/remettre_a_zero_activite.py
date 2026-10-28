"""
Efface toute l'activité de test (ventes, factures, paiements, clients, réceptions par scan,
transferts, ouvertures) pour repartir de zéro avec les MÊMES lots et les MÊMES QR codes.

    python manage.py remettre_a_zero_activite              # simulation : affiche ce qui serait effacé
    python manage.py remettre_a_zero_activite --confirmer  # efface vraiment

Effacé :
- ventes, lignes de vente, factures, paiements, moratoires, échéances ;
- clients (sauf avec --garder-clients) ;
- scans, entrées en stock, transferts entre dépôts, ouvertures de balles, stock de pièces.

Remis à l'état « avant l'arrivée » :
- lots reçus -> statut « Créé », balles reçues et date de réception vidées, « Non ouverte » ;
- QR codes : date de premier scan vidée (la date d'envoi au fournisseur est conservée).

Conservé :
- lots, QR codes et étiquettes (mêmes codes FRPLX-LOT-…), prix, conteneurs, fournisseurs,
  références, catégories, qualités, dépôts, utilisateurs et mots de passe, journal d'audit.

Les numéros de vente, de facture et de transfert repartent à 000001.
Tout se fait dans une seule transaction (tout ou rien) et l'opération est inscrite au journal d'audit.
"""
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils import timezone

from core.models import AuditLogs

# Ordre imposé par les clés étrangères : les tables « filles » d'abord.
TABLES_ACTIVITE = [
    ("affectations_paiements", "affectation(s) de paiement"),
    ("echeances_moratoire", "échéance(s)"),
    ("moratoires", "moratoire(s)"),
    ("paiements", "paiement(s)"),
    ("factures", "facture(s)"),
    ("lignes_vente", "ligne(s) de vente"),
    ("ventes", "vente(s)"),
    ("lignes_transfert", "ligne(s) de transfert (ancien format)"),
    ("mouvements_stock", "entrée(s) en stock / mouvement(s)"),
    ("transferts_stock", "transfert(s) entre dépôts"),
    ("scans_lots", "scan(s)"),
    ("lignes_ouverture", "ligne(s) d'ouverture"),
    ("ouvertures_lots", "ouverture(s) de balles"),
    ("stocks", "ligne(s) de stock de pièces"),
]


def _compter(cursor, table):
    cursor.execute(f"SELECT count(*) FROM {table}")
    return cursor.fetchone()[0]


def _existe(cursor, table):
    cursor.execute("SELECT to_regclass(%s) IS NOT NULL", [table])
    return cursor.fetchone()[0]


class Command(BaseCommand):
    help = "Efface l'activité de test (ventes, clients, scans, transferts) en gardant lots, QR codes et réglages."

    def add_arguments(self, parser):
        parser.add_argument("--confirmer", action="store_true", help="Effectue réellement l'effacement.")
        parser.add_argument("--garder-clients", action="store_true", help="Ne supprime pas les fiches clients.")

    def handle(self, *args, **options):
        tables = list(TABLES_ACTIVITE)
        if not options["garder_clients"]:
            tables.insert(tables.index(("ventes", "vente(s)")) + 1, ("clients", "client(s)"))

        with connection.cursor() as c:
            tables = [(t, libelle) for t, libelle in tables if _existe(c, t)]
            comptes = {t: _compter(c, t) for t, _ in tables}
            c.execute("SELECT count(*) FROM lots WHERE statut_logistique = 'RECU' OR statut_ouverture <> 'NON_OUVERT'")
            lots_a_remettre = c.fetchone()[0]
            c.execute("SELECT count(*) FROM qr_codes WHERE date_activation IS NOT NULL")
            qr_a_remettre = c.fetchone()[0]
            c.execute("SELECT count(*) FROM lots")
            nb_lots = c.fetchone()[0]

        self.stdout.write("Activité de test à effacer :")
        for t, libelle in tables:
            if comptes[t]:
                self.stdout.write(f"  {comptes[t]:>6}  {libelle}")
        self.stdout.write(f"  {lots_a_remettre:>6}  lot(s) remis à l'état « avant l'arrivée »")
        self.stdout.write(f"  {qr_a_remettre:>6}  QR code(s) remis à « jamais scanné »")
        self.stdout.write(f"Conservé : {nb_lots} lot(s) avec leurs QR codes, prix, conteneurs, dépôts et utilisateurs.")
        if options["garder_clients"]:
            self.stdout.write("Les fiches clients sont conservées.")

        if not any(comptes.values()) and not lots_a_remettre and not qr_a_remettre:
            self.stdout.write(self.style.SUCCESS("Rien à effacer : le site est déjà propre."))
            return

        if not options["confirmer"]:
            self.stdout.write(self.style.WARNING(
                "\nSimulation : rien n'a été effacé. Relancez avec --confirmer pour effacer vraiment."
            ))
            return

        with transaction.atomic():
            with connection.cursor() as c:
                for t, _ in tables:
                    c.execute(f"DELETE FROM {t}")
                c.execute("""
                    UPDATE lots SET statut_logistique = CASE WHEN statut_logistique = 'RECU' THEN 'CREE' ELSE statut_logistique END,
                                    nombre_balles_recues = NULL, date_reception = NULL,
                                    statut_ouverture = 'NON_OUVERT', date_ouverture = NULL, updated_at = now()
                    WHERE statut_logistique = 'RECU' OR statut_ouverture <> 'NON_OUVERT'
                       OR nombre_balles_recues IS NOT NULL OR date_reception IS NOT NULL
                """)
                c.execute("UPDATE qr_codes SET date_activation = NULL WHERE date_activation IS NOT NULL")
            AuditLogs.objects.create(
                utilisateur=None,
                action="REMISE_A_ZERO_ACTIVITE",
                table_concernee="(toutes)",
                objet_id=None,
                date_action=timezone.now(),
                ancienne_valeur={t: comptes[t] for t, _ in tables} | {"lots_remis": lots_a_remettre, "qr_remis": qr_a_remettre},
                nouvelle_valeur={"lots_conserves": nb_lots},
            )

        self.stdout.write(self.style.SUCCESS(
            "\nC'est fait : l'activité de test est effacée. Les balles peuvent être scannées à nouveau à leur arrivée."
        ))
