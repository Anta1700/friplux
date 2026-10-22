"""Pages Stock et Transferts (téléphone)."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Depots, Lots, ResultatScan, StatutTransfert, TransfertsStock
from .scans import identifier
from .stock import (
    ErreurStock, abandonner_transfert, ajouter_au_transfert, annuler_transfert, balles_dans_depot, cloturer_avec_ecart,
    envoyer_transfert, message_balles_ailleurs, preparer_transfert, progression, retirer_du_transfert, stock_balles,
    stock_du_depot, transfert_en_preparation, transferts_a_recevoir, transferts_envoyes_en_route,
)


@login_required
def stock(request):
    """Stock de balles d'un dépôt. Administration : tous les dépôts, avec choix du dépôt."""
    depots = Depots.objects.filter(actif=True).order_by("nom")
    depot = None
    if request.user.is_staff:
        if request.GET.get("depot", "").isdigit():
            depot = depots.filter(pk=request.GET["depot"]).first()
    else:
        depot = request.user.depot

    contexte = {"depots": depots, "depot": depot}
    if depot:
        lignes, resume, total = stock_du_depot(depot)
        contexte.update({
            "lignes": lignes, "resume": resume, "total": total,
            "a_recevoir": [(t, *progression(t)) for t in transferts_a_recevoir(depot.pk)],
            "envoyes": [(t, *progression(t)) for t in transferts_envoyes_en_route(depot.pk)],
        })
    elif request.user.is_staff:
        stock_tous, en_route = stock_balles()
        par_depot = {}
        for (lot_id, depot_id), n in stock_tous.items():
            if n > 0:
                par_depot[depot_id] = par_depot.get(depot_id, 0) + n
        contexte.update({
            "par_depot": [{"depot": d, "balles": par_depot.get(d.pk, 0)} for d in depots],
            "total": sum(par_depot.values()), "en_route": sum(en_route.values()),
        })
    contexte["preparation"] = transfert_en_preparation(request.user)
    return render(request, "core/stock.html", contexte)


# ------------------------------------------------------------------
# Envoi
# ------------------------------------------------------------------

@login_required
def transfert_envoi(request):
    """Préparer un envoi : choisir le dépôt de destination, puis la liste des balles."""
    if not request.user.depot_id:
        messages.error(request, "Votre compte n'est rattaché à aucun dépôt : impossible d'envoyer des balles.")
        return redirect("core:stock")
    autres = Depots.objects.filter(actif=True).exclude(pk=request.user.depot_id).order_by("nom")
    if request.method == "POST" and "depot_arrivee" in request.POST:
        depot = autres.filter(pk=request.POST.get("depot_arrivee") or 0).first()
        if depot is None:
            messages.error(request, "Choisissez le dépôt de destination.")
        else:
            try:
                preparer_transfert(request.user, depot)
            except ErreurStock as erreur:
                messages.error(request, str(erreur))
            else:
                if request.POST.get("ensuite") == "scanner":
                    return redirect("core:transfert_scanner")
        return redirect("core:transfert_envoi")

    t = transfert_en_preparation(request.user)
    lignes = list(t.mouvements.select_related("lot__categorie_lot", "lot__categorie_produit", "lot__qualite")) if t else []
    return render(request, "core/transfert_envoi.html", {
        "transfert": t, "lignes": lignes, "autres": autres, "total": sum(m.balles for m in lignes),
    })


@login_required
def transfert_scanner(request):
    t = transfert_en_preparation(request.user)
    if not t:
        return redirect("core:transfert_envoi")
    if request.method == "POST":
        lot, qr, resultat = identifier(request.POST.get("code", ""))
        if resultat == ResultatScan.INCONNU or lot is None:
            messages.error(request, "Code inconnu dans Frip'Lux. Vérifiez l'étiquette ou saisissez le code du lot.")
            return redirect("core:transfert_scanner")
        return redirect("core:transfert_ajouter", code_lot=lot.code_lot)
    return render(request, "core/scanner.html", {"mode_transfert": True, "transfert": t})


class FormulaireNombre(forms.Form):
    nombre = forms.IntegerField(min_value=1)


