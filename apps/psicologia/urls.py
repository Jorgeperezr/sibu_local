from django.urls import path

from . import views

app_name = "psicologia"

urlpatterns = [
    path("", views.bandeja, name="bandeja"),
    path("iniciar/<int:expediente_id>/", views.iniciar, name="iniciar"),
    path("proceso/<int:pk>/", views.proceso, name="proceso"),
]
