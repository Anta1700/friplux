"""
Ventes de balles entières.

Déroulement :
1. Le vendeur scanne le QR d'un lot, choisit le nombre de balles et le prix par balle
   (prix conseillé proposé, négociable) -> ligne ajoutée à SA vente en cours (statut BROUILLON).
   Une vente peut contenir des balles de plusieurs lots.
2. Il valide : client facultatif, montant payé tout de suite et moyen de paiement.
   -> numéro de vente et numéro de facture attribués, facture créée automatiquement.
   S'il reste un montant à payer : moratoire avec échéances mensuelles (client obligatoire).
3. Les paiements suivants sont imputés sur les échéances, de la plus ancienne à la plus récente.

Stock : on ne vend que les balles présentes dans SON dépôt (voir core/stock.py : réceptions,
transferts et ventes déjà validées). Vérifié à l'ajout, puis à nouveau à la validation sous verrou, pour que deux
vendeurs ne puissent pas vendre la même balle.

Numérotation : FRPLX-VTE-AAAA-NNNNNN et FRPLX-FAC-AAAA-NNNNNN, sans trou (attribués seulement à la
validation, sous verrou PostgreSQL).
"""
import calendar
import re
import uuid
from datetime import date
from decimal import Decimal

from django.db import connection, transaction
from django.db.models import Sum
from django.utils import timezone

from .models import (
    AffectationsPaiements,
    AuditLogs,
    Clients,
    EcheancesMoratoire,
    Factures,
    LignesVente,
    Lots,
    ModePaiement,
    Moratoires,
    Paiements,
    StatutEcheance,
    StatutFacture,
    StatutLogistique,
    StatutMoratoire,
    StatutPaiement,
    StatutVente,
    TypeClient,
    Ventes,
)
from .montants import entier_fcfa
from .stock import balles_dans_depot, message_balles_ailleurs, stock_balles

PREFIXE_VENTE = "FRPLX-VTE"
PREFIXE_FACTURE = "FRPLX-FAC"
CLE_VERROU_VENTES = 20260002
CLE_VERROU_FACTURES = 20260003
CLE_VERROU_CLIENTS = 20260004
MAX_ECHEANCES = 12


class ErreurVente(Exception):
    """Message destiné au vendeur (affiché tel quel)."""


# ------------------------------------------------------------------
# Numérotation
# ------------------------------------------------------------------

def _prochain_numero(modele, champ, prefixe, cle_verrou):
    if not connection.in_atomic_block:
        raise RuntimeError("La numérotation doit se faire dans transaction.atomic().")
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [cle_verrou])
    debut = f"{prefixe}-{timezone.localdate().year}-"
    dernier = (
        modele.objects.filter(**{f"{champ}__regex": rf"^{re.escape(debut)}\d{{6}}$"})
        .order_by(f"-{champ}")
        .values_list(champ, flat=True)
        .first()
    )
    return f"{debut}{(int(dernier[-6:]) + 1 if dernier else 1):06d}"


# ------------------------------------------------------------------
# Stock de balles
# ------------------------------------------------------------------

def balles_vendues(lot):
    total = (
        LignesVente.objects.filter(lot=lot, vente__statut=StatutVente.VALIDEE).aggregate(t=Sum("quantite"))["t"]
    )
    return int(total or 0)


def balles_disponibles(lot, depot_id=None):
    """
    Balles disponibles à la vente (0 pour un lot annulé) :
    dans le dépôt `depot_id` si indiqué, sinon dans tous les dépôts réunis.
    """
    if lot.statut_logistique == StatutLogistique.ANNULE:
        return 0
    if depot_id:
        return balles_dans_depot(lot, depot_id)
    stock, _ = stock_balles(lots=[lot.pk])
    return sum(n for n in stock.values() if n > 0)


def designation_lot(lot):
    morceaux = [str(lot.categorie_lot)]
    if lot.categorie_produit_id:
        morceaux[0] += f" › {lot.categorie_produit.nom}"
    if lot.qualite_id:
        morceaux.append(str(lot.qualite))
    return " · ".join(morceaux)[:200]


