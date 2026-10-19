import re

from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404

from .models import Conteneurs, QrCodes
from .services import RELATIONS_ETIQUETTE, pdf_etiquettes, png_qr


@staff_member_required
def qr_code_png(request, pk):
    """Étiquette QR d'un lot en PNG. ?telecharger=1 pour forcer le téléchargement."""
    qr_code = get_object_or_404(QrCodes.objects.select_related(*RELATIONS_ETIQUETTE), pk=pk)
    reponse = HttpResponse(png_qr(qr_code), content_type="image/png")
    if request.GET.get("telecharger"):
        reponse["Content-Disposition"] = f'attachment; filename="{qr_code.code}.png"'
    return reponse


@staff_member_required
def etiquettes_conteneur(request, conteneur_id):
    """
    PDF des étiquettes actives des lots d'un conteneur (à envoyer au fournisseur).
    ?copies=balles : une étiquette par balle (l'étiquette du lot est répétée).
    """
    conteneur = get_object_or_404(Conteneurs, pk=conteneur_id)
    qr_codes = list(
        QrCodes.objects.filter(lot__conteneur=conteneur, actif=True)
        .select_related(*RELATIONS_ETIQUETTE)
        .order_by("lot__code_lot")
    )
    if not qr_codes:
        raise Http404("Aucun lot avec QR code actif dans ce conteneur.")
    une_par_balle = request.GET.get("copies") == "balles"
    nom = re.sub(r"[^A-Za-z0-9_-]", "", conteneur.numero_conteneur)
    suffixe = "_une_par_balle" if une_par_balle else ""
    reponse = HttpResponse(pdf_etiquettes(qr_codes, une_par_balle=une_par_balle), content_type="application/pdf")
    reponse["Content-Disposition"] = f'attachment; filename="etiquettes_{nom}{suffixe}.pdf"'
    return reponse
