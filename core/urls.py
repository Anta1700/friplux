from django.contrib.auth import views as auth_views
from django.urls import path

from . import views, views_compte, views_scan, views_stock, views_vente

app_name = "core"

urlpatterns = [
    path("", views_scan.accueil, name="accueil"),
    path("sante/", views.sante, name="sante"),
    path("connexion/", auth_views.LoginView.as_view(template_name="core/connexion.html"), name="connexion"),
    path("deconnexion/", auth_views.LogoutView.as_view(next_page="core:connexion"), name="deconnexion"),
    path("mot-de-passe/", views_compte.mot_de_passe, name="mot_de_passe"),
    path("comptes/", views_compte.comptes, name="comptes"),
    path("comptes/<int:pk>/mot-de-passe-provisoire/", views_compte.compte_mot_de_passe_provisoire,
         name="compte_mot_de_passe_provisoire"),
    path("scanner/", views_scan.scanner, name="scanner"),
    path("balles/<str:code_lot>/", views_scan.fiche_balle, name="fiche_balle"),
    path("ventes/", views_vente.ventes, name="ventes"),
    path("ventes/scanner/", views_vente.vente_scanner, name="vente_scanner"),
    path("ventes/ajouter/<str:code_lot>/", views_vente.vente_ajouter, name="vente_ajouter"),
    path("ventes/ligne/<int:ligne_id>/retirer/", views_vente.vente_retirer, name="vente_retirer"),
    path("ventes/abandonner/", views_vente.vente_abandonner, name="vente_abandonner"),
    path("ventes/valider/", views_vente.vente_valider, name="vente_valider"),
    path("ventes/client/", views_vente.client_par_telephone, name="client_par_telephone"),
    path("ventes/<int:pk>/", views_vente.vente_detail, name="vente_detail"),
    path("f/<str:jeton>/", views_vente.facture_client, name="facture_client"),
    path("f/<str:jeton>/facture.pdf", views_vente.facture_client_pdf, name="facture_client_pdf"),
    path("ventes/<int:pk>/facture.pdf", views_vente.facture_pdf_vue, name="facture_pdf"),
    path("ventes/<int:pk>/encaisser/", views_vente.vente_encaisser, name="vente_encaisser"),
    path("stock/", views_stock.stock, name="stock"),
    path("transferts/envoi/", views_stock.transfert_envoi, name="transfert_envoi"),
    path("transferts/envoi/scanner/", views_stock.transfert_scanner, name="transfert_scanner"),
    path("transferts/envoi/ajouter/<str:code_lot>/", views_stock.transfert_ajouter, name="transfert_ajouter"),
    path("transferts/envoi/ligne/<int:mouvement_id>/retirer/", views_stock.transfert_retirer, name="transfert_retirer"),
    path("transferts/envoi/abandonner/", views_stock.transfert_abandonner, name="transfert_abandonner"),
    path("transferts/envoi/envoyer/", views_stock.transfert_envoyer, name="transfert_envoyer"),
    path("transferts/<int:pk>/", views_stock.transfert_detail, name="transfert_detail"),
    path("transferts/<int:pk>/cloturer/", views_stock.transfert_cloturer, name="transfert_cloturer"),
    path("transferts/<int:pk>/annuler/", views_stock.transfert_annuler, name="transfert_annuler"),
    path("statistiques/ventes/", views_vente.statistiques_ventes, name="statistiques_ventes"),
    path("statistiques/", views_scan.statistiques, name="statistiques"),
    path("qr/<int:pk>.png", views.qr_code_png, name="qr_code_png"),
    path("etiquettes/conteneur/<int:conteneur_id>.pdf", views.etiquettes_conteneur, name="etiquettes_conteneur"),
]
