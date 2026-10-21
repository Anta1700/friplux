"""
Mots de passe des employés.

- L'administrateur donne un mot de passe provisoire (à la création du compte ou en cas d'oubli) :
  le compte est marqué « doit choisir son mot de passe ».
- À la connexion suivante, l'employé est conduit vers « Choisir mon mot de passe » et ne peut
  rien faire d'autre tant qu'il ne l'a pas changé. Ainsi, l'administrateur ne connaît jamais
  le mot de passe définitif.
"""
import secrets

from django.shortcuts import redirect
from django.urls import reverse

# Pas de lettres ou chiffres faciles à confondre à l'oral ou à l'écrit (0/O, 1/l/I…).
_LETTRES = "abcdefghjkmnpqrstuvwxyz"
_CHIFFRES = "23456789"


def generer_mot_de_passe_provisoire():
    """Facile à dicter ou à écrire sur un papier : « kimo-4827 »."""
    mot = "".join(secrets.choice(_LETTRES) for _ in range(4))
    nombre = "".join(secrets.choice(_CHIFFRES) for _ in range(4))
    return f"{mot}-{nombre}"


def donner_mot_de_passe_provisoire(utilisateur, mot_de_passe=None):
    mot_de_passe = mot_de_passe or generer_mot_de_passe_provisoire()
    utilisateur.set_password(mot_de_passe)
    utilisateur.doit_changer_mot_de_passe = True
    utilisateur.save()
    return mot_de_passe


class ChangementMotDePasseObligatoire:
    """Tant que le mot de passe est provisoire, toute page renvoie vers « Choisir mon mot de passe »."""

    PREFIXES_LIBRES = ("/static/", "/deconnexion/", "/admin/logout/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and getattr(user, "doit_changer_mot_de_passe", False):
            page = reverse("core:mot_de_passe")
            if request.path != page and not request.path.startswith(self.PREFIXES_LIBRES):
                return redirect(page)
        return self.get_response(request)
