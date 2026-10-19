"""
Écran d'administration : import d'une fiche de commande fournisseur (Excel).

Étape 1 : choisir le conteneur et déposer la fiche.
Étape 2 : aperçu ligne par ligne, avec le classement (catégorie, sous-catégorie, qualité)
          reconnu dans le catalogue ou proposé automatiquement, modifiable.
Étape 3 : création des lots (un par ligne de la fiche, avec son QR code) et mémorisation du classement.
"""
from django import forms
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.html import format_html

from .import_fiche import ErreurFiche, LigneFiche, lire_fiche, normaliser_numero_conteneur, proposer_classement
from .models import (
    CategoriesLots,
    CategoriesProduits,
    Conteneurs,
    Qualites,
    ReferencesFournisseurs,
    sous_categorie_compatible,
)
from .services import importer_fiche

CLE_SESSION = "friplux_import_fiche"


class FormulaireFiche(forms.Form):
    conteneur = forms.ModelChoiceField(
        queryset=Conteneurs.objects.select_related("fournisseur").order_by("-id"),
        help_text="Le conteneur doit exister (Conteneurs → Ajouter). Son fournisseur est celui de la fiche.",
    )
    fichier = forms.FileField(label="Fiche Excel (.xlsx)")

    def clean_fichier(self):
        fichier = self.cleaned_data["fichier"]
        if not fichier.name.lower().endswith((".xlsx", ".xlsm")):
            raise forms.ValidationError("Choisissez un fichier Excel .xlsx.")
        return fichier


class FormulaireLigne(forms.Form):
    categorie_lot = forms.ModelChoiceField(
        queryset=CategoriesLots.objects.filter(actif=True).order_by("nom"), label="Catégorie"
    )
    categorie_produit = forms.ModelChoiceField(
        queryset=CategoriesProduits.objects.filter(actif=True, parent__isnull=False)
        .select_related("parent")
        .order_by("parent__nom", "nom"),
        required=False,
        label="Sous-catégorie",
    )
    qualite = forms.ModelChoiceField(queryset=Qualites.objects.filter(actif=True), label="Qualité")

    def clean(self):
        donnees = super().clean()
        if not sous_categorie_compatible(donnees.get("categorie_lot"), donnees.get("categorie_produit")):
            self.add_error("categorie_produit", "N'appartient pas à la catégorie choisie.")
        return donnees


FormulaireLignes = forms.formset_factory(FormulaireLigne, extra=0)


def _contexte(modeladmin, request, **extra):
    return {
        **modeladmin.admin_site.each_context(request),
        "opts": modeladmin.model._meta,
        "title": "Importer une fiche fournisseur",
        **extra,
    }


def vue_import(modeladmin, request):
    """Étape 1 : dépôt de la fiche."""
    if request.method == "POST":
        formulaire = FormulaireFiche(request.POST, request.FILES)
        if formulaire.is_valid():
            try:
                fiche = lire_fiche(formulaire.cleaned_data["fichier"])
            except ErreurFiche as erreur:
                formulaire.add_error("fichier", str(erreur))
            else:
                request.session[CLE_SESSION] = {
                    "conteneur_id": formulaire.cleaned_data["conteneur"].pk,
                    "nom_fichier": formulaire.cleaned_data["fichier"].name,
                    "date": fiche.date,
                    "numero_conteneur": fiche.numero_conteneur,
                    "lignes": [ligne.to_dict() for ligne in fiche.lignes],
                    "ignorees": fiche.lignes_ignorees,
                }
                return redirect("admin:core_lots_import_apercu")
    else:
        formulaire = FormulaireFiche()

    return render(request, "admin/core/lots/import_fiche.html", _contexte(modeladmin, request, formulaire=formulaire))


def _classement_initial(lignes, fournisseur):
    """Classement de départ : catalogue si la référence est connue, sinon proposition automatique."""
    connues = {
        r.code: r
        for r in ReferencesFournisseurs.objects.filter(fournisseur=fournisseur, code__in=[l.code for l in lignes])
    }
    categories = {c.code: c for c in CategoriesLots.objects.all()}
    sous_categories = {c.code: c for c in CategoriesProduits.objects.all()}
    qualites = {q.code: q for q in Qualites.objects.all()}

    initial, statuts = [], []
    for ligne in lignes:
        reference = connues.get(ligne.code)
        if reference:
            initial.append({
                "categorie_lot": reference.categorie_lot_id,
                "categorie_produit": reference.categorie_produit_id,
                "qualite": reference.qualite_id,
            })
            statuts.append("connue")
            continue

        code_cat, code_sous_cat, code_qualite = proposer_classement(ligne)
        categorie = categories.get(code_cat)
        sous_categorie = sous_categories.get(code_sous_cat)
        qualite = qualites.get(code_qualite)
        initial.append({
            "categorie_lot": categorie.pk if categorie else None,
            "categorie_produit": sous_categorie.pk if sous_categorie and sous_categorie.actif else None,
            "qualite": qualite.pk if qualite else None,
        })
        statuts.append("proposee" if categorie and qualite else "a_classer")
    return initial, statuts


