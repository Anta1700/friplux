from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from functools import partial

from django.db.models import Exists, OuterRef
from django.http import HttpResponse
from django.urls import path, reverse
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
    Qualites,
    ReferencesFournisseurs,
    ScansLots,
)
from .admin_import import vue_apercu, vue_import
from .comptes import donner_mot_de_passe_provisoire
from .stock import progression
from .montants import format_fcfa
from .ventes import ErreurVente, annuler_vente, reste_a_payer
from .depots import synchroniser_affectation
from .services import (
    creer_qr_code,
    generer_code_lot,
    marquer_envoyes_au_fournisseur,
    RELATIONS_ETIQUETTE,
    pdf_etiquettes,
    regenerer_qr_code,
)


# ============================================================
# UTILISATEURS
# ============================================================

@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("username",)

    def save_model(self, request, obj, form, change):
        if not change:
            # Le mot de passe saisi à la création est provisoire : l'employé choisira le sien.
            obj.doit_changer_mot_de_passe = True
        super().save_model(request, obj, form, change)
        # L'historique des affectations (user_depots) suit automatiquement le champ « Dépôt ».
        if not change or "depot" in form.changed_data:
            if not synchroniser_affectation(obj):
                self.message_user(
                    request,
                    "Utilisateur enregistré, mais l'historique des dépôts n'a pas pu être mis à jour.",
                    messages.WARNING,
                )

    list_display = (
        "username",
        "first_name",
        "last_name",
        "role",
        "depot",
        "is_active",
        "mot_de_passe_choisi",
        "is_staff",
        "is_superuser",
    )
    actions = ("donner_mot_de_passe_provisoire",)

    @admin.display(description="Mot de passe choisi", boolean=True, ordering="doit_changer_mot_de_passe")
    def mot_de_passe_choisi(self, obj):
        return not obj.doit_changer_mot_de_passe

    # Mots de passe : réservés au super-administrateur (case « Statut superutilisateur »).
    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.is_superuser:
            actions.pop("donner_mot_de_passe_provisoire", None)
        return actions

    def has_change_permission(self, request, obj=None):
        # Le compte d'un super-administrateur n'est modifiable que par un super-administrateur.
        if obj is not None and obj.is_superuser and not request.user.is_superuser:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_superuser and not request.user.is_superuser:
            return False
        return super().has_delete_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        champs = super().get_readonly_fields(request, obj)
        if not request.user.is_superuser:
            # Personne d'autre ne peut se donner (ou donner) les droits de super-administrateur.
            champs = tuple(champs) + ("is_superuser", "doit_changer_mot_de_passe", "groups", "user_permissions")
        return champs

    @admin.action(description="Donner un mot de passe provisoire (oubli du mot de passe)")
    def donner_mot_de_passe_provisoire(self, request, queryset):
        if not request.user.is_superuser:
            raise PermissionDenied
        for utilisateur in queryset:
            mot = donner_mot_de_passe_provisoire(utilisateur)
            self.message_user(
                request,
                format_html(
                    "{} : mot de passe provisoire <b style='font-size:1.2em;letter-spacing:.05em'>{}</b> "
                    "— donnez-le à la personne ; elle choisira le sien à la connexion.",
                    utilisateur.get_full_name(), mot,
                ),
                messages.SUCCESS,
            )

    def user_change_password(self, request, id, form_url=""):
        # « Modifier le mot de passe » depuis l'admin = mot de passe provisoire, super-administrateur seulement.
        if not request.user.is_superuser:
            raise PermissionDenied
        reponse = super().user_change_password(request, id, form_url)
        if request.method == "POST" and reponse.status_code == 302:
            User.objects.filter(pk=id).update(doit_changer_mot_de_passe=True)
        return reponse

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
                    "doit_changer_mot_de_passe",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
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
        ("parent", admin.RelatedOnlyFieldListFilter),
    )

    list_select_related = ("parent",)
    ordering = ("parent__nom", "nom")

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
        "sous_categorie",
        "qualite",
        "reference_code",
        "nombre_balles",
        "poids_kg",
        "statut_logistique",
        "statut_ouverture",
        "qr_envoye",
    )

    list_filter = (
        "statut_logistique",
        "statut_ouverture",
        "categorie_lot",
        "qualite",
        "conteneur",
    )

    search_fields = (
        "code_lot",
        "conteneur__numero_conteneur",
        "qr_codes__code",
        "reference_fournisseur__code",
        "reference_fournisseur__libelle",
    )

    list_select_related = ("conteneur", "categorie_lot", "categorie_produit", "qualite", "reference_fournisseur")
    list_per_page = 100

    readonly_fields = (
        "code_lot",
        "etiquette_qr",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        ("Identification", {"fields": ("code_lot", "conteneur", "reference_fournisseur")}),
        ("Classement", {"fields": ("categorie_lot", "categorie_produit", "qualite")}),
        ("Informations fournisseur", {"fields": ("nombre_balles", "poids_kg", "prix_achat", "date_creation")}),
        ("Vente", {"fields": ("prix_vente_balle",)}),
        ("Suivi", {"fields": ("statut_logistique", "date_reception", "nombre_balles_recues", "statut_ouverture", "date_ouverture", "notes")}),
        ("QR code", {"fields": ("etiquette_qr",)}),
        ("Dates techniques", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    inlines = (QrCodesInline,)
    actions = ("imprimer_etiquettes", "imprimer_etiquettes_par_balle", "marquer_qr_envoyes", "regenerer_qr")

    @admin.display(description="Étiquette QR")
    def etiquette_qr(self, obj):
        if not obj.pk:
            return "Le code et le QR code seront générés automatiquement à l'enregistrement."
        return _lien_etiquette(obj.qr_actif)

    @admin.display(description="QR envoyé", boolean=True, ordering="_qr_envoye")
    def qr_envoye(self, obj):
        return obj._qr_envoye

    @admin.display(description="Sous-catégorie", ordering="categorie_produit__nom")
    def sous_categorie(self, obj):
        return obj.categorie_produit.nom if obj.categorie_produit_id else "—"

    @admin.display(description="Réf.", ordering="reference_fournisseur__code")
    def reference_code(self, obj):
        return obj.reference_fournisseur.code if obj.reference_fournisseur_id else "—"

    def get_queryset(self, request):
        # Calculé en une seule requête pour toute la liste (au lieu d'une par ligne).
        envoye = QrCodes.objects.filter(lot=OuterRef("pk"), actif=True, date_envoi_fournisseur__isnull=False)
        return super().get_queryset(request).annotate(_qr_envoye=Exists(envoye))

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "categorie_produit":
            kwargs["queryset"] = (
                CategoriesProduits.objects.filter(actif=True, parent__isnull=False)
                .select_related("parent")
                .order_by("parent__nom", "nom")
            )
        elif db_field.name == "reference_fournisseur":
            kwargs["queryset"] = ReferencesFournisseurs.objects.order_by("code")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_urls(self):
        urls = [
            path("importer/", self.admin_site.admin_view(partial(vue_import, self)), name="core_lots_import"),
            path("importer/verification/", self.admin_site.admin_view(partial(vue_apercu, self)), name="core_lots_import_apercu"),
        ]
        return urls + super().get_urls()

    def save_model(self, request, obj, form, change):
        # L'admin enregistre déjà dans une transaction : le verrou de
        # generer_code_lot() est donc tenu jusqu'à l'insertion du lot et de son QR.
        if not change:
            obj.code_lot = generer_code_lot()
            super().save_model(request, obj, form, change)
            creer_qr_code(obj)
        else:
            super().save_model(request, obj, form, change)

    def _pdf_etiquettes(self, request, queryset, une_par_balle):
        qr_codes = list(
            QrCodes.objects.filter(lot__in=queryset, actif=True)
            .select_related(*RELATIONS_ETIQUETTE)
            .order_by("lot__code_lot")
        )
        if not qr_codes:
            self.message_user(request, "Aucun QR code actif dans la sélection.", messages.WARNING)
            return None
        reponse = HttpResponse(pdf_etiquettes(qr_codes, une_par_balle=une_par_balle), content_type="application/pdf")
        nom = "etiquettes_qr_friplux_une_par_balle.pdf" if une_par_balle else "etiquettes_qr_friplux.pdf"
        reponse["Content-Disposition"] = f'attachment; filename="{nom}"'
        return reponse

    @admin.action(description="Imprimer les étiquettes QR : une par lot (PDF)")
    def imprimer_etiquettes(self, request, queryset):
        return self._pdf_etiquettes(request, queryset, une_par_balle=False)

    @admin.action(description="Imprimer les étiquettes QR : une par balle, prêtes à coller (PDF)")
    def imprimer_etiquettes_par_balle(self, request, queryset):
        return self._pdf_etiquettes(request, queryset, une_par_balle=True)

    @admin.action(description="Marquer les QR comme envoyés au fournisseur")
    def marquer_qr_envoyes(self, request, queryset):
        nombre = marquer_envoyes_au_fournisseur(QrCodes.objects.filter(lot__in=queryset, actif=True))
        self.message_user(request, f"{nombre} QR code(s) marqué(s) comme envoyé(s).", messages.SUCCESS)

    @admin.action(description="Remplacer le QR code du lot (étiquettes perdues ou abîmées)")
    def regenerer_qr(self, request, queryset):
        nouveaux = [regenerer_qr_code(lot).code for lot in queryset]
        self.message_user(
            request,
            "Nouveaux QR codes : " + ", ".join(nouveaux)
            + ". Les anciennes étiquettes ne sont plus valables : remplacez-les sur toutes les balles du lot.",
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
    """Réceptions de balles et transferts : lecture seule (le stock se calcule à partir de ces lignes)."""
    list_display = ("date_mouvement", "type_mouvement", "lot", "balles", "balles_recues", "depot_depart", "depot_arrivee",
                    "transfert", "utilisateur", "statut")
    list_filter = ("type_mouvement", "statut", "depot_depart", "depot_arrivee", ("date_mouvement", admin.DateFieldListFilter))
    search_fields = ("lot__code_lot", "reference_document", "transfert__reference_transfert")
    list_select_related = ("lot", "depot_depart", "depot_arrivee", "transfert", "utilisateur")
    date_hierarchy = "date_mouvement"
    list_per_page = 100

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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

class MouvementsTransfertInline(admin.TabularInline):
    model = MouvementsStock
    extra = 0
    fields = ("lot", "balles", "balles_recues", "statut")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(TransfertsStock)
class TransfertsStockAdmin(admin.ModelAdmin):
    list_display = ("reference_transfert", "date_transfert", "depot_depart", "depot_arrivee", "balles", "statut", "utilisateur")
    list_filter = ("statut", "depot_depart", "depot_arrivee", ("date_transfert", admin.DateFieldListFilter))
    search_fields = ("reference_transfert", "mouvements__lot__code_lot")
    list_select_related = ("depot_depart", "depot_arrivee", "utilisateur")
    readonly_fields = ("reference_transfert", "depot_depart", "depot_arrivee", "utilisateur", "date_transfert", "statut", "motif")
    fields = readonly_fields
    inlines = (MouvementsTransfertInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).exclude(statut="BROUILLON")

    @admin.display(description="Balles arrivées / envoyées")
    def balles(self, obj):
        arrivees, total = progression(obj)
        return f"{arrivees} / {total}"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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
# VENTES (saisies depuis le téléphone ; ici : consultation et annulation)
# Les montants, numéros et échéances sont calculés par l'application :
# pas de modification à la main, pour que facture, paiements et stock restent cohérents.
# ============================================================

class LectureSeuleMixin:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class LignesVenteInline(LectureSeuleMixin, admin.TabularInline):
    model = LignesVente
    extra = 0
    fields = ("lot", "designation", "quantite", "prix_unitaire", "prix_conseille", "remise", "montant_ligne")
    readonly_fields = fields


class PaiementsInline(LectureSeuleMixin, admin.TabularInline):
    model = Paiements
    extra = 0
    fields = ("date_paiement", "montant", "mode_paiement", "reference", "utilisateur", "statut")
    readonly_fields = fields


@admin.register(Ventes)
class VentesAdmin(admin.ModelAdmin):
    list_display = ("numero_vente", "date_vente", "client", "depot", "vendeur", "total_fcfa", "reste_fcfa", "statut")
    list_filter = ("statut", "depot", "vendeur", ("date_vente", admin.DateFieldListFilter))
    search_fields = ("numero_vente", "facture__numero_facture", "client__nom", "client__telephone", "lignes__lot__code_lot")
    list_select_related = ("client", "depot", "vendeur")
    date_hierarchy = "date_vente"
    readonly_fields = ("numero_vente", "facture_lien", "date_vente", "client", "depot", "vendeur", "total_fcfa",
                       "reste_fcfa", "statut", "notes")
    fields = readonly_fields
    inlines = (LignesVenteInline, PaiementsInline)
    actions = ("annuler",)
    list_per_page = 100

    def get_queryset(self, request):
        return super().get_queryset(request).exclude(statut="BROUILLON")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Total", ordering="montant_total")
    def total_fcfa(self, obj):
        return f"{format_fcfa(obj.montant_total)} FCFA"

    @admin.display(description="Reste à payer")
    def reste_fcfa(self, obj):
        reste = reste_a_payer(obj)
        return f"{format_fcfa(reste)} FCFA" if reste else "—"

    @admin.display(description="Facture")
    def facture_lien(self, obj):
        if not obj.pk or obj.statut == "BROUILLON":
            return "—"
        facture = getattr(obj, "facture", None)
        return format_html('<a href="{}" target="_blank">{} – voir / imprimer</a>',
                           reverse("core:vente_detail", args=[obj.pk]), facture.numero_facture if facture else "Facture")

    @admin.action(description="Annuler les ventes sélectionnées (balles remises en stock, paiements remboursés)")
    def annuler(self, request, queryset):
        faites = 0
        for vente in queryset:
            try:
                annuler_vente(request.user, vente, motif="annulée depuis l'administration")
                faites += 1
            except ErreurVente as erreur:
                self.message_user(request, str(erreur), messages.WARNING)
        if faites:
            self.message_user(request, f"{faites} vente(s) annulée(s) : les balles sont de nouveau disponibles.", messages.SUCCESS)


@admin.register(Paiements)
class PaiementsAdmin(LectureSeuleMixin, admin.ModelAdmin):
    list_display = ("date_paiement", "vente", "montant", "mode_paiement", "reference", "utilisateur", "statut")
    list_filter = ("mode_paiement", "statut", ("date_paiement", admin.DateFieldListFilter), "vente__depot")
    search_fields = ("vente__numero_vente", "reference", "vente__client__nom")
    list_select_related = ("vente", "utilisateur")
    date_hierarchy = "date_paiement"


@admin.register(Factures)
class FacturesAdmin(LectureSeuleMixin, admin.ModelAdmin):
    list_display = ("numero_facture", "date_facture", "vente", "montant_total", "statut", "voir")
    list_filter = ("statut", ("date_facture", admin.DateFieldListFilter))
    search_fields = ("numero_facture", "vente__numero_vente", "vente__client__nom")
    list_select_related = ("vente",)

    @admin.display(description="Facture")
    def voir(self, obj):
        return format_html('<a href="{}" target="_blank">Voir / imprimer</a>', reverse("core:vente_detail", args=[obj.vente_id]))


class EcheancesInline(LectureSeuleMixin, admin.TabularInline):
    model = EcheancesMoratoire
    extra = 0
    fields = ("numero_echeance", "date_echeance", "montant_prevu", "statut")
    readonly_fields = fields


@admin.register(Moratoires)
class MoratoiresAdmin(LectureSeuleMixin, admin.ModelAdmin):
    list_display = ("vente", "client", "montant_concerne", "date_debut", "date_echeance", "statut", "autorise_par")
    list_filter = ("statut",)
    search_fields = ("vente__numero_vente", "vente__client__nom", "vente__client__telephone")
    list_select_related = ("vente__client", "autorise_par")
    inlines = (EcheancesInline,)

    @admin.display(description="Client")
    def client(self, obj):
        return obj.vente.client or "—"


@admin.register(EcheancesMoratoire)
class EcheancesMoratoireAdmin(LectureSeuleMixin, admin.ModelAdmin):
    list_display = ("date_echeance", "moratoire", "numero_echeance", "montant_prevu", "statut")
    list_filter = ("statut", ("date_echeance", admin.DateFieldListFilter))
    search_fields = ("moratoire__vente__numero_vente", "moratoire__vente__client__nom")


# ============================================================
# UTILISATION DES DÉPÔTS
# ============================================================

@admin.register(UserDepots)
class UserDepotsAdmin(admin.ModelAdmin):
    """
    Historique des affectations, tenu automatiquement à partir du champ « Dépôt »
    de chaque utilisateur : consultation seulement.
    """
    list_display = (
        "user",
        "depot",
        "date_debut",
        "date_fin",
        "actif",
    )
    list_select_related = ("user", "depot")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

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

# ============================================================
# QUALITÉS ET RÉFÉRENCES FOURNISSEURS
# ============================================================

@admin.register(Qualites)
class QualitesAdmin(admin.ModelAdmin):
    list_display = ("ordre", "code", "nom", "actif")
    list_display_links = ("code", "nom")
    list_editable = ("ordre", "actif")


@admin.register(ReferencesFournisseurs)
class ReferencesFournisseursAdmin(admin.ModelAdmin):
    """
    Catalogue des codes articles fournisseurs et de leur classement.
    Modifier un classement ici s'applique aux prochains imports (pas aux balles déjà créées).
    """
    list_display = ("code", "libelle", "fournisseur", "categorie_lot", "categorie_produit", "qualite", "prix_vente_balle", "actif")
    list_editable = ("categorie_lot", "categorie_produit", "qualite", "prix_vente_balle")
    list_filter = ("fournisseur", "categorie_lot", "qualite", "actif")
    search_fields = ("code", "libelle")
    list_select_related = ("fournisseur", "categorie_lot", "categorie_produit__parent", "qualite")
    ordering = ("fournisseur__nom", "code")
    readonly_fields = ("created_at", "updated_at")
    list_per_page = 100

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "categorie_produit":
            kwargs["queryset"] = (
                CategoriesProduits.objects.filter(actif=True, parent__isnull=False)
                .select_related("parent")
                .order_by("parent__nom", "nom")
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ============================================================
# HISTORIQUE DES SCANS (lecture seule : chaque ligne est une preuve)
# ============================================================

@admin.register(ScansLots)
class ScansLotsAdmin(admin.ModelAdmin):
    list_display = ("date_scan", "code_scanne", "resultat", "lot", "categorie_lot", "utilisateur", "depot")
    list_filter = ("resultat", "categorie_lot", "depot", "utilisateur", ("date_scan", admin.DateFieldListFilter))
    search_fields = ("code_scanne", "lot__code_lot")
    list_select_related = ("lot", "categorie_lot", "utilisateur", "depot")
    date_hierarchy = "date_scan"
    list_per_page = 100

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
