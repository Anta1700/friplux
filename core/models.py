import unicodedata
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager


# ============================================================
# GESTIONNAIRE DU MODÈLE USER
# ============================================================

class UserManager(BaseUserManager):

    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError("Le nom d'utilisateur est obligatoire.")

        # Dates obligatoires dans la table users
        now = timezone.now()
        extra_fields.setdefault("created_at", now)
        extra_fields.setdefault("updated_at", now)

        user = self.model(
            username=username,
            **extra_fields
        )

        if password:
            user.set_password(password)

        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        # Droits Django
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        # Informations obligatoires dans la table users
        extra_fields.setdefault("first_name", "Administrateur")
        extra_fields.setdefault("last_name", "Frip'Lux")

        # Rôle Administrateur Frip'Lux
        # id = 1 dans la table roles
        if "role_id" not in extra_fields:
            extra_fields["role_id"] = 1

        return self.create_user(
            username=username,
            password=password,
            **extra_fields
        )


# ============================================================
# ROLES
# ============================================================

class Roles(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(unique=True, max_length=30)
    nom = models.CharField(max_length=80)
    description = models.TextField(blank=True, null=True)
    actif = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "roles"

    def __str__(self):
        return self.nom


# ============================================================
# UTILISATEURS
# ============================================================

class User(AbstractBaseUser, PermissionsMixin):

    id = models.BigAutoField(primary_key=True)

    username = models.CharField(
        max_length=100,
        unique=True,
        db_column="username"
    )

    first_name = models.CharField(
        max_length=100,
        db_column="first_name"
    )

    last_name = models.CharField(
        max_length=100,
        db_column="last_name"
    )

    phone = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        db_column="phone"
    )

    email = models.CharField(
        max_length=254,
        blank=True,
        null=True,
        db_column="email"
    )

    role = models.ForeignKey(
        "Roles",
        on_delete=models.DO_NOTHING,
        db_column="role_id"
    )

    depot = models.ForeignKey(
        "Depots",
        on_delete=models.DO_NOTHING,
        blank=True,
        null=True,
        db_column="depot_id"
    )

    is_active = models.BooleanField(
        default=True,
        db_column="is_active"
    )

    is_staff = models.BooleanField(
        default=False,
        db_column="is_staff"
    )

    # Vrai quand le mot de passe a été donné par l'administrateur :
    # l'utilisateur doit choisir le sien à sa prochaine connexion.
    doit_changer_mot_de_passe = models.BooleanField(
        "doit choisir son mot de passe",
        default=False,
        help_text="Coché automatiquement quand vous créez le compte ou donnez un mot de passe provisoire.",
    )

    created_at = models.DateTimeField(
        db_column="created_at"
    )

    updated_at = models.DateTimeField(
        db_column="updated_at"
    )

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    class Meta:
        managed = False
        db_table = "users"

    def __str__(self):
        return self.username

    def get_full_name(self):
        nom = f"{self.first_name or ''} {self.last_name or ''}".strip()
        return nom or self.username

    def get_short_name(self):
        return self.first_name or self.username

    def save(self, *args, **kwargs):
        # Les colonnes created_at / updated_at sont NOT NULL en base.
        # Django envoie NULL si on ne les renseigne pas : on les remplit ici,
        # quel que soit le chemin de création (admin, shell, createsuperuser).
        now = timezone.now()
        if self.created_at is None:
            self.created_at = now
        self.updated_at = now
        super().save(*args, **kwargs)


# ============================================================
# MODÈLES MÉTIER FRIP'LUX
# ============================================================

class AffectationsPaiements(models.Model):
    id = models.BigAutoField(primary_key=True)
    paiement = models.ForeignKey('Paiements', models.DO_NOTHING, related_name="affectations")
    echeance = models.ForeignKey('EcheancesMoratoire', models.DO_NOTHING, related_name="affectations")
    montant_affecte = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        managed = False
        db_table = 'affectations_paiements'
        unique_together = (('paiement', 'echeance'),)


