"""Pages Frip'Lux hors administration : scanner une balle, fiche de la balle, statistiques des scans."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .models import CategoriesLots, Conteneurs, Depots, Lots, ResultatScan, ScansLots, StatutLogistique, User
from .scans import EffetScan, compteurs_par_categorie, derniere_reception, enregistrer_scan, filtrer_scans


def _message_scan(request, scan, effet):
    """Message court et clair après un scan."""
    lot = scan.lot
    lot.refresh_from_db(fields=["nombre_balles_recues", "statut_logistique"])
    compteur = f"{lot.nombre_balles_recues or 0} / {lot.nombre_balles}"
    if effet == EffetScan.LOT_COMPLET:
        messages.success(request, f"✓ Lot complet : {compteur} balles scannées.")
    elif effet == EffetScan.BALLE_COMPTEE:
        messages.success(request, f"Balle enregistrée : {compteur} scannées.")
    elif effet == EffetScan.DEJA_COMPLET:
        messages.info(request, f"Toutes les balles de ce lot sont déjà scannées ({compteur}).")
    elif effet == EffetScan.DOUBLON:
        messages.warning(request, f"Scan répété à l'instant : balle non recomptée ({compteur}).")
    elif effet == EffetScan.NON_RECEVABLE:
        messages.error(request, f"Lot {lot.get_statut_logistique_display().lower()} : balle non comptée.")


@login_required
def accueil(request):
    return redirect("core:scanner")


@login_required
@require_http_methods(["GET", "POST"])
def scanner(request):
    """Page de scan. Le navigateur envoie le code lu (caméra, photo ou saisie) en POST."""
    if request.method == "POST":
        code = request.POST.get("code", "")
        scan, effet = enregistrer_scan(code, request.user)
        if scan.resultat == ResultatScan.INCONNU:
            messages.error(
                request,
                f"Code « {scan.code_scanne} » inconnu dans Frip'Lux. Vérifiez l'étiquette ou saisissez le code du lot.",
            )
            return redirect("core:scanner")
        _message_scan(request, scan, effet)
        url = reverse("core:fiche_balle", args=[scan.lot.code_lot])
        return redirect(f"{url}?scan={scan.pk}")

    derniers = (
        ScansLots.objects.filter(utilisateur=request.user)
        .exclude(resultat=ResultatScan.INCONNU)
        .select_related("lot", "categorie_lot")[:5]
    )
    return render(request, "core/scanner.html", {"derniers": derniers})


@login_required
def fiche_balle(request, code_lot):
    lot = get_object_or_404(
        Lots.objects.select_related(
            "conteneur__fournisseur", "categorie_lot", "categorie_produit", "qualite", "reference_fournisseur"
        ),
        code_lot=code_lot,
    )

    scan = None
    if request.GET.get("scan", "").isdigit():
        scan = ScansLots.objects.select_related("qr_code").filter(pk=request.GET["scan"], lot=lot).first()

    contexte = {
        "lot": lot,
        "scan": scan,
        "qr_actif": lot.qr_codes.filter(actif=True).first(),
        "reception": derniere_reception(lot),
        "scannees": lot.nombre_balles_recues or 0,
        "voir_prix": request.user.is_staff,
        "StatutLogistique": StatutLogistique,
    }
    return render(request, "core/fiche_balle.html", contexte)


class FiltresStatistiques(forms.Form):
    date_debut = forms.DateField(label="Du", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_fin = forms.DateField(label="Au", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    conteneur = forms.ModelChoiceField(Conteneurs.objects.order_by("-id"), required=False, empty_label="Tous")
    depot = forms.ModelChoiceField(Depots.objects.order_by("nom"), required=False, label="Dépôt", empty_label="Tous")
    utilisateur = forms.ModelChoiceField(
        User.objects.filter(is_active=True).order_by("username"), required=False, empty_label="Tous"
    )


@login_required
def statistiques(request):
    filtres = FiltresStatistiques(request.GET or None)
    criteres = filtres.cleaned_data if filtres.is_valid() else {}
    scans = filtrer_scans(**{k: v for k, v in criteres.items() if v})

    lignes, totaux, inconnus = compteurs_par_categorie(scans)
    # Afficher toutes les catégories, même sans scan (0), dans un ordre stable.
    par_nom = {l["categorie_lot__nom"]: l for l in lignes}
    tableau = [
        {
            "categorie": c.nom,
            "scans": par_nom.get(c.nom, {}).get("scans", 0),
            "lots": par_nom.get(c.nom, {}).get("lots", 0),
            "balles": par_nom.get(c.nom, {}).get("balles", 0),
        }
        for c in CategoriesLots.objects.filter(actif=True).order_by("nom")
    ]

    historique = scans.select_related("lot", "categorie_lot", "utilisateur", "depot")[:50]
    return render(
        request,
        "core/statistiques.html",
        {"filtres": filtres, "tableau": tableau, "totaux": totaux, "inconnus": inconnus, "historique": historique},
    )
