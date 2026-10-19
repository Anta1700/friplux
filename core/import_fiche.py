"""
Import des fiches de commande fournisseur (Excel).

Format attendu (fiche SILTEX) :
- en-tête : lignes « DATE » et « CONTENEUR » (colonne A = libellé, colonne B = valeur) ;
- une ligne de titres contenant « Code », « Article », « N° de balles », « Kg », « EUR / kg » ;
- des lignes de section sans code (« QUALITÉ A », « DESTOCKAGE »…) ;
- une ligne par article : code, libellé, nombre de balles, kg total, prix au kg ;
- la lecture s'arrête à « TOTAL ».

Une ligne d'article donne UN lot (un code, un QR code) regroupant ses N balles :
poids du lot = kg de la ligne, prix du lot = kg × prix au kg.
"""
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import openpyxl

CENTIME = Decimal("0.01")


class ErreurFiche(Exception):
    pass


def normaliser(texte):
    texte = unicodedata.normalize("NFKD", str(texte or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = texte.replace("’", "'")
    return re.sub(r"\s+", " ", texte).strip().lower()


def normaliser_numero_conteneur(numero):
    """« TIIU418469 9 » et « TIIU4184699 » désignent le même conteneur."""
    return re.sub(r"[^A-Z0-9]", "", str(numero or "").upper())


@dataclass
class LigneFiche:
    numero_ligne: int
    section: str
    code: str
    libelle: str
    nombre_balles: int
    poids_total: str          # Decimal sérialisé (stocké en session)
    prix_kg: str
    alertes: list = field(default_factory=list)

    def poids_moyen_balle(self):
        return (Decimal(self.poids_total) / self.nombre_balles).quantize(CENTIME, ROUND_HALF_UP)

    def prix_total(self):
        return prix_balle(Decimal(self.poids_total), self.prix_kg)

    def to_dict(self):
        return asdict(self)


@dataclass
class Fiche:
    date: str = ""
    numero_conteneur: str = ""
    lignes: list = field(default_factory=list)
    lignes_ignorees: list = field(default_factory=list)

    @property
    def nombre_balles(self):
        return sum(l.nombre_balles for l in self.lignes)

    @property
    def poids_total(self):
        return sum((Decimal(l.poids_total) for l in self.lignes), Decimal("0"))


def _decimal(valeur):
    if valeur is None or valeur == "":
        return None
    try:
        return Decimal(str(valeur).replace(",", ".").strip())
    except InvalidOperation:
        return None


def prix_balle(poids, prix_kg):
    return (poids * Decimal(prix_kg)).quantize(CENTIME, ROUND_HALF_UP)


def lire_fiche(fichier):
    """Lit une fiche Excel et retourne un objet Fiche. Lève ErreurFiche si le format n'est pas reconnu."""
    try:
        classeur = openpyxl.load_workbook(fichier, data_only=True, read_only=True)
    except Exception as erreur:
        raise ErreurFiche(f"Le fichier n'est pas un classeur Excel (.xlsx) lisible : {erreur}") from erreur

    feuille = classeur.worksheets[0]
    lignes = list(feuille.iter_rows(values_only=True))
    classeur.close()

    fiche = Fiche()
    colonnes = None
    section = ""

    for index, valeurs in enumerate(lignes, start=1):
        valeurs = list(valeurs) + [None] * 8
        textes = [normaliser(v) for v in valeurs]

        if colonnes is None:
            if textes[0] == "date" and valeurs[1] is not None:
                fiche.date = str(valeurs[1]).strip()
            elif textes[0] == "conteneur" and valeurs[1] is not None:
                fiche.numero_conteneur = str(valeurs[1]).strip()
            elif "code" in textes and "kg" in textes:
                colonnes = {
                    "code": textes.index("code"),
                    "libelle": next(i for i, t in enumerate(textes) if t.startswith("article")),
                    "balles": next(i for i, t in enumerate(textes) if "balle" in t),
                    "kg": textes.index("kg"),
                    "prix_kg": next(i for i, t in enumerate(textes) if t.replace(" ", "") in ("eur/kg", "€/kg")),
                }
            continue

        if any(t.startswith("total") for t in textes if t):
            break

        code = valeurs[colonnes["code"]]
        libelle = valeurs[colonnes["libelle"]]
        balles = _decimal(valeurs[colonnes["balles"]])
        kg = _decimal(valeurs[colonnes["kg"]])
        prix_kg = _decimal(valeurs[colonnes["prix_kg"]])

        if all(v is None for v in valeurs[:6]):
            continue

        # Ligne de section : un texte, ni code ni balles
        if code is None and libelle and balles is None and kg is None:
            if not any(v is not None for i, v in enumerate(valeurs[:6]) if i != colonnes["libelle"]):
                section = str(libelle).strip()
                continue

        if not balles:
            fiche.lignes_ignorees.append(
                {"numero_ligne": index, "texte": str(libelle or code or "").strip(), "raison": "pas de nombre de balles"}
            )
            continue

        ligne = LigneFiche(
            numero_ligne=index,
            section=section,
            code=str(code).strip() if code is not None else "",
            libelle=str(libelle or "").strip(),
            nombre_balles=int(balles),
            poids_total=str(kg or 0),
            prix_kg=str(prix_kg or 0),
        )
        if not ligne.code:
            ligne.alertes.append("code article manquant")
        if balles != int(balles) or balles < 1:
            ligne.alertes.append("nombre de balles invalide")
        if not kg or kg <= 0:
            ligne.alertes.append("poids manquant")
        if prix_kg is None:
            ligne.alertes.append("prix au kg manquant")
        fiche.lignes.append(ligne)

    if colonnes is None:
        raise ErreurFiche(
            "Ligne de titres introuvable (colonnes « Code », « Article », « N° de balles », « Kg », « EUR / kg »)."
        )
    if not fiche.lignes:
        raise ErreurFiche("Aucune ligne d'article trouvée dans la fiche.")
    return fiche


# ----------------------------------------------------------------------
# Classement proposé pour une référence encore inconnue.
# C'est une proposition : l'utilisateur la vérifie dans l'aperçu avant import,
# puis elle est mémorisée dans le catalogue des références fournisseurs.
# ----------------------------------------------------------------------

QUALITE_PAR_SECTION = (
    ("qualite a", "PREMIER_CHOIX"),
    ("qualite b", "DEUXIEME_CHOIX"),
    ("destockage", "DESTOCKAGE"),
    ("chiffon", "CHIFFONS"),
    ("chaussures", "PREMIER_CHOIX"),
)

# (mots-clés, code de la sous-catégorie) : le premier qui correspond l'emporte.
REGLES_ACCESSOIRES = (
    (("chaussure",), "ACCESSOIRES_CHAUSSURES"),
    (("sac",), "ACCESSOIRES_SACS"),
    (("ceinture",), "ACCESSOIRES_CEINTURES"),
    (("casquette",), "ACCESSOIRES_CASQUETTES"),
    (("foulard", "echarpe"), "ACCESSOIRES_FOULARDS"),
    (("cuir",), "ACCESSOIRES_CUIR"),
)
REGLES_TAPISSERIE = (
    (("rideau",), "TAPISSERIE_RIDEAUX"),
    (("ameublement",), "TAPISSERIE_TISSUS"),
    (("serviette",), "TAPISSERIE_SERVIETTES"),
    (("drap",), "TAPISSERIE_DRAPS"),
    (("tapis", "descente de lit"), "TAPISSERIE_TAPIS"),
    (("garnissage", "coussin"), "TAPISSERIE_GARNISSAGE"),
    (("tapisserie",), "TAPISSERIE_ASSORTIMENT"),
)
REGLES_BEBE = (
    (("jean",), "BEBE_JEANS"),
    (("survetement",), "BEBE_SURVETEMENTS"),
    (("pantalon",), "BEBE_PANTALONS"),
    (("garcon",), "BEBE_GARCON"),
    (("",), "BEBE_VETEMENTS"),
)
REGLES_MIXTE = (
    (("veste en jean", "vestes en jean"), "MIXTE_VESTES_JEAN"),
    (("sous-vetement",), "MIXTE_SOUS_VETEMENTS"),
    (("maillot",), "MIXTE_MAILLOTS"),
    (("sport",), "MIXTE_SPORT"),
    (("survetement",), "MIXTE_SURVETEMENTS"),
    (("impermeable",), "MIXTE_IMPERMEABLES"),
    (("nuit", "pyjama", "peignoir"), "MIXTE_NUIT"),
    (("chaussette",), "MIXTE_CHAUSSETTES"),
    (("flanelle",), "MIXTE_CHEMISES_FLANELLE"),
    (("travail",), "MIXTE_TRAVAIL"),
    (("t-shirt", "tshirt"), "MIXTE_TSHIRTS"),
    (("pantalon",), "MIXTE_PANTALONS"),
    (("jean",), "MIXTE_JEANS"),
)
REGLES_FEMME = (
    (("robe",), "FEMME_ROBES"),
    (("jupe",), "FEMME_JUPES"),
    (("chemisier", "blouse"), "FEMME_CHEMISES"),
    (("legging",), "FEMME_LEGGINGS"),
    (("soutien",), "FEMME_LINGERIE"),
    (("sexy", "tendance"), "FEMME_TENDANCE"),
    (("jean",), "FEMME_JEANS"),
    (("pantalon",), "FEMME_PANTALONS"),
    (("polo",), "FEMME_POLOS"),
    (("veste",), "FEMME_VESTES"),
)
REGLES_HOMME = (
    (("chemise",), "HOMME_CHEMISES"),
    (("ensemble",), "HOMME_ENSEMBLES"),
    (("short",), "HOMME_SHORTS"),
    (("jean",), "HOMME_JEANS"),
    (("pantalon",), "HOMME_PANTALONS"),
    (("polo",), "HOMME_POLOS"),
    (("veste",), "HOMME_VESTES"),
    (("t-shirt", "tshirt"), "HOMME_TSHIRTS"),
)


def _appliquer(regles, texte):
    for mots, code in regles:
        if any(m in texte for m in mots):
            return code
    return None


def proposer_classement(ligne):
    """
    Retourne (code catégorie, code sous-catégorie, code qualité) proposés pour une ligne,
    chaque élément pouvant être None si rien de fiable n'est trouvé.
    """
    texte = normaliser(ligne.libelle)
    section = normaliser(ligne.section)

    qualite = next((q for mot, q in QUALITE_PAR_SECTION if mot in section), None)
    if "creme" in texte:
        qualite = "CREME"

    # Lignes vendues en lot sans détail : déstockage, chiffons, crème.
    if qualite in ("DESTOCKAGE", "CHIFFONS", "CREME"):
        if "tapisserie" in texte:
            return "TAPISSERIE", "TAPISSERIE_ASSORTIMENT", qualite
        return "MIXTE", "MIXTE_ASSORTIMENT", qualite

    sous_cat = _appliquer(REGLES_ACCESSOIRES, texte)
    if sous_cat:
        return "ACCESSOIRES", sous_cat, qualite
    sous_cat = _appliquer(REGLES_TAPISSERIE, texte)
    if sous_cat:
        return "TAPISSERIE", sous_cat, qualite

    homme = "homme" in texte
    femme = "femme" in texte
    if any(m in texte for m in ("bebe", "enfant", "garcon")):
        return "BEBE", _appliquer(REGLES_BEBE, texte), qualite
    if (homme and femme) or not (homme or femme):
        sous_cat = _appliquer(REGLES_MIXTE, texte)
        if sous_cat:
            return "MIXTE", sous_cat, qualite
    if femme or not homme:
        sous_cat = _appliquer(REGLES_FEMME, texte)
        if sous_cat:
            return "FEMME", sous_cat, qualite
    if homme:
        sous_cat = _appliquer(REGLES_HOMME, texte)
        return "HOMME", sous_cat, qualite
    return None, None, qualite
