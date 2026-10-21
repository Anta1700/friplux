"""Pages de vente (téléphone) : vente en cours, ajout de balles par scan, validation, facture, encaissement."""
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    Clients, Lots, ModePaiement, Paiements, ResultatScan, StatutFacture, StatutPaiement, StatutVente, Ventes,
)
from .montants import entier_fcfa
from .scans import identifier
from .ventes import (
    ErreurVente, MAX_ECHEANCES, abandonner_vente, ajouter_au_panier, ajouter_mois, balles_disponibles,
    deja_affecte, echeances_en_retard, encaisser, montant_paye, normaliser_telephone, reste_a_payer,
    retirer_ligne, valider_vente, vente_en_cours,
)

CHAMP_MONTANT = {"inputmode": "numeric", "autocomplete": "off"}


def ventes_visibles(utilisateur):
    """Administration : toutes les ventes. Sinon : celles de son dépôt (et les siennes)."""
    qs = Ventes.objects.exclude(statut=StatutVente.BROUILLON)
    if utilisateur.is_staff:
        return qs
    filtre = Q(vendeur=utilisateur)
    if utilisateur.depot_id:
        filtre |= Q(depot_id=utilisateur.depot_id)
    return qs.filter(filtre)


def _vente_visible_ou_403(request, pk):
    vente = get_object_or_404(Ventes.objects.select_related("client", "depot", "vendeur"), pk=pk)
    if vente.statut == StatutVente.BROUILLON:
        if vente.vendeur_id != request.user.pk:
            raise PermissionDenied
        return vente
    if not ventes_visibles(request.user).filter(pk=vente.pk).exists():
        raise PermissionDenied
    return vente


# ------------------------------------------------------------------
# Vente en cours
# ------------------------------------------------------------------

@login_required
def ventes(request):
    vente = vente_en_cours(request.user)
    lignes = list(vente.lignes.select_related("lot", "lot__qualite").all()) if vente else []

    visibles = ventes_visibles(request.user).filter(statut=StatutVente.VALIDEE)
    a_encaisser = list(
        visibles.filter(facture__statut=StatutFacture.EMISE).select_related("client", "facture").order_by("date_vente")[:30]
    )
    for v in a_encaisser:
        v.reste = reste_a_payer(v)
        v.en_retard = bool(echeances_en_retard(v))
    dernieres = visibles.select_related("client", "facture", "vendeur").order_by("-date_vente")[:10]

    aujourd_hui = timezone.localdate()
    du_jour = visibles.filter(date_vente__date=aujourd_hui)
    encaisse = Paiements.objects.filter(
        vente__in=ventes_visibles(request.user), statut=StatutPaiement.VALIDE, date_paiement__date=aujourd_hui
    ).aggregate(t=Sum("montant"))["t"] or 0
    return render(request, "core/ventes.html", {
        "vente": vente,
        "lignes": lignes,
        "a_encaisser": a_encaisser,
        "dernieres": dernieres,
        "jour": {
            "ventes": du_jour.count(),
            "balles": int(du_jour.aggregate(t=Sum("lignes__quantite"))["t"] or 0),
            "montant": du_jour.aggregate(t=Sum("montant_total"))["t"] or 0,
            "encaisse": encaisse,
        },
    })


@login_required
def vente_scanner(request):
    """Même écran que la réception, mais le code lu ajoute le lot à la vente (rien n'est « reçu »)."""
    if request.method == "POST":
        lot, qr, resultat = identifier(request.POST.get("code", ""))
        if resultat == ResultatScan.INCONNU or lot is None:
            messages.error(request, "Code inconnu dans Frip'Lux. Vérifiez l'étiquette ou saisissez le code du lot.")
            return redirect("core:vente_scanner")
        if resultat == ResultatScan.QR_REMPLACE:
            messages.warning(request, "Ancienne étiquette : pensez à la remplacer. Le lot est quand même reconnu.")
        return redirect("core:vente_ajouter", code_lot=lot.code_lot)
    if not request.user.depot_id:
        messages.error(request, "Votre compte n'est rattaché à aucun dépôt : impossible de vendre. "
                                "Demandez à l'administrateur de vous rattacher à votre dépôt.")
    return render(request, "core/scanner.html", {"mode_vente": True, "vente": vente_en_cours(request.user)})


