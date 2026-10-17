from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import (
    User,
    Roles,
    AffectationsPaiements,
    AuditLogs,
    CategoriesLots,
    CategoriesProduits,
    Clients,
    Conteneurs,
    Depots,
    EcheancesMoratoire,
    Factures,
    Fournisseurs,
    LignesOuverture,
    LignesTransfert,
    LignesVente,
    Lots,
    Moratoires,
    MouvementsStock,
    OuverturesLots,
    Paiements,
    QrCodes,
    Stocks,
    TransfertsStock,
    UserDepots,
    Ventes,
)


# ============================================================
# UTILISATEURS
# ============================================================

@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("username",)

    list_display = (
        "username",
        "first_name",
        "last_name",
        "role",
        "depot",
        "is_active",
        "is_staff",
        "is_superuser",
    )

    list_filter = (
        "is_active",
        "is_staff",
        "is_superuser",
        "role",
        "depot",
    )

    search_fields = (
        "username",
        "first_name",
        "last_name",
        "email",
        "phone",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "last_login",
    )

    fieldsets = (
        (
            "Informations de connexion",
            {
                "fields": (
                    "username",
                    "password",
                )
            },
        ),
        (
            "Informations personnelles",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "email",
                    "phone",
                )
            },
        ),
        (
            "Organisation Frip'Lux",
            {
                "fields": (
                    "role",
                    "depot",
                )
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                )
            },
        ),
        (
            "Dates",
            {
                "fields": (
                    "last_login",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )


@admin.register(Roles)
class RolesAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "code",
        "nom",
        "actif",
    )

    list_filter = (
        "actif",
    )

    search_fields = (
        "code",
        "nom",
        "description",
    )


# ============================================================
# ADMINISTRATION GÉNÉRALE
# ============================================================

@admin.register(Fournisseurs)
class FournisseursAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "code",
        "nom",
        "pays",
        "ville",
        "telephone",
        "email",
        "actif",
    )

    list_filter = (
        "actif",
        "pays",
    )

    search_fields = (
        "code",
        "nom",
        "pays",
        "ville",
        "telephone",
        "email",
    )
# Ajoutez ces lignes ici :
    readonly_fields = (
        "created_at",
        "updated_at",
    )

@admin.register(Clients)
class ClientsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "code_client",
        "nom",
        "telephone",
        "type_client",
        "actif",
    )

    list_filter = (
        "actif",
        "type_client",
    )

    search_fields = (
        "code_client",
        "nom",
        "telephone",
        "email",
    )
readonly_fields = (
    "created_at",
    "updated_at",
)

@admin.register(CategoriesLots)
class CategoriesLotsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "code",
        "nom",
        "actif",
    )

    list_filter = (
        "actif",
    )

    search_fields = (
        "code",
        "nom",
        "description",
    )


@admin.register(CategoriesProduits)
class CategoriesProduitsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "code",
        "nom",
        "parent",
        "actif",
    )

    list_filter = (
        "actif",
    )

    search_fields = (
        "code",
        "nom",
    )


# ============================================================
# LOGISTIQUE
# ============================================================

@admin.register(Depots)
class DepotsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "code",
        "nom",
        "responsable",
        "telephone",
        "actif",
    )

    list_filter = (
        "actif",
    )

    search_fields = (
        "code",
        "nom",
        "adresse",
        "telephone",
    )
readonly_fields = (
    "created_at",
    "updated_at",
)

@admin.register(Conteneurs)
class ConteneursAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "numero_conteneur",
        "fournisseur",
        "pays_origine",
        "statut",
        "date_arrivee_estimee",
        "date_arrivee_reelle",
    )

    list_filter = (
        "statut",
        "pays_origine",
    )

    search_fields = (
        "numero_conteneur",
        "pays_origine",
        "fournisseur__nom",
    )
readonly_fields = (
    "created_at",
    "updated_at",
)

@admin.register(Lots)
class LotsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "code_lot",
        "conteneur",
        "categorie_lot",
        "poids_kg",
        "prix_achat",
        "statut_logistique",
        "statut_ouverture",
        "date_reception",
    )

    list_filter = (
        "statut_logistique",
        "statut_ouverture",
        "categorie_lot",
    )

    search_fields = (
        "code_lot",
        "conteneur__numero_conteneur",
    )
    
readonly_fields = (
    "created_at",
    "updated_at",
)

@admin.register(QrCodes)
class QrCodesAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "code",
        "lot",
        "version",
        "date_generation",
        "date_envoi_fournisseur",
        "date_activation",
        "actif",
    )

    list_filter = (
        "actif",
        "version",
    )

    search_fields = (
        "code",
        "lot__code_lot",
    )


# ============================================================
# STOCK
# ============================================================