class AuditLogs(models.Model):
    id = models.BigAutoField(primary_key=True)

    utilisateur = models.ForeignKey(
        'User',
        models.DO_NOTHING,
        blank=True,
        null=True
    )

    action = models.CharField(max_length=100)
    table_concernee = models.CharField(max_length=100)
    objet_id = models.BigIntegerField(blank=True, null=True)
    date_action = models.DateTimeField()
    ancienne_valeur = models.JSONField(blank=True, null=True)
    nouvelle_valeur = models.JSONField(blank=True, null=True)
    adresse_ip = models.GenericIPAddressField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'audit_logs'


class CategoriesLots(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(unique=True, max_length=30)
    nom = models.CharField(unique=True, max_length=100)
    description = models.TextField(blank=True, null=True)
    actif = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = 'categories_lots'
    def __str__(self):
        return self.nom


class CategoriesProduits(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(unique=True, max_length=40)
    nom = models.CharField(max_length=100)

    parent = models.ForeignKey(
        'self',
        models.DO_NOTHING,
        blank=True,
        null=True
    )

    actif = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = 'categories_produits'
        unique_together = (('parent', 'nom'),)
        verbose_name = "sous-catégorie"
        verbose_name_plural = "sous-catégories"

    def __str__(self):
        # « Femme › Pantalons » : plusieurs catégories ont une sous-catégorie du même nom.
        if self.parent_id:
            return f"{self.parent.nom} › {self.nom}"
        return self.nom


class TypeClient(models.TextChoices):
    PARTICULIER = "PARTICULIER", "Particulier"
    PROFESSIONNEL = "PROFESSIONNEL", "Professionnel"


class Clients(models.Model):
    id = models.BigAutoField(primary_key=True)
    code_client = models.CharField("code client", unique=True, max_length=50, blank=True, null=True)
    nom = models.CharField(max_length=150)
    telephone = models.CharField("téléphone", max_length=30, blank=True, null=True)
    numero_piece_identite = models.CharField("n° de carte d'identité", max_length=50, blank=True, null=True)
    email = models.CharField(max_length=254, blank=True, null=True)
    adresse = models.TextField(blank=True, null=True)
    type_client = models.CharField("type", max_length=30, choices=TypeClient.choices, default=TypeClient.PARTICULIER)
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'clients'
        verbose_name = "client"
        verbose_name_plural = "clients"

    def __str__(self):
        return f"{self.nom} ({self.telephone})" if self.telephone else self.nom


class Conteneurs(models.Model):
    id = models.BigAutoField(primary_key=True)
    numero_conteneur = models.CharField(unique=True, max_length=100)
    fournisseur = models.ForeignKey('Fournisseurs', models.DO_NOTHING)
    pays_origine = models.CharField(max_length=100, blank=True, null=True)
    date_commande = models.DateField(blank=True, null=True)
    date_expedition = models.DateField(blank=True, null=True)
    date_arrivee_estimee = models.DateField(blank=True, null=True)
    date_arrivee_reelle = models.DateField(blank=True, null=True)
    statut = models.CharField(max_length=30)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'conteneurs'
    def __str__(self):
        return self.numero_conteneur


class Depots(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(unique=True, max_length=30)
    nom = models.CharField(max_length=120)
    adresse = models.TextField(blank=True, null=True)
    telephone = models.CharField(max_length=30)

    responsable = models.ForeignKey(
        'User',
        models.DO_NOTHING,
        blank=True,
        null=True
    )

    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'depots'
    def __str__(self):
        return self.nom


class StatutEcheance(models.TextChoices):
    A_PAYER = "A_PAYER", "À payer"
    PARTIELLE = "PARTIELLE", "Payée en partie"
    PAYEE = "PAYEE", "Payée"
    ANNULEE = "ANNULEE", "Annulée"


class EcheancesMoratoire(models.Model):
    id = models.BigAutoField(primary_key=True)
    moratoire = models.ForeignKey('Moratoires', models.DO_NOTHING, related_name="echeances")
    numero_echeance = models.IntegerField("n°")
    date_echeance = models.DateField("date")
    montant_prevu = models.DecimalField("montant", max_digits=15, decimal_places=2)
    statut = models.CharField(max_length=20, choices=StatutEcheance.choices, default=StatutEcheance.A_PAYER)

    class Meta:
        managed = False
        db_table = 'echeances_moratoire'
        unique_together = (('moratoire', 'numero_echeance'),)
        ordering = ("numero_echeance",)
        verbose_name = "échéance"
        verbose_name_plural = "échéances"


class StatutFacture(models.TextChoices):
    EMISE = "EMISE", "Émise (reste à payer)"
    PAYEE = "PAYEE", "Payée"
    ANNULEE = "ANNULEE", "Annulée"


class Factures(models.Model):
    id = models.BigAutoField(primary_key=True)
    numero_facture = models.CharField("n° de facture", unique=True, max_length=50)
    vente = models.OneToOneField('Ventes', models.DO_NOTHING, related_name="facture")
    date_facture = models.DateTimeField("date")
    montant_total = models.DecimalField("montant (FCFA)", max_digits=15, decimal_places=2)
    statut = models.CharField(max_length=30, choices=StatutFacture.choices, default=StatutFacture.EMISE)
    fichier_pdf = models.TextField(blank=True, null=True)
    jeton_public = models.CharField("lien secret", max_length=64, blank=True, null=True, unique=True, editable=False)
    lien_public_actif = models.BooleanField(
        "lien client actif", default=True,
        help_text="Décocher pour que le QR code / lien de cette facture ne fonctionne plus.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'factures'
        verbose_name = "facture"
        verbose_name_plural = "factures"

    def __str__(self):
        return self.numero_facture


class Fournisseurs(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(unique=True, max_length=30)
    nom = models.CharField(max_length=150)
    pays = models.CharField(max_length=100, blank=True, null=True)
    ville = models.CharField(max_length=100, blank=True, null=True)
    telephone = models.CharField(max_length=30, blank=True, null=True)
    email = models.CharField(max_length=254, blank=True, null=True)
    adresse = models.TextField(blank=True, null=True)
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'fournisseurs'
    def __str__(self):
        return self.nom


class LignesOuverture(models.Model):
    id = models.BigAutoField(primary_key=True)

    ouverture = models.ForeignKey(
        'OuverturesLots',
        models.DO_NOTHING
    )

    categorie_produit = models.ForeignKey(
        CategoriesProduits,
        models.DO_NOTHING
    )

    quantite_pieces = models.IntegerField()
    poids_kg = models.DecimalField(
        max_digits=12,
        decimal_places=3
    )

    class Meta:
        managed = False
        db_table = 'lignes_ouverture'
        unique_together = (('ouverture', 'categorie_produit'),)


class LignesTransfert(models.Model):
    id = models.BigAutoField(primary_key=True)

    transfert = models.ForeignKey(
        'TransfertsStock',
        models.DO_NOTHING
    )

    categorie_produit = models.ForeignKey(
        CategoriesProduits,
        models.DO_NOTHING
    )

    quantite_pieces = models.IntegerField()
    poids_kg = models.DecimalField(
        max_digits=12,
        decimal_places=3
    )

    class Meta:
        managed = False
        db_table = 'lignes_transfert'
        unique_together = (('transfert', 'categorie_produit'),)


class LignesVente(models.Model):
    """Une ligne = N balles entières d'un même lot."""
    id = models.BigAutoField(primary_key=True)
    vente = models.ForeignKey('Ventes', models.DO_NOTHING, related_name="lignes")
    lot = models.ForeignKey("Lots", models.DO_NOTHING, blank=True, null=True, related_name="lignes_vente")
    categorie_produit = models.ForeignKey(
        CategoriesProduits, models.DO_NOTHING, blank=True, null=True, verbose_name="sous-catégorie"
    )
    designation = models.CharField("désignation", max_length=200)
    unite_vente = models.CharField(max_length=10, default="BALLE")
    quantite = models.DecimalField("balles", max_digits=12, decimal_places=3)
    prix_unitaire = models.DecimalField("prix par balle", max_digits=15, decimal_places=2)
    prix_conseille = models.DecimalField("prix conseillé", max_digits=15, decimal_places=2, blank=True, null=True)
    remise = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="Écart total sous le prix conseillé (négociation)."
    )
    montant_ligne = models.DecimalField("montant", max_digits=15, decimal_places=2, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'lignes_vente'
        ordering = ("id",)
        verbose_name = "ligne de vente"
        verbose_name_plural = "lignes de vente"

    @property
    def nombre_balles(self):
        return int(self.quantite)


def _normaliser(texte):
    """« Bébé » -> « bebe » : compare les noms sans accents ni majuscules."""
    texte = unicodedata.normalize("NFKD", texte or "")
    return "".join(c for c in texte if not unicodedata.combining(c)).strip().lower()


def sous_categorie_compatible(categorie_lot, categorie_produit):
    """Vrai si la sous-catégorie appartient bien à la catégorie (ex. Robes ⊂ Femme)."""
    if not categorie_lot or not categorie_produit:
        return True
    parent = categorie_produit.parent
    return parent is not None and _normaliser(parent.nom) == _normaliser(categorie_lot.nom)


class Qualites(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(unique=True, max_length=30)
    nom = models.CharField(unique=True, max_length=80)
    ordre = models.IntegerField(default=0)
    actif = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "qualites"
        ordering = ("ordre",)
        verbose_name = "qualité"
        verbose_name_plural = "qualités"

    def __str__(self):
        return self.nom


class ReferencesFournisseurs(models.Model):
    """
    Catalogue : un code article d'un fournisseur (ex. SILTEX 2545 « Robes femme été »)
    et son classement Frip'Lux. Classée une fois, la référence est reconnue
    automatiquement aux imports suivants.
    """
    id = models.BigAutoField(primary_key=True)
    fournisseur = models.ForeignKey("Fournisseurs", models.DO_NOTHING)
    code = models.CharField("code article", max_length=50)
    libelle = models.CharField("libellé", max_length=200)
    categorie_lot = models.ForeignKey(CategoriesLots, models.DO_NOTHING, verbose_name="catégorie")
    categorie_produit = models.ForeignKey(
        CategoriesProduits, models.DO_NOTHING, blank=True, null=True, verbose_name="sous-catégorie"
    )
    qualite = models.ForeignKey(Qualites, models.DO_NOTHING, blank=True, null=True, verbose_name="qualité")
    prix_vente_balle = models.DecimalField(
        "prix de vente conseillé par balle (FCFA)", max_digits=15, decimal_places=2, blank=True, null=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Proposé au vendeur pour toutes les balles de cette référence (il peut le négocier).",
    )
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "references_fournisseurs"
        unique_together = (("fournisseur", "code"),)
        verbose_name = "référence fournisseur"
        verbose_name_plural = "références fournisseurs"

    def __str__(self):
        return f"{self.code} – {self.libelle}"

    def clean(self):
        if self.categorie_lot_id and self.categorie_produit_id and not sous_categorie_compatible(
            self.categorie_lot, self.categorie_produit
        ):
            raise ValidationError(
                {"categorie_produit": f"Cette sous-catégorie n'appartient pas à la catégorie « {self.categorie_lot} »."}
            )


class StatutLogistique(models.TextChoices):
    # Valeurs identiques à la contrainte chk_lots_statut_logistique
    CREE = "CREE", "Créé"
    EN_TRANSIT = "EN_TRANSIT", "En transit"
    RECU = "RECU", "Reçu"
    ANNULE = "ANNULE", "Annulé"


class StatutOuverture(models.TextChoices):
    # Valeurs identiques à la contrainte chk_lots_statut_ouverture
    NON_OUVERT = "NON_OUVERT", "Non ouverte"
    OUVERT = "OUVERT", "Ouverte"


class Lots(models.Model):
    id = models.BigAutoField(primary_key=True)
    code_lot = models.CharField(
        "code du lot",
        unique=True,
        max_length=50,
        help_text="Généré automatiquement à la création (FRPLX-LOT-AAAA-NNNNNN).",
    )

    conteneur = models.ForeignKey(
        Conteneurs,
        models.DO_NOTHING,
        related_name="lots",
    )

    categorie_lot = models.ForeignKey(
        CategoriesLots,
        models.DO_NOTHING,
        verbose_name="catégorie",
    )

    categorie_produit = models.ForeignKey(
        CategoriesProduits,
        models.DO_NOTHING,
        blank=True,
        null=True,
        verbose_name="sous-catégorie",
        related_name="lots",
    )

    qualite = models.ForeignKey(
        Qualites,
        models.DO_NOTHING,
        blank=True,
        null=True,
        verbose_name="qualité",
    )

    reference_fournisseur = models.ForeignKey(
        ReferencesFournisseurs,
        models.DO_NOTHING,
        blank=True,
        null=True,
        verbose_name="référence fournisseur",
        related_name="lots",
    )

    # Un lot = une ligne de la fiche fournisseur ; il peut regrouper plusieurs balles
    # qui partagent le même code et le même QR code.
    nombre_balles = models.PositiveIntegerField(
        "nombre de balles",
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Balles annoncées par le fournisseur pour ce lot.",
    )
    nombre_balles_recues = models.PositiveIntegerField(
        "balles reçues",
        blank=True,
        null=True,
        help_text="Balles comptées à la réception (vide tant que le lot n'est pas reçu).",
    )

    poids_kg = models.DecimalField(
        "poids total (kg)",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    prix_achat = models.DecimalField(
        "prix d'achat total",
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )

    prix_vente_balle = models.DecimalField(
        "prix de vente conseillé par balle (FCFA)", max_digits=15, decimal_places=2, blank=True, null=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Laisser vide pour reprendre le prix de la référence fournisseur.",
    )

    date_creation = models.DateField("date de création", default=timezone.localdate)
    date_reception = models.DateField(
        "date de réception",
        blank=True,
        null=True
    )

    statut_logistique = models.CharField(
        "statut logistique",
        max_length=30,
        choices=StatutLogistique.choices,
        default=StatutLogistique.CREE,
    )
    statut_ouverture = models.CharField(
        "statut d'ouverture",
        max_length=20,
        choices=StatutOuverture.choices,
        default=StatutOuverture.NON_OUVERT,
    )

    date_ouverture = models.DateTimeField(
        "date d'ouverture",
        blank=True,
        null=True
    )

    notes = models.TextField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'lots'
        verbose_name = "lot"
        verbose_name_plural = "lots"

    def __str__(self):
        return self.code_lot or f"Lot #{self.pk}"

    def clean(self):
        # Reprend les contraintes CHECK de la base pour afficher un message
        # clair dans le formulaire au lieu d'une erreur PostgreSQL.
        erreurs = {}

        if self.categorie_lot_id and self.categorie_produit_id and not sous_categorie_compatible(
            self.categorie_lot, self.categorie_produit
        ):
            erreurs["categorie_produit"] = (
                f"Cette sous-catégorie n'appartient pas à la catégorie « {self.categorie_lot} »."
            )

        if self.date_reception and self.date_creation and self.date_reception < self.date_creation:
            erreurs["date_reception"] = "La date de réception ne peut pas être antérieure à la date de création."

        if self.statut_ouverture == StatutOuverture.OUVERT and not self.date_ouverture:
            erreurs["date_ouverture"] = "Un lot ouvert doit avoir une date d'ouverture."
        if self.statut_ouverture == StatutOuverture.NON_OUVERT and self.date_ouverture:
            erreurs["date_ouverture"] = "Un lot non ouvert ne doit pas avoir de date d'ouverture."

        if erreurs:
            raise ValidationError(erreurs)

    @property
    def poids_moyen_balle(self):
        """Poids moyen d'une balle du lot (information, pas une mesure)."""
        if self.poids_kg and self.nombre_balles:
            return (self.poids_kg / self.nombre_balles).quantize(Decimal("0.01"))
        return None

    @property
    def balles_manquantes(self):
        """Écart à la réception (None tant que le lot n'est pas compté)."""
        if self.nombre_balles_recues is None:
            return None
        return self.nombre_balles - self.nombre_balles_recues

    @property
    def prix_conseille(self):
        """Prix de vente proposé par balle : celui du lot, sinon celui de sa référence fournisseur."""
        if self.prix_vente_balle is not None:
            return self.prix_vente_balle
        if self.reference_fournisseur_id:
            return self.reference_fournisseur.prix_vente_balle
        return None

    @property
    def qr_actif(self):
        """Le QR code actuellement valable pour ce lot (ou None)."""
        return self.qr_codes.filter(actif=True).first()


class StatutMoratoire(models.TextChoices):
    EN_COURS = "EN_COURS", "En cours"
    SOLDE = "SOLDE", "Soldé"
    ANNULE = "ANNULE", "Annulé"


class Moratoires(models.Model):
    """Paiement échelonné du reste d'une vente."""
    id = models.BigAutoField(primary_key=True)
    vente = models.ForeignKey('Ventes', models.DO_NOTHING, related_name="moratoires")
    date_debut = models.DateField("début")
    date_echeance = models.DateField("dernière échéance")
    montant_concerne = models.DecimalField("montant échelonné", max_digits=15, decimal_places=2)
    type_moratoire = models.CharField(max_length=20, default="ECHEANCIER")
    motif = models.TextField(blank=True, null=True)
    statut = models.CharField(max_length=20, choices=StatutMoratoire.choices, default=StatutMoratoire.EN_COURS)
    autorise_par = models.ForeignKey('User', models.DO_NOTHING, db_column='autorise_par', verbose_name="accordé par")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'moratoires'
        verbose_name = "moratoire"
        verbose_name_plural = "moratoires"


class TypeMouvement(models.TextChoices):
    RECEPTION_BALLE = "RECEPTION_BALLE", "Réception d'une balle"
    TRANSFERT_BALLES = "TRANSFERT_BALLES", "Transfert de balles"


class MouvementsStock(models.Model):
    """
    Mouvements de balles entre « lieux » : réception dans un dépôt, transfert d'un dépôt à un autre.
    Le stock d'un dépôt = réceptions + transferts reçus - transferts envoyés - balles vendues.
    """
    id = models.BigAutoField(primary_key=True)
    type_mouvement = models.CharField("type", max_length=30)
    depot_depart = models.ForeignKey(Depots, models.DO_NOTHING, blank=True, null=True, verbose_name="dépôt de départ",
                                     related_name="mouvements_sortants")
    depot_arrivee = models.ForeignKey(Depots, models.DO_NOTHING, blank=True, null=True, verbose_name="dépôt d'arrivée",
                                      related_name="mouvementsstock_depot_arrivee_set")
    lot = models.ForeignKey(Lots, models.DO_NOTHING, blank=True, null=True, related_name="mouvements")
    categorie_produit = models.ForeignKey(CategoriesProduits, models.DO_NOTHING, blank=True, null=True)
    balles = models.IntegerField(blank=True, null=True)
    balles_recues = models.IntegerField("balles arrivées", blank=True, null=True)
    transfert = models.ForeignKey("TransfertsStock", models.DO_NOTHING, blank=True, null=True, related_name="mouvements")
    quantite_pieces = models.IntegerField(default=0)
    poids_kg = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    reference_document = models.CharField(max_length=100, blank=True, null=True)
    utilisateur = models.ForeignKey('User', models.DO_NOTHING)
    date_mouvement = models.DateTimeField("date")
    statut = models.CharField(max_length=20)
    commentaire = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'mouvements_stock'
        verbose_name = "mouvement de stock"
        verbose_name_plural = "mouvements de stock"

    @property
    def balles_manquantes(self):
        return (self.balles or 0) - (self.balles_recues or 0)


class OuverturesLots(models.Model):
    id = models.BigAutoField(primary_key=True)

    lot = models.OneToOneField(
        Lots,
        models.DO_NOTHING
    )

    depot = models.ForeignKey(
        Depots,
        models.DO_NOTHING
    )

    utilisateur = models.ForeignKey(
        'User',
        models.DO_NOTHING
    )

    date_ouverture = models.DateTimeField()
    commentaire = models.TextField(blank=True, null=True)
    statut = models.CharField(max_length=20)

    class Meta:
        managed = False
        db_table = 'ouvertures_lots'


class ModePaiement(models.TextChoices):
    ESPECES = "ESPECES", "Espèces"
    WAVE = "WAVE", "Wave"
    ORANGE_MONEY = "ORANGE_MONEY", "Orange Money"
    VIREMENT = "VIREMENT", "Virement"
    CHEQUE = "CHEQUE", "Chèque"


# Moyens proposés aux vendeurs. Virement et Chèque ne sont plus proposés, mais restent connus
# pour afficher correctement les anciens paiements.
MODES_PAIEMENT_PROPOSES = (ModePaiement.ESPECES, ModePaiement.WAVE, ModePaiement.ORANGE_MONEY)
CHOIX_MODES_PAIEMENT = [(m.value, m.label) for m in MODES_PAIEMENT_PROPOSES]


class StatutPaiement(models.TextChoices):
    VALIDE = "VALIDE", "Validé"
    ANNULE = "ANNULE", "Annulé"


class Paiements(models.Model):
    id = models.BigAutoField(primary_key=True)
    vente = models.ForeignKey('Ventes', models.DO_NOTHING, related_name="paiements")
    montant = models.DecimalField("montant (FCFA)", max_digits=15, decimal_places=2)
    date_paiement = models.DateTimeField("date")
    mode_paiement = models.CharField("moyen", max_length=30, choices=ModePaiement.choices)
    reference = models.CharField(
        "référence", max_length=100, blank=True, null=True, help_text="N° de transaction Wave / Orange Money, n° de chèque…"
    )
    utilisateur = models.ForeignKey('User', models.DO_NOTHING, verbose_name="encaissé par")
    statut = models.CharField(max_length=20, choices=StatutPaiement.choices, default=StatutPaiement.VALIDE)
    commentaire = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'paiements'
        ordering = ("date_paiement", "id")
        verbose_name = "paiement"
        verbose_name_plural = "paiements"


class QrCodes(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(unique=True, max_length=100)

    # ForeignKey (et non OneToOne) : un lot peut avoir plusieurs versions de
    # QR code (étiquette abîmée puis réimprimée), une seule étant active.
    # La base le garantit avec uq_qr_codes_lot_version et uq_qr_codes_active_lot.
    lot = models.ForeignKey(
        Lots,
        models.DO_NOTHING,
        related_name="qr_codes",
    )

    version = models.IntegerField(default=1)
    date_generation = models.DateTimeField(default=timezone.now)

    date_envoi_fournisseur = models.DateTimeField(
        blank=True,
        null=True
    )

    date_activation = models.DateTimeField(
        blank=True,
        null=True
    )

    actif = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = 'qr_codes'
        unique_together = (('lot', 'version'),)
        verbose_name = "QR code"
        verbose_name_plural = "QR codes"

    def __str__(self):
        return self.code


class Stocks(models.Model):
    id = models.BigAutoField(primary_key=True)

    depot = models.ForeignKey(
        Depots,
        models.DO_NOTHING
    )

    categorie_produit = models.ForeignKey(
        CategoriesProduits,
        models.DO_NOTHING
    )

    quantite_pieces = models.IntegerField()
    poids_kg = models.DecimalField(
        max_digits=12,
        decimal_places=3
    )

    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'stocks'
        unique_together = (('depot', 'categorie_produit'),)


class StatutTransfert(models.TextChoices):
    BROUILLON = "BROUILLON", "En préparation"
    EN_COURS = "EN_COURS", "En route"
    RECU = "RECU", "Arrivé"
    RECU_AVEC_ECART = "RECU_AVEC_ECART", "Arrivé avec balles manquantes"
    ANNULE = "ANNULE", "Annulé"


class TransfertsStock(models.Model):
    id = models.BigAutoField(primary_key=True)
    reference_transfert = models.CharField("n° de transfert", unique=True, max_length=50)
    depot_depart = models.ForeignKey(Depots, models.DO_NOTHING, verbose_name="de", related_name="transferts_sortants")
    depot_arrivee = models.ForeignKey(Depots, models.DO_NOTHING, verbose_name="vers",
                                      related_name='transfertsstock_depot_arrivee_set')
    utilisateur = models.ForeignKey('User', models.DO_NOTHING, verbose_name="envoyé par")
    date_transfert = models.DateTimeField("date d'envoi")
    statut = models.CharField(max_length=20, choices=StatutTransfert.choices, default=StatutTransfert.BROUILLON)
    motif = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'transferts_stock'
        verbose_name = "transfert"
        verbose_name_plural = "transferts entre dépôts"

    def __str__(self):
        return self.reference_transfert


class UserDepots(models.Model):
    id = models.BigAutoField(primary_key=True)

    user = models.ForeignKey(
        'User',
        models.DO_NOTHING
    )

    depot = models.ForeignKey(
        Depots,
        models.DO_NOTHING
    )

    date_debut = models.DateField()
    date_fin = models.DateField(
        blank=True,
        null=True
    )

    actif = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = 'user_depots'
        unique_together = (('user', 'depot'),)
        verbose_name = "affectation à un dépôt"
        verbose_name_plural = "historique des affectations aux dépôts"


class StatutVente(models.TextChoices):
    BROUILLON = "BROUILLON", "En cours de saisie"
    VALIDEE = "VALIDEE", "Validée"
    ANNULEE = "ANNULEE", "Annulée"


class Ventes(models.Model):
    id = models.BigAutoField(primary_key=True)
    numero_vente = models.CharField("n° de vente", unique=True, max_length=50)
    client = models.ForeignKey(Clients, models.DO_NOTHING, blank=True, null=True, related_name="ventes")
    depot = models.ForeignKey(Depots, models.DO_NOTHING, verbose_name="dépôt")
    vendeur = models.ForeignKey('User', models.DO_NOTHING, related_name="ventes")
    date_vente = models.DateTimeField("date")
    montant_total = models.DecimalField("total (FCFA)", max_digits=15, decimal_places=2, default=0)
    statut = models.CharField(max_length=20, choices=StatutVente.choices, default=StatutVente.BROUILLON)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'ventes'
        verbose_name = "vente"
        verbose_name_plural = "ventes"

    def __str__(self):
        return self.numero_vente if self.statut != StatutVente.BROUILLON else f"Vente en cours de {self.vendeur}"


# ============================================================
# HISTORIQUE DES SCANS
# ============================================================

class ResultatScan(models.TextChoices):
    OK = "OK", "Balle trouvée"
    QR_REMPLACE = "QR_REMPLACE", "Ancienne étiquette (remplacée)"
    INCONNU = "INCONNU", "Code inconnu"


class ScansLots(models.Model):
    """
    Une ligne par lecture de QR code. Les compteurs (scans, balles uniques)
    sont calculés à partir de cette table, jamais saisis à la main.
    """
    id = models.BigAutoField(primary_key=True)
    date_scan = models.DateTimeField("date du scan", default=timezone.now)
    code_scanne = models.CharField("code lu", max_length=100)
    resultat = models.CharField("résultat", max_length=20, choices=ResultatScan.choices)
    lot = models.ForeignKey(Lots, models.DO_NOTHING, blank=True, null=True, related_name="scans")
    qr_code = models.ForeignKey(QrCodes, models.DO_NOTHING, blank=True, null=True, verbose_name="QR code")
    categorie_lot = models.ForeignKey(
        CategoriesLots, models.DO_NOTHING, blank=True, null=True, verbose_name="catégorie (au moment du scan)"
    )
    utilisateur = models.ForeignKey("User", models.DO_NOTHING, blank=True, null=True)
    depot = models.ForeignKey(Depots, models.DO_NOTHING, blank=True, null=True, verbose_name="dépôt")

    class Meta:
        managed = False
        db_table = "scans_lots"
        ordering = ("-date_scan",)
        verbose_name = "scan de balle"
        verbose_name_plural = "historique des scans"

    def __str__(self):
        return f"{self.code_scanne} – {self.date_scan:%d/%m/%Y %H:%M}"
