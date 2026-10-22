"""
Stock de balles par dépôt et transferts entre dépôts.

Les balles d'un même lot (même QR) peuvent être réparties entre plusieurs dépôts.
Balles d'un lot dans un dépôt =
    + balles scannées à la réception dans ce dépôt          (mouvements RECEPTION_BALLE)
    + balles arrivées par transfert dans ce dépôt           (TRANSFERT_BALLES, balles_recues)
    - balles envoyées par transfert depuis ce dépôt          (TRANSFERT_BALLES, balles, dès l'envoi)
    - balles vendues par ce dépôt                            (lignes des ventes validées)

Transfert : le dépôt de départ prépare l'envoi (scan des lots, nombre de balles) puis l'envoie ;
les balles quittent son stock et sont « en route ». À l'arrivée, chaque balle scannée (écran Scanner
habituel) entre dans le stock du dépôt d'arrivée. S'il manque des balles, le transfert peut être
clôturé : les balles manquantes sont signalées et ne comptent plus dans aucun dépôt.
"""
import re
import uuid
from collections import defaultdict
from decimal import Decimal

from django.db import connection, transaction
from django.db.models import F, Sum
from django.utils import timezone

from .models import (
    AuditLogs, Depots, LignesVente, Lots, MouvementsStock, StatutLogistique, StatutTransfert, StatutVente,
    TransfertsStock, TypeMouvement,
)

PREFIXE_TRANSFERT = "FRPLX-TRF"
CLE_VERROU_TRANSFERTS = 20260005
STATUTS_TRANSFERT_ACTIFS = (StatutTransfert.EN_COURS, StatutTransfert.RECU, StatutTransfert.RECU_AVEC_ECART)


class ErreurStock(Exception):
    """Message destiné à l'utilisateur (affiché tel quel)."""


def _audit(utilisateur, action, table, objet_id, valeurs):
    AuditLogs.objects.create(utilisateur=utilisateur, action=action, table_concernee=table, objet_id=objet_id,
                             date_action=timezone.now(), nouvelle_valeur=valeurs)


# ------------------------------------------------------------------
# Calcul du stock
# ------------------------------------------------------------------

def stock_balles(lots=None, depot=None):
    """
    Balles disponibles par (lot, dépôt) : {(lot_id, depot_id): balles}, plus {lot_id: balles en route}.
    `lots` : queryset/liste d'id pour limiter le calcul ; `depot` : limiter à un dépôt.
    """
    stock = defaultdict(int)
    en_route = defaultdict(int)

    receptions = MouvementsStock.objects.filter(type_mouvement=TypeMouvement.RECEPTION_BALLE, statut="VALIDE")
    transferts = MouvementsStock.objects.filter(type_mouvement=TypeMouvement.TRANSFERT_BALLES,
                                                transfert__statut__in=STATUTS_TRANSFERT_ACTIFS)
    ventes = LignesVente.objects.filter(vente__statut=StatutVente.VALIDEE, lot__isnull=False)
    if lots is not None:
        receptions, transferts, ventes = (q.filter(lot__in=lots) for q in (receptions, transferts, ventes))

    for lot_id, depot_id, n in receptions.values_list("lot_id", "depot_arrivee_id").annotate(n=Sum("balles")):
        stock[(lot_id, depot_id)] += n or 0
    for lot_id, depart, arrivee, envoyees, arrivees, statut_t in transferts.values_list(
        "lot_id", "depot_depart_id", "depot_arrivee_id", "balles", "balles_recues", "transfert__statut"
    ):
        stock[(lot_id, depart)] -= envoyees or 0
        stock[(lot_id, arrivee)] += arrivees or 0
        if statut_t == StatutTransfert.EN_COURS:
            en_route[lot_id] += (envoyees or 0) - (arrivees or 0)
    for lot_id, depot_id, n in ventes.values_list("lot_id", "vente__depot_id").annotate(n=Sum("quantite")):
        stock[(lot_id, depot_id)] -= int(n or 0)

    if depot is not None:
        depot_id = getattr(depot, "pk", depot)
        stock = {k: v for k, v in stock.items() if k[1] == depot_id}
    return dict(stock), dict(en_route)


