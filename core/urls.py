from django.contrib.auth import views as auth_views
from django.urls import path

from . import views, views_scan

app_name = "core"

urlpatterns = [
    path("", views_scan.accueil, name="accueil"),
    path("connexion/", auth_views.LoginView.as_view(template_name="core/connexion.html"), name="connexion"),
    path("deconnexion/", auth_views.LogoutView.as_view(next_page="core:connexion"), name="deconnexion"),
    path("scanner/", views_scan.scanner, name="scanner"),
    path("balles/<str:code_lot>/", views_scan.fiche_balle, name="fiche_balle"),
    path("statistiques/", views_scan.statistiques, name="statistiques"),
    path("qr/<int:pk>.png", views.qr_code_png, name="qr_code_png"),
    path("etiquettes/conteneur/<int:conteneur_id>.pdf", views.etiquettes_conteneur, name="etiquettes_conteneur"),
]
