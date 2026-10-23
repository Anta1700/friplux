"""
Facture au format PDF (A4), fabriquée sur le serveur avec Pillow (déjà installé) :
le vendeur peut l'envoyer au client par WhatsApp depuis son téléphone, ou l'imprimer.
Mêmes informations que la page facture ; jamais le prix conseillé ni le rabais.
"""
import io
from pathlib import Path

from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from .montants import format_fcfa, montant_en_lettres

DPI = 200
LARGEUR, HAUTEUR = 1654, 2339          # A4 à 200 points par pouce
MARGE = 120
NOIR, GRIS, VERT, ORANGE, ROUGE, TRAIT = (29, 35, 33), (93, 102, 98), (31, 59, 55), (154, 91, 0), (161, 42, 42), (210, 204, 192)

_DOSSIER_POLICES = Path(__file__).resolve().parent / "polices"   # incluses dans le projet : même rendu partout
_NORMAL = (str(_DOSSIER_POLICES / "DejaVuSans.ttf"), "arial.ttf", "DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
           "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf")
_GRAS = (str(_DOSSIER_POLICES / "DejaVuSans-Bold.ttf"), "arialbd.ttf", "DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf")
_polices = {}


def police(taille, gras=False):
    cle = (taille, gras)
    if cle not in _polices:
        for nom in (_GRAS if gras else _NORMAL):
            try:
                _polices[cle] = ImageFont.truetype(nom, taille)
                break
            except OSError:
                continue
        else:
            _polices[cle] = ImageFont.load_default(size=taille)
    return _polices[cle]


class Page:
    """Écrit de haut en bas ; ajoute une page quand la place manque."""

    def __init__(self):
        self.pages = []
        self.nouvelle()

    def nouvelle(self):
        self.image = Image.new("RGB", (LARGEUR, HAUTEUR), "white")
        self.d = ImageDraw.Draw(self.image)
        self.pages.append(self.image)
        self.y = MARGE

    def place(self, hauteur):
        if self.y + hauteur > HAUTEUR - MARGE:
            self.nouvelle()

    def texte(self, x, texte, taille=30, gras=False, couleur=NOIR, aligne="gauche", y=None):
        f = police(taille, gras)
        if aligne == "droite":
            x -= self.d.textlength(texte, font=f)
        elif aligne == "centre":
            x -= self.d.textlength(texte, font=f) / 2
        self.d.text((x, self.y if y is None else y), texte, font=f, fill=couleur)

    def couper(self, texte, largeur, taille=30, gras=False):
        """Découpe un texte en lignes qui tiennent dans `largeur`."""
        f, lignes, ligne = police(taille, gras), [], ""
        for mot in str(texte).split():
            essai = f"{ligne} {mot}".strip()
            if self.d.textlength(essai, font=f) <= largeur or not ligne:
                ligne = essai
            else:
                lignes.append(ligne)
                ligne = mot
        return lignes + ([ligne] if ligne else [])

    def trait(self, epaisseur=2, couleur=TRAIT):
        self.d.line((MARGE, self.y, LARGEUR - MARGE, self.y), fill=couleur, width=epaisseur)

    def pdf(self):
        sortie = io.BytesIO()
        premiere, suite = self.pages[0], self.pages[1:]
        premiere.save(sortie, "PDF", resolution=DPI, save_all=True, append_images=suite, quality=90)
        return sortie.getvalue()