def repartition(lot):
    """Où sont les balles d'un lot : [(dépôt, balles), …] (dépôts avec au moins une balle), balles en route."""
    stock, en_route = stock_balles(lots=[lot.pk])
    noms = dict(Depots.objects.values_list("id", "nom"))
    lignes = sorted(((noms.get(d, "Sans dépôt"), n) for (l, d), n in stock.items() if n > 0), key=lambda x: (-x[1], x[0]))
    return lignes, en_route.get(lot.pk, 0)


def balles_dans_depot(lot, depot_id):
    if lot.statut_logistique == StatutLogistique.ANNULE or not depot_id:
        return 0
    stock, _ = stock_balles(lots=[lot.pk])
    return max(0, stock.get((lot.pk, depot_id), 0))


def message_balles_ailleurs(lot, depot_id):
    """Phrase pour expliquer où se trouvent les balles quand le dépôt n'en a plus."""
    stock, en_route = stock_balles(lots=[lot.pk])
    noms = dict(Depots.objects.values_list("id", "nom"))
    ailleurs = [f"{noms.get(d, 'sans dépôt')} : {n} balle{'s' if n > 1 else ''}"
                for (l, d), n in sorted(stock.items(), key=lambda i: -i[1]) if n > 0 and d != depot_id]
    morceaux = []
    if ailleurs:
        morceaux.append("Ailleurs : " + ", ".join(ailleurs) + ". Demandez un transfert.")
    n = en_route.get(lot.pk, 0)
    if n:
        morceaux.append(f"{n} balle{'s' if n > 1 else ''} en route (transfert).")
    return " ".join(morceaux)


def stock_du_depot(depot):
    """
    Pour la page Stock : lignes [{lot, balles}] du dépôt (balles > 0), triées par catégorie,
    et résumé par catégorie × qualité.
    """
    stock, _ = stock_balles(depot=depot)
    par_lot = {lot_id: n for (lot_id, d), n in stock.items() if n > 0}
    lots = (Lots.objects.filter(pk__in=par_lot).exclude(statut_logistique=StatutLogistique.ANNULE)
            .select_related("categorie_lot", "categorie_produit", "qualite").order_by("categorie_lot__nom", "code_lot"))
    lignes = [{"lot": l, "balles": par_lot[l.pk]} for l in lots]
    resume = defaultdict(int)
    for x in lignes:
        resume[(str(x["lot"].categorie_lot), str(x["lot"].qualite) if x["lot"].qualite_id else "Sans qualité")] += x["balles"]
    resume = [{"categorie": c, "qualite": q, "balles": n} for (c, q), n in sorted(resume.items(), key=lambda i: (-i[1], i[0]))]
    return lignes, resume, sum(x["balles"] for x in lignes)


# ------------------------------------------------------------------
# Réception initiale (appelée par le scan)
# ------------------------------------------------------------------

def enregistrer_reception_balle(lot, utilisateur, depot_id):
    MouvementsStock.objects.create(
        type_mouvement=TypeMouvement.RECEPTION_BALLE, depot_arrivee_id=depot_id, lot=lot,
        categorie_produit_id=lot.categorie_produit_id, balles=1, quantite_pieces=0,
        poids_kg=lot.poids_moyen_balle or 0, utilisateur=utilisateur, date_mouvement=timezone.now(), statut="VALIDE",
    )


# ------------------------------------------------------------------
# Transferts : préparation et envoi
# ------------------------------------------------------------------

def transfert_en_preparation(utilisateur):
    return (TransfertsStock.objects.select_related("depot_arrivee", "depot_depart")
            .filter(utilisateur=utilisateur, statut=StatutTransfert.BROUILLON).order_by("-id").first())


@transaction.atomic
def preparer_transfert(utilisateur, depot_arrivee):
    """Commence (ou réoriente) l'envoi en préparation vers `depot_arrivee`."""
    if not utilisateur.depot_id:
        raise ErreurStock("Votre compte n'est rattaché à aucun dépôt : impossible d'envoyer des balles.")
    if depot_arrivee.pk == utilisateur.depot_id:
        raise ErreurStock("Choisissez un autre dépôt que le vôtre.")
    t = transfert_en_preparation(utilisateur)
    if t:
        t.depot_arrivee = depot_arrivee
        t.save(update_fields=["depot_arrivee"])
        t.mouvements.update(depot_arrivee=depot_arrivee)
        return t
    return TransfertsStock.objects.create(
        reference_transfert=f"BROUILLON-{uuid.uuid4().hex[:12].upper()}", depot_depart_id=utilisateur.depot_id,
        depot_arrivee=depot_arrivee, utilisateur=utilisateur, date_transfert=timezone.now(),
        statut=StatutTransfert.BROUILLON,
    )


