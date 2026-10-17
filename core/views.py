from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from .models import QrCodes
from .services import png_qr


@staff_member_required
def qr_code_png(request, pk):
    """Étiquette QR d'un lot en PNG. ?telecharger=1 pour forcer le téléchargement."""
    qr_code = get_object_or_404(QrCodes.objects.select_related("lot__categorie_lot", "lot__conteneur"), pk=pk)
    reponse = HttpResponse(png_qr(qr_code), content_type="image/png")
    if request.GET.get("telecharger"):
        reponse["Content-Disposition"] = f'attachment; filename="{qr_code.code}.png"'
    return reponse