def facture_pdf(contexte):
    """`contexte` : celui de la page facture (_contexte_facture)."""
    vente, facture, societe = contexte["vente"], contexte["facture"], contexte["societe"]
    p = Page()
    droite = LARGEUR - MARGE

    # En-tête : société à gauche, FACTURE à droite
    p.texte(MARGE, societe["nom"], 56, gras=True, couleur=VERT)
    p.texte(droite, "FACTURE", 52, gras=True, aligne="droite")
    y0 = p.y
    p.y += 76
    for ligne in [l for l in (societe.get("adresse") or "").splitlines() if l.strip()] + (
            [f"Tél. {societe['telephone']}"] if societe.get("telephone") else []):
        p.texte(MARGE, ligne, 28, couleur=GRIS)
        p.y += 38
    yd = y0 + 72
    p.texte(droite, facture.numero_facture, 32, gras=True, aligne="droite", y=yd)
    p.texte(droite, f"du {timezone.localtime(facture.date_facture):%d/%m/%Y à %H:%M}", 28, couleur=GRIS, aligne="droite", y=yd + 44)
    if vente.statut == "ANNULEE":
        tampon, couleur = "ANNULÉE", ROUGE
    elif contexte["reste"]:
        tampon, couleur = "RESTE À PAYER", ORANGE
    else:
        tampon, couleur = "PAYÉE", (46, 125, 79)
    f = police(32, True)
    lt = p.d.textlength(tampon, font=f)
    p.d.rounded_rectangle((droite - lt - 36, yd + 96, droite, yd + 152), radius=10, outline=couleur, width=5)
    p.texte(droite - 18, tampon, 32, gras=True, couleur=couleur, aligne="droite", y=yd + 104)
    p.y = max(p.y, yd + 180) + 10
    p.trait(4, VERT)
    p.y += 30

    # Informations
    client = vente.client
    blocs = [
        ("CLIENT", [client.nom, client.telephone or ""] if client else ["Client de passage"]),
        ("VENTE", [vente.numero_vente]),
        ("DÉPÔT", [vente.depot.nom]),
        ("VENDEUR", [vente.vendeur.get_full_name()]),
    ]
    milieu = MARGE + (LARGEUR - 2 * MARGE) // 2
    for i in (0, 2):
        y = p.y
        hauteur = 0
        for j, x in ((i, MARGE), (i + 1, milieu + 20)):
            titre, lignes = blocs[j]
            p.texte(x, titre, 24, couleur=GRIS, y=y)
            for k, l in enumerate(x for x in lignes if x):
                p.texte(x, l, 30, gras=(k == 0), y=y + 36 + k * 40)
            hauteur = max(hauteur, 36 + 40 * len([x for x in lignes if x]))
        p.y = y + hauteur + 24

    # Lignes
    col_balles, col_prix, col_montant = droite - 600, droite - 300, droite
    p.y += 10
    for x, t, a in ((MARGE, "DÉSIGNATION", "gauche"), (col_balles, "BALLES", "droite"),
                    (col_prix, "PRIX / BALLE", "droite"), (col_montant, "MONTANT", "droite")):
        p.texte(x, t, 24, gras=True, couleur=GRIS, aligne=a)
    p.y += 44
    p.trait()
    p.y += 18
    largeur_designation = col_balles - 140 - MARGE
    for l in contexte["lignes"]:
        lignes_txt = p.couper(l.designation, largeur_designation, 30)
        hauteur = 40 * len(lignes_txt) + 40
        p.place(hauteur + 20)
        y = p.y
        for k, t in enumerate(lignes_txt):
            p.texte(MARGE, t, 30, y=y + 40 * k)
        p.texte(MARGE, f"Lot {l.lot.code_lot}" if l.lot_id else "", 24, couleur=GRIS, y=y + 40 * len(lignes_txt))
        p.texte(col_balles, str(l.nombre_balles), 30, aligne="droite", y=y)
        p.texte(col_prix, format_fcfa(l.prix_unitaire), 30, aligne="droite", y=y)
        p.texte(col_montant, format_fcfa(l.montant_ligne), 30, aligne="droite", y=y)
        p.y = y + hauteur + 14
        p.trait(1)
        p.y += 16

    # Total
    p.place(200)
    p.texte(MARGE, "TOTAL", 36, gras=True)
    p.texte(col_balles, str(contexte["balles"]), 36, gras=True, aligne="droite")
    p.texte(col_montant, f"{format_fcfa(vente.montant_total)} FCFA", 36, gras=True, aligne="droite")
    p.y += 64
    for t in p.couper(f"Arrêtée la présente facture à la somme de : {montant_en_lettres(vente.montant_total)}.",
                      LARGEUR - 2 * MARGE, 28):
        p.texte(MARGE, t, 28)
        p.y += 38
    p.y += 20

    # Paiements et reste
    if vente.statut != "ANNULEE":
        for pa in contexte["paiements"]:
            p.place(50)
            libelle = f"Payé le {timezone.localtime(pa.date_paiement):%d/%m/%Y} · {pa.get_mode_paiement_display()}"
            if pa.reference:
                libelle += f" ({pa.reference})"
            p.texte(MARGE, libelle, 28)
            p.texte(col_montant, f"{format_fcfa(pa.montant)} FCFA", 28, aligne="droite")
            p.y += 44
        if contexte["reste"]:
            p.place(60)
            p.texte(MARGE, "Reste à payer", 32, gras=True, couleur=ROUGE)
            p.texte(col_montant, f"{format_fcfa(contexte['reste'])} FCFA", 32, gras=True, couleur=ROUGE, aligne="droite")
            p.y += 56

    # Échéancier
    if contexte["echeances"]:
        p.place(160)
        p.y += 20
        p.texte(MARGE, "ÉCHÉANCIER", 30, gras=True, couleur=VERT)
        p.y += 52
        for e in contexte["echeances"]:
            p.place(48)
            etat = "En retard" if e.en_retard else e.get_statut_display()
            p.texte(MARGE, f"N° {e.numero_echeance}", 28)
            p.texte(MARGE + 160, f"{e.date_echeance:%d/%m/%Y}", 28)
            p.texte(col_prix, f"{format_fcfa(e.montant_prevu)} FCFA", 28, aligne="droite")
            p.texte(col_montant, etat, 28, couleur=ROUGE if e.en_retard else NOIR, aligne="droite")
            p.y += 44

    lien = contexte.get("lien_public")
    if lien:
        from .facture_publique import qr_png
        qr = qr_png(lien, taille_case=8)
        cote = 260
        qr = qr.resize((cote, cote), Image.NEAREST)
        p.place(cote + 60)
        p.y += 30
        p.image.paste(qr, (MARGE, p.y))
        texte_y = p.y + cote // 2 - 50
        p.texte(MARGE + cote + 30, "Retrouvez votre facture sur votre téléphone :", 28, gras=True, y=texte_y)
        p.texte(MARGE + cote + 30, "scannez ce code avec l'appareil photo.", 28, couleur=GRIS, y=texte_y + 44)
        p.y += cote

    p.place(80)
    p.y += 40
    p.texte(LARGEUR // 2, "Merci de votre confiance.", 26, couleur=GRIS, aligne="centre")
    return p.pdf()