def _verifier_disponible(lot, depot_id, nombre):
    if lot.statut_logistique == StatutLogistique.ANNULE:
        raise ErreurStock(f"Le lot {lot.code_lot} est annulé.")
    dispo = balles_dans_depot(lot, depot_id)
    if nombre > dispo:
        debut = (f"Il ne reste que {dispo} balle{'s' if dispo > 1 else ''} de ce lot dans votre dépôt."
                 if dispo else f"Aucune balle du lot {lot.code_lot} dans votre dépôt.")
        raise ErreurStock(f"{debut} {message_balles_ailleurs(lot, depot_id)}".strip())


@transaction.atomic
def ajouter_au_transfert(utilisateur, lot, nombre):
    try:
        nombre = int(str(nombre).strip())
    except ValueError:
        raise ErreurStock("Nombre de balles invalide.")
    if nombre < 1:
        raise ErreurStock("Choisissez au moins 1 balle.")
    t = transfert_en_preparation(utilisateur)
    if not t:
        raise ErreurStock("Choisissez d'abord le dépôt de destination.")
    lot = Lots.objects.select_for_update(of=("self",)).get(pk=lot.pk)
    _verifier_disponible(lot, t.depot_depart_id, nombre)
    valeurs = dict(depot_depart_id=t.depot_depart_id, depot_arrivee_id=t.depot_arrivee_id, balles=nombre, balles_recues=0,
                   poids_kg=(lot.poids_moyen_balle or Decimal("0")) * nombre, categorie_produit_id=lot.categorie_produit_id)
    m = t.mouvements.filter(lot=lot).first()
    if m:
        for k, v in valeurs.items():
            setattr(m, k, v)
        m.save()
    else:
        m = MouvementsStock.objects.create(
            type_mouvement=TypeMouvement.TRANSFERT_BALLES, lot=lot, transfert=t, quantite_pieces=0, utilisateur=utilisateur,
            date_mouvement=timezone.now(), statut="EN_TRANSIT", **valeurs,
        )
    return m


@transaction.atomic
def retirer_du_transfert(utilisateur, mouvement_id):
    t = transfert_en_preparation(utilisateur)
    if t:
        t.mouvements.filter(pk=mouvement_id).delete()


@transaction.atomic
def abandonner_transfert(utilisateur):
    t = transfert_en_preparation(utilisateur)
    if t:
        t.mouvements.all().delete()
        t.delete()


def _prochaine_reference():
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [CLE_VERROU_TRANSFERTS])
    debut = f"{PREFIXE_TRANSFERT}-{timezone.localdate().year}-"
    dernier = (TransfertsStock.objects.filter(reference_transfert__regex=rf"^{re.escape(debut)}\d{{6}}$")
               .order_by("-reference_transfert").values_list("reference_transfert", flat=True).first())
    return f"{debut}{(int(dernier[-6:]) + 1 if dernier else 1):06d}"


@transaction.atomic
def envoyer_transfert(utilisateur):
    t = TransfertsStock.objects.select_for_update().filter(
        utilisateur=utilisateur, statut=StatutTransfert.BROUILLON).order_by("-id").first()
    if not t or not t.mouvements.exists():
        raise ErreurStock("L'envoi est vide : scannez au moins une balle.")
    mouvements = list(t.mouvements.select_related("lot").order_by("lot_id"))
    # Même verrou que les ventes : une balle ne peut pas être vendue et envoyée en même temps.
    lots = {l.pk: l for l in Lots.objects.select_for_update().filter(pk__in=[m.lot_id for m in mouvements]).order_by("pk")}
    for m in mouvements:
        _verifier_disponible(lots[m.lot_id], t.depot_depart_id, m.balles)
    t.reference_transfert = _prochaine_reference()
    t.statut = StatutTransfert.EN_COURS
    t.date_transfert = timezone.now()
    t.save(update_fields=["reference_transfert", "statut", "date_transfert"])
    t.mouvements.update(reference_document=t.reference_transfert, date_mouvement=t.date_transfert)
    _audit(utilisateur, "TRANSFERT_ENVOYE", "transferts_stock", t.pk, {
        "reference": t.reference_transfert, "de": t.depot_depart_id, "vers": t.depot_arrivee_id,
        "lots": [{"lot": m.lot.code_lot, "balles": m.balles} for m in mouvements],
    })
    return t


