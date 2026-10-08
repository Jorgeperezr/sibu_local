from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "expediente"

urlpatterns = [
    # La ruta obvia no debe morir en 404: lleva a la búsqueda de expedientes.
    path(
        "", RedirectView.as_view(pattern_name="expediente:buscar", permanent=False), name="indice"
    ),
    path("buscar/", views.buscar, name="buscar"),
    path("nuevo/", views.nuevo, name="nuevo"),
    path("lote/", views.alta_masiva, name="alta_masiva"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/alertas/", views.alertas, name="alertas"),
    path("<int:pk>/ajustar/", views.ajustar, name="ajustar"),
    path("<int:pk>/datos/", views.datos, name="datos"),
]
