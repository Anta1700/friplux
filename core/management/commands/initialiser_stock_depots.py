"""
Range dans un dépôt les balles reçues AVANT la mise en place du stock par dépôt.

    python manage.py initialiser_stock_depots --depot DEPOT-PRINCIPAL             (simulation)
    python manage.py initialiser_stock_depots --depot DEPOT-PRINCIPAL --confirmer

Pour chaque lot reçu dont des balles ne sont encore dans aucun dépôt :
- dépôt où ont été faits la plupart de ses scans de réception, s'il est connu ;
- sinon le dépôt indiqué par --depot.
Peut être relancé sans risque : les balles déjà rangées ne sont pas comptées deux fois.
"""
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.models import AuditLogs, Depots, Lots, MouvementsStock, ResultatScan, ScansLots, TypeMouvement, User


class Command(BaseCommand):
    help = "Range dans un dépôt les balles reçues avant le stock par dépôt."

    def add_arguments(self, parser):
        parser.add_argument("--depot", help="Code du dépôt à utiliser quand le dépôt des scans est inconnu.")
        parser.add_argument("--confirmer", action="store_true", help="Enregistre réellement.")

    def handle(self, *args, **options):
        defaut = None
        if options["depot"]:
            defaut = Depots.objects.filter(code=options["depot"].strip().upper()).first()
            if defaut is None:
                codes = ", ".join(Depots.objects.values_list("code", flat=True))
                raise CommandError(f"Dépôt « {options['depot']} » introuvable. Dépôts : {codes}")

        auteur = User.objects.filter(is_superuser=True, is_active=True).order_by("id").first()
        if auteur is None:
            raise CommandError("Aucun super-administrateur actif : créez-en un d'abord.")

        a_faire, sans_depot = [], []
        for lot in Lots.objects.filter(nombre_balles_recues__gt=0).order_by("code_lot"):
            rangees = MouvementsStock.objects.filter(lot=lot, type_mouvement=TypeMouvement.RECEPTION_BALLE).aggregate(
                n=Sum("balles"))["n"] or 0
            manquantes = lot.nombre_balles_recues - rangees
            if manquantes <= 0:
                continue
            depots_scans = Counter(ScansLots.objects.filter(lot=lot, resultat=ResultatScan.OK, depot__isnull=False)
                                   .values_list("depot_id", flat=True))
            depot_id = depots_scans.most_common(1)[0][0] if depots_scans else (defaut.pk if defaut else None)
            (a_faire if depot_id else sans_depot).append((lot, manquantes, depot_id))

        noms = dict(Depots.objects.values_list("id", "nom"))
        for lot, n, depot_id in a_faire:
            self.stdout.write(f"  {lot.code_lot} : {n} balle(s) → {noms[depot_id]}")
        for lot, n, _ in sans_depot:
            self.stdout.write(self.style.WARNING(f"  {lot.code_lot} : {n} balle(s) sans dépôt connu (indiquez --depot)"))
        if not a_faire:
            self.stdout.write(self.style.SUCCESS("Rien à ranger : toutes les balles reçues sont déjà dans un dépôt."))
            return
        if not options["confirmer"]:
            self.stdout.write(self.style.WARNING(
                f"Simulation : {len(a_faire)} lot(s) à ranger, rien n'a été enregistré. Relancez avec --confirmer."))
            return

        with transaction.atomic():
            maintenant = timezone.now()
            for lot, n, depot_id in a_faire:
                MouvementsStock.objects.create(
                    type_mouvement=TypeMouvement.RECEPTION_BALLE, depot_arrivee_id=depot_id, lot=lot,
                    categorie_produit_id=lot.categorie_produit_id, balles=n, quantite_pieces=0,
                    poids_kg=(lot.poids_moyen_balle or 0) * n, utilisateur=auteur, date_mouvement=maintenant,
                    statut="VALIDE", commentaire="Initialisation du stock par dépôt",
                )
            AuditLogs.objects.create(
                utilisateur=auteur, action="INITIALISATION_STOCK_DEPOTS", table_concernee="mouvements_stock",
                date_action=maintenant, nouvelle_valeur={"lots": len(a_faire), "balles": sum(n for _, n, _ in a_faire)},
            )
        self.stdout.write(self.style.SUCCESS(f"{len(a_faire)} lot(s) rangé(s) dans leur dépôt."))