class FormulaireAjout(forms.Form):
    nombre = forms.IntegerField(label="Nombre de balles", min_value=1)
    prix = forms.CharField(label="Prix par balle (FCFA)", widget=forms.TextInput(attrs=CHAMP_MONTANT))


@login_required
def vente_ajouter(request, code_lot):
    lot = get_object_or_404(
        Lots.objects.select_related("categorie_lot", "categorie_produit", "qualite", "reference_fournisseur"),
        code_lot=code_lot,
    )
    vente = vente_en_cours(request.user)
    ligne = vente.lignes.filter(lot=lot).first() if vente else None
    disponibles = balles_disponibles(lot)
    conseille = lot.prix_conseille

    if request.method == "POST":
        formulaire = FormulaireAjout(request.POST)
        if formulaire.is_valid():
            try:
                ligne = ajouter_au_panier(request.user, lot, formulaire.cleaned_data["nombre"], formulaire.cleaned_data["prix"])
            except ErreurVente as erreur:
                messages.error(request, str(erreur))
            else:
                n = ligne.nombre_balles
                messages.success(request, f"{n} balle{'s' if n > 1 else ''} du lot {lot.code_lot} dans la vente.")
                return redirect("core:ventes")
    else:
        formulaire = FormulaireAjout(initial={
            "nombre": ligne.nombre_balles if ligne else 1,
            "prix": entier_fcfa(ligne.prix_unitaire) if ligne else (entier_fcfa(conseille) if conseille else ""),
        })

    return render(request, "core/vente_ajouter.html", {
        "lot": lot, "formulaire": formulaire, "disponibles": disponibles, "conseille": conseille, "ligne": ligne,
    })


@login_required
@require_POST
def vente_retirer(request, ligne_id):
    retirer_ligne(request.user, ligne_id)
    messages.info(request, "Ligne retirée de la vente.")
    return redirect("core:ventes")


@login_required
@require_POST
def vente_abandonner(request):
    abandonner_vente(request.user)
    messages.info(request, "Vente abandonnée : aucune balle n'a été vendue.")
    return redirect("core:ventes")


# ------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------

class FormulaireValidation(forms.Form):
    client_nom = forms.CharField(label="Nom du client", required=False, max_length=150)
    client_telephone = forms.CharField(
        label="Téléphone", required=False, max_length=30,
        widget=forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "off"}),
    )
    montant_paye = forms.CharField(label="Montant payé maintenant (FCFA)", widget=forms.TextInput(attrs=CHAMP_MONTANT))
    mode_paiement = forms.ChoiceField(
        label="Moyen de paiement", choices=ModePaiement.choices, initial=ModePaiement.ESPECES, widget=forms.RadioSelect
    )
    reference = forms.CharField(label="N° de transaction (facultatif)", required=False, max_length=100)
    nombre_echeances = forms.IntegerField(label="Payer le reste en", min_value=1, max_value=MAX_ECHEANCES, initial=1)
    date_premiere_echeance = forms.DateField(
        label="Première échéance le", required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    )


@login_required
def vente_valider(request):
    vente = vente_en_cours(request.user)
    if not vente or not vente.lignes.exists():
        messages.info(request, "La vente est vide : scannez d'abord une balle.")
        return redirect("core:ventes")
    total = entier_fcfa(vente.montant_total)

    if request.method == "POST":
        formulaire = FormulaireValidation(request.POST)
        if formulaire.is_valid():
            d = formulaire.cleaned_data
            try:
                vente = valider_vente(
                    request.user,
                    client_nom=d["client_nom"], client_telephone=d["client_telephone"],
                    montant_paye=d["montant_paye"], mode_paiement=d["mode_paiement"], reference=d["reference"],
                    nombre_echeances=d["nombre_echeances"], date_premiere_echeance=d["date_premiere_echeance"],
                )
            except ErreurVente as erreur:
                messages.error(request, str(erreur))
            else:
                messages.success(request, f"✓ Vente {vente.numero_vente} enregistrée. Voici la facture.")
                return redirect("core:vente_detail", pk=vente.pk)
    else:
        formulaire = FormulaireValidation(initial={
            "montant_paye": total, "date_premiere_echeance": ajouter_mois(timezone.localdate(), 1),
        })

    return render(request, "core/vente_valider.html", {
        "vente": vente, "lignes": vente.lignes.select_related("lot"), "total": total, "formulaire": formulaire,
        "balles": sum(l.nombre_balles for l in vente.lignes.all()),
    })