def _verifier_vendable(lot, nombre, depot_id):
    if lot.statut_logistique == StatutLogistique.ANNULE:
        raise ErreurVente(f"Le lot {lot.code_lot} est annulé : il ne peut pas être vendu.")
    if not lot.nombre_balles_recues:
        raise ErreurVente(
            f"Le lot {lot.code_lot} n'a pas encore été réceptionné. "
            "Scannez d'abord ses balles avec « Scanner » (réception), puis vendez-les."
        )
    dispo = balles_disponibles(lot, depot_id)
    if nombre > dispo:
        ailleurs = message_balles_ailleurs(lot, depot_id)
        if dispo == 0:
            debut = (f"Aucune balle du lot {lot.code_lot} dans votre dépôt." if ailleurs
                     else f"Plus aucune balle disponible pour le lot {lot.code_lot} : tout est vendu.")
        else:
            debut = (f"Il ne reste que {dispo} balle{'s' if dispo > 1 else ''} disponible{'s' if dispo > 1 else ''} "
                     f"pour le lot {lot.code_lot} dans votre dépôt.")
        raise ErreurVente(f"{debut} {ailleurs}".strip())


# ------------------------------------------------------------------
# Vente en cours (panier)
# ------------------------------------------------------------------

def vente_en_cours(utilisateur):
    return (
        Ventes.objects.filter(vendeur=utilisateur, statut=StatutVente.BROUILLON).order_by("-id").first()
    )


def _vente_en_cours_ou_nouvelle(utilisateur):
    vente = vente_en_cours(utilisateur)
    if vente:
        return vente
    if not utilisateur.depot_id:
        raise ErreurVente(
            "Votre compte n'est rattaché à aucun dépôt : impossible de vendre. "
            "Demandez à l'administrateur de vous rattacher à votre dépôt."
        )
    maintenant = timezone.now()
    return Ventes.objects.create(
        numero_vente=f"BROUILLON-{uuid.uuid4().hex[:12].upper()}",
        depot_id=utilisateur.depot_id,
        vendeur=utilisateur,
        date_vente=maintenant,
        montant_total=0,
        statut=StatutVente.BROUILLON,
    )


def _recalculer_total(vente):
    total = vente.lignes.aggregate(t=Sum("montant_ligne"))["t"] or Decimal("0")
    vente.montant_total = total
    vente.save(update_fields=["montant_total", "updated_at"])
    return total


def _entier_positif(valeur, nom):
    try:
        n = Decimal(re.sub(r"\s", "", str(valeur)).replace(",", "."))
    except Exception:
        raise ErreurVente(f"{nom} : nombre invalide.")
    if n != n.to_integral_value():
        raise ErreurVente(f"{nom} : entrez un nombre entier.")
    if n < 0:
        raise ErreurVente(f"{nom} : le nombre ne peut pas être négatif.")
    return int(n)


@transaction.atomic
def ajouter_au_panier(utilisateur, lot, nombre, prix):
    """
    Met `nombre` balles du lot dans la vente en cours, au prix `prix` par balle.
    Si le lot y est déjà, la ligne est remplacée (nouveau nombre et nouveau prix).
    """
    nombre = _entier_positif(nombre, "Nombre de balles")
    prix = _entier_positif(prix, "Prix par balle")
    if nombre < 1:
        raise ErreurVente("Choisissez au moins 1 balle.")
    if prix <= 0:
        raise ErreurVente("Indiquez le prix par balle.")

    lot = Lots.objects.select_for_update(of=("self",)).select_related(
        "categorie_lot", "categorie_produit", "qualite", "reference_fournisseur"
    ).get(pk=lot.pk)
    if not utilisateur.depot_id:
        raise ErreurVente(
            "Votre compte n'est rattaché à aucun dépôt : impossible de vendre. "
            "Demandez à l'administrateur de vous rattacher à votre dépôt."
        )
    _verifier_vendable(lot, nombre, utilisateur.depot_id)

    vente = _vente_en_cours_ou_nouvelle(utilisateur)
    conseille = lot.prix_conseille
    remise = max(Decimal("0"), (Decimal(conseille) - prix) * nombre) if conseille else Decimal("0")
    valeurs = dict(
        categorie_produit_id=lot.categorie_produit_id,
        designation=designation_lot(lot),
        unite_vente="BALLE",
        quantite=nombre,
        prix_unitaire=prix,
        prix_conseille=conseille,
        remise=remise,
        montant_ligne=Decimal(prix) * nombre,
    )
    ligne = vente.lignes.filter(lot=lot).first()
    if ligne:
        for k, v in valeurs.items():
            setattr(ligne, k, v)
        ligne.save()
    else:
        ligne = LignesVente.objects.create(vente=vente, lot=lot, **valeurs)
    _recalculer_total(vente)
    return ligne


