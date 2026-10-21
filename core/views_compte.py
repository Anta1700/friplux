"""Compte de l'employé : choisir / changer son mot de passe."""
from django import forms
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.shortcuts import redirect, render


class _DifferentDuProvisoire:
    def clean_new_password1(self):
        nouveau = self.cleaned_data.get("new_password1")
        if nouveau and self.user.check_password(nouveau):
            raise forms.ValidationError("Choisissez un mot de passe différent de l'ancien.")
        return nouveau


class ChoixMotDePasse(_DifferentDuProvisoire, SetPasswordForm):
    """Première connexion : l'employé vient de taper le provisoire, on ne le redemande pas."""


class ChangementMotDePasse(_DifferentDuProvisoire, PasswordChangeForm):
    """Changement volontaire : l'ancien mot de passe est demandé (téléphone prêté, oublié ouvert…)."""


@login_required
def mot_de_passe(request):
    provisoire = request.user.doit_changer_mot_de_passe
    Formulaire = ChoixMotDePasse if provisoire else ChangementMotDePasse
    formulaire = Formulaire(request.user, request.POST or None)
    for champ in formulaire.fields.values():
        champ.help_text = ""
    if request.method == "POST" and formulaire.is_valid():
        user = formulaire.save(commit=False)
        user.doit_changer_mot_de_passe = False
        user.save()
        update_session_auth_hash(request, user)   # reste connecté après le changement
        messages.success(request, "✓ Votre mot de passe est enregistré. Retenez-le bien.")
        return redirect("core:scanner")
    return render(request, "core/mot_de_passe.html", {"formulaire": formulaire, "provisoire": provisoire})
