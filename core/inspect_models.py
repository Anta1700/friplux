# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class AffectationsPaiements(models.Model):
    id = models.BigAutoField(primary_key=True)
    paiement = models.ForeignKey('Paiements', models.DO_NOTHING)
    echeance = models.ForeignKey('EcheancesMoratoire', models.DO_NOTHING)
    montant_affecte = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        managed = False
        db_table = 'affectations_paiements'
        unique_together = (('paiement', 'echeance'),)


class AuditLogs(models.Model):
    id = models.BigAutoField(primary_key=True)
    utilisateur = models.ForeignKey('Users', models.DO_NOTHING, blank=True, null=True)
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
    actif = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'categories_lots'


class CategoriesProduits(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(unique=True, max_length=40)
    nom = models.CharField(max_length=100)
    parent = models.ForeignKey('self', models.DO_NOTHING, blank=True, null=True)
    actif = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'categories_produits'
        unique_together = (('parent', 'nom'),)


class Clients(models.Model):
    id = models.BigAutoField(primary_key=True)
    code_client = models.CharField(unique=True, max_length=50, blank=True, null=True)
    nom = models.CharField(max_length=150)
    telephone = models.CharField(max_length=30, blank=True, null=True)
    email = models.CharField(max_length=254, blank=True, null=True)
    adresse = models.TextField(blank=True, null=True)
    type_client = models.CharField(max_length=30)
    actif = models.BooleanField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'clients'


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
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'conteneurs'


class Depots(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(unique=True, max_length=30)
    nom = models.CharField(max_length=120)
    adresse = models.TextField(blank=True, null=True)
    telephone = models.CharField(max_length=30, blank=True, null=True)
    responsable = models.ForeignKey('Users', models.DO_NOTHING, blank=True, null=True)
    actif = models.BooleanField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'depots'


class EcheancesMoratoire(models.Model):
    id = models.BigAutoField(primary_key=True)
    moratoire = models.ForeignKey('Moratoires', models.DO_NOTHING)
    numero_echeance = models.IntegerField()
    date_echeance = models.DateField()
    montant_prevu = models.DecimalField(max_digits=15, decimal_places=2)
    statut = models.CharField(max_length=20)

    class Meta:
        managed = False
        db_table = 'echeances_moratoire'
        unique_together = (('moratoire', 'numero_echeance'),)


class Factures(models.Model):
    id = models.BigAutoField(primary_key=True)
    numero_facture = models.CharField(unique=True, max_length=50)
    vente = models.OneToOneField('Ventes', models.DO_NOTHING)
    date_facture = models.DateTimeField()
    montant_total = models.DecimalField(max_digits=15, decimal_places=2)
    statut = models.CharField(max_length=30)
    fichier_pdf = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'factures'


class Fournisseurs(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(unique=True, max_length=30)
    nom = models.CharField(max_length=150)
    pays = models.CharField(max_length=100, blank=True, null=True)
    ville = models.CharField(max_length=100, blank=True, null=True)
    telephone = models.CharField(max_length=30, blank=True, null=True)
    email = models.CharField(max_length=254, blank=True, null=True)
    adresse = models.TextField(blank=True, null=True)
    actif = models.BooleanField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'fournisseurs'


class LignesOuverture(models.Model):
    id = models.BigAutoField(primary_key=True)
    ouverture = models.ForeignKey('OuverturesLots', models.DO_NOTHING)
    categorie_produit = models.ForeignKey(CategoriesProduits, models.DO_NOTHING)
    quantite_pieces = models.IntegerField()
    poids_kg = models.DecimalField(max_digits=12, decimal_places=3)

    class Meta:
        managed = False
        db_table = 'lignes_ouverture'
        unique_together = (('ouverture', 'categorie_produit'),)


class LignesTransfert(models.Model):
    id = models.BigAutoField(primary_key=True)
    transfert = models.ForeignKey('TransfertsStock', models.DO_NOTHING)
    categorie_produit = models.ForeignKey(CategoriesProduits, models.DO_NOTHING)
    quantite_pieces = models.IntegerField()
    poids_kg = models.DecimalField(max_digits=12, decimal_places=3)

    class Meta:
        managed = False
        db_table = 'lignes_transfert'
        unique_together = (('transfert', 'categorie_produit'),)


class LignesVente(models.Model):
    id = models.BigAutoField(primary_key=True)
    vente = models.ForeignKey('Ventes', models.DO_NOTHING)
    categorie_produit = models.ForeignKey(CategoriesProduits, models.DO_NOTHING)
    designation = models.CharField(max_length=200)
    unite_vente = models.CharField(max_length=10)
    quantite = models.DecimalField(max_digits=12, decimal_places=3)
    prix_unitaire = models.DecimalField(max_digits=15, decimal_places=2)
    remise = models.DecimalField(max_digits=15, decimal_places=2)
    montant_ligne = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'lignes_vente'


class Lots(models.Model):
    id = models.BigAutoField(primary_key=True)
    code_lot = models.CharField(unique=True, max_length=50)
    conteneur = models.ForeignKey(Conteneurs, models.DO_NOTHING)
    categorie_lot = models.ForeignKey(CategoriesLots, models.DO_NOTHING)
    poids_kg = models.DecimalField(max_digits=10, decimal_places=2)
    prix_achat = models.DecimalField(max_digits=15, decimal_places=2)
    date_creation = models.DateField()
    date_reception = models.DateField(blank=True, null=True)
    statut_logistique = models.CharField(max_length=30)
    statut_ouverture = models.CharField(max_length=20)
    date_ouverture = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'lots'


class Moratoires(models.Model):
    id = models.BigAutoField(primary_key=True)
    vente = models.ForeignKey('Ventes', models.DO_NOTHING)
    date_debut = models.DateField()
    date_echeance = models.DateField()
    montant_concerne = models.DecimalField(max_digits=15, decimal_places=2)
    type_moratoire = models.CharField(max_length=20)
    motif = models.TextField(blank=True, null=True)
    statut = models.CharField(max_length=20)
    autorise_par = models.ForeignKey('Users', models.DO_NOTHING, db_column='autorise_par')
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'moratoires'


class MouvementsStock(models.Model):
    id = models.BigAutoField(primary_key=True)
    type_mouvement = models.CharField(max_length=30)
    depot_depart = models.ForeignKey(Depots, models.DO_NOTHING, blank=True, null=True)
    depot_arrivee = models.ForeignKey(Depots, models.DO_NOTHING, related_name='mouvementsstock_depot_arrivee_set', blank=True, null=True)
    lot = models.ForeignKey(Lots, models.DO_NOTHING, blank=True, null=True)
    categorie_produit = models.ForeignKey(CategoriesProduits, models.DO_NOTHING, blank=True, null=True)
    quantite_pieces = models.IntegerField()
    poids_kg = models.DecimalField(max_digits=12, decimal_places=3)
    reference_document = models.CharField(max_length=100, blank=True, null=True)
    utilisateur = models.ForeignKey('Users', models.DO_NOTHING)
    date_mouvement = models.DateTimeField()
    statut = models.CharField(max_length=20)
    commentaire = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'mouvements_stock'


class OuverturesLots(models.Model):
    id = models.BigAutoField(primary_key=True)
    lot = models.OneToOneField(Lots, models.DO_NOTHING)
    depot = models.ForeignKey(Depots, models.DO_NOTHING)
    utilisateur = models.ForeignKey('Users', models.DO_NOTHING)
    date_ouverture = models.DateTimeField()
    commentaire = models.TextField(blank=True, null=True)
    statut = models.CharField(max_length=20)

    class Meta:
        managed = False
        db_table = 'ouvertures_lots'


class Paiements(models.Model):
    id = models.BigAutoField(primary_key=True)
    vente = models.ForeignKey('Ventes', models.DO_NOTHING)
    montant = models.DecimalField(max_digits=15, decimal_places=2)
    date_paiement = models.DateTimeField()
    mode_paiement = models.CharField(max_length=30)
    reference = models.CharField(max_length=100, blank=True, null=True)
    utilisateur = models.ForeignKey('Users', models.DO_NOTHING)
    statut = models.CharField(max_length=20)
    commentaire = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'paiements'


class QrCodes(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(unique=True, max_length=100)
    lot = models.OneToOneField(Lots, models.DO_NOTHING)
    version = models.IntegerField()
    date_generation = models.DateTimeField()
    date_envoi_fournisseur = models.DateTimeField(blank=True, null=True)
    date_activation = models.DateTimeField(blank=True, null=True)
    actif = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'qr_codes'
        unique_together = (('lot', 'version'),)


class Roles(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(unique=True, max_length=30)
    nom = models.CharField(max_length=80)
    description = models.TextField(blank=True, null=True)
    actif = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'roles'


class Stocks(models.Model):
    id = models.BigAutoField(primary_key=True)
    depot = models.ForeignKey(Depots, models.DO_NOTHING)
    categorie_produit = models.ForeignKey(CategoriesProduits, models.DO_NOTHING)
    quantite_pieces = models.IntegerField()
    poids_kg = models.DecimalField(max_digits=12, decimal_places=3)
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'stocks'
        unique_together = (('depot', 'categorie_produit'),)


class TransfertsStock(models.Model):
    id = models.BigAutoField(primary_key=True)
    reference_transfert = models.CharField(unique=True, max_length=50)
    depot_depart = models.ForeignKey(Depots, models.DO_NOTHING)
    depot_arrivee = models.ForeignKey(Depots, models.DO_NOTHING, related_name='transfertsstock_depot_arrivee_set')
    utilisateur = models.ForeignKey('Users', models.DO_NOTHING)
    date_transfert = models.DateTimeField()
    statut = models.CharField(max_length=20)
    motif = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'transferts_stock'


class UserDepots(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey('Users', models.DO_NOTHING)
    depot = models.ForeignKey(Depots, models.DO_NOTHING)
    date_debut = models.DateField()
    date_fin = models.DateField(blank=True, null=True)
    actif = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'user_depots'
        unique_together = (('user', 'depot'),)


class Users(models.Model):
    id = models.BigAutoField(primary_key=True)
    username = models.CharField(unique=True, max_length=100)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=30, blank=True, null=True)
    email = models.CharField(max_length=254, blank=True, null=True)
    role = models.ForeignKey(Roles, models.DO_NOTHING)
    depot = models.ForeignKey(Depots, models.DO_NOTHING, blank=True, null=True)
    is_active = models.BooleanField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'users'


class Ventes(models.Model):
    id = models.BigAutoField(primary_key=True)
    numero_vente = models.CharField(unique=True, max_length=50)
    client = models.ForeignKey(Clients, models.DO_NOTHING, blank=True, null=True)
    depot = models.ForeignKey(Depots, models.DO_NOTHING)
    vendeur = models.ForeignKey(Users, models.DO_NOTHING)
    date_vente = models.DateTimeField()
    montant_total = models.DecimalField(max_digits=15, decimal_places=2)
    statut = models.CharField(max_length=20)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'ventes'
