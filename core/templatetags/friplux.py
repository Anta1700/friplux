from django import template

from ..montants import format_fcfa, montant_en_lettres

register = template.Library()


@register.filter
def fcfa(valeur):
    """{{ montant|fcfa }} -> « 47 500 FCFA »."""
    return f"{format_fcfa(valeur)}\u00a0FCFA"


@register.filter
def fcfa_nombre(valeur):
    """{{ montant|fcfa_nombre }} -> « 47 500 » (sans la devise, pour les colonnes)."""
    return format_fcfa(valeur)


@register.filter
def en_lettres(valeur):
    return montant_en_lettres(valeur)


@register.filter
def s(nombre):
    """Pluriel à la française : {{ n }} balle{{ n|s }} -> « 0 balle », « 1 balle », « 2 balles »."""
    try:
        return "s" if abs(float(nombre)) >= 2 else ""
    except (TypeError, ValueError):
        return ""
