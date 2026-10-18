"""
Scan des balles : identification, historique, activation des QR codes, réception et compteurs.

Règles :
- Chaque lecture est enregistrée dans scans_lots (même un code inconnu, pour diagnostic).
- date_activation du QR code = date du PREMIER scan réussi (preuve que l'étiquette est sur la balle).
- « Marquer comme reçue » : statut RECU + date de réception, tracé dans audit_logs.
- Compteurs calculés depuis l'historique : total des scans ≠ nombre de balles uniques
  (rescanner une balle n'en fait pas une nouvelle balle reçue).
"""
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from .models import AuditLogs, Lots, QrCodes, ResultatScan, ScansLots, StatutLogistique

STATUTS_RECEVABLES = (StatutLogistique.CREE, StatutLogistique.EN_TRANSIT)


class ErreurReception(Exception):
    pass


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


@transaction.atomic
def enregistrer_scan(code, utilisateur):
    """Enregistre une lecture et active le QR code au premier scan réussi."""
    lot, qr, resultat = identifier(code)
    scan = ScansLots.objects.create(
        date_scan=timezone.now(),
        code_scanne=normaliser_code(code)[:100] or "(vide)",
        resultat=resultat,
        lot=lot,
        qr_code=qr,
        categorie_lot_id=lot.categorie_lot_id if lot else None,
        utilisateur=utilisateur if utilisateur and utilisateur.is_authenticated else None,
        depot_id=getattr(utilisateur, "depot_id", None),
    )
    if resultat == ResultatScan.OK and qr and qr.actif:
        # Filtre sur date_activation vide : seul le tout premier scan la renseigne.
        QrCodes.objects.filter(pk=qr.pk, date_activation__isnull=True).update(date_activation=scan.date_scan)
    return scan


@transaction.atomic
def marquer_recu(lot, utilisateur, adresse_ip=None):
    """Passe la balle au statut Reçu avec la date du jour, et trace l'opération."""
    lot = Lots.objects.select_for_update().get(pk=lot.pk)

    if lot.statut_logistique == StatutLogistique.RECU:
        raise ErreurReception(f"Cette balle est déjà reçue (le {lot.date_reception:%d/%m/%Y}).")
    if lot.statut_logistique not in STATUTS_RECEVABLES:
        raise ErreurReception(f"Impossible : la balle est au statut « {lot.get_statut_logistique_display()} ».")

    aujourd_hui = timezone.localdate()
    if lot.date_creation and aujourd_hui < lot.date_creation:
        raise ErreurReception("La date de réception ne peut pas précéder la date de création de la balle.")

    avant = {"statut_logistique": lot.statut_logistique, "date_reception": None}
    lot.statut_logistique = StatutLogistique.RECU
    lot.date_reception = aujourd_hui
    lot.save(update_fields=["statut_logistique", "date_reception", "updated_at"])

    AuditLogs.objects.create(
        utilisateur=utilisateur,
        action="RECEPTION_LOT",
        table_concernee="lots",
        objet_id=lot.pk,
        date_action=timezone.now(),
        ancienne_valeur=avant,
        nouvelle_valeur={
            "statut_logistique": lot.statut_logistique,
            "date_reception": aujourd_hui.isoformat(),
            "depot_id": getattr(utilisateur, "depot_id", None),
        },
        adresse_ip=adresse_ip,
    )
    return lot


def derniere_reception(lot):
    """Entrée d'audit de la réception (qui, quand), ou None."""
    return (
        AuditLogs.objects.select_related("utilisateur")
        .filter(table_concernee="lots", objet_id=lot.pk, action="RECEPTION_LOT")
        .order_by("-date_action")
        .first()
    )


def resume_scans_lot(lot):
    """Nombre de scans d'une balle, premier et dernier scan."""
    scans = ScansLots.objects.filter(lot=lot).exclude(resultat=ResultatScan.INCONNU)
    return {
        "nombre": scans.count(),
        "premier": scans.order_by("date_scan").first(),
        "dernier": scans.order_by("-date_scan").first(),
    }


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
    Pour chaque catégorie : nombre total de scans et nombre de balles uniques.
    Les codes inconnus sont comptés à part.
    """
    reconnus = scans.exclude(resultat=ResultatScan.INCONNU)
    lignes = list(
        reconnus.values("categorie_lot__nom")
        .annotate(scans=Count("id"), balles=Count("lot", distinct=True))
        .order_by("categorie_lot__nom")
    )
    totaux = reconnus.aggregate(scans=Count("id"), balles=Count("lot", distinct=True))
    inconnus = scans.filter(resultat=ResultatScan.INCONNU).count()
    return lignes, totaux, inconnus