@login_required
def transfert_ajouter(request, code_lot):
    t = transfert_en_preparation(request.user)
    if not t:
        return redirect("core:transfert_envoi")
    lot = get_object_or_404(Lots.objects.select_related("categorie_lot", "categorie_produit", "qualite"), code_lot=code_lot)
    ligne = t.mouvements.filter(lot=lot).first()
    disponibles = balles_dans_depot(lot, request.user.depot_id)
    if request.method == "POST":
        formulaire = FormulaireNombre(request.POST)
        if formulaire.is_valid():
            try:
                m = ajouter_au_transfert(request.user, lot, formulaire.cleaned_data["nombre"])
            except ErreurStock as erreur:
                messages.error(request, str(erreur))
            else:
                messages.success(request, f"{m.balles} balle{'s' if m.balles > 1 else ''} du lot {lot.code_lot} dans l'envoi.")
                return redirect("core:transfert_envoi")
    return render(request, "core/transfert_ajouter.html", {
        "transfert": t, "lot": lot, "ligne": ligne, "disponibles": disponibles,
        "ailleurs": message_balles_ailleurs(lot, request.user.depot_id) if not disponibles else "",
        "nombre": ligne.balles if ligne else 1,
    })


@login_required
@require_POST
def transfert_retirer(request, mouvement_id):
    retirer_du_transfert(request.user, mouvement_id)
    return redirect("core:transfert_envoi")


@login_required
@require_POST
def transfert_abandonner(request):
    abandonner_transfert(request.user)
    messages.info(request, "Envoi abandonné : aucune balle n'a bougé.")
    return redirect("core:stock")


@login_required
@require_POST
def transfert_envoyer(request):
    try:
        t = envoyer_transfert(request.user)
    except ErreurStock as erreur:
        messages.error(request, str(erreur))
        return redirect("core:transfert_envoi")
    messages.success(request, f"✓ Envoi {t.reference_transfert} vers {t.depot_arrivee.nom} enregistré. "
                              "Les balles seront comptées à leur arrivée, quand le dépôt les scannera.")
    return redirect("core:transfert_detail", pk=t.pk)


# ------------------------------------------------------------------
# Suivi et arrivée
# ------------------------------------------------------------------

def _transfert_visible_ou_403(request, pk):
    t = get_object_or_404(TransfertsStock.objects.select_related("depot_depart", "depot_arrivee", "utilisateur"), pk=pk)
    if t.statut == StatutTransfert.BROUILLON:
        raise PermissionDenied
    if not request.user.is_staff and request.user.depot_id not in (t.depot_depart_id, t.depot_arrivee_id):
        raise PermissionDenied
    return t


@login_required
def transfert_detail(request, pk):
    t = _transfert_visible_ou_403(request, pk)
    lignes = list(t.mouvements.select_related("lot__categorie_lot", "lot__categorie_produit", "lot__qualite").order_by("id"))
    arrivees, total = progression(t)
    return render(request, "core/transfert_detail.html", {
        "t": t, "lignes": lignes, "arrivees": arrivees, "total": total,
        "cote_arrivee": request.user.is_staff or request.user.depot_id == t.depot_arrivee_id,
        "cote_depart": request.user.is_staff or request.user.depot_id == t.depot_depart_id,
        "en_route": t.statut == StatutTransfert.EN_COURS,
        "manquantes": sum(m.balles_manquantes for m in lignes) if t.statut == StatutTransfert.RECU_AVEC_ECART else 0,
    })


@login_required
@require_POST
def transfert_cloturer(request, pk):
    t = _transfert_visible_ou_403(request, pk)
    try:
        t = cloturer_avec_ecart(request.user, t)
    except ErreurStock as erreur:
        messages.error(request, str(erreur))
    else:
        messages.warning(request, "Transfert clôturé. Les balles manquantes sont signalées à l'administration.")
    return redirect("core:transfert_detail", pk=t.pk)


@login_required
@require_POST
def transfert_annuler(request, pk):
    t = _transfert_visible_ou_403(request, pk)
    try:
        annuler_transfert(request.user, t)
    except ErreurStock as erreur:
        messages.error(request, str(erreur))
    else:
        messages.info(request, "Envoi annulé : les balles sont de nouveau dans votre stock.")
    return redirect("core:transfert_detail", pk=t.pk)
