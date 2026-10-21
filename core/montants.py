"""Montants en FCFA : affichage (47 500) et écriture en lettres pour les factures."""
from decimal import ROUND_HALF_UP, Decimal

_UNITES = (
    "zéro un deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze seize "
    "dix-sept dix-huit dix-neuf"
).split()
_DIZAINES = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante", 8: "quatre-vingt"}


def entier_fcfa(valeur):
    """Le FCFA n'a pas de centimes : arrondi au franc."""
    return int(Decimal(valeur or 0).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_fcfa(valeur):
    """47500 -> « 47 500 » (espace insécable fine entre les milliers)."""
    return f"{entier_fcfa(valeur):,}".replace(",", "\u202f")


def _moins_de_cent(n):
    if n < 20:
        return _UNITES[n]
    d, u = divmod(n, 10)
    if d in (7, 9):                      # 70-79 : soixante-dix… ; 90-99 : quatre-vingt-dix…
        base, reste = _DIZAINES[d - 1], 10 + u
        lien = " et " if (d == 7 and u == 1) else "-"
        return base + lien + _UNITES[reste]
    if u == 0:
        return _DIZAINES[d] + ("s" if d == 8 else "")
    lien = " et " if (u == 1 and d != 8) else "-"
    return _DIZAINES[d] + lien + _UNITES[u]


def _moins_de_mille(n, final=True):
    c, r = divmod(n, 100)
    morceaux = []
    if c:
        if c == 1:
            morceaux.append("cent")
        else:
            # « deux cents » mais « deux cent un » et « deux cent mille »
            morceaux.append(_UNITES[c] + " cent" + ("s" if r == 0 and final else ""))
    if r:
        texte = _moins_de_cent(r)
        if not final and texte.endswith("quatre-vingts"):
            texte = texte[:-1]            # « quatre-vingt mille »
        morceaux.append(texte)
    return " ".join(morceaux)


def en_lettres(n):
    """Nombre entier en toutes lettres (orthographe traditionnelle) : 47500 -> « quarante-sept mille cinq cents »."""
    n = int(n)
    if n == 0:
        return "zéro"
    if n < 0:
        return "moins " + en_lettres(-n)
    morceaux = []
    for valeur, singulier, pluriel in ((10**9, "milliard", "milliards"), (10**6, "million", "millions")):
        q, n = divmod(n, valeur)
        if q:
            morceaux.append(f"{en_lettres(q)} {singulier if q == 1 else pluriel}")
    q, n = divmod(n, 1000)
    if q:
        morceaux.append("mille" if q == 1 else _moins_de_mille(q, final=False) + " mille")
    if n:
        morceaux.append(_moins_de_mille(n))
    return " ".join(morceaux)


def montant_en_lettres(valeur):
    """« Quarante-sept mille cinq cents francs CFA »."""
    texte = en_lettres(entier_fcfa(valeur))
    return f"{texte[0].upper()}{texte[1:]} francs CFA"