@admin.register(Stocks)
class StocksAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "depot",
        "categorie_produit",
        "quantite_pieces",
        "poids_kg",
        "updated_at",
    )

    list_filter = (
        "depot",
        "categorie_produit",
    )

    search_fields = (
        "depot__nom",
        "categorie_produit__nom",
    )


@admin.register(MouvementsStock)
class MouvementsStockAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "type_mouvement",
        "depot_depart",
        "depot_arrivee",
        "lot",
        "categorie_produit",
        "quantite_pieces",
        "poids_kg",
        "utilisateur",
        "date_mouvement",
        "statut",
    )

    list_filter = (
        "type_mouvement",
        "statut",
        "depot_depart",
        "depot_arrivee",
    )

    search_fields = (
        "reference_document",
        "lot__code_lot",
        "utilisateur__username",
    )


@admin.register(OuverturesLots)
class OuverturesLotsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "lot",
        "depot",
        "utilisateur",
        "date_ouverture",
        "statut",
    )

    list_filter = (
        "statut",
        "depot",
    )

    search_fields = (
        "lot__code_lot",
        "utilisateur__username",
    )


@admin.register(LignesOuverture)
class LignesOuvertureAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "ouverture",
        "categorie_produit",
        "quantite_pieces",
        "poids_kg",
    )

    list_filter = (
        "categorie_produit",
    )


# ============================================================
# TRANSFERTS
# ============================================================

@admin.register(TransfertsStock)
class TransfertsStockAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "reference_transfert",
        "depot_depart",
        "depot_arrivee",
        "utilisateur",
        "date_transfert",
        "statut",
    )

    list_filter = (
        "statut",
        "depot_depart",
        "depot_arrivee",
    )

    search_fields = (
        "reference_transfert",
        "utilisateur__username",
    )


@admin.register(LignesTransfert)
class LignesTransfertAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "transfert",
        "categorie_produit",
        "quantite_pieces",
        "poids_kg",
    )

    list_filter = (
        "categorie_produit",
    )


# ============================================================
# VENTES
# ============================================================

@admin.register(Ventes)
class VentesAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "numero_vente",
        "client",
        "depot",
        "vendeur",
        "date_vente",
        "montant_total",
        "statut",
    )

    list_filter = (
        "statut",
        "depot",
        "date_vente",
    )

    search_fields = (
        "numero_vente",
        "client__nom",
        "vendeur__username",
    )


@admin.register(LignesVente)
class LignesVenteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "vente",
        "categorie_produit",
        "designation",
        "unite_vente",
        "quantite",
        "prix_unitaire",
        "remise",
        "montant_ligne",
    )

    list_filter = (
        "unite_vente",
        "categorie_produit",
    )

    search_fields = (
        "designation",
        "vente__numero_vente",
    )


@admin.register(Paiements)
class PaiementsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "vente",
        "montant",
        "date_paiement",
        "mode_paiement",
        "statut",
        "utilisateur",
    )

    list_filter = (
        "mode_paiement",
        "statut",
        "date_paiement",
    )

    search_fields = (
        "vente__numero_vente",
        "reference",
        "utilisateur__username",
    )


# ============================================================
# FACTURATION / MORATOIRES
# ============================================================

@admin.register(Factures)
class FacturesAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "numero_facture",
        "vente",
        "date_facture",
        "montant_total",
        "statut",
    )

    list_filter = (
        "statut",
        "date_facture",
    )

    search_fields = (
        "numero_facture",
        "vente__numero_vente",
    )


@admin.register(Moratoires)
class MoratoiresAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "vente",
        "date_debut",
        "date_echeance",
        "montant_concerne",
        "type_moratoire",
        "statut",
        "autorise_par",
    )

    list_filter = (
        "type_moratoire",
        "statut",
    )

    search_fields = (
        "vente__numero_vente",
        "autorise_par__username",
    )


@admin.register(EcheancesMoratoire)
class EcheancesMoratoireAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "moratoire",
        "numero_echeance",
        "date_echeance",
        "montant_prevu",
        "statut",
    )

    list_filter = (
        "statut",
        "date_echeance",
    )


@admin.register(AffectationsPaiements)
class AffectationsPaiementsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "paiement",
        "echeance",
        "montant_affecte",
    )


# ============================================================
# UTILISATION DES DÉPÔTS
# ============================================================

@admin.register(UserDepots)
class UserDepotsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "depot",
        "date_debut",
        "date_fin",
        "actif",
    )

    list_filter = (
        "actif",
        "depot",
    )

    search_fields = (
        "user__username",
        "depot__nom",
    )


# ============================================================
# AUDIT
# ============================================================

@admin.register(AuditLogs)
class AuditLogsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "utilisateur",
        "action",
        "table_concernee",
        "objet_id",
        "date_action",
        "adresse_ip",
    )

    list_filter = (
        "action",
        "table_concernee",
        "date_action",
    )

    search_fields = (
        "utilisateur__username",
        "action",
        "table_concernee",
    )