@transaction.atomic
def retirer_ligne(utilisateur, ligne_id):
    vente = vente_en_cours(utilisateur)
    if not vente:
        return
    vente.lignes.filter(pk=ligne_id).delete()
    _recalculer_total(vente)


@transaction.atomic
def abandonner_vente(utilisateur):
    vente = vente_en_cours(utilisateur)
    if vente:
        vente.lignes.all().delete()
        vente.delete()


# ------------------------------------------------------------------
# Clients
# ------------------------------------------------------------------

def normaliser_telephone(telephone):
    """Garde les chiffres (et un + initial) : « 77 123 45 67 » -> « 771234567 »."""
    telephone = (telephone or "").strip()
    plus = telephone.startswith("+")
    chiffres = re.sub(r"\D", "", telephone)
    return ("+" if plus else "") + chiffres


def trouver_ou_creer_client(nom, telephone):
    """Client retrouvé par son téléphone, sinon créé. Rien saisi -> None (client de passage)."""
    nom = " ".join((nom or "").split())
    telephone = normaliser_telephone(telephone)
    if not nom and not telephone:
        return None
    if telephone:
        client = Clients.objects.filter(telephone=telephone).order_by("id").first()
        if client:
            if nom and nom != client.nom:
                client.nom = nom
                client.save(update_fields=["nom", "updated_at"])
            return client
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [CLE_VERROU_CLIENTS])
    client = Clients.objects.create(
        nom=nom or telephone, telephone=telephone or None, type_client=TypeClient.PARTICULIER, actif=True
    )
    client.code_client = f"CLI-{client.pk:06d}"
    client.save(update_fields=["code_client"])
    return client


# ------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------

def ajouter_mois(jour, n):
    mois = jour.month - 1 + n
    annee, mois = jour.year + mois // 12, mois % 12 + 1
    return date(annee, mois, min(jour.day, calendar.monthrange(annee, mois)[1]))


def repartir(montant, nombre):
    """Parts égales en francs entiers ; la dernière absorbe l'arrondi. 100 000 en 3 -> 33 333, 33 333, 33 334."""
    montant = entier_fcfa(montant)
    part = montant // nombre
    return [part] * (nombre - 1) + [montant - part * (nombre - 1)]


def _audit(utilisateur, action, table, objet_id, valeurs):
    AuditLogs.objects.create(
        utilisateur=utilisateur,
        action=action,
        table_concernee=table,
        objet_id=objet_id,
        date_action=timezone.now(),
        nouvelle_valeur=valeurs,
    )


