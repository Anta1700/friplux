"""
Scan des balles : identification, historique, activation des QR codes, réception et compteurs.

Règles :
- Chaque lecture est enregistrée dans scans_lots (même un code inconnu, pour diagnostic).
- date_activation du QR code = date du PREMIER scan réussi (preuve que l'étiquette est sur la balle).
- Réception par le scan : toutes les balles d'un lot portent le même QR ; chaque scan valide
  compte une balle reçue (le lot passe au statut Reçu dès la première), jusqu'au nombre
  de balles annoncé. Pas de bouton : scanner = recevoir.
- Une relecture immédiate (même personne, même lot, moins de 5 s) n'est pas comptée.
- Début et fin de réception d'un lot sont tracés dans audit_logs.
- Stock par dépôt : la balle reçue entre dans le dépôt de la personne qui scanne (obligatoire).
  Une balle attendue par transfert dans ce dépôt est comptée comme arrivée du transfert.
"""
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from .models import AuditLogs, Lots, QrCodes, ResultatScan, ScansLots, StatutLogistique
from .stock import enregistrer_reception_balle, recevoir_balle_transferee

STATUTS_RECEVABLES = (StatutLogistique.CREE, StatutLogistique.EN_TRANSIT)


def normaliser_code(code):
    return (code or "").strip().upper()


def identifier(code):
    """
    Retrouve la balle à partir du texte lu.
    Accepte le contenu du QR (FRPLX-LOT-2026-000001-V1) ou le code du lot tapé à la main.
    Retourne (lot, qr_code, resultat).
    """
    code = normaliser_code(code)
    if not code:
        return None, None, ResultatScan.INCONNU

    qr = QrCodes.objects.select_related("lot").filter(code=code).first()
    if qr:
        return qr.lot, qr, (ResultatScan.OK if qr.actif else ResultatScan.QR_REMPLACE)

    lot = Lots.objects.filter(code_lot=code).first()
    if lot:
        return lot, lot.qr_codes.filter(actif=True).first(), ResultatScan.OK

    return None, None, ResultatScan.INCONNU


# Deux scans du même lot par la même personne à moins de DELAI_DOUBLON secondes :
# le second est une relecture accidentelle (caméra), il ne compte pas comme une balle de plus.
DELAI_DOUBLON_SECONDES = 5


class EffetScan:
    """Ce que le scan a changé, pour l'afficher à l'utilisateur."""
    BALLE_COMPTEE = "balle_comptee"      # une balle de plus reçue
    LOT_COMPLET = "lot_complet"          # cette balle complète le lot (ex. 9/9)
    DEJA_COMPLET = "deja_complet"        # toutes les balles étaient déjà scannées
    DOUBLON = "doublon"                  # relecture immédiate, non comptée
    NON_RECEVABLE = "non_recevable"      # lot annulé : rien n'est compté
    SANS_DEPOT = "sans_depot"            # la personne n'a pas de dépôt : la balle ne peut pas entrer en stock
    TRANSFERT_BALLE = "transfert_balle"  # balle arrivée par transfert dans le dépôt de la personne
    TRANSFERT_COMPLET = "transfert_complet"  # … et c'était la dernière balle attendue de ce transfert
    AUCUN = "aucun"                      # code inconnu ou ancienne étiquette


@transaction.atomic
def enregistrer_scan(code, utilisateur):
    """
    Enregistre une lecture. Si c'est une balle d'un lot (étiquette valide), elle est comptée
    comme reçue : le lot passe au statut Reçu dès la première balle, et le compteur
    « balles scannées » avance jusqu'au nombre de balles annoncé.

    Retourne (scan, effet) où effet est une valeur de EffetScan.
    """
    lot, qr, resultat = identifier(code)
    maintenant = timezone.now()
    personne = utilisateur if utilisateur and utilisateur.is_authenticated else None

    doublon = False
    if lot and resultat == ResultatScan.OK and personne:
        doublon = ScansLots.objects.filter(
            lot=lot,
            utilisateur=personne,
            resultat=ResultatScan.OK,
            date_scan__gte=maintenant - timezone.timedelta(seconds=DELAI_DOUBLON_SECONDES),
        ).exists()

    scan = ScansLots.objects.create(
        date_scan=maintenant,
        code_scanne=normaliser_code(code)[:100] or "(vide)",
        resultat=resultat,
        lot=lot,
        qr_code=qr,
        categorie_lot_id=lot.categorie_lot_id if lot else None,
        utilisateur=personne,
        depot_id=getattr(utilisateur, "depot_id", None),
    )

    if resultat != ResultatScan.OK or lot is None:
        return scan, EffetScan.AUCUN

    if qr and qr.actif:
        # Filtre sur date_activation vide : seul le tout premier scan la renseigne.
        QrCodes.objects.filter(pk=qr.pk, date_activation__isnull=True).update(date_activation=maintenant)

    if doublon:
        return scan, EffetScan.DOUBLON

    # Balle attendue par transfert dans le dépôt de la personne : elle entre dans son stock.
    mouvement, complet = recevoir_balle_transferee(lot, personne)
    if mouvement:
        scan.transfert = mouvement
        return scan, EffetScan.TRANSFERT_COMPLET if complet else EffetScan.TRANSFERT_BALLE
    return scan, compter_balle_recue(lot, personne)


