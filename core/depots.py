"""
Affectation des utilisateurs aux dépôts.

Règle : on ne renseigne QUE le champ « Dépôt » de la fiche utilisateur (users.depot_id).
La table user_depots devient l'historique des affectations, tenu automatiquement :
- l'ancienne affectation est clôturée (actif = faux, date de fin = aujourd'hui) ;
- la nouvelle est ouverte (actif = vrai, date de début = aujourd'hui), ou réactivée
  si la personne revient dans un dépôt où elle a déjà travaillé.
"""
import logging

from django.db import DatabaseError, transaction
from django.utils import timezone

from .models import UserDepots

journal = logging.getLogger(__name__)


def synchroniser_affectation(utilisateur):
    """
    Met l'historique user_depots en accord avec utilisateur.depot.
    Retourne True si tout s'est bien passé ; en cas de refus de la base, l'utilisateur
    reste enregistré et False est retourné (l'historique pourra être corrigé ensuite).
    """
    aujourd_hui = timezone.localdate()
    try:
        with transaction.atomic():
            anciennes = UserDepots.objects.filter(user=utilisateur, actif=True)
            if utilisateur.depot_id:
                anciennes = anciennes.exclude(depot_id=utilisateur.depot_id)
            for affectation in anciennes:
                affectation.actif = False
                affectation.date_fin = max(aujourd_hui, affectation.date_debut)
                affectation.save(update_fields=["actif", "date_fin"])

            if utilisateur.depot_id:
                affectation = UserDepots.objects.filter(user=utilisateur, depot_id=utilisateur.depot_id).first()
                if affectation is None:
                    UserDepots.objects.create(
                        user=utilisateur, depot_id=utilisateur.depot_id, date_debut=aujourd_hui, actif=True
                    )
                elif not affectation.actif or affectation.date_fin:
                    affectation.actif = True
                    affectation.date_fin = None
                    affectation.save(update_fields=["actif", "date_fin"])
        return True
    except DatabaseError:
        journal.exception("Historique des dépôts non mis à jour pour %s", utilisateur)
        return False
