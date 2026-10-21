"""
Statistiques des ventes : par dépôt, par vendeur, par moyen de paiement, par catégorie et qualité,
et échéances en retard.

Définitions (affichées aussi sur la page) :
- Vendu      : total des ventes validées sur la période (payées ou non).
- Encaissé   : argent reçu sur la période (y compris les échéances de ventes plus anciennes).
- Reste      : ce qui reste à payer sur les ventes de la période, à ce jour.
- Rabais     : écart sous le prix conseillé, accordé en négociation (administration seulement).
"""
from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, DecimalField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import EcheancesMoratoire, LignesVente, ModePaiement, Paiements, StatutPaiement, StatutVente
from .montants import entier_fcfa

ZERO = Value(Decimal("0"), output_field=DecimalField(max_digits=15, decimal_places=2))


def _paye_par_vente():
    """Sous-requête : total payé (paiements valides, toutes dates) pour chaque vente."""
    return Coalesce(
        Subquery(
            Paiements.objects.filter(vente=OuterRef("pk"), statut=StatutPaiement.VALIDE)
            .values("vente").annotate(t=Sum("montant")).values("t")[:1],
            output_field=DecimalField(max_digits=15, decimal_places=2),
        ),
        ZERO,
    )


def _ligne_vide(nom):
    return {"nom": nom, "ventes": 0, "balles": 0, "vendu": 0, "encaisse": 0, "reste": 0, "rabais": 0}


def statistiques_ventes(ventes_visibles, date_debut=None, date_fin=None, depot=None, vendeur=None):
    """
    `ventes_visibles` : ventes que la personne a le droit de voir (déjà limitées à son dépôt si besoin).
    Retourne un dictionnaire prêt pour la page.
    """
    ventes = ventes_visibles.filter(statut=StatutVente.VALIDEE)
    paiements = Paiements.objects.filter(statut=StatutPaiement.VALIDE, vente__in=ventes_visibles,
                                         vente__statut=StatutVente.VALIDEE)
    if date_debut:
        ventes = ventes.filter(date_vente__date__gte=date_debut)
        paiements = paiements.filter(date_paiement__date__gte=date_debut)
    if date_fin:
        ventes = ventes.filter(date_vente__date__lte=date_fin)
        paiements = paiements.filter(date_paiement__date__lte=date_fin)
    if depot:
        ventes = ventes.filter(depot=depot)
        paiements = paiements.filter(vente__depot=depot)
    if vendeur:
        ventes = ventes.filter(vendeur=vendeur)
        paiements = paiements.filter(utilisateur=vendeur)   # encaissé PAR cette personne

    lignes = LignesVente.objects.filter(vente__in=ventes)

    # --- Par dépôt et par vendeur -------------------------------------------------
    par_depot, par_vendeur = {}, {}
    for v in ventes.select_related("depot", "vendeur").annotate(paye=_paye_par_vente()):
        for table, cle, nom in ((par_depot, v.depot_id, v.depot.nom),
                                (par_vendeur, v.vendeur_id, v.vendeur.get_full_name())):
            ligne = table.setdefault(cle, _ligne_vide(nom))
            ligne["ventes"] += 1
            ligne["vendu"] += entier_fcfa(v.montant_total)
            ligne["reste"] += max(0, entier_fcfa(v.montant_total) - entier_fcfa(v.paye))

    for depot_id, vendeur_id, balles, rabais in lignes.values("vente__depot_id", "vente__vendeur_id").annotate(
        b=Sum("quantite"), r=Sum("remise")
    ).values_list("vente__depot_id", "vente__vendeur_id", "b", "r"):
        for table, cle in ((par_depot, depot_id), (par_vendeur, vendeur_id)):
            table[cle]["balles"] += int(balles or 0)
            table[cle]["rabais"] += entier_fcfa(rabais)

    for depot_id, nom, montant in paiements.values("vente__depot_id", "vente__depot__nom").annotate(
        t=Sum("montant")
    ).values_list("vente__depot_id", "vente__depot__nom", "t"):
        par_depot.setdefault(depot_id, _ligne_vide(nom))["encaisse"] += entier_fcfa(montant)

    for user_id, prenom, nom, identifiant, montant in paiements.values(
        "utilisateur_id", "utilisateur__first_name", "utilisateur__last_name", "utilisateur__username"
    ).annotate(t=Sum("montant")).values_list(
        "utilisateur_id", "utilisateur__first_name", "utilisateur__last_name", "utilisateur__username", "t"
    ):
        nom_complet = f"{prenom or ''} {nom or ''}".strip() or identifiant
        par_vendeur.setdefault(user_id, _ligne_vide(nom_complet))["encaisse"] += entier_fcfa(montant)

    def trier(table):
        return sorted(table.values(), key=lambda l: (-l["vendu"], -l["encaisse"], l["nom"]))

    depots, vendeurs = trier(par_depot), trier(par_vendeur)
    totaux = _ligne_vide("Total")
    for l in depots:
        for k in ("ventes", "balles", "vendu", "encaisse", "reste", "rabais"):
            totaux[k] += l[k]

    # --- Encaissé par moyen de paiement ------------------------------------------
    libelles = dict(ModePaiement.choices)
    par_mode = {code: {"nom": libelle, "nombre": 0, "montant": 0} for code, libelle in ModePaiement.choices}
    for mode, nombre, montant in paiements.values("mode_paiement").annotate(n=Count("id"), t=Sum("montant")).values_list(
        "mode_paiement", "n", "t"
    ):
        par_mode.setdefault(mode, {"nom": libelles.get(mode, mode), "nombre": 0, "montant": 0})
        par_mode[mode]["nombre"] += nombre
        par_mode[mode]["montant"] += entier_fcfa(montant)
    modes = [m for m in par_mode.values()]

    # --- Par catégorie et qualité ------------------------------------------------
    categories = []
    for categorie, qualite, balles, montant in lignes.values(
        "lot__categorie_lot__nom", "lot__qualite__nom"
    ).annotate(b=Sum("quantite"), t=Sum("montant_ligne")).values_list(
        "lot__categorie_lot__nom", "lot__qualite__nom", "b", "t"
    ):
        balles = int(balles or 0)
        montant = entier_fcfa(montant)
        categories.append({
            "categorie": categorie or "—", "qualite": qualite or "Sans qualité", "balles": balles,
            "montant": montant, "prix_moyen": entier_fcfa(Decimal(montant) / balles) if balles else 0,
        })
    categories.sort(key=lambda c: (-c["montant"], c["categorie"], c["qualite"]))

    return {
        "totaux": totaux,
        "depots": depots,
        "vendeurs": vendeurs,
        "modes": modes,
        "categories": categories,
        "retards": echeances_en_retard(ventes_visibles, depot=depot, vendeur=vendeur),
    }