def vue_apercu(modeladmin, request):
    """Étapes 2 et 3 : aperçu modifiable, puis création."""
    donnees = request.session.get(CLE_SESSION)
    if not donnees:
        messages.warning(request, "Aucune fiche en cours : déposez d'abord le fichier.")
        return redirect("admin:core_lots_import")

    conteneur = Conteneurs.objects.select_related("fournisseur").get(pk=donnees["conteneur_id"])
    lignes = [LigneFiche(**l) for l in donnees["lignes"]]

    # Points à vérifier avant import
    alertes_bloquantes = [f"Ligne {l.numero_ligne} ({l.code or l.libelle}) : {', '.join(l.alertes)}" for l in lignes if l.alertes]
    avertissements = []
    if donnees["numero_conteneur"] and normaliser_numero_conteneur(donnees["numero_conteneur"]) != normaliser_numero_conteneur(conteneur.numero_conteneur):
        avertissements.append(
            f"La fiche indique le conteneur « {donnees['numero_conteneur']} », "
            f"mais vous avez choisi « {conteneur.numero_conteneur} »."
        )
    deja = conteneur.lots.count()
    if deja:
        avertissements.append(
            f"Ce conteneur contient déjà {deja} lot(s). Importer à nouveau la même fiche créerait des doublons. "
            "Pour repartir de zéro, utilisez la commande « reinitialiser_conteneur »."
        )

    initial, statuts = _classement_initial(lignes, conteneur.fournisseur)

    if request.method == "POST":
        if "annuler" in request.POST:
            request.session.pop(CLE_SESSION, None)
            messages.info(request, "Import annulé, aucune balle créée.")
            return redirect("admin:core_lots_changelist")

        formset = FormulaireLignes(request.POST, initial=initial)
        confirme = request.POST.get("confirmer_avertissements") == "on"
        if alertes_bloquantes:
            messages.error(request, "Corrigez la fiche Excel avant d'importer (voir les lignes signalées).")
        elif avertissements and not confirme:
            messages.error(request, "Cochez la case de confirmation des avertissements pour importer.")
        elif formset.is_valid():
            classements = [form.cleaned_data for form in formset.forms]
            lots = importer_fiche(conteneur, donnees["date"], lignes, classements)
            request.session.pop(CLE_SESSION, None)

            url_pdf = reverse("core:etiquettes_conteneur", args=[conteneur.pk])
            messages.success(
                request,
                format_html(
                    "{} lots créés pour le conteneur {} ({} balles), chacun avec son QR code. "
                    'Étiquettes : <a href="{}"><strong>une par lot (PDF)</strong></a> · '
                    '<a href="{}?copies=balles"><strong>une par balle, prêtes à coller (PDF)</strong></a>',
                    len(lots), conteneur.numero_conteneur, sum(l.nombre_balles for l in lots), url_pdf, url_pdf,
                ),
            )
            url = reverse("admin:core_lots_changelist") + f"?conteneur__id__exact={conteneur.pk}"
            return redirect(url)
        else:
            messages.error(request, "Certaines lignes sont incomplètes ou incohérentes (voir en rouge).")
    else:
        formset = FormulaireLignes(initial=initial)

    rangees = []
    for ligne, form, statut in zip(lignes, formset.forms, statuts):
        rangees.append({"ligne": ligne, "form": form, "statut": statut})

    total_statuts = {s: statuts.count(s) for s in ("connue", "proposee", "a_classer")}
    return render(
        request,
        "admin/core/lots/import_apercu.html",
        _contexte(
            modeladmin,
            request,
            title="Vérifier la fiche avant import",
            donnees=donnees,
            conteneur=conteneur,
            formset=formset,
            rangees=rangees,
            nombre_lots=len(lignes),
            nombre_balles=sum(l.nombre_balles for l in lignes),
            poids_total=sum(float(l.poids_total) for l in lignes),
            alertes_bloquantes=alertes_bloquantes,
            avertissements=avertissements,
            total_statuts=total_statuts,
        ),
    )