# ------------------------------------------------------------------
# Transferts : arrivée
# ------------------------------------------------------------------

def recevoir_balle_transferee(lot, utilisateur):
    """
    Appelée par le scan : si une balle de ce lot est attendue par transfert dans le dépôt de la personne,
    elle entre dans son stock. Retourne (mouvement, transfert_complet) ou (None, False).
    """
    if not getattr(utilisateur, "depot_id", None):
        return None, False
    m = (MouvementsStock.objects.select_for_update()
         .filter(type_mouvement=TypeMouvement.TRANSFERT_BALLES, lot=lot, depot_arrivee_id=utilisateur.depot_id,
                 transfert__statut=StatutTransfert.EN_COURS, balles_recues__lt=F("balles"))
         .select_related("transfert").order_by("transfert__date_transfert", "id").first())
    if m is None:
        return None, False
    m.balles_recues = (m.balles_recues or 0) + 1
    if m.balles_recues >= m.balles:
        m.statut = "RECU"
    m.save(update_fields=["balles_recues", "statut"])
    t = m.transfert
    complet = not t.mouvements.filter(balles_recues__lt=F("balles")).exists()
    if complet:
        t.statut = StatutTransfert.RECU
        t.save(update_fields=["statut"])
        _audit(utilisateur, "TRANSFERT_RECU", "transferts_stock", t.pk, {"reference": t.reference_transfert})
    return m, complet


@transaction.atomic
def cloturer_avec_ecart(utilisateur, transfert):
    """Le dépôt d'arrivée déclare que des balles manquent : le transfert est clos, l'écart est tracé."""
    t = TransfertsStock.objects.select_for_update().get(pk=transfert.pk)
    if t.statut != StatutTransfert.EN_COURS:
        raise ErreurStock("Ce transfert n'est plus en route.")
    if not utilisateur.is_staff and utilisateur.depot_id != t.depot_arrivee_id:
        raise ErreurStock("Seul le dépôt d'arrivée peut clôturer ce transfert.")
    manquantes = [{"lot": m.lot.code_lot, "manquantes": m.balles_manquantes}
                  for m in t.mouvements.select_related("lot") if m.balles_manquantes > 0]
    t.statut = StatutTransfert.RECU_AVEC_ECART if manquantes else StatutTransfert.RECU
    t.save(update_fields=["statut"])
    t.mouvements.update(statut="RECU")
    _audit(utilisateur, "TRANSFERT_CLOTURE_ECART", "transferts_stock", t.pk,
           {"reference": t.reference_transfert, "balles_manquantes": manquantes})
    return t


@transaction.atomic
def annuler_transfert(utilisateur, transfert):
    """Le dépôt de départ annule un envoi dont aucune balle n'est encore arrivée : les balles reviennent chez lui."""
    t = TransfertsStock.objects.select_for_update().get(pk=transfert.pk)
    if t.statut != StatutTransfert.EN_COURS:
        raise ErreurStock("Ce transfert n'est plus en route.")
    if not utilisateur.is_staff and utilisateur.depot_id != t.depot_depart_id:
        raise ErreurStock("Seul le dépôt de départ peut annuler cet envoi.")
    if t.mouvements.filter(balles_recues__gt=0).exists():
        raise ErreurStock("Des balles sont déjà arrivées : l'envoi ne peut plus être annulé. "
                          "Le dépôt d'arrivée peut le clôturer en signalant les balles manquantes.")
    t.statut = StatutTransfert.ANNULE
    t.save(update_fields=["statut"])
    t.mouvements.update(statut="ANNULE")
    _audit(utilisateur, "TRANSFERT_ANNULE", "transferts_stock", t.pk, {"reference": t.reference_transfert})
    return t


def transferts_a_recevoir(depot_id):
    return (TransfertsStock.objects.filter(depot_arrivee_id=depot_id, statut=StatutTransfert.EN_COURS)
            .select_related("depot_depart", "utilisateur").order_by("date_transfert"))


def transferts_envoyes_en_route(depot_id):
    return (TransfertsStock.objects.filter(depot_depart_id=depot_id, statut=StatutTransfert.EN_COURS)
            .select_related("depot_arrivee").order_by("date_transfert"))


def progression(transfert):
    agr = transfert.mouvements.aggregate(b=Sum("balles"), r=Sum("balles_recues"))
    return int(agr["r"] or 0), int(agr["b"] or 0)
