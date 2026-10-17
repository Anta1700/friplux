from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("qr/<int:pk>.png", views.qr_code_png, name="qr_code_png"),
]
