"""
Supprime les lots d'un conteneur (avec leurs QR codes et leurs scans) pour pouvoir
réimporter sa fiche proprement.

    python manage.py reinitialiser_conteneur "TIIU418469 9"              # simulation : n'efface rien
    python manage.py reinitialiser_conteneur "TIIU418469 9" --confirmer  # efface vraiment

Sécurités :
- refuse si un lot du conteneur a déjà été ouvert ou a un mouvement de stock ;
- tout se fait dans une seule transaction (tout ou rien) ;
- le conteneur, le fournisseur et le catalogue des références sont conservés ;
- l'opération est inscrite dans le journal d'audit.

À n'utiliser que si les étiquettes n'ont PAS encore été envoyées au fournisseur :
après réimport, les codes FRPLX-LOT-… sont réattribués.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import AuditLogs, Conteneurs, Lots, MouvementsStock, OuverturesLots, QrCodes, ScansLots


class Command(BaseCommand):
    help = "Supprime les lots d'un conteneur (et leurs QR codes / scans) pour réimporter sa fiche."

    def add_arguments(self, parser):
        parser.add_argument("numero_conteneur", help='Numéro du conteneur, ex. "TIIU418469 9"')
        parser.add_argument("--confirmer", action="store_true", help="Effectue réellement la suppression.")

    def handle(self, *args, **options):
        numero = options["numero_conteneur"].strip()
        conteneur = Conteneurs.objects.filter(numero_conteneur=numero).first()
        if conteneur is None:
            proches = list(Conteneurs.objects.values_list("numero_conteneur", flat=True)[:20])
            raise CommandError(f"Conteneur « {numero} » introuvable. Conteneurs existants : {', '.join(proches)}")

        lots = Lots.objects.filter(conteneur=conteneur)
        nb_lots = lots.count()
        nb_qr = QrCodes.objects.filter(lot__in=lots).count()
        nb_scans = ScansLots.objects.filter(lot__in=lots).count()
        nb_recus = lots.filter(statut_logistique="RECU").count()
        nb_ouvertures = OuverturesLots.objects.filter(lot__in=lots).count()
        nb_mouvements = MouvementsStock.objects.filter(lot__in=lots).count()
        nb_ouverts = lots.filter(statut_ouverture="OUVERT").count()

        self.stdout.write(f"Conteneur {conteneur.numero_conteneur} ({conteneur.fournisseur}) :")
        self.stdout.write(f"  {nb_lots} lot(s), {nb_qr} QR code(s), {nb_scans} scan(s), {nb_recus} lot(s) marqué(s) reçu(s)")

        if nb_ouvertures or nb_mouvements or nb_ouverts:
            raise CommandError(
                f"Refusé : {nb_ouverts} lot(s) ouvert(s), {nb_ouvertures} ouverture(s) et "
                f"{nb_mouvements} mouvement(s) de stock enregistrés. Ces lots ont déjà servi."
            )
        if nb_lots == 0:
            self.stdout.write(self.style.SUCCESS("Rien à supprimer."))
            return

        if not options["confirmer"]:
            self.stdout.write(self.style.WARNING(
                "Simulation : rien n'a été supprimé. Relancez avec --confirmer pour effectuer la suppression."
            ))
            return

        with transaction.atomic():
            codes = list(lots.order_by("code_lot").values_list("code_lot", flat=True))
            ScansLots.objects.filter(lot__in=lots).delete()
            QrCodes.objects.filter(lot__in=lots).delete()
            lots.delete()
            AuditLogs.objects.create(
                utilisateur=None,
                action="REINITIALISATION_CONTENEUR",
                table_concernee="conteneurs",
                objet_id=conteneur.pk,
                date_action=timezone.now(),
                ancienne_valeur={
                    "lots": nb_lots, "qr_codes": nb_qr, "scans": nb_scans,
                    "premier_code": codes[0], "dernier_code": codes[-1],
                },
                nouvelle_valeur={"lots": 0},
            )

        self.stdout.write(self.style.SUCCESS(
            f"Supprimé : {nb_lots} lot(s), {nb_qr} QR code(s), {nb_scans} scan(s). "
            "Vous pouvez réimporter la fiche du conteneur."
        ))
