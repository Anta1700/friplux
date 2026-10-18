from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("qr/<int:pk>.png", views.qr_code_png, name="qr_code_png"),
    path("etiquettes/conteneur/<int:conteneur_id>.pdf", views.etiquettes_conteneur, name="etiquettes_conteneur"),
]
