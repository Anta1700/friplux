from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.http import HttpResponse
from django.urls import reverse
from django.utils.html import format_html

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
from .services import (
    creer_qr_code,
    generer_code_lot,
    marquer_envoyes_au_fournisseur,
    pdf_etiquettes,
    regenerer_qr_code,
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

    # Formulaire « Ajouter un utilisateur » : la table users exige
    # prénom, nom et rôle (NOT NULL), absents du formulaire Django standard.
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "first_name",
                    "last_name",
                    "role",
                    "depot",
                    "password1",
                    "password2",
                ),
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

# ---------- Lots et QR codes ----------

def _lien_etiquette(qr_code):
    if not qr_code or not qr_code.pk:
        return "—"
    url = reverse("core:qr_code_png", args=[qr_code.pk])
    return format_html(
        '<a href="{0}" target="_blank"><img src="{0}" style="height:160px;border:1px solid #ccc"></a><br>'
        '<a href="{0}?telecharger=1">Télécharger l\'étiquette (PNG)</a>',
        url,
    )


class QrCodesInline(admin.TabularInline):
    model = QrCodes
    extra = 0
    can_delete = False
    fields = ("code", "version", "actif", "date_generation", "date_envoi_fournisseur", "date_activation")
    readonly_fields = fields
    ordering = ("-version",)
    verbose_name_plural = "Historique des QR codes"

    def has_add_permission(self, request, obj=None):
        # Les QR codes sont créés automatiquement, jamais à la main.
        return False


@admin.register(Lots)
class LotsAdmin(admin.ModelAdmin):
    list_display = (
        "code_lot",
        "conteneur",
        "categorie_lot",
        "poids_kg",
        "prix_achat",
        "statut_logistique",
        "statut_ouverture",
        "date_reception",
        "qr_envoye",
    )

    list_filter = (
        "statut_logistique",
        "statut_ouverture",
        "categorie_lot",
        "conteneur",
    )

    search_fields = (
        "code_lot",
        "conteneur__numero_conteneur",
        "qr_codes__code",
    )

    list_select_related = ("conteneur", "categorie_lot")

    readonly_fields = (
        "code_lot",
        "etiquette_qr",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        ("Identification", {"fields": ("code_lot", "conteneur", "categorie_lot")}),
        ("Informations fournisseur", {"fields": ("poids_kg", "prix_achat", "date_creation")}),
        ("Suivi", {"fields": ("statut_logistique", "date_reception", "statut_ouverture", "date_ouverture", "notes")}),
        ("QR code", {"fields": ("etiquette_qr",)}),
        ("Dates techniques", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    inlines = (QrCodesInline,)
    actions = ("imprimer_etiquettes", "marquer_qr_envoyes", "regenerer_qr")

    @admin.display(description="Étiquette QR")
    def etiquette_qr(self, obj):
        if not obj.pk:
            return "Le code et le QR code seront générés automatiquement à l'enregistrement."
        return _lien_etiquette(obj.qr_actif)

    @admin.display(description="QR envoyé", boolean=True)
    def qr_envoye(self, obj):
        qr = obj.qr_actif
        return bool(qr and qr.date_envoi_fournisseur)

    def save_model(self, request, obj, form, change):
        # L'admin enregistre déjà dans une transaction : le verrou de
        # generer_code_lot() est donc tenu jusqu'à l'insertion du lot et de son QR.
        if not change:
            obj.code_lot = generer_code_lot()
            super().save_model(request, obj, form, change)
            creer_qr_code(obj)
        else:
            super().save_model(request, obj, form, change)

    @admin.action(description="Imprimer les étiquettes QR (PDF)")
    def imprimer_etiquettes(self, request, queryset):
        qr_codes = list(
            QrCodes.objects.filter(lot__in=queryset, actif=True)
            .select_related("lot__categorie_lot", "lot__conteneur")
            .order_by("lot__code_lot")
        )
        if not qr_codes:
            self.message_user(request, "Aucun QR code actif dans la sélection.", messages.WARNING)
            return None
        reponse = HttpResponse(pdf_etiquettes(qr_codes), content_type="application/pdf")
        reponse["Content-Disposition"] = 'attachment; filename="etiquettes_qr_friplux.pdf"'
        return reponse

    @admin.action(description="Marquer les QR comme envoyés au fournisseur")
    def marquer_qr_envoyes(self, request, queryset):
        nombre = marquer_envoyes_au_fournisseur(QrCodes.objects.filter(lot__in=queryset, actif=True))
        self.message_user(request, f"{nombre} QR code(s) marqué(s) comme envoyé(s).", messages.SUCCESS)

    @admin.action(description="Remplacer le QR code (étiquette perdue ou abîmée)")
    def regenerer_qr(self, request, queryset):
        nouveaux = [regenerer_qr_code(lot).code for lot in queryset]
        self.message_user(
            request,
            "Nouveaux QR codes : " + ", ".join(nouveaux) + ". Les anciennes étiquettes ne sont plus valables.",
            messages.WARNING,
        )


@admin.register(QrCodes)
class QrCodesAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "lot",
        "version",
        "actif",
        "date_generation",
        "date_envoi_fournisseur",
        "date_activation",
    )

    list_filter = (
        "actif",
        "version",
    )

    search_fields = (
        "code",
        "lot__code_lot",
    )

    list_select_related = ("lot",)

    fields = ("code", "lot", "version", "actif", "date_generation", "date_envoi_fournisseur", "date_activation", "etiquette")
    # Code, lot, version et état actif sont gérés uniquement par Frip'Lux
    # (création du lot, action « Remplacer le QR code »).
    readonly_fields = ("code", "lot", "version", "actif", "date_generation", "etiquette")

    @admin.display(description="Étiquette")
    def etiquette(self, obj):
        return _lien_etiquette(obj)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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