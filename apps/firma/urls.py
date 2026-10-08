from django.urls import path

from . import api, views

app_name = "firma"

urlpatterns = [
    path("solicitar/<int:atencion_id>/", views.solicitar, name="solicitar"),
    path("panel/<int:pk>/", views.panel, name="panel"),
    path("estado/<int:pk>/", api.estado_solicitud, name="estado"),
    path("subir-firmado/<int:pk>/", views.subir_firmado, name="subir_firmado"),
    path("descargar/<int:pk>/", views.descargar, name="descargar"),
    path("descargar-original/<int:pk>/", views.descargar_original, name="descargar_original"),
]
