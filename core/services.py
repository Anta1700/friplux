"""
Logique métier Frip'Lux : codes de lots et QR codes.

Règles appliquées :
- Code lot : FRPLX-LOT-<année>-<numéro sur 6 chiffres>, numérotation qui repart à 1 chaque année.
- Unicité garantie même en cas de créations simultanées : verrou transactionnel
  PostgreSQL (pg_advisory_xact_lock) + contrainte UNIQUE lots_code_lot_key en dernier filet.
- Chaque lot reçoit automatiquement un QR code (version 1) dans la même transaction :
  soit le lot ET son QR existent, soit aucun des deux.
- Le QR contient uniquement un identifiant stable (le code du QR), jamais les données
  du lot : elles sont relues en base au moment du scan.
- Réimpression : on désactive l'ancien QR et on crée la version suivante
  (une seule version active par lot, garanti par uq_qr_codes_active_lot).
"""

import io
import re

import qrcode
from PIL import Image, ImageDraw, ImageFont
from django.db import connection, transaction
from django.utils import timezone

from .models import Lots, QrCodes

PREFIXE_LOT = "FRPLX-LOT"
NUMERO_MAX = 999_999

# Identifiant arbitraire (mais fixe) du verrou PostgreSQL qui sérialise la
# génération des codes de lots. Ne pas le réutiliser pour autre chose.
CLE_VERROU_CODES_LOTS = 2026_0001


class ErreurCodeLot(Exception):
    pass


# ------------------------------------------------------------------
# Codes de lots
# ------------------------------------------------------------------

def generer_code_lot(annee=None):
    """
    Retourne le prochain code libre, par exemple FRPLX-LOT-2026-000001.

    Doit être appelée DANS une transaction (transaction.atomic) qui insère
    ensuite le lot : le verrou est conservé jusqu'à la fin de la transaction,
    ce qui empêche deux créations simultanées d'obtenir le même numéro.
    """
    if not connection.in_atomic_block:
        raise ErreurCodeLot(
            "generer_code_lot() doit être appelée dans transaction.atomic(), "
            "sinon deux créations simultanées pourraient obtenir le même code."
        )

    annee = annee or timezone.localdate().year

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [CLE_VERROU_CODES_LOTS])

    prefixe = f"{PREFIXE_LOT}-{annee}-"
    # Les numéros ont toujours 6 chiffres : l'ordre alphabétique = l'ordre numérique.
    dernier_code = (
        Lots.objects.filter(code_lot__regex=rf"^{re.escape(prefixe)}\d{{6}}$")
        .order_by("-code_lot")
        .values_list("code_lot", flat=True)
        .first()
    )

    numero = int(dernier_code[-6:]) + 1 if dernier_code else 1
    if numero > NUMERO_MAX:
        raise ErreurCodeLot(f"Plus de numéros disponibles pour l'année {annee}.")

    return f"{prefixe}{numero:06d}"


# ------------------------------------------------------------------
# QR codes
# ------------------------------------------------------------------

def code_qr_pour(lot, version):
    """Texte encodé dans le QR : code du lot + version (ex. FRPLX-LOT-2026-000001-V1)."""
    return f"{lot.code_lot}-V{version}"


def creer_qr_code(lot):
    """Crée la version 1 du QR code d'un lot qui vient d'être créé."""
    return QrCodes.objects.create(
        lot=lot,
        code=code_qr_pour(lot, 1),
        version=1,
        date_generation=timezone.now(),
        actif=True,
    )


@transaction.atomic
def creer_lot(**champs):
    """
    Crée un lot avec son code automatique et son QR code, en une seule transaction.

    Exemple :
        creer_lot(conteneur=c, categorie_lot=cat, poids_kg=Decimal("45.50"), prix_achat=Decimal("120000"))
    """
    if champs.get("code_lot"):
        raise ErreurCodeLot("Le code du lot est généré automatiquement : ne pas le fournir.")

    lot = Lots(**champs)
    lot.code_lot = generer_code_lot()
    lot.full_clean()
    lot.save()
    creer_qr_code(lot)
    return lot