@transaction.atomic
def valider_vente(
    utilisateur,
    *,
    client_nom="",
    client_telephone="",
    montant_paye=None,
    mode_paiement=ModePaiement.ESPECES,
    reference="",
    nombre_echeances=1,
    date_premiere_echeance=None,
):
    vente = Ventes.objects.select_for_update().filter(vendeur=utilisateur, statut=StatutVente.BROUILLON).order_by("-id").first()
    if not vente or not vente.lignes.exists():
        raise ErreurVente("La vente est vide : scannez au moins une balle.")

    lignes = list(vente.lignes.select_related("lot").order_by("lot_id"))
    # Verrou sur les lots vendus (dans un ordre fixe) puis contrôle final du stock.
    lots = {l.pk: l for l in Lots.objects.select_for_update().filter(pk__in=[x.lot_id for x in lignes]).order_by("pk")}
    for ligne in lignes:
        _verifier_vendable(lots[ligne.lot_id], ligne.nombre_balles, vente.depot_id)

    total = entier_fcfa(sum((l.montant_ligne for l in lignes), Decimal("0")))
    paye = total if montant_paye in (None, "") else _entier_positif(montant_paye, "Montant payé")
    if paye > total:
        raise ErreurVente("Le montant payé dépasse le total de la vente.")
    if paye > 0 and mode_paiement not in ModePaiement.values:
        raise ErreurVente("Choisissez le moyen de paiement.")
    reste = total - paye

    if reste > 0:
        if not (client_nom or "").strip() or not normaliser_telephone(client_telephone):
            raise ErreurVente("Paiement en plusieurs fois : le nom et le téléphone du client sont obligatoires.")
        nombre_echeances = _entier_positif(nombre_echeances, "Nombre d'échéances")
        if not 1 <= nombre_echeances <= MAX_ECHEANCES:
            raise ErreurVente(f"Nombre d'échéances : entre 1 et {MAX_ECHEANCES}.")
        if nombre_echeances > reste:
            raise ErreurVente("Trop d'échéances pour le montant restant.")
        aujourd_hui = timezone.localdate()
        date_premiere_echeance = date_premiere_echeance or ajouter_mois(aujourd_hui, 1)
        if date_premiere_echeance < aujourd_hui:
            raise ErreurVente("La première échéance ne peut pas être dans le passé.")

    client = trouver_ou_creer_client(client_nom, client_telephone)
    maintenant = timezone.now()

    vente.numero_vente = _prochain_numero(Ventes, "numero_vente", PREFIXE_VENTE, CLE_VERROU_VENTES)
    vente.client = client
    vente.date_vente = maintenant
    vente.montant_total = total
    vente.statut = StatutVente.VALIDEE
    vente.save()

    facture = Factures.objects.create(
        numero_facture=_prochain_numero(Factures, "numero_facture", PREFIXE_FACTURE, CLE_VERROU_FACTURES),
        vente=vente,
        date_facture=maintenant,
        montant_total=total,
        statut=StatutFacture.PAYEE if reste == 0 else StatutFacture.EMISE,
    )

    if paye > 0:
        Paiements.objects.create(
            vente=vente, montant=paye, date_paiement=maintenant, mode_paiement=mode_paiement,
            reference=(reference or "").strip() or None, utilisateur=utilisateur, statut=StatutPaiement.VALIDE,
        )

    if reste > 0:
        dates = [ajouter_mois(date_premiere_echeance, i) for i in range(nombre_echeances)]
        moratoire = Moratoires.objects.create(
            vente=vente, date_debut=timezone.localdate(), date_echeance=dates[-1], montant_concerne=reste,
            type_moratoire="ECHEANCIER", statut=StatutMoratoire.EN_COURS, autorise_par=utilisateur,
        )
        for i, (jour, montant) in enumerate(zip(dates, repartir(reste, nombre_echeances)), start=1):
            EcheancesMoratoire.objects.create(
                moratoire=moratoire, numero_echeance=i, date_echeance=jour, montant_prevu=montant,
                statut=StatutEcheance.A_PAYER,
            )

    _audit(utilisateur, "VENTE_VALIDEE", "ventes", vente.pk, {
        "numero_vente": vente.numero_vente, "numero_facture": facture.numero_facture, "total": total,
        "paye": paye, "reste": reste, "depot_id": vente.depot_id, "client_id": client.pk if client else None,
        "lignes": [{"lot": l.lot.code_lot, "balles": l.nombre_balles, "prix": entier_fcfa(l.prix_unitaire)} for l in lignes],
    })
    return vente


# ------------------------------------------------------------------
# Paiements
# ------------------------------------------------------------------

def montant_paye(vente):
    return entier_fcfa(
        vente.paiements.filter(statut=StatutPaiement.VALIDE).aggregate(t=Sum("montant"))["t"] or 0
    )


def reste_a_payer(vente):
    if vente.statut != StatutVente.VALIDEE:
        return 0
    return max(0, entier_fcfa(vente.montant_total) - montant_paye(vente))


def deja_affecte(echeance):
    return entier_fcfa(
        echeance.affectations.filter(paiement__statut=StatutPaiement.VALIDE).aggregate(t=Sum("montant_affecte"))["t"] or 0
    )