@login_required
def client_par_telephone(request):
    """Remplit le nom quand le téléphone d'un client connu est saisi."""
    telephone = normaliser_telephone(request.GET.get("telephone", ""))
    client = Clients.objects.filter(telephone=telephone).order_by("id").first() if len(telephone) >= 6 else None
    return JsonResponse({"nom": client.nom if client else ""})


# ------------------------------------------------------------------
# Facture et encaissements
# ------------------------------------------------------------------

def _contexte_facture(vente):
    paiements = list(vente.paiements.select_related("utilisateur").order_by("date_paiement", "id"))
    echeances = []
    for moratoire in vente.moratoires.all():
        for e in moratoire.echeances.all():
            e.paye = deja_affecte(e)
            e.en_retard = e.statut in ("A_PAYER", "PARTIELLE") and e.date_echeance < timezone.localdate()
            echeances.append(e)
    lignes = list(vente.lignes.select_related("lot").all())
    return {
        "vente": vente,
        "facture": getattr(vente, "facture", None),
        "lignes": lignes,
        "balles": sum(l.nombre_balles for l in lignes),
        "paiements": paiements,
        "paye": montant_paye(vente),
        "reste": reste_a_payer(vente),
        "echeances": echeances,
        "societe": settings.FRIPLUX_SOCIETE,
    }


@login_required
def vente_detail(request, pk):
    vente = _vente_visible_ou_403(request, pk)
    if vente.statut == StatutVente.BROUILLON:
        return redirect("core:ventes")
    return render(request, "core/facture.html", _contexte_facture(vente))


class FormulaireEncaissement(forms.Form):
    montant = forms.CharField(label="Montant reçu (FCFA)", widget=forms.TextInput(attrs=CHAMP_MONTANT))
    mode_paiement = forms.ChoiceField(
        label="Moyen de paiement", choices=ModePaiement.choices, initial=ModePaiement.ESPECES, widget=forms.RadioSelect
    )
    reference = forms.CharField(label="N° de transaction (facultatif)", required=False, max_length=100)


@login_required
def vente_encaisser(request, pk):
    vente = _vente_visible_ou_403(request, pk)
    reste = reste_a_payer(vente)
    if reste == 0:
        messages.info(request, "Cette vente est déjà entièrement payée.")
        return redirect("core:vente_detail", pk=vente.pk)

    contexte = _contexte_facture(vente)
    prochaine = next((e for e in contexte["echeances"] if e.statut in ("A_PAYER", "PARTIELLE")), None)
    if request.method == "POST":
        formulaire = FormulaireEncaissement(request.POST)
        if formulaire.is_valid():
            d = formulaire.cleaned_data
            try:
                encaisser(request.user, vente, d["montant"], d["mode_paiement"], d["reference"])
            except ErreurVente as erreur:
                messages.error(request, str(erreur))
            else:
                nouveau_reste = reste_a_payer(vente)
                if nouveau_reste:
                    messages.success(request, "Paiement enregistré.")
                else:
                    messages.success(request, "✓ Paiement enregistré : la vente est entièrement payée.")
                return redirect("core:vente_detail", pk=vente.pk)
    else:
        suggestion = min(reste, entier_fcfa(prochaine.montant_prevu) - prochaine.paye) if prochaine else reste
        formulaire = FormulaireEncaissement(initial={"montant": suggestion})

    contexte.update({"formulaire": formulaire, "prochaine": prochaine})
    return render(request, "core/vente_encaisser.html", contexte)
