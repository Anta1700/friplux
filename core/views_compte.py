"""Compte de l'employé : choisir / changer son mot de passe."""
from django import forms
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .comptes import donner_mot_de_passe_provisoire
from .models import AuditLogs, User


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


# ------------------------------------------------------------------
# Super-administrateur : mot de passe oublié d'un employé
# ------------------------------------------------------------------

def _super_admin_ou_403(request):
    if not request.user.is_superuser:
        raise PermissionDenied


@login_required
def comptes(request):
    """Liste des employés ; un bouton par personne pour donner un mot de passe provisoire."""
    _super_admin_ou_403(request)
    recherche = request.GET.get("q", "").strip()
    employes = User.objects.filter(is_active=True).select_related("depot", "role").order_by("first_name", "last_name")
    if recherche:
        employes = employes.filter(
            Q(first_name__icontains=recherche) | Q(last_name__icontains=recherche) | Q(username__icontains=recherche)
        )
    return render(request, "core/comptes.html", {"employes": employes, "recherche": recherche})


@login_required
@require_POST
def compte_mot_de_passe_provisoire(request, pk):
    _super_admin_ou_403(request)
    employe = get_object_or_404(User, pk=pk, is_active=True)
    if employe.pk == request.user.pk:
        messages.error(request, "Pour votre propre compte, utilisez « Changer mon mot de passe ».")
        return redirect("core:comptes")
    mot = donner_mot_de_passe_provisoire(employe)
    AuditLogs.objects.create(
        utilisateur=request.user, action="MOT_DE_PASSE_PROVISOIRE", table_concernee="users", objet_id=employe.pk,
        date_action=timezone.now(), nouvelle_valeur={"pour": employe.username},   # jamais le mot de passe lui-même
    )
    return render(request, "core/compte_provisoire.html", {"employe": employe, "mot": mot})