@transaction.atomic
def encaisser(utilisateur, vente, montant, mode_paiement, reference=""):
    vente = Ventes.objects.select_for_update().get(pk=vente.pk)
    if vente.statut != StatutVente.VALIDEE:
        raise ErreurVente("Cette vente n'est pas validée (ou a été annulée).")
    montant = _entier_positif(montant, "Montant")
    reste = reste_a_payer(vente)
    if reste == 0:
        raise ErreurVente("Cette vente est déjà entièrement payée.")
    if montant <= 0:
        raise ErreurVente("Indiquez le montant reçu.")
    if montant > reste:
        raise ErreurVente(f"Le montant dépasse le reste à payer ({reste:,} FCFA).".replace(",", "\u202f"))
    if mode_paiement not in ModePaiement.values:
        raise ErreurVente("Choisissez le moyen de paiement.")

    paiement = Paiements.objects.create(
        vente=vente, montant=montant, date_paiement=timezone.now(), mode_paiement=mode_paiement,
        reference=(reference or "").strip() or None, utilisateur=utilisateur, statut=StatutPaiement.VALIDE,
    )

    # Imputation sur les échéances, de la plus ancienne à la plus récente.
    a_repartir = montant
    echeances = EcheancesMoratoire.objects.select_for_update().filter(
        moratoire__vente=vente, moratoire__statut=StatutMoratoire.EN_COURS,
        statut__in=[StatutEcheance.A_PAYER, StatutEcheance.PARTIELLE],
    ).order_by("moratoire_id", "numero_echeance")
    for echeance in echeances:
        if a_repartir <= 0:
            break
        du = entier_fcfa(echeance.montant_prevu) - deja_affecte(echeance)
        part = min(du, a_repartir)
        if part <= 0:
            continue
        AffectationsPaiements.objects.create(paiement=paiement, echeance=echeance, montant_affecte=part)
        a_repartir -= part
        echeance.statut = StatutEcheance.PAYEE if part == du else StatutEcheance.PARTIELLE
        echeance.save(update_fields=["statut"])

    solde = reste_a_payer(vente) == 0
    if solde:
        Factures.objects.filter(vente=vente).update(statut=StatutFacture.PAYEE)
        vente.moratoires.filter(statut=StatutMoratoire.EN_COURS).update(statut=StatutMoratoire.SOLDE)

    _audit(utilisateur, "PAIEMENT", "paiements", paiement.pk, {
        "numero_vente": vente.numero_vente, "montant": montant, "mode": mode_paiement, "solde": solde,
    })
    return paiement


# ------------------------------------------------------------------
# Annulation (administration)
# ------------------------------------------------------------------

@transaction.atomic
def annuler_vente(utilisateur, vente, motif=""):
    """
    Annule une vente validée : les balles redeviennent disponibles, la facture est annulée,
    les échéances non réglées aussi. Les paiements sont marqués « Annulé » (argent rendu au client).
    """
    vente = Ventes.objects.select_for_update().get(pk=vente.pk)
    if vente.statut != StatutVente.VALIDEE:
        raise ErreurVente(f"La vente {vente.numero_vente} n'est pas validée.")
    paye = montant_paye(vente)
    vente.statut = StatutVente.ANNULEE
    vente.notes = ((vente.notes or "") + f"\nAnnulée le {timezone.localdate():%d/%m/%Y} : {motif}".rstrip(" :")).strip()
    vente.save(update_fields=["statut", "notes", "updated_at"])
    Factures.objects.filter(vente=vente).update(statut=StatutFacture.ANNULEE)
    vente.moratoires.exclude(statut=StatutMoratoire.ANNULE).update(statut=StatutMoratoire.ANNULE)
    EcheancesMoratoire.objects.filter(moratoire__vente=vente).exclude(statut=StatutEcheance.PAYEE).update(
        statut=StatutEcheance.ANNULEE
    )
    vente.paiements.update(statut=StatutPaiement.ANNULE)
    _audit(utilisateur, "VENTE_ANNULEE", "ventes", vente.pk, {
        "numero_vente": vente.numero_vente, "motif": motif, "montant_rembourse": paye,
    })
    return vente


def echeances_en_retard(vente):
    return [
        e for e in EcheancesMoratoire.objects.filter(
            moratoire__vente=vente, statut__in=[StatutEcheance.A_PAYER, StatutEcheance.PARTIELLE]
        )
        if e.date_echeance < timezone.localdate()
    ]