def echeances_en_retard(ventes_visibles, depot=None, vendeur=None):
    """Échéances dépassées et pas (entièrement) payées, à ce jour, quelle que soit la période choisie."""
    qs = EcheancesMoratoire.objects.filter(
        statut__in=["A_PAYER", "PARTIELLE"], moratoire__statut="EN_COURS",
        date_echeance__lt=timezone.localdate(),
        moratoire__vente__in=ventes_visibles.filter(statut=StatutVente.VALIDEE),
    )
    if depot:
        qs = qs.filter(moratoire__vente__depot=depot)
    if vendeur:
        qs = qs.filter(moratoire__vente__vendeur=vendeur)
    qs = qs.select_related("moratoire__vente__client", "moratoire__vente__depot").annotate(
        affecte=Coalesce(Sum("affectations__montant_affecte", filter=Q(affectations__paiement__statut=StatutPaiement.VALIDE)), ZERO)
    ).order_by("date_echeance")

    liste, par_depot = [], defaultdict(lambda: {"nombre": 0, "montant": 0})
    aujourd_hui = timezone.localdate()
    for e in qs:
        du = entier_fcfa(e.montant_prevu) - entier_fcfa(e.affecte)
        if du <= 0:
            continue
        vente = e.moratoire.vente
        liste.append({"echeance": e, "vente": vente, "du": du, "jours": (aujourd_hui - e.date_echeance).days})
        par_depot[vente.depot.nom]["nombre"] += 1
        par_depot[vente.depot.nom]["montant"] += du
    return {
        "liste": liste,
        "par_depot": sorted(({"nom": k, **v} for k, v in par_depot.items()), key=lambda d: -d["montant"]),
        "total": sum(x["du"] for x in liste),
    }