@transaction.atomic
def regenerer_qr_code(lot):
    """
    Remplace le QR code d'un lot (étiquette perdue ou abîmée) :
    l'ancien est désactivé, une nouvelle version active est créée.
    Le code du lot, lui, ne change jamais.
    """
    # Verrouille la ligne du lot : deux réimpressions simultanées ne peuvent
    # pas calculer le même numéro de version.
    lot = Lots.objects.select_for_update().get(pk=lot.pk)

    derniere_version = (
        QrCodes.objects.filter(lot=lot).order_by("-version").values_list("version", flat=True).first()
        or 0
    )
    # Désactiver AVANT de créer : l'index uq_qr_codes_active_lot n'autorise
    # qu'un seul QR actif par lot.
    QrCodes.objects.filter(lot=lot, actif=True).update(actif=False)

    nouvelle_version = derniere_version + 1
    return QrCodes.objects.create(
        lot=lot,
        code=code_qr_pour(lot, nouvelle_version),
        version=nouvelle_version,
        date_generation=timezone.now(),
        actif=True,
    )


def marquer_envoyes_au_fournisseur(qr_codes):
    """Renseigne la date d'envoi au fournisseur des QR qui n'en ont pas encore."""
    return qr_codes.filter(date_envoi_fournisseur__isnull=True).update(
        date_envoi_fournisseur=timezone.now()
    )


# ------------------------------------------------------------------
# Images et étiquettes imprimables
# ------------------------------------------------------------------

# Polices avec accents : Arial sous Windows, DejaVu/Liberation sous Linux.
POLICES_CANDIDATES = (
    "arial.ttf",
    "DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)
LARGEUR_ETIQUETTE = 600  # pixels ; marge autour du QR pour le texte


def _police(taille):
    for nom in POLICES_CANDIDATES:
        try:
            return ImageFont.truetype(nom, taille)
        except OSError:
            continue
    return ImageFont.load_default(size=taille)  # sans accents, dernier recours


def _police_ajustee(dessin, texte, taille, largeur_max):
    """Réduit la taille de police jusqu'à ce que le texte tienne dans la largeur."""
    while taille > 10:
        police = _police(taille)
        if dessin.textlength(texte, font=police) <= largeur_max:
            return police
        taille -= 2
    return _police(10)


def image_qr(code):
    """Image PIL du QR seul. Correction d'erreur élevée (Q) : lisible même si l'étiquette est un peu abîmée."""
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_Q, box_size=10, border=4)
    qr.add_data(code)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").get_image().convert("RGB")


def image_etiquette(qr_code):
    """
    Étiquette prête à imprimer : QR + code en clair + catégorie et conteneur.
    Le code en clair permet une saisie manuelle si le QR devient illisible.
    """
    lot = qr_code.lot
    image = image_qr(qr_code.code)
    largeur = max(LARGEUR_ETIQUETTE, image.width)
    largeur_texte_max = largeur - 40

    textes = [
        (lot.code_lot, 40),
        (f"{lot.categorie_lot}  ·  Conteneur {lot.conteneur}", 26),
    ]
    if qr_code.version > 1:
        textes.append((f"Étiquette version {qr_code.version}", 22))

    mesure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lignes = [(texte, _police_ajustee(mesure, texte, taille, largeur_texte_max)) for texte, taille in textes]

    espacement = 12
    hauteur_texte = sum(police.size + espacement for _, police in lignes) + 20
    etiquette = Image.new("RGB", (largeur, image.height + hauteur_texte), "white")
    etiquette.paste(image, ((largeur - image.width) // 2, 0))

    dessin = ImageDraw.Draw(etiquette)
    y = image.height - 10
    for texte, police in lignes:
        largeur_ligne = dessin.textlength(texte, font=police)
        dessin.text(((largeur - largeur_ligne) / 2, y), texte, fill="black", font=police)
        y += police.size + espacement

    return etiquette


def png_qr(qr_code):
    """Contenu PNG de l'étiquette d'un QR code."""
    tampon = io.BytesIO()
    image_etiquette(qr_code).save(tampon, format="PNG")
    return tampon.getvalue()


def pdf_etiquettes(qr_codes):
    """PDF avec une étiquette par page, à envoyer au fournisseur ou à imprimer."""
    images = [image_etiquette(qr) for qr in qr_codes]
    if not images:
        raise ValueError("Aucun QR code à imprimer.")
    tampon = io.BytesIO()
    images[0].save(tampon, format="PDF", save_all=True, append_images=images[1:], resolution=200)
    return tampon.getvalue()
