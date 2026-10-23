"""
Lien public secret de chaque facture.

Le client scanne le QR code de sa facture (écran du vendeur, PDF ou papier) : sa facture PDF s'ouvre
sur son téléphone, sans compte. Le lien contient un jeton aléatoire de 32 caractères (impossible à
deviner) : il ne donne accès qu'à CETTE facture. Un administrateur peut le désactiver.
"""
import base64
import io
import secrets

from django.conf import settings
from django.urls import reverse

from .models import Factures

ADRESSES_LOCALES = ("localhost", "127.0.0.1", "[::1]")


def nouveau_jeton():
    return secrets.token_urlsafe(24)   # 32 caractères


def jeton_de(facture):
    """Jeton de la facture, créé au besoin (factures faites avant le script 008)."""
    if not facture.jeton_public:
        facture.jeton_public = nouveau_jeton()
        Factures.objects.filter(pk=facture.pk, jeton_public__isnull=True).update(jeton_public=facture.jeton_public)
        facture.refresh_from_db(fields=["jeton_public"])
    return facture.jeton_public


def adresse_de_base(request):
    return settings.FRIPLUX_ADRESSE_PUBLIQUE or f"{request.scheme}://{request.get_host()}"


def lien_public(request, facture):
    return adresse_de_base(request) + reverse("core:facture_client", args=[jeton_de(facture)])


def adresse_locale(request):
    """Vrai si le lien ne marchera que sur cet ordinateur (localhost)."""
    if settings.FRIPLUX_ADRESSE_PUBLIQUE:
        return False
    return request.get_host().split(":")[0] in ADRESSES_LOCALES


def qr_png(texte, taille_case=8):
    import qrcode
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=taille_case, border=2)
    qr.add_data(texte)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").get_image().convert("RGB")


def qr_data_uri(texte):
    sortie = io.BytesIO()
    qr_png(texte).save(sortie, "PNG")
    return "data:image/png;base64," + base64.b64encode(sortie.getvalue()).decode()
