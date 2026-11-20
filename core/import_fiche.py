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

Le poids peut manquer (il n'est pas inventé : le lot reste sans poids).
Colonnes facultatives :
- « Traduction » : libellé en français, imprimé sous le libellé d'origine sur l'étiquette ;
- « EUR / kg » : sans cette colonne (fiche sans prix), le prix d'achat est laissé à 0.
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
    poids_total: str          # Decimal sérialisé (stocké en session) ; "" si la fiche ne donne pas le poids
    prix_kg: str
    alertes: list = field(default_factory=list)
    traduction: str = ""
    qualite_fiche: str = ""   # code Frip'Lux de la qualité écrite sur la fiche (colonne « Qualité » : A, B…)

    def poids(self):
        return Decimal(self.poids_total) if self.poids_total not in ("", None) else None

    def poids_moyen_balle(self):
        poids = self.poids()
        return (poids / self.nombre_balles).quantize(CENTIME, ROUND_HALF_UP) if poids else None

    def prix_total(self):
        return prix_balle(self.poids(), self.prix_kg)

    def to_dict(self):
        return asdict(self)


@dataclass
class Fiche:
    date: str = ""
    numero_conteneur: str = ""
    lignes: list = field(default_factory=list)
    lignes_ignorees: list = field(default_factory=list)
    remarques: list = field(default_factory=list)

    @property
    def nombre_balles(self):
        return sum(l.nombre_balles for l in self.lignes)

    @property
    def poids_total(self):
        return sum((l.poids() or Decimal("0") for l in self.lignes), Decimal("0"))


def _decimal(valeur):
    if valeur is None or valeur == "":
        return None
    try:
        return Decimal(str(valeur).replace(",", ".").strip())
    except InvalidOperation:
        return None


def _poids(valeur):
    """43, « 43 », « 13 kg », « 13,5kg » -> Decimal ; sinon None."""
    if valeur is None or valeur == "":
        return None
    if isinstance(valeur, (int, float, Decimal)):
        return Decimal(str(valeur))
    trouve = re.search(r"\d+(?:[.,]\d+)?", str(valeur))
    return Decimal(trouve.group().replace(",", ".")) if trouve else None


def _cle(valeur):
    """Titre de colonne réduit à ses lettres et chiffres : « Kg.balla » -> « kgballa », « N° de balles » -> « ndeballes »."""
    return re.sub(r"[^a-z0-9]", "", normaliser(valeur))


# Titres de colonnes reconnus (fiches en français, en italien ou en anglais).
_TITRES_CODE = {"code", "codearticle", "cod", "codice", "ref", "reference", "refarticle"}
_DEBUT_ARTICLE = ("article", "articolo", "designation", "libelle", "descrizione", "description", "produit", "marchandise")
_TITRES_BALLES = {"nombre", "nb", "nbr", "nrbls", "nbls", "bls", "colis", "quantite", "qte", "qty", "nballes", "nbballes"}
_TITRES_KG_TOTAL = {"kg", "kgs", "poids", "poidstotal", "kgtotal", "totalkg", "peso", "pesototale", "poidskg"}
_DEBUT_POIDS = ("kg", "poids", "peso")
_DEBUT_QUALITE = ("qualit", "quality", "grade")

# Qualité écrite sur la fiche -> code Frip'Lux (une lettre seule : A = premier choix, B = deuxième choix).
_QUALITES_FICHE = {"a": "PREMIER_CHOIX", "1": "PREMIER_CHOIX", "b": "DEUXIEME_CHOIX", "2": "DEUXIEME_CHOIX"}


def _qualite_fiche(valeur):
    texte = normaliser(valeur)
    if not texte:
        return ""
    if texte in _QUALITES_FICHE:
        return _QUALITES_FICHE[texte]
    for mot, code in (("creme", "CREME"), ("destock", "DESTOCKAGE"), ("chif", "CHIFFONS"),
                      ("premier", "PREMIER_CHOIX"), ("1er", "PREMIER_CHOIX"), ("deuxieme", "DEUXIEME_CHOIX"), ("2e", "DEUXIEME_CHOIX")):
        if mot in texte:
            return code
    return ""   # ex. « C » : pas de qualité C dans Frip'Lux, on laisse vide


def _reperer_colonnes(valeurs):
    """Repère la ligne des titres. Indispensables : l'article et le nombre de balles ; le reste est facultatif."""
    cles = [_cle(v) for v in valeurs]

    def trouve(test, sauf=()):
        return next((i for i, c in enumerate(cles) if c and i not in sauf and test(c)), None)

    est_poids = lambda c: c.startswith(_DEBUT_POIDS)
    balles = trouve(lambda c: not est_poids(c) and ("balle" in c or "balla" in c or c in _TITRES_BALLES or c.startswith("nombre")))
    if balles is None:
        return None
    libelle = trouve(lambda c: c == "art" or c.startswith(_DEBUT_ARTICLE))
    if libelle is None:
        # Colonne des articles sans titre, à gauche du nombre de balles (ex. fiche « INVERNALE »).
        libelle = next((i for i in range(balles) if not cles[i]), None)
    if libelle is None:
        return None
    kg = trouve(lambda c: c in _TITRES_KG_TOTAL)
    kg_balle = None if kg is not None else trouve(lambda c: est_poids(c) and ("ball" in c or "unit" in c))
    return {
        "code": trouve(lambda c: c in _TITRES_CODE),
        "libelle": libelle,
        "balles": balles,
        "kg": kg,
        "kg_balle": kg_balle,
        "qualite": trouve(lambda c: c.startswith(_DEBUT_QUALITE)),
        "prix_kg": next((i for i, v in enumerate(valeurs)
                         if str(v or "").replace(" ", "").lower() in ("€/kg", "eur/kg", "prix/kg", "prixaukg")), None),
        "traduction": trouve(lambda c: c.startswith(("traduction", "francais"))),
    }


def _code_genere(libelle, qualite_brute, deja):
    """Fiche sans code article : code tiré du libellé (même article = même code d'une fiche à l'autre)."""
    base = re.sub(r"[^A-Z0-9]+", "-", normaliser(libelle).upper()).strip("-")[:44] or "ARTICLE"
    lettre = normaliser(qualite_brute).upper()
    if len(lettre) == 1 and lettre.isalnum() and not base.endswith(f"-{lettre}"):
        base += f"-{lettre}"
    code, n = base, 2
    while code in deja:
        code, n = f"{base}-{n}", n + 1
    deja.add(code)
    return code


def prix_balle(poids, prix_kg):
    if not poids:
        return Decimal("0.00")
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
    codes_vus = set()
    poids_ambigus = []   # (ligne, poids lu) quand la colonne « Kg » peut être un poids total ou par balle

    for index, valeurs in enumerate(lignes, start=1):
        valeurs = list(valeurs) + [None] * 8
        textes = [normaliser(v) for v in valeurs]

        if colonnes is None:
            if textes[0] == "date" and valeurs[1] is not None:
                fiche.date = str(valeurs[1]).strip()
            elif textes[0] == "conteneur" and valeurs[1] is not None:
                fiche.numero_conteneur = str(valeurs[1]).strip()
            else:
                colonnes = _reperer_colonnes(valeurs)
            continue

        if any(t.startswith("total") for t in textes if t):
            break
        if all(v is None or str(v).strip() == "" for v in valeurs):
            continue

        val = lambda nom: valeurs[colonnes[nom]] if colonnes[nom] is not None else None
        libelle = str(val("libelle") or "").strip()
        code = str(val("code") or "").strip()
        balles = _decimal(val("balles"))
        qualite_brute = val("qualite")

        if not libelle and not code:
            if balles is not None:   # sous-total sous un groupe d'articles
                fiche.lignes_ignorees.append({"numero_ligne": index, "texte": str(balles), "raison": "sous-total"})
            continue

        # Ligne de section : un texte seul
        if libelle and balles is None and not any(
            v not in (None, "") for i, v in enumerate(valeurs[:8]) if i != colonnes["libelle"]
        ):
            section = libelle
            continue

        if not balles:
            fiche.lignes_ignorees.append(
                {"numero_ligne": index, "texte": libelle or code, "raison": "pas de nombre de balles"}
            )
            continue

        if colonnes["kg_balle"] is not None:
            par_balle = _poids(val("kg_balle"))
            kg = par_balle * balles if par_balle else None
        else:
            kg = _poids(val("kg"))
        prix_kg = _decimal(val("prix_kg")) if colonnes["prix_kg"] is not None else Decimal("0")

        ligne = LigneFiche(
            numero_ligne=index,
            section=section,
            code=code or _code_genere(libelle, qualite_brute, codes_vus),
            libelle=libelle,
            nombre_balles=int(balles),
            poids_total=str(kg) if kg else "",
            prix_kg=str(prix_kg or 0),
            traduction=" ".join(str(val("traduction") or "").split()),
            qualite_fiche=_qualite_fiche(qualite_brute),
        )
        if balles != int(balles) or balles < 1:
            ligne.alertes.append("nombre de balles invalide")
        if kg is not None and kg < 0:
            ligne.alertes.append("poids négatif")
        if prix_kg is None:
            ligne.alertes.append("prix au kg manquant")
        if colonnes["kg_balle"] is None and kg:
            poids_ambigus.append((ligne, kg))
        fiche.lignes.append(ligne)

    # Colonne « Kg » : poids total de la ligne, ou poids d'UNE balle ? (fiche fournisseur : « Kg. » = 43 pour 50 balles)
    # Une balle pèse au moins une dizaine de kilos : si, sur les lignes de plusieurs balles, le poids lu
    # divisé par le nombre de balles est presque toujours sous 10 kg, c'est un poids par balle.
    plusieurs = [(l, kg) for l, kg in poids_ambigus if l.nombre_balles >= 2]
    if plusieurs and sum(1 for l, kg in plusieurs if kg / l.nombre_balles < 10) > len(plusieurs) / 2:
        for ligne, kg in poids_ambigus:
            ligne.poids_total = str(kg * ligne.nombre_balles)
        fiche.remarques.append("La colonne des kilos donne le poids d'une balle : il a été multiplié par le nombre de balles.")

    if colonnes is None:
        raise ErreurFiche(
            "Ligne de titres introuvable : il faut au moins une colonne pour l'article (ex. « Article ») "
            "et une pour le nombre de balles (ex. « Nombre », « N° de balles »)."
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
    (("casquette", "bonnet"), "ACCESSOIRES_CASQUETTES"),
    (("foulard", "echarpe"), "ACCESSOIRES_FOULARDS"),
    (("cuir",), "ACCESSOIRES_CUIR"),
)
REGLES_TAPISSERIE = (
    (("rideau",), "TAPISSERIE_RIDEAUX"),
    (("ameublement",), "TAPISSERIE_TISSUS"),
    (("serviette",), "TAPISSERIE_SERVIETTES"),
    (("drap",), "TAPISSERIE_DRAPS"),
    (("garnissage", "coussin"), "TAPISSERIE_GARNISSAGE"),
    (("tapisseri", "linge de maison", "couverture"), "TAPISSERIE_ASSORTIMENT"),   # avant « tapis » (contenu dans « tapisserie »)
    (("tapis", "descente de lit"), "TAPISSERIE_TAPIS"),
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


# Reconnus sans sous-catégorie précise : la catégorie est proposée, la sous-catégorie reste à choisir.
ACCESSOIRES_SANS_DETAIL = ("gant", "jouet", "mouchoir")
VETEMENTS_MIXTES_SANS_DETAIL = ("blouson", "pull", "sweat", "maille", "gilet")


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
    texte = normaliser(getattr(ligne, "traduction", "") or ligne.libelle)
    section = normaliser(ligne.section)

    qualite = getattr(ligne, "qualite_fiche", "") or next((q for mot, q in QUALITE_PAR_SECTION if mot in section), None)
    # « Chaussures d'été, qualité B » : la qualité écrite dans l'article l'emporte sur la section.
    if "qualite b" in texte:
        qualite = "DEUXIEME_CHOIX"
    elif "qualite c" in texte:
        qualite = None
    elif "qualite a" in texte:
        qualite = "PREMIER_CHOIX"
    if "creme" in texte:
        qualite = "CREME"
    if "chiffon" in texte or "chifon" in texte:
        qualite = "CHIFFONS"

    # Lignes vendues en lot sans détail : déstockage, chiffons, crème.
    if qualite in ("DESTOCKAGE", "CHIFFONS", "CREME"):
        if "tapisserie" in texte:
            return "TAPISSERIE", "TAPISSERIE_ASSORTIMENT", qualite
        return "MIXTE", "MIXTE_ASSORTIMENT", qualite

    sous_cat = _appliquer(REGLES_ACCESSOIRES, texte)
    if sous_cat:
        return "ACCESSOIRES", sous_cat, qualite
    if any(m in texte for m in ACCESSOIRES_SANS_DETAIL):
        return "ACCESSOIRES", None, qualite
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
    if femme:
        return "FEMME", None, qualite
    if any(m in texte for m in VETEMENTS_MIXTES_SANS_DETAIL):
        return "MIXTE", None, qualite
    return None, None, qualite