def compter_balle_recue(lot, utilisateur):
    """Compte une balle reçue pour ce lot (appelé à chaque scan valide)."""
    lot = Lots.objects.select_for_update().get(pk=lot.pk)

    if lot.statut_logistique not in STATUTS_RECEVABLES + (StatutLogistique.RECU,):
        return EffetScan.NON_RECEVABLE

    deja = lot.nombre_balles_recues or 0
    if deja >= lot.nombre_balles:
        return EffetScan.DEJA_COMPLET

    depot_id = getattr(utilisateur, "depot_id", None)
    if not depot_id:
        # Une balle reçue doit être rangée dans un dépôt (stock par dépôt).
        return EffetScan.SANS_DEPOT

    premiere_balle = lot.statut_logistique != StatutLogistique.RECU
    avant = {"statut_logistique": lot.statut_logistique, "nombre_balles_recues": lot.nombre_balles_recues}

    lot.nombre_balles_recues = deja + 1
    champs = ["nombre_balles_recues", "updated_at"]
    if premiere_balle:
        lot.statut_logistique = StatutLogistique.RECU
        lot.date_reception = timezone.localdate()
        champs += ["statut_logistique", "date_reception"]
    lot.save(update_fields=champs)
    enregistrer_reception_balle(lot, utilisateur, depot_id)

    complet = lot.nombre_balles_recues >= lot.nombre_balles
    if premiere_balle or complet:
        # Le détail balle par balle est dans l'historique des scans ;
        # l'audit garde les deux moments clés : début et fin de réception du lot.
        AuditLogs.objects.create(
            utilisateur=utilisateur,
            action="RECEPTION_LOT" if premiere_balle else "RECEPTION_LOT_COMPLETE",
            table_concernee="lots",
            objet_id=lot.pk,
            date_action=timezone.now(),
            ancienne_valeur=avant,
            nouvelle_valeur={
                "statut_logistique": lot.statut_logistique,
                "date_reception": lot.date_reception.isoformat() if lot.date_reception else None,
                "nombre_balles": lot.nombre_balles,
                "nombre_balles_recues": lot.nombre_balles_recues,
                "depot_id": getattr(utilisateur, "depot_id", None),
            },
        )
    return EffetScan.LOT_COMPLET if complet else EffetScan.BALLE_COMPTEE


def derniere_reception(lot):
    """Entrée d'audit de la réception (qui, quand), ou None."""
    return (
        AuditLogs.objects.select_related("utilisateur")
        .filter(table_concernee="lots", objet_id=lot.pk, action="RECEPTION_LOT")
        .order_by("-date_action")
        .first()
    )


def filtrer_scans(date_debut=None, date_fin=None, conteneur=None, depot=None, utilisateur=None):
    scans = ScansLots.objects.all()
    if date_debut:
        scans = scans.filter(date_scan__date__gte=date_debut)
    if date_fin:
        scans = scans.filter(date_scan__date__lte=date_fin)
    if conteneur:
        scans = scans.filter(lot__conteneur=conteneur)
    if depot:
        scans = scans.filter(depot=depot)
    if utilisateur:
        scans = scans.filter(utilisateur=utilisateur)
    return scans


def compteurs_par_categorie(scans):
    """
    Pour chaque catégorie : nombre total de scans, nombre de lots différents scannés,
    et nombre de balles contenues dans ces lots. Les codes inconnus sont comptés à part.
    """
    reconnus = scans.exclude(resultat=ResultatScan.INCONNU)

    # Lots distincts scannés (avec leur catégorie au moment du scan et leur nombre de balles)
    lots_vus = {}
    for categorie, lot_id, nb_balles in reconnus.values_list("categorie_lot__nom", "lot_id", "lot__nombre_balles"):
        lots_vus[(categorie, lot_id)] = nb_balles or 0

    scans_par_categorie = dict(
        reconnus.values("categorie_lot__nom").annotate(n=Count("id")).values_list("categorie_lot__nom", "n")
    )
    lignes = []
    for categorie in sorted(scans_par_categorie, key=lambda c: c or ""):
        lots_cat = [nb for (cat, _), nb in lots_vus.items() if cat == categorie]
        lignes.append({
            "categorie_lot__nom": categorie,
            "scans": scans_par_categorie[categorie],
            "lots": len(lots_cat),
            "balles": sum(lots_cat),
        })

    lots_distincts = {lot_id: nb for (_, lot_id), nb in lots_vus.items()}
    totaux = {
        "scans": sum(scans_par_categorie.values()),
        "lots": len(lots_distincts),
        "balles": sum(lots_distincts.values()),
    }
    inconnus = scans.filter(resultat=ResultatScan.INCONNU).count()
    return lignes, totaux, inconnus
